#ifdef MOTORSTORM_JOB_WAIT_FIXTURE
#include "native_job_wait_api.h"
#else
#include "ppu_recomp.h"
#endif
#include "job_wait.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>
#if defined(_WIN32) && !defined(MOTORSTORM_JOB_WAIT_FIXTURE)
#include <Windows.h>
#else
#include <chrono>
#include <thread>
#endif

void game_original_job_marker_wait(ppu_context*);
namespace {
struct State {
    bool enabled = true;
    std::atomic<std::uint64_t> calls{0}, polls{0}, cooperations{0}, fallbacks{0};
    State() {
        const char* mode = std::getenv("MS_NATIVE_JOB_WAIT");
        if (mode && std::strcmp(mode, "0") && std::strcmp(mode, "1"))
            throw std::runtime_error("MS_NATIVE_JOB_WAIT must be 0 or 1");
        enabled = !mode || std::strcmp(mode, "0");
        std::fprintf(stderr, "[native-job-wait] enabled=%d\n", enabled ? 1 : 0);
    }
};
State& state() { static State value; return value; }

motorstorm::game::JobProgressStart begin(void* user) {
    auto* ctx = static_cast<ppu_context*>(user);
    const std::uint32_t owner = vm_read32(ctx->gpr[3] + 4);
    if (!owner || std::uint64_t(owner) + 32 > 0x100000000ULL)
        throw std::runtime_error("Unsupported job progress ownership range");
    return {owner, vm_read16(owner + 18)};
}
void barrier(void*) { std::atomic_thread_fence(std::memory_order_seq_cst); }
std::uint16_t active(void*, std::uint32_t owner, unsigned lane) {
    return vm_read16(owner + 20 + lane*2);
}
void cooperate(void*) {
#ifdef MOTORSTORM_JOB_WAIT_FIXTURE
    native_job_wait_fixture_cooperate();
#elif defined(_WIN32)
    struct Timer {
        HANDLE handle;
        Timer() {
            // Win10 1803+ high-resolution timer; a failure remains visible and
            // returns control to the retained original operation.
            handle = CreateWaitableTimerExW(nullptr, nullptr, 0x2, TIMER_MODIFY_STATE | SYNCHRONIZE);
            if (!handle) throw std::runtime_error("Native job timer creation failed: " + std::to_string(GetLastError()));
        }
        ~Timer() { CloseHandle(handle); }
    };
    thread_local Timer timer;
    LARGE_INTEGER due; due.QuadPart = -1000; // Relative 100 microseconds.
    if (!SetWaitableTimer(timer.handle, &due, 0, nullptr, nullptr, FALSE))
        throw std::runtime_error("Native job timer setup failed: " + std::to_string(GetLastError()));
    if (WaitForSingleObject(timer.handle, INFINITE) != WAIT_OBJECT_0)
        throw std::runtime_error("Native job timer wait failed: " + std::to_string(GetLastError()));
#else
    std::this_thread::sleep_for(std::chrono::microseconds(100));
#endif
}
}

void motorstorm_job_marker_wait(ppu_context* ctx) {
    State* runtime = nullptr;
    try {
        runtime = &state();
        if (runtime->enabled) {
            const auto marker = static_cast<std::uint32_t>(ctx->gpr[4]);
            const auto result = motorstorm::game::wait_for_job_marker(
                {ctx, begin, barrier, active, cooperate}, marker);
            // Preserve the actual AOT return state as well as the game ABI.
            ctx->gpr[0] = ctx->gpr[11] = result.minimum;
            ctx->gpr[8] = result.owner;
            ctx->gpr[9] = std::uint64_t(result.owner) + 26;
            ctx->gpr[10] = 6;
            ctx->ctr = 0;
            ctx->cr = (ctx->cr & ~0xfu) | (marker < result.minimum ? 8u : 2u);
            const auto polls = runtime->polls.fetch_add(result.polls) + result.polls;
            const auto cooperations = runtime->cooperations.fetch_add(result.cooperations) + result.cooperations;
            const auto calls = ++runtime->calls;
            if (calls <= 4 || (calls % 256) == 0)
                std::fprintf(stderr, "[native-job-wait] completed=%llu polls=%llu cooperations=%llu fallbacks=%llu\n",
                    static_cast<unsigned long long>(calls), static_cast<unsigned long long>(polls),
                    static_cast<unsigned long long>(cooperations), static_cast<unsigned long long>(runtime->fallbacks.load()));
            return;
        }
    } catch (const std::exception& error) {
        if (runtime) ++runtime->fallbacks;
        std::fprintf(stderr, "[native-job-wait] ORIGINAL fallback: %s\n", error.what());
    }
    game_original_job_marker_wait(ctx);
}
