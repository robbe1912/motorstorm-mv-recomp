#pragma once

#include <array>
#include <cstddef>

namespace motorstorm::game {

struct VisibilityPoint {
    float x, y, z;
};

struct VisibilityPlane {
    float x, y, z, offset;
};

using VisibilityCorners = std::array<VisibilityPoint, 8>;

struct VisibilityPlaneResult {
    std::size_t tested;
    bool rejected;
};

// Requires baseline CPU/OS admission for AVX2 and FMA. Inputs remain immutable.
// Visit planes in order; reject when any corner's dot product is below threshold.
// Count zero reads no inputs. Otherwise all supplied values must be finite.
// Numeric ranges outside native float semantics throw; caller FP state is restored.
VisibilityPlaneResult test_visibility_planes(
    const VisibilityPlane* planes, std::size_t count,
    const VisibilityCorners& corners, float threshold = 0.0f);

} // namespace motorstorm::game
