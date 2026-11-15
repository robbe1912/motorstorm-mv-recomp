/* Driver for scripts/check_fps_csv_persistence.py. Links the production
 * rsx_fps_stats.c, built with RSX_FPS_STATS_TEST_SEAMS (authored clock and
 * write faults) or, for the historical control, the previous source as-is.
 *
 *   fps_csv <mode> <presents> <step_us> [fail_after_flushes]
 *
 * modes: normal    -> return from main (atexit summary runs)
 *        terminate -> _exit(0) after the last present (owned abrupt stop:
 *                     no atexit, no stdio flush)
 *        overhead  -> time the presents and print ns/present, then _exit
 */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <process.h>
#include <windows.h>
#else
#include <unistd.h>
#endif
#include "rsx_fps_stats.h"

/* loadtime_trace stubs: the first-present event is out of scope here. */
int loadtime_on(void) { return 0; }
void loadtime_event(const char* kind, const char* detail) { (void)kind; (void)detail; }

static unsigned long long g_now_ns = 1000000000ull;   /* authored clock */
static long g_fail_after = -1;                        /* writes before a fault */
static long g_flushes;

unsigned long long rsx_fps_stats_test_now_ns(void) { return g_now_ns; }

/* Authored device fault on the Nth write: nothing written, or (partial
 * mode) the first half of the data written before the device fills. */
size_t rsx_fps_stats_test_fwrite(const void* data, size_t size, size_t count, FILE* stream)
{
    if (g_fail_after >= 0 && g_flushes++ >= g_fail_after) {
        size_t part = getenv("FPS_TEST_PARTIAL") ? (size * count) / 2 : 0;
        if (part) fwrite(data, 1, part, stream);
        errno = ENOSPC;
        return part;
    }
    return fwrite(data, size, count, stream);
}

static double host_seconds(void)
{
#ifdef _WIN32
    LARGE_INTEGER f, c;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)f.QuadPart;
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
#endif
}

int main(int argc, char** argv)
{
    if (argc < 4) return 64;
    const char* mode = argv[1];
    long presents = strtol(argv[2], NULL, 10);
    unsigned long long step_ns = strtoull(argv[3], NULL, 10) * 1000ull;
    if (argc > 4) g_fail_after = strtol(argv[4], NULL, 10);

    double t0 = host_seconds();
    for (long i = 0; i < presents; i++) {
        if (i % 7 == 3) rsx_fps_stats_on_flip();
        rsx_fps_stats_on_present();
        g_now_ns += step_ns;
    }
    double elapsed = host_seconds() - t0;

    if (!strcmp(mode, "overhead")) {
        printf("ns_per_present=%.1f\n", elapsed * 1e9 / (double)(presents ? presents : 1));
        fflush(stdout);
        _exit(0);
    }
    if (!strcmp(mode, "terminate")) {
        fflush(stderr);
        _exit(0);   /* no atexit summary, no stdio flush */
    }
    return 0;       /* normal: atexit summary closes the CSV */
}
