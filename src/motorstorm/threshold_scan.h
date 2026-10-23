#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace motorstorm::game {

struct ThresholdRecord {
    std::array<float, 4> samples;
};
using ThresholdFlags = std::array<std::uint32_t, 4>;

// Four cyclic views of packed samples. For a selected component c, view i
// compares samples[(c+i)%4] against thresholds[i]. A failed strict comparison
// changes that view's flag to 1; otherwise its initial word remains intact.
// Selection continues into the next record after component 3.
// Zero samples read no records. Used records and all thresholds must contain
// only normal finite numbers or signed zero. Invalid inputs throw before any
// floating comparison; input storage and the caller's FP environment are kept.
ThresholdFlags accumulate_threshold_failures(
    const ThresholdRecord* records, std::size_t record_count,
    unsigned first_component, std::size_t sample_count,
    const std::array<float, 4>& thresholds, ThresholdFlags initial);

} // namespace motorstorm::game
