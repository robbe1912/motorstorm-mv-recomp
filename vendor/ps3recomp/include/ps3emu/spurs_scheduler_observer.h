#ifndef PS3EMU_SPURS_SCHEDULER_OBSERVER_H
#define PS3EMU_SPURS_SCHEDULER_OBSERVER_H
#include <stdint.h>
#ifndef PS3_SPURS_SCHEDULER_OBSERVATION
#define PS3_SPURS_SCHEDULER_OBSERVATION 0
#endif
#ifdef __cplusplus
extern "C" {
#endif
enum {
    PS3_SPURS_INSTANCE_RESERVED=1, PS3_SPURS_INSTANCE_RESULT,
    PS3_SPURS_INSTANCE_CLOSED, PS3_SPURS_WORKLOAD_ADDED,
    PS3_SPURS_WORKLOAD_REMOVED, PS3_SPURS_ADMITTED,
    PS3_SPURS_WORKER_BEGIN, PS3_SPURS_WORKER_RETURN
};
enum {
    PS3_SPURS_CLOCK_INVALID=1, PS3_SPURS_IDENTITY_INVALID=2,
    PS3_SPURS_TIME_INTERVAL=4, PS3_SPURS_SEQUENTIAL_SNAPSHOT=8
};
typedef struct ps3_spurs_dispatch_info {
    uint64_t instance, workload_generation, dispatch, argument;
    uint32_t instance_ea, workload, lane, pm_ea, pm_size, nspus;
    int32_t image;
} ps3_spurs_dispatch_info;
typedef struct ps3_spurs_scheduler_event {
    ps3_spurs_dispatch_info info;
    uint64_t tick_begin, tick_end, polls;
    uint32_t kind, flags, ready, signal, active, max_contention;
    int32_t result;
} ps3_spurs_scheduler_event;
typedef struct ps3_spurs_scheduler_observer {
    void* user;
    uint64_t (*clock)(void*);
    void (*observe)(void*,const ps3_spurs_scheduler_event*);
    int (*accept)(void*,const ps3_spurs_scheduler_event*);
} ps3_spurs_scheduler_observer;
/* Install/clear only with all producers quiescent and synchronized before
 * resuming. Retain immutable observer/user; report setup rejection. Callbacks
 * are concurrent and run outside scheduler/registry/coherence locks. They must
 * return normally without guest/runtime mutation, reentry, allocation, I/O,
 * formatting or application locks. NULL accept admits every event. Event
 * pointers are valid only during the callback; copy values for retention.
 *
 * ADMITTED bounds publication between a clock sampled before acquiring the
 * pass's instance lock and one after release. Several slots share a pass.
 * Delivery may follow WORKER_BEGIN: never substitute delivery order or interval
 * endpoints for an exact commit instant / OS ready delay. Demand fields are
 * sequential observations, NOT job eligibility or a consumed dispatch token.
 * Lifecycle samples are after the observed operation; RESERVED is not success.
 * Failed init has INSTANCE_RESULT, but is not a live instance needing CLOSED.
 * Instance closure also retires remaining workloads without per-workload events.
 *
 * IDs never wrap: exhaustion yields zero, flagged invalid. IDs are process-local
 * and require a capture run identity. Policy dispatch/return can span many jobs
 * or no productive jobs. Neither a policy return nor contention is completion.
 * Filtering/missing lifecycle records remain coverage gaps. Admission-window
 * begin clocks are sampled once per pass even if all events are later filtered.
 */
int ps3_spurs_scheduler_observer_install(const ps3_spurs_scheduler_observer*);
/* Copy this thread's active HOST worker assignment, or return 0 without writing
 * out. This does not prove that an arbitrary SPU context belongs to that
 * assignment; nested/direct policy calls still require original job binding. */
int ps3_spurs_current_dispatch(ps3_spurs_dispatch_info* out);
#if PS3_SPURS_SCHEDULER_OBSERVATION
uint64_t ps3_spurs_scheduler_clock(void);
void ps3_spurs_scheduler_publish(const ps3_spurs_scheduler_event*);
void ps3_spurs_scheduler_worker_begin(const ps3_spurs_dispatch_info*);
void ps3_spurs_scheduler_worker_return(int32_t result,uint64_t polls);
#endif
#ifdef __cplusplus
}
#endif
#endif
