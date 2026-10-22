/* Authored IL/BI leaf called by BRSL, not an extracted program. */
#include "spu_interp.h"
#include "spu_native_leaf.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include <signal.h>
#ifdef BASELINE_ONLY
/* Link-only traps for new API paths absent from the hash-pinned original.
 * Its legacy-record driver never invokes either one. */
int spu_native_leaf_register(const spu_native_leaf* leaf) { (void)leaf;abort(); }
uint32_t spu_interp_run_until_budget(spu_context* c,uint32_t start,uint32_t stop,uint64_t budget) {
    (void)c;(void)start;(void)stop;(void)budget;abort();
}
#endif
#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
#include <xmmintrin.h>
typedef unsigned HostFP;
static HostFP get_fp(void) { return _mm_getcsr(); }
static void set_fp(HostFP s) { _mm_setcsr(s); }
static void mode_fp(HostFP s,unsigned mode) { set_fp((s&~0x6000u)|(mode<<13)|0x20u); }
static int same_fp(HostFP a,HostFP b) { return a==b; }
#elif defined(__aarch64__)
typedef struct { uint64_t control,status; } HostFP;
static HostFP get_fp(void) {
    HostFP s;
    __asm__ volatile("mrs %0, fpcr" : "=r"(s.control));
    __asm__ volatile("mrs %0, fpsr" : "=r"(s.status));
    return s;
}
static void set_fp(HostFP s) {
    __asm__ volatile("msr fpcr, %0" : : "r"(s.control) : "memory");
    __asm__ volatile("msr fpsr, %0" : : "r"(s.status) : "memory");
}
static void mode_fp(HostFP s,unsigned mode) {
    s.control=(s.control&~(3ull<<22))|((uint64_t)mode<<22);
    s.status|=1u<<4;set_fp(s);
}
static int same_fp(HostFP a,HostFP b) { return a.control==b.control && a.status==b.status; }
#else
#error Host FP verification needs x86 or AArch64
#endif
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <pthread.h>
#endif

u128 spu_rdch(spu_context* c,uint32_t ch) { (void)c;(void)ch;abort(); }
void spu_wrch(spu_context* c,uint32_t ch,u128 v) { (void)c;(void)ch;(void)v;abort(); }
uint32_t spu_rchcnt(spu_context* c,uint32_t ch) { (void)c;(void)ch;abort(); }
void spu_spurs_taskset_syscall(spu_context* c) { (void)c;abort(); }
void spu_trace_pc(spu_context* c,uint32_t pc) { (void)c;(void)pc;abort(); }
spu_lifted_fn spu_lifted_lookup(const spu_context* c,uint32_t pc) { (void)c;(void)pc;return NULL; }
void spu_indirect_branch(spu_context* c) { (void)c;abort(); }
int spu_pm_recoverable_bail(spu_context* c,uint32_t site,int service) { (void)c;(void)site;(void)service;abort(); }
/* Authored programs cannot reach these channel/dispatch/memory-write paths.
 * Link the real interrupt implementation; unexpected broader runtime work is
 * fatal rather than replaced by a successful stub. */
int spu_walkin_lift(uint32_t pc,int image,int relative) { (void)pc;(void)image;(void)relative;abort(); }
volatile unsigned g_spu_iret_bails;
void spu_pm_fill_note(spu_context* c,uint32_t lsa,const void* bytes,const char* src) {
    (void)c;(void)lsa;(void)bytes;(void)src;abort();
}
void spu_lockline_lock(void) { abort(); }
void spu_lockline_unlock(void) { abort(); }
void spu_coh_notify_write(uint32_t ea) { (void)ea;abort(); }
void spu_check_stack_reset(spu_context* c,void (*fn)(spu_context*)) { (void)c;(void)fn;abort(); }
void spu_halt(spu_context* c) { (void)c;abort(); }
void spu_restart_dispatch(spu_context* c) { (void)c;abort(); }
void yz_lockstep_tick(spu_context* c) { (void)c;abort(); }
void (*spu_lookup(uint32_t address,int image))(spu_context*) { (void)address;(void)image;abort(); }
uint8_t* vm_base;
int g_spu_ls_watch_n,g_spu_ls_probe,g_wws_read_probe,g_wws_code_probe,g_spu_smc_watch,g_spu_ls_dbg;
void spu_ls_watch_slow(uint32_t a,int w,const uint8_t* p,uint32_t pc,uint32_t lr) {
    (void)a;(void)w;(void)p;(void)pc;(void)lr;abort();
}
static atomic_int enabled,calls;
static int bad,nested,options;
static uint8_t shared_ls[0x40000];
static void require(int ok,const char* why) {
    if (!ok) { fprintf(stderr,"FAIL %s\n",why); exit(1); }
}
static void be32(uint8_t* p,uint32_t w) {
    p[0]=(uint8_t)(w>>24);p[1]=(uint8_t)(w>>16);p[2]=(uint8_t)(w>>8);p[3]=(uint8_t)w;
}
static uint32_t word(const uint8_t* p) {
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static spu_context* program(unsigned value) {
    spu_context* c=(spu_context*)calloc(1,sizeof(*c)); require(c!=NULL,"allocation");
    c->ls=c->ls_store;c->image_id=0;
    for (unsigned r=0;r<128;r++) for(unsigned lane=0;lane<4;lane++)
        c->gpr[r]._u32[lane]=0x12345678u+17*r+lane;
    be32(c->ls+0x100,0x33002000u); /* BRSL r0,+0x100 */
    be32(c->ls+0x104,0x00002000u); /* STOP 0x2000 */
    be32(c->ls+0x200,0x40800003u|(value<<7)); /* IL r3,value */
    be32(c->ls+0x204,0x35000000u); /* BI r0 */
    if (options&1) c->list_stall_mask=1;
    if (options&2) { c->int_enable=1;c->event_status=c->event_mask=2; }
    if (options&4) { memcpy(shared_ls,c->ls,0x40000);c->ls=shared_ls; }
    if (options&8) be32(c->ls+0x204,0x00002001u);
    if (options&16) c->image_id=-1;
    if (options&64) {
        be32(c->ls+0x100,0x33000000u|(0xffc0u<<7));
        be32(c->ls,0x40800003u|(value<<7));be32(c->ls+4,0x35000000u);
    }
    if (options&32) {
        c->int_enable=1;c->event_status=c->event_mask=2;
        be32(c->ls,0x30000000u|((0x300u/4)<<7)); /* BRA interrupt vector */
        be32(c->ls+0x300,0x00002002u); /* authored handler STOP */
    }
    return c;
}
static void execute(spu_context* c,const spu_native_leaf_plan* plan) {
    atomic_fetch_add(&calls,1);
    if (nested) {
        int before=atomic_load(&calls);
        spu_context* inner=program(42);
        require(spu_interp_run(inner,0x100)==0x2000,"nested real interpreter");
        require(atomic_load(&calls)==before,"nested native execution declined");free(inner);
    }
    for(unsigned lane=0;lane<4;lane++) c->gpr[3]._u32[lane]=42;
    c->pc=plan->resume_pc+(bad==1 ? 4 : 0);
    if (bad==3) g_spu_trampoline_fn=NULL;
}
static int prepare(const spu_context* c,uint64_t remaining,spu_native_leaf_plan* plan) {
    (void)remaining; /* runtime must also enforce a too-large returned plan */
    if (!atomic_load(&enabled) || word(c->ls+c->pc)!=(0x40800003u|(42u<<7)) ||
        word(c->ls+c->pc+4)!=0x35000000u) return 0;
    plan->instructions=bad==2 ? 0 : 2;plan->last_pc=c->pc+4;
    plan->resume_pc=c->gpr[0]._u32[0]&0x3fffcu;plan->execute=execute;
    return 1;
}
static int also_prepare(const spu_context* c,uint64_t r,spu_native_leaf_plan* p) {
    if(c->pc!=0x200) return 0; /* distinct accepting guard, including under ICF */
    return prepare(c,r,p);
}
static void compare(unsigned value,uint32_t stop,uint64_t budget,int expected_calls) {
    spu_context* ref=program(value),*actual=program(value);
    HostFP csr=get_fp();
    void (*queued)(spu_context*)=g_spu_trampoline_fn;
    g_spu_interp_budget_hit=0;
    atomic_store(&enabled,0);
    uint32_t result=spu_interp_run_until_budget(ref,0x100,stop,budget);
    uint64_t steps=g_spu_interp_steps;uint32_t last=g_spu_interp_last_pc;
    int hit=g_spu_interp_budget_hit;g_spu_interp_budget_hit=0;
    atomic_store(&enabled,1);int before=atomic_load(&calls);
    uint32_t got=spu_interp_run_until_budget(actual,0x100,stop,budget);
    require(atomic_load(&calls)-before==expected_calls,"real host execution count");
    require(got==result && g_spu_interp_steps==steps && g_spu_interp_last_pc==last,"stop/budget/count/last-PC parity");
    require(g_spu_interp_budget_hit==hit,"legacy ceiling report parity");
    require(g_spu_trampoline_fn==queued,"caller TLS queue");
    if (options&32) require(got==0x2002 && actual->irq_saved && actual->srr0==0x100 && !actual->int_enable,"real pending interrupt delivery");
    actual->ls=ref->ls;
    require(!memcmp(actual,ref,sizeof(*ref)),"complete context/memory parity");
    require(same_fp(get_fp(),csr),"caller FP state");free(ref);free(actual);
}
#ifdef _WIN32
static DWORD WINAPI worker(void* unused) {
#else
static void* worker(void* unused) {
#endif
    (void)unused;
    for(unsigned i=0;i<100;i++) {
        spu_context* c=program(42);
        require(spu_interp_run(c,0x100)==0x2000,"worker stop");
        require(g_spu_interp_steps==4 && c->gpr[3]._u32[0]==42,"worker state/steps");free(c);
    }
    return 0;
}
static void aborted(int sig) { (void)sig; _Exit(86); }
static void forbidden_continuation(spu_context* c) { (void)c;abort(); }
static int legacy_record(void) {
#ifdef _WIN32
    require(_setmode(_fileno(stdout),_O_BINARY)!=-1,"binary record mode");
#endif
    g_spu_trampoline_fn=NULL;
    for(unsigned rounding=0;rounding<4;rounding++) {
        HostFP saved=get_fp();mode_fp(saved,rounding);
        for(options=0;options<=32;options+=32) for(unsigned ceiling=0;ceiling<=6;ceiling++) {
            spu_context* c=program(42);g_spu_interp_budget=ceiling;g_spu_interp_budget_hit=0;
            uint32_t result=spu_interp_run_until(c,0x100,0);
            uint64_t telemetry[]={sizeof(*c),result,g_spu_interp_steps,g_spu_interp_last_pc,(uint64_t)g_spu_interp_budget_hit};
            HostFP fp=get_fp();c->ls=NULL; /* only allocation identity differs between processes */
            require(fwrite(telemetry,sizeof(telemetry),1,stdout)==1 &&
                    fwrite(&fp,sizeof(fp),1,stdout)==1 && fwrite(c,sizeof(*c),1,stdout)==1,"legacy record write");
            free(c);
        }
        set_fp(saved);
    }
    require(!fflush(stdout),"legacy record flush");return 0;
}
int main(int argc,char** argv) {
    signal(SIGABRT,aborted);
    const char* mode=argc>1 ? argv[1] : "normal";
    if (!strcmp(mode,"legacy-record")) return legacy_record();
    g_spu_trampoline_fn=forbidden_continuation;
    if (!strcmp(mode,"empty")) { compare(42,0,0,0);puts("PASS empty registry unchanged");return 0; }
    spu_native_leaf leaf={0x200,0x208,prepare};
    require(spu_native_leaf_register(NULL)==-1,"invalid registration");
    require(spu_native_leaf_register(&leaf)==0,"registration");
    require(spu_native_leaf_register(&leaf)==-1,"duplicate registration");
    spu_native_leaf zero={0,8,prepare};require(!spu_native_leaf_register(&zero),"zero entry registration");
    if (!strcmp(mode,"ambiguous")) {
        leaf.prepare=also_prepare;require(!spu_native_leaf_register(&leaf),"second guard");
    }
    if (!strcmp(mode,"bad")) bad=1;
    if (!strcmp(mode,"plan")) bad=2;
    if (!strcmp(mode,"tls")) { bad=3;compare(42,0,0,1);require(0,"TLS oracle missed faulty callback"); }
    if (bad || !strcmp(mode,"ambiguous")) {
        atomic_store(&enabled,1);spu_context* c=program(42);spu_interp_run(c,0x100);
        require(0,"invalid execution was accepted");
    }
    if (!strcmp(mode,"instrumented")) { compare(42,0,0,0); puts("PASS instrumented stream retained");return 0; }
    for(unsigned rounding=0;rounding<4;rounding++) {
        HostFP saved=get_fp();mode_fp(saved,rounding);
        compare(42,0,0,1);compare(43,0,0,0);
        compare(42,0x200,0,0);compare(42,0x204,0,0);compare(42,0x104,0,1);
        for(unsigned limit=1;limit<=5;limit++) compare(42,0,limit,limit>=3 ? 1 : 0);
        set_fp(saved);
    }
    nested=1;compare(42,0,0,1);nested=0;
    for (unsigned ceiling=1;ceiling<=6;ceiling++) {
        g_spu_interp_budget=ceiling;compare(42,0,0,ceiling>=4 ? 1 : 0);
        for(unsigned local=1;local<=5;local++) compare(42,0,local,ceiling>=4 && local>=3 ? 1 : 0);
    }
    g_spu_interp_budget=0;
    g_spu_ls_watch_n=1;compare(42,0,0,0);g_spu_ls_watch_n=0;
    for(options=1;options<=8;options*=2) compare(42,0,0,0);
    options=16;compare(42,0,0,1);compare(43,0,0,0);
    options=32;compare(42,0,0,0);
    options=64;compare(42,0,0,1);compare(43,0,0,0);
    options=0;
    spu_context* c=program(42);c->int_enable=1;c->event_mask=c->event_status=2;
    int before=atomic_load(&calls);spu_interp_run(c,0x100);
    require(atomic_load(&calls)==before && c->event_status==2,"pending event retained");free(c);
    require(spu_native_leaf_register(&leaf)==-1,"frozen registry");
    before=atomic_load(&calls);
#ifdef _WIN32
    HANDLE threads[4];
    for(unsigned i=0;i<4;i++) { threads[i]=CreateThread(NULL,0,worker,NULL,0,NULL);require(threads[i]!=NULL,"thread create"); }
    require(WaitForMultipleObjects(4,threads,TRUE,10000)==WAIT_OBJECT_0,"thread join");
    for(unsigned i=0;i<4;i++) CloseHandle(threads[i]);
#else
    pthread_t threads[4];
    for(unsigned i=0;i<4;i++) require(!pthread_create(&threads[i],NULL,worker,NULL),"thread create");
    for(unsigned i=0;i<4;i++) require(!pthread_join(threads[i],NULL),"thread join");
#endif
    require(atomic_load(&calls)-before==400,"all workers executed real replacements");
    puts("PASS actual interpreter native leaves: complete state, guards, stops, budgets, nesting, events, FP and workers");return 0;
}
