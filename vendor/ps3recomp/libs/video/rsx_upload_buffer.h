/* Grow a two-parity upload allocation without changing offsets within a half.
 * The caller serializes recording/submission. Allocation and GPU retirement are
 * adapters so the preservation/failure contract can be tested without a GPU. */
#ifndef PS3RECOMP_RSX_UPLOAD_BUFFER_H
#define PS3RECOMP_RSX_UPLOAD_BUFFER_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>

typedef struct rsx_upload_buffer {
    void* resource;
    void* memory;
    uint32_t capacity; /* vertices per parity */
} rsx_upload_buffer;

typedef struct rsx_upload_ops {
    void* context;
    int (*allocate)(void*, uint64_t, rsx_upload_buffer*);
    int (*retire_readers)(void*);
    void (*dispose)(void*, rsx_upload_buffer*);
} rsx_upload_ops;

static int rsx_upload_reserve(rsx_upload_buffer* buffer, uint32_t used_bytes,
                              uint64_t vertices, uint32_t stride,
                              const rsx_upload_ops* ops)
{
    uint64_t limit, used, required, capacity, old_bytes, new_bytes;
    rsx_upload_buffer next, previous;
    if (!stride || !buffer->capacity || !buffer->memory ||
        !buffer->resource || used_bytes % stride) return 0;
    /* D3D12_VERTEX_BUFFER_VIEW::SizeInBytes and byte offsets are uint32_t. */
    limit = UINT32_MAX / stride;
    used = used_bytes / stride;
    if (buffer->capacity > limit || used > buffer->capacity ||
        vertices > limit - used) return 0;
    required = used + vertices;
    if (required <= buffer->capacity) return 1;
    capacity = buffer->capacity;
    while (capacity < required)
        capacity = capacity > limit / 2 ? limit : capacity * 2;
    old_bytes = (uint64_t)buffer->capacity * stride;
    new_bytes = capacity * stride;
    if (new_bytes > SIZE_MAX / 2) return 0;
    memset(&next, 0, sizeof(next));
    if (!ops->allocate(ops->context, new_bytes * 2, &next)) return 0;
    if (!next.memory || !next.resource || !ops->retire_readers(ops->context)) {
        ops->dispose(ops->context, &next);
        return 0;
    }
    /* The second half moves when capacity grows; a contiguous copy is wrong. */
    memcpy(next.memory, buffer->memory, (size_t)old_bytes);
    memcpy((unsigned char*)next.memory + (size_t)new_bytes,
           (unsigned char*)buffer->memory + (size_t)old_bytes, (size_t)old_bytes);
    next.capacity = (uint32_t)capacity;
    previous = *buffer;
    *buffer = next;
    ops->dispose(ops->context, &previous);
    return 1;
}
#endif
