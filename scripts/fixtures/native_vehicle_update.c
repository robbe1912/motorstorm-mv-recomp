/* Runs the native vehicle update kernel on kernel pair files and compares the result with the
   return state of each pair. A pair file holds the registers and the local store at the entry of
   0x11FE0 (from the lifted code in the replay), the state at its return address, and the bitmap of
   the SPU instructions that executed inside the extent. Format (little-endian words):
   header[10] = { 0x33505556, 1, job, pair, entry pc, return pc, 0x40000, 128, 8192, 0 },
   entry registers (128 x 4 words), return registers (128 x 4 words), entry local store,
   return local store, extent bitmap (8192 bytes).

   The kernel result must equal the return state in all registers and in the whole local store.
   The EXTENT lines list what the extent changes between the entry and the return. */
#include "vehicle_update.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PAIR_MAGIC 0x33505556u
#define WORDS 512
#define BITMAP 8192
#define OBJECT 0x21400u
#define OBJECT_SIZE 7712u
#define LINES (MOTORSTORM_VEHICLE_LS_SIZE / 16)

static uint32_t entry_regs[WORDS], return_regs[WORDS];
static uint8_t entry_ls[MOTORSTORM_VEHICLE_LS_SIZE], return_ls[MOTORSTORM_VEHICLE_LS_SIZE];
static uint8_t entry_copy[MOTORSTORM_VEHICLE_LS_SIZE];
static uint8_t bitmap[BITMAP];
/* Per 16-byte line of the local store and per register word: number of pairs that change it. */
static uint16_t line_pairs[LINES];
static uint16_t reg_pairs[WORDS];
static MotorstormVehicleState state;

static int read_exact(FILE* f, void* p, size_t n) { return fread(p, 1, n, f) == n; }

static const char* base_name(const char* path) {
    const char* slash = strrchr(path, '/'), *backslash = strrchr(path, '\\');
    const char* last = slash && (!backslash || slash > backslash) ? slash : backslash;
    return last ? last + 1 : path;
}

static int check(const char* path) {
    const char* name = base_name(path);
    FILE* f = fopen(path, "rb");
    if (!f) { printf("FAIL open %s\n", path); return 2; }
    uint32_t head[10];
    int bad = !read_exact(f, head, sizeof head) || head[0] != PAIR_MAGIC || head[1] != 1 ||
              head[6] != MOTORSTORM_VEHICLE_LS_SIZE || head[7] != 128 || head[8] != BITMAP ||
              head[4] != MOTORSTORM_VEHICLE_ENTRY || head[5] != MOTORSTORM_VEHICLE_RETURN;
    bad = bad || !read_exact(f, entry_regs, sizeof entry_regs) || !read_exact(f, return_regs, sizeof return_regs) ||
          !read_exact(f, entry_ls, sizeof entry_ls) || !read_exact(f, return_ls, sizeof return_ls) ||
          !read_exact(f, bitmap, sizeof bitmap);
    fclose(f);
    if (bad) { printf("FAIL format %s\n", name); return 2; }

    memcpy(entry_copy, entry_ls, sizeof entry_copy);
    memset(&state, 0, sizeof state);
    memcpy(state.gpr, entry_regs, sizeof state.gpr);
    state.ls = entry_ls;
    const int done = motorstorm_vehicle_update(&state);
    unsigned k_ls = 0, k_ls_first = 0, k_reg = 0;
    for (uint32_t i = 0; i < MOTORSTORM_VEHICLE_LS_SIZE; ++i)
        if (entry_ls[i] != return_ls[i]) {
            if (!k_ls_first) k_ls_first = i;
            ++k_ls;
        }
    for (uint32_t i = 0; i < WORDS; ++i)
        if (((const uint32_t*)state.gpr)[i] != return_regs[i]) ++k_reg;
    const int ok = done && !k_ls && !k_reg;

    unsigned executed = 0, changed = 0, object_changed = 0, reg_changed = 0;
    for (uint32_t i = 0; i < BITMAP; ++i)
        for (unsigned j = 0; j < 8; ++j) executed += (bitmap[i] >> j) & 1u;
    for (uint32_t i = 0; i < MOTORSTORM_VEHICLE_LS_SIZE; ++i) {
        if (entry_copy[i] == return_ls[i]) continue;
        ++changed;
        if (i >= OBJECT && i < OBJECT + OBJECT_SIZE) ++object_changed;
    }
    for (uint32_t i = 0; i < LINES; ++i)
        if (memcmp(entry_copy + 16 * i, return_ls + 16 * i, 16)) {
            if (line_pairs[i] != 65535) ++line_pairs[i];
        }
    for (uint32_t i = 0; i < WORDS; ++i)
        if (entry_regs[i] != return_regs[i]) {
            ++reg_changed;
            if (reg_pairs[i] != 65535) ++reg_pairs[i];
        }
    printf("%s %s blocks=%llu pair: addresses executed %u, local store bytes changed %u (object %u), "
           "register words changed %u\n",
           ok ? "OK" : (done ? "DIFF" : "BAIL"), name, (unsigned long long)state.blocks, executed, changed,
           object_changed, reg_changed);
    if (!ok) {
        printf("   kernel against return: local store bytes %u (first 0x%05X), register words %u\n",
               k_ls, k_ls_first, k_reg);
        if (k_ls_first) {
            printf("   local store at 0x%05X: kernel", k_ls_first);
            for (unsigned j = 0; j < 16; ++j) printf(" %02X", entry_ls[k_ls_first + j]);
            printf(" | return");
            for (unsigned j = 0; j < 16; ++j) printf(" %02X", return_ls[k_ls_first + j]);
            printf("\n");
        }
    }
    return ok ? 0 : 1;
}

static void print_ranges(void) {
    /* Runs of 16-byte lines that change in at least one pair. A gap of fewer than 16 lines
       (256 bytes) joins two runs. */
    uint32_t i = 0;
    while (i < LINES) {
        if (!line_pairs[i]) { ++i; continue; }
        const uint32_t start = i;
        uint32_t end = i, most = 0, j = i;
        while (j < LINES) {
            if (line_pairs[j]) {
                end = j + 1;
                if (line_pairs[j] > most) most = line_pairs[j];
            } else if (j + 1 - end >= 16) {
                break;
            }
            ++j;
        }
        printf("   0x%05X..0x%05X (%u bytes) in at most %u pairs\n", start * 16, end * 16, (end - start) * 16, most);
        i = end;
    }
}

int main(int argc, char** argv) {
    if (argc < 2) { printf("usage: native_vehicle_update <pair file>...\n"); return 2; }
    int failures = 0, count = 0;
    for (int i = 1; i < argc; ++i) {
        const int r = check(argv[i]);
        failures += r != 0;
        count += r != 2;
    }
    printf("EXTENT registers changed in at least one pair (SPU register numbers):");
    for (uint32_t r = 0; r < 128; ++r)
        if (reg_pairs[4 * r] || reg_pairs[4 * r + 1] || reg_pairs[4 * r + 2] || reg_pairs[4 * r + 3]) printf(" r%u", r);
    printf("\n");
    printf("EXTENT local store ranges changed in at least one pair:\n");
    print_ranges();
    printf("PAIRS %d failed %d\n", count, failures);
    return failures ? 1 : 0;
}
