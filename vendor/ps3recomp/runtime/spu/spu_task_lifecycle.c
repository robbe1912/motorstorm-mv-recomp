#include "spu_task_lifecycle.h"
#include "../../libs/spurs/spurs_taskset.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
static SRWLOCK s_lock = SRWLOCK_INIT;
void spu_task_lifecycle_lock(void) { AcquireSRWLockExclusive(&s_lock); }
void spu_task_lifecycle_unlock(void) { ReleaseSRWLockExclusive(&s_lock); }
#else
#include <pthread.h>
static pthread_mutex_t s_lock = PTHREAD_MUTEX_INITIALIZER;
void spu_task_lifecycle_lock(void) { pthread_mutex_lock(&s_lock); }
void spu_task_lifecycle_unlock(void) { pthread_mutex_unlock(&s_lock); }
#endif

typedef struct taskset_state {
    struct taskset_state* next;
    uint32_t ea;
    uint8_t running[16], active[128], started[128];
    uint64_t generation[128], dispatch[128];
} taskset_state;
static taskset_state* s_sets;
static uint64_t s_sequence;

static uint64_t sequence(void)
{
    if (s_sequence == UINT64_MAX) {
        fprintf(stderr, "[taskset] ownership sequence exhausted\n"); abort();
    }
    return ++s_sequence;
}
static taskset_state* state(uint32_t ea, int create)
{
    if (!ea) return NULL;
    for (taskset_state* s = s_sets; s; s = s->next) if (s->ea == ea) return s;
    if (!create) return NULL;
    taskset_state* s = calloc(1, sizeof(*s));
    if (!s) { fprintf(stderr, "[taskset] cannot allocate ownership state\n"); return NULL; }
    s->ea = ea; s->next = s_sets; s_sets = s;
    return s;
}
uint8_t* spu_task_running_locked(uint32_t ea)
{
    taskset_state* s = state(ea, 1); return s ? s->running : NULL;
}
static uint8_t mask(uint32_t id) { return (uint8_t)(0x80u >> (id & 7)); }
static int acquire(uint32_t ea, uint8_t* h, uint32_t id, int fresh, spu_task_owner* o)
{
    if (!h || !o || id >= 128 || !ea) return 0;
    taskset_state* s = state(ea, 1);
    uint8_t m = mask(id);
    if (!s || !(h[0x30 + id/8] & m) || (s->running[id/8] & m)) return 0;
    if (fresh || !s->active[id]) s->generation[id] = sequence();
    s->active[id] = 1; s->started[id] = 0;
    s->dispatch[id] = sequence(); s->running[id/8] |= m;
    *o = (spu_task_owner){ea, id, s->generation[id], s->dispatch[id]};
    return 1;
}
int spu_task_publish_locked(uint32_t ea, uint8_t* h, uint32_t id, spu_task_owner* o)
{ return acquire(ea, h, id, 1, o); }
int spu_task_claim_locked(uint32_t ea, uint8_t* h, uint32_t id, spu_task_owner* o)
{ return acquire(ea, h, id, 0, o); }
int spu_task_current_locked(const spu_task_owner* o)
{
    if (!o || !o->taskset_ea || o->taskid >= 128 || !o->generation || !o->dispatch) return 0;
    taskset_state* s = state(o->taskset_ea, 0); uint32_t id = o->taskid;
    return s && (s->running[id/8] & mask(id)) &&
           s->generation[id] == o->generation && s->dispatch[id] == o->dispatch;
}
int spu_task_start_locked(const spu_task_owner* o, uint8_t* h)
{
    if (!h || !spu_task_current_locked(o)) return 0;
    taskset_state* s = state(o->taskset_ea, 0); uint32_t id = o->taskid;
    if (s->started[id]) return 0;
    s->started[id] = 1; uint8_t m = mask(id);
    vm_write8(o->taskset_ea + id/8, h[id/8] | m);
    vm_write8(o->taskset_ea + 0x10 + id/8, h[0x10 + id/8] & (uint8_t)~m);
    vm_write8(o->taskset_ea + 0x20 + id/8, h[0x20 + id/8] & (uint8_t)~m);
    return 1;
}
int spu_task_finish_locked(const spu_task_owner* o, uint8_t* h, int explicit_exit)
{
    if (!h || !spu_task_current_locked(o)) return 0;
    taskset_state* s = state(o->taskset_ea, 0); uint32_t id = o->taskid;
    if (!s->started[id]) return 0;
    uint8_t m = mask(id);
    s->running[id/8] &= (uint8_t)~m; s->started[id] = 0;
    vm_write8(o->taskset_ea + id/8, h[id/8] & (uint8_t)~m);
    if (explicit_exit) {
        for (unsigned offset = 0x10; offset <= 0x50; offset += 0x10)
            vm_write8(o->taskset_ea + offset + id/8, h[offset + id/8] & (uint8_t)~m);
        s->active[id] = 0;
    }
    return 1;
}
int spu_task_cancel_locked(const spu_task_owner* o, uint8_t* h)
{
    if (!h || !spu_task_current_locked(o)) return 0;
    taskset_state* s = state(o->taskset_ea, 0); uint32_t id = o->taskid;
    s->running[id/8] &= (uint8_t)~mask(id); s->started[id] = 0;
    vm_write8(o->taskset_ea + id/8, h[id/8] & (uint8_t)~mask(id));
    vm_write8(o->taskset_ea + 0x10 + id/8, h[0x10 + id/8] | mask(id));
    return 1;
}
int spu_task_reset_ls(uint64_t* stored, uint64_t generation, uint8_t* ls, size_t size, int* loaded)
{
    if (!stored || !generation || !ls || !loaded) return 0;
    if (*stored == generation) return 0;
    memset(ls, 0, size); *loaded = 0; *stored = generation;
    return 1;
}
