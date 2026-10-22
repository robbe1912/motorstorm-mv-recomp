#include "native_visibility_api.h"
#include "native_cpu.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <csignal>
#include <memory>
#include <initializer_list>
#include <stdexcept>
#include <string>
#include <immintrin.h>

namespace {
void require(bool yes, const char* message) {
    if (!yes) { std::fprintf(stderr, "FAIL %s\n", message); std::exit(1); }
}
bool cpu = true, matches = true, spy = false;
unsigned hook = 0, real_calls = 0;
spu_context* real_context = nullptr;
std::unique_ptr<spu_context> expected_entry;
void put_float(unsigned char* p, float value) {
    std::uint32_t word; std::memcpy(&word, &value, 4);
    for (unsigned j = 0; j < 4; ++j) p[j] = static_cast<unsigned char>(word >> (24 - 8 * j));
}
float offset(const unsigned char* p) {
    const std::uint32_t word = (std::uint32_t(p[0]) << 24) | (std::uint32_t(p[1]) << 16) |
                               (std::uint32_t(p[2]) << 8) | p[3];
    float value; std::memcpy(&value, &word, 4); return value;
}
std::unique_ptr<spu_context> entry(unsigned count, unsigned fail) {
    auto ctx = std::make_unique<spu_context>();
    for (unsigned r = 0; r < 128; ++r) for (unsigned lane = 0; lane < 4; ++lane)
        ctx->gpr[r]._u32[lane] = 0xff123450u + r * 37 + lane;
    constexpr unsigned coefficients[] = {19,41,40,18,39,38,17,37,36,16,35,34,
                                        15,33,32,22,31,30,20,29,28,21,27,26};
    for (auto r : coefficients) for (auto& word : ctx->gpr[r]._u32) word = 0;
    for (auto& word : ctx->gpr[13]._u32) word = 0;
    ctx->gpr[0]._u32[0] = 0x300;
    ctx->gpr[14]._u32[0] = 0x10000;
    ctx->gpr[23]._u32[0] = 7; ctx->gpr[25]._u32[0] = 7 + count;
    ctx->ls = ctx->ls_store; ctx->pc = 0x84a0; ctx->status = 1;
    ctx->int_enable = 1; ctx->event_mask = 2; ctx->host_depth = count & 1;
    for (unsigned i = 0; i < count; ++i) put_float(ctx->ls + 0x10000 + i * 16 + 12, i == fail ? -1.f : 1.f);
    return ctx;
}
using Function = void (*)(spu_context*);
Function drain(spu_context* ctx, bool retained) {
    Function next = jobmod_056ac0eea1a6_e12270_spu_func_000084A0;
    for (unsigned step = 0; step < 140; ++step) {
        if (retained && next == jobmod_056ac0eea1a6_e12270_spu_func_000084A0)
            next = game_original_visibility_planes;
        g_spu_trampoline_fn = nullptr; next(ctx); next = g_spu_trampoline_fn;
        if (ctx->pc == 0x300 && (!next || next == spu_indirect_branch)) return next;
        require(next != nullptr, "Unexpected missing operation continuation");
    }
    throw std::runtime_error("Authored operation exceeded bound");
}
void expect_original(spu_context* ctx) {
    real_context = ctx; real_calls = 0; spy = true;
    expected_entry = ctx ? std::make_unique<spu_context>(*ctx) : nullptr;
    motorstorm_visibility_planes(ctx);
    require(real_calls == 1, "Retained original executes exactly once");
    spy = false; expected_entry.reset();
}
} // namespace

extern "C" {
thread_local void (*g_spu_trampoline_fn)(spu_context*) = nullptr;
int g_spu_ls_watch_n = 0;
void spu_indirect_branch(spu_context*) { throw std::runtime_error("Unexpected caller dispatch"); }
int game_visibility_code_matches(const spu_context*) { return matches; }
void jobmod_056ac0eea1a6_e12270_spu_func_000084A0(spu_context* ctx) { motorstorm_visibility_planes(ctx); }
void jobmod_056ac0eea1a6_e12270_spu_func_00008440(spu_context* ctx) {
    for (auto& word : ctx->gpr[3]._u32) word = 0;
    ctx->pc = ctx->gpr[0]._u32[0];
    if (!ctx->host_depth) g_spu_trampoline_fn = spu_indirect_branch;
}
void jobmod_056ac0eea1a6_e12270_spu_func_0000849C(spu_context* ctx) {
    if (ctx->gpr[23]._u32[0] >= ctx->gpr[25]._u32[0]) {
        ctx->pc = 0x8440; g_spu_trampoline_fn = jobmod_056ac0eea1a6_e12270_spu_func_00008440;
    } else { ctx->pc = 0x84a0; g_spu_trampoline_fn = jobmod_056ac0eea1a6_e12270_spu_func_000084A0; }
}
// Independent authored offset-only geometry and observable ABI model. Actual
// instruction/context parity is a separate private original-reference check.
void game_original_visibility_planes(spu_context* ctx) {
    if (ctx == real_context) ++real_calls;
    if (spy) {
        require(!ctx || (expected_entry && !std::memcmp(ctx, expected_entry.get(), sizeof(*ctx))),
                "Original fallback has no partial guest writes");
        return;
    }
    const auto pointer = ctx->gpr[14]._u32[0];
    const bool fails = offset(ctx->ls + pointer + 12) < 0;
    for (unsigned lane = 0; lane < 4; ++lane) {
        ctx->gpr[14]._u32[lane] += 16; ++ctx->gpr[23]._u32[lane];
        ctx->gpr[45]._u32[lane] = ctx->gpr[14]._u32[lane] ^ ctx->gpr[23]._u32[lane];
    }
    if (fails) {
        for (auto& word : ctx->gpr[3]._u32) word = 1;
        ctx->pc = ctx->gpr[0]._u32[0];
        if (!ctx->host_depth) g_spu_trampoline_fn = spu_indirect_branch;
    } else { ctx->pc = 0x849c; g_spu_trampoline_fn = jobmod_056ac0eea1a6_e12270_spu_func_0000849C; }
}
}
bool native_visibility_fixture_cpu() { return cpu; }
void native_visibility_fixture_after_math(spu_context* ctx) {
    if (hook == 1) { ctx->event_status |= 2; if (expected_entry) expected_entry->event_status |= 2; }
    if (hook == 2) { ctx->ls[0x10000] ^= 1; if (expected_entry) expected_entry->ls_store[0x10000] ^= 1; }
}

int main(int argc, char** argv) { try {
    std::signal(SIGABRT, [](int) { std::_Exit(86); }); // Fatal mutant, no modal crash UI.
    if (!motorstorm::game::supports_native_world_transforms()) {
        std::fputs("Unsupported AVX2/FMA/OS host\n", stderr); return 77;
    }
    const std::string mode = std::getenv("MS_NATIVE_VISIBILITY") ? std::getenv("MS_NATIVE_VISIBILITY") : "0";
    const std::string command = argc > 1 ? argv[1] : "all";
    if (command == "invalid") {
        auto ctx = entry(2, 2);
        motorstorm_visibility_planes(ctx.get());
        throw std::runtime_error("Invalid mode was accepted");
    }
    if (command == "unsupported" || command == "instrumented") {
        cpu = command != "unsupported"; auto ctx = entry(2, 2); expect_original(ctx.get());
        std::puts("PASS unsupported/instrumented original"); return 0;
    }
    if (command == "scratch_only") {
        auto ctx = entry(3, 3); ctx->gpr[13]._u32[1] = 0x7f800001;
        expect_original(ctx.get()); std::puts("PASS nonpreferred scratch range fallback"); return 0;
    }
    if (command != "guard_only") for (unsigned rounding = 0; rounding < 4; ++rounding)
        for (unsigned count : {1u, 2u, 3u, 4u, 5u, 6u, 64u}) for (unsigned fail = 0; fail <= count; ++fail) {
        if (count == 64 && fail != 0 && fail != 63 && fail != 64) continue;
        const auto saved = _mm_getcsr(); _mm_setcsr((saved & ~0x6000u) | (rounding << 13) | 0x20u);
        auto ctx = entry(count, fail); auto reference = std::make_unique<spu_context>(*ctx); reference->ls = reference->ls_store;
        const auto expected_exit = drain(reference.get(), true);
        real_context = ctx.get(); real_calls = 0;
        const auto caller = _mm_getcsr(); const auto actual_exit = drain(ctx.get(), false);
        require(_mm_getcsr() == caller, "Caller FP state preserved");
        ctx->ls = reference->ls;
        require(actual_exit == expected_exit && !std::memcmp(ctx.get(), reference.get(), sizeof(*ctx)), "Adapter full-context parity");
        require(mode != "1" || real_calls == 1, "Native retains one decisive iteration");
        _mm_setcsr(saved);
    }
    if (mode == "0") { std::puts("PASS reference context"); return 0; }
    auto ctx = entry(3, 3);
    if (command != "guard_only") {
        expect_original(nullptr);
        auto raw = std::make_unique<unsigned char[]>(0x40000); ctx->ls = raw.get(); expect_original(ctx.get()); ctx->ls = ctx->ls_store;
        ctx->pc = 0x90; expect_original(ctx.get()); ctx->pc = 0x84a0;
        ctx->status = 0; expect_original(ctx.get()); ctx->status = 1;
        ctx->list_stall_mask = 1; expect_original(ctx.get()); ctx->list_stall_mask = 0;
        ctx->event_status = 2; expect_original(ctx.get()); ctx->event_status = 0;
        matches = false; expect_original(ctx.get()); matches = true;
        g_spu_ls_watch_n = 1; expect_original(ctx.get()); g_spu_ls_watch_n = 0;
        ctx->gpr[14]._u32[0] = 0x10001; expect_original(ctx.get());
        ctx->gpr[14]._u32[0] = 0x3fff0; expect_original(ctx.get()); ctx->gpr[14]._u32[0] = 0x10000;
        ctx->gpr[25]._u32[0] = 7; expect_original(ctx.get());
        ctx->gpr[25]._u32[0] = 72; expect_original(ctx.get()); ctx->gpr[25]._u32[0] = 10;
        ctx->gpr[13]._u32[0] = 0x7fc00000; expect_original(ctx.get()); ctx->gpr[13]._u32[0] = 0;
        ctx->gpr[13]._u32[1] = 0x7f800001; expect_original(ctx.get()); ctx->gpr[13]._u32[1] = 0;
        ctx->gpr[19]._u32[3] = 0x7f7fffff; expect_original(ctx.get()); ctx->gpr[19]._u32[3] = 0;
    }
    hook = 1; expect_original(ctx.get()); hook = 0; ctx->event_status = 0;
    hook = 2; expect_original(ctx.get()); hook = 0;
    std::puts("PASS adapter full-context/ownership/IRQ/span/code/instrumentation/transaction guards"); return 0;
} catch (const std::exception& error) { std::fprintf(stderr, "FAIL %s\n", error.what()); return 1; } }
