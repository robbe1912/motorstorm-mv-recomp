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
#include "../../vendor/ps3recomp/runtime/spu/spu_jobmod_identity.h"
#include <cstdint>
#include <cstring>

enum : std::uint32_t {
    JOB_POLICY_PRIVATE_LS = 1,
    JOB_POLICY_NULL_LS = 2,
    JOB_POLICY_EXTERNAL_LS = 4,
    JOB_POLICY_CLOCK_INVALID = 8
};

enum : std::uint32_t {
    JOB_POLICY_MODULE_VALID = 1,
    JOB_POLICY_MODULE_BAD_BASE = 2,
    JOB_POLICY_MODULE_BAD_HEADER = 4,
    JOB_POLICY_MODULE_WRONG_ENTRY = 8
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
    std::uint32_t module_flags, module_base, module_span, module_entry_size;
    std::uint64_t module_fingerprint;
    std::uint8_t module_header[48], module_entry[64];
    std::uint8_t dispatcher[168]; // Original dispatcher extent 0x3008..0x30B0.
};

// Only the original interpreted dispatcher call requests a module fingerprint.
// The bounded header span and fingerprint basis match the existing SDK registry.
inline void capture_job_module_identity(const std::uint8_t* ls,
        job_policy_observation& result) {
    const auto& event = result.execution;
    if (event.kind != PS3_SPU_INTERPRETED_CONTROL || event.source_pc != 0x3094 ||
            (event.flags & (PS3_SPU_SOURCE_INSTRUCTION | PS3_SPU_SOURCE_UNAVAILABLE)) !=
                PS3_SPU_SOURCE_INSTRUCTION)
        return;
    const auto base = stage_be32(result.module);
    result.module_base = base;
    if (!base || (base & 15u) || base > 0x3e000u - sizeof(result.module_header)) {
        result.module_flags = JOB_POLICY_MODULE_BAD_BASE;
        return;
    }
    std::memcpy(result.module_header, ls + base, sizeof(result.module_header));
    const auto span = stage_header_span(result.module_header, base, sizeof(result.module_header));
    if (!span) {
        result.module_flags = JOB_POLICY_MODULE_BAD_HEADER;
        return;
    }
    result.module_span = span;
    const auto entry = stage_be32(result.module_header + 0x10);
    if (entry >= span || event.target_pc != base + entry || result.context_pc != event.target_pc) {
        result.module_flags = JOB_POLICY_MODULE_WRONG_ENTRY;
        return;
    }
    result.module_entry_size = span - entry < sizeof(result.module_entry)
        ? span - entry : sizeof(result.module_entry);
    std::memcpy(result.module_entry, ls + base + entry, result.module_entry_size);
    std::uint64_t fingerprint = UINT64_C(1469598103934665603);
    for (std::uint32_t i = 0; i < span; ++i)
        fingerprint = (fingerprint ^ ls[base + i]) * UINT64_C(1099511628211);
    result.module_fingerprint = fingerprint;
    result.module_flags = JOB_POLICY_MODULE_VALID;
}

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
            result.preferred_registers[i] = spu_preferred_u32(&context->gpr[registers[i]]);
        std::memcpy(result.running, ls + 0x12e0, sizeof(result.running));
        std::memcpy(result.storing, ls + 0x12f0, sizeof(result.storing));
        std::memcpy(result.lane, ls + 0x1340, sizeof(result.lane));
        std::memcpy(result.module, ls + 0x1330, sizeof(result.module));
        std::memcpy(result.records, ls + 0x1430, sizeof(result.records));
        std::memcpy(result.dispatcher, ls + 0x3008, sizeof(result.dispatcher));
        capture_job_module_identity(ls, result);
    }
    result.after_tick = clock ? clock(user) : 0;
    if (!result.before_tick || result.after_tick < result.before_tick)
        result.flags |= JOB_POLICY_CLOCK_INVALID;
    return true;
}
