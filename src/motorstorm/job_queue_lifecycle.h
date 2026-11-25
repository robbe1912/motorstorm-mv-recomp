#pragma once
#include <cstdint>

/* Process-local call observations, not queue-generation or completion proof.
 * Install/remove only while all producers are quiescent. The observer and its
 * user data must outlive every call; callbacks cannot mutate guest state,
 * block, allocate, perform I/O, or re-enter the runtime. */
enum class job_queue_operation : std::uint32_t { reset = 1, init = 2, add_job = 3 };
// Returned records the host wrapper return, including any deferred work.
// A call pair alone does not establish guest completion or queue generation.
enum class job_queue_phase : std::uint32_t { enter = 1, returned = 2 };
struct job_queue_event {
    std::uint64_t call_id;
    std::uintptr_t context;
    std::uint32_t object, argument;
    job_queue_operation operation;
    job_queue_phase phase;
    std::uint64_t header;
    std::uint64_t entry_lr; // raw guest LR at wrapper entry
};
struct job_queue_observer {
    void* user;
    void (*event)(void*, const job_queue_event&) noexcept;
};
bool job_queue_observer_install(const job_queue_observer*) noexcept;
