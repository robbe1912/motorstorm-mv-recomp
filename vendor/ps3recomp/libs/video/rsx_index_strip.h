/* Incremental RSX indexed strip/fan assembly. No vertex fetch for restart. */
#ifndef PS3RECOMP_RSX_INDEX_STRIP_H
#define PS3RECOMP_RSX_INDEX_STRIP_H
#include <stdint.h>
typedef struct { uint32_t first, previous, held, odd; } rsx_index_strip;
static inline int rsx_index_strip_push(rsx_index_strip* s, uint32_t index,
    int fan, uint32_t restart_enable, uint32_t restart, int index_is_u32,
    uint32_t triangle[3])
{
    if (restart_enable && (index_is_u32 || restart <= 0xffffu) && index == restart) {
        s->held = s->odd = 0;
        return 0;
    }
    if (!s->held) { s->first = index; s->held = 1; return 0; }
    if (s->held == 1) { s->previous = index; s->held = 2; return 0; }
    triangle[0] = !fan && s->odd ? s->previous : s->first;
    triangle[1] = !fan && s->odd ? s->first : s->previous;
    triangle[2] = index;
    if (!fan) s->first = s->previous;
    s->previous = index;
    s->odd ^= 1u;
    return 1;
}
#endif
