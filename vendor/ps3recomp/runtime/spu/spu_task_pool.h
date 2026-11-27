/*
 * ps3recomp - a host thread pool for async SPU tasks
 *
 * spu_workload_dispatch_* runs each async SPU task on its own detached host
 * thread, and a title can start several per frame. Each new thread pays the
 * creation, a cold stack and fresh thread-local state again. This pool runs
 * the tasks on reused threads without changing what a task can rely on:
 *
 *  - Every task still starts at once, on a thread of its own. A task is handed
 *    to the pool only when more pool threads are idle and waiting than tasks
 *    are already queued for them; otherwise a new pool thread is created for
 *    it, exactly as without the pool. So a task that waits for another task
 *    can never be queued behind it, and there are never fewer threads than
 *    running tasks.
 *  - A pool thread that has been idle for idle_ms without work exits.
 *
 * The pool owns no task memory. spu_task_pool_submit() takes an item the
 * caller embeds in its own task record; the item must stay valid until the
 * task starts running, and the run function may free it.
 *
 * Header-only so a synthetic test can drive it directly. The POSIX half is
 * sp00nznet/ps3recomp#733 (6f88eec1); the Windows half follows it with
 * SRW locks, a condition variable and CreateThread (stack_size is reserved,
 * not committed).
 */
#ifndef PS3RECOMP_SPU_TASK_POOL_H
#define PS3RECOMP_SPU_TASK_POOL_H

#include <stddef.h>

struct spu_task_pool;

typedef struct spu_task_pool_item {
    void (*run)(void* arg);
    void* arg;
    struct spu_task_pool* pool;
    struct spu_task_pool_item* next;
} spu_task_pool_item;

#if !defined(_WIN32)
#include <errno.h>
#include <pthread.h>
#include <time.h>

typedef struct spu_task_pool {
    pthread_mutex_t mu;
    pthread_cond_t  cv;
    spu_task_pool_item* head;
    spu_task_pool_item* tail;
    unsigned queued;               /* handed off, not yet picked up */
    unsigned idle;                 /* pool threads waiting for work */
    unsigned threads;              /* pool threads alive */
    unsigned long long reused;     /* tasks handed to an idle thread */
    unsigned long long created;    /* tasks that got a new thread */
    unsigned long long retired;    /* threads that exited idle */
    unsigned idle_ms;              /* idle time before a thread exits */
    size_t   stack_size;           /* per-thread stack reservation; 0 = default */
} spu_task_pool;

#define SPU_TASK_POOL_INIT(idle_ms, stack_size)                          \
    { PTHREAD_MUTEX_INITIALIZER, PTHREAD_COND_INITIALIZER, NULL, NULL,   \
      0, 0, 0, 0, 0, 0, (idle_ms), (stack_size) }
#define spu_task_pool_lock(p)   pthread_mutex_lock(&(p)->mu)
#define spu_task_pool_unlock(p) pthread_mutex_unlock(&(p)->mu)

static inline void* spu_task_pool_thread(void* p)
{
    spu_task_pool_item* it = (spu_task_pool_item*)p;
    spu_task_pool* pool = it->pool;
    for (;;) {
        /* Copy out first: the task may free the record the item lives in. */
        void (*run)(void*) = it->run;
        void* arg = it->arg;
        run(arg);

        pthread_mutex_lock(&pool->mu);
        pool->idle++;
        struct timespec until;
        clock_gettime(CLOCK_REALTIME, &until);
        until.tv_sec  += (time_t)(pool->idle_ms / 1000u);
        until.tv_nsec += (long)(pool->idle_ms % 1000u) * 1000000L;
        if (until.tv_nsec >= 1000000000L) { until.tv_sec++; until.tv_nsec -= 1000000000L; }
        int timed_out = 0;
        while (!pool->head && !timed_out)
            timed_out = pthread_cond_timedwait(&pool->cv, &pool->mu, &until) == ETIMEDOUT;
        pool->idle--;
        /* A queued task is taken even after a timeout: it was handed off
         * while this thread still counted as idle. */
        if (!pool->head) {
            pool->threads--;
            pool->retired++;
            pthread_mutex_unlock(&pool->mu);
            return NULL;
        }
        it = pool->head;
        pool->head = it->next;
        if (!pool->head) pool->tail = NULL;
        pool->queued--;
        pthread_mutex_unlock(&pool->mu);
    }
}

/* Start run(arg) now: on an idle pool thread if one is free, else on a new
 * one. 1 when the task is running or about to, 0 when no thread could be
 * created (the item is then unused and the caller still owns its task). */
static inline int spu_task_pool_submit(spu_task_pool* pool, spu_task_pool_item* it,
                                void (*run)(void*), void* arg)
{
    it->run = run;
    it->arg = arg;
    it->pool = pool;
    it->next = NULL;

    pthread_mutex_lock(&pool->mu);
    if (pool->idle > pool->queued) {
        if (pool->tail) pool->tail->next = it; else pool->head = it;
        pool->tail = it;
        pool->queued++;
        pool->reused++;
        pthread_cond_signal(&pool->cv);
        pthread_mutex_unlock(&pool->mu);
        return 1;
    }
    /* Counted before the thread runs, so a later hand-off sees it. */
    pool->threads++;
    pool->created++;
    pthread_mutex_unlock(&pool->mu);

    pthread_t th;
    int rc = EINVAL;
    if (pool->stack_size) {
        pthread_attr_t attr;
        pthread_attr_init(&attr);
        if (pthread_attr_setstacksize(&attr, pool->stack_size) == 0)
            rc = pthread_create(&th, &attr, spu_task_pool_thread, it);
        pthread_attr_destroy(&attr);
    }
    /* A host that will not reserve that much still gets the thread, on the
     * default stack, as the thread-per-task path does. */
    if (rc != 0)
        rc = pthread_create(&th, NULL, spu_task_pool_thread, it);
    if (rc != 0) {
        pthread_mutex_lock(&pool->mu);
        pool->threads--;
        pool->created--;
        pthread_mutex_unlock(&pool->mu);
        return 0;
    }
    pthread_detach(th);
    return 1;
}

#else /* _WIN32 */
#include <windows.h>

typedef struct spu_task_pool {
    SRWLOCK            mu;
    CONDITION_VARIABLE cv;
    spu_task_pool_item* head;
    spu_task_pool_item* tail;
    unsigned queued;               /* handed off, not yet picked up */
    unsigned idle;                 /* pool threads waiting for work */
    unsigned threads;              /* pool threads alive */
    unsigned long long reused;     /* tasks handed to an idle thread */
    unsigned long long created;    /* tasks that got a new thread */
    unsigned long long retired;    /* threads that exited idle */
    unsigned idle_ms;              /* idle time before a thread exits */
    size_t   stack_size;           /* per-thread stack reservation; 0 = default */
} spu_task_pool;

#define SPU_TASK_POOL_INIT(idle_ms, stack_size)                          \
    { SRWLOCK_INIT, CONDITION_VARIABLE_INIT, NULL, NULL,                 \
      0, 0, 0, 0, 0, 0, (idle_ms), (stack_size) }
#define spu_task_pool_lock(p)   AcquireSRWLockExclusive(&(p)->mu)
#define spu_task_pool_unlock(p) ReleaseSRWLockExclusive(&(p)->mu)

static DWORD WINAPI spu_task_pool_thread(LPVOID p)
{
    spu_task_pool_item* it = (spu_task_pool_item*)p;
    spu_task_pool* pool = it->pool;
    for (;;) {
        /* Copy out first: the task may free the record the item lives in. */
        void (*run)(void*) = it->run;
        void* arg = it->arg;
        run(arg);

        AcquireSRWLockExclusive(&pool->mu);
        pool->idle++;
        const ULONGLONG until = GetTickCount64() + pool->idle_ms;
        int timed_out = 0;
        while (!pool->head && !timed_out) {
            const ULONGLONG now = GetTickCount64();
            if (now >= until) { timed_out = 1; break; }
            /* Spurious and timed-out wakes both re-check the queue and the
             * deadline; only the deadline ends the wait. */
            SleepConditionVariableSRW(&pool->cv, &pool->mu, (DWORD)(until - now), 0);
        }
        pool->idle--;
        /* A queued task is taken even after a timeout: it was handed off
         * while this thread still counted as idle. */
        if (!pool->head) {
            pool->threads--;
            pool->retired++;
            ReleaseSRWLockExclusive(&pool->mu);
            return 0;
        }
        it = pool->head;
        pool->head = it->next;
        if (!pool->head) pool->tail = NULL;
        pool->queued--;
        ReleaseSRWLockExclusive(&pool->mu);
    }
}

/* Start run(arg) now: on an idle pool thread if one is free, else on a new
 * one. 1 when the task is running or about to, 0 when no thread could be
 * created (the item is then unused and the caller still owns its task).
 * *new_thread (optional) receives the new thread's handle, which the caller
 * must close, or NULL when an idle thread took the task. */
static inline int spu_task_pool_submit_ex(spu_task_pool* pool, spu_task_pool_item* it,
                                          void (*run)(void*), void* arg, HANDLE* new_thread)
{
    it->run = run;
    it->arg = arg;
    it->pool = pool;
    it->next = NULL;
    if (new_thread) *new_thread = NULL;

    AcquireSRWLockExclusive(&pool->mu);
    if (pool->idle > pool->queued) {
        if (pool->tail) pool->tail->next = it; else pool->head = it;
        pool->tail = it;
        pool->queued++;
        pool->reused++;
        WakeConditionVariable(&pool->cv);
        ReleaseSRWLockExclusive(&pool->mu);
        return 1;
    }
    /* Counted before the thread runs, so a later hand-off sees it. */
    pool->threads++;
    pool->created++;
    ReleaseSRWLockExclusive(&pool->mu);

    HANDLE th = NULL;
    if (pool->stack_size)
        th = CreateThread(NULL, pool->stack_size, spu_task_pool_thread, it,
                          STACK_SIZE_PARAM_IS_A_RESERVATION, NULL);
    /* A host that will not reserve that much still gets the thread, on the
     * default stack. */
    if (!th)
        th = CreateThread(NULL, 0, spu_task_pool_thread, it, 0, NULL);
    if (!th) {
        AcquireSRWLockExclusive(&pool->mu);
        pool->threads--;
        pool->created--;
        ReleaseSRWLockExclusive(&pool->mu);
        return 0;
    }
    if (new_thread) *new_thread = th; else CloseHandle(th);
    return 1;
}

static inline int spu_task_pool_submit(spu_task_pool* pool, spu_task_pool_item* it,
                                       void (*run)(void*), void* arg)
{
    return spu_task_pool_submit_ex(pool, it, run, arg, NULL);
}
#endif /* _WIN32 */

#endif /* PS3RECOMP_SPU_TASK_POOL_H */
