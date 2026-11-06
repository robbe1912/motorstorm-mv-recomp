#pragma once

#include <array>
#include <cstdint>

namespace motorstorm::game {

enum class DepthSampleMode { point, bilinear };

struct DepthPatch {
    // Top left, top right, bottom left, bottom right, from one coherent view.
    std::array<std::uint8_t, 4> samples;
    float x_fraction;
    float y_fraction;
};

// Fractions must be finite and in [0,1]. The operation follows the original
// binary32 rounding boundaries and double fused multiply-add, with nearest-even
// rounding and gradual underflow. Caller FP state is restored on every exit.
// Acquiring the view, coordinate transformation, borders and synchronization
// belong to the caller; this function does not access guest or GPU memory.
float sample_deformation_depth(const DepthPatch& patch, DepthSampleMode mode);

} // namespace motorstorm::game
