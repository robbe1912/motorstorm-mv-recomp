/* Authored capture consumer and same-thread lock witnesses. Included before
 * the actual cellSpurs implementation; wrappers affect only that production TU. */
#include <assert.h>
#include <stdatomic.h>
#include "ps3emu/spurs_scheduler_observer.h"
#include "win32_compat.h"
#include "spu_coherency.h"
#if PS3_SPURS_SCHEDULER_OBSERVATION
static _Thread_local unsigned trace_held;
static void trace_acquire(SRWLOCK* lock) { AcquireSRWLockExclusive(lock);trace_held++; }
static void trace_release(SRWLOCK* lock) { assert(trace_held);trace_held--;ReleaseSRWLockExclusive(lock); }
static void trace_line_lock(void) { spu_lockline_lock();trace_held++; }
static void trace_line_unlock(void) { assert(trace_held);trace_held--;spu_lockline_unlock(); }
#define AcquireSRWLockExclusive trace_acquire
#define ReleaseSRWLockExclusive trace_release
#define spu_lockline_lock trace_line_lock
#define spu_lockline_unlock trace_line_unlock
static ps3_spurs_scheduler_event trace_records[16384];
static atomic_uint trace_count,trace_phase,trace_dropped;
static atomic_ullong trace_ticks;
static uint64_t trace_clock(void* user) {
    (void)user;assert(!trace_held && "scheduler callback under lock");
    return atomic_load(&trace_phase)==1 ? 0 : atomic_fetch_add(&trace_ticks,1)+1;
}
static int trace_accept(void* user,const ps3_spurs_scheduler_event* event) {
    (void)user;(void)event;assert(!trace_held && "scheduler callback under lock");
    return atomic_load(&trace_phase)!=2;
}
static void trace_observe(void* user,const ps3_spurs_scheduler_event* event) {
    (void)user;assert(!trace_held && "scheduler callback under lock");
    unsigned phase=atomic_load(&trace_phase);
    if (phase==1) {
        assert((event->flags&PS3_SPURS_CLOCK_INVALID) && "invalid scheduler clock hidden");return;
    }
    if (phase==3) {
        assert((event->flags&PS3_SPURS_IDENTITY_INVALID) && "exhausted identity hidden");
        if(event->kind>=PS3_SPURS_ADMITTED)assert(!event->info.dispatch && "dispatch identity wrapped");
        return;
    }
    assert(!(event->flags&(PS3_SPURS_CLOCK_INVALID|PS3_SPURS_IDENTITY_INVALID)));
    if (event->kind==PS3_SPURS_WORKER_BEGIN || event->kind==PS3_SPURS_WORKER_RETURN) {
        ps3_spurs_dispatch_info now={0};
        assert(ps3_spurs_current_dispatch(&now) && "worker assignment missing");
        assert(now.instance==event->info.instance && now.dispatch==event->info.dispatch);
    }
    unsigned index=atomic_fetch_add(&trace_count,1);
    if(index<sizeof(trace_records)/sizeof(trace_records[0]))trace_records[index]=*event;
    else atomic_fetch_add(&trace_dropped,1);
}
static const ps3_spurs_scheduler_observer trace_observer={0,trace_clock,trace_observe,trace_accept};
static void trace_setup(void) {
    ps3_spurs_scheduler_observer invalid={0};
    assert(!ps3_spurs_scheduler_observer_install(&invalid));
    assert(ps3_spurs_scheduler_observer_install(&trace_observer));
}
static void trace_check_context(spu_context* c) {
    ps3_spurs_dispatch_info info={0};
    uint32_t owner=spu_ls_read32(c,0x1C4);
    if(owner==0x11000 || owner==0x12000) { /* Authored direct-call instances. */
        info.dispatch=99;
        assert(!ps3_spurs_current_dispatch(&info) && info.dispatch==99);
        return;
    }
    assert(ps3_spurs_current_dispatch(&info) && "worker assignment missing");
    assert(info.instance_ea==spu_ls_read32(c,0x1C4) &&
           info.workload==spu_ls_read32(c,0x1DC) &&
           info.lane==spu_ls_read32(c,0x1C8) && "worker slot identity mismatch");
    assert(info.image==c->image_id && info.lane<info.nspus);
    if(atomic_load(&trace_phase)!=3)assert(info.instance && info.workload_generation && info.dispatch);
}
/* Run only after all real workers/coordinators have joined. The record array
 * is not a replacement for the production bounded recorder. */
static int trace_same(const ps3_spurs_dispatch_info* a,const ps3_spurs_dispatch_info* b) {
    return a->instance==b->instance && a->dispatch==b->dispatch;
}
static void trace_validate(void) {
    unsigned count=atomic_load(&trace_count),admitted=0,failed_return=0;
    assert(!atomic_load(&trace_dropped));
    for(unsigned i=0;i<count;i++) {
        const ps3_spurs_scheduler_event* event=&trace_records[i];
        assert(event->tick_begin && event->tick_end>=event->tick_begin);
        for(unsigned j=0;j<i;j++) {
            const ps3_spurs_scheduler_event* old=&trace_records[j];
            if(event->kind==PS3_SPURS_INSTANCE_RESERVED && old->kind==event->kind)
                assert(event->info.instance!=old->info.instance && "instance generation reused");
            if(event->kind==PS3_SPURS_WORKLOAD_ADDED && old->kind==event->kind &&
               event->info.instance==old->info.instance && event->info.workload==old->info.workload)
                assert(event->info.workload_generation!=old->info.workload_generation && "workload generation reused");
        }
    }
    /* Validate lifetime uniqueness before interpreting any dependent dispatch. */
    for(unsigned i=0;i<count;i++) {
        const ps3_spurs_scheduler_event* event=&trace_records[i];
        if(event->kind==PS3_SPURS_WORKER_RETURN && event->info.image==82) {
            assert(event->result==-2 && "policy return result changed");failed_return++;
        }
        if(event->kind!=PS3_SPURS_ADMITTED)continue;
        admitted++;
        assert((event->flags&(PS3_SPURS_TIME_INTERVAL|PS3_SPURS_SEQUENTIAL_SNAPSHOT))==
               (PS3_SPURS_TIME_INTERVAL|PS3_SPURS_SEQUENTIAL_SNAPSHOT));
        assert(event->active && event->active<=event->max_contention);
        unsigned claims=0,begins=0,ends=0,registered=0;
        uint64_t begin=0,end=0;
        for(unsigned j=0;j<count;j++) {
            const ps3_spurs_scheduler_event* peer=&trace_records[j];
            if(peer->kind==PS3_SPURS_WORKLOAD_ADDED && peer->info.instance==event->info.instance &&
               peer->info.workload==event->info.workload && peer->info.workload_generation==event->info.workload_generation)
                registered++;
            if(!trace_same(&event->info,&peer->info))continue;
            if(peer->kind>=PS3_SPURS_ADMITTED) {
                assert(peer->info.workload==event->info.workload &&
                       peer->info.workload_generation==event->info.workload_generation &&
                       peer->info.lane==event->info.lane && peer->info.image==event->info.image &&
                       peer->info.pm_ea==event->info.pm_ea && peer->info.pm_size==event->info.pm_size &&
                       peer->info.argument==event->info.argument && "dispatch assignment changed");
            }
            if(peer->kind==PS3_SPURS_ADMITTED)claims++;
            if(peer->kind==PS3_SPURS_WORKER_BEGIN){begins++;begin=peer->tick_end;}
            if(peer->kind==PS3_SPURS_WORKER_RETURN){ends++;end=peer->tick_end;}
        }
        assert(registered==1 && claims==1 && begins==1 && ends==1 && "dispatch lifecycle incomplete or reused");
        assert(event->tick_begin<=begin && begin<=end && "dispatch chronology invalid");
    }
    assert(admitted && "admission observations missing");
    assert(failed_return);
    /* Every worker observation must have an admission, not only vice versa. */
    for(unsigned i=0;i<count;i++) if(trace_records[i].kind>=PS3_SPURS_WORKER_BEGIN) {
        unsigned matches=0;
        for(unsigned j=0;j<count;j++)if(trace_records[j].kind==PS3_SPURS_ADMITTED &&
           trace_same(&trace_records[i].info,&trace_records[j].info))matches++;
        assert(matches==1 && "orphan worker observation");
    }
    ps3_spurs_dispatch_info untouched={0};untouched.dispatch=99;
    assert(!ps3_spurs_current_dispatch(&untouched) && untouched.dispatch==99);
    assert(!ps3_spurs_current_dispatch(0));
}
#else
static void trace_setup(void) {
    ps3_spurs_scheduler_observer value={0};
    assert(!ps3_spurs_scheduler_observer_install(&value));
    assert(ps3_spurs_scheduler_observer_install(0));
}
static void trace_check_context(spu_context* c) {
    ps3_spurs_dispatch_info info={0};info.dispatch=99;(void)c;
    assert(!ps3_spurs_current_dispatch(&info) && info.dispatch==99);
}
static void trace_validate(void) {}
#endif
