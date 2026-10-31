/* Exercises actual storage using authored complete atomic observations. */
#include "ps3emu/sized_trace.h"
#include "ps3emu/native_atomic_observer.h"
#include <assert.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
typedef HANDLE thread;
static void yield_thread(void) { SwitchToThread(); }
#else
#include <pthread.h>
#include <sched.h>
typedef pthread_t thread;
static void yield_thread(void) { sched_yield(); }
#endif
static atomic_int hold, reserved, release_writer;
static void before_copy(ps3_sized_trace*, uint64_t);
#define PS3_SIZED_TRACE_BEFORE_COPY(trace, index) before_copy(trace, index)
#ifndef SIZED_TRACE_IMPLEMENTATION
#define SIZED_TRACE_IMPLEMENTATION "../../vendor/ps3recomp/runtime/diag/sized_trace.c"
#endif
#include SIZED_TRACE_IMPLEMENTATION
static void before_copy(ps3_sized_trace* trace, uint64_t index)
{
    (void)trace; (void)index;
    if (!atomic_load_explicit(&hold, memory_order_acquire)) return;
    atomic_store_explicit(&reserved, 1, memory_order_release);
    while (!atomic_load_explicit(&release_writer, memory_order_acquire)) yield_thread();
}
#define WORKERS 4u
#define COUNT 1024u
typedef struct producer { ps3_sized_trace* trace; unsigned id, count; } producer;
#ifdef _WIN32
static DWORD WINAPI produce(LPVOID arg)
#else
static void* produce(void* arg)
#endif
{
    producer* p = arg;
    for (unsigned n = 0; n < p->count; ++n) {
        ps3_atomic_observation e = {0};
        e.begin_tick = n + 1; e.end_tick = n + 2; e.address = p->id;
        e.source = PS3_ATOMIC_SPU_STORE; e.flags = PS3_ATOMIC_COMMITTED;
        for (unsigned i = 0; i < 128; ++i) {
            e.before[i] = (unsigned char)(n + i + p->id);
            e.after[i] = (unsigned char)~e.before[i];
        }
        assert(ps3_sized_trace_append(p->trace, &e, sizeof(e)) == PS3_SIZED_TRACE_RECORDED);
    }
    return 0;
}
#ifdef _WIN32
static thread start(producer* p) { thread t = CreateThread(NULL, 0, produce, p, 0, NULL); assert(t); return t; }
static void join(thread t) { assert(WaitForSingleObject(t, 15000) == WAIT_OBJECT_0); assert(CloseHandle(t)); }
#else
static thread start(producer* p) { thread t; assert(!pthread_create(&t, NULL, produce, p)); return t; }
static void join(thread t) { assert(!pthread_join(t, NULL)); }
#endif
int main(void)
{
    assert(!ps3_sized_trace_create(0, 1));
    assert(!ps3_sized_trace_create(1, 0));
    assert(!ps3_sized_trace_create(1, PS3_SIZED_TRACE_MAX_PAYLOAD + 1));
    assert(!ps3_sized_trace_create(PS3_SIZED_TRACE_MAX_RECORDS + 1, 1));
    ps3_atomic_observation e = {0}, out = {0};
    assert(ps3_sized_trace_append(NULL, &e, sizeof(e)) == PS3_SIZED_TRACE_DISABLED);
    ps3_sized_trace* trace = ps3_sized_trace_create(1, sizeof(e)); assert(trace);
    assert(ps3_sized_trace_append(trace, &e, sizeof(e) - 1) == PS3_SIZED_TRACE_INVALID);
    out.address = 42;
    atomic_store(&hold, 1);
    producer p = {trace, 0, 1}; thread t = start(&p);
    while (!atomic_load_explicit(&reserved, memory_order_acquire)) yield_thread();
    assert(ps3_sized_trace_read(trace, 0, &out, sizeof(out)) == 0 && out.address == 42);
    atomic_store_explicit(&release_writer, 1, memory_order_release); join(t);
    atomic_store(&hold, 0);
    assert(ps3_sized_trace_read(trace, 0, &out, sizeof(out)) == 1);
    assert(ps3_sized_trace_read(trace, 0, &out, sizeof(out) - 1) == -1);
    assert(ps3_sized_trace_append(trace, &e, sizeof(e)) == PS3_SIZED_TRACE_FULL);
    ps3_sized_trace_info info;
    assert(ps3_sized_trace_describe(trace, &info) && info.attempted == 2 && info.dropped == 1);
    assert(info.payload_size == sizeof(e) && info.record_stride >= sizeof(e) + sizeof(uint64_t));
    atomic_store(&trace->attempted, UINT64_MAX); atomic_store(&trace->dropped, UINT64_MAX);
    assert(ps3_sized_trace_append(trace, &e, sizeof(e)) == PS3_SIZED_TRACE_FULL);
    assert(ps3_sized_trace_describe(trace, &info) && info.attempted == UINT64_MAX && info.dropped == UINT64_MAX);
    ps3_sized_trace_destroy(trace);
    trace = ps3_sized_trace_create(WORKERS * COUNT, sizeof(e)); assert(trace);
    producer producers[WORKERS]; thread threads[WORKERS];
    for (unsigned i = 0; i < WORKERS; ++i) { producers[i] = (producer){trace,i,COUNT}; threads[i] = start(&producers[i]); }
    for (unsigned i = 0; i < WORKERS; ++i) join(threads[i]);
    unsigned char seen[WORKERS][COUNT] = {{0}};
    for (unsigned i = 0; i < WORKERS * COUNT; ++i) {
        assert(ps3_sized_trace_read(trace, i, &out, sizeof(out)) == 1);
        unsigned lane = (unsigned)out.address, n = (unsigned)out.begin_tick - 1;
        assert(lane < WORKERS && n < COUNT && !seen[lane][n]++);
        assert(out.end_tick == n + 2 && out.source == PS3_ATOMIC_SPU_STORE && out.flags == PS3_ATOMIC_COMMITTED);
        for (unsigned j = 0; j < 128; ++j) {
            unsigned char before = (unsigned char)(n + j + lane);
            assert(out.before[j] == before && out.after[j] == (unsigned char)~before);
        }
    }
    assert(ps3_sized_trace_describe(trace, &info) && info.attempted == WORKERS * COUNT && !info.dropped);
    ps3_sized_trace_destroy(trace);
    unsigned char odd[13], odd_result[13];
    memset(odd, 0xA5, sizeof(odd)); memset(odd_result, 0, sizeof(odd_result));
    trace = ps3_sized_trace_create(2, sizeof(odd)); assert(trace);
    assert(ps3_sized_trace_append(trace, odd, sizeof(odd)) == PS3_SIZED_TRACE_RECORDED);
    assert(ps3_sized_trace_append(trace, odd, sizeof(odd)) == PS3_SIZED_TRACE_RECORDED);
    assert(ps3_sized_trace_read(trace, 1, odd_result, sizeof(odd_result)) == 1 && !memcmp(odd, odd_result, sizeof(odd)));
    assert(ps3_sized_trace_describe(trace, &info) && info.record_stride % _Alignof(sized_slot) == 0);
    ps3_sized_trace_destroy(trace);
    puts("PASS complete atomic payloads, pending publication, overflow, saturation and concurrent writers");
    return 0;
}
