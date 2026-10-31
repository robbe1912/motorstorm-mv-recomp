#include "job_capture_snapshot.h"
#include <string.h>

static int write_record(void* user, uint64_t index, const job_capture_record* record) {
    FILE* stream = static_cast<FILE*>(user);
    return fwrite(&index, sizeof(index), 1, stream) == 1 &&
           fwrite(record, sizeof(*record), 1, stream) == 1;
}

int job_capture_write_snapshot(const job_capture* capture, FILE* stream) {
    if (!capture || !stream) return 0;
    job_capture_file_header header{};
    memcpy(header.magic, "MSJOB001", sizeof(header.magic));
    header.version = JOB_CAPTURE_FILE_VERSION;
    header.header_size = sizeof(header);
    header.record_size = sizeof(job_capture_record);
    header.snapshot_size = sizeof(job_capture_snapshot);
    if (fwrite(&header, sizeof(header), 1, stream) != 1) return 0;
    job_capture_file_footer footer{};
    if (!job_capture_visit(capture, write_record, stream, &footer.snapshot) ||
        footer.snapshot.consumer_failed) return 0;
    /* Storage addresses are process-local implementation details. */
    footer.snapshot.before.storage.records_address = 0;
    footer.snapshot.after.storage.records_address = 0;
    memcpy(footer.magic, "MSEND001", sizeof(footer.magic));
    return fwrite(&footer, sizeof(footer), 1, stream) == 1 && fflush(stream) == 0;
}

int job_capture_read_snapshot(FILE* stream, int (*consumer)(void*, uint64_t,
                              const job_capture_record*), void* user, job_capture_snapshot* out) {
    if (!stream || !consumer || !out || fseek(stream, 0, SEEK_END)) return 0;
    long length = ftell(stream);
    if (length < 0 || static_cast<unsigned long>(length) < sizeof(job_capture_file_header) + sizeof(job_capture_file_footer) ||
        fseek(stream, 0, SEEK_SET)) return 0;
    job_capture_file_header header{};
    if (fread(&header, sizeof(header), 1, stream) != 1 || memcmp(header.magic, "MSJOB001", 8) ||
        header.version != JOB_CAPTURE_FILE_VERSION || header.header_size != sizeof(header) ||
        header.record_size != sizeof(job_capture_record) || header.snapshot_size != sizeof(job_capture_snapshot) ||
        fseek(stream, length - static_cast<long>(sizeof(job_capture_file_footer)), SEEK_SET)) return 0;
    job_capture_file_footer footer{};
    if (fread(&footer, sizeof(footer), 1, stream) != 1 || memcmp(footer.magic, "MSEND001", 8)) return 0;
    const auto& s = footer.snapshot;
    uint64_t bytes = static_cast<uint64_t>(length) - sizeof(header) - sizeof(footer);
    uint64_t stride = sizeof(uint64_t) + sizeof(job_capture_record);
    if (s.consumer_failed || s.before.schema_version != JOB_CAPTURE_SCHEMA_VERSION ||
        s.after.schema_version != JOB_CAPTURE_SCHEMA_VERSION || s.before.record_size != sizeof(job_capture_record) ||
        s.after.record_size != sizeof(job_capture_record) || s.before.pointer_size != sizeof(uintptr_t) ||
        s.after.pointer_size != sizeof(uintptr_t) || !s.before.run_id || s.before.run_id != s.after.run_id ||
        !s.before.ticks_per_second || s.before.ticks_per_second != s.after.ticks_per_second ||
        s.before.storage.capacity != s.after.storage.capacity ||
        s.after.storage.attempted < s.before.storage.attempted ||
        s.before.storage.records_address || s.after.storage.records_address || s.delivered > s.examined ||
        s.pending != s.examined - s.delivered || s.examined > s.before.storage.capacity ||
        s.examined != (s.before.storage.attempted < s.before.storage.capacity ?
                       s.before.storage.attempted : s.before.storage.capacity) ||
        bytes % stride || bytes / stride != s.delivered ||
        fseek(stream, sizeof(header), SEEK_SET)) return 0;
    uint64_t previous = 0;
    for (uint64_t i = 0; i < s.delivered; ++i) {
        uint64_t index;
        job_capture_record record{};
        if (fread(&index, sizeof(index), 1, stream) != 1 || fread(&record, sizeof(record), 1, stream) != 1 ||
            index >= s.examined || (i && index <= previous)) return 0;
        previous = index;
    }
    if (fseek(stream, sizeof(header), SEEK_SET)) return 0;
    for (uint64_t i = 0; i < s.delivered; ++i) {
        uint64_t index;
        job_capture_record record{};
        if (fread(&index, sizeof(index), 1, stream) != 1 || fread(&record, sizeof(record), 1, stream) != 1 ||
            !consumer(user, index, &record)) return 0;
    }
    *out = s;
    return 1;
}
