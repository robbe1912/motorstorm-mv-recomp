#include "../../src/motorstorm/job_capture.h"
#include <atomic>
#include <cassert>
#include <cstring>
#include <thread>

static const ps3_atomic_observer *ppu, *spu;
static const ps3_spu_execution_observer* execution;
static const ps3_spurs_scheduler_observer* scheduler;
static int fail_at, install_call;
static thread_local uint64_t assignment;
extern "C" int ps3_spurs_current_dispatch(ps3_spurs_dispatch_info* out) {
    if (!assignment) return 0;
    *out = {}; out->dispatch = assignment; return 1;
}
static bool reject(const void* p) { return p && ++install_call == fail_at; }
extern "C" int ps3_atomic_observer_install_ppu(const ps3_atomic_observer* p) {
    if (reject(p)) return 0;
    ppu = p; return 1;
}
extern "C" int ps3_atomic_observer_install_spu(const ps3_atomic_observer* p) {
    if (reject(p)) return 0;
    spu = p; return 1;
}
extern "C" int ps3_spu_execution_observer_install(const ps3_spu_execution_observer* p) {
    if (reject(p)) return 0;
    execution = p; return 1;
}
extern "C" int ps3_spurs_scheduler_observer_install(const ps3_spurs_scheduler_observer* p) {
    if (reject(p)) return 0;
    scheduler = p; return 1;
}
static std::atomic<uint64_t> ticks{1};
static thread_local uint64_t tid = 11;
static uint64_t clock_now(void*) { return ticks.fetch_add(1); }
static uint64_t thread_now(void*) { return tid; }
static int visit(void* user, uint64_t index, const job_capture_record*) {
    auto* count = static_cast<unsigned*>(user);
    assert(index == *count); ++*count; return *count < 7;
}

static void produce(unsigned id) {
    tid = id + 1;
    assignment = id + 101;
    for (unsigned n = 0; n < 1000; ++n) {
        ps3_atomic_observation e{};
        e.context = id + 1; e.size = 128; e.address = n;
        for (unsigned j = 0; j < 128; ++j) {
            e.before[j] = static_cast<uint8_t>(id + n + j);
            e.after[j] = static_cast<uint8_t>(~e.before[j]);
        }
        const auto* o = (id & 1) ? spu : ppu;
        o->observe(o->user, &e);
    }
}
int main() {
    job_capture_config config{7, 10000000, 4004, nullptr, clock_now, thread_now};
    assert(!job_capture_start(nullptr));
    for (int fail = 1; fail <= 4; ++fail) {
        fail_at = fail; install_call = 0;
        assert(!job_capture_start(&config));
        assert(!ppu && !spu && !execution && !scheduler);
    }
    fail_at = 0; install_call = 0;
    auto* capture = job_capture_start(&config); assert(capture);
    assert(!job_capture_start(&config));
    ps3_spu_execution_event e{}; e.context = 123; e.kind = PS3_SPU_NATIVE_BEGIN;
    execution->observe(execution->user, &e);
    ps3_spurs_scheduler_event s{}; s.info.instance = 5; s.kind = PS3_SPURS_WORKER_BEGIN;
    scheduler->observe(scheduler->user, &s);
    tid = 0; ps3_atomic_observation empty{}; ppu->observe(ppu->user, &empty);
    std::thread threads[4];
    for (unsigned i = 0; i < 4; ++i) threads[i] = std::thread(produce, i);
    for (auto& t : threads) t.join();
    job_capture_info info{}; assert(job_capture_describe(capture, &info));
    assert(info.run_id == 7 && info.ticks_per_second == 10000000);
    assert(info.schema_version == JOB_CAPTURE_SCHEMA_VERSION && info.record_size == sizeof(job_capture_record) && info.pointer_size == sizeof(uintptr_t));
    assert(info.storage.attempted == 4003 && info.storage.dropped == 0);
    job_capture_record r{};
    assert(job_capture_read(capture, 0, &r) == 1 && r.kind == JOB_CAPTURE_EXECUTION && r.value.execution.context == 123);
    assert(job_capture_read(capture, 1, &r) == 1 && r.kind == JOB_CAPTURE_SCHEDULER && r.value.scheduler.info.instance == 5);
    assert(job_capture_read(capture, 2, &r) == 1 && r.flags == JOB_CAPTURE_THREAD_UNKNOWN);
    unsigned seen[4]{};
    for (unsigned i = 3; i < 4003; ++i) {
        assert(job_capture_read(capture, i, &r) == 1 && r.kind == JOB_CAPTURE_ATOMIC);
        assert(r.thread >= 1 && r.thread <= 4 && r.value.atomic.context == r.thread);
        assert((r.flags & JOB_CAPTURE_HOST_ASSIGNMENT) && r.host_assignment.dispatch == r.thread + 100);
        ++seen[r.thread - 1];
        for (unsigned j = 0; j < 128; ++j)
            assert(r.value.atomic.after[j] == static_cast<uint8_t>(~r.value.atomic.before[j]));
    }
    for (auto n : seen) assert(n == 1000);
    assert(job_capture_read(capture, 4003, &r) == 0);
    unsigned visited = 0; job_capture_snapshot snapshot{};
    assert(job_capture_visit(capture, visit, &visited, &snapshot));
    assert(visited == 7 && snapshot.consumer_failed && snapshot.examined == 7 && snapshot.delivered == 6);
    assert(snapshot.before.storage.attempted == 4003 && snapshot.after.storage.attempted == 4003);
    ps3_atomic_observation a{}; ppu->observe(ppu->user, &a); ppu->observe(ppu->user, &a);
    assert(job_capture_describe(capture, &info) && info.storage.attempted == 4005 && info.storage.dropped == 1);
    job_capture_stop(capture);
    assert(!ppu && !spu && !execution && !scheduler);
    return 0;
}
