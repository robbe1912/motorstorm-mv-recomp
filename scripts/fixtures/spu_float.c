/* Authored value cases from IBM SPU ISA v1.2 section 9; no game inputs. */
#include "spu_helpers.h"
#include <stdio.h>
static u128 word(uint32_t x) { u128 r; for(int i=0;i<4;i++)r._u32[i]=x; return r; }
static unsigned failures, checks;
static void check(const char* label,u128 result,uint32_t expected) {
    for(int i=0;i<4;i++){++checks;if(result._u32[i]!=expected){++failures;fprintf(stderr,"%s lane%d: %08x != %08x\n",label,i,result._u32[i],expected);}}
}
int main(void) {
    check("ISA case 0: spu_fa",spu_fa(word(0x00800000u),word(0x807fffffu)),0x00800000u);
    check("ISA case 1: spu_fa",spu_fa(word(0x7fffffffu),word(0x7fffffffu)),0x7fffffffu);
    check("ISA case 2: spu_fa",spu_fa(word(0xffffffffu),word(0xffffffffu)),0xffffffffu);
    check("ISA case 3: spu_fa",spu_fa(word(0x3f800000u),word(0x33800000u)),0x3f800000u);
    check("ISA case 4: spu_fs",spu_fs(word(0x3f800000u),word(0x3f800000u)),0x00000000u);
    check("ISA case 5: spu_fs",spu_fs(word(0x00000000u),word(0x80000000u)),0x00000000u);
    check("ISA case 6: spu_fs",spu_fs(word(0x3f800000u),word(0x33800000u)),0x3f7fffffu);
    check("ISA case 7: spu_fm",spu_fm(word(0x00000000u),word(0x7fffffffu)),0x00000000u);
    check("ISA case 8: spu_fm",spu_fm(word(0x80000000u),word(0x7f800000u)),0x00000000u);
    check("ISA case 9: spu_fm",spu_fm(word(0x3f800000u),word(0x7fffffffu)),0x7fffffffu);
    check("ISA case 10: spu_fm",spu_fm(word(0x00800000u),word(0x3f000000u)),0x00000000u);
    check("ISA case 11: spu_fm",spu_fm(word(0x00800000u),word(0xbf000000u)),0x00000000u);
    check("ISA case 12: spu_fma",spu_fma(word(0x7fffffffu),word(0x40000000u),word(0xffffffffu)),0x7fffffffu);
    check("ISA case 13: spu_fma",spu_fma(word(0x00800000u),word(0x3f000000u),word(0x00800000u)),0x00c00000u);
    check("ISA case 14: spu_fms",spu_fms(word(0x7fffffffu),word(0x40000000u),word(0x7fffffffu)),0x7fffffffu);
    check("ISA case 15: spu_fnms",spu_fnms(word(0x7fffffffu),word(0x40000000u),word(0x7fffffffu)),0xffffffffu);
    check("ISA case 16: spu_fi",spu_fi(word(0x00000000u),word(0x7fb50160u)),0x7fb50000u);
    check("ISA case 17: spu_fi",spu_fi(word(0x00000000u),word(0xffb50160u)),0xffb50000u);
    check("ISA case 18: spu_fi",spu_fi(word(0x0007ffffu),word(0x3f8003ffu)),0x3f600803u);
    u128 zero=word(0),estimate=spu_frsqest(zero);
    check("zero normalization chain",spu_fm(zero,spu_fi(zero,estimate)),0);
    printf("SPU float values: %u lanes, %u failures\n",checks,failures);
    return failures!=0;
}
