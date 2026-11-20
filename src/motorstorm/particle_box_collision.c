#include "particle_box_collision.h"
#include "spu_helpers.h"
#include <string.h>

typedef u128 CollisionVector;

static int supported_number(uint32_t value) {
    const uint32_t exponent = value & UINT32_C(0x7f800000);
    return exponent != UINT32_C(0x7f800000) &&
           (exponent || !(value & UINT32_C(0x007fffff)));
}

static int supported_xyz(MotorstormCollisionVector value) {
    for (unsigned i = 0; i < 3; ++i)
        if (!supported_number(value.component[i])) return 0;
    return 1;
}

static int overlap(const void* a, size_t a_size, const void* b, size_t b_size) {
    const uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a_size || !b_size) return 0;
    if (a_size > UINTPTR_MAX - x || b_size > UINTPTR_MAX - y) return 1;
    return x < y + b_size && y < x + a_size;
}

static CollisionVector vector(MotorstormCollisionVector value) {
    CollisionVector result;
    memcpy(result._u32, value.component, sizeof(value.component));
    return result;
}

static CollisionVector transform(const CollisionVector columns[4], CollisionVector value) {
    const CollisionVector x = spu_splat_u32(value._u32[0]);
    const CollisionVector y = spu_splat_u32(value._u32[1]);
    const CollisionVector z = spu_splat_u32(value._u32[2]);
    const CollisionVector w = spu_splat_u32(value._u32[3]);
    return spu_fa(spu_fma(columns[2], z, spu_fm(columns[0], x)),
                  spu_fma(columns[3], w, spu_fm(columns[1], y)));
}

// Each component retains its original pairwise sum order. A single scalar
// dot product changes rounding for the other components of the reciprocal.
static CollisionVector squared_length(CollisionVector value) {
    const CollisionVector next = spu_rotqbyi(value, 4);
    const CollisionVector pairs = spu_fma(next, next, spu_fm(value, value));
    return spu_fa(spu_rotqbyi(pairs, 8), pairs);
}

static CollisionVector unit_direction(CollisionVector value) {
    const CollisionVector squared = squared_length(value);
    const CollisionVector estimate = spu_fi(squared, spu_frsqest(squared));
    const CollisionVector root = spu_fm(estimate, squared);
    const CollisionVector residual = spu_fnms(estimate, root, spu_splat_u32(0x3f800001));
    const CollisionVector half = spu_fm(estimate, spu_splat_u32(0x3f000000));
    return spu_fm(value, spu_fma(residual, half, estimate));
}

static CollisionVector inverse_direction(CollisionVector value) {
    const CollisionVector estimate = spu_fi(value, spu_frest(value));
    const CollisionVector residual = spu_fnms(value, estimate, spu_splat_u32(0x3f800001));
    return spu_fma(residual, estimate, estimate);
}

static uint32_t travel_length(CollisionVector travel) {
    const CollisionVector squared = squared_length(travel);
    const CollisionVector estimate = spu_fi(squared, spu_frsqest(squared));
    const CollisionVector root = spu_fm(estimate, squared);
    const CollisionVector residual = spu_fnms(estimate, root, spu_splat_u32(0x3f800001));
    const CollisionVector half = spu_fm(root, spu_splat_u32(0x3f000000));
    return spu_fma(residual, half, root)._u32[0];
}

static int greater(uint32_t a, uint32_t b) {
    const CollisionVector x = spu_splat_u32(a), y = spu_splat_u32(b);
    return x._f32[0] > y._f32[0];
}

static int contact(const MotorstormCollisionParticle* particle,
                   const MotorstormCollisionBox* box, const CollisionVector columns[4],
                   MotorstormCollisionVector* output) {
    CollisionVector position = vector(particle->position);
    position._u32[3] = 0x3f800000;
    const CollisionVector origin = transform(columns, position);
    CollisionVector relative = spu_fa(spu_fs(vector(particle->motion), vector(box->motion)),
                                      spu_splat_u32(0x33d6bf94));
    relative._u32[3] = 0;
    const CollisionVector motion = transform(columns, relative);
    const CollisionVector direction = unit_direction(motion);
    const CollisionVector inverse = inverse_direction(direction);
    const CollisionVector extent = vector(box->half_extent);
    CollisionVector negative = extent;
    for (unsigned i = 0; i < 4; ++i) negative._u32[i] ^= UINT32_C(0x80000000);
    const CollisionVector first = spu_fm(spu_fs(negative, origin), inverse);
    const CollisionVector second = spu_fm(spu_fs(extent, origin), inverse);
    uint32_t lower[3], upper[3];
    for (unsigned i = 0; i < 3; ++i) {
        const int reversed = greater(0, direction._u32[i]);
        lower[i] = reversed ? second._u32[i] : first._u32[i];
        upper[i] = reversed ? first._u32[i] : second._u32[i];
    }
    const uint32_t near_xy = greater(lower[1], lower[0]) ? lower[1] : lower[0];
    const uint32_t far_xy = greater(upper[0], upper[1]) ? upper[1] : upper[0];
    if (greater(lower[0], upper[1]) || greater(lower[1], upper[0]) ||
        greater(near_xy, upper[2]) || greater(lower[2], far_xy)) return 0;
    const uint32_t near = greater(lower[2], near_xy) ? lower[2] : near_xy;
    if (!greater(near, 0)) return 0;
    const CollisionVector travel = spu_fm(motion, spu_splat_u32(box->step));
    if (greater(near, travel_length(travel))) return 0;

    // Retain the game's contact-payload formula, including its displacement
    // scaling. Replacing it with an idealized ray hit changes consumer data.
    CollisionVector point = spu_fma(travel, spu_splat_u32(near), origin);
    point._u32[3] = box->contact_metadata;
    memcpy(output->component, point._u32, sizeof(output->component));
    return 1;
}

int motorstorm_particle_box_contacts(const MotorstormCollisionParticle* particles,
    size_t count, const MotorstormCollisionBox* box, MotorstormCollisionResult* output) {
    if (!box || !output || count > MOTORSTORM_COLLISION_PARTICLES ||
        (count && !particles) ||
        overlap(output, sizeof(*output), box, sizeof(*box)) ||
        overlap(output, sizeof(*output), particles, count * sizeof(*particles))) return 0;
    if (!supported_number(box->step) || !supported_xyz(box->half_extent) ||
        !supported_xyz(box->motion)) return 0;
    for (unsigned axis = 0; axis < 4; ++axis) {
        if (!supported_xyz(box->columns[axis]) ||
            box->columns[axis].component[3] != (axis == 3 ? 0x3f800000u : 0)) return 0;
    }
    for (size_t i = 0; i < count; ++i)
        if (particles[i].enabled && (!supported_xyz(particles[i].position) ||
                                    !supported_xyz(particles[i].motion))) return 0;

    MotorstormCollisionResult result = {0};
    CollisionVector columns[4];
    for (unsigned i = 0; i < 4; ++i) columns[i] = vector(box->columns[i]);
    const uint64_t scope = spu_sf_simd_enter();
    for (size_t i = 0; i < count; ++i) {
        ++result.examined;
        if (!particles[i].enabled) continue;
        result.hit[i] = (uint8_t)contact(&particles[i], box, columns, &result.contact[i]);
        result.contacts += result.hit[i];
    }
    spu_sf_simd_leave(scope);
    *output = result;
    return 1;
}
