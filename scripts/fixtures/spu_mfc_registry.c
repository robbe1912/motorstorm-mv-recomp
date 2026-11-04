/* Actual registry, authored opaque contexts/engine payloads. No guest bytes. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "win32_compat.h"
#ifdef _MSC_VER
#define SPU_THREAD_LOCAL __declspec(thread)
#else
#define SPU_THREAD_LOCAL __thread
#endif
typedef struct { unsigned identity; } spu_context;
typedef struct { unsigned tag_mask, queue_count; } mfc_engine;
static void mfc_engine_init(mfc_engine *e) { memset(e, 0, sizeof(*e)); }
static volatile LONG locks;
static void counted_lock(SRWLOCK *lock) {
    InterlockedIncrement(&locks);
    AcquireSRWLockExclusive(lock);
}
#define AcquireSRWLockExclusive counted_lock
#include "spu_mfc_registry.h"
#undef AcquireSRWLockExclusive
static unsigned checks, failures;
static void check(int ok, const char *name) {
    ++checks;
    if (!ok) { ++failures; fprintf(stderr, "FAIL %s\n", name); }
}
static spu_context contexts[32];
static mfc_engine *engines[32];
static volatile LONG ready, start;
static DWORD WINAPI claim(void *arg) {
    unsigned i = (unsigned)(uintptr_t)arg;
    InterlockedIncrement(&ready);
    ULONGLONG deadline = GetTickCount64() + 5000;
    while (!InterlockedCompareExchange(&start, 0, 0)) {
        if (GetTickCount64() > deadline) return 1;
        SwitchToThread();
    }
    engines[i] = mfc_for(&contexts[i]);
    return 0;
}
static DWORD WINAPI release_other_thread(void *ctx) {
    spu_mfc_release((spu_context *)ctx); return 0;
}
int main(void) {
    HANDLE threads[32];
    for (unsigned i = 0; i < 32; ++i) {
        threads[i] = CreateThread(NULL, 0, claim, (void *)(uintptr_t)i, 0, NULL);
        if (!threads[i]) return 2;
    }
    ULONGLONG deadline = GetTickCount64() + 5000;
    while (InterlockedCompareExchange(&ready, 0, 0) != 32) {
        if (GetTickCount64() > deadline) return 2;
        SwitchToThread();
    }
    InterlockedExchange(&start, 1);
    int joined = 1;
    for (unsigned i = 0; i < 32; ++i) {
        DWORD code = 1;
        if (WaitForSingleObject(threads[i], 10000) != WAIT_OBJECT_0 ||
            !GetExitCodeThread(threads[i], &code) || code) joined = 0;
        CloseHandle(threads[i]);
    }
    check(joined, "concurrent claims complete");
    int unique = 1, fresh = 1;
    for (unsigned i = 0; i < 32; ++i) {
        if (!engines[i]) return 2;
        if (engines[i]->queue_count || engines[i]->tag_mask) fresh = 0;
        for (unsigned j = 0; j < i; ++j) if (engines[i] == engines[j]) unique = 0;
    }
    check(unique, "32 retained contexts own distinct engines");
    check(fresh, "new engines start with empty queues and tags");
    for (unsigned i = 0; i < 32; ++i) engines[i]->tag_mask = 0x100 + i;
    int stable = 1, private = 1, warm_locks = 0;
    for (unsigned i = 0; i < 32; ++i) {
        if (mfc_for(&contexts[i]) != engines[i]) stable = 0; /* warm this host */
        LONG before = locks;
        for (unsigned n = 0; n < 1000; ++n)
            if (mfc_for(&contexts[i]) != engines[i]) stable = 0;
        warm_locks += locks - before;
        if (engines[i]->tag_mask != 0x100 + i) private = 0;
    }
    check(stable, "warm lookups preserve engine identity");
    check(private, "queue and tag ownership stays private");
    check(warm_locks == 0, "32000 warm lookups acquire no registry locks");
    /* This thread holds a cached overflow pointer; another releases it while
     * its SPU is stopped. Reusing the same context address must be fresh. */
    unsigned victim = 0;
    for (unsigned i = 0; i < 32; ++i) {
        int inline_slot = 0;
        for (unsigned j = 0; j < SPU_MAX_CONTEXTS; ++j)
            if (engines[i] == &s_mfc_slots[j].mfc) inline_slot = 1;
        if (!inline_slot) { victim = i; break; }
    }
    (void)mfc_for(&contexts[victim]);
    HANDLE releaser = CreateThread(NULL, 0, release_other_thread, &contexts[victim], 0, NULL);
    if (!releaser || WaitForSingleObject(releaser, 10000) != WAIT_OBJECT_0) return 2;
    CloseHandle(releaser);
    mfc_engine *reused = mfc_for(&contexts[victim]);
    check(reused->tag_mask == 0 && reused->queue_count == 0,
          "cross-thread release invalidates cached pointer and address reuse");
    reused->tag_mask = 0x800;
    spu_mfc_release(&contexts[31]); /* also invalidate an unrelated cache */
    if (victim != 31)
        check(mfc_for(&contexts[victim])->tag_mask == 0x800,
              "unrelated release preserves live engine payload");
    unsigned inline_owner = 32, overflow_owner = 32;
    mfc_engine *overflow_engine = NULL;
    for (unsigned i = 0; i < 31; ++i) {
        if (i == victim) continue;
        mfc_engine *e = mfc_for(&contexts[i]);
        int inline_slot = 0;
        for (unsigned j = 0; j < SPU_MAX_CONTEXTS; ++j)
            if (e == &s_mfc_slots[j].mfc) inline_slot = 1;
        if (inline_slot) inline_owner = i;
        else { overflow_owner = i; overflow_engine = e; }
    }
    if (inline_owner == 32 || overflow_owner == 32) return 2;
    spu_mfc_release(&contexts[inline_owner]);
    check(mfc_for(&contexts[overflow_owner]) == overflow_engine &&
          overflow_engine->tag_mask == 0x100 + overflow_owner,
          "free inline slot does not migrate an existing overflow owner");
    for (unsigned i = 0; i < 32; ++i) spu_mfc_release(&contexts[i]);
    int empty = 1;
    for (unsigned i = 0; i < SPU_MAX_CONTEXTS; ++i) if (s_mfc_slots[i].ctx) empty = 0;
    check(empty, "all inline owners released");
    check(s_mfc_overflow == NULL, "all private overflow engines released");
    printf("checks=%u failures=%u warm_locks=%d\n", checks, failures, warm_locks);
    return failures ? 1 : 0;
}
