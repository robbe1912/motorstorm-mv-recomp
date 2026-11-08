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
        throw std::runtime_error("Truncated depth-plan input");
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
        std::uint32_t x_bits, y_bits, width, height, bytes;
        read(in, x_bits); read(in, y_bits); read(in, width); read(in, height); read(in, bytes);
        std::uint32_t status = 0;
        std::uint64_t offsets[4]{};
        std::uint32_t fractions[2]{};
        const int old_round = std::fegetround(), old_flags = std::fetestexcept(FE_ALL_EXCEPT);
#if defined(_M_X64) || defined(__x86_64__)
        const auto old_csr = _mm_getcsr();
#endif
        try {
            const auto plan = motorstorm::game::plan_deformation_depth(
                std::bit_cast<float>(x_bits), std::bit_cast<float>(y_bits), width, height, bytes);
            for (unsigned n = 0; n != 4; ++n) offsets[n] = plan.byte_offsets[n];
            fractions[0] = std::bit_cast<std::uint32_t>(plan.x_fraction);
            fractions[1] = std::bit_cast<std::uint32_t>(plan.y_fraction);
        } catch (const std::invalid_argument&) { status = 1; }
        if (std::fegetround() != old_round || std::fetestexcept(FE_ALL_EXCEPT) != old_flags)
            return 5;
#if defined(_M_X64) || defined(__x86_64__)
        if (_mm_getcsr() != old_csr) return 6;
#endif
        out.write(reinterpret_cast<const char*>(&status), sizeof(status));
        out.write(reinterpret_cast<const char*>(offsets), sizeof(offsets));
        out.write(reinterpret_cast<const char*>(fractions), sizeof(fractions));
    }
    return out ? 0 : 4;
}
