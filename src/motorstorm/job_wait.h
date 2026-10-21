#pragma once
#include <cstdint>

namespace motorstorm::game {
struct JobProgressStart { std::uint32_t owner; std::uint16_t taken; };
struct JobProgressSource {
    void* user;
    JobProgressStart (*begin)(void*);
    void (*full_barrier)(void*);
    std::uint16_t (*active)(void*, std::uint32_t owner, unsigned lane);
    void (*cooperate)(void*);
};
struct JobWaitResult {
    std::uint32_t owner;
    std::uint16_t minimum;
    std::uint64_t polls, cooperations;
};

// Resolve ownership on every poll. Read taken BEFORE the full barrier, then all
// six active lanes. Completion is unsigned and has no synthetic deadline.
JobWaitResult wait_for_job_marker(const JobProgressSource&, std::uint32_t marker);
}
