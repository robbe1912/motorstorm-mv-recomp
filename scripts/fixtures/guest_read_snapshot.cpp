#include "ps3emu/guest_read_sync.h"
#include <array>
#include <atomic>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <thread>
#include <vector>
#ifdef _WIN32
#include <crtdbg.h>
#include <cstdlib>
#endif

static std::atomic<unsigned> calls, scalar_calls;
static int result = VM_READ_SNAPSHOT_OK;
static const unsigned char source[16] = {1,  7,  11, 19, 23, 29, 31, 37,
                                         41, 43, 47, 53, 59, 61, 67, 71};
static int provider(const VmReadSnapshotRange *ranges, uint32_t count,
                    void *dst, uint32_t bytes, void *opaque) {
  assert(opaque == source);
  ++calls;
  auto *out = static_cast<unsigned char *>(dst);
  if (result != VM_READ_SNAPSHOT_OK) {
    out[0] = 0xAA;
    return result;
  }
  for (uint32_t i = 0; i < count; i++) {
    if (ranges[i].address < 0x4000 ||
        uint64_t(ranges[i].address) + ranges[i].bytes > 0x4010)
      return VM_READ_SNAPSHOT_UNAVAILABLE;
    assert(uint64_t(ranges[i].output_offset) + ranges[i].bytes <= bytes);
    std::memcpy(out + ranges[i].output_offset,
                source + ranges[i].address - 0x4000, ranges[i].bytes);
  }
  return VM_READ_SNAPSHOT_OK;
}
static void scalar(uint32_t, uint32_t, void *) { ++scalar_calls; }
int main() {
#ifdef _WIN32
  _set_error_mode(_OUT_TO_STDERR);
  _set_abort_behavior(0, _WRITE_ABORT_MSG | _CALL_REPORTFAULT);
  _CrtSetReportMode(_CRT_ASSERT, _CRTDBG_MODE_FILE);
  _CrtSetReportFile(_CRT_ASSERT, _CRTDBG_FILE_STDERR);
#endif
  VmReadSnapshotRange ranges[] = {
      {0x4000, 1, 0}, {0x4001, 1, 2}, {0x4008, 1, 4}, {0x4009, 1, 6}};
  std::array<unsigned char, 8> out;
  out.fill(0xCD);
  const auto untouched = out;
  assert(vm_read_snapshot(ranges, 4, out.data(), out.size()) ==
             VM_READ_SNAPSHOT_UNAVAILABLE &&
         out == untouched);
  vm_read_sync_set_handler(scalar, nullptr);
  vm_read_sync_mark_range(0x4000, 16);
  for (auto r : ranges)
    vm_cpu_read_sync(r.address, r.bytes);
  assert(scalar_calls == 4);
  vm_read_snapshot_set_handler(provider, const_cast<unsigned char *>(source));
  assert(vm_read_snapshot(ranges, 4, out.data(), out.size()) ==
             VM_READ_SNAPSHOT_OK &&
         calls == 1 && scalar_calls == 4);
  const std::array<unsigned char, 8> expected = {1,  0xCD, 7,  0xCD,
                                                 41, 0xCD, 43, 0xCD};
  assert(out == expected);
  for (int failure : std::array<int, 4>{VM_READ_SNAPSHOT_UNAVAILABLE,
                                        VM_READ_SNAPSHOT_INVALID,
                                        VM_READ_SNAPSHOT_FAILED, 2}) {
    result = failure;
    out = untouched;
    assert(vm_read_snapshot(ranges, 4, out.data(), out.size()) ==
           (failure == 2 ? VM_READ_SNAPSHOT_FAILED : failure));
    assert(out == untouched);
  }
  result = VM_READ_SNAPSHOT_OK;
  auto invalid = [&](const VmReadSnapshotRange *r, uint32_t count,
                     void *destination, uint32_t bytes) {
    const auto before = calls.load();
    out = untouched;
    assert(vm_read_snapshot(r, count, destination, bytes) ==
               VM_READ_SNAPSHOT_INVALID &&
           calls == before && out == untouched);
  };
  invalid(nullptr, 4, out.data(), 8);
  invalid(ranges, 0, out.data(), 8);
  invalid(ranges, 17, out.data(), 8);
  invalid(ranges, 4, nullptr, 8);
  invalid(ranges, 4, out.data(), 0);
  invalid(ranges, 4, out.data(), 4097);
  VmReadSnapshotRange bad[] = {{0xffffffffu, 2, 0}};
  invalid(bad, 1, out.data(), 8);
  bad[0] = {0x4000, 0, 0};
  invalid(bad, 1, out.data(), 8);
  bad[0] = {0x4000, 2, 7};
  invalid(bad, 1, out.data(), 8);
  bad[0] = {0x4000, 2, 0xffffffffu};
  invalid(bad, 1, out.data(), 8);
  VmReadSnapshotRange overlap[] = {{0x4000, 2, 0}, {0x4002, 1, 1}};
  invalid(overlap, 2, out.data(), 8);
  bad[0] = {0xffffffffu, 1, 0};
  assert(vm_read_snapshot(bad, 1, out.data(), 8) ==
             VM_READ_SNAPSHOT_UNAVAILABLE &&
         out == untouched);
  VmReadSnapshotRange maximum[16];
  for (unsigned i = 0; i < 16; i++)
    maximum[i] = {0x4000 + i, 1, i};
  std::array<unsigned char, 4096> large;
  large.fill(0xCD);
  assert(vm_read_snapshot(maximum, 16, large.data(), large.size()) ==
         VM_READ_SNAPSHOT_OK);
  assert(std::memcmp(large.data(), source, 16) == 0);
  for (unsigned i = 16; i < 4096; i++)
    assert(large[i] == 0xCD);
  std::vector<std::thread> threads;
  for (unsigned i = 0; i < 4; i++)
    threads.emplace_back([&] {
      for (unsigned j = 0; j < 2048; j++) {
        auto local = untouched;
        assert(vm_read_snapshot(ranges, 4, local.data(), local.size()) ==
                   VM_READ_SNAPSHOT_OK &&
               local == expected);
      }
    });
  for (auto &thread : threads)
    thread.join();
  vm_read_snapshot_set_handler(nullptr, nullptr);
  out = untouched;
  assert(vm_read_snapshot(ranges, 4, out.data(), out.size()) ==
             VM_READ_SNAPSHOT_UNAVAILABLE &&
         out == untouched);
  vm_read_sync_set_handler(nullptr, nullptr);
  std::puts("PASS actual snapshot dispatch: bounds, transactional failures, "
            "four scalar calls versus one batch, gaps, quiescent lifecycle and "
            "concurrent readers; CPU fixture only, not GPU visibility");
}
