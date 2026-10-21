#include "native_cpu.h"
#if defined(_MSC_VER)
#include <intrin.h>
#elif defined(__x86_64__) || defined(__i386__)
#include <cpuid.h>
#endif

namespace motorstorm::game {
#if defined(_MSC_VER)
#if defined(__clang__)
__attribute__((target("xsave")))
#endif
static std::uint64_t enabled_vector_state() { return _xgetbv(0); }
#elif defined(__x86_64__) || defined(__i386__)
static std::uint64_t enabled_vector_state() {
    std::uint32_t low, high;
    __asm__ volatile("xgetbv" : "=a"(low), "=d"(high) : "c"(0));
    return (std::uint64_t(high) << 32) | low;
}
#endif

bool supports_native_world_transforms() {
#if defined(_MSC_VER)
    int registers[4];
    __cpuidex(registers, 0, 0);
    const auto max_leaf = static_cast<std::uint32_t>(registers[0]);
    if (max_leaf < 7) return false;
    __cpuidex(registers, 1, 0);
    const auto ecx = static_cast<std::uint32_t>(registers[2]);
    __cpuidex(registers, 7, 0);
    const auto ebx = static_cast<std::uint32_t>(registers[1]);
#elif defined(__x86_64__) || defined(__i386__)
    const auto max_leaf = __get_cpuid_max(0, nullptr);
    if (max_leaf < 7) return false;
    unsigned a, b, ecx, d, ebx, unused;
    __cpuid_count(1, 0, a, b, ecx, d);
    __cpuid_count(7, 0, a, ebx, unused, d);
#else
    return false;
#endif
#if defined(_MSC_VER) || defined(__x86_64__) || defined(__i386__)
    // Never execute XGETBV until CPUID proves that the OS enables XSAVE.
    if (!world_transform_features(max_leaf, ecx, ebx, 6)) return false;
    return world_transform_features(max_leaf, ecx, ebx, enabled_vector_state());
#endif
}
}
