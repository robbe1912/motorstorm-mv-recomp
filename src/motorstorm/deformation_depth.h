#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace motorstorm::game {

enum class DepthSampleMode { point, bilinear };

struct DepthPatch {
    // Top left, top right, bottom left, bottom right, from one coherent view.
    std::array<std::uint8_t, 4> samples;
    float x_fraction;
    float y_fraction;
};

// A two-by-two plan recovered from the original GetDepth query after its
// surface coordinate transform has succeeded. Coordinates are normalized and
// must be finite in [0,1]; dimensions are positive signed-int-sized values.
// The original clamps only the top-left coordinate. In bilinear mode its
// right/below loads are not clamped, so the owner must admit a coherent view
// containing those byte offsets before sampling them.
struct DeformationDepthPlan {
    std::array<std::size_t, 4> byte_offsets;
    float x_fraction;
    float y_fraction;
};

DeformationDepthPlan plan_deformation_depth(
    float normalized_x, float normalized_y, std::uint32_t width,
    std::uint32_t height, std::uint32_t bytes_per_pixel);

// Fractions must be finite and in [0,1]. The operation follows the original
// binary32 rounding boundaries and double fused multiply-add, with nearest-even
// rounding and gradual underflow. Caller FP state is restored on every exit.
// Acquiring the view, coordinate transformation, borders and synchronization
// belong to the caller; this function does not access guest or GPU memory.
float sample_deformation_depth(const DepthPatch& patch, DepthSampleMode mode);

} // namespace motorstorm::game
