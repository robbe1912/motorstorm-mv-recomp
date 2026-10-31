#ifndef PS3EMU_SIZED_TRACE_H
#define PS3EMU_SIZED_TRACE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* One independently published opaque payload per slot. The capture owner
 * defines the schema, clock, identity, filtering and validity of every byte. */
typedef struct ps3_sized_trace ps3_sized_trace;
enum { PS3_SIZED_TRACE_MAX_PAYLOAD = 4096, PS3_SIZED_TRACE_MAX_RECORDS = 1048576 };
typedef struct ps3_sized_trace_info {
    uint64_t attempted, dropped, records_address;
    uint32_t capacity, payload_size, record_stride, payload_offset;
} ps3_sized_trace_info;
enum { PS3_SIZED_TRACE_DISABLED = 0, PS3_SIZED_TRACE_RECORDED = 1,
       PS3_SIZED_TRACE_FULL = 2, PS3_SIZED_TRACE_INVALID = 3 };
/* Allocate and initialize before producers run; report failures. Append and
 * read do not allocate or perform I/O. Slots never wrap or get reused. */
ps3_sized_trace* ps3_sized_trace_create(uint32_t capacity, uint32_t payload_size);
int ps3_sized_trace_append(ps3_sized_trace*, const void* payload, uint32_t size);
/* 1 complete, 0 pending/unused without touching output, -1 invalid. */
int ps3_sized_trace_read(const ps3_sized_trace*, uint64_t index, void* output, uint32_t size);
int ps3_sized_trace_describe(const ps3_sized_trace*, ps3_sized_trace_info*);
/* Counters saturate at UINT64_MAX; that value indicates an inexact count.
 * Live metadata isn't a coherent final snapshot; only destroy after all
 * producers and consumers are quiescent and synchronized. */
void ps3_sized_trace_destroy(ps3_sized_trace*);
#ifdef __cplusplus
}
#endif
#endif
