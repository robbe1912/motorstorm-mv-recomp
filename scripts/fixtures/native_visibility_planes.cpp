#include "native_cpu.h"
#include "visibility_planes.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <immintrin.h>
#include <initializer_list>
#include <limits>
#include <stdexcept>

using namespace motorstorm::game;

static void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

static float bits(std::uint32_t value) {
    float result;
    std::memcpy(&result, &value, sizeof result);
    return result;
}

static std::uint32_t seed = 0x126ad53u;
static int bounded(int bound) {
    seed ^= seed << 13;
    seed ^= seed >> 17;
    seed ^= seed << 5;
    return static_cast<int>(seed % (2u * bound + 1u)) - bound;
}

static void exact_cases() {
    // Independent integer oracle: every product and sum is exactly representable.
    // This does not claim exhaustive floating-point or original-AOT equivalence.
    for (int sample = 0; sample < 512; ++sample) {
        VisibilityCorners corners{};
        for (auto& p : corners) {
            p = {float(bounded(16)), float(bounded(16)), float(bounded(16))};
        }
        std::array<VisibilityPlane, 6> planes{};
        for (auto& p : planes) {
            p = {float(bounded(4)), float(bounded(4)), float(bounded(4)), float(bounded(8))};
        }
        const auto original_corners = corners;
        const auto original_planes = planes;
        const auto count = static_cast<std::size_t>(sample % 7);
        const auto threshold = bounded(3);
        VisibilityPlaneResult expected{count, false};
        for (std::size_t i = 0; i < count; ++i) {
            bool outside = false;
            for (const auto& p : corners) {
                const auto& q = planes[i];
                const int distance = int(p.x) * int(q.x) + int(p.y) * int(q.y)
                    + int(p.z) * int(q.z) + int(q.offset);
                outside = outside || distance < threshold;
            }
            if (outside) { expected = {i + 1, true}; break; }
        }
        const auto actual = test_visibility_planes(planes.data(), count, corners, float(threshold));
        require(actual.tested == expected.tested && actual.rejected == expected.rejected,
            "Independent integer plane oracle");
        require(std::memcmp(corners.data(), original_corners.data(), sizeof corners) == 0
            && std::memcmp(planes.data(), original_planes.data(), sizeof planes) == 0,
            "Visibility inputs changed");
    }
}

static void controls() {
    VisibilityCorners corners{};
    for (auto& p : corners) p = {2.0f, 0.0f, 0.0f};
    const VisibilityPlane plane{1.0f, 0.0f, 0.0f, 0.0f};
    for (std::size_t lane = 0; lane < corners.size(); ++lane) {
        corners[lane].x = -1.0f;
        auto result = test_visibility_planes(&plane, 1, corners);
        require(result.rejected && result.tested == 1, "Every corner participates; any failing corner");
        corners[lane].x = 2.0f;
    }
    for (auto& p : corners) p.x = 0.0f;
    require(!test_visibility_planes(&plane, 1, corners).rejected, "Boundary equality is inside");
    const VisibilityPlane ordered[] = {{0, 0, 0, 1}, {0, 0, 0, -1}, {0, 0, 0, -2}};
    auto result = test_visibility_planes(ordered, 3, corners);
    require(result.rejected && result.tested == 2, "First failing plane determines prefix");
    require(!test_visibility_planes(nullptr, 0, corners).rejected, "Empty planes");

    for (auto& p : corners) p = {bits(0x3f800001u), 0, 0};
    const VisibilityPlane rounded{1.5f, 0, 0, -bits(0x3fc00001u)};
    // Exact product is halfway between adjacent floats. Toward-zero chooses the
    // lower one, so subtracting it gives zero, below the positive half-ulp limit.
    require(test_visibility_planes(&rounded, 1, corners, 0x1p-24f).rejected,
        "Independent toward-zero plane product");

    for (auto& p : corners) p = {-1.0f, bits(0x3f800001u), 0};
    const VisibilityPlane fused{1, bits(0x3f7ffffeu), 0, 0};
    // (1+2^-23)*(1-2^-23)-1 = -2^-46. Splitting the FMA under
    // toward-zero instead yields -2^-24, crossing the -2^-40 threshold.
    require(!test_visibility_planes(&fused, 1, corners, -0x1p-40f).rejected,
        "Independent fused plane cancellation");

    bool invalid = false;
    try { test_visibility_planes(nullptr, 1, corners); }
    catch (const std::invalid_argument&) { invalid = true; }
    require(invalid, "Missing plane input rejected");
    const VisibilityPlane nonfinite{std::numeric_limits<float>::infinity(), 0, 0, 0};
    invalid = false;
    try { test_visibility_planes(&nonfinite, 1, corners); }
    catch (const std::invalid_argument&) { invalid = true; }
    require(invalid, "Non-finite plane rejected");
    for (const float x : {std::numeric_limits<float>::max(), std::numeric_limits<float>::min()}) {
        for (auto& p : corners) p = {x, 0, 0};
        const VisibilityPlane range{x == std::numeric_limits<float>::max() ? 2.0f : 0.5f, 0, 0, 0};
        bool rejected = false;
        try { test_visibility_planes(&range, 1, corners); }
        catch (const std::range_error&) { rejected = true; }
        require(rejected, "Unsupported visibility numeric range rejected");
    }
}

int main() {
    if (!supports_native_world_transforms()) {
        std::fputs("UNSUPPORTED: requires AVX2/FMA and OS XMM/YMM state\n", stderr);
        return 77;
    }
    const auto saved = _mm_getcsr();
    try {
        for (unsigned mode = 0; mode < 4; ++mode) {
            const auto caller = (saved & ~0x6000u) | (mode << 13);
            _mm_setcsr(caller);
            controls();
            exact_cases();
            require(_mm_getcsr() == caller, "Exact caller MXCSR restored including exceptions");
        }
        _mm_setcsr(saved);
        std::puts("PASS: native visibility analytic/integer/rounding/fusion/range/FP-state cases");
        return 0;
    } catch (const std::exception& error) {
        _mm_setcsr(saved);
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}
