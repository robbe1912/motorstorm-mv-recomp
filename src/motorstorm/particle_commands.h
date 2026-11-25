#pragma once
#include "particle_box_collision.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Commands of one native dispatcher run.
enum { MOTORSTORM_COMMANDS = 32 };

// Local-store layout of the particle job (image 213).
enum {
    MOTORSTORM_COMMAND_SLOT_COUNT = 11,  // emitter slots of 96 bytes at header + 704
    MOTORSTORM_COMMAND_COUNTER = 36,     // counted commands; above 127 no operator runs (word)
    MOTORSTORM_COMMAND_LIFE = 44,        // 128 life ratios (words)
    MOTORSTORM_COMMAND_EVENTS = 684,     // used, capacity and buffer words
    MOTORSTORM_COMMAND_FLAG = 736        // completion flag (word)
};

// Dispatcher state that the original keeps in callee-saved registers.
typedef struct { uint32_t header, list, data, index, count; } MotorstormCommandState;

typedef struct {
    uint32_t commands;                                 // commands of the run
    uint32_t slots, collisions;                        // operator 8 and operator 5 calls
    uint8_t scan[MOTORSTORM_COMMANDS];                 // completion scan followed the command
    int finished;                                      // the list ended; the epilogue runs next
    uint32_t collision_list, collision_data, collision_index;  // position of the last collision
} MotorstormCommandTrace;

typedef struct {
    uint32_t count;
    MotorstormCollisionResult item[MOTORSTORM_COMMANDS];
} MotorstormCommandResults;

// Runs the command loop of the particle job on a writable local-store image.
// Operator 8 copies an emitter slot. Operator 5 runs the box collision batch
// with its event publication and removal. Each command advances the payload
// and runs the completion scan when the flag word is one. The command counter
// stays unchanged: the original counts only operators 26 and 27, and a counter
// above 127 stops the run before the skipped operator. The run stops
// before the first other operator, when a bound fails or at the end of the
// list. Returns 0 without any change when the first command is
// unsupported; otherwise the image, the state and the trace hold the applied
// prefix and the collision results are recorded in order. `stack` is the
// dispatcher frame pointer; a collision keeps its temporary payload at
// stack - 368 and needs 432 bytes below stack + 32.
int motorstorm_particle_commands_plan(uint8_t* image, MotorstormCommandState* state, uint32_t stack,
                                      uint32_t limit, MotorstormCommandResults* results,
                                      MotorstormCommandTrace* trace);

// Publishes a planned run on the local store with the recorded collision
// results; no collision is computed again. The image must still hold the
// planned input. Returns 0 without any change when a bound of the plan fails.
int motorstorm_particle_commands_apply(uint8_t* ls, const MotorstormCommandState* before, uint32_t stack,
                                       const MotorstormCommandResults* results,
                                       const MotorstormCommandTrace* trace,
                                       MotorstormCommandState* after);

#ifdef __cplusplus
}
#endif
