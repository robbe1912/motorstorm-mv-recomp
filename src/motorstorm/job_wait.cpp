#include "job_wait.h"
#include <stdexcept>

namespace motorstorm::game {
JobWaitResult wait_for_job_marker(const JobProgressSource& source, std::uint32_t marker) {
    if (!source.begin || !source.full_barrier || !source.active || !source.cooperate || marker > 0xffffu)
        throw std::invalid_argument("Unsupported job progress source or marker");
    JobWaitResult result{};
    for (;;) {
        const auto start = source.begin(source.user);
        result.owner = start.owner;
        result.minimum = start.taken;
        source.full_barrier(source.user);
        for (unsigned lane = 0; lane < 6; ++lane) {
            const auto value = source.active(source.user, start.owner, lane);
            if (value < result.minimum) result.minimum = value;
        }
        ++result.polls;
        if (result.minimum >= marker) return result;
        if (result.polls >= 64) {
            source.cooperate(source.user);
            ++result.cooperations;
        }
    }
}
}
