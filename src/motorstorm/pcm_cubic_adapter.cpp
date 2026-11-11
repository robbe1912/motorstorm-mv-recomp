#include "spu_context.h"
#include "spu_lockstep.h"
#include "spu_native_owned.h"
#include "native_cpu.h"
#include "pcm_cubic.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cfenv>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <immintrin.h>
#include <memory>
#include <stdexcept>
#include <vector>

extern "C" {
void game_original_pcm_cubic(spu_context*);
void motorstorm_pcm_cubic(spu_context*);
void spu_0000_at_00EDE500_spu_func_00009D5C(spu_context*);
int game_pcm_cubic_code_matches(const spu_context*);
void (*spu_lookup(std::uint32_t, int))(spu_context*);
}

namespace {
using namespace motorstorm::game;
enum class Mode { reference, shadow, native };
struct Policy {
    Mode mode = Mode::reference;
    bool cpu = supports_native_world_transforms();
    std::atomic<unsigned long long> calls{0}, completed{0}, compared{0}, fallback{0};
    Policy() {
        const auto text = std::getenv("MS_NATIVE_PCM_CUBIC");
        if (!text || !std::strcmp(text, "0")) {}
        else if (!std::strcmp(text, "shadow")) mode = Mode::shadow;
        else if (!std::strcmp(text, "1")) mode = Mode::native;
        else throw std::invalid_argument("MS_NATIVE_PCM_CUBIC must be 0, shadow or 1");
        std::fprintf(stderr, "[native-pcm] mode=%s cpu=%d\n", text ? text : "0", int(cpu));
    }
};
Policy& policy() { static Policy value; return value; }

struct HostFpState {
    std::fenv_t environment;
    unsigned csr;
    HostFpState() : csr(_mm_getcsr()) {
        if (std::fegetenv(&environment)) throw std::runtime_error("Cannot read caller FP state");
    }
    void restore() const {
        if (std::fesetenv(&environment)) throw std::runtime_error("Cannot restore caller FP state");
        _mm_setcsr(csr);
    }
};

bool overlaps(std::uint32_t a, std::uint32_t an, std::uint32_t b, std::uint32_t bn) {
    return a < std::uint64_t(b) + bn && b < std::uint64_t(a) + an;
}

// Integer inspection avoids changing the caller's floating-point state.
bool positive_floor(std::uint32_t bits, std::uint32_t& integer) {
    if ((bits >> 31) && (bits & 0x7fffffffu)) return false;
    const auto exponent = (bits >> 23) & 255;
    if (exponent >= 145) return false;
    if (exponent < 127) { integer = 0; return true; }
    integer = ((bits & 0x7fffffu) | 0x800000u) >> (150 - exponent);
    return true;
}

struct Prepared {
    std::vector<std::int16_t> samples;
    std::array<float, 1008> output;
    PcmCubicState phase;
    std::uint32_t destination;
};

const char* prepare(spu_context* ctx, Prepared& p) {
    if (!policy().cpu) return "CPU/OS";
    if (!ctx || ctx->ls != ctx->ls_store || ctx->status != SPU_STATUS_RUNNING)
        return "context ownership/state";
    if (ctx->image_id <= 0 || spu_lookup(0x9d5c, ctx->image_id) != spu_0000_at_00EDE500_spu_func_00009D5C)
        return "registered image";
    for (const auto& owner : ctx->resident_code) {
        if (0x9d5cu >= owner.lsa && std::uint64_t(0x9d5c) < std::uint64_t(owner.lsa) + owner.size) {
            if (owner.image_id != ctx->image_id || owner.rel ||
                std::uint64_t(owner.lsa) + owner.size < 0xa1d0) return "resident owner";
            break;
        }
    }
    if (ctx->irq_frame || ctx->irq_saved || ctx->list_stall_mask ||
        (ctx->mfc_tag_status & ctx->mfc_tag_mask) != ctx->mfc_tag_mask ||
        (ctx->int_enable && (ctx->event_status & ctx->event_mask))) return "IRQ/DMA/event";
    if (ctx->interp_span_lo || ctx->interp_span_hi) return "interpreter scope";
    if (g_spu_ls_watch_n || g_spu_ls_probe || g_spu_smc_watch ||
        spu_native_owned_observed() || yz_lockstep_enabled() ||
        std::getenv("SPU_INTERP_STATS")) return "execution observer";
    if (!game_pcm_cubic_code_matches(ctx)) return "code/table identity";
    for (unsigned i = 0; i < 4; ++i) if (ctx->gpr[74]._u32[i]) return "loop entry";
    const auto stack = ctx->gpr[1]._u32[0], source = ctx->gpr[80]._u32[0];
    const auto table = ctx->gpr[81]._u32[0];
    p.destination = ctx->gpr[69]._u32[0];
    if ((stack | source | table | p.destination) & 15u ||
        stack > SPU_LS_SIZE - 368 || table > SPU_LS_SIZE - 224 ||
        source >= SPU_LS_SIZE || p.destination > SPU_LS_SIZE - 4096) return "LS bounds/alignment";
    for (auto pair : {std::pair{63u, 0xf9f0u}, {66u, 0xf9e0u}, {67u, 0xf9d0u}, {68u, 0xf9c0u}}) {
        const auto expected = spu_ls_read128(ctx, pair.second);
        if (std::memcmp(&expected, &ctx->gpr[pair.first], 16)) return "shuffle state";
    }
    for (auto bits : ctx->gpr[64]._u32) if (bits != 0x3f000000u) return "coefficient";
    if (std::memcmp(ctx->ls + table, ctx->ls + 0xfa50, 224)) return "sample permutation table";
    std::uint32_t largest = 0, step_ceiling = 0;
    for (unsigned group = 0; group < 4; ++group) {
        for (unsigned lane = 0; lane < 4; ++lane) {
            const auto bits = ctx->gpr[73 - group]._u32[lane]; std::uint32_t index;
            if (!positive_floor(bits, index)) return "phase range";
            largest = std::max(largest, index);
            p.phase.positions[group * 4 + lane] = std::bit_cast<float>(bits);
        }
    }
    for (unsigned lane = 0; lane < 4; ++lane) {
        const auto bits = ctx->gpr[65]._u32[lane];
        if ((bits & 0x7f800000u) == 0x7f800000u) return "phase advance";
        p.phase.advance[lane] = std::bit_cast<float>(bits);
        if (!(bits >> 31)) {
            std::uint32_t floor;
            if (!positive_floor(bits, floor)) return "phase advance";
            const auto exponent = (bits >> 23) & 255;
            const auto fractional = exponent && (exponent < 127 ||
                (bits & ((1u << (150 - exponent)) - 1)));
            // Integer ceiling bounds positive advances without host FP work.
            // Subnormals are zero under the admitted flush contract.
            step_ceiling = std::max(step_ceiling, floor + fractional);
        }
    }
    const auto count = std::uint64_t(largest) + 252 * std::uint64_t(step_ceiling) + 4;
    if (count > (SPU_LS_SIZE - source) / 2) return "PCM window";
    const auto bytes = std::uint32_t(count * 2);
    if (overlaps(p.destination, 4096, source, bytes) ||
        overlaps(p.destination, 4096, stack, 368) ||
        overlaps(p.destination, 4096, table, 224) ||
        overlaps(p.destination, 4096, 0x3000, 0xd3a0)) return "output alias";
    p.samples.resize(std::size_t(count));
    for (std::size_t i = 0; i < count; ++i) {
        const auto bits = std::uint16_t((ctx->ls[source + i * 2] << 8) | ctx->ls[source + i * 2 + 1]);
        p.samples[i] = std::bit_cast<std::int16_t>(bits);
    }
    try { resample_pcm16_cubic(p.samples, p.phase, p.output); }
    catch (const std::invalid_argument&) { return "numeric/source window"; }
    return nullptr;
}

void commit(spu_context* ctx, const Prepared& p) {
    for (unsigned i = 0; i < 252; ++i) {
        u128 value; std::memcpy(&value, p.output.data() + i * 4, 16);
        spu_ls_write128(ctx, p.destination + i * 16, value);
    }
    for (unsigned group = 0; group < 4; ++group)
        std::memcpy(&ctx->gpr[73 - group], p.phase.positions.data() + group * 4, 16);
    for (unsigned lane = 0; lane < 4; ++lane) ctx->gpr[69]._u32[lane] += 4032;
    for (auto& bits : ctx->gpr[74]._u32) bits = 63;
    // Preserve observable scratch lanes, stack restoration and the real return.
    // Only this final 16-sample iteration still uses the original operation.
    game_original_pcm_cubic(ctx);
}

void execute(spu_context* ctx) {
    const HostFpState incoming;
    auto& control = policy(); ++control.calls;
    if (control.mode == Mode::reference) { incoming.restore(); game_original_pcm_cubic(ctx); return; }
    thread_local Prepared prepared;
    if (const auto reason = prepare(ctx, prepared)) {
        if (++control.fallback == 1) std::fprintf(stderr, "[native-pcm] fallback=%s\n", reason);
        incoming.restore(); game_original_pcm_cubic(ctx); return;
    }
    if (control.mode == Mode::shadow) {
        auto reference = std::make_unique<spu_context>();
        auto native = std::make_unique<spu_context>();
        std::memcpy(reference.get(), ctx, sizeof(*ctx));
        std::memcpy(native.get(), reference.get(), sizeof(*ctx));
        reference->ls = reference->ls_store; native->ls = native->ls_store;
        incoming.restore();
        const auto queued = g_spu_trampoline_fn;
        game_original_pcm_cubic(reference.get());
        const auto reference_queue = g_spu_trampoline_fn;
        const auto reference_csr = _mm_getcsr();
        const auto reference_exceptions = std::fetestexcept(FE_ALL_EXCEPT);
        g_spu_trampoline_fn = queued;
        incoming.restore();
        commit(native.get(), prepared);
        reference->ls = native->ls;
        if (std::memcmp(reference.get(), native.get(), sizeof(*ctx)) ||
            g_spu_trampoline_fn != reference_queue || _mm_getcsr() != reference_csr ||
            std::fetestexcept(FE_ALL_EXCEPT) != reference_exceptions)
            throw std::runtime_error("PCM cubic shadow state/FP/return mismatch");
        // External mailbox producers may update the live context while these
        // pure operations run. Compare identical private snapshots, then write
        // only the operation's actual outputs to the live context once.
        g_spu_trampoline_fn = queued;
        incoming.restore();
        commit(ctx, prepared);
        ++control.compared;
    } else { incoming.restore(); commit(ctx, prepared); }
    const HostFpState outgoing;
    const auto completed = ++control.completed;
    if (completed == 1 || completed % 4096 == 0)
        std::fprintf(stderr, "[native-pcm] completed=%llu compared=%llu fallback=%llu\n",
            completed, control.compared.load(), control.fallback.load());
    outgoing.restore();
}
} // namespace

extern "C" void motorstorm_pcm_cubic(spu_context* ctx) {
    try { execute(ctx); }
    catch (const std::exception& error) {
        std::fprintf(stderr, "NATIVE_PCM_ERROR %s\n", error.what()); std::abort();
    }
}
