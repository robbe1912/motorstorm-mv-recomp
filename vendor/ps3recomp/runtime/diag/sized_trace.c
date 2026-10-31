#include "ps3emu/sized_trace.h"
#include <stdatomic.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

typedef struct sized_slot { atomic_uint_fast64_t sequence; unsigned char bytes[]; } sized_slot;
struct ps3_sized_trace {
    atomic_uint_fast64_t attempted, dropped;
    unsigned char* records;
    uint32_t capacity, payload_size, stride, offset;
};
#ifndef PS3_SIZED_TRACE_BEFORE_COPY
#define PS3_SIZED_TRACE_BEFORE_COPY(trace, index) ((void)0)
#endif
static sized_slot* slot(const ps3_sized_trace* trace, uint64_t index)
{
    return (sized_slot*)(void*)(trace->records + (size_t)index * trace->stride);
}
/* Saturate rather than allowing a long-running capture to reuse a slot. */
static uint64_t increment_saturating(atomic_uint_fast64_t* counter)
{
    uint_fast64_t previous = atomic_load_explicit(counter, memory_order_relaxed);
    while (previous != UINT64_MAX &&
           !atomic_compare_exchange_weak_explicit(counter, &previous, previous + 1,
                                                   memory_order_relaxed, memory_order_relaxed)) {}
    return (uint64_t)previous;
}
ps3_sized_trace* ps3_sized_trace_create(uint32_t capacity, uint32_t size)
{
    if (!capacity || capacity > PS3_SIZED_TRACE_MAX_RECORDS || !size ||
        size > PS3_SIZED_TRACE_MAX_PAYLOAD) return NULL;
    size_t alignment = _Alignof(sized_slot), offset = offsetof(sized_slot, bytes);
    size_t stride = (offset + size + alignment - 1) / alignment * alignment;
    if (stride > UINT32_MAX || stride > SIZE_MAX / capacity) return NULL;
    ps3_sized_trace* trace = calloc(1, sizeof(*trace));
    if (!trace) return NULL;
    atomic_init(&trace->attempted, 0); atomic_init(&trace->dropped, 0);
    if (!atomic_is_lock_free(&trace->attempted) || !atomic_is_lock_free(&trace->dropped)) {
        free(trace); return NULL;
    }
    trace->records = calloc(capacity, stride);
    if (!trace->records) { free(trace); return NULL; }
    trace->capacity = capacity; trace->payload_size = size;
    trace->stride = (uint32_t)stride; trace->offset = (uint32_t)offset;
    for (uint32_t i = 0; i < capacity; ++i) atomic_init(&slot(trace, i)->sequence, 0);
    if (!atomic_is_lock_free(&slot(trace, 0)->sequence)) {
        free(trace->records); free(trace); return NULL;
    }
    return trace;
}
int ps3_sized_trace_append(ps3_sized_trace* trace, const void* payload, uint32_t size)
{
    if (!trace) return PS3_SIZED_TRACE_DISABLED;
    if (!payload || size != trace->payload_size) return PS3_SIZED_TRACE_INVALID;
    uint64_t index = increment_saturating(&trace->attempted);
    if (index >= trace->capacity) {
        increment_saturating(&trace->dropped);
        return PS3_SIZED_TRACE_FULL;
    }
    sized_slot* record = slot(trace, index);
    PS3_SIZED_TRACE_BEFORE_COPY(trace, index);
    memcpy(record->bytes, payload, size);
    atomic_store_explicit(&record->sequence, index + 1, memory_order_release);
    return PS3_SIZED_TRACE_RECORDED;
}
int ps3_sized_trace_read(const ps3_sized_trace* trace, uint64_t index, void* output, uint32_t size)
{
    if (!trace || !output || size != trace->payload_size || index >= trace->capacity) return -1;
    sized_slot* record = slot(trace, index);
    if (atomic_load_explicit(&record->sequence, memory_order_acquire) != index + 1) return 0;
    memcpy(output, record->bytes, size);
    return 1;
}
int ps3_sized_trace_describe(const ps3_sized_trace* trace, ps3_sized_trace_info* output)
{
    if (!trace || !output) return 0;
    *output = (ps3_sized_trace_info){atomic_load_explicit(&trace->attempted, memory_order_relaxed),
        atomic_load_explicit(&trace->dropped, memory_order_relaxed), (uint64_t)(uintptr_t)trace->records,
        trace->capacity, trace->payload_size, trace->stride, trace->offset};
    return 1;
}
void ps3_sized_trace_destroy(ps3_sized_trace* trace)
{
    if (trace) { free(trace->records); free(trace); }
}
