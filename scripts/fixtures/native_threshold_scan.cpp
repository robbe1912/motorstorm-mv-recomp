#include "threshold_scan.h"
#include <cassert>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <vector>
#include <xmmintrin.h>

using namespace motorstorm::game;
namespace {
float number(std::uint32_t bits) {
    float value;
    std::memcpy(&value, &bits, 4);
    return value;
}
ThresholdFlags oracle(const std::vector<ThresholdRecord>& records, unsigned first,
                     std::size_t count, const std::array<float, 4>& thresholds,
                     ThresholdFlags initial) {
    // Independent scalar definition: visit each selected sample in order.
    for (std::size_t n = 0; n < count; ++n)
        for (unsigned view = 0; view < 4; ++view)
            if (!(thresholds[view] > records[(n + first) / 4].samples[
                      ((n + first) % 4 + view) % 4])) initial[view] = 1;
    return initial;
}
void compare(const std::vector<ThresholdRecord>& records, unsigned first,
             std::size_t count, const std::array<float, 4>& thresholds,
             ThresholdFlags initial) {
    const auto expected = oracle(records, first, count, thresholds, initial);
    const auto saved = records;
    const auto before = _mm_getcsr();
    assert(accumulate_threshold_failures(records.data(), records.size(), first,
                                        count, thresholds, initial) == expected);
    assert(_mm_getcsr() == before);
    assert(std::memcmp(records.data(), saved.data(), records.size() * sizeof(ThresholdRecord)) == 0);
}
template<class Function> void rejected(Function run) {
    const auto before = _mm_getcsr();
    bool threw = false;
    try { run(); } catch (const std::invalid_argument&) { threw = true; }
    assert(threw && _mm_getcsr() == before);
}
std::uint32_t seed = 0x214093bu;
std::uint32_t next() {
    seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5;
    return seed;
}
float finite() {
    const auto bits = next();
    return number((bits & 0x807fffffu) | ((1 + next() % 254) << 23));
}
} // namespace
int main() {
    const ThresholdFlags initial{0, 0x12345678u, 0xffffffffu, 1};
    const std::array<float, 4> thresholds{0.0f, -0.0f, 1.0f, -1.0f};
    assert(accumulate_threshold_failures(nullptr, 0, 99, 0, thresholds, initial) == initial);
    std::vector<ThresholdRecord> records(64);
    for (unsigned round = 0; round < 4; ++round) {
        const auto saved = _mm_getcsr();
        _mm_setcsr((saved & ~0x6000u) | (round << 13) | 0x20u);
        for (unsigned iteration = 0; iteration < 2048; ++iteration) {
            for (auto& record : records)
                for (float& value : record.samples) value = finite();
            std::array<float, 4> limits{finite(), finite(), finite(), finite()};
            const unsigned first = next() % 4;
            const auto count = next() % (records.size() * 4 - first + 1);
            compare(records, first, count, limits, initial);
        }
        for (auto& record : records) record.samples = {-0.0f, 0.0f, 1.0f, -1.0f};
        for (unsigned first = 0; first < 4; ++first)
            for (unsigned count = 1; count <= 64; ++count)
                compare(records, first, count, thresholds, initial);
        const auto largest = std::numeric_limits<float>::max();
        compare(records, 3, 249, {largest, largest, largest, largest}, initial);
        _mm_setcsr(saved);
    }
    rejected([&] { accumulate_threshold_failures(nullptr, 1, 0, 1, thresholds, initial); });
    rejected([&] { accumulate_threshold_failures(records.data(), 1, 4, 1, thresholds, initial); });
    rejected([&] { accumulate_threshold_failures(records.data(), 1, 3, 2, thresholds, initial); });
    rejected([&] { accumulate_threshold_failures(records.data(),
        std::numeric_limits<std::size_t>::max(), 0, 1, thresholds, initial); });
    for (auto bits : {1u, 0x807fffffu, 0x7f800000u, 0xff800000u, 0x7fc00000u, 0x7f800001u}) {
        auto limits = thresholds; limits[2] = number(bits);
        rejected([&] { accumulate_threshold_failures(records.data(), records.size(), 0, 8, limits, initial); });
        auto bad = records; bad[0].samples[3] = number(bits);
        rejected([&] { accumulate_threshold_failures(bad.data(), bad.size(), 0, 8, thresholds, {1,1,1,1}); });
    }
    // Unselected records are outside the memory/numeric contract.
    records[1].samples[0] = number(0x7f800001u);
    compare(records, 0, 1, thresholds, initial);
}
