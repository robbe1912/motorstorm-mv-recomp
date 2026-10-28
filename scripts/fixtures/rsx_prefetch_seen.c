/* Authored programs and forced hash collisions; no guest bytes. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "rsx_prefetch_seen.h"
#include "rsx_fp_decompiler.h"
static rsx_prefetch_seen seen;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"FAIL %d %s\n",__LINE__,#x);return 1;}}while(0)
static void word(u8*p,u32 v){v=(v<<16)|(v>>16);p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;}
int main(void){unsigned checks=0;unsigned char a[32]={0},b[32],ca[32],cb[32];
 word(a,(1u<<24)|(15u<<9)|1u);word(a+4,(7u<<18)|0x1c800u|2u);word(a+8,0x1c800u);word(a+12,0x1c800u);
 memcpy(b,a,32);memset(b+16,0xff,16);
 CHECK(rsx_fp_canonical_program(a,32,ca,32)==32);CHECK(rsx_fp_canonical_program(b,32,cb,32)==32);
 CHECK(!memcmp(ca,cb,32));CHECK(!rsx_fp_canonical_program(a,31,ca,32));
 CHECK(!rsx_fp_canonical_program(a,32,ca,31));
 rsx_prefetch_begin(&seen);CHECK(!rsx_prefetch_contains_or_add(&seen,7,ca,32));
 CHECK(rsx_prefetch_contains_or_add(&seen,7,cb,32));cb[2]^=1;
 CHECK(!rsx_prefetch_contains_or_add(&seen,7,cb,32));CHECK(rsx_prefetch_contains_or_add(&seen,7,cb,32));
 rsx_prefetch_begin(&seen);CHECK(!rsx_prefetch_contains_or_add(&seen,7,ca,32));
 for(unsigned i=0;i<RSX_PREFETCH_SEEN_COUNT+4;i++){
  CHECK(!rsx_prefetch_contains_or_add(&seen,9,&i,sizeof(i)));
 }
 seen.generation=UINT64_MAX;rsx_prefetch_begin(&seen);CHECK(seen.generation==1 && seen.used==0);
 CHECK(!rsx_prefetch_contains_or_add(&seen,7,ca,32));seen.used=RSX_PREFETCH_KEY_BYTES;
 CHECK(!rsx_prefetch_contains_or_add(&seen,8,cb,32));CHECK(rsx_prefetch_contains_or_add(&seen,7,ca,32));
 printf("PASS exact prefetch checks=%u\n",checks);return 0;
}
