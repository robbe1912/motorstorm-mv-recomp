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
    uint8_t* ls;         /* local store, MOTORSTORM_VEHICLE_LS_SIZE bytes, in place */
    uint32_t pc;         /* entry address of the block that ran last */
    uint32_t bail_pc;    /* first block that the kernel does not hold; 0 when there is none */
    uint64_t blocks;     /* blocks that ran */
} MotorstormVehicleState;

/* Runs the extent from MOTORSTORM_VEHICLE_ENTRY to its return address MOTORSTORM_VEHICLE_RETURN.
   Returns 1 when the extent returned there: the registers and the local store hold the result.
   Returns 0 when control reached a block that is not ported: the local store can hold partial
   stores of the extent, so the caller restores the state of the entry and runs the original path. */
int motorstorm_vehicle_update(MotorstormVehicleState* state);

/* Same run from the address of a ported segment. Returns 0 when the address is not a ported
   segment or when the kernel stops at a block that it does not hold. */
int motorstorm_vehicle_update_at(MotorstormVehicleState* state, uint32_t address);

#ifdef __cplusplus
}
#endif
