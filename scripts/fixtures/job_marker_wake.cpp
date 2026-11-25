// Authored fixture of the marker wake (SPURS_MARKER_WAKE=1). The check compiles the
// production adapter with the stand-in ppu_recomp.h of this directory and this
// file. A job list lives at guest address 0x5000: taken at +18, active at +20 to
// +31, all in the 128-byte line 0x5000. The check compiles with
// MOTORSTORM_JOB_WAIT_WAKE_FALLBACK_MS=200, so that a lost wake shows as a wait of
// 200 ms. Prints one record per scenario.
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <thread>
#include <Windows.h>
#include "ps3emu/spu_host_line_commit.h"
#include "ppu_recomp.h"

void motorstorm_job_marker_wait(ppu_context*);
void game_original_job_marker_wait(ppu_context*) { std::fprintf(stderr, "original fallback\n"); }
// The runtime defines this pointer. The adapter installs its hook with SPURS_MARKER_WAKE=1.
extern "C" { void (*g_spu_host_line_commit_hook)(std::uint32_t) = nullptr; }

namespace {
std::atomic<unsigned> g_taken{1}, g_active{0};
// Scenario "stale": the first 64 reads of taken return 1. The read of the last lane
// of the 64th poll completes the marker and reports the commit: taken was read
// before the commit, so the poll does not see the completion.
bool g_hold_taken = false;
unsigned g_taken_reads = 0;

std::uint64_t now_ms() {
    return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

ppu_context context() {
    ppu_context ctx;
    std::memset(&ctx, 0xa5, sizeof(ctx));
    ctx.gpr[3] = 0x1000;   // wait object: the job list address is at +4
    ctx.gpr[4] = 3;        // marker 3
    return ctx;
}

void complete() {
    g_active = 3;          // the six lanes read one value
    g_taken = 3;
}

void report(const char* scenario, std::uint64_t elapsed, const ppu_context& ctx) {
    std::printf("[job_marker_wake] scenario=%s elapsed=%llu complete=%d\n", scenario,
                static_cast<unsigned long long>(elapsed), ctx.gpr[0] == 3 ? 1 : 0);
}

// Scenarios "wake" and "fallback": the counters complete after 20 ms. With report
// set, the runtime reports the commit of the job list line.
void scenario_commit(bool report_commit) {
    g_taken = 1; g_active = 0;
    std::thread commit([report_commit] {
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
        complete();
        if (report_commit && g_spu_host_line_commit_hook) g_spu_host_line_commit_hook(0x5000);
    });
    const auto start = now_ms();
    auto ctx = context();
    motorstorm_job_marker_wait(&ctx);
    const auto elapsed = now_ms() - start;
    commit.join();
    report(report_commit ? "wake" : "fallback", elapsed, ctx);
}

void scenario_stale() {
    g_taken = 1; g_active = 0; g_taken_reads = 0; g_hold_taken = true;
    const auto start = now_ms();
    auto ctx = context();
    motorstorm_job_marker_wait(&ctx);
    report("stale", now_ms() - start, ctx);
}
}

std::uint32_t vm_read32(std::uint64_t address) { return address == 0x1004 ? 0x5000u : 0u; }
std::uint16_t vm_read16(std::uint64_t address) {
    if (address == 0x5000 + 20 + 5 * 2 && g_hold_taken && g_taken_reads >= 64) {
        g_hold_taken = false;
        complete();
        if (g_spu_host_line_commit_hook) g_spu_host_line_commit_hook(0x5000);
        return static_cast<std::uint16_t>(g_active.load());
    }
    if (address == 0x5000 + 18 && g_hold_taken && ++g_taken_reads <= 64) return 1;
    if (address == 0x5000 + 18) return static_cast<std::uint16_t>(g_taken.load());
    return static_cast<std::uint16_t>(g_active.load());
}

int main() {
    std::printf("[job_marker_wake] installed=%d\n", g_spu_host_line_commit_hook ? 1 : 0);
    scenario_commit(true);
    scenario_commit(false);
    scenario_stale();
    return 0;
}
