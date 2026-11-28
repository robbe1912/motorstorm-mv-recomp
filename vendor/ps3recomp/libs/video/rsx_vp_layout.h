/* Compact VP-path vertex layout.
 *
 * The VP path uploads each vertex as float4 attribute slots. A vertex
 * program usually reads only a few of the sixteen RSX inputs, so when its
 * inputs are known exactly (rsx_vp_analyze_inputs) only those slots are
 * uploaded, packed in slot order at 16 bytes each, and the input layout
 * declares the same slots at the same offsets. A program whose inputs are not
 * known exactly keeps all sixteen slots (256 bytes).
 *
 * The upload buffer's capacity stays counted in 256-byte units, so the
 * allocation and parity arithmetic of rsx_upload_reserve is unchanged; these
 * helpers convert byte requests into those units. Pure helpers, so the packing
 * and offset arithmetic can be checked without a GPU. */
#ifndef PS3RECOMP_RSX_VP_LAYOUT_H
#define PS3RECOMP_RSX_VP_LAYOUT_H
#include <stdint.h>
#include <string.h>
#include "rsx_upload_buffer.h"

#define RSX_VP_SLOT_BYTES 16u
#define RSX_VP_UNIT_BYTES 256u   /* one full 16-slot vertex: the capacity unit */

typedef struct rsx_vp_layout {
    uint32_t mask;     /* attribute slots carried; never 0 */
    uint32_t stride;   /* bytes per vertex: 16 per carried slot */
    uint32_t count;    /* carried slots */
    uint8_t slot[16];  /* slot[k] = attribute stored at byte 16 * k */
    int8_t index_of[16]; /* index_of[a] = k with slot[k] == a, or -1 */
} rsx_vp_layout;

#define RSX_VP_LAYOUT_FULL \
    { 0xFFFFu, RSX_VP_UNIT_BYTES, 16u, \
      { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 },       { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 } }

/* Layout for a vertex program that reads the attributes in `mask`. A program
 * that reads none still gets slot 0, so every vertex keeps a nonzero stride;
 * the input layout may declare an element the shader does not consume. */
static uint32_t rsx_vp_layout_mask(uint32_t mask)
{
    mask &= 0xFFFFu;
    return mask ? mask : 1u;
}

static void rsx_vp_layout_init(rsx_vp_layout* layout, uint32_t mask)
{
    layout->mask = rsx_vp_layout_mask(mask);
    layout->count = 0;
    for (uint32_t attr = 0; attr < 16; ++attr) {
        layout->index_of[attr] = -1;
        if (layout->mask & (1u << attr)) {
            layout->index_of[attr] = (int8_t)layout->count;
            layout->slot[layout->count++] = (uint8_t)attr;
        }
    }
    for (uint32_t k = layout->count; k < 16; ++k) layout->slot[k] = 0;
    layout->stride = layout->count * RSX_VP_SLOT_BYTES;
}

/* Vertex `index` of an upload that starts at `base`. */
static unsigned char* rsx_vp_layout_at(const rsx_vp_layout* layout, void* base,
                                       uint32_t index)
{
    return (unsigned char*)base + (uint64_t)index * layout->stride;
}

/* Copy the carried slots of a full 16-slot vertex to `dst`, in slot order. */
static void rsx_vp_layout_pack(const rsx_vp_layout* layout, void* dst,
                               const void* full_vertex)
{
    unsigned char* d = (unsigned char*)dst;
    const unsigned char* s = (const unsigned char*)full_vertex;
    if (layout->count == 16) {
        memcpy(d, s, RSX_VP_UNIT_BYTES);
        return;
    }
    for (uint32_t k = 0; k < layout->count; ++k)
        memcpy(d + (size_t)k * RSX_VP_SLOT_BYTES,
               s + (size_t)layout->slot[k] * RSX_VP_SLOT_BYTES, RSX_VP_SLOT_BYTES);
}

/* Copy one vertex already in this layout (`count` slots) to `dst`. Fixed
 * 16-byte copies, like the pack, so no variable-length memcpy call. */
static void rsx_vp_layout_copy(const rsx_vp_layout* layout, void* dst,
                               const void* packed_vertex)
{
    unsigned char* d = (unsigned char*)dst;
    const unsigned char* s = (const unsigned char*)packed_vertex;
    for (uint32_t k = 0; k < layout->count; ++k)
        memcpy(d + (size_t)k * RSX_VP_SLOT_BYTES, s + (size_t)k * RSX_VP_SLOT_BYTES,
               RSX_VP_SLOT_BYTES);
}

/* First offset at or after `offset` where a draw with this stride can start,
 * so that its first vertex is offset / stride. Returns 0 with *aligned
 * untouched if the result does not fit a 32-bit buffer offset. */
static int rsx_vp_layout_align(uint32_t offset, uint32_t stride, uint32_t* aligned)
{
    uint64_t a;
    if (!stride) return 0;
    a = ((uint64_t)offset + stride - 1) / stride * stride;
    if (a > UINT32_MAX) return 0;
    *aligned = (uint32_t)a;
    return 1;
}

/* Make room for `bytes` more bytes after `used_bytes` in a buffer whose
 * capacity is counted in 256-byte units. The units already used are rounded
 * up, so a partly used unit is never handed out twice. */
static int rsx_vp_layout_reserve(rsx_upload_buffer* buffer, uint32_t used_bytes,
                                 uint64_t bytes, const rsx_upload_ops* ops)
{
    uint64_t used_units = ((uint64_t)used_bytes + RSX_VP_UNIT_BYTES - 1) / RSX_VP_UNIT_BYTES;
    uint64_t end_units;
    if (bytes > UINT64_MAX - used_bytes - RSX_VP_UNIT_BYTES) return 0;
    end_units = ((uint64_t)used_bytes + bytes + RSX_VP_UNIT_BYTES - 1) / RSX_VP_UNIT_BYTES;
    if (used_units * RSX_VP_UNIT_BYTES > UINT32_MAX) return 0;
    return rsx_upload_reserve(buffer, (uint32_t)(used_units * RSX_VP_UNIT_BYTES),
                              end_units - used_units, RSX_VP_UNIT_BYTES, ops);
}
#endif
