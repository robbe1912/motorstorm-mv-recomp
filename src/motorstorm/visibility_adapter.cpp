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
void game_original_visibility_box(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_000083A0(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_000083C0(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_000083C8(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_000083E0(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_00008418(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_00008448(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_00008450(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_00008440(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_0000849C(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_000084A0(spu_context*);
void motorstorm_visibility_planes(spu_context*);
// Generated in the ignored copied TU; includes code and its permutation table.
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
    game_original_visibility_box(ctx);
}
bool pending(const spu_context* ctx) {
    const volatile std::uint32_t& events = ctx->event_status;
    return ctx->int_enable && (events & ctx->event_mask);
}
const char* admission(const spu_context* ctx) {
    if (!ctx || ctx->ls != ctx->ls_store) return "local-store ownership";
    if (ctx->pc != 0x83a0 || ctx->status != 1) return "entry state";
    if (ctx->list_stall_mask || pending(ctx)) return "pending DMA/event";
    if (state().instrumentation || g_spu_ls_watch_n > 0) return "active instrumentation";
    if (!game_visibility_code_matches(ctx)) return "code/data identity";
    return nullptr;
}
std::uint32_t big_word(const unsigned char* p) {
    return (std::uint32_t(p[0]) << 24) | (std::uint32_t(p[1]) << 16) |
           (std::uint32_t(p[2]) << 8) | p[3];
}
float float_word(std::uint32_t word) { float value; std::memcpy(&value, &word, 4); return value; }
bool supported_corners(const VisibilityCorners& corners) {
    // Every coefficient lane is a corner coordinate or 1. With magnitudes at
    // most 2^32, retained nonpreferred dot products remain below 2^67: skipped
    // comparisons cannot lose an invalid flag from exponent-255 intermediates.
    for (const auto& point : corners) for (float value : {point.x,point.y,point.z}) {
        std::uint32_t word; std::memcpy(&word, &value, 4);
        if ((word & 0x7fffffffu) > 0x4f800000u) return false;
    }
    return true;
}
struct Prepared {
    VisibilityCorners corners;
    VisibilityPlaneResult result;
};
// ABI marshalling only; geometry lives in the ordinary typed math operation.
// Preserve every lane, including scratch that is not a preferred scalar.
void commit(spu_context* ctx, const Prepared& prepared) {
    constexpr unsigned registers[8][3] = {{19,41,40},{18,39,38},{17,37,36},{16,35,34},
                                         {15,33,32},{22,31,30},{20,29,28},{21,27,26}};
    for (unsigned i = 0; i < 8; ++i) {
        const auto& point = prepared.corners[i];
        const float values[] = {point.x,point.y,point.z,1.0f};
        for (unsigned component = 0; component < 3; ++component)
            for (unsigned lane = 0; lane < 4; ++lane)
                std::memcpy(&ctx->gpr[registers[i][component]]._u32[lane],
                            &values[(lane + component) % 4], 4);
    }
    const auto skipped = std::uint32_t(prepared.result.tested - 1);
    ctx->gpr[25] = ctx->gpr[5];
    for (unsigned lane = 0; lane < 4; ++lane) {
        ctx->gpr[13]._u32[lane] = 0;
        ctx->gpr[14]._u32[lane] = ctx->gpr[4]._u32[lane] + skipped * 16;
        ctx->gpr[23]._u32[lane] = skipped;
    }
    ctx->pc = 0x84a0;
}
Function finish(spu_context* copy, std::size_t count, bool entry) {
    const Function saved = g_spu_trampoline_fn;
    struct Restore { Function value; ~Restore() { g_spu_trampoline_fn = value; } } restore{saved};
    const auto return_pc = copy->gpr[0]._u32[0];
    Function next = entry ? game_original_visibility_box :
                            jobmod_056ac0eea1a6_e12270_spu_func_000084A0;
    const auto bound = entry ? count * 2 + 10 : 3;
    for (std::size_t step = 0; step < bound; ++step) {
        g_spu_trampoline_fn = nullptr; next(copy); next = g_spu_trampoline_fn;
        if (copy->pc == return_pc && (!next || next == spu_indirect_branch)) return next;
        if (next == motorstorm_visibility_planes ||
            next == jobmod_056ac0eea1a6_e12270_spu_func_000083A0)
            next = game_original_visibility_box;
        bool allowed = next == jobmod_056ac0eea1a6_e12270_spu_func_000084A0 ||
                       next == jobmod_056ac0eea1a6_e12270_spu_func_00008440 ||
                       next == jobmod_056ac0eea1a6_e12270_spu_func_0000849C;
        if (entry) for (Function setup : {game_original_visibility_box,
            jobmod_056ac0eea1a6_e12270_spu_func_000083C0,
            jobmod_056ac0eea1a6_e12270_spu_func_000083C8,
            jobmod_056ac0eea1a6_e12270_spu_func_000083E0,
            jobmod_056ac0eea1a6_e12270_spu_func_00008418,
            jobmod_056ac0eea1a6_e12270_spu_func_00008448,
            jobmod_056ac0eea1a6_e12270_spu_func_00008450}) allowed |= next == setup;
        if (!allowed) throw std::runtime_error("Visibility reference escaped its operation");
    }
    throw std::runtime_error("Visibility reference exceeded bounded operation");
}
void compare(spu_context* ctx, const Prepared& prepared, std::size_t count) {
    auto reference = std::make_unique<spu_context>();
    auto candidate = std::make_unique<spu_context>();
    std::memcpy(reference.get(), ctx, sizeof(*ctx));
    std::memcpy(candidate.get(), ctx, sizeof(*ctx));
    reference->ls = reference->ls_store; candidate->ls = candidate->ls_store;
    const auto reference_exit = finish(reference.get(), count, true);
    commit(candidate.get(), prepared);
    const auto candidate_exit = finish(candidate.get(), 1, false);
    candidate->ls = reference->ls;
    if (reference_exit != candidate_exit || std::memcmp(reference.get(), candidate.get(), sizeof(*ctx))) {
        std::fputs("NATIVE_VISIBILITY_SHADOW_MISMATCH\n", stderr); std::abort();
    }
    ++state().compared;
}
} // namespace

extern "C" void motorstorm_visibility_planes(spu_context* ctx) try {
    auto& config = state();
    if (config.mode == Mode::reference) { game_original_visibility_box(ctx); return; }
    if (!config.cpu) { original(ctx, "CPU/OS features"); return; }
    if (const char* reason = admission(ctx)) { original(ctx, reason); return; }
    constexpr std::size_t maximum_planes = 64;
    const auto matrix = ctx->gpr[3]._u32[0], cursor = ctx->gpr[4]._u32[0], count = ctx->gpr[5]._u32[0];
    const auto size = sizeof(ctx->ls_store);
    if ((matrix & 15) || matrix > size || size - matrix < 64 ||
        !count || count > maximum_planes || (cursor & 15) ||
        cursor > size || count * 16 > size - cursor) {
        original(ctx, "matrix/plane span"); return;
    }
    std::array<unsigned char, 64> matrix_snapshot, argument_snapshot;
    std::array<unsigned char, maximum_planes * 16> snapshot;
    std::memcpy(matrix_snapshot.data(), ctx->ls + matrix, 64);
    std::memcpy(argument_snapshot.data(), &ctx->gpr[0], 16);
    std::memcpy(argument_snapshot.data() + 16, &ctx->gpr[3], 48);
    std::memcpy(snapshot.data(), ctx->ls + cursor, count * 16);
    for (std::size_t byte = 0; byte < count * 16; byte += 4)
        if ((big_word(snapshot.data() + byte) & 0x7fffffffu) > 0x4f800000u) {
            original(ctx, "plane numeric range"); return;
        }
    const auto point = [&](unsigned row) {
        const auto* p = matrix_snapshot.data() + row * 16;
        return VisibilityPoint{float_word(big_word(p)),float_word(big_word(p+4)),float_word(big_word(p+8))};
    };
    VisibilityBox box{point(0), {}};
    for (unsigned i = 0; i < 3; ++i)
        box.axes[i] = {point(i + 1),float_word(big_word(matrix_snapshot.data() + (i+1)*16 + 12))};
    std::array<VisibilityPlane, maximum_planes> planes;
    for (std::size_t i = 0; i < count; ++i) {
        const auto* p = snapshot.data() + i * 16;
        planes[i] = {float_word(big_word(p)),float_word(big_word(p+4)),
                     float_word(big_word(p+8)),float_word(big_word(p+12))};
    }
    Prepared prepared;
    try {
        prepared.corners = make_visibility_corners(box);
        if (!supported_corners(prepared.corners)) { original(ctx, "corner numeric range"); return; }
        prepared.result = test_visibility_planes(planes.data(), count, prepared.corners);
    } catch (const std::invalid_argument&) { original(ctx, "nonfinite input"); return; }
      catch (const std::range_error&) { original(ctx, "numeric range"); return; }
    if (!prepared.result.tested || prepared.result.tested > count)
        throw std::runtime_error("Invalid native visibility prefix");
#ifdef MOTORSTORM_VISIBILITY_FIXTURE
    native_visibility_fixture_after_math(ctx);
#endif
    if (const char* reason = admission(ctx)) { original(ctx, reason); return; }
    if (std::memcmp(argument_snapshot.data(), &ctx->gpr[0], 16) ||
        std::memcmp(argument_snapshot.data()+16, &ctx->gpr[3], 48) ||
        std::memcmp(matrix_snapshot.data(), ctx->ls + matrix, 64) ||
        std::memcmp(snapshot.data(), ctx->ls + cursor, count * 16)) {
        original(ctx, "input changed"); return;
    }
    if (config.mode == Mode::shadow) compare(ctx, prepared, count);
    else commit(ctx, prepared);
    const auto completed = ++config.completed;
    if (completed == 1 || completed % 1024 == 0)
        std::fprintf(stderr, "[native-visibility] completed=%llu compared=%llu fallbacks=%llu\n",
                     completed, config.compared.load(), config.fallbacks.load());
    if (config.mode == Mode::shadow) game_original_visibility_box(ctx);
    else jobmod_056ac0eea1a6_e12270_spu_func_000084A0(ctx);
} catch (const std::exception& error) {
    std::fprintf(stderr, "NATIVE_VISIBILITY_ERROR %s\n", error.what()); std::abort();
} catch (...) {
    std::fputs("NATIVE_VISIBILITY_ERROR unknown exception\n", stderr); std::abort();
}
