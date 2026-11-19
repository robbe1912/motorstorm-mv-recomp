#ifndef MOTORSTORM_VISIBILITY_BATCH_H
#define MOTORSTORM_VISIBILITY_BATCH_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t local_address;
    uint32_t high_address;
    uint32_t low_address;
    uint32_t tag;
    const uint8_t* payload;
} MotorstormVisibilityFlush;

// Publish the 16 KiB payload before returning. The pointer is borrowed for
// this call. The publisher must preserve the classifier's local-store state.
typedef void (*MotorstormVisibilityPublish)(const MotorstormVisibilityFlush*, void*);

// Read-only admission for a nonempty batch guaranteed to stay below the PUT threshold.
int motorstorm_us_visibility_nonflushing(const uint8_t* ls, unsigned count);

// Classify the debug-US layout in an owned 256 KiB local store after input
// DMA. Return zero without modifying local store on unsupported layouts.
// A potentially flushing batch requires a publisher. The caller qualifies
// the staged image and owns the floating-point scope and the guest epilogue.
int motorstorm_us_visibility_classify(uint8_t* ls, unsigned count, uint32_t output_high,
                                      MotorstormVisibilityPublish publish, void* publication);

// Prepare one debug-US occluder's edge planes from its completed input DMA.
// Unsupported layouts return zero without writes. The caller retains object
// iteration, DMA, register ownership and completion.
int motorstorm_us_visibility_occluder_supported(const uint8_t* ls, unsigned index,
                                               unsigned temporary_normal);
int motorstorm_us_visibility_occluder(uint8_t* ls, unsigned index,
                                     unsigned temporary_normal);

#ifdef __cplusplus
}
#endif

#endif
