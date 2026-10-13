#ifndef SPU_TASK_LIFECYCLE_TRACE_H
#define SPU_TASK_LIFECYCLE_TRACE_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <stdatomic.h>
#include <time.h>
#endif

static inline uint32_t spu_task_trace_be32(const uint8_t* p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

/* Diagnostic only: sequential reads, not an atomic taskset snapshot.
 * Budgets are independent per translation unit, and filtered events do not
 * spend them. NULL header/LS inputs are printed as unavailable, not zero. */
static inline void spu_task_lifecycle_trace(const char* event, int image,
    uint32_t request, uint32_t taskset, uint32_t task,
    const uint8_t* ls, const uint8_t* header)
{
    const char* option = getenv("SPU_TASK_LIFECYCLE_TRACE");
    if (!option) return;
    int limit = atoi(option);
    if (limit < 1 || limit > 4096) return;
    option = getenv("SPU_TASK_LIFECYCLE_IMAGE");
    if (option && atoi(option) != image) return;
#ifdef _WIN32
    static volatile LONG count;
    LONG sequence = InterlockedIncrement(&count);
    if (sequence > limit) return;
    unsigned long long tick = GetTickCount64();
    unsigned long thread = GetCurrentThreadId();
#else
    static atomic_uint count;
    unsigned sequence = atomic_fetch_add(&count, 1) + 1;
    if (sequence > (unsigned)limit) return;
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    unsigned long long tick = (unsigned long long)now.tv_sec * 1000 + now.tv_nsec / 1000000;
    unsigned long thread = 0; /* No portable native TID is assumed. */
#endif
    int enabled = -1, selected = -1;
    if (header) {
        enabled = 0;
        for (unsigned byte = 0; byte < 16; ++byte)
            for (unsigned bit = 0; bit < 8; ++bit)
                enabled += (header[0x30 + byte] >> bit) & 1;
        if (task < 128)
            selected = !!(header[0x30 + task / 8] & (0x80u >> (task & 7)));
    }
    fprintf(stderr, "[spu-task-life] event=%s tick_ms=%llu thread=%lu seq=%lu "
        "image=%d request=%08X taskset=%08X task=%u has_ls=%d "
        "x2fc0=%08X%08X x2fd4=%08X enabled=%d selected_enabled=%d\n",
        event, tick, thread, (unsigned long)sequence, image, request, taskset,
        task, ls != NULL, ls ? spu_task_trace_be32(ls + 0x2FC0) : 0,
        ls ? spu_task_trace_be32(ls + 0x2FC4) : 0,
        ls ? spu_task_trace_be32(ls + 0x2FD4) : 0, enabled, selected);
}

#endif
