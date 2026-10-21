#include "world_transforms.h"

#include <immintrin.h>
#include <stdexcept>
#include <vector>

namespace motorstorm::game {
namespace {

class FloatScope {
public:
    FloatScope() : saved_(_mm_getcsr()) {
        _mm_setcsr((saved_ & ~0x603fu) | 0x6000u | 0x8040u | 0x1f80u);
    }
    ~FloatScope() { _mm_setcsr(saved_); }
    FloatScope(const FloatScope&) = delete;
    FloatScope& operator=(const FloatScope&) = delete;

private:
    unsigned saved_;
};

}

void evaluate_world_transforms(WorldTransforms& h) {
    if (!h.transforms_dirty && !h.topology_dirty) return;
    if (h.count && (!h.local || !h.world || !h.parent || !h.root))
        throw std::invalid_argument("World transform buffer ownership");
    if (h.count && h.local == h.world)
        throw std::invalid_argument("World transform input/output alias");

    for (std::uint32_t i = 0; i < h.count; ++i) {
        if (h.parent[i] > i)
            throw std::invalid_argument("World transform parent order");
        const auto owner = h.parent[i] == i ? i : h.root[h.parent[i]];
        if (h.topology_dirty) h.root[i] = owner;
        else if (h.root[i] != owner)
            throw std::invalid_argument("World transform root ownership");
    }
    if (h.topology_dirty) {
        h.transforms_dirty = true;
        h.topology_dirty = false;
    }

    FloatScope floating;
    std::vector<Float4> translations(h.count);
    const auto exponent = _mm_set1_epi32(0x7f800000);
    for (std::uint32_t i = 0; i < h.count; ++i) {
        for (const auto& row : h.local[i].row) {
            const auto bits = _mm_castps_si128(_mm_loadu_ps(row.value));
            if (_mm_movemask_epi8(_mm_cmpeq_epi32(_mm_and_si128(bits, exponent), exponent)))
                throw std::domain_error("World transform non-finite input");
        }
        if (h.parent[i] == i) {
            translations[i] = h.local[i].row[3];
            translations[i].value[3] = 0;
            h.world[i] = h.local[i];
            h.world[i].row[3] = Float4{{0, 0, 0, 1}};
            continue;
        }

        const auto& parent = h.world[h.parent[i]];
        const auto p0 = _mm_loadu_ps(parent.row[0].value);
        const auto p1 = _mm_loadu_ps(parent.row[1].value);
        const auto p2 = _mm_loadu_ps(parent.row[2].value);
        const auto p3 = _mm_loadu_ps(parent.row[3].value);
        for (unsigned row = 0; row < 4; ++row) {
            const auto* a = h.local[i].row[row].value;
            const auto x = _mm_fmadd_ps(p2, _mm_set1_ps(a[2]),
                                      _mm_mul_ps(p0, _mm_set1_ps(a[0])));
            const auto y = _mm_fmadd_ps(p3, _mm_set1_ps(a[3]),
                                      _mm_mul_ps(p1, _mm_set1_ps(a[1])));
            auto result = _mm_add_ps(x, y);
            result = _mm_andnot_ps(_mm_cmpeq_ps(result, _mm_setzero_ps()), result);
            _mm_storeu_ps(h.world[i].row[row].value, result);
        }
    }

    for (std::uint32_t i = 0; i < h.count; ++i) {
        _mm_storeu_ps(h.world[i].row[3].value,
            _mm_add_ps(_mm_loadu_ps(h.world[i].row[3].value),
                       _mm_loadu_ps(translations[h.root[i]].value)));
    }
    if (_mm_getcsr() & 0x1du)
        throw std::domain_error("World transform floating-point range");
    h.transforms_dirty = false;
}

}
