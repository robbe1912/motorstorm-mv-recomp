/* Authored host lifecycle fixture. No game bytes or guest instructions. */
#include "spu_task_lifecycle.h"
#include "task_vm_fixture.h"
#include <assert.h>
#ifdef NDEBUG
#error Lifecycle fixture requires assertions
#endif
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#endif
static uint8_t* concurrent_header;
static void concurrent_lifetimes(unsigned id)
{
    uint8_t m = (uint8_t)(0x80u >> id);
    for (unsigned i = 0; i < 256; ++i) {
        spu_task_owner o;
        spu_task_lifecycle_lock();
        concurrent_header[0x30] |= m; concurrent_header[0x10] |= m;
        assert(spu_task_publish_locked(0x20000, concurrent_header, id, &o));
        assert(spu_task_start_locked(&o, concurrent_header));
        spu_task_lifecycle_unlock();
        spu_task_lifecycle_lock();
        assert(spu_task_finish_locked(&o, concurrent_header, 1));
        assert(concurrent_header[0x30] & 1);
        spu_task_lifecycle_unlock();
    }
}
#ifdef _WIN32
static DWORD WINAPI thread_main(void* p) { concurrent_lifetimes((unsigned)(uintptr_t)p); return 0; }
#else
static void* thread_main(void* p) { concurrent_lifetimes((unsigned)(uintptr_t)p); return NULL; }
#endif
int main(void)
{
    vm_base = calloc(1, 0x50000); assert(vm_base);
    uint8_t* h = vm_base + 0x10000;
    concurrent_header = vm_base + 0x20000;
    uint8_t ls[64]; uint64_t stored = 0; int loaded = 1;
    h[128] = 0x7b; h[129] = 0x7b;
    spu_task_owner old = {0};
    for (unsigned i = 0; i < 512; ++i) {
        spu_task_owner o;
        spu_task_lifecycle_lock();
        for (unsigned off = 0; off <= 0x50; off += 0x10) h[off] = 0xc0;
        assert(spu_task_publish_locked(0x10000, h, 0, &o));
        assert(o.generation != old.generation);
        assert(!spu_task_finish_locked(&old, h, 1));
        assert(spu_task_start_locked(&o, h));
        assert(!spu_task_start_locked(&o, h));
        memset(ls, 0xa5, sizeof ls); loaded = 1;
        assert(spu_task_reset_ls(&stored, o.generation, ls, sizeof ls, &loaded));
        assert(!loaded); for (unsigned b = 0; b < sizeof ls; ++b) assert(!ls[b]);
        ls[0] = 0x55; loaded = 1;
        assert(!spu_task_reset_ls(&stored, o.generation, ls, sizeof ls, &loaded));
        assert(ls[0] == 0x55 && loaded);
        assert(spu_task_finish_locked(&o, h, 1));
        for (unsigned off = 0; off <= 0x50; off += 0x10) assert(h[off] == 0x40);
        assert(h[128] == 0x7b && h[129] == 0x7b);
        old = o; spu_task_lifecycle_unlock();
    }
    /* Return/yield retains enabled, READY and LS; a resumed dispatch has a new
     * execution token within the same incarnation. Late cleanup is rejected. */
    spu_task_owner a, b;
    spu_task_lifecycle_lock(); h[0x30] = 0xc0;
    assert(spu_task_publish_locked(0x10000, h, 0, &a));
    assert(spu_task_start_locked(&a, h)); h[0x10] |= 0x80;
    assert(spu_task_finish_locked(&a, h, 0));
    assert(h[0x30] == 0xc0 && (h[0x10] & 0x80));
    assert(spu_task_claim_locked(0x10000, h, 0, &b));
    assert(a.generation == b.generation && a.dispatch != b.dispatch);
    assert(!spu_task_finish_locked(&a, h, 1));
    assert(spu_task_start_locked(&b, h));
    assert(spu_task_finish_locked(&b, h, 1));
    /* Failed dispatch releases only this execution and relatches READY. */
    h[0x30] |= 0x80;
    assert(spu_task_publish_locked(0x10000, h, 0, &a));
    assert(spu_task_cancel_locked(&a, h));
    assert((h[0x30] & 0x80) && (h[0x10] & 0x80));
    assert(spu_task_claim_locked(0x10000, h, 0, &b));
    assert(!spu_task_cancel_locked(&a, h));
    assert(spu_task_start_locked(&b, h)); assert(spu_task_finish_locked(&b, h, 1));
    assert(!spu_task_publish_locked(0, h, 0, &a));
    assert(!spu_task_publish_locked(0x10000, h, 128, &a));
    for (unsigned i = 0; i < 16; ++i) {
        uint8_t* other = vm_base + 0x30000 + i*0x1000; other[0x30] = 0x80;
        assert(spu_task_publish_locked(0x30000 + i*0x1000, other, 0, &a));
        assert(spu_task_start_locked(&a, other)); assert(spu_task_finish_locked(&a, other, 1));
    }
    spu_task_lifecycle_unlock();
    concurrent_header[0x30] = 1;
#ifdef _WIN32
    HANDLE threads[4];
    for (unsigned i = 0; i < 4; ++i) { threads[i] = CreateThread(NULL, 0, thread_main, (void*)(uintptr_t)i, 0, NULL); assert(threads[i]); }
    assert(WaitForMultipleObjects(4, threads, TRUE, 30000) == WAIT_OBJECT_0);
    for (unsigned i = 0; i < 4; ++i) CloseHandle(threads[i]);
#else
    pthread_t threads[4];
    for (unsigned i = 0; i < 4; ++i) assert(!pthread_create(&threads[i], NULL, thread_main, (void*)(uintptr_t)i));
    for (unsigned i = 0; i < 4; ++i) assert(!pthread_join(threads[i], NULL));
#endif
    assert(concurrent_header[0x30] == 1);
    puts("PASS lifecycle: 512 recycled + 1024 concurrent lifetimes; return, stale owner, LS and neighbors");
    return 0;
}
