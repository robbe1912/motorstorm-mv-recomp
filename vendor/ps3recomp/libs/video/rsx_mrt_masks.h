/* NV4097 primary byte lanes and secondary ARGB nibbles -> D3D RGBA nibbles. */
#ifndef PS3RECOMP_RSX_MRT_MASKS_H
#define PS3RECOMP_RSX_MRT_MASKS_H
#include <stdint.h>
static uint32_t rsx_mrt_color_masks(uint32_t primary, uint32_t mrt)
{
    uint32_t out = ((primary & 0x00010000) ? 1u : 0u)
                 | ((primary & 0x00000100) ? 2u : 0u)
                 | ((primary & 0x00000001) ? 4u : 0u)
                 | ((primary & 0x01000000) ? 8u : 0u);
    for (unsigned r=1;r<4;r++) {
        uint32_t argb=(mrt>>(r*4))&15u;
        out |= (((argb&14u)>>1)|((argb&1u)<<3)) << (r*4);
    }
    return out;
}
/* Packed blend factors use bits1..26; bits27..29 retain MRT1..3 enables. */
static uint32_t rsx_mrt_blend_enables(int primary, uint32_t secondary)
{
    return (primary ? 1u : 0u) | (secondary & 14u);
}
static uint32_t rsx_mrt_blend_key_bits(uint32_t enables)
{
    return (enables & 1u) | ((enables & 14u) << 26);
}
static uint32_t rsx_mrt_blend_key_enables(uint32_t key)
{
    return (key & 1u) | ((key >> 26) & 14u);
}
#endif
