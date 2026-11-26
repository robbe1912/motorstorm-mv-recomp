#pragma once
// Shared parts of the two bound particle adapters of SPU image 213 (jobmod_556b30b5e654_e12e20).
// The build-time binding (scripts/native_game_binding.py) renames each lifted function to
// game_original_... and defines its symbol as a wrapper that calls the native entry here.
// Mode 0 or an unsupported state calls the renamed original. Shadow mode runs the kernel on
// one copy of the context and the original on another copy; a difference stops the process.
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>

#include "spu_context.h"
#include "spu_helpers.h"

#ifdef MOTORSTORM_PARTICLE_FIXTURE
// Fixtures replace the environment and can switch the mode while they run.
extern "C" const char* motorstorm_particle_fixture_option(const char* name);
extern "C" unsigned motorstorm_particle_fixture_generation(void);
#endif

struct MotorstormParticleBindCounts {
    unsigned long long native_calls, compared, fallbacks;
};

namespace motorstorm_particle_bind {
using Function = void (*)(spu_context*);
enum class Mode { reference, shadow, native };
// Transfers that one shadow comparison may step. A batch of 256 records needs about 6000.
constexpr unsigned long long STEP_LIMIT = 1ull << 24;

struct Config {
    Mode mode = Mode::reference;
    const char* text = "0";
    bool instrumentation = false;
};
inline const char* option(const char* name) {
#ifdef MOTORSTORM_PARTICLE_FIXTURE
    return motorstorm_particle_fixture_option(name);
#else
    return std::getenv(name);
#endif
}
inline Config read(const char* name) {
    Config config;
    config.text = option(name);
    if (!config.text || !std::strcmp(config.text, "0")) {
        // Absent and "0" are the reference mode.
    } else if (!std::strcmp(config.text, "shadow")) {
        config.mode = Mode::shadow;
    } else if (!std::strcmp(config.text, "1")) {
        config.mode = Mode::native;
    } else {
        std::fprintf(stderr, "NATIVE_PARTICLE_ERROR %s must be 0, shadow or 1\n", name);
        std::abort();
    }
    for (const char* variable : {"SPU_LS_LOWREAD", "SPU_LS_WATCH", "SPU_SMC_WATCH", "SPU_PCHIST"})
        config.instrumentation |= option(variable) != nullptr;
    return config;
}
inline const Config& config(const char* name) {
    static Config value = read(name);
#ifdef MOTORSTORM_PARTICLE_FIXTURE
    static unsigned generation = motorstorm_particle_fixture_generation();
    const unsigned current = motorstorm_particle_fixture_generation();
    if (current != generation) {
        generation = current;
        value = read(name);
    }
#endif
    return value;
}
inline bool pending_event(const spu_context* ctx) {
    const volatile uint32_t& events = ctx->event_status;
    return ctx->int_enable && (events & ctx->event_mask);
}
// The reason to decline, or null when the native entry may run. The lifted code takes its
// interrupt and DMA decisions between blocks; the native entry must not skip a pending one.
template <class Matches>
const char* admission(const Config& config, const spu_context* ctx, Matches matches) {
    if (!ctx || ctx->ls != ctx->ls_store) return "local-store ownership";
    if (ctx->irq_saved) return "active interrupt frame";
    if (ctx->status != SPU_STATUS_RUNNING) return "entry state";
    if (ctx->list_stall_mask || pending_event(ctx)) return "pending DMA/event";
    if (config.instrumentation || g_spu_ls_watch_n > 0) return "active instrumentation";
    if (!matches(ctx)) return "code/data identity";
    return nullptr;
}
struct Copies {
    spu_context reference, candidate;
};
inline Copies& copies() {
    static thread_local Copies value;
    return value;
}
// Both copies start from one state of the caller. A context that changed between the two
// reads cannot give a defined comparison, so the shadow mode declines it.
inline bool snapshot(const spu_context* ctx, Copies& out) {
    std::memcpy(&out.reference, ctx, sizeof *ctx);
    std::atomic_signal_fence(std::memory_order_seq_cst);
    std::memcpy(&out.candidate, &out.reference, sizeof *ctx);
    out.reference.ls = out.reference.ls_store;
    out.candidate.ls = out.candidate.ls_store;
    return out.reference.status == SPU_STATUS_RUNNING && !out.reference.irq_saved &&
           !out.reference.list_stall_mask && !pending_event(&out.reference);
}
// Runs the lifted original on a copy until it returns to ret. Returns false when the copy
// does not return in a defined way.
inline bool run_lifted(spu_context* copy, Function original, uint32_t ret) {
    original(copy);
    for (unsigned long long steps = 0;; ++steps) {
        Function next = g_spu_trampoline_fn;
        if ((copy->pc & SPU_LS_MASK) == (ret & SPU_LS_MASK) && (!next || next == spu_indirect_branch)) {
            g_spu_trampoline_fn = nullptr;
            return true;
        }
        if (!next || steps > STEP_LIMIT) return false;
        g_spu_trampoline_fn = nullptr;
        next(copy);
    }
}
[[noreturn]] inline void mismatch(const char* port, const char* what, unsigned long long where,
                                  unsigned long long original, unsigned long long native) {
    std::fprintf(stderr, "NATIVE_PARTICLE_%s_SHADOW_MISMATCH %s %llu original=%016llx native=%016llx\n",
                 port, what, where, original, native);
    std::abort();
}
inline bool same_bytes(const char* port, const uint8_t* original, const uint8_t* native, size_t size,
                       uint32_t base) {
    if (!std::memcmp(original, native, size)) return true;
    size_t i = 0;
    while (original[i] == native[i]) ++i;
    mismatch(port, "local store byte", base + uint32_t(i), original[i], native[i]);
}
inline bool same_word(const char* port, unsigned register_, unsigned lane, uint32_t original, uint32_t native) {
    if (original == native) return true;
    mismatch(port, "register", register_ * 4 + lane, original, native);
}
}  // namespace motorstorm_particle_bind
