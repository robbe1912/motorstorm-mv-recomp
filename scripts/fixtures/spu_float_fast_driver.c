/* Authored inputs only: no game input, no guest bytes.
 *
 * Fast forms of spu_fa, spu_fs, spu_fm, spu_fma, spu_fms and spu_fnms.
 * References: the exact integer path of the tree (ref), the scoped host form of
 * the earlier path (spu_sf_simd_binary, spu_sf_simd_fused), and the rows that the
 * runner sends to stdin (the exact-rational model in robbe_float_oracle.py).
 * The two macros below count the calls that take the fast form. Each call must
 * take it when and only when the rules in expect_fast hold.
 * Argument "quick" lowers the number of random vectors (used for the mutants). */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <intrin.h>
#include "runtime/spu/spu_float_simd.h"
static uint64_t s_hit[6];
#define spu_sf_fast_binary(out, a, b, op) (__extension__({ int hit_ = spu_sf_fast_binary(out, a, b, op); \
    s_hit[op] += (uint64_t)hit_; hit_; }))
#define spu_sf_fast_fused(out, a, b, c, np, nc) (__extension__({ int hit_ = spu_sf_fast_fused(out, a, b, c, np, nc); \
    s_hit[3 + ((np) ? 2 : (nc) ? 1 : 0)] += (uint64_t)hit_; hit_; }))
#include "runtime/spu/spu_helpers.h"

#define GROUPS_MAX 16
#define RANDOM_FULL 1048576u   /* vectors per helper: above one million */
#define RANDOM_QUICK 16384u
static uint64_t s_calls[GROUPS_MAX][6], s_fast[GROUPS_MAX][6], s_value[GROUPS_MAX][6];
static uint64_t s_badhit[GROUPS_MAX][6], s_host[GROUPS_MAX][6], s_rows[6];
static const char *s_gname[GROUPS_MAX];
static int s_ngroups, s_fail_lines, s_failed;
static const char *const NAMES[6] = {"fa", "fs", "fm", "fma", "fms", "fnms"};

static uint64_t s_state = 0x9e3779b97f4a7c15ull;
static uint32_t rnd(void) { s_state ^= s_state << 13; s_state ^= s_state >> 7; s_state ^= s_state << 17; return (uint32_t)(s_state >> 32); }

static u128 call(int h, u128 a, u128 b, u128 c) {
    switch (h) {
    case 0: return spu_fa(a, b);
    case 1: return spu_fs(a, b);
    case 2: return spu_fm(a, b);
    case 3: return spu_fma(a, b, c);
    case 4: return spu_fms(a, b, c);
    default: return spu_fnms(a, b, c);
    }
}

/* The exact path of the tree: the _ref forms of the fork, the integer helpers
 * that the vendor helpers call. */
static u128 ref(int h, u128 a, u128 b, u128 c) {
#ifdef SPU_FLOAT_FAST_TREE_FORK
    switch (h) {
    case 0: return spu_fa_ref(a, b);
    case 1: return spu_fs_ref(a, b);
    case 2: return spu_fm_ref(a, b);
    case 3: return spu_fma_ref(a, b, c);
    case 4: return spu_fms_ref(a, b, c);
    default: return spu_fnms_ref(a, b, c);
    }
#else
    u128 r;
    for (int k = 0; k < 4; k++) {
        const uint32_t x = a._u32[k], y = b._u32[k], z = c._u32[k];
        switch (h) {
        case 0: r._u32[k] = spu_sf_add(x, y); break;
        case 1: r._u32[k] = spu_sf_add(x, y ^ 0x80000000u); break;
        case 2: r._u32[k] = spu_sf_mul(x, y); break;
        case 3: r._u32[k] = spu_sf_madd(x, y, z, 0); break;
        case 4: r._u32[k] = spu_sf_madd(x, y, z ^ 0x80000000u, 0); break;
        default: r._u32[k] = spu_sf_madd(x, y, z, 0x80000000u); break;
        }
    }
    return r;
#endif
}

/* The scoped host form of the earlier path. Returns 1 with the result when it
 * applies. */
static int host(int h, u128 a, u128 b, u128 c, u128 *r) {
    if (h < 3) return spu_sf_simd_binary(r->_u32, a._u32, b._u32, h);
    return spu_sf_simd_fused(r->_u32, a._u32, b._u32, c._u32, h == 5 ? 0x80000000u : 0u, h == 4 ? 0x80000000u : 0u);
}

/* The rules of the fast form, written here a second time: a scope is active;
 * the host mode is the mode of a scope; the fused family has the FMA3 admission
 * (scope value 2); no input lane has exponent field 255; no result lane reaches
 * 2^127. */
static int expect_fast(int h, int scope, int mode_ok, u128 a, u128 b, u128 c, u128 want) {
    const uint32_t m = 0x7f800000u;
    if (!SPU_SF_FAST || !scope || !mode_ok) return 0;
    if (h >= 3 && scope != 2) return 0;
    for (int k = 0; k < 4; k++) {
        /* fa, fs and fm do not read the third operand. */
        if ((a._u32[k] & m) == m || (b._u32[k] & m) == m || (h >= 3 && (c._u32[k] & m) == m)) return 0;
        if ((want._u32[k] & 0x7fffffffu) >= 0x7f000000u) return 0;
    }
    return 1;
}

static int lanes_differ(u128 x, u128 y) { int n = 0; for (int k = 0; k < 4; k++) n += x._u32[k] != y._u32[k]; return n; }

static void fail_line(const char *what, const char *group, int h, u128 a, u128 b, u128 c, u128 got, u128 want) {
    if (s_fail_lines++ < 40)
        printf("FAIL %s %s a=%08x,%08x,%08x,%08x b=%08x,%08x,%08x,%08x c=%08x,%08x,%08x,%08x got=%08x,%08x,%08x,%08x want=%08x,%08x,%08x,%08x\n",
               what, group, a._u32[0], a._u32[1], a._u32[2], a._u32[3], b._u32[0], b._u32[1], b._u32[2], b._u32[3],
               c._u32[0], c._u32[1], c._u32[2], c._u32[3], got._u32[0], got._u32[1], got._u32[2], got._u32[3],
               want._u32[0], want._u32[1], want._u32[2], want._u32[3]);
}

/* One call of helper h. mode_ok: the host mode is the mode of a scope. */
static u128 one(int g, int h, u128 a, u128 b, u128 c, int mode_ok, int *hit_out) {
    const int scope = g_spu_sf_simd_scope;
    const uint64_t hit_before = s_hit[h];
    u128 hr;
    const u128 want = ref(h, a, b, c);
    const u128 got = call(h, a, b, c);
    const int hit = (int)(s_hit[h] - hit_before);
    const int value = lanes_differ(got, want);
    const int badhit = hit != expect_fast(h, scope, mode_ok, a, b, c, want);
    const int hostbad = host(h, a, b, c, &hr) ? lanes_differ(got, hr) : 0;
    s_calls[g][h]++; s_fast[g][h] += (unsigned)hit;
    s_value[g][h] += (unsigned)value; s_badhit[g][h] += (unsigned)badhit; s_host[g][h] += (unsigned)hostbad;
    if (value) fail_line("value", s_gname[g], h, a, b, c, got, want);
    if (badhit) fail_line("hit", s_gname[g], h, a, b, c, got, want);
    if (hostbad) fail_line("host", s_gname[g], h, a, b, c, got, hr);
    s_failed += value != 0; s_failed += badhit != 0; s_failed += hostbad != 0;
    if (hit_out) *hit_out = hit;
    return got;
}

static int group(const char *name) { s_gname[s_ngroups] = name; return s_ngroups++; }

static u128 splat(uint32_t x) { u128 v; for (int k = 0; k < 4; k++) v._u32[k] = x; return v; }

/* Special lane values: both zeros, denormals, the smallest normals, values that
 * need truncation, the largest finite values, exponent field 255 (finite on the
 * SPU, NaN and infinity patterns on the host). */
static const uint32_t W[] = {
    0x00000000u, 0x80000000u, 0x00000001u, 0x80000001u, 0x007fffffu, 0x807fffffu, 0x00800000u, 0x80800000u,
    0x00400000u, 0x00c00000u, 0x00800001u, 0x3eaaaaabu, 0xbf000000u, 0x3f000000u, 0x3f7fffffu, 0x3f800000u,
    0xbf800000u, 0x3f800001u, 0xbf800001u, 0x33800000u, 0x33800001u, 0x4b000000u, 0x4b800000u, 0x4effffffu,
    0x4f000000u, 0x4f000001u, 0x5f000000u, 0x7e7fffffu, 0x7e800000u, 0x7effffffu, 0xfeffffffu, 0x7f000000u,
    0xff000000u, 0x7f000001u, 0x7f400000u, 0x7f7fffffu, 0xff7fffffu, 0x7f800000u, 0xff800000u, 0x7f800001u,
    0xff800001u, 0x7fa00000u, 0x7fbfffffu, 0x7fc00000u, 0xffc00000u, 0x7fffffffu, 0xffffffffu,
};
#define NW ((int)(sizeof(W) / sizeof(W[0])))

static uint32_t filler(int operand, int lane, int i, int j) {
    static const uint32_t base[3] = {0x3f000000u, 0x3f800000u, 0x40000000u};
    return (base[operand] ^ ((uint32_t)(lane & 1) << 31))
         | (uint32_t)((lane * 0x2001 + i * 7919 + j * 104729 + operand * 31) & 0x7fffff);
}

static u128 vec(uint32_t x, int lane, int operand, int i, int j) {
    u128 v;
    for (int k = 0; k < 4; k++) v._u32[k] = k == lane ? x : filler(operand, k, i, j);
    return v;
}

/* Every pair of special values in each lane position, the other lanes normal.
 * For the fused family the third operand is special too, in each position. */
static void matrix(int g, int mode_ok) {
    for (int h = 0; h < 6; h++)
        for (int lane = 0; lane < 4; lane++)
            for (int i = 0; i < NW; i++)
                for (int j = 0; j < NW; j++) {
                    int hit;
                    const uint32_t x = W[i], y = W[j], z = W[(i * 5 + j * 3) % NW];
                    if (h < 3) { one(g, h, vec(x, lane, 0, i, j), vec(y, lane, 1, i, j), vec(0, lane, 2, i, j), mode_ok, &hit); continue; }
                    one(g, h, vec(x, lane, 0, i, j), vec(y, lane, 1, i, j), vec(z, lane, 2, i, j), mode_ok, &hit);
                    one(g, h, vec(x, lane, 0, i, j), vec(y, lane, 2, i, j), vec(z, lane, 1, i, j), mode_ok, &hit);
                    one(g, h, vec(z, lane, 2, i, j), vec(x, lane, 0, i, j), vec(y, lane, 1, i, j), mode_ok, &hit);
                }
}

/* Vectors that need one rounding, that give a signed zero on the host, that
 * flush, that saturate, and that truncate. All sign combinations, in all lanes
 * and in one lane. */
static void explicit_vectors(int g) {
    static const uint32_t E[][3] = {
        {0x3f800001u, 0x3fc00000u, 0xbfc00000u},  /* (1+2^-23)*1.5 - 1.5: one rounding gives 2^-23+2^-24 */
        {0x3f800001u, 0x3fc00000u, 0xbfc00001u},  /* product less its truncation: 2^-24; two roundings give +0 */
        {0x3f800001u, 0x40400000u, 0xc0400001u},
        {0x80000000u, 0x00000000u, 0x80000000u},  /* signed zeros */
        {0xc0000000u, 0x00000000u, 0x80000000u},  /* -3 times +0 */
        {0x3f800000u, 0x80000000u, 0xbf800000u},
        {0x3f800000u, 0xbf800000u, 0x3f800000u},  /* x + (-x) */
        {0x00000001u, 0x80000001u, 0x3f800000u},  /* denormals */
        {0x00000001u, 0x4b800000u, 0x00000000u},  /* denormal times 2^24 */
        {0x00800000u, 0x3f000000u, 0x00000000u},  /* 2^-127: flush */
        {0x00ffffffu, 0x3f000000u, 0x00000000u},
        {0x00800001u, 0x3fffffffu, 0x00000000u},  /* below 2^-126 after truncation */
        {0x7effffffu, 0x40000000u, 0x00000000u},  /* 2^127 and above */
        {0x7f000000u, 0x3f000000u, 0x00000000u},  /* exponent field 255 as input */
        {0x7effffffu, 0x3f800001u, 0x00000000u},
        {0x3f800000u, 0x33800001u, 0x00000000u},  /* the sum needs truncation */
        {0x3f800001u, 0x33800000u, 0x00000000u},
        {0x4b7fffffu, 0x3f800001u, 0x00000000u},
    };
    int hit;
    for (unsigned e = 0; e < sizeof(E) / sizeof(E[0]); e++)
        for (unsigned mask = 0; mask < 8; mask++) {
            const uint32_t x = E[e][0] ^ ((mask & 1u) << 31), y = E[e][1] ^ (((mask >> 1) & 1u) << 31), z = E[e][2] ^ (((mask >> 2) & 1u) << 31);
            for (int h = 0; h < 6; h++) {
                one(g, h, splat(x), splat(y), splat(z), 1, &hit);
                for (int lane = 0; lane < 4; lane++) one(g, h, vec(x, lane, 0, e, mask), vec(y, lane, 1, e, mask), vec(z, lane, 2, e, mask), 1, &hit);
            }
        }
}

static uint32_t gen_word(int kind, int salt, uint32_t n) {
    const uint32_t r = rnd() ^ (n * 0x9e3779b9u + (uint32_t)salt * 0x85ebca6bu);
    uint32_t exponent;
    switch (kind) {
    case 0: return (r & 0x807fffffu) | ((r & 0x1000u) ? 0x7f800000u : ((r >> 23) % 255u) << 23);   /* half with field 255 */
    case 1: exponent = (r >> 23) % 255u; break;         /* denormal to the largest finite value */
    case 2: exponent = 110u + (r >> 24) % 33u; break;   /* 2^-17 to 2^15 */
    default: exponent = 118u + (r >> 24) % 20u; break;  /* 2^-9 to 2^10 */
    }
    return (r & 0x807fffffu) | (exponent << 23);
}

/* count vectors for each helper. Every fourth vector has arbitrary lanes, so
 * that both paths run. Each sixteenth vector repeats the fused family with a
 * third operand near the negative product. */
static void random_group(int g, uint32_t count) {
    int hit;
    for (uint32_t n = 0; n < count; n++) {
        const int kind = n & 3;
        u128 a, b, c;
        for (int k = 0; k < 4; k++) {
            a._u32[k] = gen_word(kind, k, n); b._u32[k] = gen_word(kind, k + 1, n); c._u32[k] = gen_word(kind, k + 2, n);
        }
        for (int h = 0; h < 6; h++) one(g, h, a, b, c, 1, &hit);
        if ((n & 15) == 0) {
            u128 f;
            const __m128 product = _mm_mul_ps(_mm_loadu_ps((const float *)a._u32), _mm_loadu_ps((const float *)b._u32));
            _mm_storeu_si128((__m128i *)f._u32, _mm_xor_si128(_mm_castps_si128(product), _mm_set1_epi32((int)0x80000000u)));
            for (int h = 3; h < 6; h++) one(g, h, a, b, f, 1, &hit);
        }
    }
}

/* Rows from the runner: op, then the three vectors. Prints the result of the
 * helper for the exact-rational model of the runner. */
static void model_rows(int g) {
    unsigned op;
    while (scanf("%u", &op) == 1) {
        uint32_t words[12];
        u128 a, b, c;
        for (int i = 0; i < 12; i++) if (scanf("%x", &words[i]) != 1) { printf("FAIL model input\n"); s_failed++; return; }
        if (op > 5) { printf("FAIL model op %u\n", op); s_failed++; continue; }
        memcpy(a._u32, words, 16); memcpy(b._u32, words + 4, 16); memcpy(c._u32, words + 8, 16);
        int hit = 0;
        const u128 got = one(g, (int)op, a, b, c, 1, &hit);
        s_rows[op]++;
        printf("%08x %08x %08x %08x\n", got._u32[0], got._u32[1], got._u32[2], got._u32[3]);
    }
}

static void check(int condition, const char *what) {
    if (!condition) { printf("FAIL %s\n", what); s_failed++; }
}

int main(int argc, char **argv) {
    const int quick = argc > 1 && !strcmp(argv[1], "quick");
    const uint32_t caller = _mm_getcsr();
    const uint32_t spu_mode = 0x1f80u | 0x8040u | 0x6000u;   /* masks, FTZ, DAZ, toward zero */
    static const uint32_t changed[] = {0x1f80u | 0x8040u, 0x1f80u | 0x8040u | 0x2000u, 0x1f80u | 0x8040u | 0x4000u,
                                       0x1f80u | 0x8000u | 0x6000u, 0x1f80u | 0x0040u | 0x6000u, 0x1f80u};
    static const char *const changed_name[] = {"mode-nearest-ftz-daz", "mode-down-ftz-daz", "mode-up-ftz-daz",
                                               "mode-rtz-ftz-no-daz", "mode-rtz-no-ftz", "mode-nearest-no-ftz"};
    unsigned i;
    int hit, g;
    uint64_t saved, total = 0, fast = 0;
    printf("FF gates fast=%d x86=%d\n", (int)SPU_SF_FAST, (int)SPU_SF_X86_SIMD);
    saved = spu_sf_simd_enter();
    printf("FF scope=%d\n", g_spu_sf_simd_scope);
    g = group("scope-held");
    {   /* Information for the report: the flags that one exact fast call raises. */
        const uint32_t before = _mm_getcsr();
        one(g, 0, splat(0x3f800000u), splat(0x40000000u), splat(0), 1, &hit);
        printf("FF flags exact-add new=%02x\n", (_mm_getcsr() ^ before) & 0x3fu);
    }
    matrix(g, 1); explicit_vectors(g);
    g = group("scope-held-random"); random_group(g, quick ? RANDOM_QUICK : RANDOM_FULL);
    {
        const uint64_t inner = spu_sf_simd_enter();
        g = group("scope-nested"); matrix(g, 1);
        spu_sf_simd_leave(inner);
    }
    const uint32_t held = _mm_getcsr() & ~0x3fu;
    for (i = 0; i < 6; i++) {
        _mm_setcsr(changed[i]);
        g = group(changed_name[i]); matrix(g, 0);
    }
    _mm_setcsr(held);
    {   /* Scope value 1: the host has no FMA3. */
        const int capability = g_spu_sf_simd_scope;
        g_spu_sf_simd_scope = 1;
        g = group("scope-without-fma"); matrix(g, 1); explicit_vectors(g);
        g_spu_sf_simd_scope = capability;
    }
    spu_sf_simd_leave(saved);
    check(_mm_getcsr() == caller, "leave restores the MXCSR of the caller");
    _mm_setcsr(spu_mode);
    g = group("outside-scope-spu-mode"); matrix(g, 1); explicit_vectors(g);
    _mm_setcsr(0x1f80u);
    g = group("outside-scope-nearest"); matrix(g, 0);
    _mm_setcsr(caller);
    saved = spu_sf_simd_enter();
    g = group("model"); model_rows(g);
    spu_sf_simd_leave(saved);
    check(_mm_getcsr() == caller, "leave restores the MXCSR of the caller after the model rows");
    for (g = 0; g < s_ngroups; g++)
        for (int h = 0; h < 6; h++) {
            printf("group %s op %s calls=%llu fast=%llu value=%llu hit=%llu host=%llu\n", s_gname[g], NAMES[h],
                   (unsigned long long)s_calls[g][h], (unsigned long long)s_fast[g][h], (unsigned long long)s_value[g][h],
                   (unsigned long long)s_badhit[g][h], (unsigned long long)s_host[g][h]);
            total += s_calls[g][h]; fast += s_fast[g][h];
        }
    for (int op = 0; op < 6; op++) printf("model %s rows=%llu fast=%llu\n", NAMES[op], (unsigned long long)s_rows[op],
                                          (unsigned long long)s_fast[s_ngroups - 1][op]);
    printf("RESULT %s cases=%llu fast=%llu\n", s_failed ? "FAIL" : "PASS", (unsigned long long)total, (unsigned long long)fast);
    return s_failed ? 1 : 0;
}
