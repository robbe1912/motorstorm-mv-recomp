/* Default-off renderer-thread phase accounting for queued CPU surface reads
 * (RSX_CPU_SURFACE_PROFILE=1). The renderer is the only writer: at each phase
 * transition it charges the QPC time since the previous transition to the
 * innermost open phase. Any thread can snapshot the totals under a sequence
 * count, sampling its clock inside the same window, so the per-phase deltas
 * between a read's queue and service ticks add up exactly to its queue time.
 * Time outside any phase is "other". */
#ifndef RSX_RENDERER_PHASE_H
#define RSX_RENDERER_PHASE_H
#include <stdint.h>
enum {
    RSX_PHASE_OTHER, RSX_PHASE_IDLE, RSX_PHASE_FIFO, RSX_PHASE_DRAW, RSX_PHASE_VERTEX,
    /* Batch submission; render_frame relabels the open submit phase at its
     * stage boundaries (RSX_PHASE_STATS names), the capacity drain at retire. */
    RSX_PHASE_SUBMIT, RSX_PHASE_SUBMIT_DRAIN, RSX_PHASE_SUBMIT_PREP, RSX_PHASE_SUBMIT_REPLAY,
    RSX_PHASE_SUBMIT_POST, RSX_PHASE_SUBMIT_PRESENT, RSX_PHASE_SUBMIT_NEXT, RSX_PHASE_SUBMIT_RETIRE,
    RSX_PHASE_GPU_WAIT, RSX_PHASE_PRESENT, RSX_PHASE_SURFACE, RSX_PHASE_COUNT
};
#ifndef __cplusplus   /* the frame clock (C++) needs only the phases and exports */
#include <stdatomic.h>
#define RSX_PHASE_DEPTH 16
typedef struct RsxRendererPhases {
    _Atomic uint64_t sequence;               /* odd while the renderer charges */
    _Atomic uint64_t total[RSX_PHASE_COUNT];
    _Atomic uint64_t last;                   /* tick of the previous transition */
    _Atomic uint32_t current;                /* innermost open phase */
    uint32_t depth;                          /* renderer only */
    uint8_t stack[RSX_PHASE_DEPTH];
} RsxRendererPhases;
/* The clock is read inside the odd window: a snapshot that sees the same even
 * count before and after its own clock read then lies wholly before or after
 * this transition, never between its tick and its update. */
static void rsx_renderer_phase_charge(RsxRendererPhases *s,uint64_t (*tick)(void),uint32_t next) {
    uint64_t sequence=atomic_load_explicit(&s->sequence,memory_order_relaxed);
    atomic_store_explicit(&s->sequence,sequence+1,memory_order_relaxed);
    atomic_thread_fence(memory_order_seq_cst);
    uint64_t now=tick();
    uint32_t current=atomic_load_explicit(&s->current,memory_order_relaxed);
    uint64_t last=atomic_load_explicit(&s->last,memory_order_relaxed);
    if(now>last) {
        atomic_store_explicit(&s->total[current],atomic_load_explicit(&s->total[current],memory_order_relaxed)+(now-last),memory_order_relaxed);
        atomic_store_explicit(&s->last,now,memory_order_relaxed);
    }
    atomic_store_explicit(&s->current,next,memory_order_relaxed);
    atomic_store_explicit(&s->sequence,sequence+2,memory_order_release);
}
/* Renderer thread only. 0 on an unknown phase or a full stack. */
static int rsx_renderer_phase_enter(RsxRendererPhases *s,uint64_t (*tick)(void),unsigned phase) {
    if(phase>=RSX_PHASE_COUNT || s->depth>=RSX_PHASE_DEPTH)return 0;
    s->stack[s->depth++]=(uint8_t)phase;
    rsx_renderer_phase_charge(s,tick,phase);
    return 1;
}
/* Renderer thread only. 0 when no phase is open (an exit whose enter came
 * before the renderer thread was known); nothing is charged then. */
static int rsx_renderer_phase_exit(RsxRendererPhases *s,uint64_t (*tick)(void)) {
    if(!s->depth)return 0;
    s->depth--;
    rsx_renderer_phase_charge(s,tick,s->depth?s->stack[s->depth-1]:RSX_PHASE_OTHER);
    return 1;
}
/* Renderer thread only. Relabel the innermost open phase when it lies in
 * [first,last]; otherwise (or with none open) nothing changes. 0 when not
 * relabelled. Early returns need no matching exit. */
static int rsx_renderer_phase_switch(RsxRendererPhases *s,uint64_t (*tick)(void),unsigned phase,unsigned first,unsigned last) {
    if(phase>=RSX_PHASE_COUNT || !s->depth)return 0;
    unsigned top=s->stack[s->depth-1];
    if(top<first || top>last || top==phase)return 0;
    s->stack[s->depth-1]=(uint8_t)phase;
    rsx_renderer_phase_charge(s,tick,phase);
    return 1;
}
/* Totals as of *now, from any thread. The clock is read inside the sequence
 * window, so no transition lies between the totals and *now; the open phase
 * is charged up to *now. */
static void rsx_renderer_phase_snapshot(RsxRendererPhases *s,uint64_t (*tick)(void),uint64_t *now,uint64_t out[RSX_PHASE_COUNT]) {
    for(;;) {
        uint64_t before=atomic_load_explicit(&s->sequence,memory_order_acquire);
        if(before&1)continue;
        for(unsigned i=0;i<RSX_PHASE_COUNT;i++)out[i]=atomic_load_explicit(&s->total[i],memory_order_relaxed);
        uint32_t current=atomic_load_explicit(&s->current,memory_order_relaxed);
        uint64_t last=atomic_load_explicit(&s->last,memory_order_relaxed);
        uint64_t t=tick();
        atomic_thread_fence(memory_order_seq_cst);   /* tick before the recheck */
        if(atomic_load_explicit(&s->sequence,memory_order_relaxed)!=before)continue;
        if(t>last)out[current]+=t-last;
        *now=t;return;
    }
}
#endif
/* Exported by the D3D12 backend for the frame clock; no-ops unless profiling. */
#ifdef __cplusplus
extern "C" {
#endif
void rsx_d3d12_renderer_phase_begin(unsigned phase);
void rsx_d3d12_renderer_phase_end(void);
void rsx_d3d12_renderer_phase_submit_stage(unsigned phase);
#ifdef __cplusplus
}
#endif
#endif
