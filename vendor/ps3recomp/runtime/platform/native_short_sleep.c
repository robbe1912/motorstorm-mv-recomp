#include "native_short_sleep.h"
#ifdef _WIN32
#include <windows.h>
#include <fenv.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(_M_X64) || defined(_M_IX86) || defined(__SSE__)
#include <xmmintrin.h>
#define SHORT_SLEEP_MXCSR 1
#endif
#ifndef CREATE_WAITABLE_TIMER_HIGH_RESOLUTION
#define CREATE_WAITABLE_TIMER_HIGH_RESOLUTION 0x00000002
#endif

static INIT_ONCE short_once = INIT_ONCE_STATIC_INIT;
static DWORD short_key = FLS_OUT_OF_INDEXES;
static uint64_t short_frequency;
static int short_enabled;

static void short_fatal(const char* reason) {
    fprintf(stderr,"[short-sleep] ERROR %s (Win32=%lu)\n",reason,(unsigned long)GetLastError());
    abort();
}
static VOID CALLBACK short_destroy(PVOID timer) {
    if (timer && !CloseHandle((HANDLE)timer)) short_fatal("timer close at thread exit");
}
static BOOL CALLBACK short_init(PINIT_ONCE once, PVOID param, PVOID* context) {
    (void)once; (void)param; (void)context;
    const char* value=getenv("PS3_NATIVE_SHORT_SLEEP");
    if (!value || !strcmp(value,"0")) return TRUE;
    if (strcmp(value,"1")) short_fatal("PS3_NATIVE_SHORT_SLEEP must be 0 or 1");
    LARGE_INTEGER frequency;
    if (!QueryPerformanceFrequency(&frequency) || frequency.QuadPart<=0)
        short_fatal("invalid performance-counter frequency");
    short_frequency=(uint64_t)frequency.QuadPart;
    short_key=FlsAlloc(short_destroy);
    if (short_key==FLS_OUT_OF_INDEXES) {
        fprintf(stderr,"[short-sleep] FlsAlloc failed (%lu); reference waits retained\n",(unsigned long)GetLastError());
        return TRUE;
    }
    short_enabled=1;
    fprintf(stderr,"[short-sleep] native blocking waits enabled, frequency=%llu\n",(unsigned long long)short_frequency);
    return TRUE;
}
static int short_fallback(HANDLE timer,const char* reason) {
    DWORD error=GetLastError();
    if (timer) {
        if (!FlsSetValue(short_key,NULL)) short_fatal("clearing failed timer ownership");
        if (!CloseHandle(timer)) short_fatal("closing failed timer");
    }
    fprintf(stderr,"[short-sleep] %s failed (%lu); executing reference wait\n",reason,(unsigned long)error);
    return 0;
}
static uint64_t short_now(void) {
    LARGE_INTEGER now;
    if (!QueryPerformanceCounter(&now) || now.QuadPart<0) short_fatal("invalid performance counter");
    return (uint64_t)now.QuadPart;
}
static int short_wait(uint64_t usec) {
    if (!InitOnceExecuteOnce(&short_once,short_init,NULL,NULL))
        return short_fallback(NULL,"InitOnceExecuteOnce");
    if (!short_enabled) return 0;
    /* Split multiplication avoids overflow when converting a sub-ms request. */
    uint64_t whole=(short_frequency/1000000)*usec;
    uint64_t part=(short_frequency%1000000)*usec;
    uint64_t ticks=whole+part/1000000+(part%1000000!=0);
    uint64_t begin=short_now();
    if (begin>(uint64_t)INT64_MAX-ticks) short_fatal("deadline overflow");
    uint64_t deadline=begin+ticks,previous=begin;
    HANDLE timer=(HANDLE)FlsGetValue(short_key);
    if (!timer) {
        timer=CreateWaitableTimerExW(NULL,NULL,CREATE_WAITABLE_TIMER_HIGH_RESOLUTION,SYNCHRONIZE|TIMER_MODIFY_STATE);
        if (!timer) return short_fallback(NULL,"CreateWaitableTimerExW");
        if (!FlsSetValue(short_key,timer)) {
            DWORD error=GetLastError();
            if (!CloseHandle(timer)) short_fatal("closing unowned timer");
            SetLastError(error);
            return short_fallback(NULL,"FlsSetValue");
        }
    }
    for (;;) {
        uint64_t now=short_now();
        if (now<previous) short_fatal("performance counter moved backwards");
        if (now>=deadline) return 1;
        previous=now;
        uint64_t remaining=deadline-now;
        if (remaining>UINT64_MAX/10000000) short_fatal("relative timer conversion overflow");
        uint64_t numerator=remaining*10000000;
        uint64_t relative=numerator/short_frequency+(numerator%short_frequency!=0);
        if (!relative || relative>(uint64_t)INT64_MAX) short_fatal("invalid relative timer");
        LARGE_INTEGER due; due.QuadPart=-(LONGLONG)relative;
        if (!SetWaitableTimerEx(timer,&due,0,NULL,NULL,NULL,0)) return short_fallback(timer,"SetWaitableTimerEx");
        if (WaitForSingleObject(timer,INFINITE)!=WAIT_OBJECT_0) return short_fallback(timer,"WaitForSingleObject");
        /* Older/early notifications must re-block; never spin to the deadline. */
    }
}
int ps3_native_short_sleep(uint64_t usec) {
    if (!usec || usec>=1000) return 0;
    fenv_t environment;
    if (fegetenv(&environment)) short_fatal("saving caller floating-point state");
#ifdef SHORT_SLEEP_MXCSR
    unsigned csr=_mm_getcsr();
#endif
    int result=short_wait(usec);
    if (fesetenv(&environment)) short_fatal("restoring caller floating-point state");
#ifdef SHORT_SLEEP_MXCSR
    _mm_setcsr(csr);
#endif
    return result;
}
#else
int ps3_native_short_sleep(uint64_t usec) { (void)usec; return 0; }
#endif
