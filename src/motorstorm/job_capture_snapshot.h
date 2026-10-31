#pragma once
#include "job_capture.h"
#include <stdio.h>

/* Native-ABI private snapshot, not a portable interchange format. The caller
 * owns and exclusively accesses the stream and its path, and must keep capture
 * alive during this call. A reader must validate the complete file. The format
 * has no payload checksum and fflush does not guarantee durable disk storage. */
enum { JOB_CAPTURE_FILE_VERSION = 1 };
struct job_capture_file_header {
    char magic[8];
    uint32_t version, header_size, record_size, snapshot_size;
};
struct job_capture_file_footer {
    char magic[8];
    job_capture_snapshot snapshot;
};
/* Writes header, (index, record) pairs, then a footer. Returns 0 on any visit,
 * write or flush error. A failed/incomplete file must not be treated as valid.
 * The output can describe a partial concurrent view; it is not a global order. */
int job_capture_write_snapshot(const job_capture*, FILE*);
/* Validates the complete file before delivering records; accepts only this
 * process ABI. A consumer failure or any invalid/truncated file returns 0. */
int job_capture_read_snapshot(FILE*, int (*consumer)(void*, uint64_t,
                              const job_capture_record*), void*, job_capture_snapshot*);
