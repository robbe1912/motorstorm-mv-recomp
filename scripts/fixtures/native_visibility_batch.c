#include "visibility_batch.h"
#include "spu_float_simd.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum {
    stats = 0x28930, primary = 0x28950, auxiliary = 0x2c950, secondary = 0x2e950,
    records = 0x30950, matrices = 0x30a00, spheres = 0x30b00, boxes = 0x30c00
};
static uint8_t ls[0x40000], original[sizeof(ls)];

static void require(int condition, const char* description) {
    if (condition) return;
    fprintf(stderr, "FAIL: %s\n", description);
    exit(1);
}

static void write_word(unsigned address, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i)
        ls[address + i] = (uint8_t)(value >> (24 - 8 * i));
}

static uint32_t read_word(const uint8_t* bytes, unsigned address) {
    return (uint32_t)bytes[address] << 24 | (uint32_t)bytes[address + 1] << 16 |
           (uint32_t)bytes[address + 2] << 8 | bytes[address + 3];
}

static void configure(void) {
    memset(ls, 0, sizeof(ls));
    write_word(0x16880, stats);
    write_word(0x16890, secondary);
    write_word(0x168a0, auxiliary);
    write_word(0x168b0, primary);
    write_word(0x16b30, records);
    write_word(0x16b40, boxes);
    write_word(0x16b50, spheres);
    write_word(0x16b60, matrices);
    write_word(0x27000, 100);
    write_word(0x168c0, 1);
    for (unsigned i = 0; i < 4; ++i) {
        write_word(records + i * 20, 0x3f800000);
        write_word(records + i * 20 + 8, 0x10000);
        for (unsigned lane = 0; lane < 4; ++lane)
            write_word(matrices + i * 64 + lane * 20, 0x3f800000);
        write_word(matrices + i * 64 + 40, 0x40000000);
    }
    write_word(records + 12, 1);
    write_word(records + 32, 5);
    write_word(records + 52, 1);
    write_word(records + 48, 0x20000);
}

static void output_order(void) {
    configure();
    require(motorstorm_us_visibility_classify(ls, 4, 0, NULL, NULL), "valid batch accepted");
    require(read_word(ls, records) == 0x40000000 && read_word(ls, records + 20) == 0x40000000 &&
            read_word(ls, records + 40) == 0x40000000 && read_word(ls, records + 60) == 0x3f800000,
            "radius writeback for enabled records");
    require(read_word(ls, stats + 8) == 1 && read_word(ls, stats + 12) == 2 &&
            read_word(ls, stats + 16) == 1, "LOD and output statistics");
    require(read_word(ls, 0x16870) == 1 && read_word(ls, primary) == 100 &&
            read_word(ls, 0x17bd0) == 1 && read_word(ls, auxiliary) == 101 &&
            read_word(ls, 0x16bb0) == 1 && read_word(ls, 0x16bc0) == 101,
            "primary, auxiliary and special identities");
    require(read_word(ls, 0x17bc0) == 2 && read_word(ls, secondary) == 100 &&
            read_word(ls, secondary + 4) == 101 && read_word(ls, 0x17be0) == 0 &&
            read_word(ls, 0x17be4) == 0 && read_word(ls, 0x19be0) == 0,
            "ordered secondary IDs and companion depths");
}

static void reject(unsigned count) {
    memcpy(original, ls, sizeof(ls));
    require(!motorstorm_us_visibility_classify(ls, count, 0, NULL, NULL), "invalid batch rejected");
    require(memcmp(ls, original, sizeof(ls)) == 0, "rejection left local store unchanged");
}

static void publication(const MotorstormVisibilityFlush* flush, void* opaque) {
    unsigned* calls = opaque;
    ++*calls;
    require(flush->local_address == primary && flush->high_address == 7 &&
            flush->low_address == 0x14000 && flush->tag == 2, "flush descriptor");
    require(read_word(flush->payload, 0) == 19 &&
            read_word(flush->payload, 16380) == 100 && read_word(ls, 0x16870) == 4096,
            "full ordered payload before counter reset");
}

int main(void) {
    output_order();
    const uint64_t scope = spu_sf_simd_enter();
    output_order();
    spu_sf_simd_leave(scope);

    configure();
    reject(257);
    write_word(0x16b50, records);
    reject(4);
    configure();
    write_word(0x17bc0, 2047);
    reject(4);
    configure();
    write_word(records + 8, 0x1000c);
    reject(4);
    configure();
    write_word(0x16870, 4095);
    write_word(0x16854, 0x10000);
    write_word(0x167c0, 1);
    write_word(0x167d0, 34);
    write_word(primary, 19);
    reject(4);
    unsigned calls = 0;
    require(motorstorm_us_visibility_classify(ls, 4, 7, publication, &calls), "flush batch accepted");
    require(calls == 1 && read_word(ls, 0x16870) == 0 && read_word(ls, 0x167c0) == 2 &&
            read_word(ls, secondary + 4) == 101, "counter reset and continued classification");
    puts("PASS native visibility batch order, radius, transactional admission and 16 KiB publication");
    return 0;
}
