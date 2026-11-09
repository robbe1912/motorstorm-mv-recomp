#include "deformation_depth_observer.h"

#include "ppu_recomp.h"
#include "ps3emu/ppu_function_registry.h"

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

void game_original_deformation_depth(ppu_context*);

namespace {
/* Original-US lifted PPU entry identities recovered from the pinned ELF.
 * These are observation targets, not special completion paths. */
constexpr std::uint32_t kGetDepth = 0x0029c684u;
constexpr std::uint32_t kPixelBufferLock = 0x00799db4u;

struct RawSample {
    std::uint64_t depth_gpr[4]{};
    std::uint64_t depth_fpr[4]{};
    std::uint64_t return_gpr3{};
    std::uint64_t return_fpr1{};
    std::uint64_t lock_object{}, lock_out_slot{}, lock_mode{}, lock_status{};
    bool lock_seen{};
};

struct State {
    ps3emu_ppu_function get_depth{};
    ps3emu_ppu_function lock{};
    std::atomic<std::uint64_t> completed{0};
    std::atomic<std::uint64_t> completed_by_lock[2]{};
    bool enabled{};
};

State& state() { static State value; return value; }
thread_local RawSample* active_sample{};

std::uint64_t raw_bits(double value) {
    std::uint64_t bits{};
    static_assert(sizeof(bits) == sizeof(value), "unexpected PPU FPR width");
    std::memcpy(&bits, &value, sizeof(bits));
    return bits;
}

void print_sample(std::uint64_t sequence, const RawSample& value) {
    std::fprintf(stderr,
        "[depth-observe] seq=%llu depth-gpr=%llx,%llx,%llx,%llx "
        "depth-fpr=%llx,%llx,%llx,%llx lock-seen=%u "
        "lock=%llx,%llx,%llx,status=%llx return=%llx,%llx\n",
        static_cast<unsigned long long>(sequence),
        static_cast<unsigned long long>(value.depth_gpr[0]),
        static_cast<unsigned long long>(value.depth_gpr[1]),
        static_cast<unsigned long long>(value.depth_gpr[2]),
        static_cast<unsigned long long>(value.depth_gpr[3]),
        static_cast<unsigned long long>(value.depth_fpr[0]),
        static_cast<unsigned long long>(value.depth_fpr[1]),
        static_cast<unsigned long long>(value.depth_fpr[2]),
        static_cast<unsigned long long>(value.depth_fpr[3]),
        unsigned(value.lock_seen),
        static_cast<unsigned long long>(value.lock_object),
        static_cast<unsigned long long>(value.lock_out_slot),
        static_cast<unsigned long long>(value.lock_mode),
        static_cast<unsigned long long>(value.lock_status),
        static_cast<unsigned long long>(value.return_gpr3),
        static_cast<unsigned long long>(value.return_fpr1));
}

void observe_lock(ppu_context* ctx) {
    RawSample* sample = active_sample;
    const std::uint64_t object = ctx->gpr[3];
    const std::uint64_t out_slot = ctx->gpr[4];
    const std::uint64_t mode = ctx->gpr[5];
    state().lock(ctx);
    if (!sample) return;
    sample->lock_seen = true;
    sample->lock_object = object;
    sample->lock_out_slot = out_slot;
    sample->lock_mode = mode;
    sample->lock_status = ctx->gpr[3];
}

void observe_depth(ppu_context* ctx) {
    RawSample sample{};
    for (unsigned index = 0; index < 4; ++index) {
        sample.depth_gpr[index] = ctx->gpr[index + 3];
        sample.depth_fpr[index] = raw_bits(ctx->fpr[index + 1]);
    }
    RawSample* const previous = active_sample;
    active_sample = &sample;
    state().get_depth(ctx);
    active_sample = previous;
    sample.return_gpr3 = ctx->gpr[3];
    sample.return_fpr1 = raw_bits(ctx->fpr[1]);

    const std::uint64_t sequence = state().completed.fetch_add(1, std::memory_order_relaxed) + 1;
    const std::uint64_t class_sequence =
        state().completed_by_lock[sample.lock_seen].fetch_add(1, std::memory_order_relaxed) + 1;
    /* This explicitly opt-in diagnostic is bounded to keep the log and its
     * perturbation finite. Independent budgets retain nested-Lock evidence
     * after startup calls without Lock. Raw bits do not invent a call ABI. */
    if (class_sequence <= 64) print_sample(sequence, sample);
    else if (class_sequence == 65)
        std::fprintf(stderr, "[depth-observe] capture cap=64 reached lock-seen=%u\n",
                     unsigned(sample.lock_seen));
}
} // namespace

// The verified generated-input binding retains this entry for both direct and
// registered callers. Disabled observation still executes the exact original.
void motorstorm_observe_deformation_depth(ppu_context* ctx) {
    if (!state().enabled) {
        game_original_deformation_depth(ctx);
        return;
    }
    observe_depth(ctx);
}

void deformation_depth_observer_install() {
    const char* enabled = std::getenv("MS_DEPTH_OBSERVER");
    if (!enabled || std::strcmp(enabled, "1") != 0) return;

    auto& value = state();
    if (value.enabled) {
        std::fputs("[depth-observe] install rejected: already installed\n", stderr);
        return;
    }
    ps3emu_ppu_function get_depth{};
    ps3emu_ppu_function lock{};
    if (!ppu_get_registered_function(kGetDepth, &get_depth) || get_depth != func_0029C684 ||
        !ppu_get_registered_function(kPixelBufferLock, &lock)) {
        std::fputs("[depth-observe] install rejected: original entries unavailable\n", stderr);
        return;
    }
    value.get_depth = game_original_deformation_depth;
    value.lock = lock;
    /* Registration is immediately after generated registration and before
     * guest execution, satisfying the registry's quiescence contract. */
    ppu_register_function(kPixelBufferLock, observe_lock);
    value.enabled = true;
    std::fputs("[depth-observe] installed raw GetDepth/PixelBuffer::Lock observer\n", stderr);
}
