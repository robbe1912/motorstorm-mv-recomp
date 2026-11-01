/* Actual generated registration and HLE bridge; unrelated guest services abort. */
#include "ppu_context.h"
#include "ps3emu/guest_call.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
extern "C" {
uint8_t* vm_base;
uint32_t ppu_vm_size=0x10000, g_ww_lo=0, g_ww_hi=0;
int g_resv_store_active=0;
ps3_guest_caller_fn g_ps3_guest_caller=nullptr;
void ppu_hle_register_all();
int ps3_hle_has(uint32_t);
void ps3_hle_call(uint32_t,ppu_context*);
uint32_t prx_resolve_export(uint32_t) { return 0; }
void ps3_indirect_call(ppu_context*) { std::abort(); }
uint64_t ppu_guest_call(uint32_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t) { std::abort(); }
void ppu_prof_stamp(void*,unsigned) {}
void ppu_gcm_pump() {}
uint32_t ppu_prof_resolve_host(void*) { return 0; }
void ps3_msf(const char*,...) {}
int spu_coh_is_reserved(uint32_t) { return 0; }
void spu_coh_notify_write(uint32_t) {}
void spu_lockline_lock() {}
void spu_lockline_unlock() {}
void ppu_resv_break_store(uint64_t) {}
void ps3_ww_report_inline(uint32_t,uint64_t,int) {}
uint32_t vm_read32(uint64_t a) { uint32_t x;std::memcpy(&x,vm_base+a,4);return __builtin_bswap32(x); }
void vm_write32(uint64_t a,uint32_t x) { x=__builtin_bswap32(x);std::memcpy(vm_base+a,&x,4); }
uint64_t vm_read64(uint64_t a) { uint64_t x;std::memcpy(&x,vm_base+a,8);return __builtin_bswap64(x); }
void ppu_dump_guest_stack(ppu_context*,const char*) {}
void ppu_dump_bctrl_ring(uint32_t,const char*) {}
void ppu_guest_callstack(const char*) {}
uint32_t g_ydkj_real_spurs_ea=0,g_ydkj_real_taskset_ea=0;
volatile int g_spu_coh_armed=0;
uint32_t sysmem_spu_alias_fixup(uint32_t a) { return a; }
void ppu_guest_throttle() {}
void ppu_fm_arm() {}
void vm_write64(uint64_t a,uint64_t x) { x=__builtin_bswap64(x);std::memcpy(vm_base+a,&x,8); }
}
#define CHECK(x) do { if(!(x)) { std::fprintf(stderr,"FAIL: %s\n",#x);return 1; } } while(0)
int main() {
    vm_base=static_cast<uint8_t*>(std::calloc(1,ppu_vm_size)); CHECK(vm_base);
    ppu_hle_register_all(); CHECK(ps3_hle_has(0xefeb2679));
    for (uint32_t max=1;max<=6;max++) {
        ppu_context c{}; c.gpr[1]=0x8000; c.gpr[3]=0x1000; c.gpr[4]=0x12345678;
        c.gpr[5]=0x87654321; c.gpr[6]=0x11112222; c.gpr[7]=0x33334444;
        c.gpr[8]=0x123456789abcdef0ULL; c.gpr[9]=0x2000; c.gpr[10]=3;
        for(unsigned i=0;i<8;i++) vm_base[0x2000+i]=static_cast<uint8_t>(i+1);
        vm_write64(0x8070,0xa1b2c3d400000000ULL|max);
        ps3_hle_call(0xefeb2679,&c);
        CHECK(c.gpr[3]==0); CHECK(vm_read32(0x1024)==max);
        CHECK(vm_read32(0x1000)==0x12345678); CHECK(vm_read32(0x1004)==0x87654321);
        CHECK(vm_read32(0x1008)==0x11112222); CHECK(vm_read32(0x100c)==0x33334444);
        CHECK(vm_read64(0x1010)==0x123456789abcdef0ULL); CHECK(vm_read32(0x1020)==3);
        for(unsigned i=0;i<8;i++) CHECK(vm_base[0x1018+i]==i+1);
    }
    ppu_context c{};c.gpr[1]=0x8000;c.gpr[3]=0;
    ps3_hle_call(0xefeb2679,&c);
    CHECK(c.gpr[3]==uint64_t(int64_t(int32_t(0x80410711u))));
    std::puts("PASS generated SPURS NID and actual PPU HLE dispatch");
}
