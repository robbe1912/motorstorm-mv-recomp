/* Load-stage timing implementation; see include/ps3emu/loadtime_trace.h. */
#include "ps3emu/loadtime_trace.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include <errno.h>
#include <stdint.h>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <pthread.h>
#include <time.h>
#endif

/* Hard cap: a full 600 s load run produces far fewer events than this;
 * past it the observer stops rather than grow without bound. */
#ifndef LT_MAX_EVENTS
#define LT_MAX_EVENTS 4000000u
#endif

static atomic_int g_state = ATOMIC_VAR_INIT(-1);        /* -1 unresolved, 0 off, 1 on */
static FILE* g_out;
static unsigned long long g_t0;          /* QPC/clock counts at anchor */
static unsigned long long g_qpf = 1;     /* counts per second */
static unsigned long long g_events;

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
    if (atomic_load_explicit(&g_state,memory_order_acquire) < 0) {
#ifdef _WIN32
        AcquireSRWLockExclusive(&g_lock);
#else
        pthread_mutex_lock(&g_lock);
#endif
        if (atomic_load_explicit(&g_state,memory_order_acquire) < 0) {
            const char* e = getenv("LOADTIME_TRACE");
            int enabled = (e && *e && strcmp(e,"0") != 0);
            if (enabled) {
                g_qpf = lt_freq();
                g_t0 = lt_now_counts();
                g_out = stderr;
                const char* f = getenv("LOADTIME_TRACE_FILE");
                if (f && *f) {
                    FILE* out = fopen(f, "wb");
                    if (out) g_out = out;
                    else { fprintf(stderr,"[loadtime] fopen failed path=%s errno=%d\n",f,errno); enabled=0; }
                }
                if (enabled) fprintf(g_out, "{\"t_us\":0,\"tid\":0,\"kind\":\"trace_start\","
                               "\"detail\":\"pid_window_begin\",\"anchor_ticks\":%llu,\"clock_hz\":%llu}\n",g_t0,g_qpf);
                if (enabled && fflush(g_out)) { fprintf(stderr,"[loadtime] initial flush failed errno=%d\n",errno); enabled=0; }
            }
            atomic_store_explicit(&g_state,enabled,memory_order_release);
        }
#ifdef _WIN32
        ReleaseSRWLockExclusive(&g_lock);
#else
        pthread_mutex_unlock(&g_lock);
#endif
    }
    return atomic_load_explicit(&g_state,memory_order_acquire);
}

unsigned long long loadtime_us(void)
{
    if (atomic_load_explicit(&g_state,memory_order_acquire) != 1) return 0;
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

static void lt_emit(const char* kind, const char* detail, const char* path)
{
    if (!loadtime_on()) return;
#ifdef _WIN32
    AcquireSRWLockExclusive(&g_lock);
#else
    pthread_mutex_lock(&g_lock);
#endif
    if (atomic_load_explicit(&g_state,memory_order_relaxed) != 1) goto done;
    if (g_events >= LT_MAX_EVENTS) {
        fprintf(g_out,"{\"t_us\":%llu,\"tid\":%u,\"kind\":\"trace_truncated\",\"detail\":\"event_budget_reached\"}\n",loadtime_us(),lt_tid());
        fflush(g_out);
        fprintf(stderr,"[loadtime] event budget reached; trace incomplete\n");
        atomic_store_explicit(&g_state,0,memory_order_release);
        goto done;
    }
    fprintf(g_out,"{\"t_us\":%llu,\"tid\":%u,\"kind\":",loadtime_us(),lt_tid());
    lt_write_escaped(g_out,kind ? kind : "");
    fputs(",\"detail\":",g_out);
    lt_write_escaped(g_out,detail ? detail : "");
    if (path) { fputs(",\"path\":",g_out); lt_write_escaped(g_out,path); }
    fputs("}\n",g_out);
    g_events++;
    if (ferror(g_out) || fflush(g_out)) {
        fprintf(stderr,"[loadtime] trace write/flush failed errno=%d; capture disabled\n",errno);
        atomic_store_explicit(&g_state,0,memory_order_release);
    }
done:
#ifdef _WIN32
    ReleaseSRWLockExclusive(&g_lock);
#else
    pthread_mutex_unlock(&g_lock);
#endif
}
void loadtime_event(const char* kind,const char* detail) { lt_emit(kind,detail,NULL); }
void loadtime_event_path(const char* kind,const char* detail,const char* path) { lt_emit(kind,detail,path); }
