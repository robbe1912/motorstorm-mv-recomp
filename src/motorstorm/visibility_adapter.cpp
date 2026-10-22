#ifdef MOTORSTORM_VISIBILITY_FIXTURE
#include "native_visibility_api.h"
#else
#include "spu_context.h"
#endif
#include "native_cpu.h"
#include "visibility_planes.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <memory>
#include <stdexcept>

extern "C" {
void game_original_visibility_planes(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_00008440(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_0000849C(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_000084A0(spu_context*);
void motorstorm_visibility_planes(spu_context*);
// Generated only in the ignored copied TU from identity-verified original bytes.
int game_visibility_code_matches(const spu_context*);
}

namespace {
using namespace motorstorm::game;
using Function = void (*)(spu_context*);
enum class Mode { reference, shadow, native };
struct State {
    Mode mode = Mode::reference;
    bool cpu, instrumentation;
    std::atomic<unsigned long long> completed{0}, fallbacks{0}, compared{0};
    State() : cpu(supports_native_world_transforms()), instrumentation(false) {
#ifdef MOTORSTORM_VISIBILITY_FIXTURE
        cpu = cpu && native_visibility_fixture_cpu();
#endif
        const char* mode_text = std::getenv("MS_NATIVE_VISIBILITY");
        if (!mode_text || !std::strcmp(mode_text, "0")) {}
        else if (!std::strcmp(mode_text, "shadow")) mode = Mode::shadow;
        else if (!std::strcmp(mode_text, "1")) mode = Mode::native;
        else throw std::invalid_argument("MS_NATIVE_VISIBILITY must be 0, shadow or 1");
        for (const char* name : {"SPU_LS_LOWREAD", "SPU_LS_WATCH", "SPU_SMC_WATCH", "SPU_PCHIST"})
            instrumentation |= std::getenv(name) != nullptr;
        std::fprintf(stderr, "[native-visibility] mode=%s cpu=%d\n",
                     mode_text ? mode_text : "0", int(cpu));
    }
};

State& state() { static State value; return value; }
void original(spu_context* ctx, const char* reason) {
    const auto count = ++state().fallbacks;
    std::fprintf(stderr, "[native-visibility] ORIGINAL fallback=%llu reason=%s\n", count, reason);
    game_original_visibility_planes(ctx);
}

bool pending(const spu_context* ctx) {
    // Match the runtime drain's event boundary; reread after pure computation.
    const volatile std::uint32_t& events = ctx->event_status;
    return ctx->int_enable && (events & ctx->event_mask);
}

const char* admission(const spu_context* ctx) {
    if (!ctx || ctx->ls != ctx->ls_store) return "local-store ownership";
    if (ctx->pc != 0x84a0 || ctx->status != 1) return "entry state";
    if (ctx->list_stall_mask || pending(ctx)) return "pending DMA/event";
    if (state().instrumentation || g_spu_ls_watch_n > 0) return "active instrumentation";
    if (!game_visibility_code_matches(ctx)) return "code identity";
    return nullptr;
}

std::uint32_t big_word(const unsigned char* p) {
    return (std::uint32_t(p[0]) << 24) | (std::uint32_t(p[1]) << 16) |
           (std::uint32_t(p[2]) << 8) | p[3];
}
float float_word(std::uint32_t word) { float value; std::memcpy(&value, &word, 4); return value; }

// Run only this operation's retained blocks on a clone. Never dispatch into a
// caller, process an interrupt or consume an unrelated queued trampoline.
Function finish(spu_context* copy, std::size_t count) {
    const Function saved = g_spu_trampoline_fn;
    struct Restore { Function value; ~Restore() { g_spu_trampoline_fn = value; } } restore{saved};
    const auto return_pc = copy->gpr[0]._u32[0];
    Function next = game_original_visibility_planes;
    for (std::size_t step = 0; step < count * 2 + 3; ++step) {
        g_spu_trampoline_fn = nullptr;
        next(copy);
        next = g_spu_trampoline_fn;
        if (copy->pc == return_pc && (!next || next == spu_indirect_branch)) return next;
        if (next == motorstorm_visibility_planes ||
            next == jobmod_056ac0eea1a6_e12270_spu_func_000084A0)
            next = game_original_visibility_planes;
        if (next != game_original_visibility_planes &&
            next != jobmod_056ac0eea1a6_e12270_spu_func_00008440 &&
            next != jobmod_056ac0eea1a6_e12270_spu_func_0000849C)
            throw std::runtime_error("Visibility reference escaped its operation");
    }
    throw std::runtime_error("Visibility reference exceeded bounded operation");
}

void advance(spu_context* ctx, std::size_t skipped) {
    for (unsigned lane = 0; lane < 4; ++lane) {
        ctx->gpr[14]._u32[lane] += std::uint32_t(skipped * 16);
        ctx->gpr[23]._u32[lane] += std::uint32_t(skipped);
    }
}

void compare(spu_context* ctx, const VisibilityPlaneResult& result, std::size_t count) {
    auto reference = std::make_unique<spu_context>();
    auto candidate = std::make_unique<spu_context>();
    std::memcpy(reference.get(), ctx, sizeof(*ctx));
    std::memcpy(candidate.get(), ctx, sizeof(*ctx));
    reference->ls = reference->ls_store; candidate->ls = candidate->ls_store;
    const auto reference_exit = finish(reference.get(), count);
    advance(candidate.get(), result.tested - 1);
    const auto candidate_exit = finish(candidate.get(), 1);
    candidate->ls = reference->ls;
    if (reference_exit != candidate_exit || std::memcmp(reference.get(), candidate.get(), sizeof(*ctx))) {
        std::fputs("NATIVE_VISIBILITY_SHADOW_MISMATCH\n", stderr);
        std::abort();
    }
    ++state().compared;
}
} // namespace

extern "C" void motorstorm_visibility_planes(spu_context* ctx) try {
    auto& config = state();
    if (config.mode == Mode::reference) { game_original_visibility_planes(ctx); return; }
    if (!config.cpu) { original(ctx, "CPU/OS features"); return; }
    if (const char* reason = admission(ctx)) { original(ctx, reason); return; }
    constexpr std::size_t maximum_planes = 64;
    const std::uint32_t index = ctx->gpr[23]._u32[0], end = ctx->gpr[25]._u32[0];
    const std::uint32_t cursor = ctx->gpr[14]._u32[0];
    if (index >= end || end - index > maximum_planes || (cursor & 15) ||
        cursor > sizeof(ctx->ls_store) || std::size_t(end - index) * 16 > sizeof(ctx->ls_store) - cursor) {
        original(ctx, "plane span"); return;
    }
    const std::size_t count = end - index;
    std::array<unsigned char, maximum_planes * 16> snapshot;
    std::memcpy(snapshot.data(), ctx->ls + cursor, count * 16);
    std::array<VisibilityPlane, maximum_planes> planes;
    for (std::size_t i = 0; i < count; ++i) {
        const auto* p = snapshot.data() + i * 16;
        planes[i] = {float_word(big_word(p)), float_word(big_word(p + 4)),
                     float_word(big_word(p + 8)), float_word(big_word(p + 12))};
    }
    constexpr unsigned registers[8][3] = {{19,41,40},{18,39,38},{17,37,36},{16,35,34},
                                         {15,33,32},{22,31,30},{20,29,28},{21,27,26}};
    // The retained comparison also visits nonpreferred scratch lanes. Bound
    // their magnitudes without floating arithmetic so skipped iterations cannot
    // lose a host invalid flag from an exponent-255 intermediate. With inputs
    // at most 2^32, three products plus offset stay below 2^67. Unsupported
    // vectors execute the complete original operation, including its FP effects.
    constexpr std::uint32_t maximum_magnitude = 0x4f800000u;
    for (std::size_t byte = 0; byte < count * 16; byte += 4)
        if ((big_word(snapshot.data() + byte) & 0x7fffffffu) > maximum_magnitude) {
            original(ctx, "scratch numeric range"); return;
        }
    for (unsigned lane = 0; lane < 4; ++lane) {
        if ((ctx->gpr[13]._u32[lane] & 0x7fffffffu) > maximum_magnitude) {
            original(ctx, "scratch numeric range"); return;
        }
        for (const auto& corner : registers) for (auto reg : corner)
            if ((ctx->gpr[reg]._u32[lane] & 0x7fffffffu) > maximum_magnitude) {
                original(ctx, "scratch numeric range"); return;
            }
    }
    VisibilityCorners corners;
    for (std::size_t i = 0; i < corners.size(); ++i)
        corners[i] = {float_word(ctx->gpr[registers[i][0]]._u32[0]),
                      float_word(ctx->gpr[registers[i][1]]._u32[0]),
                      float_word(ctx->gpr[registers[i][2]]._u32[0])};
    VisibilityPlaneResult result;
    try { result = test_visibility_planes(planes.data(), count, corners, float_word(ctx->gpr[13]._u32[0])); }
    catch (const std::invalid_argument&) { original(ctx, "nonfinite input"); return; }
    catch (const std::range_error&) { original(ctx, "numeric range"); return; }
    if (!result.tested || result.tested > count) throw std::runtime_error("Invalid native visibility prefix");
#ifdef MOTORSTORM_VISIBILITY_FIXTURE
    native_visibility_fixture_after_math(ctx);
#endif
    if (const char* reason = admission(ctx)) { original(ctx, reason); return; }
    if (std::memcmp(snapshot.data(), ctx->ls + cursor, count * 16)) {
        original(ctx, "input changed"); return;
    }
    if (config.mode == Mode::shadow) compare(ctx, result, count);
    else advance(ctx, result.tested - 1);
    const auto completed = ++config.completed;
    if (completed == 1 || completed % 1024 == 0)
        std::fprintf(stderr, "[native-visibility] completed=%llu compared=%llu fallbacks=%llu\n",
                     completed, config.compared.load(), config.fallbacks.load());
    // Retain the decisive original iteration and its normal exit/drain path.
    game_original_visibility_planes(ctx);
} catch (const std::exception& error) {
    std::fprintf(stderr, "NATIVE_VISIBILITY_ERROR %s\n", error.what());
    std::abort(); // No C++ exception may escape the generated C call boundary.
} catch (...) {
    std::fputs("NATIVE_VISIBILITY_ERROR unknown exception\n", stderr);
    std::abort();
}
