#pragma once
#include <stdint.h>
#include "ps3emu/native_atomic_observer.h"
#include "ps3emu/spu_execution_observer.h"
#include "ps3emu/spurs_scheduler_observer.h"
#include "ps3emu/sized_trace.h"

/* Process-local, versioned data. The raw pointer fields are observations, not
 * lifetime-qualified guest identities. The owner defines the output format. */
enum { JOB_CAPTURE_SCHEMA_VERSION = 1 };
enum { JOB_CAPTURE_ATOMIC = 1, JOB_CAPTURE_EXECUTION, JOB_CAPTURE_SCHEDULER };
enum { JOB_CAPTURE_THREAD_UNKNOWN = 1, JOB_CAPTURE_HOST_ASSIGNMENT = 2 };
struct job_capture_record {
    uint64_t thread;
    uint32_t kind, flags;
    /* Current host-worker assignment, not proof of the observed context's owner. */
    ps3_spurs_dispatch_info host_assignment;
    union {
        ps3_atomic_observation atomic;
        ps3_spu_execution_event execution;
        ps3_spurs_scheduler_event scheduler;
    } value;
};
struct job_capture;
struct job_capture_config {
    uint64_t run_id, ticks_per_second;
    uint32_t capacity;
    void* user;
    uint64_t (*clock)(void*);
    uint64_t (*thread_id)(void*);
};
struct job_capture_info {
    uint64_t run_id, ticks_per_second;
    uint32_t schema_version, record_size, pointer_size;
    ps3_sized_trace_info storage;
};
struct job_capture_snapshot {
    job_capture_info before, after;
    uint64_t examined, delivered, pending;
    int consumer_failed;
};
/* Install once before any producers start, with no other observer owner.
 * Callbacks must be concurrent-safe and perform no allocation, I/O, guest
 * mutation, runtime reentry or application locking. Zero IDs are invalid. */
job_capture* job_capture_start(const job_capture_config*);
/* Live reads can encounter pending records. Info is not an atomic snapshot. */
int job_capture_describe(const job_capture*, job_capture_info*);
int job_capture_read(const job_capture*, uint64_t index, job_capture_record*);
/* Scans the initial reservation horizon; a concurrent writer can complete a
 * pending slot later. Consumer runs on the caller, outside observer callbacks.
 * Results are a partial live view, not an atomic or causally ordered trace. */
int job_capture_visit(const job_capture*, int (*consumer)(void*, uint64_t,
                      const job_capture_record*), void*, job_capture_snapshot*);
/* Only after all producers and readers are quiescent and synchronized. */
void job_capture_stop(job_capture*);
