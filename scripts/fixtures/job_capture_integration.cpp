#include "../../src/motorstorm/job_capture.h"
#include "job_capture_window.h"
#include "../../src/motorstorm/job_capture_snapshot.h"
#include "../../vendor/ps3recomp/runtime/spu/spu_context.h"
#include "ppu_recomp.h"
#include <cassert>

static const ps3_atomic_observer *ppu, *spu;
extern "C" int ps3_atomic_observer_install_ppu(const ps3_atomic_observer* p) { ppu = p; return 1; }
extern "C" int ps3_atomic_observer_install_spu(const ps3_atomic_observer* p) { spu = p; return 1; }
static uint64_t tick(void*) { static uint64_t value = 10; return ++value; }
static uint64_t thread(void*) { return 42; }
static int only_target(void*, uint32_t, uintptr_t, uint32_t, uint32_t target) { return target == 0x30; }
static int reject_initialization(void*, const job_queue_event* event) {
    return event->operation != job_queue_operation::init;
}
static int no_scheduler(void*, const ps3_spurs_scheduler_event*) { return 0; }
static spu_context context;
void game_original_queue_reset_multi(ppu_context* ctx) { ++ctx->gpr[3]; }
void game_original_queue_reset(ppu_context* c) { ++c->gpr[3]; }
void game_original_queue_init(ppu_context* c) { ++c->gpr[4]; }
void game_original_add_job(ppu_context*) {}
void motorstorm_observe_queue_reset(ppu_context*);
void motorstorm_observe_queue_reset_multi(ppu_context*);
void motorstorm_observe_queue_init(ppu_context*);
void motorstorm_observe_add_job(ppu_context*);
static int count_queue(void* user, uint64_t, const job_capture_record* r) {
    if (r->kind == JOB_CAPTURE_QUEUE_CALL) {
        ++*static_cast<unsigned*>(user);
        if (r->value.queue_call.event.operation == job_queue_operation::add_job)
            assert(r->value.queue_call.event.header == 0x123456789abcdef0ULL);
    }
    return 1;
}
int main() {
    job_capture_config cfg{9, 1000, 8, nullptr, tick, thread, nullptr, nullptr, nullptr, nullptr};
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
    cfg.accept_execution = only_target; cfg.accept_scheduler = no_scheduler;
    c = job_capture_start(&cfg); assert(c);
    ps3_spurs_scheduler_worker_begin(&info);
    ps3_spu_execution_notify(PS3_SPU_NATIVE_BEGIN, &context, 0x10, 0x20, 7, 0, 0);
    ps3_spu_execution_notify(PS3_SPU_NATIVE_END, &context, 0x20, 0x30, 8, 0, 0);
    ps3_spurs_scheduler_worker_return(0, 4);
    job_capture_info metadata{}; assert(job_capture_describe(c, &metadata));
    assert(metadata.excluded_execution == 1 && metadata.excluded_scheduler == 2 && metadata.storage.attempted == 1);
    assert(job_capture_read(c, 0, &r) == 1 && r.kind == JOB_CAPTURE_EXECUTION);
    assert((r.flags & JOB_CAPTURE_HOST_ASSIGNMENT) && r.host_assignment.dispatch == 3);
    job_capture_stop(c);

    cfg.accept_execution = nullptr; cfg.accept_scheduler = nullptr;
    job_capture_window window(cfg); assert(window.available());
    auto gated = window.config();
    c = job_capture_start(&gated); assert(c);
    job_queue_observer queue_owner{c, job_capture_queue_call};
    assert(job_queue_observer_install(&queue_owner));
    ppu_context queue{}; queue.gpr[3] = 456; queue.gpr[4] = 789;
    motorstorm_observe_queue_reset(&queue);
    ps3_spurs_scheduler_worker_begin(&info);
    ps3_spu_execution_notify(PS3_SPU_NATIVE_BEGIN, &context, 0x10, 0x20, 7, 0, 0);
    ps3_spurs_scheduler_worker_return(0, 4);
    assert(job_capture_describe(c, &metadata));
    assert(metadata.storage.attempted == 0 && metadata.excluded_execution == 1 && metadata.excluded_scheduler == 2 && metadata.excluded_queue_call == 2);
    uint64_t before = 0, after = 0;
    assert(window.open(&before, &after) == job_capture_window::opened && after >= before);
    motorstorm_observe_queue_reset(&queue);
    queue.gpr[5] = 0x123456789abcdef0ULL;
    motorstorm_observe_add_job(&queue);
    ps3_spurs_scheduler_worker_begin(&info);
    ps3_spu_execution_notify(PS3_SPU_NATIVE_BEGIN, &context, 0x10, 0x20, 7, 0, 0);
    ps3_spurs_scheduler_worker_return(0, 4);
    assert(job_capture_describe(c, &metadata));
    assert(metadata.storage.attempted == 7 && metadata.excluded_execution == 1 && metadata.excluded_scheduler == 2 && metadata.excluded_queue_call == 2);
    assert(job_capture_read(c, 0, &r) == 1 && r.kind == JOB_CAPTURE_QUEUE_CALL && r.value.queue_call.event.call_id == 2 && r.value.queue_call.tick > 0 && r.value.queue_call.event.phase == job_queue_phase::enter);
    assert(job_capture_read(c, 1, &r) == 1 && r.kind == JOB_CAPTURE_QUEUE_CALL && r.value.queue_call.event.call_id == 2 && r.value.queue_call.event.phase == job_queue_phase::returned);
    assert(queue.gpr[3] == 458);
    assert(job_capture_read(c, 5, &r) == 1 && r.kind == JOB_CAPTURE_EXECUTION);
    assert(r.thread == 42 && (r.flags & JOB_CAPTURE_HOST_ASSIGNMENT) && r.host_assignment.dispatch == 3);
    FILE* file = tmpfile(); assert(file && job_capture_write_snapshot(c, file));
    unsigned count = 0; job_capture_snapshot snapshot{};
    assert(job_capture_read_snapshot(file, count_queue, &count, &snapshot));
    assert(count == 4 && snapshot.before.excluded_queue_call == 2 && snapshot.before.schema_version == JOB_CAPTURE_SCHEMA_VERSION);
    fclose(file);
    assert(job_queue_observer_install(nullptr));
    job_capture_stop(c);

    // Startup history supplies lifecycle boundaries while the high-volume gate is closed.
    cfg.capacity = 16;
    job_capture_window history(cfg, true);
    gated = history.config();
    c = job_capture_start(&gated); assert(c);
    queue_owner.user = c;
    assert(job_queue_observer_install(&queue_owner));
    motorstorm_observe_queue_reset_multi(&queue);
    motorstorm_observe_queue_init(&queue);
    motorstorm_observe_add_job(&queue);
    ps3_spurs_scheduler_worker_begin(&info);
    ps3_spu_execution_notify(PS3_SPU_NATIVE_BEGIN, &context, 0x10, 0x20, 7, 0, 0);
    ps3_spurs_scheduler_worker_return(0, 4);
    assert(!ppu->accept(ppu->user, PS3_ATOMIC_PPU32, 1, 42, 4));
    assert(job_capture_describe(c, &metadata));
    assert(metadata.storage.attempted == 4 && "startup reset and init records missing");
    assert(metadata.excluded_queue_call == 2 && metadata.excluded_atomic == 1);
    assert(metadata.excluded_execution == 1 && metadata.excluded_scheduler == 2);
    assert(history.open(&before, &after) == job_capture_window::opened);
    for (unsigned index = 0; index < 4; ++index) {
        assert(job_capture_read(c, index, &r) == 1 && r.kind == JOB_CAPTURE_QUEUE_CALL);
        assert(r.value.queue_call.tick < before);
        const auto expected = index < 2 ? job_queue_operation::reset : job_queue_operation::init;
        assert(r.value.queue_call.event.operation == expected);
    }
    motorstorm_observe_add_job(&queue);
    motorstorm_observe_queue_reset_multi(&queue);
    assert(job_capture_describe(c, &metadata) && metadata.storage.attempted == 8);
    assert(job_capture_read(c, 4, &r) == 1 && r.value.queue_call.tick > after);
    assert(r.value.queue_call.event.operation == job_queue_operation::add_job);
    assert(job_queue_observer_install(nullptr));
    job_capture_stop(c);

    cfg.accept_queue_call = reject_initialization;
    job_capture_window filtered_history(cfg, true);
    gated = filtered_history.config();
    c = job_capture_start(&gated); assert(c);
    queue_owner.user = c;
    assert(job_queue_observer_install(&queue_owner));
    motorstorm_observe_queue_init(&queue);
    motorstorm_observe_queue_reset_multi(&queue);
    assert(filtered_history.open(&before, &after) == job_capture_window::opened);
    motorstorm_observe_queue_init(&queue);
    motorstorm_observe_add_job(&queue);
    assert(job_capture_describe(c, &metadata));
    assert(metadata.storage.attempted == 4 && metadata.excluded_queue_call == 4);
    assert(job_queue_observer_install(nullptr));
    job_capture_stop(c);


    cfg.accept_execution = nullptr;
    cfg.accept_scheduler = nullptr;
    cfg.accept_queue_call = nullptr;
    cfg.capacity = 8;
    cfg.capture_policy_state = true;
    context.policy_mode = 1;
    context.ls = context.ls_store;
    context.pc = 0x6000;
    for (unsigned i = 0; i < SPU_LS_SIZE; ++i) context.ls[i] = static_cast<uint8_t>(i);
    c = job_capture_start(&cfg); assert(c);
    ps3_spu_execution_notify(PS3_SPU_INTERPRETED_CONTROL, &context, 0x3094, 0x6000, 0,
                             PS3_SPU_SOURCE_INSTRUCTION, 0);
    assert(job_capture_describe(c, &metadata));
    assert(metadata.storage.attempted == 2 && "execution policy state missing");
    assert(job_capture_read(c, 1, &r) == 1 && r.kind == JOB_CAPTURE_POLICY);
    assert(r.value.policy.execution.context == reinterpret_cast<uintptr_t>(&context));
    assert(r.value.policy.flags == JOB_POLICY_PRIVATE_LS);
    assert(r.value.policy.before_tick > r.value.policy.execution.tick);
    assert(r.value.policy.after_tick > r.value.policy.before_tick);
    assert(!std::memcmp(r.value.policy.records, context.ls + 0x1430, 96));
    job_capture_stop(c);
    cfg.capture_policy_state = false;
    c = job_capture_start(&cfg); assert(c);
    ps3_spu_execution_notify(PS3_SPU_INTERPRETED_CONTROL, &context, 0x3094, 0x6000, 0, 0, 0);
    assert(job_capture_describe(c, &metadata) && metadata.storage.attempted == 1);
    job_capture_stop(c);
    return 0;
}
