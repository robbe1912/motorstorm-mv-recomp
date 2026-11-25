#include "particle_box_collision.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <xmmintrin.h>

static uint32_t bits(float value) { uint32_t result; memcpy(&result, &value, 4); return result; }
static float number(uint32_t value) { float result; memcpy(&result, &value, 4); return result; }
static MotorstormCollisionVector vec(float x, float y, float z) {
    MotorstormCollisionVector result = {{bits(x), bits(y), bits(z), 0}};
    return result;
}
static MotorstormCollisionBox box(void) {
    MotorstormCollisionBox result = {0};
    result.columns[0] = vec(1, 0, 0);
    result.columns[1] = vec(0, 1, 0);
    result.columns[2] = vec(0, 0, 1);
    result.columns[3].component[3] = bits(1);
    result.half_extent = vec(1, 1, 1);
    result.step = bits(4);
    result.contact_metadata = 0x1234abcd;
    return result;
}
static uint32_t seed = 337;
static float random_value(float scale) {
    seed = seed * 1664525u + 1013904223u;
    return ((float)(seed >> 8) / 8388608.f - 1.f) * scale;
}

int main(void) {
    MotorstormCollisionBox shape = box(), original_box = shape;
    MotorstormCollisionParticle particles[256] = {0}, original[256];
    MotorstormCollisionResult result, poison;
    particles[0] = (MotorstormCollisionParticle){vec(-2, 0, 0), vec(1, 0, 0), 1};
    particles[1] = (MotorstormCollisionParticle){vec(0, 0, 0), vec(1, 0, 0), 1};
    particles[2] = (MotorstormCollisionParticle){vec(2, 2, 0), vec(-1, 0, 0), 1};
    particles[3] = (MotorstormCollisionParticle){vec(2, 0, 0), vec(-1, 0, 0), 1};
    memcpy(original, particles, sizeof(original));
    assert(motorstorm_particle_box_contacts(particles, 4, &shape, &result));
    assert(result.examined == 4 && result.contacts == 2);
    assert(result.hit[0] && !result.hit[1] && !result.hit[2] && result.hit[3]);
    assert(fabsf(number(result.contact[0].component[0]) - 2.f) < .0001f);
    assert(number(result.contact[0].component[1]) > 0);
    assert(result.contact[0].component[3] == shape.contact_metadata);
    assert(!memcmp(original, particles, sizeof(original)) && !memcmp(&original_box, &shape, sizeof(shape)));

    // Independent double-precision slab oracle, away from rounding boundaries.
    unsigned checked = 0;
    for (unsigned sample = 0; sample < 4096; ++sample) {
        particles[0].position = vec(random_value(8), random_value(8), random_value(8));
        particles[0].motion = vec(random_value(4), random_value(4), random_value(4));
        particles[0].enabled = 1;
        double direction[3], length2 = 0, near = -HUGE_VAL, far = HUGE_VAL;
        for (unsigned axis = 0; axis < 3; ++axis) {
            direction[axis] = number(particles[0].motion.component[axis]) + 1.e-7;
            length2 += direction[axis] * direction[axis];
        }
        const double length = sqrt(length2);
        for (unsigned axis = 0; axis < 3; ++axis) {
            const double p = number(particles[0].position.component[axis]);
            const double a = (-1 - p) / (direction[axis] / length);
            const double b = (1 - p) / (direction[axis] / length);
            near = fmax(near, fmin(a, b)); far = fmin(far, fmax(a, b));
        }
        if (fabs(near) < .0001 || fabs(near - far) < .0001 || fabs(near - length * 4) < .0001) continue;
        assert(motorstorm_particle_box_contacts(particles, 1, &shape, &result));
        assert(result.hit[0] == (near <= far && near > 0 && near <= length * 4));
        ++checked;
    }
    assert(checked > 4000);

    memset(&poison, 0xa5, sizeof(poison));
    result = poison; particles[0].motion.component[0] = 0x7fc00001;
    assert(!motorstorm_particle_box_contacts(particles, 1, &shape, &result));
    assert(!memcmp(&result, &poison, sizeof(result)));
    particles[0].enabled = 0;
    assert(motorstorm_particle_box_contacts(particles, 1, &shape, &result) && !result.contacts);
    particles[0].enabled = 1; particles[0].motion = vec(1, 0, 0);
    result = poison; shape.columns[0].component[3] = bits(1);
    assert(!motorstorm_particle_box_contacts(particles, 1, &shape, &result));
    assert(!memcmp(&result, &poison, sizeof(result)));
    shape = box();
    assert(!motorstorm_particle_box_contacts(particles, 257, &shape, &result));
    assert(!motorstorm_particle_box_contacts(particles, 1, &shape, (MotorstormCollisionResult*)particles));
    assert(motorstorm_particle_box_contacts(NULL, 0, &shape, &result) && !result.examined);
    const unsigned saved = _mm_getcsr(), changed = saved ^ 0x4000u;
    _mm_setcsr(changed);
    assert(motorstorm_particle_box_contacts(particles, 1, &shape, &result));
    assert(_mm_getcsr() == changed); _mm_setcsr(saved);
    printf("PASS %u independent slab cases, payload, immutable inputs, declines and FP state\n", checked);
    return 0;
}
