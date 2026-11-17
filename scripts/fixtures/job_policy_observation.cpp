#include "job_policy_observation.h"
#include <cassert>
#include <cstdio>
#include <cstring>

static spu_context context;
static std::uint64_t now = 100;
static std::uint64_t tick(void* user) {
    assert(user == &now);
    return ++now;
}
int main() {
    context.ls = context.ls_store;
    context.pc = 0x6000;
    for (unsigned i = 0; i < SPU_LS_SIZE; ++i)
        context.ls[i] = static_cast<std::uint8_t>(i ^ (i >> 8));
    const unsigned registers[] = {0, 3, 4, 5};
    for (unsigned i = 0; i < 4; ++i) {
        context.gpr[registers[i]] = spu_make_preferred_u32(0x12340000 + i);
        context.gpr[registers[i]]._u32[3] = 0xdead0000 + i;
    }
    ps3_spu_execution_event event{};
    event.context = reinterpret_cast<std::uintptr_t>(&context);
    event.policy_mode = 1;
    event.source_pc = 0x3094;
    event.target_pc = 0x6000;
    event.tick = 99;
    job_policy_observation result{};
    assert(capture_job_policy_observation(event, result, tick, &now) && "policy state missing");
    assert(result.before_tick == 101 && result.after_tick == 102);
    assert(result.context_pc == 0x6000 && result.flags == JOB_POLICY_PRIVATE_LS);
    assert(result.execution.tick == event.tick && result.execution.context == event.context);
    assert(result.execution.source_pc == event.source_pc && result.execution.target_pc == event.target_pc);
    assert(result.execution.policy_mode == event.policy_mode && result.execution.flags == event.flags);
    assert(!std::memcmp(result.running, context.ls + 0x12e0, 16));
    assert(!std::memcmp(result.storing, context.ls + 0x12f0, 16));
    assert(!std::memcmp(result.lane, context.ls + 0x1340, 16));
    assert(!std::memcmp(result.module, context.ls + 0x1330, 16));
    assert(!std::memcmp(result.records, context.ls + 0x1430, 96));
    assert(!std::memcmp(result.dispatcher, context.ls + 0x3008, 168));
    for (unsigned i = 0; i < 4; ++i) {
        assert(result.preferred_registers[i] == 0x12340000 + i);
        assert(spu_preferred_u32(&context.gpr[registers[i]]) == 0x12340000 + i);
        assert(context.gpr[registers[i]]._u32[3] == 0xdead0000 + i);
    }
    assert(context.pc == 0x6000 && context.ls == context.ls_store);
    for (unsigned i = 0; i < SPU_LS_SIZE; ++i)
        assert(context.ls[i] == static_cast<std::uint8_t>(i ^ (i >> 8)));
    event.policy_mode = 0;
    assert(!capture_job_policy_observation(event, result, tick, &now));
    event.policy_mode = 1;
    event.context = 0;
    assert(!capture_job_policy_observation(event, result, tick, &now));
    event.context = reinterpret_cast<std::uintptr_t>(&context);
    context.ls = nullptr;
    assert(capture_job_policy_observation(event, result, tick, &now));
    assert(result.flags == JOB_POLICY_NULL_LS);
    for (auto value : result.records) assert(value == 0);
    context.ls = context.ls_store + 16;
    assert(capture_job_policy_observation(event, result, tick, &now));
    assert(result.flags == JOB_POLICY_EXTERNAL_LS);
    context.ls = context.ls_store;
    now = UINT64_MAX;
    assert(capture_job_policy_observation(event, result, tick, &now));
    assert(result.flags & JOB_POLICY_CLOCK_INVALID);
    std::puts("PASS owned policy bytes, registers, backing rejection, clock bounds and immutable inputs");
}
