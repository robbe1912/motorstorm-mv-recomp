#ifndef PPU_FASTMEM_HEADER
#define PPU_FASTMEM_HEADER "ps3emu/ppu_fastmem.h"
#endif
#include PPU_FASTMEM_HEADER
#include "ps3emu/guest_read_sync.h"
#include "rsx_surface_readback.h"
#include <stdio.h>
#include <string.h>
static unsigned char memory[0x30000];
uint8_t *vm_base=memory;uint32_t ppu_vm_size=sizeof memory,ppu_hle_inject_base=0;
volatile uint32_t ppu_fm_diag=0;
uint32_t sysmem_spu_alias_fixup(uint32_t a){return a;}
uint8_t vm_read8(uint64_t a){return memory[a];}
uint16_t vm_read16(uint64_t a){return (uint16_t)((memory[a]<<8)|memory[a+1]);}
uint32_t vm_read32(uint64_t a){return ((uint32_t)vm_read16(a)<<16)|vm_read16(a+2);}
uint64_t vm_read64(uint64_t a){return ((uint64_t)vm_read32(a)<<32)|vm_read32(a+4);}
void ppu_fm_hotread8(uint32_t a,void *r){(void)a;(void)r;}
void ppu_fm_hotread16(uint32_t a,void *r){(void)a;(void)r;}
void ppu_fm_hotread32(uint32_t a,uint32_t v,void *r){(void)a;(void)v;(void)r;}
void ppu_fm_hotread64(uint32_t a,uint64_t v,void *r){(void)a;(void)v;(void)r;}
void ppu_fm_refpoll(void){}
static unsigned calls;
static const unsigned char host_half[8]={0x00,0x3c,0x00,0xbc,0x00,0x7c,0x00,0xfe};
static void device_sync(uint32_t a,uint32_t n,void *context) {
    (void)a;(void)n;(void)context;calls++;
    if(rsx_surface_readback_rows(memory+0x20120,8,8,host_half,8,8,1,1,11))calls=999;
}
#define REQUIRE(x,label) do {if(!(x)){fprintf(stderr,"FAIL: %s\n",label);return 1;}}while(0)
int main(void){
    vm_read_sync_set_handler(device_sync,NULL);
    REQUIRE(vm_read_sync_mark_range(0x20120,8)==0,"register surface");
    REQUIRE(ppu_fm_read16(0x20120)==0x3c00,"fast guest half read sees device 1.0");
    REQUIRE(ppu_fm_read16(0x20122)==0xbc00,"negative half bits");
    REQUIRE(ppu_fm_read32(0x20124)==0x7c00fe00,"infinity and NaN payload preserved");
    REQUIRE(ppu_fm_read8(0x20120)==0x3c,"byte load barrier");
    REQUIRE(ppu_fm_read64(0x20120)==UINT64_C(0x3c00bc007c00fe00),"64-bit load barrier");
    REQUIRE(calls==5,"every overlapping read synchronizes");
    REQUIRE(ppu_fm_read16(0x11000)==0&&calls==5,"unowned page has no callback");
    REQUIRE(vm_read_sync_mark_range(0xfffffffc,8)!=0,"wrapped range rejected");
    unsigned char src[32]={0},dst[40];memset(dst,0xa5,sizeof dst);
    memcpy(src,host_half,8);memcpy(src+16,host_half,8);
    REQUIRE(rsx_surface_readback_rows(dst,sizeof dst,20,src,sizeof src,16,1,2,11)==0,"different host and guest pitch");
    REQUIRE(dst[0]==0x3c&&dst[20]==0x3c&&dst[8]==0xa5&&dst[28]==0xa5,"row padding remains untouched");
    REQUIRE(rsx_surface_readback_rows(dst,7,20,src,sizeof src,16,1,2,11)!=0,"short destination rejected");
    const unsigned char rgba[4]={0x12,0x34,0x56,0x78};
    REQUIRE(rsx_surface_readback_rows(dst,4,4,rgba,4,4,1,1,8)==0,"RGBA8 surface packing");
    const unsigned char argb[4]={0x78,0x12,0x34,0x56};
    REQUIRE(memcmp(dst,argb,4)==0,"guest ARGB byte order");
    const unsigned char fp32[16]={0,0,0x80,0x3f,0,0,0x80,0xbf,0,0,0x80,0x7f,0x12,0x34,0xc0,0x7f};
    const unsigned char be32[16]={0x3f,0x80,0,0,0xbf,0x80,0,0,0x7f,0x80,0,0,0x7f,0xc0,0x34,0x12};
    REQUIRE(rsx_surface_readback_rows(dst,16,16,fp32,16,16,1,1,12)==0&&memcmp(dst,be32,16)==0,"FP32 bits preserved");
    REQUIRE(rsx_surface_readback_rows(dst,16,16,fp32,16,16,1,1,1)!=0,"unsupported format fails");
    vm_read_sync_set_handler(NULL,NULL);unsigned old=calls;vm_cpu_read_sync(0x20120,2);REQUIRE(calls==old,"handler removal");
    puts("PASS: CPU surface coherence");return 0;
}
