/* Actual runner result bridge; execution and device hooks are host adapters. */
#include "spu_lifted_job.h"
#include "task_vm_fixture.h"
#include <assert.h>
#ifdef NDEBUG
#error Runner fixture requires assertions
#endif
static int exit_next;
static void entry(spu_context* c) {
    assert(!c->task_exit_requested && !c->gpr[127]._u32[0]);
    c->task_exit_requested = exit_next == 1; c->gpr[127]._u32[0] = 0xbad;
    if (exit_next == 2) c->stop_code = 0x123; /* An ordinary STOP is not task EXIT. */
}
int spu_run_with_halt(spu_lifted_entry_fn fn, spu_context* c) { fn(c); return exit_next; }
void spu_coh_unregister(spu_context* c) { (void)c; }
int main(void)
{
    uint32_t reason = 99;
    exit_next = 0;
    assert(spu_run_lifted_job_abi_result(entry, NULL, 0, 0, 0, NULL, NULL, &reason) == 0 && reason == 0);
    exit_next = 2;
    assert(spu_run_lifted_job_abi_result(entry, NULL, 0, 0, 0, NULL, NULL, &reason) == 0 && reason == 0);
    exit_next = 1;
    assert(spu_run_lifted_job_abi_result(entry, NULL, 0, 0, 0, NULL, NULL, &reason) == 0 && reason == 1);
    exit_next = 0;
    assert(spu_run_lifted_job_abi_result(entry, NULL, 0, 0, 0, NULL, NULL, &reason) == 0 && reason == 0);
    assert(spu_run_lifted_job_abi_result(NULL, NULL, 0, 0, 0, NULL, NULL, &reason) == -1 && reason == 0);
    puts("PASS actual runner: return/EXIT/return/no-entry result, fresh context"); return 0;
}
