#pragma once

#include <array>
#include <cstdint>
#include <span>

namespace motorstorm::game {

// Four groups of four sample positions, in output order. Each group advances
// from the preceding group by advance; advancing a block produces 16 samples.
struct PcmCubicState {
    std::array<float, 16> positions;
    std::array<float, 4> advance;
};

// Normalized signed PCM16, four adjacent samples per cubic interpolation.
// Position i interpolates between samples[i+1] and samples[i+2]. All source
// samples, positions and output storage must be disjoint. Output size must be
// a multiple of 16. Invalid inputs throw before changing state/output.
// Requires AVX2/FMA hardware and OS vector-state admission before entry.
// Arithmetic follows the admitted truncate/flush/fused contract; caller FP
// controls and exception flags are restored on success and failure.
void resample_pcm16_cubic(std::span<const std::int16_t> samples,
                         PcmCubicState& state, std::span<float> output);

} // namespace motorstorm::game
