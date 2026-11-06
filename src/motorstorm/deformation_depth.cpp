#include "deformation_depth.h"

#include <bit>
#include <cfenv>
#include <cmath>
#include <stdexcept>
#if defined(_M_X64) || defined(__x86_64__)
#include <immintrin.h>
#endif

namespace motorstorm::game {
namespace {

bool fraction_valid(float value) {
    const auto bits = std::bit_cast<std::uint32_t>(value);
    return bits <= 0x3f800000u || bits == 0x80000000u;
}

class ScopedDepthFp {
public:
    ScopedDepthFp() {
#if defined(_M_X64) || defined(__x86_64__)
        csr_ = _mm_getcsr();
#endif
        if (std::feholdexcept(&environment_) != 0)
            throw std::runtime_error("Cannot save depth sampling FP state");
        if (std::fesetround(FE_TONEAREST) != 0) {
            std::fesetenv(&environment_);
            throw std::runtime_error("Cannot select depth sampling rounding");
        }
#if defined(_M_X64) || defined(__x86_64__)
        _mm_setcsr((_mm_getcsr() & ~0xe07fu) | 0x1f80u);
#endif
    }
    ~ScopedDepthFp() {
        std::fesetenv(&environment_);
#if defined(_M_X64) || defined(__x86_64__)
        _mm_setcsr(csr_);
#endif
    }
    ScopedDepthFp(const ScopedDepthFp&) = delete;
    ScopedDepthFp& operator=(const ScopedDepthFp&) = delete;
private:
    std::fenv_t environment_;
#if defined(_M_X64) || defined(__x86_64__)
    unsigned csr_;
#endif
};

double single(double value) { return static_cast<float>(value); }
double multiply(double a, double b) { return single(a * b); }
double madd(double a, double b, double c) { return single(std::fma(a, b, c)); }

} // namespace

float sample_deformation_depth(const DepthPatch& patch, DepthSampleMode mode) {
    if (!fraction_valid(patch.x_fraction) || !fraction_valid(patch.y_fraction) ||
        (mode != DepthSampleMode::point && mode != DepthSampleMode::bilinear))
        throw std::invalid_argument("Invalid depth sampling patch");
    const ScopedDepthFp fp;
    constexpr double scale = static_cast<double>(std::bit_cast<float>(0x3b808081u));
    const double a = multiply(patch.samples[0], scale);
    if (mode == DepthSampleMode::point) return static_cast<float>(a);
    const double b = multiply(patch.samples[1], scale);
    const double c = multiply(patch.samples[2], scale);
    const double d = multiply(patch.samples[3], scale);
    const double x = patch.x_fraction, y = patch.y_fraction;
    const double right_top = multiply(x, b);
    const double inverse_y = single(1.0 - y);
    const double inverse_x = single(1.0 - x);
    const double right_bottom = multiply(x, d);
    const double upper_right = multiply(inverse_y, right_top);
    const double left_top = multiply(a, inverse_x);
    const double left_bottom = multiply(c, inverse_x);
    const double top = madd(left_top, inverse_y, upper_right);
    const double with_left_bottom = madd(y, left_bottom, top);
    return static_cast<float>(madd(y, right_bottom, with_left_bottom));
}

} // namespace motorstorm::game
