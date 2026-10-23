#include "ps3emu/spu_execution_observer.h"
#if PS3_EXECUTION_OBSERVATION
#include "../spu/spu_context.h"
static const ps3_spu_execution_observer* observer;
#endif
int ps3_spu_execution_observer_install(const ps3_spu_execution_observer* value) {
#if PS3_EXECUTION_OBSERVATION
    if (value && (!value->clock || !value->observe)) return 0;
    observer = value;
    return 1;
#else
    return value == 0;
#endif
}
#if PS3_EXECUTION_OBSERVATION
void ps3_spu_execution_notify(uint32_t kind, spu_context* ctx,
    uint32_t source, uint32_t target, uint64_t detail, uint32_t flags,
    uintptr_t function) {
    const ps3_spu_execution_observer* value = observer;
    if (!value || !ctx) return;
    if (value->accept && !value->accept(value->user, kind, (uintptr_t)ctx,
                                      source, target)) return;
    ps3_spu_execution_event event = {0};
    event.tick = value->clock(value->user);
    event.detail = detail; event.context = (uintptr_t)ctx; event.function = function;
    event.kind = kind; event.flags = flags | (!event.tick ? PS3_SPU_CLOCK_INVALID : 0);
    event.source_pc = source; event.target_pc = target;
    event.image = ctx->image_id; event.host_depth = ctx->host_depth;
    event.policy_mode = ctx->policy_mode;
    value->observe(value->user, &event);
}
#endif
