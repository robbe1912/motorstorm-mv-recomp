#include "ppu_recomp.h"
#include "ps3emu/guest_read_sync.h"

#include <bit>
#include <cfenv>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <immintrin.h>
#include <stdexcept>
#include <string>
#include <vector>

extern "C" {
thread_local void (*g_trampoline_fn)(void *) = nullptr;
}
void motorstorm_native_deformation_depth(ppu_context *);
#ifdef PRIVATE_DEPTH_REFERENCE
void private_original_depth(ppu_context *);
#endif

namespace {
constexpr std::uint32_t manager = 0x1000, pixel = 0x3000, stack = 0x900000;
constexpr std::uint32_t toc = 0xe8a6c0, sdk_toc = 0xe9a128;
std::vector<std::uint8_t> memory(0x1000000);
std::vector<std::string> events;
std::vector<std::uint64_t> byte_reads;
bool transform_success = true, locked, deferred_calls;
int snapshot_status = VM_READ_SNAPSHOT_OK;
unsigned snapshot_calls;
std::uint32_t expected_addresses[4] = {0x9040, 0x9041, 0x9140, 0x9141};

void check(bool value, const char *message) {
  if (value)
    return;
  std::fprintf(stderr, "query check failed: %s\n", message);
  std::exit(1);
}
void bounds(std::uint64_t address, unsigned bytes) {
  check(address <= memory.size() && bytes <= memory.size() - address,
        "VM bounds");
}
} // namespace

std::uint8_t vm_read8(std::uint64_t address) {
  bounds(address, 1);
  byte_reads.push_back(address);
  return memory[address];
}
std::uint32_t vm_read32(std::uint64_t address) {
  bounds(address, 4);
  std::uint32_t value = 0;
  for (unsigned byte = 0; byte != 4; ++byte)
    value = (value << 8) | memory[address + byte];
  return value;
}
std::uint64_t vm_read64(std::uint64_t address) {
  return (std::uint64_t(vm_read32(address)) << 32) | vm_read32(address + 4);
}
void vm_write32(std::uint64_t address, std::uint32_t value) {
  bounds(address, 4);
  for (unsigned byte = 0; byte != 4; ++byte)
    memory[address + byte] = std::uint8_t(value >> (24 - 8 * byte));
}
void vm_write64(std::uint64_t address, std::uint64_t value) {
  vm_write32(address, std::uint32_t(value >> 32));
  vm_write32(address + 4, std::uint32_t(value));
}

void perform_surface_query(ppu_context *context) {
  events.emplace_back("surface-query");
  check(context->gpr[3] == 0x1438 && context->gpr[4] == 0x76543210 &&
            context->gpr[5] == 0x30000f,
        "surface query arguments");
  check(context->gpr[6] == stack - 0xe0 + 0x90,
        "surface query output ownership");
  vm_write32(context->gpr[6] + 0x3c, transform_success ? 0x2407 : 0);
  context->gpr[3] = 0xdeadbeef; // The matrix pointer determines success.
}

void func_0029BE08(ppu_context *context) {
  (void)context;
  check(false, "retained projection called from native query");
}

void func_006CCF6C(ppu_context *context) {
  if (deferred_calls) {
    g_trampoline_fn = [](void *opaque) {
      perform_surface_query(static_cast<ppu_context *>(opaque));
    };
  } else {
    perform_surface_query(context);
  }
}

void func_00754348(ppu_context *context) {
  const auto table = vm_read32(context->gpr[2] + 0x5aac);
  context->gpr[3] = vm_read32(table + 4 * context->gpr[3]) >> 3;
}

void perform_virtual(ppu_context *context) {
  check(context->gpr[2] == sdk_toc && context->gpr[3] == pixel,
        "virtual descriptor TOC/object");
  if (context->ctr == 0x799db4) {
    check(!locked, "one Lock");
    locked = true;
    events.emplace_back("lock");
    check(context->gpr[4] == stack - 0xe0 + 0x70 && !context->gpr[5] &&
              !context->gpr[6] && !context->gpr[7],
          "Lock arguments");
    check(context->fpr[1] == 0.25, "Lock floating argument");
    vm_write32(context->gpr[4], 0x7000);
    context->gpr[3] = 0x1000; // The original ignores this status.
  } else {
    check(context->ctr == 0x799728 && locked, "one Unlock");
    events.emplace_back("unlock");
    locked = false;
    context->gpr[3] = pixel;
  }
}

extern "C" void ps3_indirect_call(ppu_context *context) {
  if (deferred_calls) {
    g_trampoline_fn = [](void *opaque) {
      perform_virtual(static_cast<ppu_context *>(opaque));
    };
  } else {
    perform_virtual(context);
  }
}

extern "C" int vm_read_snapshot(const VmReadSnapshotRange *ranges,
                                std::uint32_t count, void *destination,
                                std::uint32_t bytes) {
  check(locked && count == 4 && bytes == 4, "snapshot inside Lock");
  events.emplace_back("snapshot");
  ++snapshot_calls;
  for (unsigned index = 0; index != 4; ++index) {
    check(ranges[index].address == expected_addresses[index] &&
              ranges[index].bytes == 1 && ranges[index].output_offset == index,
          "planned snapshot ranges");
    if (snapshot_status == VM_READ_SNAPSHOT_OK)
      static_cast<std::uint8_t *>(destination)[index] =
          memory[expected_addresses[index]];
  }
  return snapshot_status;
}

namespace {
ppu_context setup() {
#ifdef PRIVATE_DEPTH_REFERENCE
  vm_base = memory.data();
#endif
  std::fill(memory.begin(), memory.end(), 0);
  events.clear();
  byte_reads.clear();
  locked = false;
  g_trampoline_fn = nullptr;
  transform_success = true;
  snapshot_status = VM_READ_SNAPSHOT_OK;
  snapshot_calls = 0;
  const std::uint32_t addresses[] = {0x9040, 0x9041, 0x9140, 0x9141};
  std::copy(std::begin(addresses), std::end(addresses), expected_addresses);
  vm_write32(manager + 0x14, 0x1400);
  vm_write32(manager + 0x48, 1);
  vm_write32(manager + 0x24, 0x2000);
  vm_write32(manager + 0x28, 0x2008);
  vm_write32(manager + 0x44, 0xf);
  vm_write32(manager + 0x4c, 0x1234);
  vm_write32(0x2000, 0x2200);
  vm_write32(0x2004, 0x2210);
  vm_write32(0x2200, 2);
  vm_write32(0x2210, 3);
  vm_write32(0x2214, 0x2900);
  vm_write32(0x2900, pixel);
  vm_write32(pixel, 0x3200);
  vm_write32(0x321c, 0x3100);
  vm_write32(0x3218, 0x3120);
  vm_write32(0x3100, 0x799db4);
  vm_write32(0x3104, sdk_toc);
  vm_write32(0x3120, 0x799728);
  vm_write32(0x3124, sdk_toc);
  vm_write32(pixel + 0x54, 12);
  vm_write32(pixel + 0x60, 256);
  vm_write32(pixel + 0x64, 128);
  vm_write32(toc + 0x5aac, 0x6000);
  vm_write32(0x6030, 8);
  vm_write32(toc - 0x2c70, 0x5000);
  vm_write32(toc - 0x2c6c, 0x3e800000);
  vm_write32(toc - 0x2cac, 0x3f800000);
  vm_write32(toc - 0x2c74, 0x3b808081);
  vm_write32(toc - 0x2c90, 0x6107);
  vm_write32(0x6100, 0x3f800000); // Homogeneous coordinate constant.
  const std::uint32_t point[] = {0x40000000, 0xbf000000, 0x40800000, 0xc2f60000};
  const std::uint32_t rows[] = {0x3e000000, 0x3f000000, 0x3d800000, 0x3a800000,
                                0x3e000000, 0x3f000000, 0x3e000000, 0x3e7e0000};
  for (unsigned word = 0; word != 4; ++word)
    vm_write32(0x4000 + 4 * word, point[word]);
  for (unsigned word = 0; word != 8; ++word)
    vm_write32(0x2400 + 4 * word, rows[word]);
  memory[0x5000] = 1;
  memory[0x9040] = 21;
  memory[0x9041] = 22;
  memory[0x9140] = 24;
  memory[0x9141] = 23;
  ppu_context context{};
  for (unsigned index = 0; index != 32; ++index) {
    context.gpr[index] = 0x11110000 + index;
    context.fpr[index] = index + 0.5;
  }
  context.gpr[1] = stack;
  context.gpr[2] = toc;
  context.gpr[3] = manager;
  context.gpr[4] = 0x4007;
  context.gpr[5] = 0x76543210;
  context.gpr[6] = 0x30000f;
  context.lr = 0x123456;
  context.cr = 0xabcdef12;
  return context;
}

void run_query(ppu_context *context) {
#ifdef PRIVATE_DEPTH_REFERENCE
  private_original_depth(context);
#else
  motorstorm_native_deformation_depth(context);
#endif
}

void completed(const ppu_context &context, const ppu_context &before,
               bool point) {
  const auto expected = std::bit_cast<float>(point ? 0x3da8a8a9u : 0x3dafafb0u);
  if (context.fpr[1] != double(expected))
    std::fprintf(stderr, "result observed=%016llx expected=%016llx\n",
                 static_cast<unsigned long long>(
                     std::bit_cast<std::uint64_t>(context.fpr[1])),
                 static_cast<unsigned long long>(
                     std::bit_cast<std::uint64_t>(double(expected))));
  check(context.fpr[1] == double(expected), "native/reference result");
  check(!g_trampoline_fn,
        "retained calls completed before native continuation");
  check(!locked && events.front() == "surface-query" && events.back() == "unlock",
        "call order and release");
  check(!vm_read32(manager + 0x4c) && vm_read32(manager + 0x44) == UINT32_MAX,
        "cache reset");
  check(context.gpr[1] == before.gpr[1] && context.gpr[2] == before.gpr[2] &&
            context.lr == before.lr,
        "stack/TOC/link restored");
  for (unsigned index = 14; index != 32; ++index) {
    check(context.gpr[index] == before.gpr[index], "callee-saved GPR");
    check(context.fpr[index] == before.fpr[index], "callee-saved FPR");
  }
  check((context.cr & 0x00fff000) == (before.cr & 0x00fff000),
        "callee-saved CR");
  check(vm_read32(0x4000) == 0x40000000 && vm_read32(0x400c) == 0xc2f60000,
        "input vector immutable");
}
} // namespace

int main(int argc, char **argv) {
  const auto fp_mode = argc >= 2 ? std::atoi(argv[1]) : 0;
  deferred_calls = argc >= 3 && std::atoi(argv[2]) != 0;
  check(fp_mode >= 0 && fp_mode < 16, "FP mode");
  const int rounding[] = {FE_TONEAREST, FE_DOWNWARD, FE_UPWARD, FE_TOWARDZERO};
  check(std::fesetround(rounding[fp_mode & 3]) == 0, "caller rounding setup");
  auto csr = _mm_getcsr() & ~unsigned(0x8040);
  if (fp_mode & 4)
    csr |= 0x0040;
  if (fp_mode & 8)
    csr |= 0x8000;
  _mm_setcsr(csr);
  if (argc >= 4 && std::string(argv[3]) == "capture-cap") {
    for (unsigned index = 0; index != 80; ++index) {
      auto context = setup();
      const auto before = context;
      run_query(&context);
      completed(context, before, false);
    }
    return 0;
  }
  for (unsigned point = 0; point != 2; ++point) {
    for (unsigned fallback = 0; fallback != 2; ++fallback) {
      for (unsigned cached = 0; cached != 2; ++cached) {
        auto context = setup();
        if (cached) {
          vm_write32(manager + 0x44, 3);
          vm_write32(manager + 0x4c, 0x2210);
        }
        memory[0x5000] = !point;
        snapshot_status =
            fallback ? VM_READ_SNAPSHOT_UNAVAILABLE : VM_READ_SNAPSHOT_OK;
        const auto before = context;
        const auto before_csr = _mm_getcsr();
        const auto before_rounding = std::fegetround();
        run_query(&context);
#ifndef PRIVATE_DEPTH_REFERENCE
        check(_mm_getcsr() == before_csr &&
                  std::fegetround() == before_rounding,
              "caller FP state");
#else
        (void)before_csr;
        (void)before_rounding;
#endif
        completed(context, before, point);
#ifndef PRIVATE_DEPTH_REFERENCE
        check(snapshot_calls == 1, "one bulk request");
        const std::vector<std::uint64_t> expected =
            fallback ? std::vector<std::uint64_t>{0x5000, 0x9040, 0x9041,
                                                  0x9141, 0x9140}
                     : std::vector<std::uint64_t>{0x5000};
        check(byte_reads == expected,
              "scalar fallback order and bulk read removal");
#endif
      }
    }
  }
  for (unsigned non_java = 0; non_java != 2; ++non_java) {
    auto context = setup();
    context.vscr = non_java ? PPU_VSCR_NJ : 0;
    vm_write32(0x4000, 1); // Smallest subnormal, amplified by the first row.
    vm_write32(0x4004, 0);
    vm_write32(0x4008, 0);
    for (unsigned word = 0; word != 8; ++word)
      vm_write32(0x2400 + word * 4, 0);
    vm_write32(0x2400, 0x7f7fffff);
    vm_write32(0x241c, 0x3f000000);
    const std::uint32_t addresses[] = {0xb000, 0xb001, 0xb100, 0xb101};
    std::copy(std::begin(addresses), std::end(addresses), expected_addresses);
    memory[0xb001] = memory[0xb101] = 255;
    const auto csr = _mm_getcsr();
    run_query(&context);
    const auto expected = std::bit_cast<float>(non_java ? 0u : 0x38ffffffu);
    check(context.fpr[1] == double(expected), "guest NJ controls native projection");
    check(_mm_getcsr() == csr && context.vscr == (non_java ? PPU_VSCR_NJ : 0),
          "projection preserves caller and guest FP state");
  }
  for (unsigned scenario = 0; scenario != 8; ++scenario) {
    auto context = setup();
    switch (scenario) {
    case 0:
      vm_write32(manager + 0x14, 0);
      break;
    case 1:
      vm_write32(manager + 0x48, 0);
      break;
    case 2:
      vm_write32(manager + 0x24, 0);
      break;
    case 3:
      vm_write32(manager + 0x28, 0x2000);
      break;
    case 4:
      context.gpr[6] = UINT32_MAX;
      break;
    case 5:
      transform_success = false;
      break;
    case 6:
      vm_write32(0x2210, 4);
      break;
    case 7:
      vm_write32(manager + 0x44, 3);
      vm_write32(manager + 0x4c, 0);
      break;
    }
    run_query(&context);
    check(context.fpr[1] == 0.25 && !locked, "empty query result");
    check(vm_read32(manager + 0x4c) == (scenario < 6 ? 0x1234u : 0u),
          "early versus completed cache state");
    check(snapshot_calls == 0, "empty query has no snapshot");
  }
#ifndef PRIVATE_DEPTH_REFERENCE
  for (const int status : {VM_READ_SNAPSHOT_FAILED, VM_READ_SNAPSHOT_INVALID}) {
    auto context = setup();
    snapshot_status = status;
    bool failed = false;
    try {
      run_query(&context);
    } catch (const std::runtime_error &) {
      failed = true;
    }
    check(failed && !locked && events.back() == "unlock",
          "visible failure releases Lock");
    check(context.gpr[1] == stack && context.gpr[2] == toc &&
              !vm_read32(manager + 0x4c),
          "failure cleanup");
  }
#endif
  std::puts("PASS full depth query control, cache, virtual calls, acquisition, "
            "fallback and ABI");
}
