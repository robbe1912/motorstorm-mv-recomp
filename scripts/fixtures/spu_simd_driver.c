/* Value oracle of the x86 SIMD forms of the hot SPU helpers.
 *
 * One source file, two units.
 *  - The reference unit (SPU_SIMD_REF) includes the SPU headers with the
 *    scalar bodies selected.
 *  - The driver unit includes them as a unit of the game does.
 * Both units get the same inputs. The reference is the scalar body of each
 * helper: spu_X_ref in the fork tree, the body under SPU_SIMD=0 in the vendor
 * tree. For each helper with a small definition the driver unit also holds an
 * independent model.
 * Authored inputs only: no guest programs and no captured instruction data.
 * scripts/check_spu_simd.py builds and runs this file. */
#include "spu_helpers.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#ifdef SPU_SIMD_REF
/* ---- reference unit: the scalar bodies ---- */
u128 spu_simd_ref_rotqby(u128 a, u128 b)   { return spu_rotqby(a, b); }
u128 spu_simd_ref_rotqbyi(u128 a, int sh)  { return spu_rotqbyi(a, sh); }
u128 spu_simd_ref_rotqbybi(u128 a, u128 b) { return spu_rotqbybi(a, b); }
u128 spu_simd_ref_shlqby(u128 a, u128 b)   { return spu_shlqby(a, b); }
u128 spu_simd_ref_shlqbybi(u128 a, u128 b) { return spu_shlqbybi(a, b); }
u128 spu_simd_ref_cbd(u128 a, int i7)      { return spu_cbd(a, i7); }
u128 spu_simd_ref_cdd(u128 a, int i7)      { return spu_cdd(a, i7); }
u128 spu_simd_ref_cbx(u128 a, u128 b)      { return spu_cbx(a, b); }
u128 spu_simd_ref_cwd(u128 a, int i7)      { return spu_cwd(a, i7); }
u128 spu_simd_ref_cwx(u128 a, u128 b)      { return spu_cwx(a, b); }
u128 spu_simd_ref_fm(u128 a, u128 b)       { return spu_fm(a, b); }
u128 spu_simd_ref_shufb(u128 a, u128 b, u128 c) { return spu_shufb(a, b, c); }
u128 spu_simd_ref_ls_read128(const spu_context* ctx, uint32_t lsa) { return spu_ls_read128(ctx, lsa); }
void spu_simd_ref_ls_write128(spu_context* ctx, uint32_t lsa, u128 v) { spu_ls_write128(ctx, lsa, v); }

/* Stubs for the externs of spu_context.h that this test does not use. */
int g_spu_ls_watch_n = -1;
void spu_ls_watch_slow(uint32_t lsa, int is_write, const uint8_t* p, uint32_t pc, uint32_t lr) {
    (void)lsa; (void)is_write; (void)p; (void)pc; (void)lr;
}
/* The vendor tree has the game-only lines of the local store accessors. */
#ifndef SPU_SIMD_TREE_FORK
uint8_t* vm_base;
uint32_t ppu_vm_size;
void spu_pm_fill_note(spu_context* ctx, uint32_t lsa, const void* bytes16, const char* src) {
    (void)ctx; (void)lsa; (void)bytes16; (void)src;
}
void spu_lockline_lock(void) {}
void spu_lockline_unlock(void) {}
void spu_coh_notify_write(uint32_t ea) { (void)ea; }
#endif

#else
/* ---- driver unit: the forms under test ---- */
extern u128 spu_simd_ref_rotqby(u128 a, u128 b);
extern u128 spu_simd_ref_rotqbyi(u128 a, int sh);
extern u128 spu_simd_ref_rotqbybi(u128 a, u128 b);
extern u128 spu_simd_ref_shlqby(u128 a, u128 b);
extern u128 spu_simd_ref_shlqbybi(u128 a, u128 b);
extern u128 spu_simd_ref_cbd(u128 a, int i7);
extern u128 spu_simd_ref_cdd(u128 a, int i7);
extern u128 spu_simd_ref_cbx(u128 a, u128 b);
extern u128 spu_simd_ref_cwd(u128 a, int i7);
extern u128 spu_simd_ref_cwx(u128 a, u128 b);
extern u128 spu_simd_ref_fm(u128 a, u128 b);
extern u128 spu_simd_ref_shufb(u128 a, u128 b, u128 c);
extern u128 spu_simd_ref_ls_read128(const spu_context* ctx, uint32_t lsa);
extern void spu_simd_ref_ls_write128(spu_context* ctx, uint32_t lsa, u128 v);

enum { R_ROTQBY, R_ROTQBYI, R_ROTQBYBI, R_SHLQBY, R_SHLQBYBI, R_CBD, R_CDD, R_CBX,
       R_CWD, R_CWX, R_FM, R_SHUFB, R_LS_READ, R_LS_WRITE, R_COUNT };
static const char* const names[R_COUNT] = {
    "rotqby", "rotqbyi", "rotqbybi", "shlqby", "shlqbybi", "cbd", "cdd", "cbx",
    "cwd", "cwx", "fm", "shufb", "ls_read128", "ls_write128" };
static long cases[R_COUNT], ref_bad[R_COUNT], model_bad[R_COUNT];

static uint32_t rng;
static uint32_t rnd(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return rng; }
static u128 rnd128(void) { u128 a; for (int i = 0; i < 4; i++) a._u32[i] = rnd(); return a; }
static void set128(u128* a, uint32_t w0, uint32_t w1, uint32_t w2, uint32_t w3) {
    a->_u32[0] = w0; a->_u32[1] = w1; a->_u32[2] = w2; a->_u32[3] = w3;
}

static long shown;
static void mismatch(int op, const char* side, u128 got, u128 want, const uint32_t* in, int n) {
    if (side[0] == 'r') ref_bad[op]++; else model_bad[op]++;
    if (shown++ < 8) {
        printf("mismatch %s vs %s: got %08x%08x%08x%08x want %08x%08x%08x%08x in", names[op], side,
               got._u32[0], got._u32[1], got._u32[2], got._u32[3],
               want._u32[0], want._u32[1], want._u32[2], want._u32[3]);
        for (int i = 0; i < n; i++) printf(" %08x", in[i]);
        printf("\n");
    }
}
static void compare(int op, const char* side, u128 got, u128 want, const uint32_t* in, int n) {
    if (memcmp(&got, &want, 16)) mismatch(op, side, got, want, in, n);
}

/* Independent models from the SPU ISA definitions. SPU byte P is host byte P ^ 3. */
static u128 model_rotqby(u128 a, unsigned sh) {
    u128 r; for (int i = 0; i < 16; i++) r._u8[i ^ 3] = a._u8[((i + sh) & 15) ^ 3]; return r;
}
static u128 model_shlqby(u128 a, unsigned sh) {
    u128 r; for (int i = 0; i < 16; i++) r._u8[i ^ 3] = (sh < 16 && i + sh < 16) ? a._u8[(i + sh) ^ 3] : 0; return r;
}
/* cwd: 0x10 + t at SPU byte t, then 0..3 at the word-aligned position of the sum. */
static u128 model_cwd(u128 a, uint32_t add) {
    u128 r; uint32_t p = (a._u32[0] + add) & 15u; p &= ~3u;
    for (int t = 0; t < 16; t++) r._u8[t ^ 3] = (uint8_t)(0x10 + t);
    for (uint32_t k = 0; k < 4; k++) r._u8[(p + k) ^ 3] = (uint8_t)k;
    return r;
}
static u128 model_shufb(u128 a, u128 b, u128 c) {
    u128 out;
    for (int p = 0; p < 16; ++p) {
        unsigned s = c._u8[p ^ 3], v;
        if (s < 128) v = s & 16 ? b._u8[(s & 15) ^ 3] : a._u8[(s & 15) ^ 3];
        else if (s < 192) v = 0;
        else if (s < 224) v = 255;
        else v = 128;
        out._u8[p ^ 3] = (uint8_t)v;
    }
    return out;
}

#define IN_A(a) a._u32[0], a._u32[1], a._u32[2], a._u32[3]
#define IN_B(b) b._u32[0], b._u32[1], b._u32[2], b._u32[3]
static void ck_rotqby(u128 a, u128 b) {
    const uint32_t in[8] = {IN_A(a), IN_B(b)}; u128 got = spu_rotqby(a, b); cases[R_ROTQBY]++;
    compare(R_ROTQBY, "ref", got, spu_simd_ref_rotqby(a, b), in, 8);
    compare(R_ROTQBY, "model", got, model_rotqby(a, b._u32[0] & 15), in, 8);
}
static void ck_rotqbyi(u128 a, int sh) {
    const uint32_t in[5] = {IN_A(a), (uint32_t)sh}; u128 got = spu_rotqbyi(a, sh); cases[R_ROTQBYI]++;
    compare(R_ROTQBYI, "ref", got, spu_simd_ref_rotqbyi(a, sh), in, 5);
    compare(R_ROTQBYI, "model", got, model_rotqby(a, (unsigned)sh & 15), in, 5);
}
static void ck_rotqbybi(u128 a, u128 b) {
    const uint32_t in[8] = {IN_A(a), IN_B(b)}; u128 got = spu_rotqbybi(a, b); cases[R_ROTQBYBI]++;
    compare(R_ROTQBYBI, "ref", got, spu_simd_ref_rotqbybi(a, b), in, 8);
    compare(R_ROTQBYBI, "model", got, model_rotqby(a, (b._u32[0] >> 3) & 15), in, 8);
}
static void ck_shlqby(u128 a, u128 b) {
    const uint32_t in[8] = {IN_A(a), IN_B(b)}; u128 got = spu_shlqby(a, b); cases[R_SHLQBY]++;
    compare(R_SHLQBY, "ref", got, spu_simd_ref_shlqby(a, b), in, 8);
    compare(R_SHLQBY, "model", got, model_shlqby(a, b._u32[0] & 31), in, 8);
}
static void ck_shlqbybi(u128 a, u128 b) {
    const uint32_t in[8] = {IN_A(a), IN_B(b)}; u128 got = spu_shlqbybi(a, b); cases[R_SHLQBYBI]++;
    compare(R_SHLQBYBI, "ref", got, spu_simd_ref_shlqbybi(a, b), in, 8);
    compare(R_SHLQBYBI, "model", got, model_shlqby(a, (b._u32[0] >> 3) & 31), in, 8);
}
static void ck_cbd(u128 a, int i7) {
    const uint32_t in[5] = {IN_A(a), (uint32_t)i7};
    compare(R_CBD, "ref", spu_cbd(a, i7), spu_simd_ref_cbd(a, i7), in, 5); cases[R_CBD]++;
}
static void ck_cdd(u128 a, int i7) {
    const uint32_t in[5] = {IN_A(a), (uint32_t)i7};
    compare(R_CDD, "ref", spu_cdd(a, i7), spu_simd_ref_cdd(a, i7), in, 5); cases[R_CDD]++;
}
static void ck_cbx(u128 a, u128 b) {
    const uint32_t in[8] = {IN_A(a), IN_B(b)};
    compare(R_CBX, "ref", spu_cbx(a, b), spu_simd_ref_cbx(a, b), in, 8); cases[R_CBX]++;
}
static void ck_cwd(u128 a, int i7) {
    const uint32_t in[5] = {IN_A(a), (uint32_t)i7}; u128 got = spu_cwd(a, i7); cases[R_CWD]++;
    compare(R_CWD, "ref", got, spu_simd_ref_cwd(a, i7), in, 5);
    compare(R_CWD, "model", got, model_cwd(a, (uint32_t)i7), in, 5);
}
static void ck_cwx(u128 a, u128 b) {
    const uint32_t in[8] = {IN_A(a), IN_B(b)}; u128 got = spu_cwx(a, b); cases[R_CWX]++;
    compare(R_CWX, "ref", got, spu_simd_ref_cwx(a, b), in, 8);
    compare(R_CWX, "model", got, model_cwd(a, b._u32[0]), in, 8);
}
static void ck_fm(u128 a, u128 b) {
    const uint32_t in[8] = {IN_A(a), IN_B(b)};
    compare(R_FM, "ref", spu_fm(a, b), spu_simd_ref_fm(a, b), in, 8); cases[R_FM]++;
}
static void ck_shufb(u128 a, u128 b, u128 c) {
    const uint32_t in[12] = {IN_A(a), IN_B(b), IN_B(c)}; u128 got = spu_shufb(a, b, c); cases[R_SHUFB]++;
    compare(R_SHUFB, "ref", got, spu_simd_ref_shufb(a, b, c), in, 12);
    compare(R_SHUFB, "model", got, model_shufb(a, b, c), in, 12);
}
static void ck_ls_read128(const spu_context* ctx, uint32_t lsa) {
    const uint32_t in[1] = {lsa}; u128 got = spu_ls_read128(ctx, lsa); cases[R_LS_READ]++;
    compare(R_LS_READ, "ref", got, spu_simd_ref_ls_read128(ctx, lsa), in, 1);
}
/* A write goes to the context under test and to a second context through the scalar
 * accessor. The compare covers the quadword before and after the addressed one. */
static spu_context model_ctx;
static void ck_ls_write128(spu_context* ctx, uint32_t lsa) {
    const uint32_t in[1] = {lsa}; u128 v = rnd128(); cases[R_LS_WRITE]++;
    spu_ls_write128(ctx, lsa, v); spu_simd_ref_ls_write128(&model_ctx, lsa, v);
    uint32_t lo = (lsa & ~(uint32_t)31) & (SPU_LS_SIZE - 48);
    for (int k = 0; k < 3; k++) {
        u128 got, want; memcpy(&got, ctx->ls_store + lo + 16 * k, 16); memcpy(&want, model_ctx.ls_store + lo + 16 * k, 16);
        compare(R_LS_WRITE, "ref", got, want, in, 1);
    }
}

/* Pattern k of a fixed set: bytes, words and single bits (165 patterns). */
static u128 pattern(int k) {
    u128 a; set128(&a, 0, 0, 0, 0);
    if (k < 16) { for (int i = 0; i < 16; i++) a._u8[i] = (uint8_t)(k & 1 ? 255 - i : i); }
    else if (k == 16) set128(&a, 0, 0, 0, 0);
    else if (k == 17) set128(&a, 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu, 0xFFFFFFFFu);
    else if (k == 18) set128(&a, 0x55555555u, 0x55555555u, 0x55555555u, 0x55555555u);
    else if (k == 19) set128(&a, 0xAAAAAAAAu, 0xAAAAAAAAu, 0xAAAAAAAAu, 0xAAAAAAAAu);
    else if (k < 36) { a._u8[k - 20] = 0x80; }                       /* one byte set */
    else if (k < 164) { a._u8[(k - 36) >> 3] = (uint8_t)(1u << ((k - 36) & 7)); }  /* one bit set */
    else set128(&a, 0x01234567u, 0x89ABCDEFu, 0xFEDCBA98u, 0x76543210u);
    return a;
}

int main(void) {
    static spu_context ctx;
    long n;
#if defined(SPU_SIMD_X86)
    const int g_int = SPU_SIMD_X86, g_ssse3 = SPU_SIMD_SSSE3;
#else
    const int g_int = SPU_X86_SIMD, g_ssse3 = SPU_X86_SIMD_SSSE3;
#endif
    printf("gates int=%d ssse3=%d ls=%d shufb=%d\n", g_int, g_ssse3, SPU_LS_SSSE3, SPU_SHUFB_UNIT_SSSE3);

    /* rotqbyi: every count in a window round zero (each low bit pattern with carries and
     * borrows), the extreme counts, then random operands. */
    rng = 0x10001u;
    for (int sh = -2048; sh < 2048; sh++)
        for (int k = 0; k < 256; k++) ck_rotqbyi(rnd128(), sh);
    { static const int edge[12] = {0, 1, 15, 16, -1, -15, -16, -17, 0x7FFFFFFF, 0x80000000, 0x7FFFFFF0, (int)0x80000001u};
      for (int e = 0; e < 12; e++) for (int k = 0; k < 165; k++) ck_rotqbyi(pattern(k), edge[e]); }

    /* rotqby: word 0 of b through the low 16 bits with random operands, then random pairs. */
    rng = 0x20002u;
    for (uint32_t b0 = 0; b0 < 0x10000; b0++) {
        u128 a = pattern((int)(b0 % 36)), b = rnd128(); b._u32[0] = b0; ck_rotqby(a, b);
    }
    for (n = 0; n < 1000000; n++) ck_rotqby(rnd128(), rnd128());
    for (int k = 0; k < 165; k++) for (uint32_t b0 = 0; b0 < 16; b0++) {
        u128 b = rnd128(); b._u32[0] = b0 * 0x11111111u; ck_rotqby(pattern(k), b); }

    /* rotqbybi, shlqby and shlqbybi keep their scalar bodies: a regression of the neighbors. */
    rng = 0x30003u;
    for (uint32_t b0 = 0; b0 < 0x10000; b0++) {
        u128 a = rnd128(), b = rnd128(); b._u32[0] = b0 * 0x01010101u; ck_rotqbybi(a, b); ck_shlqby(a, b); ck_shlqbybi(a, b);
    }
    for (n = 0; n < 400000; n++) { u128 a = rnd128(), b = rnd128(); ck_rotqbybi(a, b); ck_shlqby(a, b); ck_shlqbybi(a, b); }

    /* cwd: word 0 of a through the low 16 bits with counts that move the low bits, then
     * random pairs. The count list holds the boundaries of the 7-bit signed range. */
    rng = 0x40004u;
    { static const int counts[8] = {0, 1, 3, 4, 63, 64, -1, -64};
      for (uint32_t a0 = 0; a0 < 0x10000; a0++) {
          u128 a = rnd128(); a._u32[0] = a0; ck_cwd(a, counts[a0 & 7]);
      } }
    for (n = 0; n < 1000000; n++) ck_cwd(rnd128(), (int)(rnd() >> 3) - 0x10000000);
    { static const int edge[10] = {0, 1, 63, 64, 127, -1, -64, -65, 0x7FFFFFFF, (int)0x80000000u};
      for (int e = 0; e < 10; e++) for (uint32_t a0 = 0; a0 < 256; a0++) {
          u128 a = pattern((int)(a0 % 36)); a._u32[0] = a0; ck_cwd(a, edge[e]); } }

    /* cwx: the low bytes of both words (all sums of the low 4 bits), then random pairs. */
    rng = 0x50005u;
    for (uint32_t a0 = 0; a0 < 256; a0++) for (uint32_t b0 = 0; b0 < 256; b0++) {
        u128 a = rnd128(), b = rnd128(); a._u32[0] = a0; b._u32[0] = b0; ck_cwx(a, b);
    }
    { static const uint32_t bpat[8] = {0, 3, 4, 5, 8, 12, 0xFFFFFFFCu, 0xFFFFFFFFu};
      for (uint32_t a0 = 0; a0 < 0x10000; a0++) {
          u128 a = rnd128(), b = rnd128(); a._u32[0] = a0; b._u32[0] ^= bpat[a0 & 7]; ck_cwx(a, b); } }
    for (n = 0; n < 1000000; n++) ck_cwx(rnd128(), rnd128());

    /* cbd, cdd and cbx keep their scalar bodies: a regression of the neighbors. */
    rng = 0x60006u;
    for (n = 0; n < 300000; n++) {
        u128 a = rnd128(), b = rnd128(); ck_cbd(a, (int)(rnd() >> 3)); ck_cdd(a, (int)(rnd() >> 3)); ck_cbx(a, b);
    }

    /* fm: random patterns, random ordinary singles, then all pairs of a structured set
     * (every biased exponent, both signs, 8 fraction classes): 16.7 M lane pairs. */
    rng = 0x70007u;
    for (n = 0; n < 1000000; n++) ck_fm(rnd128(), rnd128());
    for (n = 0; n < 1000000; n++) {
        u128 a, b;
        for (int i = 0; i < 4; i++) { a._u32[i] = ((rnd() & 1) << 31) | ((1 + (rnd() % 254)) << 23) | (rnd() & 0x7FFFFFu);
                                      b._u32[i] = ((rnd() & 1) << 31) | ((1 + (rnd() % 254)) << 23) | (rnd() & 0x7FFFFFu); }
        ck_fm(a, b);
    }
    { static const uint32_t frac[8] = {0, 1, 0x7FFFFFu, 0x7FFFFEu, 0x400000u, 0x3FFFFFu, 0x000001u, 0x555555u};
      uint32_t x[4096]; int k = 0;
      for (uint32_t e = 0; e < 256; e++) for (int s = 0; s < 2; s++) for (int f = 0; f < 8; f++) x[k++] = ((uint32_t)s << 31) | (e << 23) | frac[f];
      for (int i = 0; i < 4096; i++) for (int j = 0; j < 4096; j += 4) {
          u128 a, b; set128(&a, x[i], x[i], x[i], x[i]); set128(&b, x[j], x[j + 1], x[j + 2], x[j + 3]); ck_fm(a, b);
      } }

    /* shufb: every selector in every byte, every selector in all bytes, then random masks
     * (bit 7 is set in half of the bytes). */
    rng = 0x80008u;
    { u128 a = pattern(1), b = pattern(2), c;
      for (uint32_t s = 0; s < 256; s++) { memset(c._u8, (int)s, 16); ck_shufb(a, b, c); }
      for (int p = 0; p < 16; p++) for (uint32_t s = 0; s < 256; s++) {
          c = pattern(0); c._u8[p] = (uint8_t)s; ck_shufb(pattern(0), pattern(1), c); ck_shufb(pattern(17), pattern(18), c);
          ck_shufb(rnd128(), rnd128(), c); } }
    for (n = 0; n < 2000000; n++) ck_shufb(rnd128(), rnd128(), rnd128());

    /* Local store: a read of every aligned address with each of the 16 low bits set, then
     * random addresses. The store holds random bytes. */
    rng = 0x90009u;
    memset(&ctx, 0, sizeof ctx); memset(&model_ctx, 0, sizeof model_ctx);
    ctx.ls = ctx.ls_store; model_ctx.ls = model_ctx.ls_store;
    for (uint32_t i = 0; i < SPU_LS_SIZE; i += 4) { uint32_t w = rnd(); memcpy(ctx.ls_store + i, &w, 4); }
    memcpy(model_ctx.ls_store, ctx.ls_store, SPU_LS_SIZE);
    for (uint32_t base = 0; base < SPU_LS_SIZE; base += 16) for (uint32_t low = 0; low < 16; low++) ck_ls_read128(&ctx, base | low);
    for (n = 0; n < 1000000; n++) { uint32_t lsa = rnd(); if ((n & 3) == 0) lsa = 0xFFFFFFF0u + (rnd() & 15); ck_ls_read128(&ctx, lsa); }

    /* Local store writes: every aligned address with four low-bit patterns, a compare of
     * the whole store, then random writes with the window compare. */
    { static const uint32_t lows[4] = {0, 5, 9, 15}; const uint32_t zero = 0;
      for (uint32_t base = 0; base < SPU_LS_SIZE; base += 16) for (int k = 0; k < 4; k++) ck_ls_write128(&ctx, base | lows[k]);
      cases[R_LS_WRITE]++;
      if (memcmp(ctx.ls_store, model_ctx.ls_store, SPU_LS_SIZE)) mismatch(R_LS_WRITE, "ref", *(u128*)ctx.ls_store, *(u128*)model_ctx.ls_store, &zero, 1);
    }
    for (n = 0; n < 1000000; n++) ck_ls_write128(&ctx, rnd());

    long total = 0, bad = 0;
    for (int op = 0; op < R_COUNT; op++) {
        printf("op %-11s cases=%ld ref=%ld model=%ld\n", names[op], cases[op], ref_bad[op], model_bad[op]);
        total += cases[op]; bad += ref_bad[op] + model_bad[op];
    }
    printf("RESULT %s cases=%ld\n", bad ? "FAIL" : "PASS", total);
    return bad != 0;
}
#endif
