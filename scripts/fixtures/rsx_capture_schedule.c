/* Game-free checks of the selector called by the D3D12 capture producer. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rsx_capture_schedule.h"
#include "rsx_capture_event.h"
#define CHECK(c) do { if (!(c)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#c); return 1; } } while (0)
static int screen_checks, screen_failures;
static void check(int good, const char* name) {
    ++screen_checks;
    if (!good) { ++screen_failures; fprintf(stderr, "FAIL %s\n", name); }
}
int main(int argc, char** argv)
{
    rsx_capture_schedule s;
    rsx_capture_pad_configure(0);
    rsx_capture_pad_notify(0x10);
    CHECK(rsx_capture_pad_take() == 0);
    rsx_capture_pad_configure(0x10);
    rsx_capture_pad_notify(0x4000);
    CHECK(rsx_capture_pad_take() == 0);
    rsx_capture_pad_notify(0x10);
    rsx_capture_pad_notify(0x30);
    CHECK(rsx_capture_pad_take() == 0x10);
    CHECK(rsx_capture_pad_take() == 0);
    rsx_capture_pad_notify(0x30);
    CHECK(rsx_capture_pad_take() == 0x30);
    uint32_t index = 99;
    rsx_capture_schedule_init(&s, 1, 2, 120);
    CHECK(!rsx_capture_schedule_next(&s, 0, 1, 1, &index));
    CHECK(rsx_capture_schedule_next(&s, 1, 1, 0, &index) == RSX_CAPTURE_SCHEDULED && index == 0);
    CHECK(!rsx_capture_schedule_next(&s, 120, 1, 1, &index));
    CHECK(rsx_capture_schedule_next(&s, 121, 1, 1, &index) == RSX_CAPTURE_SCHEDULED && index == 1);
    CHECK(!rsx_capture_schedule_next(&s, 1000, 1, 1, &index));
    CHECK(!rsx_capture_schedule_arm(&s, 0));
    CHECK(!rsx_capture_schedule_arm(&s, RSX_CAPTURE_BURST_MAX + 1));
    CHECK(rsx_capture_schedule_arm(&s, 3));
    CHECK(!rsx_capture_schedule_next(&s, 1001, 0, 1, &index));
    CHECK(!rsx_capture_schedule_next(&s, 1002, 1, 0, &index));
    CHECK(s.burst_remaining == 3);
    for (unsigned i = 0; i < 3; ++i)
        CHECK(rsx_capture_schedule_next(&s, 1003 + i, 1, 1, &index) == RSX_CAPTURE_BURST && index == i + 2);
    CHECK(!rsx_capture_schedule_next(&s, 1006, 1, 1, &index));
    CHECK(!rsx_capture_schedule_arm(&s, 3));
    rsx_capture_schedule_init(&s, 1, 3, 2);
    CHECK(rsx_capture_schedule_arm(&s, 2));
    CHECK(rsx_capture_schedule_next(&s, 1, 1, 1, &index) == 3 && index == 0);
    CHECK(rsx_capture_schedule_next(&s, 2, 1, 1, &index) == RSX_CAPTURE_BURST && index == 1);
    CHECK(rsx_capture_schedule_next(&s, 3, 1, 1, &index) == RSX_CAPTURE_SCHEDULED && index == 2);
    CHECK(rsx_capture_schedule_next(&s, 5, 1, 1, &index) == RSX_CAPTURE_SCHEDULED && index == 3);
    CHECK(!rsx_capture_schedule_next(&s, 6, 1, 1, &index));
    rsx_capture_schedule_init(&s, UINT32_MAX, 2, UINT32_MAX);
    CHECK(rsx_capture_schedule_next(&s, UINT32_MAX, 1, 1, &index));
    CHECK(!rsx_capture_schedule_next(&s, (uint64_t)UINT32_MAX + 1, 1, 1, &index));
    CHECK(rsx_capture_schedule_next(&s, (uint64_t)UINT32_MAX * 2, 1, 1, &index));
    rsx_capture_schedule_init(&s, 0, 0, 0);
    CHECK(rsx_capture_schedule_arm(&s, RSX_CAPTURE_BURST_MAX));
    for (unsigned i = 0; i < RSX_CAPTURE_BURST_MAX; ++i)
        CHECK(rsx_capture_schedule_next(&s, i, 1, 1, &index) == RSX_CAPTURE_BURST && index == i);
    CHECK(!rsx_capture_schedule_next(&s, RSX_CAPTURE_BURST_MAX, 1, 1, &index));
    unsigned captured, offscreen;
    rsx_capture_schedule_init(&s, 2, 3, 2);
    check(!s.screen_only, "raw diagnostic mode remains default");
    check(rsx_capture_schedule_screen_only(&s, "1") && s.screen_only, "screen mode enabled");
    check(!rsx_capture_schedule_screen_only(&s, "") && s.screen_only, "empty mode rejected without mutation");
    check(!rsx_capture_schedule_screen_only(&s, "2") && s.screen_only, "invalid mode rejected without mutation");
    check(rsx_capture_schedule_screen_only(&s, "0") && !s.screen_only, "explicit raw mode");
    check(rsx_capture_schedule_screen_only(&s, NULL) && !s.screen_only, "unset raw mode");
    rsx_capture_schedule_screen_only(&s, "1");
    if (argc > 1 && !strcmp(argv[1], "--ignore-screen")) s.screen_only = 0;
    captured = offscreen = 0;
    unsigned batches[3] = {0,0,0};
    for (unsigned frame = 0; frame < 9; ++frame) {
        int presenting = (frame & 1) != 0;
        if (rsx_capture_schedule_next(&s, frame, 1, presenting, &index)) {
            if (!presenting) ++offscreen;
            if (captured < 3) batches[captured] = frame;
            ++captured;
        }
    }
    check(captured == 3 && !offscreen && batches[0] == 3 && batches[1] == 5 &&
        batches[2] == 7 && s.index == 3 && s.done == 3,
        "periodic offscreen alias defers without spending screen budget");
    rsx_capture_schedule_init(&s, 1, 1, 4);
    rsx_capture_schedule_screen_only(&s, "1");
    check(rsx_capture_schedule_arm(&s, 2), "screen burst armed");
    check(!rsx_capture_schedule_next(&s, 1, 0, 1, &index) &&
        !s.done && !s.index && s.burst_remaining == 2, "empty screen consumes nothing");
    check(!rsx_capture_schedule_next(&s, 2, 1, 0, &index) &&
        !s.done && !s.index && s.burst_remaining == 2, "offscreen consumes neither budget");
    check(rsx_capture_schedule_next(&s, 3, 1, 1, &index) == 3 &&
        !index && s.done == 1 && s.burst_remaining == 1, "deferred sample overlaps burst once");
    check(!rsx_capture_schedule_next(&s, 4, 1, 0, &index) &&
        s.burst_remaining == 1 && s.index == 1, "offscreen preserves remaining burst");
    check(rsx_capture_schedule_next(&s, 5, 1, 1, &index) == 2 &&
        index == 1 && s.done == 1 && !s.burst_remaining, "remaining burst only on screen");
    check(!rsx_capture_schedule_next(&s, 6, 1, 1, &index) &&
        s.index == 2, "screen and burst bounds preserved");
    printf("screen_checks=%d failures=%d\n", screen_checks, screen_failures);
    if (screen_failures) return 1;
    puts("PASS: cross-TU input event latch, sparse schedule, late finite once-only burst, presented/empty filtering, overlap, unique indices, overflow");
    return 0;
}
