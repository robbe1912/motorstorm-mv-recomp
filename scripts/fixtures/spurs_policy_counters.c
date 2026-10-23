/* Authored policies exercise actual runner/kernel intercepts, never game code. */
#include "cellSpurs.c"
#include "spu_dma.h"
#include <stdatomic.h>

uint8_t* vm_base;
uint32_t ppu_vm_size=0x20000;
int g_resv_store_active;
uint32_t g_ww_lo,g_ww_hi,g_barrier_sync_watch;
uint32_t g_spu_image_src_ea,g_spu_image_ls_start,g_spu_image_span;
PPU_THREAD_LOCAL ppu_context* g_active_ctx;
unsigned long long ps3_ms_now(void) {
    LARGE_INTEGER n,f; QueryPerformanceCounter(&n); QueryPerformanceFrequency(&f);
    return (unsigned long long)(n.QuadPart*1000/f.QuadPart);
}
static void require(int ok,const char* what) {
    if (!ok) { fprintf(stderr,"FAIL %s\n",what);exit(1); }
}
/* Unreachable SDK linkage on COFF: abort, never manufacture task completion. */
static void unexpected(void) { fprintf(stderr,"FAIL out-of-scope SDK API\n");abort(); }
void ppu_resv_break_store(uint64_t ea) { (void)ea;unexpected(); }
void ps3_ww_report_inline(uint32_t a,uint64_t v,int w) { (void)a;(void)v;(void)w;unexpected(); }
void spurs_taskset_init(uint32_t a,uint32_t b,uint64_t c,uint32_t d,uint32_t e,uint32_t f,uint32_t g) { unexpected(); }
void spurs_taskset_add_task(uint32_t a,uint32_t b,uint64_t c,uint64_t d,const uint32_t e[4],const uint32_t f[4]) { unexpected(); }
int sys_event_queue_push_by_id(uint32_t a,uint64_t b,uint64_t c,uint64_t d,uint64_t e) { unexpected();return -1; }
uint64_t spurs_pm_build_context(uint8_t* a,uint32_t b,uint32_t c,uint32_t d,uint32_t e) { unexpected();return 0; }
void ydkj_wake_all_event_flags(void) { unexpected(); }
void sys_event_queue_cancel_by_id(u32 id) { (void)id;unexpected(); }
void sys_event_queue_uncancel_by_id(u32 id) { (void)id;unexpected(); }
unsigned mainspin_watch_n(void) { unexpected();return 0; }
unsigned mainspin_watch_at(int i) { (void)i;unexpected();return 0; }
uint32_t spu_thread_register_phantom(void) { unexpected();return 0; }
void spu_thread_publish_ctx(uint32_t tid,void* ctx) { (void)tid;(void)ctx;unexpected(); }

void spu_indirect_branch(spu_context*);
void spu_halt(spu_context*);
static atomic_uint entered,other_done;
static unsigned phase;
static unsigned interpreted,expected_lanes,poll_lane;
static atomic_uint visited;
static int results[2];
static unsigned polls[2],batches[2];
static uint8_t image[16];
void policy_counter_interpreted_kernel(spu_context*);
static void dispatch_kernel(spu_context* c) {
    if (interpreted) policy_counter_interpreted_kernel(c);
    else spu_indirect_branch(c);
}
static void wait_for(atomic_uint* p,const char* what) {
    const unsigned long long deadline=ps3_ms_now()+3000;
    do { if(atomic_load(p))return;Sleep(1); } while(ps3_ms_now()<deadline);
    require(0,what);
}
static void kernel_exit(spu_context* c) {
    c->pc=SPURS_PM_EXIT_TO_KERNEL_LS;dispatch_kernel(c);
    require(0,"kernel exit did not unwind");
}
static void poll_kernel(spu_context* c) {
    c->pc=SPURS_PM_SELECT_WORKLOAD_LS;c->gpr[0]._u32[0]=0xA00;
    dispatch_kernel(c);
}
static void fetch_commands(spu_context* c) {
    mfc_engine engine;mfc_engine_init(&engine);
    int image_id=c->image_id;c->image_id=2;
    c->mfc_lsa=0xC00;c->mfc_eah=0;c->mfc_eal=0x10000;c->mfc_size=16;c->mfc_tag=0;
    for (unsigned i=0;i<7;i++) require(mfc_submit(&engine,c,0x40)==0,"actual command GET");
    require(memcmp(c->ls+0xC00,vm_base+0x10000,16)==0,"actual command bytes");
    c->image_id=image_id;
}
static void policy(spu_context* c) {
    unsigned lane=spu_ls_read32(c,0x1C8);
    if (phase==3) {
        require(lane<expected_lanes,"round physical lane");
        require(!(atomic_fetch_or(&visited,1u<<lane)&(1u<<lane)),"duplicate physical lane");
        atomic_fetch_add(&entered,1);
        unsigned long long deadline=ps3_ms_now()+3000;
        while (atomic_load(&entered)!=expected_lanes) {
            require(ps3_ms_now()<deadline,"round lanes did not overlap");Sleep(1);
        }
        if (lane==poll_lane) poll_kernel(c);
        kernel_exit(c);
    }
    if (!lane) {
        if (phase==1) { poll_kernel(c);fetch_commands(c); }
        atomic_store(&entered,1);wait_for(&other_done,"other policy did not return");
        if (phase==0) { c->status=SPU_STATUS_STOPPED_BY_HALT;spu_halt(c); }
        kernel_exit(c);
    } else {
        if (phase==1) { /* Reset by runner must not erase the other lane's poll. */
            require(g_spurs_pm_polls==0,"fresh worker poll state");
            require(g_wws_batch_gets==0,"fresh worker DMA state");
        }
        kernel_exit(c);
    }
}
static DWORD WINAPI run_policy(LPVOID arg) {
    unsigned lane=(unsigned)(uintptr_t)arg;
    results[lane]=spu_run_policy_module(policy,79,image,sizeof image,0,3,0x1000,lane);
    polls[lane]=g_spurs_pm_polls;batches[lane]=g_wws_batch_gets;
    if (lane) atomic_store(&other_done,1);
    return 0;
}
static void paired(unsigned which) {
    phase=which;atomic_store(&entered,0);atomic_store(&other_done,0);
    HANDLE a=CreateThread(NULL,0,run_policy,NULL,0,NULL);require(a!=NULL,"first thread");
    wait_for(&entered,"first policy did not enter");
    HANDLE b=CreateThread(NULL,0,run_policy,(LPVOID)(uintptr_t)1,0,NULL);require(b!=NULL,"second thread");
    require(WaitForSingleObject(a,5000)==WAIT_OBJECT_0,"first thread join");
    require(WaitForSingleObject(b,5000)==WAIT_OBJECT_0,"second thread join");
    require(CloseHandle(a) && CloseHandle(b),"close owned threads");
    if (!which) {
        require(results[0]==-2 && results[1]==0,"per-run stop versus kernel-exit classification");
    } else {
        require(results[0]==0 && results[1]==0,"polling run kernel returns");
        require(polls[0]==1 && polls[1]==0,"per-run poll isolation");
        require(batches[0]==7 && batches[1]==0,"per-run DMA diagnostic isolation");
    }
}
static void joined_rounds(void) {
    phase=3;
    for (unsigned lanes=1;lanes<=6;lanes++) {
        expected_lanes=lanes;
        for (poll_lane=0;poll_lane<=lanes;poll_lane++) {
            atomic_store(&entered,0);atomic_store(&visited,0);
            struct spurs_pm_worker_arg round={policy,79,image,sizeof image,0,3,0x1000,0,0};
            require(spurs_pm_run_lanes(round,lanes)==(poll_lane<lanes),"joined worker productivity aggregation");
            require(atomic_load(&visited)==(1u<<lanes)-1,"joined round visited all physical lanes");
        }
    }
    /* Admission rejection must clear old state before a worker records it. */
    g_spurs_pm_polls=9;g_spurs_pm_exited=1;g_wws_batch_gets=8;
    struct spurs_pm_worker_arg rejected={NULL,79,image,sizeof image,0,3,0x1000,0,0};
    require(spurs_pm_run_lanes(rejected,1)==0,"rejected run inherited stale productivity");
    require(!g_spurs_pm_polls && !g_spurs_pm_exited && !g_wws_batch_gets,"rejected run stale counters");
    puts("PASS actual joined scheduler worker productivity and idle rounds");
}
int main(int argc,char** argv) {
    interpreted=argc>1 && !strcmp(argv[1],"--interpreted");
    vm_base=VirtualAlloc(NULL,0x50000000ull,MEM_RESERVE,PAGE_READWRITE);
    require(vm_base!=NULL,"guest allocation");
    require(VirtualAlloc(vm_base,ppu_vm_size,MEM_COMMIT,PAGE_READWRITE)!=NULL,"guest commit");
    /* Keep the retained unexpected-stop diagnostic readable, with authored zeros. */
    require(VirtualAlloc(vm_base+0x4023F000,0x1000,MEM_COMMIT,PAGE_READWRITE)!=NULL,"diagnostic page");
    /* Prime option caches sequentially; the test concerns run state, not options. */
    phase=2;atomic_store(&other_done,1);
    require(spu_run_policy_module(policy,79,image,sizeof image,0,3,0x1000,1)==0,"warm policy");
    paired(0);paired(1);
    joined_rounds();
    puts("PASS actual concurrent policy exit/poll/DMA isolation");
    printf("PASS actual %s kernel intercepts\n",interpreted?"interpreted":"compiled");
    return 0;
}
