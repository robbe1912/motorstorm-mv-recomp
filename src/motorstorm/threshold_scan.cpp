#include "threshold_scan.h"

#include <algorithm>
#include <cstring>
#include <limits>
#include <stdexcept>

namespace motorstorm::game {
namespace {
void require_number(float value) {
    std::uint32_t bits;
    static_assert(sizeof(bits) == sizeof(value));
    std::memcpy(&bits, &value, sizeof(bits));
    const auto exponent = bits & 0x7f800000u;
    const auto fraction = bits & 0x007fffffu;
    if (exponent == 0x7f800000u || (exponent == 0 && fraction != 0))
        throw std::invalid_argument("Unsupported threshold numeric range");
}
bool complete(const ThresholdFlags& flags) {
    return flags[0] == 1 && flags[1] == 1 && flags[2] == 1 && flags[3] == 1;
}
} // namespace

ThresholdFlags accumulate_threshold_failures(
    const ThresholdRecord* records, std::size_t record_count,
    unsigned first_component, std::size_t sample_count,
    const std::array<float, 4>& thresholds, ThresholdFlags flags) {
    if (sample_count == 0) return flags;
    if (!records || first_component >= 4 ||
        record_count > std::numeric_limits<std::size_t>::max() / 4 ||
        record_count * 4 < first_component ||
        sample_count > record_count * 4 - first_component)
        throw std::invalid_argument("Invalid threshold sample extent");

    const auto used = (sample_count + first_component - 1) / 4 + 1;
    // Validate the same records even if the accumulated result is saturated.
    // Integer classification avoids NaN/denormal side effects during admission.
    for (float threshold : thresholds) require_number(threshold);
    for (std::size_t r = 0; r < used; ++r)
        for (float value : records[r].samples) require_number(value);

    std::size_t remaining = sample_count;
    for (std::size_t r = 0; remaining && !complete(flags); ++r) {
        const auto take = std::min<std::size_t>(remaining, 4 - first_component);
        const auto& values = records[r].samples;
        if (take == 4) {
            // Every cyclic view visits all four values. Reduce once instead
            // of repeating four rotations and sixteen comparisons.
            const auto largest = std::max(std::max(values[0], values[1]),
                                          std::max(values[2], values[3]));
            for (unsigned view = 0; view < 4; ++view)
                if (!(thresholds[view] > largest)) flags[view] = 1;
        } else {
            for (unsigned view = 0; view < 4; ++view) {
                if (flags[view] == 1) continue;
                for (unsigned c = first_component; c < first_component + take; ++c)
                    if (!(thresholds[view] > values[(c + view) % 4])) {
                        flags[view] = 1;
                        break;
                    }
            }
        }
        remaining -= take;
        first_component = 0;
    }
    return flags;
}

} // namespace motorstorm::game
