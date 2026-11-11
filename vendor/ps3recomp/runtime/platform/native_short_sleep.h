#ifndef PS3_NATIVE_SHORT_SLEEP_H
#define PS3_NATIVE_SHORT_SLEEP_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Windows opt-in PS3_NATIVE_SHORT_SLEEP=0|1 (default 0). For 1..999 us,
 * return 1 only after a monotonic deadline has passed. Return 0 requests the
 * caller's unchanged reference wait, including after a reported API failure.
 * Other durations and non-Windows hosts always retain the reference path.
 * Auto-reset high-resolution timers belong to each FLS execution context and
 * are closed on thread/fiber exit. Installation is process-lifetime, once. */
int ps3_native_short_sleep(uint64_t usec);
#ifdef __cplusplus
}
#endif
#endif
