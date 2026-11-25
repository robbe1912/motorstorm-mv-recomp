#include <stdio.h>
#include <stdint.h>
#include <setjmp.h>
#include <string.h>
#include <math.h>
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

/* Helpers that compute with ordinary host arithmetic, by index. */
enum { HOST_OPS=17 };
static u128 host_op(unsigned k,u128 a,u128 b,u128 c,int imm) {
    switch(k){
    case 0:return spu_cflts(a,imm);case 1:return spu_cfltu(a,imm);
    case 2:return spu_csflt(a,imm);case 3:return spu_cuflt(a,imm);
    case 4:return spu_dfa(a,b);case 5:return spu_dfs(a,b);case 6:return spu_dfm(a,b);
    case 7:return spu_dfma(a,b,c);case 8:return spu_dfms(a,b,c);
    case 9:return spu_dfnms(a,b,c);case 10:return spu_dfnma(a,b,c);
    case 11:return spu_dfceq(a,b);case 12:return spu_dfcmeq(a,b);
    case 13:return spu_dfcgt(a,b);case 14:return spu_dfcmgt(a,b);
    case 15:return spu_fesd(a);default:return spu_frds(a);
    }
}
/* Host IEEE compares, the results the integer compares must keep. */
static uint32_t host_compare(unsigned k,uint32_t a,uint32_t b) {
    float x,y;memcpy(&x,&a,4);memcpy(&y,&b,4);
    switch(k){case 0:return x==y?~0u:0;case 1:return x>y?~0u:0;
    case 2:return fabsf(x)==fabsf(y)?~0u:0;default:return fabsf(x)>fabsf(y)?~0u:0;}
}
static u128 compare_op(unsigned k,u128 a,u128 b) {
    switch(k){case 0:return spu_fceq(a,b);case 1:return spu_fcgt(a,b);
    case 2:return spu_fcmeq(a,b);default:return spu_fcmgt(a,b);}
}
/* Mixed words: zeros, denormals, normals, infinities, NaN payloads, and
 * doubles/integers with every exponent. */
static uint32_t mixed_word(uint32_t *state) {
    uint32_t w=random_word(state);
    switch(w>>29){                                 /* high bits: the LCG low bits cycle */
    case 0:return w&0x807fffffu;                       /* denormal */
    case 1:return w&0x80000000u;                       /* signed zero */
    case 2:return (w&0x80000000u)|0x7f800000u|((w>>28)&1 ? w&0x7fffffu : 0); /* inf or NaN */
    case 3:return (w&0x807fffffu)|0x3f000000u;          /* near one */
    default:return random_word(state);
    }
}
static u128 execute(unsigned op,u128 a,u128 b,u128 c) {
    switch(op){case 0:return spu_fa(a,b);case 1:return spu_fs(a,b);
    case 2:return spu_fm(a,b);case 3:return spu_fma(a,b,c);
    case 4:return spu_fms(a,b,c);default:return spu_fnms(a,b,c);}
}
#if SPU_SF_X86_SIMD
/* 1 + 3*2^-54 in each double lane: three quarters of the last place of 1, so
 * the rounding direction shows in the last bit. */
static uint64_t host_rounding(void) {
    u128 one,part,r;memset(&one,0,sizeof one);memset(&part,0,sizeof part);
    for(int i=0;i<2;i++){spu__dset(&one,i,1.0);spu__dset(&part,i,0x1.8p-53);}
    r=spu_dfa(one,part);double d=spu__dget(r,0);uint64_t bits;memcpy(&bits,&d,8);return bits;
}
/* Nearest and up round up, down and toward zero do not. */
static uint64_t expected_rounding(uint32_t csr) {
    unsigned rc=(csr>>13)&3;return 0x3ff0000000000000ull+(rc==0 || rc==2);
}
/* A caller that already uses SPU controls without a scope is an ordinary host
 * environment: helpers run in it as it is, whatever an earlier scope recorded,
 * and leave it alone. A scope it enters records it. */
static void outside_scope(uint32_t *state) {
    const uint32_t callers[]={SPU_SF_CSR_SPU,SPU_SF_CSR_SPU|0x21u};
    for(unsigned n=0;n<2;++n) {
        uint32_t caller=callers[n];unsigned changed=0,moved=0,scoped=0;
        check(g_spu_sf_simd_scope==0,"no scope is active");
        for(unsigned i=0;i<20000;++i) {
            u128 a,b,c,first,second,inside;static const int scale[]={173,155,0,100,200,255,140,190};
            for(unsigned lane=0;lane<4;++lane){a._u32[lane]=mixed_word(state);b._u32[lane]=mixed_word(state);c._u32[lane]=mixed_word(state);}
            unsigned k=i%HOST_OPS;int imm=scale[(i/HOST_OPS)%8];
            uint32_t recorded=(0x1f80u|((i&3u)<<13)); /* what some earlier scope left behind */
            _mm_setcsr(caller);g_spu_sf_host_csr=caller;first=host_op(k,a,b,c,imm);
            moved+=(_mm_getcsr()&~0x3fu)!=(caller&~0x3fu);
            _mm_setcsr(caller);g_spu_sf_host_csr=recorded;second=host_op(k,a,b,c,imm);
            moved+=(_mm_getcsr()&~0x3fu)!=(caller&~0x3fu);
            changed+=memcmp(&first,&second,sizeof first)!=0;
            _mm_setcsr(caller);uint64_t token=spu_sf_simd_enter();inside=host_op(k,a,b,c,imm);spu_sf_simd_leave(token);
            scoped+=memcmp(&first,&inside,sizeof first)!=0;
        }
        _mm_setcsr(caller);g_spu_sf_host_csr=0x1f80u;
        check(host_rounding()==expected_rounding(caller),"outside a scope a truncating caller truncates");
        check(!changed,"outside a scope helpers ignore the recorded environment");
        check(!moved,"outside a scope helpers leave the caller's controls alone");
        check(!scoped,"a scope entered by a caller with SPU controls gives the same results");
        _mm_setcsr(caller);   /* the rounding probe left its inexact flag */
        uint64_t token=spu_sf_simd_enter();
        check(g_spu_sf_host_csr==caller,"the outermost scope records a caller with SPU controls");
        spu_sf_simd_leave(token);
        check(_mm_getcsr()==caller,"a caller with SPU controls is restored exactly");
    }
}
#endif
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
        check(_mm_getcsr()==(caller|SPU_SF_CSR_SPU),"scope holds SPU mode and keeps the caller's status flags");
        check(g_spu_sf_host_csr==caller,"outermost scope records the caller's environment");
        uint64_t inner=spu_sf_simd_enter();
        check(g_spu_sf_host_csr==caller,"nested scope keeps the outermost caller environment");
        spu_sf_simd_leave(inner);
        check(g_spu_sf_simd_scope==capability,"nested scope preserves enable state");
        /* Controls changed inside the scope (as by host code it calls) do not
         * make a nested entry the outermost one. */
        uint32_t held_now=_mm_getcsr(),changed=caller^0x2000u;
        _mm_setcsr(changed);
        inner=spu_sf_simd_enter();
        check(g_spu_sf_host_csr==caller,"nested entry after a control change keeps the outermost caller environment");
        check(spu_sf_csr_is_spu(_mm_getcsr()),"nested entry after a control change holds SPU mode");
        check(host_rounding()==expected_rounding(caller),"nested scope keeps the outermost caller's rounding");
        spu_sf_simd_leave(inner);
        check(g_spu_sf_host_csr==caller && (_mm_getcsr()&~0x3fu)==(changed&~0x3fu),"nested leave restores the changed controls");
        _mm_setcsr(held_now);
        check(_mm_getcsr()==(caller|SPU_SF_CSR_SPU),"nested scope restores the held SPU mode");
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
        check(spu_sf_csr_is_spu(_mm_getcsr()),"arithmetic leaves the scope's SPU mode held");
        /* An older MXCSR inside a scope (as after a longjmp to a point saved
         * outside it): the arithmetic switches per operation and stays exact. */
        _mm_setcsr(caller);
        unsigned unheld=0;
        for(unsigned i=0;i<6000;++i) {
            u128 a,b,c,r;
            for(unsigned lane=0;lane<4;++lane){a._u32[lane]=mixed_word(&state);b._u32[lane]=mixed_word(&state);c._u32[lane]=mixed_word(&state);}
            unsigned op=i%6;r=execute(op,a,b,c);
            for(unsigned lane=0;lane<4;++lane) unheld+=r._u32[lane]!=reference(op,a._u32[lane],b._u32[lane],c._u32[lane]);
        }
        check(!unheld,"scope without held SPU mode stays exact");
        check(_mm_getcsr()==caller,"per-operation switching restores an unheld environment");
        _mm_setcsr(caller|SPU_SF_CSR_SPU);
        /* Host-arithmetic helpers and float compares give the caller-environment
         * results inside the held scope. */
        unsigned host_diff=0,compare_diff=0,host_mode_lost=0;
        static const int scale[]={173,155,0,100,200,255,140,190};
        for(unsigned i=0;i<20000;++i) {
            u128 a,b,c,inside,outside;
            for(unsigned lane=0;lane<4;++lane){a._u32[lane]=mixed_word(&state);b._u32[lane]=mixed_word(&state);c._u32[lane]=mixed_word(&state);}
            unsigned k=i%HOST_OPS;int imm=scale[(i/HOST_OPS)%8];
            uint32_t held=_mm_getcsr();
            inside=host_op(k,a,b,c,imm);
            host_mode_lost+=(_mm_getcsr()&SPU_SF_CSR_SPU)!=(held&SPU_SF_CSR_SPU);
            _mm_setcsr(caller);outside=host_op(k,a,b,c,imm);_mm_setcsr(held);
            host_diff+=memcmp(&inside,&outside,sizeof inside)!=0;
            /* Compare operands: equal, sign-flipped, adjacent or unrelated. */
            u128 d=b;
            for(unsigned lane=0;lane<4;++lane) switch((i/4+lane)%4){
            case 0:d._u32[lane]=a._u32[lane];break;
            case 1:d._u32[lane]=a._u32[lane]^0x80000000u;break;
            case 2:d._u32[lane]=a._u32[lane]+((i>>3)&1 ? 1u : ~0u);break;
            default:break;
            }
            unsigned j=i%4;u128 got=compare_op(j,a,d);
            uint32_t want[4];_mm_setcsr(caller);
            for(unsigned lane=0;lane<4;++lane) want[lane]=host_compare(j,a._u32[lane],d._u32[lane]);
            _mm_setcsr(held);
            for(unsigned lane=0;lane<4;++lane) compare_diff+=got._u32[lane]!=want[lane];
        }
        if(host_diff)fprintf(stderr,"host-arithmetic helper results differed inside the scope: %u\n",host_diff);
        if(compare_diff)fprintf(stderr,"compare lanes differed from host IEEE compares: %u\n",compare_diff);
        check(!host_diff,"host-arithmetic helpers keep caller-environment results inside the scope");
        check(!host_mode_lost,"host-arithmetic helpers return to the held SPU mode");
        check(!compare_diff,"float compares match host IEEE compares inside the scope");
        uint32_t zero[4]={0},out[4];
        g_spu_sf_simd_scope=1;
        check(!spu_sf_simd_fused(out,zero,zero,zero,0,0),"FMA unavailable preserves scalar fallback");
        g_spu_sf_simd_scope=capability;
        spu_sf_simd_leave(outer);
        check(g_spu_sf_simd_scope==0 && _mm_getcsr()==caller,"caller environment restored exactly");
    }
    outside_scope(&state);
    check(fast>10000,"normal SIMD path actually exercised");
    _mm_setcsr(0x7fa1u);
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
