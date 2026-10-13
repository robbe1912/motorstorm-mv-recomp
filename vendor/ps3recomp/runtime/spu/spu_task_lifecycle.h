#ifndef SPU_TASK_LIFECYCLE_H
#define SPU_TASK_LIFECYCLE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct spu_task_owner {
    uint32_t taskset_ea, taskid;
    uint64_t generation, dispatch;
} spu_task_owner;

/* One lock covers host identity and guest bitset publication/retirement.
 * All *_locked calls require it. Returned running storage is stable. */
void spu_task_lifecycle_lock(void);
void spu_task_lifecycle_unlock(void);
uint8_t* spu_task_running_locked(uint32_t taskset_ea);
int spu_task_publish_locked(uint32_t taskset_ea, uint8_t* header,
                           uint32_t taskid, spu_task_owner* owner);
int spu_task_claim_locked(uint32_t taskset_ea, uint8_t* header,
                         uint32_t taskid, spu_task_owner* owner);
int spu_task_current_locked(const spu_task_owner* owner);
int spu_task_start_locked(const spu_task_owner* owner, uint8_t* header);
int spu_task_finish_locked(const spu_task_owner* owner, uint8_t* header,
                          int explicit_exit);
int spu_task_cancel_locked(const spu_task_owner* owner, uint8_t* header);
/* Called with the per-slot LS lock held; suspension keeps the same generation. */
int spu_task_reset_ls(uint64_t* stored_generation, uint64_t generation,
                      uint8_t* ls, size_t size, int* loaded);
#ifdef __cplusplus
}
#endif
#endif
