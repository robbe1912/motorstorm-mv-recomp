#include <stdio.h>
#include <stdint.h>
#include <setjmp.h>
#include "spu_helpers.h"
static unsigned failures,checks;
static void check(int ok,const char *name) {
    ++checks;if(!ok){++failures;fprintf(stderr,"FAIL %s\n",name);}
}
static uint32_t random_word(uint32_t *state) {
    *state=*state*1664525u+1013904223u;return *state;
}
static uint32_t reference(unsigned op,uint32_t a,uint32_t b,uint32_t c) {
    switch(op) {
    case 0:return spu_sf_add(a,b);
    case 1:return spu_sf_add(a,b^0x80000000u);
    case 2:return spu_sf_mul(a,b);
    default:return spu_sf_madd(a,b,c^(op==4?0x80000000u:0),op==5?0x80000000u:0);
    }
}
static u128 execute(unsigned op,u128 a,u128 b,u128 c) {
    switch(op){case 0:return spu_fa(a,b);case 1:return spu_fs(a,b);
    case 2:return spu_fm(a,b);case 3:return spu_fma(a,b,c);
    case 4:return spu_fms(a,b,c);default:return spu_fnms(a,b,c);}
}
int main(void) {
#if SPU_SF_X86_SIMD
    uint32_t original=_mm_getcsr();
    const uint32_t edge[]={0,0x80000000u,1,0x807fffffu,0x00800000u,
        0x3f800000u,0xbf800000u,0x3f800001u,0x3f7fffffu,
        0x7effffffu,0xfeffffffu,0x7f000000u,0xff000000u,
        0x7f7fffffu,0x7f800000u,0x7fffffffu,0xffffffffu};
    unsigned long long lanes=0,fast=0;
    uint32_t state=0x7a91123u;
    for(unsigned mode=0;mode<4;++mode) {
        uint32_t caller=0x1fa1u|(mode<<13);_mm_setcsr(caller);
        uint64_t outer=spu_sf_simd_enter();int capability=g_spu_sf_simd_scope;
        check(capability>=1,"SSE scope enabled");
        check(_mm_getcsr()==caller,"scope preserves rounding of other host services");
        uint64_t inner=spu_sf_simd_enter();spu_sf_simd_leave(inner);
        check(g_spu_sf_simd_scope==capability,"nested scope preserves enable state");
        u128 one,above_half,constant_result;
        for(unsigned lane=0;lane<4;++lane){one._u32[lane]=0x3f800000u;above_half._u32[lane]=0x33800001u;}
        constant_result=spu_fa(one,above_half);
        check(constant_result._u32[0]==0x3f800000u,"constant operands still use SPU truncation");
        uint32_t fused_out[4];
        int fused=spu_sf_simd_fused(fused_out,one._u32,one._u32,one._u32,0,0);
        check(fused==(capability==2),"hardware FMA admission follows checked CPU capability");
        if(fused)check(fused_out[0]==0x40000000u,"hardware fused result is correct");
        unsigned mismatches=0;
        for(unsigned i=0;i<120000;++i) {
            u128 a,b,c,r;
            for(unsigned lane=0;lane<4;++lane) {
                a._u32[lane]=random_word(&state);b._u32[lane]=random_word(&state);c._u32[lane]=random_word(&state);
                if(i<sizeof(edge)/sizeof(edge[0])*16) {
                    a._u32[lane]=edge[(i+lane)%17];b._u32[lane]=edge[((i/17)+lane)%17];c._u32[lane]=edge[((i/7)+lane)%17];
                } else if(i&1) {
                    a._u32[lane]=(a._u32[lane]&0x807fffffu)|0x3f000000u;
                    b._u32[lane]=(b._u32[lane]&0x807fffffu)|0x3f000000u;
                    c._u32[lane]=(c._u32[lane]&0x807fffffu)|0x3f000000u;
                }
            }
            unsigned op=i%6;r=execute(op,a,b,c);
            for(unsigned lane=0;lane<4;++lane) {
                uint32_t expected=reference(op,a._u32[lane],b._u32[lane],c._u32[lane]);
                if(r._u32[lane]!=expected){if(!mismatches)fprintf(stderr,"op=%u a=%08x b=%08x c=%08x got=%08x expected=%08x\n",op,a._u32[lane],b._u32[lane],c._u32[lane],r._u32[lane],expected);++mismatches;}
                ++lanes;
            }
            fast+=op<3 ? spu_sf_simd_binary(r._u32,a._u32,b._u32,(int)op)
                : spu_sf_simd_fused(r._u32,a._u32,b._u32,c._u32,op==5?0x80000000u:0,op==4?0x80000000u:0);
        }
        check(!mismatches,"mixed-lane values match exact integer helpers");
        check(_mm_getcsr()==caller,"every arithmetic operation restores host flags and rounding");
        uint32_t zero[4]={0},out[4];
        g_spu_sf_simd_scope=1;
        check(!spu_sf_simd_fused(out,zero,zero,zero,0,0),"FMA unavailable preserves scalar fallback");
        g_spu_sf_simd_scope=capability;
        spu_sf_simd_leave(outer);
        check(g_spu_sf_simd_scope==0 && _mm_getcsr()==caller,"caller environment restored exactly");
    }
    check(fast>10000,"normal SIMD path actually exercised");
    jmp_buf jump;
    uint64_t outer=spu_sf_simd_enter();
    if(!setjmp(jump)){(void)spu_sf_simd_enter();longjmp(jump,1);}
    spu_sf_simd_leave(outer);
    check(!g_spu_sf_simd_scope && _mm_getcsr()==0x7fa1u,"outer scope restores after nested longjmp");
    _mm_setcsr(0); /* Caller has every SSE exception unmasked. */
    outer=spu_sf_simd_enter();
    u128 one,above_half;
    for(unsigned lane=0;lane<4;++lane){one._u32[lane]=0x3f800000u;above_half._u32[lane]=0x33800001u;}
    u128 truncated=spu_fa(one,above_half);
    spu_sf_simd_leave(outer);
    unsigned restored=_mm_getcsr();
    _mm_setcsr(original);
    check(!restored && truncated._u32[0]==0x3f800000u,"inexact arithmetic masks traps locally and restores unmasked caller");
    printf("lanes=%llu fast_vectors=%llu ",lanes,fast);
#endif
    printf("checks=%u failures=%u\n",checks,failures);return failures?1:0;
}
