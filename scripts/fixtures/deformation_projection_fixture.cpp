#include "deformation_depth.h"

#include <bit>
#include <cfenv>
#include <cstdio>
#include <cstdlib>
#include <immintrin.h>

int main(int argc, char** argv) {
    if (argc != 4) return 2;
    auto* input = std::fopen(argv[1], "rb");
    auto* output = std::fopen(argv[2], "wb");
    if (!input || !output) return 3;
    const unsigned mode = std::atoi(argv[3]);
    const int rounding[] = {FE_TONEAREST, FE_DOWNWARD, FE_UPWARD, FE_TOWARDZERO};
    if (mode >= 16 || std::fesetround(rounding[mode & 3])) return 4;
    auto csr = _mm_getcsr() & ~unsigned(0x8040);
    if (mode & 4) csr |= 0x40;
    if (mode & 8) csr |= 0x8000;
    _mm_setcsr(csr);
    std::feraiseexcept(FE_DIVBYZERO);
    std::array<std::uint32_t, 13> words{};
    while (std::fread(words.data(), sizeof(words), 1, input) == 1) {
        motorstorm::game::DeformationProjection projection{};
        for (unsigned i = 0; i != 4; ++i)
            projection.point[i] = std::bit_cast<float>(words[i]);
        for (unsigned row = 0; row != 2; ++row)
            for (unsigned i = 0; i != 4; ++i)
                projection.rows[row][i] = std::bit_cast<float>(words[4 + row * 4 + i]);
        projection.non_java = words[12] != 0;
        const auto before = projection;
        const auto before_csr = _mm_getcsr();
        const auto before_flags = std::fetestexcept(FE_ALL_EXCEPT);
        const auto before_rounding = std::fegetround();
        const auto result = motorstorm::game::project_deformation_point(projection);
        bool unchanged = projection.non_java == before.non_java;
        for (unsigned i = 0; i != 4; ++i)
            unchanged &= std::bit_cast<std::uint32_t>(projection.point[i]) ==
                         std::bit_cast<std::uint32_t>(before.point[i]);
        for (unsigned row = 0; row != 2; ++row)
            for (unsigned i = 0; i != 4; ++i)
                unchanged &= std::bit_cast<std::uint32_t>(projection.rows[row][i]) ==
                             std::bit_cast<std::uint32_t>(before.rows[row][i]);
        if (_mm_getcsr() != before_csr || std::fetestexcept(FE_ALL_EXCEPT) != before_flags ||
            std::fegetround() != before_rounding || !unchanged) {
            std::fputs("projection state check failed\n", stderr);
            return 5;
        }
        const std::array<std::uint32_t, 2> bits{
            std::bit_cast<std::uint32_t>(result[0]),
            std::bit_cast<std::uint32_t>(result[1])};
        if (std::fwrite(bits.data(), sizeof(bits), 1, output) != 1) return 6;
    }
    const bool failed = std::ferror(input) || std::ferror(output);
    std::fclose(input);
    return std::fclose(output) || failed ? 7 : 0;
}
