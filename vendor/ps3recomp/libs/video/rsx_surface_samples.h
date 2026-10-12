/* RSX AA samples occupy a 2D memory grid. Row pitch includes padding. */
#ifndef RSX_SURFACE_SAMPLES_H
#define RSX_SURFACE_SAMPLES_H
#include <stdint.h>

static inline int rsx_surface_sample_grid(uint32_t format, uint32_t* x, uint32_t* y)
{
    if (!x || !y) return 0;
    switch ((format >> 12) & 15u) {
    case 0: *x = 1; *y = 1; return 1;
    case 3: *x = 2; *y = 1; return 1;
    case 4: case 5: *x = 2; *y = 2; return 1;
    default: return 0;
    }
}

static inline int rsx_surface_sample_extent(uint32_t format, uint32_t w, uint32_t h,
                                          uint32_t* out_w, uint32_t* out_h)
{
    uint32_t x, y;
    if (!out_w || !out_h || !w || !h || !rsx_surface_sample_grid(format, &x, &y) ||
        w > UINT32_MAX / x || h > UINT32_MAX / y) return 0;
    *out_w = w * x;
    *out_h = h * y;
    return 1;
}
#endif
