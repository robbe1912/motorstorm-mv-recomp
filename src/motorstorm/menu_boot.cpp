#include "ppu_recomp.h"
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>

extern "C" thread_local void (*g_trampoline_fn)(void*);

void game_original_start_video(ppu_context*);
void game_original_language_event(ppu_context*);
void func_0050C5A0(ppu_context*); // StopVideo.
void func_005340A8(ppu_context*); // Accept the selected language.

namespace {
std::atomic<bool> opening_skipped{false};
std::atomic<bool> language_accepted{false};

bool enabled() {
    static const bool value = [] {
        const char* mode = std::getenv("MS_BOOT_MENU");
        if (mode && std::strcmp(mode, "0") && std::strcmp(mode, "1"))
            throw std::runtime_error("MS_BOOT_MENU must be 0 or 1");
        return !mode || std::strcmp(mode, "0") != 0;
    }();
    return value;
}

bool opening_caller(std::uint64_t return_pc) {
    // Original StartVideo_Intro callsites, verified against the selected ELF.
    switch (return_pc) {
    case 0x50da44:
    case 0x50db84:
    case 0x50dc4c:
    case 0x50dd60:
    case 0x50dde0:
    case 0x50df64:
    case 0x50e014:
        return true;
    default:
        return false;
    }
}

void complete_calls(ppu_context* context) {
    while (g_trampoline_fn) {
        auto next = g_trampoline_fn;
        g_trampoline_fn = nullptr;
        next(context);
    }
}
}

void motorstorm_boot_start_video(ppu_context* context) {
    if (enabled() && opening_caller(context->lr) &&
        !opening_skipped.exchange(true, std::memory_order_acq_rel)) {
        func_0050C5A0(context);
        complete_calls(context);
        std::fprintf(stderr, "[boot-menu] opening video closed, original completion transition retained\n");
        return;
    }
    game_original_start_video(context);
}

void motorstorm_boot_language_event(ppu_context* context) {
    if (enabled() && context->lr == 0x56bec0 &&
        static_cast<std::uint32_t>(context->gpr[4]) == 0x30 &&
        !opening_skipped.load(std::memory_order_acquire) &&
        !language_accepted.exchange(true, std::memory_order_acq_rel)) {
        func_005340A8(context);
        complete_calls(context);
        std::fprintf(stderr, "[boot-menu] configured language accepted through original handler\n");
        return;
    }
    game_original_language_event(context);
}
