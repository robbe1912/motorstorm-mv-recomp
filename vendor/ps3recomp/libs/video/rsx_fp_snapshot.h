/* Exact-byte snapshot reuse for native fragment-program recording.
 * Bound bytes/hash must come from one admitted valid program (seed zero).
 * A structurally recycled live address keeps the previously bound program;
 * inline-constant edits refresh it. No cross-draw live-memory cache is assumed.
 */
#ifndef PS3RECOMP_RSX_FP_SNAPSHOT_H
#define PS3RECOMP_RSX_FP_SNAPSHOT_H
#include <string.h>
#include "rsx_fp_decompiler.h"
enum rsx_fp_snapshot_action {
    RSX_FP_SNAPSHOT_INVALID = -1,
    RSX_FP_SNAPSHOT_KEEP = 0,
    RSX_FP_SNAPSHOT_REFRESH = 1
};
static inline int rsx_fp_snapshot_check(const u8* live, const u8* bound,
                                       u32 size, u32 capacity, u64 hash)
{
    if (!live || !bound || !hash || !size || size > capacity)
        return RSX_FP_SNAPSHOT_INVALID;
    if (memcmp(live, bound, size) == 0)
        return RSX_FP_SNAPSHOT_KEEP;
    return rsx_fp_structural_hash(live, capacity, 0) == hash
        ? RSX_FP_SNAPSHOT_REFRESH : RSX_FP_SNAPSHOT_KEEP;
}
#endif
