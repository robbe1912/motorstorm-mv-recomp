/* Authored API-boundary fixture. No game inputs or SPU execution.
 * Link the actual cellSpurs.c and BE taskset builder; only dispatch is stubbed. */
#include "cellSpurs.h"
#include "spu_workload.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif

uint8_t *vm_base;
uint32_t sysmem_spu_alias_fixup(uint32_t a) { if (a >= 0x40000) abort(); return a; }
volatile int g_spu_coh_armed;
int g_resv_store_active;
uint32_t g_ww_lo, g_ww_hi;
void ppu_resv_break_store(uint64_t a) { (void)a; abort(); }
void ps3_ww_report_inline(uint32_t a, uint64_t v, int n) { (void)a; (void)v; (void)n; abort(); }
volatile unsigned char vm_read_sync_pages[1u << 20];
void vm_read_sync_dispatch(uint32_t a, uint32_t n) { (void)a; (void)n; abort(); }
int spu_coh_is_reserved(uint32_t a) { (void)a; return 0; }
void spu_lockline_lock(void) {}
void spu_lockline_unlock(void) {}
void spu_coh_notify_write(uint32_t a) { (void)a; }
extern uint32_t g_ydkj_real_taskset_ea;
static unsigned dispatches;
static size_t image_extent = 64;
size_t spu_elf_image_size(const uint8_t *p, size_t n) {
    if (p != vm_base + 0x20000 || n < 64) abort();
    return image_extent;
}
int spu_workload_dispatch_async(const uint8_t *p, uint32_t n, uint32_t a
#ifdef SPURS_DISPATCH_HAS_OVERRIDE
                                , const uint32_t *arg
#endif
                                ) {
    if (p != vm_base + 0x20000 || n != 64 || a != 0) abort();
#ifdef SPURS_DISPATCH_HAS_OVERRIDE
    if (arg != NULL) abort();
#endif
    dispatches++;
    return 1;
}

#define TS 0x10000u
int spu_workload_dispatch_task(const uint8_t *p, uint32_t n, uint32_t a,
                               const uint32_t *arg, uint32_t ts, uint32_t id) {
    if (ts != TS || id != 1 || arg != NULL) abort();
    return spu_workload_dispatch_async(p, n, a
#ifdef SPURS_DISPATCH_HAS_OVERRIDE
                                      , arg
#endif
                                      );
}

#ifdef SPU_TASK_LIFECYCLE_H
static spu_task_owner dispatched_owner;
int spu_workload_dispatch_owned(const uint8_t* p, uint32_t n, uint32_t a,
                                const uint32_t* arg, const spu_task_owner* owner) {
    if (!owner || !owner->generation || !owner->dispatch) abort();
    dispatched_owner = *owner;
    return spu_workload_dispatch_task(p, n, a, arg, owner->taskset_ea, owner->taskid);
}
#endif
static int failures;
static void prepare(uint8_t expected[128]) {
    memset(vm_base + TS - 16, 0x7B, 0x1900 + 32);
    memset(vm_base + TS, 0, 0x1900);
    /* Existing running tasks are also enabled; task1 is the first free slot. */
    memset(vm_base + TS, 0xA5, 16);
    memset(vm_base + TS + 0x30, 0xA5, 16);
    memcpy(expected, vm_base + TS, 128);
    g_ydkj_real_taskset_ea = TS;
}
static void check(const char *name, s32 rc, const uint8_t expected[128]) {
    int bad = rc != CELL_OK || memcmp(expected, vm_base + TS, 128) != 0;
    for (unsigned i = 0; i < 16; i++)
        bad |= vm_base[TS-16+i] != 0x7B || vm_base[TS+0x1900+i] != 0x7B;
    if (bad) {
        failures++;
        fprintf(stderr, "FAIL %s: rc=%d; unexpected guest header/guard write\n", name, rc);
    } else printf("PASS %s: guest header footprint preserved\n", name);
}
int main(void) {
#ifdef _WIN32
    vm_base = _aligned_malloc(0x40000, 128);
#else
    vm_base = aligned_alloc(128, 0x40000);
#endif
    if (!vm_base) return 2;
    memset(vm_base, 0, 0x40000);
    uint8_t expected[128];
    CellSpursTaskset *handle = (CellSpursTaskset *)(uintptr_t)TS;
    prepare(expected);
    check("DestroyTaskset", cellSpursDestroyTaskset(handle), expected);
    prepare(expected);
    check("ShutdownTaskset", cellSpursShutdownTaskset(handle), expected);
    prepare(expected);
    expected[0x10] = 0x40;  /* newly-created task1 ready */
    expected[0x30] |= 0x40; /* task1 enabled; existing task bits preserved */
    s32 rc = cellSpursCreateTask(handle, (CellSpursTaskId *)(uintptr_t)0x4000,
                                (void *)(uintptr_t)0x20000, NULL, 0, 0, 0);
    check("CreateTask", rc, expected);
    if (dispatches != 1 || memcmp(vm_base + 0x4000, "\0\0\0\1", 4)) failures++;
    if (cellSpursDestroyTaskset(NULL) != CELL_SPURS_TASK_ERROR_NULL_POINTER ||
        cellSpursShutdownTaskset(NULL) != CELL_SPURS_TASK_ERROR_NULL_POINTER ||
        cellSpursCreateTask(NULL, NULL, NULL, NULL, 0, 0, 0) != CELL_SPURS_TASK_ERROR_NULL_POINTER)
        failures++;
#ifdef SPU_TASK_LIFECYCLE_H
    spu_task_lifecycle_lock();
    if (!spu_task_cancel_locked(&dispatched_owner, vm_base + TS)) abort();
    spu_task_lifecycle_unlock();
    prepare(expected); image_extent = 0;
    rc = cellSpursCreateTask(handle, (CellSpursTaskId *)(uintptr_t)0x4000,
                            (void *)(uintptr_t)0x20000, NULL, 0, 0, 0);
    spu_task_lifecycle_lock();
    spu_task_owner retry;
    int released = spu_task_claim_locked(TS, vm_base + TS, 1, &retry);
    if (released) spu_task_cancel_locked(&retry, vm_base + TS);
    spu_task_lifecycle_unlock();
    if (rc != CELL_OK || !released || dispatches != 1) {
        fprintf(stderr, "FAIL InitialDispatchCancel: unavailable ELF keeps execution claim\n");
        failures++;
    } else printf("PASS InitialDispatchCancel: unavailable ELF is ready for retry\n");
#endif
#ifdef _WIN32
    _aligned_free(vm_base);
#else
    free(vm_base);
#endif
    printf("guest-field fixture failures=%d\n", failures);
    return failures ? 1 : 0;
}
