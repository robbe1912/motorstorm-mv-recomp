#include "ps3emu/spurs_scheduler_observer.h"
#include <string.h>
#if PS3_SPURS_SCHEDULER_OBSERVATION
static const ps3_spurs_scheduler_observer* observer;
static _Thread_local ps3_spurs_dispatch_info current;
static _Thread_local int active;
#endif
int ps3_spurs_scheduler_observer_install(const ps3_spurs_scheduler_observer* value) {
#if PS3_SPURS_SCHEDULER_OBSERVATION
    if (value && (!value->clock || !value->observe)) return 0;
    observer=value; return 1;
#else
    return value==0;
#endif
}
int ps3_spurs_current_dispatch(ps3_spurs_dispatch_info* out) {
#if PS3_SPURS_SCHEDULER_OBSERVATION
    if (!active || !out) return 0;
    *out=current; return 1;
#else
    (void)out; return 0;
#endif
}
#if PS3_SPURS_SCHEDULER_OBSERVATION
uint64_t ps3_spurs_scheduler_clock(void) {
    const ps3_spurs_scheduler_observer* value=observer;
    return value ? value->clock(value->user) : 0;
}
void ps3_spurs_scheduler_publish(const ps3_spurs_scheduler_event* input) {
    const ps3_spurs_scheduler_observer* value=observer;
    if (!value || !input || (value->accept && !value->accept(value->user,input))) return;
    ps3_spurs_scheduler_event event=*input;
    event.tick_end=value->clock(value->user);
    if (event.kind!=PS3_SPURS_ADMITTED) event.tick_begin=event.tick_end;
    if (!event.tick_begin || !event.tick_end || event.tick_end<event.tick_begin)
        event.flags|=PS3_SPURS_CLOCK_INVALID;
    if (!event.info.instance ||
        (event.kind>=PS3_SPURS_WORKLOAD_ADDED && !event.info.workload_generation) ||
        (event.kind>=PS3_SPURS_ADMITTED && !event.info.dispatch))
        event.flags|=PS3_SPURS_IDENTITY_INVALID;
    value->observe(value->user,&event);
}
void ps3_spurs_scheduler_worker_begin(const ps3_spurs_dispatch_info* info) {
    current=*info; active=1;
    ps3_spurs_scheduler_event event={0};
    event.info=current; event.kind=PS3_SPURS_WORKER_BEGIN;
    ps3_spurs_scheduler_publish(&event);
}
void ps3_spurs_scheduler_worker_return(int32_t result,uint64_t polls) {
    ps3_spurs_scheduler_event event={0};
    event.info=current; event.kind=PS3_SPURS_WORKER_RETURN;
    event.result=result; event.polls=polls;
    ps3_spurs_scheduler_publish(&event);
    active=0; memset(&current,0,sizeof(current));
}
#endif
