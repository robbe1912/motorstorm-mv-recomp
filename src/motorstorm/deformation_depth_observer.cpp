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
    bool memory_captured{};
    std::uint32_t format{}, width{}, height{}, output{}, x_bits{}, y_bits{};
    std::uint32_t resource{}, resource_words[7]{}, parent_words[7]{};
    std::uint64_t byte_addresses[5]{};
    std::uint8_t byte_values[5]{};
    unsigned byte_count{};
};

struct State {
    ps3emu_ppu_function get_depth{};
    ps3emu_ppu_function lock{};
    std::atomic<std::uint64_t> completed{0};
    std::atomic<std::uint64_t> completed_by_lock[2]{};
    std::atomic<std::uint64_t> memory_attempts{0};
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
    if (!value.memory_captured) return;
    std::fprintf(stderr,
        "[depth-view] seq=%llu format=%x dims=%u,%u output=%x xy=%x,%x resource=%x\n",
        static_cast<unsigned long long>(sequence), value.format, value.width, value.height,
        value.output, value.x_bits, value.y_bits, value.resource);
    // Each independently emitted line carries its query identity, including
    // when different guest threads complete concurrently.
    std::fprintf(stderr,
        "[depth-resource] seq=%llu ea=%x words=%x,%x,%x,%x,%x,%x,%x parent=%x,%x,%x,%x,%x,%x,%x\n",
        static_cast<unsigned long long>(sequence), value.resource,
        value.resource_words[0], value.resource_words[1], value.resource_words[2],
        value.resource_words[3], value.resource_words[4], value.resource_words[5], value.resource_words[6],
        value.parent_words[0], value.parent_words[1], value.parent_words[2],
        value.parent_words[3], value.parent_words[4], value.parent_words[5], value.parent_words[6]);
    std::fprintf(stderr,
        "[depth-bytes] seq=%llu count=%u b0=%llx:%x b1=%llx:%x b2=%llx:%x b3=%llx:%x b4=%llx:%x\n",
        static_cast<unsigned long long>(sequence), value.byte_count,
        static_cast<unsigned long long>(value.byte_addresses[0]), unsigned(value.byte_values[0]),
        static_cast<unsigned long long>(value.byte_addresses[1]), unsigned(value.byte_values[1]),
        static_cast<unsigned long long>(value.byte_addresses[2]), unsigned(value.byte_values[2]),
        static_cast<unsigned long long>(value.byte_addresses[3]), unsigned(value.byte_values[3]),
        static_cast<unsigned long long>(value.byte_addresses[4]), unsigned(value.byte_values[4]));
}

void capture_resource(std::uint32_t address, std::uint32_t (&words)[7]) {
    for (unsigned index = 0; index != 7; ++index) words[index] = vm_read32(address + index * 4u);
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
    const auto attempt = state().memory_attempts.fetch_add(1, std::memory_order_relaxed);
    if (attempt == 64) std::fputs("[depth-observe] metadata cap=64 reached\n", stderr);
    if (attempt >= 64) return;
    sample->memory_captured = true;
    // Pinned GetDepth uses SP+0x70 as Lock's output slot and SP+0x74/+0x78
    // for TransformPoint output. Metadata reads use the normal VM API. They
    // are sequential observations, not an atomic or GPU-coherent snapshot.
    sample->output = vm_read32(out_slot);
    sample->x_bits = vm_read32(out_slot + 4u);
    sample->y_bits = vm_read32(out_slot + 8u);
    sample->format = vm_read32(object + 0x54u);
    sample->width = vm_read32(object + 0x60u);
    sample->height = vm_read32(object + 0x64u);
    sample->resource = vm_read32(object + 0x8cu);
    if (sample->resource) {
        capture_resource(sample->resource, sample->resource_words);
        if (sample->resource_words[6]) capture_resource(sample->resource_words[6], sample->parent_words);
    }
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

std::uint8_t motorstorm_observe_depth_byte(
    std::uint64_t address, std::uint8_t (*original_read)(std::uint64_t)) {
    RawSample* const sample = active_sample;
    const std::uint8_t value = original_read(address);
    if (sample && sample->memory_captured) {
        const unsigned index = sample->byte_count++;
        if (index < 5) {
            sample->byte_addresses[index] = address;
            sample->byte_values[index] = value;
        }
    }
    return value;
}

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
