#pragma once
#include <cstdint>

namespace motorstorm::game {
// Both hardware instructions and OS preservation of XMM/YMM state are required.
constexpr bool world_transform_features(std::uint32_t max_leaf,
    std::uint32_t leaf1_ecx, std::uint32_t leaf7_ebx, std::uint64_t xcr0) {
    constexpr std::uint32_t required = (1u << 12) | (1u << 26) | (1u << 27) | (1u << 28);
    return max_leaf >= 7 && (leaf1_ecx & required) == required &&
        (leaf7_ebx & (1u << 5)) && (xcr0 & 6) == 6;
}
bool supports_native_world_transforms();
}
