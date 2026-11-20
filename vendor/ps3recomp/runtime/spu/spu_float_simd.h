/* Value-only SIMD under a scoped SPU rounding environment.
 *
 * A scope (spu_sf_simd_enter/leave) holds the host MXCSR in SPU mode for its
 * whole extent: truncation, flush-to-zero, denormals-are-zero, every
 * exception masked. SPU single-precision arithmetic then runs without
 * switching the MXCSR per operation. Each operation still reads the MXCSR
 * and only uses the held mode when it is actually present; otherwise (for
 * example after a longjmp restored an older MXCSR) it switches around the
 * operation as before. Helpers that compute with ordinary host arithmetic
 * (conversions, double precision) run in the environment recorded when the
 * outermost scope was entered (spu_sf_host_begin/end), so their results do
 * not depend on the scope. */
#ifndef PS3RECOMP_SPU_FLOAT_SIMD_H
#define PS3RECOMP_SPU_FLOAT_SIMD_H
#include <stdint.h>
#if defined(_MSC_VER)
#define SPU_SF_TLS __declspec(thread)
#else
#define SPU_SF_TLS __thread
#endif
#ifdef __cplusplus
extern "C" {
#endif
extern SPU_SF_TLS int g_spu_sf_simd_scope;
/* MXCSR of the caller of the outermost scope (control bits are used). */
extern SPU_SF_TLS uint32_t g_spu_sf_host_csr;
uint64_t spu_sf_simd_enter(void);
void spu_sf_simd_leave(uint64_t saved);
int spu_sf_simd_fused(uint32_t *out,const uint32_t *a,const uint32_t *b,
                      const uint32_t *c,uint32_t negate_product,uint32_t negate_c);
#ifdef __cplusplus
}
#endif
#if defined(__SSE2__) || defined(_M_X64)
#define SPU_SF_X86_SIMD 1
#include <emmintrin.h>
/* MXCSR control bits of SPU mode: RC=11 (truncate), FTZ, DAZ and all six
 * exception masks. The low six bits are sticky status flags. */
#define SPU_SF_CSR_SPU 0xffc0u
static inline int spu_sf_csr_is_spu(uint32_t csr) {
    return (csr & SPU_SF_CSR_SPU)==SPU_SF_CSR_SPU;
}
static inline uint32_t spu_sf_simd_round_begin(void) {
    uint32_t saved=_mm_getcsr();
    _mm_setcsr(saved|SPU_SF_CSR_SPU);
    return saved;
}
/* Host arithmetic inside a scope: switch to the caller's environment for the
 * helper's own arithmetic and back. Outside SPU mode nothing changes. */
static inline uint32_t spu_sf_host_begin(void) {
    uint32_t csr=_mm_getcsr();
    if (spu_sf_csr_is_spu(csr)) _mm_setcsr((g_spu_sf_host_csr & ~0x3fu)|(csr & 0x3fu));
    return csr;
}
static inline void spu_sf_host_end(uint32_t csr) {
    if (spu_sf_csr_is_spu(csr)) _mm_setcsr(csr);
}
static inline int spu_sf_simd_extended(__m128i a) {
    const __m128i exponent = _mm_set1_epi32(0x7f800000);
    return _mm_movemask_epi8(_mm_cmpeq_epi32(_mm_and_si128(a,exponent),exponent));
}
static inline int spu_sf_simd_store(uint32_t *out,__m128 value) {
    __m128i bits=_mm_castps_si128(value);
    __m128i magnitude=_mm_and_si128(bits,_mm_set1_epi32(0x7fffffff));
    /* Host RTZ overflow yields its largest finite value. Recompute the entire
     * vector near that boundary, including valid SPU exponent-255 results. */
    if (_mm_movemask_epi8(_mm_cmpgt_epi32(magnitude,_mm_set1_epi32(0x7effffff)))) return 0;
    bits=_mm_andnot_si128(_mm_cmpeq_epi32(magnitude,_mm_setzero_si128()),bits);
    _mm_storeu_si128((__m128i *)out,bits);
    return 1;
}
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((optimize("rounding-math")))
#endif
static inline int spu_sf_simd_binary(uint32_t *out,const uint32_t *a,
                                     const uint32_t *b,int operation) {
#if defined(__clang__)
#pragma STDC FENV_ACCESS ON
#elif defined(_MSC_VER)
#pragma fenv_access(on)
#endif
    if (!g_spu_sf_simd_scope) return 0;
    __m128i av=_mm_loadu_si128((const __m128i *)a),bv=_mm_loadu_si128((const __m128i *)b);
    if (spu_sf_simd_extended(av) || spu_sf_simd_extended(bv)) return 0;
    if (operation==1) bv=_mm_xor_si128(bv,_mm_set1_epi32((int)0x80000000u));
    __m128 af=_mm_castsi128_ps(av),bf=_mm_castsi128_ps(bv);
    if (spu_sf_csr_is_spu(_mm_getcsr()))   /* held by the scope */
        return spu_sf_simd_store(out,operation==2 ? _mm_mul_ps(af,bf) : _mm_add_ps(af,bf));
    uint32_t saved=spu_sf_simd_round_begin();
    int result=spu_sf_simd_store(out,operation==2 ? _mm_mul_ps(af,bf) : _mm_add_ps(af,bf));
    _mm_setcsr(saved);
    return result;
}
#else
#define SPU_SF_X86_SIMD 0
static inline uint32_t spu_sf_host_begin(void) { return 0; }
static inline void spu_sf_host_end(uint32_t csr) { (void)csr; }
static inline int spu_sf_simd_binary(uint32_t *out,const uint32_t *a,
                                     const uint32_t *b,int operation) {
    (void)out;(void)a;(void)b;(void)operation;return 0;
}
#endif
#endif
