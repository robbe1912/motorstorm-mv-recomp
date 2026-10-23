#ifndef PS3EMU_NATIVE_ATOMIC_OBSERVER_H
#define PS3EMU_NATIVE_ATOMIC_OBSERVER_H

#include <stdint.h>

/* Diagnostic build only; no probe branch, clock or buffer in ordinary builds. */
#ifndef PS3_ATOMIC_OBSERVATION
#define PS3_ATOMIC_OBSERVATION 0
#endif

#ifdef __cplusplus
extern "C" {
#endif
enum {
    PS3_ATOMIC_PPU32 = 1, PS3_ATOMIC_PPU64 = 2, PS3_ATOMIC_SPU_STORE = 3,
    PS3_ATOMIC_CLOCK_INVALID = 1u, PS3_ATOMIC_ATTEMPTED = 2u,
    PS3_ATOMIC_COMMITTED = 4u, PS3_ATOMIC_RESERVATION_LOST = 8u,
    PS3_ATOMIC_DATA_UNAVAILABLE = 16u, PS3_ATOMIC_CONTEXT_UNKNOWN = 32u,
    PS3_ATOMIC_INVALID_RANGE = 64u
};
typedef struct ps3_atomic_observation {
    uint64_t begin_tick, end_tick, address;
    uintptr_t context;
    uint32_t source, command, size, flags, saved_pc, return_address;
    uint8_t before[128], after[128]; /* Guest memory byte order; unused bytes zero. */
} ps3_atomic_observation;
typedef struct ps3_atomic_observer {
    void* user;
    uint64_t (*clock)(void*);
    void (*observe)(void*, const ps3_atomic_observation*);
    int (*accept)(void*, uint32_t source, uintptr_t context, uint64_t address, uint32_t size);
} ps3_atomic_observer;

/* Install/clear ONLY while all producers are quiescent. The immutable observer
 * and user state must live until producers stop. Return 0 for malformed input
 * or a non-NULL observer in a build without probes; owners must report failure.
 * Callbacks run outside reservation/coherency locks and must return normally,
 * without guest writes, runtime reentry, allocation, formatting or file I/O.
 * clock supplies one owner-defined monotonic domain; 0/backwards is flagged.
 * [begin,end] BOUNDS the operation; neither endpoint is its exact commit time.
 * saved_pc/return_address are raw context fields, not precise instruction IDs.
 * Context addresses alone are not lifetime-qualified job identities.
 * Each event is a store request. ATTEMPTED means it entered the valid-memory
 * atomic path; range rejection and early PPU reservation rejection leave it
 * clear. It does not prove a hardware CAS executed. Only COMMITTED is success. */
/* Optional accept runs before clocks/copies/locks. NULL accepts all. Owners must
 * document filter coverage and expose excluded/unknown paths in their analysis;
 * rejected operations are not evidence of absence. All callback restrictions
 * above also apply to accept. */
int ps3_atomic_observer_install_ppu(const ps3_atomic_observer*);
int ps3_atomic_observer_install_spu(const ps3_atomic_observer*);
#ifdef __cplusplus
}
#endif

#if PS3_ATOMIC_OBSERVATION
#include <string.h>
static inline const ps3_atomic_observer* ps3_atomic_observer_select(
    const ps3_atomic_observer* o, uint32_t source, uintptr_t context,
    uint64_t address, uint32_t size)
{
    return o && (!o->accept || o->accept(o->user, source, context, address, size)) ? o : NULL;
}
static inline void ps3_atomic_observation_begin(ps3_atomic_observation* e,
    const ps3_atomic_observer* o, uint32_t source, uint32_t command,
    uint64_t address, uint32_t size, uintptr_t context, uint32_t pc, uint32_t lr)
{
    memset(e, 0, sizeof(*e));
    e->source = source; e->command = command; e->address = address;
    e->size = size; e->context = context; e->saved_pc = pc;
    e->return_address = lr;
    e->begin_tick = o->clock(o->user);
}
static inline void ps3_atomic_observation_end(ps3_atomic_observation* e,
    const ps3_atomic_observer* o, uint32_t flags)
{
    e->end_tick = o->clock(o->user);
    e->flags = flags;
    if (!e->context) e->flags |= PS3_ATOMIC_CONTEXT_UNKNOWN;
    if (!e->begin_tick || !e->end_tick || e->end_tick < e->begin_tick)
        e->flags |= PS3_ATOMIC_CLOCK_INVALID;
    o->observe(o->user, e);
}
static inline void ps3_atomic_scalar_end(ps3_atomic_observation* e,
    const ps3_atomic_observer* o, const void* observed, const void* desired, int ok)
{
    /* compare_exchange leaves the actual old value in expected on failure. */
    memcpy(e->before, observed, e->size);
    memcpy(e->after, ok ? desired : observed, e->size);
    ps3_atomic_observation_end(e, o,
        PS3_ATOMIC_ATTEMPTED | (ok ? PS3_ATOMIC_COMMITTED : 0));
}
#endif
#endif
