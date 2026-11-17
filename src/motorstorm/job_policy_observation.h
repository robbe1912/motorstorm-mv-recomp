#pragma once
#include "ps3emu/spu_execution_observer.h"
// The existing SDK uses memset for its architectural register/context storage.
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wclass-memaccess"
#endif
#include "../../vendor/ps3recomp/runtime/spu/spu_context.h"
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC diagnostic pop
#endif
#include <cstdint>
#include <cstring>

enum : std::uint32_t {
    JOB_POLICY_PRIVATE_LS = 1,
    JOB_POLICY_NULL_LS = 2,
    JOB_POLICY_EXTERNAL_LS = 4,
    JOB_POLICY_CLOCK_INVALID = 8
};

// Sequential owned copies at an execution callback. Original code identity and
// queue/job ownership are validated offline using these bytes and trace history.
struct job_policy_observation {
    ps3_spu_execution_event execution;
    std::uint64_t before_tick, after_tick;
    std::uint32_t flags, context_pc;
    std::uint32_t preferred_registers[4]; // r0, r3, r4, r5
    std::uint8_t running[16], storing[16], lane[16], module[16];
    std::uint8_t records[96]; // Three 32-byte policy records at LS 0x1430.
    std::uint8_t dispatcher[168]; // Original dispatcher extent 0x3008..0x30B0.
};

inline bool capture_job_policy_observation(const ps3_spu_execution_event& event,
        job_policy_observation& result, std::uint64_t (*clock)(void*), void* user) {
    if (!event.policy_mode || !event.context) return false;
    result = {};
    result.execution = event;
    result.before_tick = clock ? clock(user) : 0;
    const auto* context = reinterpret_cast<const spu_context*>(event.context);
    const auto* ls = context->ls;
    if (!ls) {
        result.flags = JOB_POLICY_NULL_LS;
    } else if (ls != context->ls_store) {
        result.flags = JOB_POLICY_EXTERNAL_LS;
    } else {
        result.flags = JOB_POLICY_PRIVATE_LS;
        result.context_pc = context->pc;
        const unsigned registers[] = {0, 3, 4, 5};
        for (unsigned i = 0; i < 4; ++i)
            result.preferred_registers[i] = context->gpr[registers[i]]._u32[3];
        std::memcpy(result.running, ls + 0x12e0, sizeof(result.running));
        std::memcpy(result.storing, ls + 0x12f0, sizeof(result.storing));
        std::memcpy(result.lane, ls + 0x1340, sizeof(result.lane));
        std::memcpy(result.module, ls + 0x1330, sizeof(result.module));
        std::memcpy(result.records, ls + 0x1430, sizeof(result.records));
        std::memcpy(result.dispatcher, ls + 0x3008, sizeof(result.dispatcher));
    }
    result.after_tick = clock ? clock(user) : 0;
    if (!result.before_tick || result.after_tick < result.before_tick)
        result.flags |= JOB_POLICY_CLOCK_INVALID;
    return true;
}
