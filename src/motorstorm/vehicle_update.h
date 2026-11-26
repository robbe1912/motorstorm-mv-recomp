#pragma once
/* Native kernel for the vehicle update of SPU image 219 (spuvehicle): the extent from
   MOTORSTORM_VEHICLE_ENTRY (the SPU build of evo::vehicle::Vehicle::update) to its return
   address. The kernel works on plain data: the SPU registers and the local store. */
#include "spu_context.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
    MOTORSTORM_VEHICLE_LS_SIZE = 0x40000,
    MOTORSTORM_VEHICLE_ENTRY = 0x11fe0,
    MOTORSTORM_VEHICLE_RETURN = 0x20ce0
};

typedef struct {
    u128 gpr[128];       /* SPU registers; word 0 is the preferred slot */
    uint8_t* ls;         /* local store, MOTORSTORM_VEHICLE_LS_SIZE bytes, changed in place */
    uint32_t pc;         /* word 0 of the register of the return that ran last */
    uint32_t bail_pc;    /* address that the kernel could not take; 0 when the extent returned */
    uint8_t* saved;      /* copy of each 4 KB local store page before its first kernel store; NULL: no copy */
    uint64_t dirty;      /* bit n is set when local store page n differs from its copy */
    const spu_context* ctx; /* NULL, or the context: the kernel tests its interrupt state at jump targets */
} MotorstormVehicleState;

/* Runs the extent from MOTORSTORM_VEHICLE_ENTRY to its return address MOTORSTORM_VEHICLE_RETURN.
   Returns 1 when the extent returned there: gpr, ls and pc hold the state of the return.
   Returns 0 when the kernel stopped (a function that is not ported, an address that it does not
   hold, a waiting interrupt at a jump target, or a return to another address): bail_pc is then
   the address. When `saved` is set, the caller puts back the pages of `dirty` to get the local
   store of the entry, then runs the original path. */
int motorstorm_vehicle_update(MotorstormVehicleState* state);

#ifdef __cplusplus
}
#endif
