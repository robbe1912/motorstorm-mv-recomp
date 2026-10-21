/* Default-off CPU surface latency accounting. All durations use one QPC clock. */
#ifndef RSX_CPU_SURFACE_PROFILE_H
#define RSX_CPU_SURFACE_PROFILE_H
#include <stdint.h>
typedef struct RsxCpuSurfaceProfile {
    uint64_t queued, started, finished, returned;
    uint64_t allocation, prior_fence, commands, copy_fence, packing;
    uint64_t matched, hits, copies, host_bytes, guest_bytes;
} RsxCpuSurfaceProfile;
static int rsx_cpu_surface_profile_valid(const RsxCpuSurfaceProfile *p) {
    if(p->started<p->queued || p->finished<p->started || p->returned<p->finished)return 0;
    uint64_t remaining=p->finished-p->started;
    const uint64_t stages[]={p->allocation,p->prior_fence,p->commands,p->copy_fence,p->packing};
    for(unsigned i=0;i<5;i++) { if(stages[i]>remaining)return 0;remaining-=stages[i]; }
    return p->copies<=p->matched && p->hits<=p->matched-p->copies;
}
#endif
