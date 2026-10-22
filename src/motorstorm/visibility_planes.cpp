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

VisibilityCorners make_visibility_corners(const VisibilityBox& box) {
    const ScopedVisibilityFp fp;
    const auto point = [](const VisibilityPoint& p) {
        require_finite(p.x); require_finite(p.y); require_finite(p.z);
        return _mm_setr_ps(p.x, p.y, p.z, 0.0f);
    };
    const auto center = point(box.center);
    __m128 axes[3];
    for (unsigned i = 0; i < 3; ++i) {
        require_finite(box.axes[i].extent);
        axes[i] = _mm_mul_ps(point(box.axes[i].direction), _mm_set1_ps(box.axes[i].extent));
    }
    const auto lower = _mm_sub_ps(center, axes[0]);
    const auto upper = _mm_add_ps(center, axes[0]);
    const auto difference = _mm_sub_ps(axes[2], axes[1]);
    const auto diagonal = _mm_add_ps(axes[1], axes[2]);
    const __m128 vertices[] = {
        _mm_add_ps(upper, diagonal), _mm_add_ps(lower, diagonal),
        _mm_add_ps(upper, difference), _mm_add_ps(lower, difference),
        _mm_sub_ps(upper, difference), _mm_sub_ps(lower, difference),
        _mm_sub_ps(upper, diagonal), _mm_sub_ps(lower, diagonal)};
    VisibilityCorners corners;
    for (unsigned i = 0; i < 8; ++i) {
        alignas(16) float coordinates[4];
        // This geometry contract has a single zero representation. Normalizing
        // the result is sufficient: preceding sums contain no division or
        // sign-sensitive branch, and unsupported underflow still throws below.
        const auto words = _mm_castps_si128(vertices[i]);
        const auto magnitude = _mm_and_si128(words, _mm_set1_epi32(0x7fffffff));
        const auto positive = _mm_castsi128_ps(_mm_andnot_si128(
            _mm_cmpeq_epi32(magnitude, _mm_setzero_si128()), words));
        _mm_store_ps(coordinates, positive);
        corners[i] = {coordinates[0], coordinates[1], coordinates[2]};
    }
#if defined(__GNUC__)
    __asm__ __volatile__("" : : "m"(corners) : "memory");
#endif
    if (_mm_getcsr() & 0x1du) {
        throw std::range_error("Unsupported visibility box numeric range");
    }
    return corners;
}

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
