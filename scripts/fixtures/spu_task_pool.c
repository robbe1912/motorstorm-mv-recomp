/* runtime/spu/spu_task_pool.h, the opt-in host thread pool for async SPU tasks
 * (PS3RECOMP_SPU_TASK_POOL=1), on the platform it is compiled for. Synthetic:
 * plain host tasks, no SPU code. The cases follow sp00nznet/ps3recomp#733's
 * tests/test_spu_task_pool.c; the lock, wait and thread calls go through small
 * shims so one file runs on Windows and POSIX.
 *
 *   reuse      back-to-back tasks run on one reused thread
 *   no-queue   tasks that wait for each other all start at once (each task
 *              blocks until every one of them is running), and a task
 *              submitted while every pool thread is busy gets a new thread
 *   stress     submitters on several threads race completions, hand-offs
 *              and retirements; every task runs exactly once, and each
 *              task's record is freed by the task itself
 *   retire     idle threads exit after idle_ms, leaving none behind
 *
 * Every wait has a deadline, so a pool that queues a task behind another
 * fails the run instead of hanging it. */
#if !defined(_WIN32)
#define _POSIX_C_SOURCE 200809L
#endif
#include "spu_task_pool.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
typedef SRWLOCK fx_mutex;
typedef CONDITION_VARIABLE fx_cond;
#define FX_MUTEX_INIT SRWLOCK_INIT
#define FX_COND_INIT CONDITION_VARIABLE_INIT
static void fx_lock(fx_mutex* m) { AcquireSRWLockExclusive(m); }
static void fx_unlock(fx_mutex* m) { ReleaseSRWLockExclusive(m); }
static void fx_broadcast(fx_cond* c) { WakeAllConditionVariable(c); }
static void fx_wait(fx_cond* c, fx_mutex* m, unsigned ms) { SleepConditionVariableSRW(c, m, ms, 0); }
static unsigned long long fx_now_ms(void) { return GetTickCount64(); }
static void fx_sleep_ms(unsigned ms) { Sleep(ms); }
typedef HANDLE fx_thread;
typedef DWORD fx_ret;
#define FX_CALL WINAPI
static int fx_start(fx_thread* t, fx_ret (FX_CALL *fn)(void*), void* arg)
{ *t = CreateThread(NULL, 0, (LPTHREAD_START_ROUTINE)fn, arg, 0, NULL); return *t != NULL; }
static void fx_join(fx_thread t) { WaitForSingleObject(t, INFINITE); CloseHandle(t); }
#else
#include <time.h>
typedef pthread_mutex_t fx_mutex;
typedef pthread_cond_t fx_cond;
#define FX_MUTEX_INIT PTHREAD_MUTEX_INITIALIZER
#define FX_COND_INIT PTHREAD_COND_INITIALIZER
static void fx_lock(fx_mutex* m) { pthread_mutex_lock(m); }
static void fx_unlock(fx_mutex* m) { pthread_mutex_unlock(m); }
static void fx_broadcast(fx_cond* c) { pthread_cond_broadcast(c); }
static void fx_wait(fx_cond* c, fx_mutex* m, unsigned ms)
{
    struct timespec until;
    clock_gettime(CLOCK_REALTIME, &until);
    until.tv_sec += ms / 1000u;
    until.tv_nsec += (long)(ms % 1000u) * 1000000L;
    if (until.tv_nsec >= 1000000000L) { until.tv_sec++; until.tv_nsec -= 1000000000L; }
    pthread_cond_timedwait(c, m, &until);
}
static unsigned long long fx_now_ms(void)
{
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (unsigned long long)now.tv_sec * 1000u + (unsigned long long)now.tv_nsec / 1000000u;
}
static void fx_sleep_ms(unsigned ms)
{
    struct timespec d = { (time_t)(ms / 1000u), (long)(ms % 1000u) * 1000000L };
    nanosleep(&d, NULL);
}
typedef pthread_t fx_thread;
typedef void* fx_ret;
#define FX_CALL
static int fx_start(fx_thread* t, fx_ret (*fn)(void*), void* arg) { return pthread_create(t, NULL, fn, arg) == 0; }
static void fx_join(fx_thread t) { pthread_join(t, NULL); }
#endif

static int failures;
#define CHECK(c) do { if (!(c)) { failures++; \
    fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define FAIL(msg) do { failures++; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, msg); } while (0)

static fx_mutex s_mu = FX_MUTEX_INIT;
static fx_cond  s_cv = FX_COND_INIT;
static unsigned long s_done, s_running, s_peak, s_started;

typedef struct {
    spu_task_pool_item item;      /* embedded, as spu_async_job does */
    unsigned  id;
    unsigned  gate;               /* no-queue: wait until this many started */
    unsigned* runs;               /* stress: per-id run counter */
} task;

static void task_run(void* p)
{
    task* t = (task*)p;
    fx_lock(&s_mu);
    s_running++;
    s_started++;
    if (s_running > s_peak) s_peak = s_running;
    fx_broadcast(&s_cv);
    if (t->gate) {
        const unsigned long long until = fx_now_ms() + 10000u;   /* a deadlock fails the test */
        while (s_started < t->gate && fx_now_ms() < until)
            fx_wait(&s_cv, &s_mu, 100);
    }
    if (t->runs) __atomic_add_fetch(&t->runs[t->id], 1, __ATOMIC_RELAXED);
    s_running--;
    s_done++;
    fx_broadcast(&s_cv);
    fx_unlock(&s_mu);
    free(t);   /* the task owns its record, item included */
}

static task* new_task(unsigned id, unsigned gate, unsigned* runs)
{
    task* t = (task*)calloc(1, sizeof *t);
    if (!t) abort();
    t->id = id; t->gate = gate; t->runs = runs;
    return t;
}

/* 1 when n tasks finished within 20 s. */
static int wait_done(unsigned long n)
{
    const unsigned long long until = fx_now_ms() + 20000u;
    fx_lock(&s_mu);
    while (s_done < n && fx_now_ms() < until) fx_wait(&s_cv, &s_mu, 100);
    const int ok = s_done >= n;
    fx_unlock(&s_mu);
    return ok;
}

static unsigned pool_field(spu_task_pool* pool, const unsigned* field)
{
    spu_task_pool_lock(pool);
    const unsigned v = *field;
    spu_task_pool_unlock(pool);
    return v;
}

/* Wait until `idle` pool threads are parked (so the next submit can reuse). */
static int wait_idle(spu_task_pool* pool, unsigned idle)
{
    for (int i = 0; i < 2000; i++) {
        if (pool_field(pool, &pool->idle) >= idle) return 1;
        fx_sleep_ms(1);
    }
    return 0;
}

static int wait_threads(spu_task_pool* pool, unsigned threads, int ms)
{
    for (int i = 0; i < ms; i++) {
        if (pool_field(pool, &pool->threads) == threads) return 1;
        fx_sleep_ms(1);
    }
    return 0;
}

static void reset(void) { s_done = s_running = s_peak = s_started = 0; }

static int test_reuse(void)
{
    static spu_task_pool pool = SPU_TASK_POOL_INIT(5000u, 1u << 20);
    reset();
    for (unsigned i = 0; i < 100; i++) {
        task* t = new_task(i, 0, NULL);
        CHECK(spu_task_pool_submit(&pool, &t->item, task_run, t) == 1);
        if (!wait_done(i + 1)) { FAIL("reuse: task did not run"); return 0; }
        CHECK(wait_idle(&pool, 1));
    }
    CHECK(pool.created == 1);
    CHECK(pool.reused == 99);
    CHECK(pool.threads == 1);
    printf("reuse: 100 tasks, created=%llu reused=%llu\n", pool.created, pool.reused);
    return 1;
}

static int test_no_queue(void)
{
    static spu_task_pool pool = SPU_TASK_POOL_INIT(5000u, 1u << 20);
    enum { K = 16 };
    reset();
    /* Warm the pool with K idle threads... */
    for (unsigned i = 0; i < K; i++) {
        task* t = new_task(i, K, NULL);
        CHECK(spu_task_pool_submit(&pool, &t->item, task_run, t) == 1);
    }
    if (!wait_done(K)) { FAIL("no-queue: warm-up tasks did not finish"); return 0; }
    CHECK(s_peak == K);
    CHECK(wait_idle(&pool, K));
    /* ...then 2K mutually waiting tasks: K reuse idle threads, K need new
     * ones, and none may wait in the queue behind another. */
    reset();
    for (unsigned i = 0; i < 2 * K; i++) {
        task* t = new_task(i, 2 * K, NULL);
        CHECK(spu_task_pool_submit(&pool, &t->item, task_run, t) == 1);
    }
    if (!wait_done(2 * K)) { FAIL("no-queue: tasks did not finish"); return 0; }
    CHECK(s_peak == 2 * K);
    CHECK(pool.created == 2 * K);
    CHECK(pool.reused == K);
    printf("no-queue: %u mutually waiting tasks all ran at once (created=%llu reused=%llu)\n",
           2 * K, pool.created, pool.reused);
    return 1;
}

typedef struct { spu_task_pool* pool; unsigned first, count; unsigned* runs; } submitter;

static fx_ret FX_CALL submit_many(void* p)
{
    submitter* s = (submitter*)p;
    for (unsigned i = 0; i < s->count; i++) {
        task* t = new_task(s->first + i, 0, s->runs);
        if (spu_task_pool_submit(s->pool, &t->item, task_run, t) != 1) { free(t); abort(); }
        if ((i & 63) == 0) fx_sleep_ms(0);   /* let some threads go idle */
    }
    return 0;
}

static int test_stress_and_retire(void)
{
    static spu_task_pool pool = SPU_TASK_POOL_INIT(20u, 1u << 20);
    enum { SUBMITTERS = 4, PER = 5000, N = SUBMITTERS * PER };
    unsigned* runs = (unsigned*)calloc(N, sizeof *runs);
    if (!runs) abort();
    reset();
    for (int round = 0; round < 2; round++) {
        fx_thread th[SUBMITTERS];
        submitter sub[SUBMITTERS];
        memset(runs, 0, N * sizeof *runs);
        const unsigned long base = s_done;
        for (int k = 0; k < SUBMITTERS; k++) {
            sub[k].pool = &pool; sub[k].first = (unsigned)k * PER; sub[k].count = PER; sub[k].runs = runs;
            if (!fx_start(&th[k], submit_many, &sub[k])) abort();
        }
        for (int k = 0; k < SUBMITTERS; k++) fx_join(th[k]);
        if (!wait_done(base + N)) { FAIL("stress: tasks did not finish"); free(runs); return 0; }
        unsigned bad = 0;
        for (unsigned i = 0; i < N; i++) bad += runs[i] != 1;
        CHECK(bad == 0);
        /* Every idle thread retires after idle_ms; the next round starts empty. */
        CHECK(wait_threads(&pool, 0, 3000));
        spu_task_pool_lock(&pool);
        CHECK(pool.idle == 0 && pool.queued == 0 && pool.head == NULL);
        CHECK(pool.retired == pool.created);
        spu_task_pool_unlock(&pool);
    }
    CHECK(pool.created + pool.reused == 2ull * N);
    CHECK(pool.reused > 0);
    printf("stress: %u tasks from %d submitters, created=%llu reused=%llu retired=%llu\n",
           2 * N, SUBMITTERS, pool.created, pool.reused, pool.retired);
    free(runs);
    return 1;
}

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    /* A case that could not finish leaves tasks behind; stop there. */
    if (test_reuse() && test_no_queue()) test_stress_and_retire();
    if (failures) { fprintf(stderr, "spu task pool: %d failure(s)\n", failures); return 1; }
    puts("PASS: spu task pool reuses idle threads, never queues a task behind another, retires idle threads");
    return 0;
}
