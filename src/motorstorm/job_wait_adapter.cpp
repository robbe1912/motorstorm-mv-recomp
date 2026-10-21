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
#include <functional>
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
    bool profile = false;
    std::atomic<std::uint64_t> calls{0}, polls{0}, cooperations{0}, fallbacks{0};
    State() {
        const char* mode = std::getenv("MS_NATIVE_JOB_WAIT");
        if (mode && std::strcmp(mode, "0") && std::strcmp(mode, "1"))
            throw std::runtime_error("MS_NATIVE_JOB_WAIT must be 0 or 1");
        enabled = !mode || std::strcmp(mode, "0");
        const char* profiling = std::getenv("MS_NATIVE_JOB_WAIT_PROFILE");
        if (profiling && std::strcmp(profiling, "0") && std::strcmp(profiling, "1"))
            throw std::runtime_error("MS_NATIVE_JOB_WAIT_PROFILE must be 0 or 1");
        profile = profiling && !std::strcmp(profiling, "1");
        std::fprintf(stderr, "[native-job-wait] enabled=%d profile=%d\n", enabled ? 1 : 0, profile ? 1 : 0);
    }
};
State& state() { static State value; return value; }

struct Tick { std::uint64_t value = 0, frequency = 0; };
bool profile_clock(Tick& tick) noexcept {
#ifdef MOTORSTORM_JOB_WAIT_FIXTURE
    return native_job_wait_fixture_clock(tick.value, tick.frequency);
#elif defined(_WIN32)
    LARGE_INTEGER counter, frequency;
    if (!QueryPerformanceCounter(&counter) || !QueryPerformanceFrequency(&frequency) ||
        counter.QuadPart < 0 || frequency.QuadPart <= 0) return false;
    tick = {static_cast<std::uint64_t>(counter.QuadPart), static_cast<std::uint64_t>(frequency.QuadPart)};
    return true;
#else
    const auto count = std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    if (count < 0) return false;
    tick = {static_cast<std::uint64_t>(count), 1000000000};
    return true;
#endif
}
std::uint64_t profile_thread() noexcept {
#ifdef MOTORSTORM_JOB_WAIT_FIXTURE
    return native_job_wait_fixture_thread();
#elif defined(_WIN32)
    return GetCurrentThreadId();
#else
    return std::hash<std::thread::id>{}(std::this_thread::get_id());
#endif
}
void report_wait(std::uint64_t caller, std::uint64_t object, std::uint32_t marker,
                 const motorstorm::game::JobWaitResult& result, const Tick& start, bool start_ok) noexcept {
    Tick finish;
    const bool finish_ok = profile_clock(finish);
    const bool valid = start_ok && finish_ok && start.frequency &&
        start.frequency == finish.frequency && finish.value >= start.value;
    // A failed diagnostic never repeats completed game work or invents elapsed time.
    if (!valid) {
        std::fprintf(stderr, "[NATIVE_JOB_WAIT_PROFILE] status=clock_error caller=0x%llx object=0x%llx marker=%u started=%llu finished=%llu frequency=%llu end_frequency=%llu start_ok=%d finish_ok=%d\n",
            static_cast<unsigned long long>(caller), static_cast<unsigned long long>(object), marker,
            static_cast<unsigned long long>(start.value), static_cast<unsigned long long>(finish.value),
            static_cast<unsigned long long>(start.frequency), static_cast<unsigned long long>(finish.frequency),
            start_ok ? 1 : 0, finish_ok ? 1 : 0);
        return;
    }
    std::fprintf(stderr, "[NATIVE_JOB_WAIT_PROFILE] status=complete thread=%llu caller=0x%llx object=0x%llx owner=0x%x marker=%u minimum=%u started=%llu finished=%llu frequency=%llu ticks=%llu polls=%llu cooperations=%llu\n",
        static_cast<unsigned long long>(profile_thread()), static_cast<unsigned long long>(caller),
        static_cast<unsigned long long>(object), result.owner, marker, static_cast<unsigned>(result.minimum),
        static_cast<unsigned long long>(start.value), static_cast<unsigned long long>(finish.value),
        static_cast<unsigned long long>(start.frequency), static_cast<unsigned long long>(finish.value - start.value),
        static_cast<unsigned long long>(result.polls), static_cast<unsigned long long>(result.cooperations));
}

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
            const auto caller = ctx->lr, object = ctx->gpr[3];
            Tick start;
            const bool start_ok = runtime->profile && profile_clock(start);
            const auto result = motorstorm::game::wait_for_job_marker(
                {ctx, begin, barrier, active, cooperate}, marker);
            if (runtime->profile) report_wait(caller, object, marker, result, start, start_ok);
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
    if (runtime && runtime->profile)
        std::fprintf(stderr, "[NATIVE_JOB_WAIT_PROFILE] status=%s caller=0x%llx object=0x%llx marker=%u\n",
            runtime->enabled ? "original" : "reference", static_cast<unsigned long long>(ctx->lr),
            static_cast<unsigned long long>(ctx->gpr[3]), static_cast<std::uint32_t>(ctx->gpr[4]));
    game_original_job_marker_wait(ctx);
}
