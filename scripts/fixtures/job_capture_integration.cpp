#include "../../src/motorstorm/job_capture.h"
#include "../../vendor/ps3recomp/runtime/spu/spu_context.h"
#include <cassert>

static const ps3_atomic_observer *ppu, *spu;
extern "C" int ps3_atomic_observer_install_ppu(const ps3_atomic_observer* p) { ppu = p; return 1; }
extern "C" int ps3_atomic_observer_install_spu(const ps3_atomic_observer* p) { spu = p; return 1; }
static uint64_t tick(void*) { static uint64_t value = 10; return ++value; }
static uint64_t thread(void*) { return 42; }
static spu_context context;
int main() {
    job_capture_config cfg{9, 1000, 8, nullptr, tick, thread};
    auto* c = job_capture_start(&cfg); assert(c && ppu && spu);
    ps3_spurs_dispatch_info info{};
    info.instance = 1; info.workload_generation = 2; info.dispatch = 3;
    ps3_spurs_scheduler_worker_begin(&info);
    ps3_spu_execution_notify(PS3_SPU_NATIVE_BEGIN, &context, 0x10, 0x20, 7, 0, 0);
    ps3_spurs_scheduler_worker_return(0, 4);
    ps3_spu_execution_notify(PS3_SPU_NATIVE_END, &context, 0x20, 0x30, 8, 0, 0);
    job_capture_record r{};
    assert(job_capture_read(c, 0, &r) == 1 && r.kind == JOB_CAPTURE_SCHEDULER);
    assert((r.flags & JOB_CAPTURE_HOST_ASSIGNMENT) && r.host_assignment.dispatch == 3);
    assert(job_capture_read(c, 1, &r) == 1 && r.kind == JOB_CAPTURE_EXECUTION);
    assert((r.flags & JOB_CAPTURE_HOST_ASSIGNMENT) && r.host_assignment.dispatch == 3 && r.value.execution.target_pc == 0x20);
    assert(job_capture_read(c, 2, &r) == 1 && r.kind == JOB_CAPTURE_SCHEDULER && r.value.scheduler.polls == 4);
    assert(job_capture_read(c, 3, &r) == 1 && r.kind == JOB_CAPTURE_EXECUTION && !(r.flags & JOB_CAPTURE_HOST_ASSIGNMENT));
    job_capture_stop(c);
    assert(!ppu && !spu);
    return 0;
}
