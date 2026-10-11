#ifndef PS3EMU_LOADTIME_TRACE_H
#define PS3EMU_LOADTIME_TRACE_H

/* Load-stage timing (#11). One JSONL event per boundary crossing:
 * file I/O, decrypt, SPU job runs, guest waits, pad presses, boot
 * milestones. Enabled by LOADTIME_TRACE=1; events go to
 * LOADTIME_TRACE_FILE (stderr when unset). Disabled by default and a
 * single cached-flag check per call site when off. Every line is
 * flushed as written; failed writes and event exhaustion are reported. No guest state is
 * read or changed; observers only. */

#ifdef __cplusplus
extern "C" {
#endif

/* 1 when LOADTIME_TRACE is set to a nonzero value. First call resolves
 * and anchors the t=0 timestamp. Thread-safe. */
int loadtime_on(void);

/* Monotonic microseconds since the first loadtime call. Call only after
 * loadtime_on() returned 1 (returns 0 otherwise). */
unsigned long long loadtime_us(void);

/* One event: kind is a short stable label, detail is a preformatted
 * "key=value key=value" string (JSON-escaped here). */
void loadtime_event(const char* kind, const char* detail);
/* Paths are a separate JSON field, preserving spaces/quotes/equals signs. */
void loadtime_event_path(const char* kind,const char* detail,const char* path);

#ifdef __cplusplus
}
#endif

#endif /* PS3EMU_LOADTIME_TRACE_H */
