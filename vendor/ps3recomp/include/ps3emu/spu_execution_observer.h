#ifndef PS3EMU_SPU_EXECUTION_OBSERVER_H
#define PS3EMU_SPU_EXECUTION_OBSERVER_H
#include <stdint.h>
#ifndef PS3_EXECUTION_OBSERVATION
#define PS3_EXECUTION_OBSERVATION 0
#endif
#ifdef __cplusplus
extern "C" {
#endif
struct spu_context;
enum {
    PS3_SPU_INTERPRETED_CONTROL = 1, PS3_SPU_COMPILED_DISPATCH,
    PS3_SPU_COMPILED_RETURN, PS3_SPU_NATIVE_BEGIN, PS3_SPU_NATIVE_END,
    PS3_SPU_INTERPRETER_INVOKE
};
enum {
    PS3_SPU_SOURCE_INSTRUCTION = 1, PS3_SPU_SOURCE_UNAVAILABLE = 2,
    PS3_SPU_NATIVE_LOGICAL_PC = 4, PS3_SPU_REDIRECTED = 8,
    PS3_SPU_CLOCK_INVALID = 16, PS3_SPU_TARGET_CONTEXT_PC = 32,
    PS3_SPU_RESOLVED_TARGET = 64
};
typedef struct ps3_spu_execution_event {
    uint64_t tick, detail;
    uintptr_t context, function;
    uint32_t kind, flags, source_pc, target_pc;
    int32_t image, host_depth;
    uint32_t policy_mode;
} ps3_spu_execution_event;
typedef struct ps3_spu_execution_observer {
    void* user;
    uint64_t (*clock)(void*);
    void (*observe)(void*, const ps3_spu_execution_event*);
    int (*accept)(void*, uint32_t kind, uintptr_t context,
                  uint32_t source_pc, uint32_t target_pc);
} ps3_spu_execution_observer;
/* Install/clear only with all producers quiescent and synchronized before
 * resuming; report a rejected installation as a capture setup failure.
 * Retain immutable observer
 * and user until then. Callbacks return normally, never change guest state,
 * reenter execution, allocate, format, perform I/O or take application locks.
 * NULL accept admits all. Rejections imply missing coverage, not absent work.
 * Callbacks may run concurrently; the owner must be thread-safe.
 * Owner supplies one clock; zero is flagged. Cross-event chronology and clock
 * regressions require owner validation. Context/function pointers and image IDs
 * are raw observations, not lifetime-qualified job identities.
 *
 * Interpreted control events report the instruction's actual resulting PC,
 * including conditional fallthrough. They do not assert a branch was taken.
 * Dispatch reports the selected function immediately BEFORE invocation, after
 * interrupt resolution; it does not prove its first instruction executed.
 * Interpreter invocation may subsequently admit a native leaf; it does not
 * establish that any interpreted instruction ran. Compiled returns have an
 * unavailable source PC. Native events bracket only
 * the accepted execute callback and continuation validation, not prepare cost.
 * Direct compiled calls, interrupts unwinding through longjmp, faults and other
 * nonreturning paths do not acquire fabricated begin/end pairs.
 * Uninstrumented generated units remain uncovered and must be reported.
 */
int ps3_spu_execution_observer_install(const ps3_spu_execution_observer*);
#if PS3_EXECUTION_OBSERVATION
void ps3_spu_execution_notify(uint32_t, struct spu_context*, uint32_t, uint32_t,
                              uint64_t, uint32_t, uintptr_t);
#define PS3_SPU_EXECUTION(...) ps3_spu_execution_notify(__VA_ARGS__)
#define PS3_SPU_DISPATCH_BASE(fn) uintptr_t _ps3_exec_original = (uintptr_t)(fn)
#define PS3_SPU_DISPATCH(ctx, fn) PS3_SPU_EXECUTION(PS3_SPU_COMPILED_DISPATCH, \
    (ctx), 0, (ctx)->pc, (uint64_t)_ps3_exec_original, \
    PS3_SPU_SOURCE_UNAVAILABLE | PS3_SPU_TARGET_CONTEXT_PC | \
    ((uintptr_t)(fn) != _ps3_exec_original ? PS3_SPU_REDIRECTED : 0), (uintptr_t)(fn))
#define PS3_SPU_RESOLVED(ctx, fn) PS3_SPU_EXECUTION(PS3_SPU_COMPILED_DISPATCH, \
    (ctx), 0, (ctx)->pc, (uint64_t)(uintptr_t)(fn), \
    PS3_SPU_SOURCE_UNAVAILABLE | PS3_SPU_TARGET_CONTEXT_PC | PS3_SPU_RESOLVED_TARGET, (uintptr_t)(fn))
#else
#define PS3_SPU_EXECUTION(...) ((void)0)
#define PS3_SPU_DISPATCH_BASE(fn) ((void)0)
#define PS3_SPU_DISPATCH(ctx, fn) ((void)0)
#define PS3_SPU_RESOLVED(ctx, fn) ((void)0)
#endif
#ifdef __cplusplus
}
#endif
#endif
