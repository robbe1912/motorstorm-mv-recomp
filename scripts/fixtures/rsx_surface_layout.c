#include <stdio.h>
#include <stdlib.h>
#include "rsx_commands.h"
#include "rsx_surface_samples.h"

static struct { const rsx_state* current_rsx_state; u32 width, height; } s_d3d;
int cellGcmOffsetIsDisplay(u32 offset) { return offset == 0xF0000; }

/* PRODUCTION_TARGET_FUNCTION */

int main(void)
{
    /* format, pixel width/height, padded pitch, sample width/height */
    const u32 cases[][6] = {
        {0x3148, 720, 1280, 6144, 1440, 1280},
        {0x148, 8, 8, 64, 8, 8},
        {0x4148, 320, 180, 2560, 640, 360},
        {0x5148, 320, 180, 2560, 640, 360},
        {0x14B, 64, 64, 512, 64, 64},
        {0x148, 1280, 720, 5120, 1280, 720}
    };
    rsx_state state = {0};
    s_d3d.current_rsx_state = &state;
    s_d3d.width = 1280; s_d3d.height = 720;
    state.surface_color_offset[0] = 0x20000;
    state.surface_color_offset[1] = 0x30000;
    for (unsigned target = 1; target <= 2; ++target) {
        state.color_target = target;
        for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
            u32 w = 0, h = 0;
            state.surface_format = cases[i][0];
            state.surface_clip_w = cases[i][1]; state.surface_clip_h = cases[i][2];
            state.surface_color_pitch[target - 1] = cases[i][3];
            u32 address = current_rt_off(&w, &h, NULL);
            if (address != state.surface_color_offset[target - 1] ||
                w != cases[i][4] || h != cases[i][5]) {
                fprintf(stderr, "FAIL: actual target %u case %u extent %ux%u; expected %ux%u\n",
                        target, i, w, h, cases[i][4], cases[i][5]);
                return 1;
            }
        }
    }
    u32 x, y, w = 123, h = 456;
    if (!rsx_surface_sample_grid(0x3148, &x, &y) || x != 2 || y != 1 ||
        !rsx_surface_sample_grid(0x5148, &x, &y) || x != 2 || y != 2 ||
        rsx_surface_sample_extent(0x3148, UINT32_MAX, 1, &w, &h) ||
        rsx_surface_sample_extent(0x148, 0, 1, &w, &h) ||
        rsx_surface_sample_extent(0x2148, 1, 1, &w, &h) ||
        rsx_surface_sample_extent(0x148, 1, 1, NULL, &h) || w != 123 || h != 456) {
        fputs("FAIL: sample-grid factors or invalid-layout guard\n", stderr);
        return 1;
    }
    state.surface_color_offset[1] = 0xF0000;
    current_rt_off(&w, &h, NULL);
    if (w || h) { fputs("FAIL: registered display target dimensions changed\n", stderr); return 1; }
    puts("PASS: actual target sample layouts, padding, target identity and guards");
    return 0;
}
