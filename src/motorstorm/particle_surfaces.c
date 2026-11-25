#include "particle_surfaces.h"
#include "spu_helpers.h"
#include <string.h>

typedef u128 Vector;

// Record words. The frame words at 32 hold the life counter at word 9.
enum { POSITION = 0, FRAME = 8, MOTION = 12, SIZE = 16, ENABLED = 25 };
// Big-endian word order of a rotated slot or payload quadword.
enum { ROTATE1 = 4, ROTATE2 = 8, ROTATE3 = 12 };

static int supported_number(uint32_t value) {
    const uint32_t exponent = value & UINT32_C(0x7f800000);
    return exponent != UINT32_C(0x7f800000) &&
           (exponent || !(value & UINT32_C(0x007fffff)));
}

static int supported(const uint32_t* words, unsigned count) {
    for (unsigned i = 0; i < count; ++i)
        if (!supported_number(words[i])) return 0;
    return 1;
}

static Vector vector(const uint32_t* words) {
    Vector result;
    memcpy(result._u32, words, sizeof(result));
    return result;
}
static Vector constant(uint32_t bits) { return spu_splat_u32(bits); }
static Vector splat(Vector value) { return spu_shufb(value, value, spu_ila(0x10203)); }
static Vector rotate(Vector value, unsigned bytes) { return spu_rotqbyi(value, bytes); }
static Vector with_word(Vector base, Vector value, unsigned index) {
    Vector result = base;
    result._u32[index] = value._u32[0];
    return result;
}
// A branch tests the preferred word of a compare mask.
static int any(Vector mask) { return mask._u32[0] != 0; }

// Every lane keeps its own pairwise sum order of the original rotate chain.
static Vector dot4(Vector a, Vector b) {
    const Vector pairs = spu_fma(rotate(a, ROTATE1), rotate(b, ROTATE1), spu_fm(a, b));
    return spu_fa(rotate(pairs, ROTATE2), pairs);
}
static Vector norm4(Vector a) {
    const Vector pairs = spu_fma(rotate(a, ROTATE1), rotate(a, ROTATE1), spu_fm(a, a));
    return spu_fma(rotate(a, ROTATE2), rotate(a, ROTATE2), pairs);
}

// Plane crossing time of a particle at signed distance `distance` that moves
// with normal speed `speed`: -(distance) / speed with one Newton step.
static Vector crossing_time(Vector distance, Vector speed) {
    const Vector estimate = spu_fi(speed, spu_frest(speed));
    const Vector scaled = spu_fm(distance, estimate);
    return spu_fma(spu_fnms(scaled, speed, distance), estimate, scaled);
}

// Motion change at a plane contact. Small tangential speed keeps the normal
// component scaled by payload word 2; large tangential speed scales the
// tangential part by payload word 1 instead.
static Vector contact_motion(Vector motion, Vector normal, Vector perpendicular, Vector threshold,
                             const uint32_t* data) {
    const Vector weight2 = splat(rotate(vector(data), ROTATE2));
    if (any(spu_fcgt(norm4(perpendicular), threshold))) {
        const Vector reflected = spu_fm(normal, weight2);
        return spu_fms(perpendicular, splat(rotate(vector(data), ROTATE1)), reflected);
    }
    return spu_fnms(normal, weight2, perpendicular);
}

// Triangle and rectangle contacts need two in-plane axes. The original builds
// them from the slot's Y and Z axes with two scaled cross products.
typedef struct { Vector u, v, u_rotated, v_rotated; } Frame;

static Frame frame(MotorstormSurfaceVector axis_y, MotorstormSurfaceVector axis_z) {
    // Shuffle patterns of the original: rotate by one and by two words.
    Vector pattern1, pattern2;
    pattern1._u32[0] = 0x04050607; pattern1._u32[1] = 0x08090a0b;
    pattern1._u32[2] = 0x00010203; pattern1._u32[3] = 0x0c0d0e0f;
    pattern2._u32[0] = 0x08090a0b; pattern2._u32[1] = 0x00010203;
    pattern2._u32[2] = 0x04050607; pattern2._u32[3] = 0x0c0d0e0f;
    const Vector b = vector(axis_y.component), c = vector(axis_z.component), zero = constant(0);
    const Vector b1 = rotate(b, ROTATE1), b2 = rotate(b, ROTATE2);
    const Vector c1 = rotate(c, ROTATE1), c2 = rotate(c, ROTATE2);
    const Vector p24 = spu_fm(spu_shufb(b, b, pattern1), spu_shufb(c, c, pattern2));
    const Vector p26 = spu_fm(b2, c);
    const Vector p29 = spu_fm(b, c2);
    const Vector cross = spu_fnms(spu_shufb(b, b, pattern2), spu_shufb(c, c, pattern1), p24);
    const Vector cross2 = rotate(cross, ROTATE2), cross1 = rotate(cross, ROTATE1);
    const Vector p36 = spu_fm(c2, cross), p37 = spu_fm(b2, cross);
    const Vector p39 = spu_fm(b1, cross), p40 = spu_fm(cross2, b1);
    const Vector p41 = spu_fm(c1, cross), p42 = spu_fm(cross2, b);
    const Vector p43 = spu_fnms(c, cross2, p36);
    const Vector p44 = spu_fm(c2, cross1);
    const Vector p45 = spu_fms(b, cross1, p39), p46 = spu_fnms(b2, cross1, p40);
    const Vector p47 = spu_fms(c, cross1, p41);
    const Vector p48 = spu_fm(p40, c), p49 = spu_fs(p37, p42);
    const Vector p50 = spu_fms(c1, cross2, p44);
    const Vector p52 = spu_fms(p42, c1, p48);
    const Vector p57 = spu_fnms(p37, c1, p52);
    const Vector a = with_word(with_word(with_word(zero, p46, 0), p49, 1), p45, 2);
    const Vector d = with_word(with_word(with_word(zero, p50, 0), p43, 1), p47, 2);
    const Vector p61 = spu_fnms(p29, cross1, p57);
    const Vector p62 = spu_fma(p36, b1, p61);
    const Vector squared = spu_fma(p26, cross1, p62);
    // Refined reciprocal of the squared norm.
    const Vector estimate = spu_fi(squared, spu_frest(squared));
    const Vector one = constant(0x3f800000u);
    const Vector product = spu_fm(one, estimate);
    const Vector reciprocal = spu_fma(spu_fnms(product, squared, one), estimate, product);
    const Vector sign = constant(0x80000000u);
    Frame result;
    result.u = spu_fm(d, splat(reciprocal));
    result.v = spu_fm(a, splat(spu_xor(reciprocal, sign)));
    result.u_rotated = rotate(result.u, ROTATE1);
    result.v_rotated = rotate(result.v, ROTATE1);
    return result;
}

// Signed distance product of the step across the slot's X plane. Zero is
// returned when the particle does not cross the plane.
static int crosses(Vector position, Vector motion, Vector step, Vector axis, Vector offset, Vector* distance) {
    const Vector moved = spu_fma(motion, step, position);
    const Vector before = spu_fa(dot4(position, axis), offset);
    const Vector after = spu_fa(dot4(moved, axis), offset);
    *distance = before;
    return any(spu_fcgt(constant(0), spu_fm(before, after)));
}

static void contact_record(MotorstormSurfaceRecord* record, const MotorstormSurface* surface,
                           const Frame* axes, int rectangle) {
    if (!record->word[ENABLED]) return;
    const Vector zero = constant(0), sign = constant(0x80000000u), one = constant(0x3f800000u);
    const Vector position = vector(record->word + POSITION), motion = vector(record->word + MOTION);
    const Vector axis = vector(surface->slot.axis_x.component), origin = vector(surface->slot.origin.component);
    const Vector step = splat(constant(surface->step));
    const Vector offset = rotate(vector(surface->slot.parameter[0].component), ROTATE1);
    Vector distance;
    if (!crosses(position, motion, step, axis, offset, &distance)) return;
    const Vector speed = dot4(axis, motion);
    const Vector time = splat(crossing_time(spu_xor(distance, sign), speed));
    const Vector relative = spu_fs(spu_fma(motion, time, position), origin);
    const Vector u = dot4(relative, axes->u), v = dot4(relative, axes->v);
    if (any(spu_fcgt(zero, u)) || any(spu_fcgt(zero, v))) return;
    if (rectangle ? any(spu_fcgt(u, one)) || any(spu_fcgt(v, one)) : any(spu_fcgt(spu_fa(u, v), one)))
        return;
    const Vector normal = spu_fm(axis, splat(speed));
    const Vector perpendicular = spu_fs(motion, normal);
    const Vector result = contact_motion(motion, normal, perpendicular, rotate(vector(surface->data), ROTATE3),
                                         surface->data);
    memcpy(record->word + MOTION, result._u32, sizeof(result));
}

static void plane_record(MotorstormSurfaceRecord* record, const MotorstormSurface* surface) {
    if (!record->word[ENABLED]) return;
    const Vector sign = constant(0x80000000u);
    const Vector position = vector(record->word + POSITION), motion = vector(record->word + MOTION);
    const Vector axis = vector(surface->slot.axis_x.component);
    const Vector step = splat(constant(surface->step));
    const Vector offset = rotate(vector(surface->slot.parameter[0].component), ROTATE1);
    Vector distance;
    if (!crosses(position, motion, step, axis, offset, &distance)) return;
    const Vector speed = dot4(axis, motion);
    const Vector normal = spu_fm(axis, splat(speed));
    const Vector perpendicular = spu_fs(motion, normal);
    const Vector result = contact_motion(motion, normal, perpendicular, rotate(vector(surface->data), ROTATE3),
                                         surface->data);
    memcpy(record->word + MOTION, result._u32, sizeof(result));
}

// Spherical shell around the slot origin. A particle that was inside the outer
// sphere and moves outward is mirrored. A particle that enters from outside is
// pushed back: its tangential speed is kept, or scaled by payload word 1 when
// it exceeds payload word 3.
static void shell_record(MotorstormSurfaceRecord* record, const MotorstormSurface* surface) {
    if (!record->word[ENABLED]) return;
    const Vector zero = constant(0);
    const Vector position = vector(record->word + POSITION), motion = vector(record->word + MOTION);
    const Vector origin = vector(surface->slot.origin.component), inner = vector(surface->slot.parameter[1].component);
    const Vector outer = rotate(vector(surface->slot.parameter[0].component), ROTATE3);
    const Vector step = splat(constant(surface->step));
    const Vector relative_speed = spu_fs(motion, vector(surface->wind.component));
    const Vector moved = spu_fma(relative_speed, step, position);
    const Vector moved_squared = norm4(spu_fs(moved, origin));
    if (any(spu_fcgt(moved_squared, outer)) || any(spu_fcgt(inner, moved_squared))) return;
    const Vector rest = spu_fs(position, origin);
    const Vector rest_squared = norm4(rest);
    const int inside = !(any(spu_fcgt(inner, rest_squared)) || any(spu_fcgt(rest_squared, outer)));
    const Vector radial_squared = dot4(rest, rest);
    const Vector estimate = spu_fi(radial_squared, spu_frsqest(radial_squared));
    const Vector residual = spu_fnms(estimate, spu_fm(estimate, radial_squared), constant(0x3f800001u));
    const Vector outward = spu_fm(rest, spu_fma(residual, spu_fm(estimate, constant(0x3f000000u)), estimate));
    const Vector speed = dot4(relative_speed, outward);
    const Vector normal = spu_fm(outward, splat(speed));
    const Vector tangential = spu_fs(relative_speed, normal);
    Vector result;
    if (inside) {
        if (!any(spu_fcgt(zero, speed))) return;
        result = spu_fs(tangential, normal);
    } else {
        const Vector weight2 = splat(rotate(vector(surface->data), ROTATE2));
        if (any(spu_fcgt(norm4(tangential), rotate(vector(surface->data), ROTATE3))))
            result = spu_fms(tangential, splat(rotate(vector(surface->data), ROTATE1)), spu_fm(normal, weight2));
        else
            result = spu_fnms(normal, weight2, tangential);
    }
    memcpy(record->word + MOTION, result._u32, sizeof(result));
}

typedef struct { Vector minimum_squared, maximum_squared, quarter, residual; } Ring;

// Contact inside a ring of the slot's X plane stops the particle: motion and
// size words are cleared, the enabled flag is cleared, the life word becomes a
// wrapped function of the old motion and the motion is reflected along X.
static void ring_record(MotorstormSurfaceRecord* record, const MotorstormSurface* surface, const Ring* ring) {
    if (!record->word[ENABLED]) return;
    const Vector zero = constant(0), sign = constant(0x80000000u);
    const Vector position = vector(record->word + POSITION), motion = vector(record->word + MOTION);
    const Vector axis = vector(surface->slot.axis_x.component), origin = vector(surface->slot.origin.component);
    const Vector step = splat(constant(surface->step));
    const Vector offset = rotate(vector(surface->slot.parameter[0].component), ROTATE3);
    Vector distance;
    if (!crosses(position, motion, step, axis, offset, &distance)) return;
    const Vector speed = dot4(axis, motion);
    const Vector time = splat(crossing_time(spu_xor(distance, sign), speed));
    const Vector hit_squared = norm4(spu_fs(spu_fma(motion, time, position), origin));
    if (any(spu_fcgt(ring->minimum_squared, hit_squared)) || any(spu_fcgt(hit_squared, ring->maximum_squared))) return;
    memset(record->word + MOTION, 0, 32);
    Vector life = with_word(vector(record->word + FRAME), zero, 2);
    record->word[ENABLED] = 0;
    // Word 9 keeps 12 plus the motion word 1 wrapped into a band of width 4.
    const Vector shifted = rotate(life, ROTATE1);
    const Vector absolute = spu_andc(shifted, sign);
    const Vector scaled = spu_fma(ring->residual, spu_fm(shifted, ring->quarter), spu_fm(shifted, ring->quarter));
    const Vector truncated = spu_cflts(spu_andc(scaled, sign), 173);
    const Vector floor = spu_csflt(truncated, 155), ceiling = spu_csflt(spu_ai(truncated, 1), 155);
    const Vector doubled = spu_fa(absolute, absolute), four = constant(0x40800000u);
    const Vector kept = spu_selb(floor, spu_csflt(spu_ai(truncated, -1), 155), spu_fcgt(absolute, spu_fnms(floor, four, doubled)));
    const Vector band = spu_selb(ceiling, kept, spu_fcgt(absolute, spu_fnms(ceiling, four, doubled)));
    const Vector signed_band = spu_selb(band, scaled, sign);
    const Vector wrapped = spu_fnms(signed_band, four, shifted);
    const Vector finite = spu_and(spu_fcmgt(constant(0x49800000u), scaled), spu_fcmgt(constant(0x7f800000u), shifted));
    life = with_word(life, spu_fa(spu_selb(zero, wrapped, finite), constant(0x41400000u)), 1);
    memcpy(record->word + FRAME, life._u32, sizeof(life));
    const Vector normal = spu_fm(axis, splat(speed));
    const Vector reflected = spu_xor(normal, sign);
    const Vector weight2 = splat(rotate(vector(surface->data), ROTATE2));
    const Vector result =
        any(spu_fcgt(norm4(reflected), rotate(vector(surface->data), ROTATE3)))
            ? spu_fms(reflected, splat(rotate(vector(surface->data), ROTATE1)), spu_fm(normal, weight2))
            : spu_fnms(normal, weight2, reflected);
    memcpy(record->word + MOTION, result._u32, sizeof(result));
}

int motorstorm_particle_surfaces(const MotorstormSurface* surface, MotorstormSurfaceRecord* records,
                                 size_t count) {
    if (!surface || count > MOTORSTORM_SURFACE_PARTICLES || (count && !records)) return 0;
    const uint32_t selector = surface->slot.parameter[0].component[0];
    const int triangle = selector == 2 || selector == 10;
    if (!triangle && selector != 3 && selector != 5 && selector != 9) return 0;
    if (!supported_number(surface->step)) return 0;
    // Selectors 2, 3 and 10 read parameter 1, selector 9 reads 1 to 3 and
    // selector 5 reads 3 and 4.
    const uint32_t* parameter = surface->slot.parameter[0].component;
    if (!supported(parameter + 1, selector == 9 ? 3 : selector == 5 ? 0 : 1) ||
        (selector == 5 && (!supported_number(parameter[3]) ||
                           !supported_number(surface->slot.parameter[1].component[0]))) ||
        !supported(surface->slot.origin.component, 4) || !supported(surface->slot.axis_x.component, 4) ||
        (triangle && (!supported(surface->slot.axis_y.component, 4) || !supported(surface->slot.axis_z.component, 4))) ||
        (selector == 5 && !supported(surface->wind.component, 4)) ||
        !supported(surface->data + 1, 3))
        return 0;
    for (size_t i = 0; i < count; ++i) {
        if (!records[i].word[ENABLED]) continue;
        if (!supported(records[i].word + POSITION, 4) || !supported(records[i].word + MOTION, 4) ||
            (selector == 9 && !supported_number(records[i].word[FRAME + 1])))
            return 0;
    }
    Frame axes = {{0}};
    Ring ring = {{0}};
    if (triangle) axes = frame(surface->slot.axis_y, surface->slot.axis_z);
    if (selector == 9) {
        const Vector parameter = vector(surface->slot.parameter[0].component);
        ring.maximum_squared = spu_fm(rotate(parameter, ROTATE1), rotate(parameter, ROTATE1));
        ring.minimum_squared = spu_fm(rotate(parameter, ROTATE2), rotate(parameter, ROTATE2));
        const Vector four = constant(0x40800000u), one = constant(0x3f800001u);
        ring.quarter = spu_fi(four, spu_frest(four));
        ring.residual = spu_fnms(four, ring.quarter, one);
    }
    for (size_t i = 0; i < count; ++i) {
        if (triangle) contact_record(&records[i], surface, &axes, selector == 10);
        else if (selector == 3) plane_record(&records[i], surface);
        else if (selector == 5) shell_record(&records[i], surface);
        else ring_record(&records[i], surface, &ring);
    }
    return 1;
}
