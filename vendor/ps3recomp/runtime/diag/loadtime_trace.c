/* Load-stage timing implementation; see include/ps3emu/loadtime_trace.h. */
#include "ps3emu/loadtime_trace.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <pthread.h>
#include <time.h>
#endif

/* Hard cap: a full 600 s load run produces far fewer events than this;
 * past it the observer stops rather than grow without bound. */
#define LT_MAX_EVENTS 4000000u

static volatile int g_state = -1;        /* -1 unresolved, 0 off, 1 on */
static FILE* g_out;
static unsigned long long g_t0;          /* QPC/clock counts at anchor */
static unsigned long long g_qpf = 1;     /* counts per second */
static volatile unsigned long long g_events;

#ifdef _WIN32
static SRWLOCK g_lock = SRWLOCK_INIT;
#else
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
#endif

static unsigned long long lt_now_counts(void)
{
#ifdef _WIN32
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return (unsigned long long)c.QuadPart;
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (unsigned long long)ts.tv_sec * 1000000000ull
         + (unsigned long long)ts.tv_nsec;
#endif
}

static unsigned long long lt_freq(void)
{
#ifdef _WIN32
    LARGE_INTEGER f;
    QueryPerformanceFrequency(&f);
    return (unsigned long long)f.QuadPart;
#else
    return 1000000000ull;
#endif
}

int loadtime_on(void)
{
    if (g_state < 0) {
#ifdef _WIN32
        AcquireSRWLockExclusive(&g_lock);
#else
        pthread_mutex_lock(&g_lock);
#endif
        if (g_state < 0) {
            const char* e = getenv("LOADTIME_TRACE");
            g_state = (e && *e && strcmp(e, "0") != 0) ? 1 : 0;
            if (g_state) {
                g_qpf = lt_freq();
                g_t0 = lt_now_counts();
                g_out = stderr;
                const char* f = getenv("LOADTIME_TRACE_FILE");
                if (f && *f) {
                    FILE* out = fopen(f, "wb");
                    if (out) g_out = out;   /* keep stderr on failure */
                }
                fprintf(g_out, "{\"t_us\":0,\"tid\":0,\"kind\":\"trace_start\","
                               "\"detail\":\"pid_window_begin\"}\n");
                fflush(g_out);
            }
        }
#ifdef _WIN32
        ReleaseSRWLockExclusive(&g_lock);
#else
        pthread_mutex_unlock(&g_lock);
#endif
    }
    return g_state;
}

unsigned long long loadtime_us(void)
{
    if (g_state != 1) return 0;
    return (lt_now_counts() - g_t0) * 1000000ull / g_qpf;
}

static unsigned lt_tid(void)
{
#ifdef _WIN32
    return (unsigned)GetCurrentThreadId();
#else
    return (unsigned)(uintptr_t)pthread_self();
#endif
}

/* Minimal JSON string escape for detail values (paths, numbers). */
static void lt_write_escaped(FILE* out, const char* s)
{
    fputc('"', out);
    for (const unsigned char* p = (const unsigned char*)s; *p; p++) {
        switch (*p) {
        case '"':  fputs("\\\"", out); break;
        case '\\': fputs("\\\\", out); break;
        case '\n': fputs("\\n", out);  break;
        case '\r': fputs("\\r", out);  break;
        case '\t': fputs("\\t", out);  break;
        default:
            if (*p < 0x20) fprintf(out, "\\u%04x", *p);
            else           fputc(*p, out);
        }
    }
    fputc('"', out);
}

void loadtime_event(const char* kind, const char* detail)
{
    if (g_state != 1 || !g_out) return;
    if (g_events >= LT_MAX_EVENTS) return;

#ifdef _WIN32
    AcquireSRWLockExclusive(&g_lock);
#else
    pthread_mutex_lock(&g_lock);
#endif
    fprintf(g_out, "{\"t_us\":%llu,\"tid\":%u,\"kind\":",
            loadtime_us(), lt_tid());
    lt_write_escaped(g_out, kind ? kind : "");
    fputs(",\"detail\":", g_out);   /* kind label is closed by escape's quote */
    lt_write_escaped(g_out, detail ? detail : "");
    fputs("}\n", g_out);
    fflush(g_out);
    g_events++;
#ifdef _WIN32
    ReleaseSRWLockExclusive(&g_lock);
#else
    pthread_mutex_unlock(&g_lock);
#endif
}
