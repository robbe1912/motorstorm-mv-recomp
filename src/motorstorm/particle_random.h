#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum { MOTORSTORM_RANDOM_LANES = 4, MOTORSTORM_RANDOM_REGISTERS = 10, MOTORSTORM_RANDOM_STATE = 160 };
/* Entry addresses of the random generator of job image 213 in the local store. */
enum {
    MOTORSTORM_RANDOM_ENTRY_RUN = 0x170d0,  /* fills the table on the first call, then returns one number */
    MOTORSTORM_RANDOM_ENTRY_INIT = 0x17248  /* takes the seed from r3 */
};

/* One quadword as four words. Word 0 is the preferred slot. */
typedef struct { uint32_t word[MOTORSTORM_RANDOM_LANES]; } MotorstormRandomQuadword;
typedef struct {
    MotorstormRandomQuadword registers[MOTORSTORM_RANDOM_REGISTERS]; /* r2 to r11 */
    MotorstormRandomQuadword seed;         /* local store 0x174A0 to 0x174AF */
    uint8_t state[MOTORSTORM_RANDOM_STATE]; /* local store 0x17DD0 to 0x17E70: marker, index, table */
} MotorstormRandomCall;

/* Computes one call of the generator. At entry, the call holds the registers r2 to r11
   and the local store bytes. At exit, they hold the values that the original
   instructions 0x170D0 to 0x17258 leave. The result is in r3.
   Returns 0 when the entry is not one of the two entry addresses. */
int motorstorm_particle_random(uint32_t entry, MotorstormRandomCall* call);

/* One call on a plain local store and register file. gpr holds four words for each of
   the 128 registers. Returns 0 when the entry is not supported. */
int motorstorm_particle_random_call(uint8_t* ls, uint32_t* gpr, uint32_t entry);

#ifdef __cplusplus
}
#endif
