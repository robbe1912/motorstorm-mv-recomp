#define main owner_fixture_unused_main
#include "job_capture_owner.cpp"
#undef main
#include "../../src/motorstorm/job_capture_control.h"
#include <windows.h>
#include <string>
#ifdef PORT_QUEUE_CALL_OBSERVATION
#include "ppu_recomp.h"
void game_original_queue_reset(ppu_context*) {}
void game_original_queue_init(ppu_context*) {}
static void fixture_real_store(ppu_context*);
void game_original_add_job(ppu_context* ctx) {
    fixture_real_store(ctx);
}
void motorstorm_observe_queue_reset(ppu_context*);
void motorstorm_observe_add_job(ppu_context*);
static void ignored_queue(void*, const job_queue_event&) noexcept {}
#endif

static int count_record(void* p, uint64_t, const job_capture_record* r) {
    assert(r->kind >= JOB_CAPTURE_ATOMIC && r->kind <= JOB_CAPTURE_QUEUE_CALL);
    ++*static_cast<unsigned*>(p);
    return 1;
}

/* FIXTURE_REAL_PPU_STORE */
int main(int argc, char** argv) {
    assert(argc == 3);
    if (!strcmp(argv[2], "disabled")) {
        assert(_putenv_s("MS_JOB_CAPTURE_DIR", "") == 0);
        assert(job_capture_control_start() && !ppu && !spu);
        return 0;
    }
    assert(_putenv_s("MS_JOB_CAPTURE_DIR", argv[1]) == 0);
#ifdef PORT_QUEUE_CALL_OBSERVATION
    if (!strcmp(argv[2], "conflict")) {
        job_queue_observer existing{nullptr, ignored_queue};
        assert(job_queue_observer_install(&existing));
        assert(!job_capture_control_start() && !ppu && !spu && !execution && !scheduler);
        assert(!job_queue_observer_install(&existing));
        assert(job_queue_observer_install(nullptr));
        return 0;
    }
#endif
    if (!strcmp(argv[2], "invalid")) {
        assert(!job_capture_control_start() && !ppu && !spu);
        return 0;
    }
    assert(!strcmp(argv[2], "run"));
    assert(job_capture_control_start());
    assert(ppu && spu && execution && scheduler);
    assert(!ppu->accept(ppu->user, PS3_ATOMIC_PPU32, 1, 42, 4));
    std::string open = std::string(argv[1]) + "\\open";
    FILE* f = fopen(open.c_str(), "wb"); assert(f); assert(!fclose(f));
    bool admitted = false;
    for (unsigned i = 0; i < 200 && !admitted; ++i) {
        Sleep(10); admitted = ppu->accept(ppu->user, PS3_ATOMIC_PPU32, 1, 42, 4) != 0;
    }
    assert(admitted);
#ifdef PORT_QUEUE_CALL_OBSERVATION
    ppu_context ctx{}; ctx.gpr[3] = 0x42;
    motorstorm_observe_queue_reset(&ctx);
    ctx.gpr[4] = 0x200; ctx.gpr[5] = 0x123456789abcdef0ULL;
    motorstorm_observe_add_job(&ctx);
    motorstorm_observe_add_job(&ctx); // The same zero-expected CAS now fails.
#endif
    ps3_atomic_observation event{}; event.address = 42; event.size = 4;
    event.before[0] = 0x12; event.after[0] = 0xab;
    event.flags = PS3_ATOMIC_ATTEMPTED | PS3_ATOMIC_COMMITTED |
                  PS3_ATOMIC_CLOCK_INVALID | PS3_ATOMIC_CONTEXT_UNKNOWN;
    ppu->observe(ppu->user, &event);
    ps3_spu_execution_event exec{}; exec.tick = 77; exec.context = 123; exec.target_pc = 456;
    exec.kind = PS3_SPU_COMPILED_DISPATCH; execution->observe(execution->user, &exec);
    ps3_spurs_scheduler_event sched{}; sched.info.dispatch = 42; sched.info.workload_generation = 7;
    sched.tick_begin = 80; sched.tick_end = 81; sched.kind = PS3_SPURS_ADMITTED;
    scheduler->observe(scheduler->user, &sched);
    job_queue_event queue{99, 123, 456, 789, job_queue_operation::init, job_queue_phase::enter};
    queue.entry_lr = 0x87b83c;
    job_capture_queue_call(ppu->user, queue);
    std::string request = std::string(argv[1]) + "\\snapshot";
    f = fopen(request.c_str(), "wb"); assert(f); assert(!fclose(f));
    std::string path = std::string(argv[1]) + "\\snapshot.bin";
    job_capture_snapshot snapshot{}; unsigned count = 0; bool read = false;
    for (unsigned i = 0; i < 200 && !read; ++i) {
        Sleep(10); f = fopen(path.c_str(), "rb");
        if (f) { count = 0; read = job_capture_read_snapshot(f, count_record, &count, &snapshot) != 0; fclose(f); }
    }
    assert(read && count ==
#ifdef PORT_QUEUE_CALL_OBSERVATION
        12
#else
        4
#endif
        && snapshot.before.run_id && snapshot.before.ticks_per_second);
    assert(snapshot.before.excluded_atomic >= 1 && snapshot.before.storage.dropped == 0);
    return 0;
}
