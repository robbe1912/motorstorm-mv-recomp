/* Complete actual cleanup plus the real lifecycle module. No guest execution. */
#define spu_workload_dispatch_async unused_async_declaration
#include "spu_workload.h"
#undef spu_workload_dispatch_async
#include "win32_compat.h"
#include "spu_task_lifecycle_trace.h"
#include "task_vm_fixture.h"
#include <stdio.h>
#include <string.h>
static void ts_lock(void) { spu_task_lifecycle_lock(); }
static void ts_unlock(void) { spu_task_lifecycle_unlock(); }
static uint8_t* ts_running(uint32_t ea) { return spu_task_running_locked(ea); }
size_t spu_elf_image_size(const uint8_t* p, size_t n) { (void)p; (void)n; abort(); }
int spu_workload_dispatch_async(const uint8_t* p, uint32_t n, uint32_t a, ...) { (void)p; (void)n; (void)a; abort(); }
int spu_workload_dispatch_task(const uint8_t* p, uint32_t n, uint32_t a,
    const uint32_t* arg, uint32_t ea, uint32_t id) { (void)p; (void)n; (void)a; (void)arg; (void)ea; (void)id; abort(); }
int spu_workload_dispatch_owned(const uint8_t* p, uint32_t n, uint32_t a,
    const uint32_t* arg, const spu_task_owner* o) { (void)p; (void)n; (void)a; (void)arg; (void)o; abort(); }
/* ACTUAL_COMPLETION */
static void complete(const spu_task_owner* o, int exited)
{
#ifdef TOKEN_COMPLETION
    spu_taskset_task_exited(o, 1, NULL, exited);
#else
    (void)exited; spu_taskset_task_exited(o->taskset_ea, o->taskid, 1, NULL);
#endif
}
static spu_task_owner prepare(uint32_t ea)
{
    spu_task_owner o; uint8_t* h = vm_base + ea;
    h[0x30] = 0xc0; h[0x10] = 0x80;
    ts_lock();
    if (!spu_task_publish_locked(ea, h, 0, &o) || !spu_task_start_locked(&o, h)) abort();
    ts_unlock(); return o;
}
int main(void)
{
    vm_base = calloc(1, 0x40000); if (!vm_base) abort(); int failures = 0;
    spu_task_owner a = prepare(0x10000);
    vm_base[0x10010] |= 0x80; complete(&a, 0);
    if (vm_base[0x10030] != 0xc0 || !(vm_base[0x10010] & 0x80)) {
        puts("FAIL return ownership: ordinary return destroyed guest state"); failures++;
    }
    a = prepare(0x11000); complete(&a, 1);
    if (vm_base[0x11030] != 0x40) { puts("FAIL EXIT retirement: selected enabled bit retained"); failures++; }
    a = prepare(0x12000);
    ts_lock(); if (!spu_task_finish_locked(&a, vm_base+0x12000, 1)) abort(); ts_unlock();
    spu_task_owner b = prepare(0x12000); uint8_t before[128]; memcpy(before, vm_base+0x12000, 128);
    complete(&a, 1);
    ts_lock(); int current = spu_task_current_locked(&b); ts_unlock();
    if (!current || memcmp(before, vm_base+0x12000, 128)) { puts("FAIL stale owner: delayed cleanup damaged replacement"); failures++; }
#ifdef TOKEN_COMPLETION
    complete(&b, 1);
    for (unsigned i = 0; i < 512; ++i) {
        a = prepare(0x13000); complete(&a, 1);
        if (vm_base[0x13030] != 0x40) { puts("FAIL recycled EXIT"); failures++; break; }
    }
#endif
    printf("Actual cleanup failures=%d\n", failures); return failures ? 1 : 0;
}
