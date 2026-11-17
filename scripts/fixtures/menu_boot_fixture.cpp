#include "ppu_recomp.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>

void motorstorm_boot_start_video(ppu_context *);
void motorstorm_boot_language_event(ppu_context *);
extern "C" {
thread_local void (*g_trampoline_fn)(void *) = nullptr;
}

static unsigned starts, closes, accepts, events;
static bool playing;
static bool deferred;

static void check(bool condition, const char *message) {
    if (!condition) {
        std::fprintf(stderr, "FAIL %s\n", message);
        std::exit(1);
    }
}

void game_original_start_video(ppu_context *) {
    ++starts;
    playing = true;
}
void game_original_language_event(ppu_context *) { ++events; }
static void finish_close(void *) { playing = false; }
void func_0050C5A0(ppu_context *context) {
    ++closes;
    if (deferred)
        g_trampoline_fn = finish_close;
    else
        finish_close(context);
}
static void finish_accept(void *raw) {
    auto *context = static_cast<ppu_context *>(raw);
    context->gpr[3] = 4;
}
void func_005340A8(ppu_context *context) {
    ++accepts;
    check(context->gpr[3] == 0x1234, "language object preserved");
    if (deferred)
        g_trampoline_fn = finish_accept;
    else
        finish_accept(context);
}

static int run_fixture(int argc, char **argv) {
    check(argc >= 2, "fixture mode");
    deferred = argc > 2;
    ppu_context context{};
    context.gpr[1] = 0x900000;
    context.gpr[2] = 0xe8a6c0;
    context.gpr[3] = 0x1234;
    context.gpr[4] = 0x30;
    const auto initial = context;
    if (!std::strcmp(argv[1], "language")) {
        context.lr = 0x600000;
        motorstorm_boot_language_event(&context);
        check(accepts == 0 && events == 1, "foreign language caller forwarded");
        context.lr = 0x56bec0;
        context.gpr[4] = 3;
        motorstorm_boot_language_event(&context);
        check(accepts == 0 && events == 2, "non-update event forwarded");
        context.gpr[4] = 0x30;
        motorstorm_boot_language_event(&context);
        check(accepts == 1 && events == 2 && context.gpr[3] == 4,
              "configured language was not accepted through its handler");
        context.gpr[3] = 0x1234;
        motorstorm_boot_language_event(&context);
        check(accepts == 1 && events == 3, "later language visits forwarded");
    } else if (!std::strcmp(argv[1], "original")) {
        context.lr = 0x56bec0;
        motorstorm_boot_language_event(&context);
        context.lr = 0x50da44;
        motorstorm_boot_start_video(&context);
        check(accepts == 0 && events == 1 && starts == 1 && closes == 0,
              "original startup selection preserved");
    } else {
        context.lr = 0x600000;
        motorstorm_boot_start_video(&context);
        check(starts == 1 && closes == 0 && playing, "background movie forwarded");
        context.lr = 0x50da44;
        motorstorm_boot_start_video(&context);
        check(starts == 1 && closes == 1 && !playing,
              "opening video started instead of natural finished state");
        motorstorm_boot_start_video(&context);
        check(starts == 2 && closes == 1 && playing, "later opening calls forwarded");
        context.lr = 0x56bec0;
        motorstorm_boot_language_event(&context);
        check(events == 1 && accepts == 0, "post-startup language interaction forwarded");
    }
    check(context.gpr[1] == initial.gpr[1] && context.gpr[2] == initial.gpr[2],
          "stack and TOC preserved");
    check(g_trampoline_fn == nullptr, "retained callback completion drained");
    std::puts("PASS native menu boot policy and original ownership callbacks");
    return 0;
}

int main(int argc, char **argv) {
    try {
        return run_fixture(argc, argv);
    } catch (const std::exception &error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 2;
    }
}
