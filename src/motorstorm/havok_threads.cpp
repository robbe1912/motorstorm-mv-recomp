#include "ppu_recomp.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>

void game_original_init_multithreading(ppu_context*);

namespace {
// Guest function hkMultithreadingUtil::initMultithreading(hkWorld*, int) 0xA01220:
// r3 = this, r4 = world, r5 = worker count. The guest clamps the count to 6
// (0xA0124C). The worker array has 6 entries of 72 bytes (0xA02C68).
constexpr std::uint32_t worker_limit = 6;
// this->m_numThreads. The guest counts one started worker per entry.
constexpr std::uint32_t num_threads_offset = 0x214;

// 0 keeps the game count. 1..6 is the worker count.
std::uint32_t requested() {
    static const std::uint32_t value = [] {
        const char* text = std::getenv("MS_HAVOK_THREADS");
        if (!text || std::strcmp(text, "0") == 0) return 0u;
        char* end = nullptr;
        const long count = std::strtol(text, &end, 10);
        if (*end != '\0' || count < 1 || count > static_cast<long>(worker_limit))
            throw std::runtime_error("MS_HAVOK_THREADS must be 0 or 1..6");
        return static_cast<std::uint32_t>(count);
    }();
    return value;
}
}

void motorstorm_havok_threads(ppu_context* context) {
    const std::uint32_t game = static_cast<std::uint32_t>(context->gpr[5]);
    const std::uint32_t set = requested();
    // r3 is volatile. Save it before the guest call.
    const std::uint64_t util = context->gpr[3];
    if (set != 0) context->gpr[5] = set;
    game_original_init_multithreading(context);
    // The lifted function ends with a tail call. The lifted caller drains it.
    const std::uint32_t workers = vm_read32(util + num_threads_offset);
    std::fprintf(stderr, "[HAVOK_THREADS] game=%u set=%u workers=%u\n", game, set, workers);
}
