/* Opt-in migration seam for bounded, privately owned, channel-free leaves.
 * Register before the first interpreter run; registrations are copied and then
 * frozen process-wide. Registered callback code lives for the process lifetime.
 * Preparation is read-only and thread-safe. Its plan/cookie must survive until
 * the immediate same-thread execute call and be safe to discard without it;
 * recursive runs cannot use this seam.
 * Decline leaves all state/FP/TLS unchanged. Accepted plans report the exact
 * guest instruction count and final instruction PC, not a host-work estimate.
 * Execute preserves memory/ABI/FP/TLS and sets the real guest continuation.
 * Both callbacks must preserve interrupt/DMA ownership, never call channels,
 * and must not throw. The runtime cannot establish arbitrary callback fidelity;
 * users must prove their own code/data guard, ownership and differential parity.
 */
#ifndef SPU_NATIVE_LEAF_H
#define SPU_NATIVE_LEAF_H
#include "spu_context.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct spu_native_leaf_plan spu_native_leaf_plan;
struct spu_native_leaf_plan {
    uint64_t instructions;
    uint32_t resume_pc, last_pc;
    void (*execute)(spu_context*, const spu_native_leaf_plan*);
    const void* cookie;
};
typedef struct {
    uint32_t begin, end; /* aligned, half-open instruction extent in LS */
    int (*prepare)(const spu_context*, uint64_t remaining, spu_native_leaf_plan*);
} spu_native_leaf;
/* 0 success, -1 visible invalid/conflicting/full/late registration. Different
 * guards may share an extent; more than one accepting guard is a fatal error. */
int spu_native_leaf_register(const spu_native_leaf* leaf);
#ifdef __cplusplus
}
#endif
#endif
