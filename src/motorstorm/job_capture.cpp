#include "job_capture.h"
#include <atomic>
#include <new>

struct job_capture {
    job_capture_config config;
    ps3_sized_trace* trace;
    ps3_atomic_observer atomic;
    ps3_spu_execution_observer execution;
    ps3_spurs_scheduler_observer scheduler;
    std::atomic<uint64_t> unexpected_failures;
    std::atomic<uint64_t> excluded_atomic, excluded_execution, excluded_scheduler;
};
/* Setup/teardown are serialized while producers are quiescent. */
static job_capture* active;

static uint64_t clock_now(void* p) {
    auto* c = static_cast<job_capture*>(p);
    return c->config.clock(c->config.user);
}
static void increment(std::atomic<uint64_t>& counter) {
    uint64_t previous = counter.load(std::memory_order_relaxed);
    while (previous != UINT64_MAX && !counter.compare_exchange_weak(
            previous, previous + 1, std::memory_order_relaxed)) {}
}
static int accept_atomic(void* p, uint32_t source, uintptr_t context, uint64_t address, uint32_t size) {
    auto* c = static_cast<job_capture*>(p);
    if (!c->config.accept_atomic || c->config.accept_atomic(c->config.user, source, context, address, size)) return 1;
    increment(c->excluded_atomic); return 0;
}
static int accept_execution(void* p, uint32_t kind, uintptr_t context, uint32_t source, uint32_t target) {
    auto* c = static_cast<job_capture*>(p);
    if (!c->config.accept_execution || c->config.accept_execution(c->config.user, kind, context, source, target)) return 1;
    increment(c->excluded_execution); return 0;
}
static int accept_scheduler(void* p, const ps3_spurs_scheduler_event* event) {
    auto* c = static_cast<job_capture*>(p);
    if (!c->config.accept_scheduler || c->config.accept_scheduler(c->config.user, event)) return 1;
    increment(c->excluded_scheduler); return 0;
}
static job_capture_record record_for(job_capture* c, uint32_t kind) {
    job_capture_record r{};
    r.thread = c->config.thread_id(c->config.user);
    r.flags = r.thread ? 0 : JOB_CAPTURE_THREAD_UNKNOWN;
    if (ps3_spurs_current_dispatch(&r.host_assignment)) r.flags |= JOB_CAPTURE_HOST_ASSIGNMENT;
    r.kind = kind;
    return r;
}
static void append(job_capture* c, const job_capture_record& r) {
    int result = ps3_sized_trace_append(c->trace, &r, sizeof(r));
    if (result == PS3_SIZED_TRACE_RECORDED || result == PS3_SIZED_TRACE_FULL) return;
    increment(c->unexpected_failures);
}
static void atomic_event(void* p, const ps3_atomic_observation* e) {
    auto* c = static_cast<job_capture*>(p);
    auto r = record_for(c, JOB_CAPTURE_ATOMIC);
    r.value.atomic = *e;
    append(c, r);
}
static void execution_event(void* p, const ps3_spu_execution_event* e) {
    auto* c = static_cast<job_capture*>(p);
    auto r = record_for(c, JOB_CAPTURE_EXECUTION);
    r.value.execution = *e;
    append(c, r);
}
static void scheduler_event(void* p, const ps3_spurs_scheduler_event* e) {
    auto* c = static_cast<job_capture*>(p);
    auto r = record_for(c, JOB_CAPTURE_SCHEDULER);
    r.value.scheduler = *e;
    append(c, r);
}
job_capture* job_capture_start(const job_capture_config* config) {
    if (active || !config || !config->run_id || !config->ticks_per_second ||
        !config->clock || !config->thread_id) return nullptr;
    auto* c = new (std::nothrow) job_capture{};
    if (!c) return nullptr;
    c->unexpected_failures.store(0, std::memory_order_relaxed);
    c->excluded_atomic.store(0, std::memory_order_relaxed);
    c->excluded_execution.store(0, std::memory_order_relaxed);
    c->excluded_scheduler.store(0, std::memory_order_relaxed);
    if (!c->unexpected_failures.is_lock_free() || !c->excluded_atomic.is_lock_free() ||
        !c->excluded_execution.is_lock_free() || !c->excluded_scheduler.is_lock_free()) { delete c; return nullptr; }
    c->config = *config;
    c->trace = ps3_sized_trace_create(config->capacity, sizeof(job_capture_record));
    if (!c->trace) { delete c; return nullptr; }
    c->atomic = {c, clock_now, atomic_event, accept_atomic};
    c->execution = {c, clock_now, execution_event, accept_execution};
    c->scheduler = {c, clock_now, scheduler_event, accept_scheduler};
    if (!ps3_atomic_observer_install_ppu(&c->atomic)) goto fail;
    if (!ps3_atomic_observer_install_spu(&c->atomic)) goto clear_ppu;
    if (!ps3_spu_execution_observer_install(&c->execution)) goto clear_spu;
    if (!ps3_spurs_scheduler_observer_install(&c->scheduler)) goto clear_execution;
    active = c;
    return c;
clear_execution:
    (void)ps3_spu_execution_observer_install(nullptr);
clear_spu:
    (void)ps3_atomic_observer_install_spu(nullptr);
clear_ppu:
    (void)ps3_atomic_observer_install_ppu(nullptr);
fail:
    ps3_sized_trace_destroy(c->trace);
    delete c;
    return nullptr;
}
int job_capture_describe(const job_capture* c, job_capture_info* out) {
    if (!c || !out) return 0;
    job_capture_info info{};
    info.run_id = c->config.run_id;
    info.ticks_per_second = c->config.ticks_per_second;
    info.unexpected_append_failures = c->unexpected_failures.load(std::memory_order_relaxed);
    info.excluded_atomic = c->excluded_atomic.load(std::memory_order_relaxed);
    info.excluded_execution = c->excluded_execution.load(std::memory_order_relaxed);
    info.excluded_scheduler = c->excluded_scheduler.load(std::memory_order_relaxed);
    info.filter_mask = (c->config.accept_atomic ? uint32_t(JOB_CAPTURE_FILTER_ATOMIC) : 0u) |
        (c->config.accept_execution ? uint32_t(JOB_CAPTURE_FILTER_EXECUTION) : 0u) |
        (c->config.accept_scheduler ? uint32_t(JOB_CAPTURE_FILTER_SCHEDULER) : 0u);
    info.schema_version = JOB_CAPTURE_SCHEMA_VERSION;
    info.record_size = sizeof(job_capture_record);
    info.pointer_size = sizeof(uintptr_t);
    if (!ps3_sized_trace_describe(c->trace, &info.storage)) return 0;
    *out = info;
    return 1;
}
int job_capture_read(const job_capture* c, uint64_t index, job_capture_record* out) {
    return c ? ps3_sized_trace_read(c->trace, index, out, sizeof(*out)) : -1;
}
int job_capture_visit(const job_capture* c, int (*consumer)(void*, uint64_t,
                      const job_capture_record*), void* user, job_capture_snapshot* out) {
    if (!c || !consumer || !out) return 0;
    job_capture_snapshot snapshot{};
    if (!job_capture_describe(c, &snapshot.before)) return 0;
    uint64_t limit = snapshot.before.storage.attempted;
    if (limit > snapshot.before.storage.capacity) limit = snapshot.before.storage.capacity;
    for (uint64_t i = 0; i < limit; ++i) {
        job_capture_record record{};
        int status = job_capture_read(c, i, &record);
        if (status < 0) return 0;
        ++snapshot.examined;
        if (!status) { ++snapshot.pending; continue; }
        if (!consumer(user, i, &record)) { snapshot.consumer_failed = 1; break; }
        ++snapshot.delivered;
    }
    if (!job_capture_describe(c, &snapshot.after)) return 0;
    *out = snapshot;
    return 1;
}
void job_capture_stop(job_capture* c) {
    if (!c || c != active) return;
    (void)ps3_spurs_scheduler_observer_install(nullptr);
    (void)ps3_spu_execution_observer_install(nullptr);
    (void)ps3_atomic_observer_install_spu(nullptr);
    (void)ps3_atomic_observer_install_ppu(nullptr);
    active = nullptr;
    ps3_sized_trace_destroy(c->trace);
    delete c;
}
