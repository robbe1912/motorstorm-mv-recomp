#define main owner_fixture_unused_main
#include "job_capture_owner.cpp"
#undef main
#include "../../src/motorstorm/job_capture_control.h"
#include <windows.h>
#include <string>
#ifdef PORT_QUEUE_CALL_OBSERVATION
#include "ppu_recomp.h"
void game_original_queue_reset_multi(ppu_context* ctx) { (void)ctx; }
void game_original_queue_reset(ppu_context*) {}
void game_original_queue_init(ppu_context*) {}
static void fixture_real_store(ppu_context*);
void game_original_add_job(ppu_context* ctx) {
    fixture_real_store(ctx);
}
void motorstorm_observe_queue_reset(ppu_context*);
void motorstorm_observe_queue_reset_multi(ppu_context*);
void motorstorm_observe_queue_init(ppu_context*);
void motorstorm_observe_add_job(ppu_context*);
static void ignored_queue(void*, const job_queue_event&) noexcept {}
#endif

static int count_record(void* p, uint64_t, const job_capture_record* r) {
    assert(r->kind >= JOB_CAPTURE_ATOMIC && r->kind <= JOB_CAPTURE_POLICY);
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
    const bool policy = !strcmp(argv[2], "policy");
    const bool filtered = !strcmp(argv[2], "filtered");
    assert(_putenv_s("MS_JOB_CAPTURE_EXECUTION_PCS", filtered ? "0x1c8,0x3180" : "") == 0);
    if (!strcmp(argv[2], "invalid-filter")) {
        assert(_putenv_s("MS_JOB_CAPTURE_EXECUTION_PCS", "0x1c8,junk") == 0);
        assert(!job_capture_control_start() && !ppu && !spu && !execution && !scheduler);
        return 0;
    }
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
    assert(!strcmp(argv[2], "run") || filtered || policy);
    assert(job_capture_control_start());
    assert(ppu && spu && execution && scheduler);
#ifdef PORT_QUEUE_CALL_OBSERVATION
    ppu_context startup{};
    startup.gpr[3] = 0x1234;
    motorstorm_observe_queue_reset_multi(&startup);
    motorstorm_observe_queue_init(&startup);
    job_capture_info startup_info{};
    assert(job_capture_describe(static_cast<job_capture*>(ppu->user), &startup_info));
    assert(startup_info.storage.attempted == 4 && "controller omitted startup lifecycle");
#endif
    assert(!ppu->accept(ppu->user, PS3_ATOMIC_PPU32, 1, 42, 4));
    std::string open = std::string(argv[1]) + "\\open";
    FILE* f = fopen(open.c_str(), "wb"); assert(f); assert(!fclose(f));
    bool admitted = false;
    for (unsigned i = 0; i < 200 && !admitted; ++i) {
        Sleep(10); admitted = ppu->accept(ppu->user, PS3_ATOMIC_PPU32, 1, 42, 4) != 0;
    }
    assert(admitted);
    if (filtered) {
        assert(_putenv_s("MS_JOB_CAPTURE_EXECUTION_PCS", "0x4") == 0);
        assert(!execution->accept(execution->user, PS3_SPU_COMPILED_DISPATCH, 123, 460, 464));
        assert(execution->accept(execution->user, PS3_SPU_COMPILED_DISPATCH, 123, 0, 456));
        assert(execution->accept(execution->user, PS3_SPU_INTERPRETED_CONTROL, 123, 0x3180, 464));
    }
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
    if (policy) {
        static spu_context context;
        context.ls = context.ls_store;
        context.policy_mode = 1;
        context.pc = 0x6000;
        context.ls[0x1430] = 0x7a;
        const auto put_word = [&](unsigned address, uint32_t value) {
            for (unsigned i = 0; i < 4; ++i)
                context.ls[address + i] = static_cast<uint8_t>(value >> (24 - 8 * i));
        };
        put_word(0x1330, 0x4000);
        put_word(0x4010, 0x2000);
        put_word(0x4014, 0x2100);
        put_word(0x4020, 0xc0dec0de);
        put_word(0x4028, 0x4000);
        auto policy_event = exec;
        policy_event.context = reinterpret_cast<uintptr_t>(&context);
        policy_event.policy_mode = 1;
        policy_event.kind = PS3_SPU_INTERPRETED_CONTROL;
        policy_event.flags = PS3_SPU_SOURCE_INSTRUCTION;
        policy_event.source_pc = 0x3094;
        policy_event.target_pc = 0x6000;
        execution->observe(execution->user, &policy_event);
    }
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
    assert(read && count == (policy ? 2u : 0u) +
#ifdef PORT_QUEUE_CALL_OBSERVATION
        16
#else
        4
#endif
        && snapshot.before.run_id && snapshot.before.ticks_per_second);
    assert(snapshot.before.excluded_atomic >= 1 && snapshot.before.storage.dropped == 0);
    if (filtered) assert(snapshot.before.excluded_execution >= 1);
    return 0;
}
