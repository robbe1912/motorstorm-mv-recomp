/* Authored value oracle: every selector in every destination byte, then mixed
 * random selectors. No guest programs or captured instruction data. */
#include "spu_helpers.h"
#include <stdio.h>
#include <time.h>

static uint32_t seed = 0x143;
static uint32_t random_word(void) {
    seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5;
    return seed;
}

static u128 oracle(u128 a, u128 b, u128 c) {
    u128 out;
    for (unsigned p = 0; p < 16; ++p) {
        unsigned s = c._u8[p ^ 3];
        unsigned v;
        if (s < 128) v = s & 16 ? b._u8[(s & 15) ^ 3] : a._u8[(s & 15) ^ 3];
        else if (s < 192) v = 0;
        else if (s < 224) v = 255;
        else v = 128;
        out._u8[p ^ 3] = (uint8_t)v;
    }
    return out;
}

int main(int argc, char **argv) {
    u128 a, b, c;
    (void)argv;
    for (unsigned i = 0; i < 16; ++i) {
        a._u8[i] = (uint8_t)(i * 7 + 1);
        b._u8[i] = (uint8_t)(i * 11 + 97);
        c._u8[i] = (uint8_t)i;
    }
    unsigned cases = 0;
    for (unsigned p = 0; p < 16; ++p) {
        for (unsigned s = 0; s < 256; ++s) {
            c._u8[p ^ 3] = (uint8_t)s;
            u128 actual = spu_shufb(a, b, c), expected = oracle(a, b, c);
            if (memcmp(&actual, &expected, 16)) return fprintf(stderr, "selector %u byte %u\n", s, p), 1;
            ++cases;
        }
    }
    for (unsigned n = 0; n < 200000; ++n) {
        for (unsigned i = 0; i < 4; ++i) {
            a._u32[i] = random_word(); b._u32[i] = random_word(); c._u32[i] = random_word();
        }
        u128 actual = spu_shufb(a, b, c), expected = oracle(a, b, c);
        if (memcmp(&actual, &expected, 16)) return fprintf(stderr, "random case %u\n", n), 1;
        ++cases;
    }
    printf("%u value cases passed\n", cases);
#ifdef PS3RECOMP_SPU_SHUFFLE_H
    printf("simd=%d\n", spu_shufb_simd_available());
#endif
    if (argc > 1) {
        /* Data-dependent chain; both binaries consume identical generated data.
         * The output checksum makes omitted or differing work observable. */
        u128 controls[256];
        for (unsigned n = 0; n < 256; ++n)
            for (unsigned i = 0; i < 4; ++i) controls[n]._u32[i] = random_word();
        clock_t start = clock();
        for (unsigned n = 0; n < 20000000; ++n) {
            a = spu_shufb(a, b, controls[n & 255]);
            b._u32[n & 3] += a._u32[(n + 1) & 3] + n;
        }
        printf("seconds=%.9f checksum=%08x%08x%08x%08x/%08x%08x%08x%08x\n",
               (double)(clock() - start) / CLOCKS_PER_SEC,
               a._u32[0],a._u32[1],a._u32[2],a._u32[3],
               b._u32[0],b._u32[1],b._u32[2],b._u32[3]);
    }
    return 0;
}
