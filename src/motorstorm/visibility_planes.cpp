#include "visibility_planes.h"

#include <cmath>
#include <immintrin.h>
#include <stdexcept>

namespace motorstorm::game {
namespace {

class ScopedVisibilityFp {
public:
    ScopedVisibilityFp() : saved_(_mm_getcsr()) {
        _mm_setcsr((saved_ & ~0x603fu) | 0x6000u | 0x8040u | 0x1f80u);
    }
    ~ScopedVisibilityFp() { _mm_setcsr(saved_); }
    ScopedVisibilityFp(const ScopedVisibilityFp&) = delete;
    ScopedVisibilityFp& operator=(const ScopedVisibilityFp&) = delete;
private:
    unsigned saved_;
};

void require_finite(float value) {
    if (!std::isfinite(value)) {
        throw std::invalid_argument("Non-finite visibility input");
    }
}

} // namespace

VisibilityPlaneResult test_visibility_planes(
    const VisibilityPlane* planes, std::size_t count,
    const VisibilityCorners& corners, float threshold) {
    if (count == 0) return {0, false};
    if (!planes) throw std::invalid_argument("Missing visibility planes");

    const ScopedVisibilityFp fp;
    require_finite(threshold);
    for (const auto& corner : corners) {
        require_finite(corner.x);
        require_finite(corner.y);
        require_finite(corner.z);
    }
    for (std::size_t i = 0; i < count; ++i) {
        require_finite(planes[i].x);
        require_finite(planes[i].y);
        require_finite(planes[i].z);
        require_finite(planes[i].offset);
    }

    const auto x = _mm256_setr_ps(corners[0].x, corners[1].x, corners[2].x,
        corners[3].x, corners[4].x, corners[5].x, corners[6].x, corners[7].x);
    const auto y = _mm256_setr_ps(corners[0].y, corners[1].y, corners[2].y,
        corners[3].y, corners[4].y, corners[5].y, corners[6].y, corners[7].y);
    const auto z = _mm256_setr_ps(corners[0].z, corners[1].z, corners[2].z,
        corners[3].z, corners[4].z, corners[5].z, corners[6].z, corners[7].z);
    const auto limit = _mm256_set1_ps(threshold);

    for (std::size_t i = 0; i < count; ++i) {
        const auto& plane = planes[i];
        auto distance = _mm256_mul_ps(x, _mm256_set1_ps(plane.x));
        distance = _mm256_fmadd_ps(y, _mm256_set1_ps(plane.y), distance);
        distance = _mm256_fmadd_ps(z, _mm256_set1_ps(plane.z), distance);
        distance = _mm256_add_ps(distance, _mm256_set1_ps(plane.offset));
#if defined(__GNUC__)
        // GCC does not model arithmetic exception flags as data dependencies of
        // stmxcsr. Materialize the whole vector before observing its flags.
        __asm__ __volatile__("" : "+x"(distance) : : "memory");
#endif
        if (_mm_getcsr() & 0x1du) {
            throw std::range_error("Unsupported visibility numeric range");
        }
        const auto outside = _mm256_cmp_ps(distance, limit, _CMP_LT_OQ);
        if (_mm256_movemask_ps(outside) != 0) return {i + 1, true};
    }
    return {count, false};
}

} // namespace motorstorm::game
