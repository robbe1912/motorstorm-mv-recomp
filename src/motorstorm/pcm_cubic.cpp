#include "pcm_cubic.h"

#include <bit>
#include <cstddef>
#include <immintrin.h>
#include <stdexcept>

namespace motorstorm::game {
namespace {

class AudioFpScope {
public:
    AudioFpScope() : saved_(_mm_getcsr()) {
        _mm_setcsr((saved_ & ~0x603fu) | 0x6000u | 0x8040u | 0x1f80u);
    }
    ~AudioFpScope() { _mm_setcsr(saved_); }
    AudioFpScope(const AudioFpScope&) = delete;
    AudioFpScope& operator=(const AudioFpScope&) = delete;
private:
    unsigned saved_;
};

__m128 canonical(__m128 value) {
    const auto bits = _mm_castps_si128(value);
    const auto magnitude = _mm_and_si128(bits, _mm_set1_epi32(0x7fffffff));
    return _mm_castsi128_ps(_mm_andnot_si128(
        _mm_cmpeq_epi32(magnitude, _mm_setzero_si128()), bits));
}
__m128 add(__m128 a, __m128 b) { return canonical(_mm_add_ps(a, b)); }
__m128 sub(__m128 a, __m128 b) { return canonical(_mm_sub_ps(a, b)); }
__m128 mul(__m128 a, __m128 b) { return canonical(_mm_mul_ps(a, b)); }
__m128 fused(__m128 a, __m128 b, __m128 c) {
    return canonical(_mm_fmadd_ps(a, b, c));
}

bool overlaps(const void* a, std::size_t an, const void* b, std::size_t bn) {
    if (!an || !bn) return false;
    const auto av = reinterpret_cast<std::uintptr_t>(a);
    const auto bv = reinterpret_cast<std::uintptr_t>(b);
    return av <= bv ? bv - av < an : av - bv < bn;
}

void advance(PcmCubicState& state) {
    const auto step = _mm_loadu_ps(state.advance.data());
    auto position = _mm_loadu_ps(state.positions.data() + 12);
    for (unsigned group = 0; group < 4; ++group) {
        position = add(position, step);
        _mm_storeu_ps(state.positions.data() + group * 4, position);
    }
}

void validate_positions(const PcmCubicState& state, std::size_t count) {
    for (float position : state.positions) {
        const auto bits = std::bit_cast<std::uint32_t>(position);
        if ((bits & 0x7f800000u) == 0x7f800000u ||
            ((bits & 0x80000000u) && (bits & 0x7fffffffu)) ||
            position >= static_cast<float>(count - 3)) {
            throw std::invalid_argument("PCM cubic position outside source");
        }
    }
}

__m128 interpolate(std::span<const std::int16_t> samples, __m128 position) {
    alignas(16) std::int32_t indices[4];
    _mm_store_si128(reinterpret_cast<__m128i*>(indices), _mm_cvttps_epi32(position));
    alignas(16) float points[4][4];
    for (unsigned point = 0; point < 4; ++point) {
        for (unsigned lane = 0; lane < 4; ++lane) {
            points[point][lane] = static_cast<float>(samples[indices[lane] + point]) * 0x1p-15f;
        }
    }
    const auto x0 = _mm_load_ps(points[0]), x1 = _mm_load_ps(points[1]);
    const auto x2 = _mm_load_ps(points[2]), x3 = _mm_load_ps(points[3]);
    const auto t = sub(position, _mm_cvtepi32_ps(_mm_load_si128(
        reinterpret_cast<const __m128i*>(indices))));
    const auto half = _mm_set1_ps(0.5f);
    const auto u = mul(sub(x2, x0), half);
    const auto v = sub(x1, x2), w = sub(x3, x1);
    const auto h = add(u, v), j = add(v, h);
    const auto k = fused(w, half, j), l = add(h, k);
    const auto negative_l = _mm_xor_ps(l, _mm_set1_ps(-0.0f));
    const auto m = fused(t, k, negative_l);
    const auto n = fused(t, m, u);
    return fused(t, n, x1);
}

} // namespace

void resample_pcm16_cubic(std::span<const std::int16_t> samples,
                         PcmCubicState& state, std::span<float> output) {
    if (samples.size() < 4 || samples.size() > (1u << 24) || output.size() % 16 ||
        overlaps(samples.data(), samples.size_bytes(), output.data(), output.size_bytes()) ||
        overlaps(&state, sizeof(state), samples.data(), samples.size_bytes()) ||
        overlaps(&state, sizeof(state), output.data(), output.size_bytes())) {
        throw std::invalid_argument("Invalid PCM cubic storage");
    }
    for (float step : state.advance) {
        if ((std::bit_cast<std::uint32_t>(step) & 0x7f800000u) == 0x7f800000u) {
            throw std::invalid_argument("Non-finite PCM cubic advance");
        }
    }
    AudioFpScope fp;
    auto checked = state;
    validate_positions(checked, samples.size());
    for (std::size_t block = 0; block < output.size(); block += 16) {
        advance(checked);
        validate_positions(checked, samples.size());
    }
    for (std::size_t block = 0; block < output.size(); block += 16) {
        for (unsigned group = 0; group < 4; ++group) {
            _mm_storeu_ps(output.data() + block + group * 4,
                         interpolate(samples, _mm_loadu_ps(state.positions.data() + group * 4)));
        }
        advance(state);
    }
}

} // namespace motorstorm::game
