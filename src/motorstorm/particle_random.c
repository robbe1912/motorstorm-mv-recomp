#include "particle_random.h"

/* Local store addresses of the generator state. */
enum { STATE = 0x17dd0, INDEX = 0x17de0, TABLE = 0x17df0, TABLE_END = 0x17e70 };
/* 0x170FC and 0x171D0: each word makes seed = seed * STEP + OFFSET. */
enum { STEP = 1664525, OFFSET = 1013904223, WARM_UP = 8 };
enum { R2, R3, R4, R5, R6, R7, R8, R9, R10, R11 };

static uint32_t load_word(const uint8_t* p) {
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}

static void store_word(uint8_t* p, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(value >> (24 - 8 * i));
}

static void store_quadword(uint8_t* p, const MotorstormRandomQuadword* q) {
    for (unsigned i = 0; i < MOTORSTORM_RANDOM_LANES; ++i) store_word(p + 4 * i, q->word[i]);
}

static MotorstormRandomQuadword splat(uint32_t value) {
    MotorstormRandomQuadword q;
    for (unsigned i = 0; i < MOTORSTORM_RANDOM_LANES; ++i) q.word[i] = value;
    return q;
}

static void step(MotorstormRandomQuadword* seed) {
    for (unsigned i = 0; i < MOTORSTORM_RANDOM_LANES; ++i) seed->word[i] = seed->word[i] * STEP + OFFSET;
}

/* cwx r7, r4, r11: the control bytes that shufb uses to replace one word of a quadword.
   The words keep the pattern for the word at the address in the preferred slot of r4. */
static MotorstormRandomQuadword word_select(uint32_t address) {
    MotorstormRandomQuadword q;
    const unsigned selected = (address >> 2) & 3;
    for (unsigned i = 0; i < MOTORSTORM_RANDOM_LANES; ++i)
        q.word[i] = i == selected ? UINT32_C(0x00010203) : UINT32_C(0x10111213) + i * UINT32_C(0x04040404);
    return q;
}

/* 0x17140 to 0x171BC: 8 warm-up rounds, then 32 numbers into the table. */
static void fill(MotorstormRandomCall* call) {
    MotorstormRandomQuadword* r = call->registers;
    for (unsigned i = 0; i < WARM_UP; ++i) step(&call->seed);
    for (uint32_t address = TABLE; address < TABLE_END; address += 4) {
        step(&call->seed);
        store_word(call->state + (address - STATE), call->seed.word[0]);
    }
    /* 0x17DE0 holds the last quadword of the table with word 3 first (rotqbyi 12). */
    MotorstormRandomQuadword last, rotated;
    for (unsigned i = 0; i < MOTORSTORM_RANDOM_LANES; ++i) last.word[i] = load_word(call->state + (TABLE_END - 16 - STATE) + 4 * i);
    for (unsigned i = 0; i < MOTORSTORM_RANDOM_LANES; ++i) rotated.word[i] = last.word[(i + 3) & 3];
    store_quadword(call->state + (INDEX - STATE), &rotated);
    /* 0x17DD0: 0x01000000 in each word marks the table as filled. */
    store_quadword(call->state, &(MotorstormRandomQuadword){{UINT32_C(0x01000000), UINT32_C(0x01000000),
                                                            UINT32_C(0x01000000), UINT32_C(0x01000000)}});
    r[R8] = word_select(0x17e6c); /* cwd r8, r7, 0 of the last pass */
    r[R9] = splat(UINT32_C(0x3c6ef35f));
    r[R10] = splat(0x17e70);
}

/* 0x171C0 to 0x17234: one number. */
static void draw(MotorstormRandomCall* call) {
    MotorstormRandomQuadword* r = call->registers;
    const uint32_t address = TABLE + (load_word(call->state + INDEX - STATE) & 31u) * 4;
    uint8_t* quadword = call->state + (address & ~15u) - STATE;
    const unsigned position = (address >> 2) & 3;
    for (unsigned i = 0; i < MOTORSTORM_RANDOM_LANES; ++i)
        r[R4].word[i] = (load_word(call->state + (INDEX - STATE) + 4 * i) & 31u) * 4;
    for (unsigned i = 0; i < MOTORSTORM_RANDOM_LANES; ++i) r[R5].word[i] = r[R4].word[i] + TABLE;
    r[R7] = word_select(r[R4].word[0] + TABLE);
    step(&call->seed);
    r[R6] = call->seed;
    MotorstormRandomQuadword table, rotated;
    for (unsigned i = 0; i < MOTORSTORM_RANDOM_LANES; ++i) table.word[i] = load_word(quadword + 4 * i);
    /* rotqby r2, r2, r5: the selected word moves to word 0. */
    for (unsigned i = 0; i < MOTORSTORM_RANDOM_LANES; ++i) rotated.word[i] = table.word[(position + i) & 3];
    store_quadword(call->state + (INDEX - STATE), &rotated);
    for (unsigned i = 0; i < MOTORSTORM_RANDOM_LANES; ++i) r[R3].word[i] = rotated.word[i] & UINT32_C(0x3fffffff);
    /* shufb r2, r6, r2, r7: the table word takes the new seed. */
    table.word[position] = call->seed.word[0];
    store_quadword(quadword, &table);
    r[R2] = table;
    r[R11] = splat(TABLE);
}

int motorstorm_particle_random(uint32_t entry, MotorstormRandomCall* call) {
    MotorstormRandomQuadword* r = call->registers;
    if (entry == MOTORSTORM_RANDOM_ENTRY_INIT) {
        const MotorstormRandomQuadword zero = {{0, 0, 0, 0}};
        store_quadword(call->state, &zero);
        r[R2] = zero;
        call->seed = r[R3];
        return 1;
    }
    if (entry != MOTORSTORM_RANDOM_ENTRY_RUN) return 0;
    /* 0x170D0 to 0x170E4 of the lifted code: the table is filled while byte 0 of 0x17DD0
       is 0. The init entry sets that byte to 0; the fill sets it to 1. */
    if (!call->state[0]) fill(call);
    draw(call);
    return 1;
}

int motorstorm_particle_random_call(uint8_t* ls, uint32_t* gpr, uint32_t entry) {
    MotorstormRandomCall call;
    for (unsigned r = 0; r < MOTORSTORM_RANDOM_REGISTERS; ++r)
        for (unsigned lane = 0; lane < MOTORSTORM_RANDOM_LANES; ++lane)
            call.registers[r].word[lane] = gpr[(r + 2) * MOTORSTORM_RANDOM_LANES + lane];
    for (unsigned lane = 0; lane < MOTORSTORM_RANDOM_LANES; ++lane)
        call.seed.word[lane] = load_word(ls + 0x174a0 + 4 * lane);
    for (unsigned i = 0; i < MOTORSTORM_RANDOM_STATE; ++i) call.state[i] = ls[0x17dd0 + i];
    if (!motorstorm_particle_random(entry, &call)) return 0;
    for (unsigned r = 0; r < MOTORSTORM_RANDOM_REGISTERS; ++r)
        for (unsigned lane = 0; lane < MOTORSTORM_RANDOM_LANES; ++lane)
            gpr[(r + 2) * MOTORSTORM_RANDOM_LANES + lane] = call.registers[r].word[lane];
    for (unsigned lane = 0; lane < MOTORSTORM_RANDOM_LANES; ++lane)
        store_word(ls + 0x174a0 + 4 * lane, call.seed.word[lane]);
    for (unsigned i = 0; i < MOTORSTORM_RANDOM_STATE; ++i) ls[0x17dd0 + i] = call.state[i];
    return 1;
}
