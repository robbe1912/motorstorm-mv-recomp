#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum { MOTORSTORM_COLLISION_PARTICLES = 256 };

// Floating-point bit patterns preserve the original game's arithmetic contract.
// Positions and motion use XYZ; the fourth input component is ignored.
typedef struct { uint32_t component[4]; } MotorstormCollisionVector;
typedef struct {
    MotorstormCollisionVector position, motion;
    uint32_t enabled;
} MotorstormCollisionParticle;

typedef struct {
    // Prepared world-to-box columns. Axis W components are zero; origin W is one.
    MotorstormCollisionVector columns[4];
    MotorstormCollisionVector half_extent, motion;
    uint32_t step, contact_metadata;
} MotorstormCollisionBox;

typedef struct {
    uint8_t hit[MOTORSTORM_COLLISION_PARTICLES];
    MotorstormCollisionVector contact[MOTORSTORM_COLLISION_PARTICLES];
    unsigned examined, contacts;
} MotorstormCollisionResult;

// Immutable typed inputs; no guest memory or execution state. Unsupported numbers,
// extents or aliases return zero without modifying any output. Contacts remain in
// input-index order; the caller owns bounded publication and backwards removal.
int motorstorm_particle_box_contacts(const MotorstormCollisionParticle* particles,
    size_t count, const MotorstormCollisionBox* box, MotorstormCollisionResult* output);

#ifdef __cplusplus
}
#endif
