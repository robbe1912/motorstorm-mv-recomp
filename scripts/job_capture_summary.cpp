#include "../src/motorstorm/job_capture_snapshot.h"
#include <cstdio>
#include <cstdint>
#include <cstring>

struct counts {
    bool events = false;
    bool all_events = false;
    uint64_t atomic = 0, execution = 0, scheduler = 0, queue_call = 0, policy = 0, policy_clock_invalid = 0, other = 0;
    uint64_t queue_clock_invalid = 0, queue_id_invalid = 0;
    uint64_t atomic_clock_invalid = 0, execution_clock_invalid = 0, scheduler_clock_invalid = 0;
    uint64_t atomic_context_unknown = 0, scheduler_identity_invalid = 0;
    uint64_t atomic_attempted = 0, atomic_committed = 0;
};
static void print_bytes(const char* name, const uint8_t* data, size_t size) {
    std::printf(",\"%s\":\"", name);
    for (size_t i = 0; i < size; ++i) std::printf("%02x", data[i]);
    std::printf("\"");
}
static int count_record(void* p, uint64_t index, const job_capture_record* r) {
    auto& c = *static_cast<counts*>(p);
    if (c.all_events && r->kind == JOB_CAPTURE_POLICY) {
        const auto& state = r->value.policy;
        const auto& e = state.execution;
        std::printf("{\"type\":\"policy\",\"index\":%llu,\"thread\":%llu,\"host_dispatch\":%llu,\"tick\":%llu,\"context\":%llu,\"kind\":%u,\"source_pc\":%u,\"target_pc\":%u,\"image\":%d,\"policy_mode\":%u,\"execution_flags\":%u,\"before\":%llu,\"after\":%llu,\"flags\":%u,\"context_pc\":%u,\"registers\":[%u,%u,%u,%u]",
            (unsigned long long)index, (unsigned long long)r->thread,
            (unsigned long long)r->host_assignment.dispatch, (unsigned long long)e.tick,
            (unsigned long long)e.context, e.kind, e.source_pc, e.target_pc, e.image,
            e.policy_mode, e.flags, (unsigned long long)state.before_tick,
            (unsigned long long)state.after_tick, state.flags, state.context_pc,
            state.preferred_registers[0], state.preferred_registers[1],
            state.preferred_registers[2], state.preferred_registers[3]);
        print_bytes("running", state.running, sizeof(state.running));
        print_bytes("storing", state.storing, sizeof(state.storing));
        print_bytes("lane", state.lane, sizeof(state.lane));
        print_bytes("module", state.module, sizeof(state.module));
        print_bytes("records", state.records, sizeof(state.records));
        print_bytes("dispatcher", state.dispatcher, sizeof(state.dispatcher));
        std::puts("}");
    }
    if (c.all_events && r->kind == JOB_CAPTURE_QUEUE_CALL) {
        const auto& q = r->value.queue_call; const auto& e = q.event;
        std::printf("{\"type\":\"queue_call\",\"index\":%llu,\"thread\":%llu,\"record_flags\":%u,\"host_dispatch\":%llu,\"tick\":%llu,\"call_id\":%llu,\"context\":%llu,\"object\":%u,\"argument\":%u,\"operation\":%u,\"phase\":%u,\"header\":%llu,\"entry_lr\":%llu}\n",
                    (unsigned long long)index, (unsigned long long)r->thread, r->flags,
                    (unsigned long long)r->host_assignment.dispatch, (unsigned long long)q.tick,
                    (unsigned long long)e.call_id, (unsigned long long)e.context, e.object, e.argument,
                    (unsigned)e.operation, (unsigned)e.phase, (unsigned long long)e.header, (unsigned long long)e.entry_lr);
    }
    if (c.all_events && r->kind == JOB_CAPTURE_EXECUTION) {
        const auto& e = r->value.execution;
        std::printf("{\"type\":\"execution\",\"index\":%llu,\"thread\":%llu,\"record_flags\":%u,\"host_dispatch\":%llu,\"tick\":%llu,\"detail\":%llu,\"context\":%llu,\"function\":%llu,\"kind\":%u,\"flags\":%u,\"source_pc\":%u,\"target_pc\":%u,\"image\":%d,\"host_depth\":%d,\"policy_mode\":%u}\n",
                    (unsigned long long)index, (unsigned long long)r->thread, r->flags,
                    (unsigned long long)r->host_assignment.dispatch, (unsigned long long)e.tick,
                    (unsigned long long)e.detail, (unsigned long long)e.context, (unsigned long long)e.function,
                    e.kind, e.flags, e.source_pc, e.target_pc, e.image, e.host_depth, e.policy_mode);
    }
    if (c.all_events && r->kind == JOB_CAPTURE_SCHEDULER) {
        const auto& e = r->value.scheduler; const auto& i = e.info;
        std::printf("{\"type\":\"scheduler\",\"index\":%llu,\"thread\":%llu,\"record_flags\":%u,\"host_dispatch\":%llu,\"instance\":%llu,\"workload_generation\":%llu,\"dispatch\":%llu,\"argument\":%llu,\"instance_ea\":%u,\"workload\":%u,\"lane\":%u,\"pm_ea\":%u,\"pm_size\":%u,\"nspus\":%u,\"image\":%d,\"tick_begin\":%llu,\"tick_end\":%llu,\"polls\":%llu,\"kind\":%u,\"flags\":%u,\"ready\":%u,\"signal\":%u,\"active\":%u,\"max_contention\":%u,\"result\":%d}\n",
                    (unsigned long long)index, (unsigned long long)r->thread, r->flags,
                    (unsigned long long)r->host_assignment.dispatch, (unsigned long long)i.instance,
                    (unsigned long long)i.workload_generation, (unsigned long long)i.dispatch,
                    (unsigned long long)i.argument, i.instance_ea, i.workload, i.lane, i.pm_ea, i.pm_size, i.nspus, i.image,
                    (unsigned long long)e.tick_begin, (unsigned long long)e.tick_end, (unsigned long long)e.polls,
                    e.kind, e.flags, e.ready, e.signal, e.active, e.max_contention, e.result);
    }
    if (c.events && r->kind == JOB_CAPTURE_ATOMIC) {
        const auto& a = r->value.atomic;
        std::printf("{\"type\":\"atomic\",\"index\":%llu,\"thread\":%llu,\"record_flags\":%u,"
                    "\"source\":%u,\"command\":%u,\"flags\":%u,\"address\":%llu,\"size\":%u,"
                    "\"begin\":%llu,\"end\":%llu,\"saved_pc\":%u,\"return_address\":%u,\"context\":%llu,"
                    "\"host_dispatch\":%llu,\"payload_truncated\":%s,"
                    "\"before\":\"",
                    (unsigned long long)index, (unsigned long long)r->thread, r->flags,
                    a.source, a.command, a.flags, (unsigned long long)a.address, a.size,
                    (unsigned long long)a.begin_tick, (unsigned long long)a.end_tick,
                    a.saved_pc, a.return_address, (unsigned long long)a.context,
                    (unsigned long long)r->host_assignment.dispatch,
                    a.size > sizeof(a.before) ? "true" : "false");
        for (uint32_t i = 0; i < a.size && i < sizeof(a.before); ++i) std::printf("%02x", a.before[i]);
        std::printf("\",\"after\":\"");
        for (uint32_t i = 0; i < a.size && i < sizeof(a.after); ++i) std::printf("%02x", a.after[i]);
        std::printf("\"}\n");
    }
    switch (r->kind) {
    case JOB_CAPTURE_ATOMIC:
        ++c.atomic;
        c.atomic_clock_invalid += !!(r->value.atomic.flags & PS3_ATOMIC_CLOCK_INVALID);
        c.atomic_context_unknown += !!(r->value.atomic.flags & PS3_ATOMIC_CONTEXT_UNKNOWN);
        c.atomic_attempted += !!(r->value.atomic.flags & PS3_ATOMIC_ATTEMPTED);
        c.atomic_committed += !!(r->value.atomic.flags & PS3_ATOMIC_COMMITTED);
        break;
    case JOB_CAPTURE_EXECUTION:
        ++c.execution;
        c.execution_clock_invalid += !!(r->value.execution.flags & PS3_SPU_CLOCK_INVALID);
        break;
    case JOB_CAPTURE_SCHEDULER:
        ++c.scheduler;
        c.scheduler_clock_invalid += !!(r->value.scheduler.flags & PS3_SPURS_CLOCK_INVALID);
        c.scheduler_identity_invalid += !!(r->value.scheduler.flags & PS3_SPURS_IDENTITY_INVALID);
        break;
    case JOB_CAPTURE_POLICY:
        ++c.policy;
        c.policy_clock_invalid += !!(r->value.policy.flags & JOB_POLICY_CLOCK_INVALID);
        break;
    case JOB_CAPTURE_QUEUE_CALL:
        ++c.queue_call;
        c.queue_clock_invalid += !r->value.queue_call.tick;
        c.queue_id_invalid += !r->value.queue_call.event.call_id;
        break;
    default: ++c.other; break;
    }
    return 1;
}
int main(int argc, char** argv) {
    if (argc != 2 && !(argc == 3 && (!std::strcmp(argv[2], "--atomic-events") || !std::strcmp(argv[2], "--events")))) {
        std::fprintf(stderr, "usage: job_capture_summary snapshot.bin [--atomic-events|--events]\n"); return 2;
    }
    FILE* f = std::fopen(argv[1], "rb");
    if (!f) { std::perror("snapshot"); return 1; }
    counts c{}; c.events = argc == 3; c.all_events = c.events && !std::strcmp(argv[2], "--events"); job_capture_snapshot s{};
    const int ok = job_capture_read_snapshot(f, count_record, &c, &s);
    std::fclose(f);
    if (!ok) { std::fprintf(stderr, "Invalid, truncated or incompatible snapshot\n"); return 1; }
#define U(x) static_cast<unsigned long long>(x)
    std::printf("{\"type\":\"summary\",\"run_id\":%llu,\"ticks_per_second\":%llu,\"capacity\":%u,"
                "\"examined\":%llu,\"delivered\":%llu,\"pending\":%llu,"
                "\"attempted_before\":%llu,\"attempted_after\":%llu,"
                "\"dropped_before\":%llu,\"dropped_after\":%llu,"
                "\"append_failures_after\":%llu,\"filter_mask\":%u,"
                "\"excluded_atomic_after\":%llu,\"excluded_execution_after\":%llu,"
                "\"excluded_scheduler_after\":%llu,\"excluded_queue_call_after\":%llu,\"atomic\":%llu,\"execution\":%llu,"
                "\"scheduler\":%llu,\"queue_call\":%llu,\"policy\":%llu,\"policy_clock_invalid\":%llu,\"other\":%llu,\"queue_clock_invalid\":%llu,\"queue_id_invalid\":%llu,\"atomic_clock_invalid\":%llu,"
                "\"execution_clock_invalid\":%llu,\"scheduler_clock_invalid\":%llu,"
                "\"atomic_context_unknown\":%llu,\"scheduler_identity_invalid\":%llu,"
                "\"atomic_attempted\":%llu,\"atomic_committed\":%llu}\n",
                U(s.before.run_id), U(s.before.ticks_per_second), s.before.storage.capacity,
                U(s.examined), U(s.delivered), U(s.pending), U(s.before.storage.attempted),
                U(s.after.storage.attempted), U(s.before.storage.dropped), U(s.after.storage.dropped),
                U(s.after.unexpected_append_failures), s.before.filter_mask,
                U(s.after.excluded_atomic), U(s.after.excluded_execution), U(s.after.excluded_scheduler), U(s.after.excluded_queue_call),
                U(c.atomic), U(c.execution), U(c.scheduler), U(c.queue_call), U(c.policy), U(c.policy_clock_invalid), U(c.other), U(c.queue_clock_invalid), U(c.queue_id_invalid),
                U(c.atomic_clock_invalid), U(c.execution_clock_invalid), U(c.scheduler_clock_invalid),
                U(c.atomic_context_unknown), U(c.scheduler_identity_invalid),
                U(c.atomic_attempted), U(c.atomic_committed));
#undef U
    return 0;
}
