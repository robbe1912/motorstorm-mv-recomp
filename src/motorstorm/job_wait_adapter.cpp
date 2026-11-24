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

#ifndef MOTORSTORM_JOB_WAIT_FIXTURE
// SPURS_WAIT_PRIORITY=1: the runtime asks for the job list that a PPU thread waits on.
extern "C" void spurs_wait_priority_set(std::uint64_t (*job_list)(void*), void* context);
#endif
#ifndef MOTORSTORM_JOB_WAIT_FIXTURE
#include "ps3emu/spu_host_line_commit.h"   // SPURS_MARKER_WAKE=1: each commit of a guest line
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
        const char* wake = std::getenv("SPURS_MARKER_WAKE");
        if (wake && std::strcmp(wake, "0") && std::strcmp(wake, "1"))
            throw std::runtime_error("SPURS_MARKER_WAKE must be 0 or 1");
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

// SPURS_WAIT_PRIORITY=1: the job list that a marker wait of this process
// waits on, 0 for none. The coordinator of the runtime reads it.
std::atomic<std::uint32_t> wait_priority_owner{0};
std::uint64_t wait_priority_job_list(void*) noexcept {
    return wait_priority_owner.load(std::memory_order_acquire);
}
// Clears the waited job list when the marker wait ends, also when it throws.
struct WaitPriority {
    ~WaitPriority() { wait_priority_owner.store(0, std::memory_order_release); }
    WaitPriority() = default;
    WaitPriority(const WaitPriority&) = delete;
    WaitPriority& operator=(const WaitPriority&) = delete;
};
// SPURS_MARKER_WAKE=1: the marker wait ends when a job list line commits.
// Windows puts a step below each timed wait. On one host a high-resolution
// waitable timer waits 0.52 ms for a due of 100 us. A wake from another
// thread has no step.
// MOTORSTORM_JOB_WAIT_WAKE_FALLBACK_MS: the fallback time of the wait in
// milliseconds. 0 keeps the step of the timer path, 100 us. A commit through
// another path ends the wait after that time.
#ifndef MOTORSTORM_JOB_WAIT_WAKE_FALLBACK_MS
#define MOTORSTORM_JOB_WAIT_WAKE_FALLBACK_MS 0
#endif
#if defined(_WIN32) && !defined(MOTORSTORM_JOB_WAIT_FIXTURE)
// The lines of the counters of the waited job list: taken at +18, active at
// +20 to +31. The first line is 0 when no thread waits.
std::atomic<std::uint32_t> marker_wake_first{0}, marker_wake_last{0}, marker_wake_generation{0};
// Set while a thread waits on the event.
std::atomic<bool> marker_wake_waiting{false};
// Auto-reset event of the wake: the callback sets it, the wait consumes it.
HANDLE const marker_wake_event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
bool marker_wake_on() {
    static const bool on = [] {
        const char* mode = std::getenv("SPURS_MARKER_WAKE");
        return mode && !std::strcmp(mode, "1");
    }();
    return on;
}
// The runtime calls this after a committing PUTLLC on `line`, outside its line lock.
void marker_wake_commit(std::uint32_t line) noexcept {
    const std::uint32_t first = marker_wake_first.load(std::memory_order_acquire);
    const std::uint32_t number = line >> 7;
    if (!first || number < first || number > marker_wake_last.load(std::memory_order_relaxed)) return;
    marker_wake_generation.fetch_add(1, std::memory_order_release);
    // The wait counts the commit before it reads the flag, so it never sleeps
    // through this one.
    if (marker_wake_waiting.load(std::memory_order_acquire)) SetEvent(marker_wake_event);
}
// Ends when a job list line commits, or when `timer` ends the fallback time.
void marker_wake_wait(HANDLE timer) {
    thread_local std::uint32_t seen = 0;
    const auto now = marker_wake_generation.load(std::memory_order_acquire);
    // A commit since the last wait ends this wait at once: the loop polls again.
    if (now != seen) { seen = now; return; }
    marker_wake_waiting.store(true, std::memory_order_release);
    // A commit between the read above and the flag does not set the event.
    if (marker_wake_generation.load(std::memory_order_acquire) != seen) {
        marker_wake_waiting.store(false, std::memory_order_release);
        seen = marker_wake_generation.load(std::memory_order_acquire);
        return;
    }
    LARGE_INTEGER due;
#if MOTORSTORM_JOB_WAIT_WAKE_FALLBACK_MS > 0
    due.QuadPart = -10000LL * MOTORSTORM_JOB_WAIT_WAKE_FALLBACK_MS;   // Relative milliseconds.
#else
    due.QuadPart = -1000;   // Relative 100 microseconds, the step of the timer path.
#endif
    if (!SetWaitableTimer(timer, &due, 0, nullptr, nullptr, FALSE)) {
        marker_wake_waiting.store(false, std::memory_order_release);
        throw std::runtime_error("Native job timer setup failed: " + std::to_string(GetLastError()));
    }
    HANDLE handles[2] = { marker_wake_event, timer };
    const DWORD wait = WaitForMultipleObjects(2, handles, FALSE, INFINITE);
    marker_wake_waiting.store(false, std::memory_order_release);
    if (wait != WAIT_OBJECT_0 && wait != WAIT_OBJECT_0 + 1)
        throw std::runtime_error("Native job timer wait failed: " + std::to_string(GetLastError()));
    seen = marker_wake_generation.load(std::memory_order_acquire);
}
// Installs the hook before any SPU thread runs.
struct MarkerWakeRegistration {
    MarkerWakeRegistration() { if (marker_wake_on()) g_spu_host_line_commit_hook = &marker_wake_commit; }
} const marker_wake_registration;
#endif

motorstorm::game::JobProgressStart begin(void* user) {
    auto* ctx = static_cast<ppu_context*>(user);
    const std::uint32_t owner = vm_read32(ctx->gpr[3] + 4);
    if (!owner || std::uint64_t(owner) + 32 > 0x100000000ULL)
        throw std::runtime_error("Unsupported job progress ownership range");
    // SPURS_WAIT_PRIORITY=1: the runtime gives the workload of this job list a free lane first.
    wait_priority_owner.store(owner, std::memory_order_release);
#if defined(_WIN32) && !defined(MOTORSTORM_JOB_WAIT_FIXTURE)
    // SPURS_MARKER_WAKE=1: a commit on a line of the counters of this job list ends the wait.
    // The last line goes first: the callback starts at a nonzero first line.
    if (marker_wake_on()) {
        marker_wake_last.store((owner + 31) >> 7, std::memory_order_release);
        marker_wake_first.store((owner + 18) >> 7, std::memory_order_release);
    }
#endif
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
    if (marker_wake_on()) { marker_wake_wait(timer.handle); return; }
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
#ifndef MOTORSTORM_JOB_WAIT_FIXTURE
            static const bool registered = [] { spurs_wait_priority_set(wait_priority_job_list, nullptr); return true; }();
            (void)registered;
#endif
            const auto marker = static_cast<std::uint32_t>(ctx->gpr[4]);
            const auto caller = ctx->lr, object = ctx->gpr[3];
            Tick start;
            const bool start_ok = runtime->profile && profile_clock(start);
            const WaitPriority priority;   // the waited job list is cleared when the wait ends
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
