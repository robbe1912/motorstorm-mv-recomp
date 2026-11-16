#include "deformation_depth.h"
#include "ppu_recomp.h"
#include "ps3emu/guest_read_sync.h"

#include <atomic>
#include <bit>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>

extern "C" void ps3_indirect_call(ppu_context *);
extern "C" thread_local void (*g_trampoline_fn)(void *);

namespace {
void complete_retained_calls(ppu_context *context) {
  while (g_trampoline_fn) {
    const auto next = g_trampoline_fn;
    g_trampoline_fn = nullptr;
    next(context);
  }
}

float read_float(std::uint64_t address) {
  return std::bit_cast<float>(vm_read32(address));
}

// GetDepth consumes only SurfaceQuery's complex-record matrix output.
std::uint32_t projection_matrix(std::uint32_t properties, std::uint32_t flags,
                                std::uint32_t selector) {
  if ((flags & 6u) == 0)
    return 0;
  const auto sector = (selector >> 20) & 0x7ffu;
  const auto element = selector & 0xfffffu;
  const auto receiver = properties + 0x38u;
  const auto table = vm_read32(receiver + 0x14u);
  const auto entry = vm_read32(table + sector * 4u);
  if (!entry)
    return 0;
  const auto count = std::bit_cast<std::int32_t>(vm_read32(entry + 0x1cu));
  if (count <= static_cast<std::int32_t>(element) || !vm_read8(entry + 0x20u))
    return 0;
  return vm_read32(entry + 0x24u) + element * 0x50u + 0x10u;
}

struct QueryFrame {
  ppu_context *context;
  std::uint64_t stack, toc, link;
  explicit QueryFrame(ppu_context *value)
      : context(value), stack(value->gpr[1]), toc(value->gpr[2]),
        link(value->lr) {
    if (stack < 0xe0 || stack > UINT32_MAX)
      throw std::runtime_error("Invalid native depth query stack");
    context->gpr[1] = stack - 0xe0;
    vm_write64(context->gpr[1], stack);
    vm_write64(stack + 0x10, link);
  }
  ~QueryFrame() {
    context->gpr[1] = stack;
    context->gpr[2] = toc;
    context->lr = link;
  }
};

void call_virtual(ppu_context *context, std::uint32_t object,
                  std::uint32_t slot, std::uint64_t return_address) {
  const auto descriptor = vm_read32(std::uint64_t(vm_read32(object)) + slot);
  const auto toc = context->gpr[2];
  context->ctr = vm_read32(descriptor);
  context->gpr[2] = vm_read32(std::uint64_t(descriptor) + 4);
  context->lr = return_address;
  try {
    ps3_indirect_call(context);
    complete_retained_calls(context);
  } catch (...) {
    context->gpr[2] = toc;
    throw;
  }
  context->gpr[2] = toc;
}

struct CacheReset {
  std::uint32_t manager;
  ~CacheReset() {
    vm_write32(std::uint64_t(manager) + 0x4c, 0);
    vm_write32(std::uint64_t(manager) + 0x44, UINT32_MAX);
  }
};

std::uint32_t select_surface(std::uint32_t manager, std::uint32_t id) {
  if (vm_read32(std::uint64_t(manager) + 0x44) == id)
    return vm_read32(std::uint64_t(manager) + 0x4c);
  vm_write32(std::uint64_t(manager) + 0x4c, 0);
  const auto end = vm_read32(std::uint64_t(manager) + 0x28);
  for (auto cursor = vm_read32(std::uint64_t(manager) + 0x24); cursor != end;
       cursor += 4) {
    const auto entry = vm_read32(cursor);
    if (vm_read32(entry) == id) {
      vm_write32(std::uint64_t(manager) + 0x4c, entry);
      vm_write32(std::uint64_t(manager) + 0x44, id);
      return entry;
    }
  }
  return 0;
}

struct PixelBufferLease {
  ppu_context *context;
  std::uint32_t object;
  PixelBufferLease(ppu_context *value, std::uint32_t pixel)
      : context(value), object(pixel) {
    context->gpr[3] = object;
    context->gpr[4] = context->gpr[1] + 0x70;
    context->gpr[5] = context->gpr[6] = context->gpr[7] = 0;
    call_virtual(context, object, 0x1c, 0x0029c988);
  }
  ~PixelBufferLease() {
    context->gpr[3] = object;
    call_virtual(context, object, 0x18, 0x0029cb6c);
  }
};

struct Counts {
  std::atomic<std::uint64_t> completed{}, sampled{}, snapshots{}, scalar{}, projected{};
};
Counts counts;

std::uint64_t report(bool sampled, bool snapshot) {
  std::uint64_t sample_number{};
  if (sampled) {
    sample_number = ++counts.sampled;
    if (snapshot)
      ++counts.snapshots;
    else
      ++counts.scalar;
  }
  const auto total = ++counts.completed;
  if (total <= 4 || (sampled && counts.sampled.load() <= 4) ||
      total % 1024 == 0)
    std::fprintf(stderr,
                 "[native-depth-query] completed=%llu sampled=%llu "
                 "snapshots=%llu scalar=%llu projected=%llu\n",
                 static_cast<unsigned long long>(total),
                 static_cast<unsigned long long>(counts.sampled.load()),
                 static_cast<unsigned long long>(counts.snapshots.load()),
                 static_cast<unsigned long long>(counts.scalar.load()),
                 static_cast<unsigned long long>(counts.projected.load()));
  return sample_number;
}
} // namespace

void motorstorm_native_deformation_depth(ppu_context *context) {
  const auto manager = static_cast<std::uint32_t>(context->gpr[3]);
  const auto selector = static_cast<std::uint32_t>(context->gpr[6]);
  const auto toc = context->gpr[2];
  const auto default_depth = read_float(toc - 0x2c6c);
  if (!vm_read32(std::uint64_t(manager) + 0x14) ||
      !vm_read32(std::uint64_t(manager) + 0x48)) {
    context->fpr[1] = default_depth;
    report(false, false);
    return;
  }
  const auto begin = vm_read32(std::uint64_t(manager) + 0x24);
  const auto end = begin ? vm_read32(std::uint64_t(manager) + 0x28) : 0;
  if (!begin || ((end - begin) >> 2) == 0 || selector == UINT32_MAX) {
    context->fpr[1] = default_depth;
    report(false, false);
    return;
  }
  if (end < begin || ((end - begin) & 3))
    throw std::runtime_error("Invalid native depth surface vector");

  motorstorm::game::DeformationProjection projection{};
  const auto source = context->gpr[4] & ~std::uint64_t(15);
  for (unsigned word = 0; word != 4; ++word)
    projection.point[word] = read_float(source + 4 * word);
  const auto query_argument = context->gpr[5];
  const auto properties = vm_read32(std::uint64_t(manager) + 0x14);
  QueryFrame frame(context);
  const auto matrix = projection_matrix(
      properties, static_cast<std::uint32_t>(query_argument), selector);
  if (!matrix) {
    context->fpr[1] = default_depth;
    report(false, false);
    return;
  }
  projection.point[3] = read_float(vm_read32(toc - 0x2c90) & ~std::uint32_t(15));
  projection.non_java = (context->vscr & (1u << 16)) != 0; // VSCR[NJ].
  const auto matrix_base = matrix & ~std::uint32_t(15);
  for (unsigned row = 0; row != 2; ++row)
    for (unsigned word = 0; word != 4; ++word)
      projection.rows[row][word] = read_float(std::uint64_t(matrix_base) +
                                             row * 16 + word * 4);
  const auto coordinates = motorstorm::game::project_deformation_point(projection);
  ++counts.projected;

  CacheReset cache{manager};
  const auto entry = select_surface(manager, (selector >> 20) & 0x7ff);
  context->fpr[1] = default_depth;
  if (!entry) {
    report(false, false);
    return;
  }
  const auto pixel = vm_read32(vm_read32(std::uint64_t(entry) + 4));
  double result;
  bool snapshot;
  std::uint32_t width, height, bytes_per_pixel, base;
  motorstorm::game::DeformationDepthPlan plan{};
  motorstorm::game::DepthPatch patch{};
  motorstorm::game::DepthSampleMode mode;
  {
    const PixelBufferLease lease(context, pixel);
    width = vm_read32(std::uint64_t(pixel) + 0x60);
    height = vm_read32(std::uint64_t(pixel) + 0x64);
    const auto format = vm_read32(std::uint64_t(pixel) + 0x54);
    const auto table = vm_read32(toc + 0x5aac);
    bytes_per_pixel =
        vm_read32(std::uint64_t(table) + 4ULL * format) >> 3;
    plan = motorstorm::game::plan_deformation_depth(
        coordinates[0], coordinates[1],
        width, height, bytes_per_pixel);
    base = vm_read32(context->gpr[1] + 0x70);
    VmReadSnapshotRange ranges[4]{};
    for (unsigned index = 0; index != 4; ++index) {
      if (plan.byte_offsets[index] > UINT32_MAX - base)
        throw std::runtime_error(
            "Native depth sample exceeds guest address space");
      ranges[index] = {base +
                           static_cast<std::uint32_t>(plan.byte_offsets[index]),
                       1, index};
    }
    mode = vm_read8(vm_read32(toc - 0x2c70)) != 0
                          ? motorstorm::game::DepthSampleMode::bilinear
                          : motorstorm::game::DepthSampleMode::point;
    patch = {{}, plan.x_fraction, plan.y_fraction};
    const auto status = vm_read_snapshot(ranges, 4, patch.samples.data(), 4);
    snapshot = status == VM_READ_SNAPSHOT_OK;
    if (status == VM_READ_SNAPSHOT_UNAVAILABLE) {
      // Preserve the original scalar service when a bulk view is unavailable.
      // Read order is TL, TR, BR, BL, including in point mode.
      for (const unsigned index : {0u, 1u, 3u, 2u})
        patch.samples[index] = vm_read8(ranges[index].address);
    } else if (!snapshot) {
      throw std::runtime_error("Native depth snapshot failed with status " +
                               std::to_string(status));
    }
    result = motorstorm::game::sample_deformation_depth(patch, mode);
  }
  context->fpr[1] = result;
  const auto sample_number = report(true, snapshot);
  static const bool capture_inputs = [] {
    const auto value = std::getenv("MS_DEPTH_OBSERVER");
    return value && std::strcmp(value, "1") == 0;
  }();
  if (capture_inputs && sample_number <= 64) {
    const auto bits = [](float value) {
      return std::bit_cast<std::uint32_t>(value);
    };
    // Record owned copies only after Unlock. No guest or GPU reads are added.
    std::fprintf(
        stderr,
        "[native-depth-input] seq=%llu manager=%08x selector=%08x pixel=%08x "
        "nj=%u point=%08x/%08x/%08x/%08x row0=%08x/%08x/%08x/%08x "
        "row1=%08x/%08x/%08x/%08x xy=%08x/%08x dims=%u/%u bpp=%u "
        "base=%08x offsets=%zx/%zx/%zx/%zx fractions=%08x/%08x mode=%u "
        "samples=%02x/%02x/%02x/%02x snapshot=%u value=%016llx\n",
        static_cast<unsigned long long>(sample_number), manager, selector, pixel,
        static_cast<unsigned>(projection.non_java),
        bits(projection.point[0]), bits(projection.point[1]),
        bits(projection.point[2]), bits(projection.point[3]),
        bits(projection.rows[0][0]), bits(projection.rows[0][1]),
        bits(projection.rows[0][2]), bits(projection.rows[0][3]),
        bits(projection.rows[1][0]), bits(projection.rows[1][1]),
        bits(projection.rows[1][2]), bits(projection.rows[1][3]),
        bits(coordinates[0]), bits(coordinates[1]), width, height, bytes_per_pixel,
        base, plan.byte_offsets[0], plan.byte_offsets[1], plan.byte_offsets[2],
        plan.byte_offsets[3], bits(plan.x_fraction), bits(plan.y_fraction),
        static_cast<unsigned>(mode), static_cast<unsigned>(patch.samples[0]),
        static_cast<unsigned>(patch.samples[1]),
        static_cast<unsigned>(patch.samples[2]),
        static_cast<unsigned>(patch.samples[3]), static_cast<unsigned>(snapshot),
        static_cast<unsigned long long>(std::bit_cast<std::uint64_t>(result)));
  }
}
