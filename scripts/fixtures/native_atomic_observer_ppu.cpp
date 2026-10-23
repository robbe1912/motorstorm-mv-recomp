/* Authored fixture scaffolding; real extracted PPU CAS functions follow. */
#include "native_atomic_observer_support.h"
typedef long LONG;
struct ppu_context { uint32_t reserve_addr,thread_id; uint64_t lr; };
static ppu_context fixture_ppu;
static ppu_context* g_active_ctx=&fixture_ppu;
static int fixture_resv_off, fixture_coherent, fixture_resv_held;
static uint32_t fixture_break_count;
static uint32_t fixture_watch_count;
static void wp_hit(uint32_t,uint32_t,uint32_t,const char*,void*){fixture_watch_count++;}
static uint32_t g_ww_lo,g_ww_hi;
static int resv_off(void){return fixture_resv_off;}
static int resv_diag(void){return 0;}
static void resv_check_reg(ppu_context*){abort();}
static volatile LONG* resv_slot(uint64_t){static LONG slot;return &slot;}
static void resv_lock(volatile LONG*){assert(!fixture_resv_held);fixture_resv_held=1;}
static void resv_unlock(volatile LONG*){assert(fixture_resv_held);fixture_resv_held=0;}
static int spu_coh_is_reserved(uint32_t){return fixture_coherent;}
static void ppu_resv_break(uint64_t){fixture_break_count++;fixture_ppu.reserve_addr=~0u;}
static void ppu_ww_note_atomic(uint32_t,uint32_t,int,void*){abort();}
extern "C" void issue219_ppu_setup(uint32_t reserve,int off,int coherent){
    g_active_ctx=&fixture_ppu;
    fixture_ppu.reserve_addr=reserve;fixture_ppu.lr=0x1234;
    fixture_ppu.thread_id=17;fixture_resv_off=off;fixture_coherent=coherent;
    fixture_break_count=0;fixture_watch_count=0;
}
extern "C" int issue219_ppu_reservation_lost(void){return fixture_ppu.reserve_addr==~0u;}
extern "C" uint32_t issue219_ppu_breaks(void){return fixture_break_count;}
extern "C" int issue219_ppu_lock_held(void){return fixture_resv_held;}
extern "C" void issue219_ppu_no_context(void){g_active_ctx=NULL;}
extern "C" uint32_t issue219_ppu_watch_count(void){return fixture_watch_count;}
/* FIXTURE_PRODUCTION_INSERT */
