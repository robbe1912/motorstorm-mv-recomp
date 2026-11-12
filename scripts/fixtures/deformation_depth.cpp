#include "deformation_depth.h"
#include <bit>
#include <cfenv>
#include <cstdint>
#include <fstream>
#include <stdexcept>
#include <string>
#if defined(_M_X64) || defined(__x86_64__)
#include <immintrin.h>
#endif

template<class T> void read(std::istream& in, T& value) {
    if (!in.read(reinterpret_cast<char*>(&value), sizeof(value)))
        throw std::runtime_error("Truncated authored depth input");
}
int main(int argc, char** argv) {
    if (argc != 4) return 2;
    std::ifstream in(argv[1], std::ios::binary);
    std::ofstream out(argv[2], std::ios::binary);
    if (!in || !out) return 3;
    const unsigned setting = std::stoul(argv[3]);
    const int rounding[] = {FE_TONEAREST, FE_DOWNWARD, FE_UPWARD, FE_TOWARDZERO};
    if (std::fesetround(rounding[setting & 3]) || std::feclearexcept(FE_ALL_EXCEPT) ||
        std::feraiseexcept(FE_INVALID | FE_INEXACT)) return 4;
#if defined(_M_X64) || defined(__x86_64__)
    _mm_setcsr((_mm_getcsr() & ~0x8040u) | 0x1f80u |
               ((setting & 4) ? 0x40u : 0u) | ((setting & 8) ? 0x8000u : 0u));
#endif
    std::uint32_t count;
    read(in, count);
    for (std::uint32_t i = 0; i < count; ++i) {
        motorstorm::game::DepthPatch patch{};
        read(in, patch.samples);
        std::uint32_t x, y, mode;
        read(in, x); read(in, y); read(in, mode);
        patch.x_fraction = std::bit_cast<float>(x);
        patch.y_fraction = std::bit_cast<float>(y);
        const auto before = patch;
        const int old_round = std::fegetround(), old_flags = std::fetestexcept(FE_ALL_EXCEPT);
#if defined(_M_X64) || defined(__x86_64__)
        const auto old_csr = _mm_getcsr();
#endif
        std::uint32_t status = 0, result = 0xcdcdcdcdu;
        try {
            const float value = motorstorm::game::sample_deformation_depth(
                patch, static_cast<motorstorm::game::DepthSampleMode>(mode));
            result = std::bit_cast<std::uint32_t>(value);
        } catch (const std::invalid_argument&) { status = 1; }
        if (std::fegetround() != old_round || std::fetestexcept(FE_ALL_EXCEPT) != old_flags)
            return 5;
#if defined(_M_X64) || defined(__x86_64__)
        if (_mm_getcsr() != old_csr) return 6;
#endif
        if (before.samples != patch.samples || std::bit_cast<std::uint32_t>(patch.x_fraction) != x ||
            std::bit_cast<std::uint32_t>(patch.y_fraction) != y) return 7;
        out.write(reinterpret_cast<const char*>(&status), sizeof(status));
        out.write(reinterpret_cast<const char*>(&result), sizeof(result));
    }
    return out ? 0 : 8;
}
