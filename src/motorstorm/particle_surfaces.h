#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum { MOTORSTORM_SURFACE_PARTICLES = 256 };

// Floating-point bit patterns preserve the original game's arithmetic contract.
typedef struct { uint32_t component[4]; } MotorstormSurfaceVector;

// One emitter slot of the particle header (128 bytes at header + 704): origin,
// three frame axes and eight parameter words. Word 16 selects the operation.
typedef struct {
    MotorstormSurfaceVector origin, axis_x, axis_y, axis_z;
    MotorstormSurfaceVector parameter[2];
} MotorstormSurfaceSlot;

// One 128-byte particle record as big-endian words: position at 0, frame
// words at 32, motion at 48, size words at 64 and the enabled flag at 100.
typedef struct { uint32_t word[32]; } MotorstormSurfaceRecord;

typedef struct {
    MotorstormSurfaceSlot slot;
    // Command payload words 0 to 15. Selector 2, 3, 9 and 10 read words 1, 2
    // and 3; selector 5 reads the same three words for its response.
    uint32_t data[16];
    uint32_t step;                 // header + 1780
    MotorstormSurfaceVector wind;  // header + 992
} MotorstormSurface;

// Applies the surface operation of the slot to each enabled record. Supported
// selectors: 2 (triangle), 3 (plane), 5 (spherical shell), 9 (ring) and 10
// (rectangle). Unsupported selectors, counts above 256 or non-finite and
// denormal input numbers return zero without modifying any record. Records are
// independent; the caller owns publication.
int motorstorm_particle_surfaces(const MotorstormSurface* surface, MotorstormSurfaceRecord* records,
                                 size_t count);

#ifdef __cplusplus
}
#endif
