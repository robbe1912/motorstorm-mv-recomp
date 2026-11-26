#include "vehicle_update.h"
#include "spu_interp.h"
#include "spu_native_leaf.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>

// The drain loop of the lifted path calls the function at each block boundary. All job images of
// the game run as lifted code, so this is the path of the kernel in the game. The interpreter
// path uses the native leaf below. WIRING.txt holds the two lines of the drain loop.
extern "C" {
typedef int (*spu_lifted_leaf_fn)(spu_context*, uint32_t);
extern spu_lifted_leaf_fn g_spu_lifted_leaf_try;
int motorstorm_vehicle_update_lifted(spu_context* ctx, uint32_t return_pc);
}

namespace {
constexpr uint32_t entry = MOTORSTORM_VEHICLE_ENTRY, epilogue = MOTORSTORM_VEHICLE_RETURN;
enum class Mode { reference, shadow, native };
Mode mode = Mode::reference;

bool recognized_image(const uint8_t* ls) {
    // The module of image 219 starts at 0x4000. The vehicle object (0x21400 to 0x23220) is
    // data of the job: it is not part of the identity. Qualify the module on every call; no
    // cached identity survives a reuse of the local store.
    constexpr uint32_t ranges[][2] = {{0x4000, 0x21400}, {0x23220, 0x26200}};
    uint64_t fingerprint = UINT64_C(1469598103934665603);
    for (const auto& range : ranges)
        for (uint32_t address = range[0]; address < range[1]; address += 8) {
            uint64_t word;
            std::memcpy(&word, ls + address, sizeof(word));
            fingerprint = (fingerprint ^ word) * UINT64_C(1099511628211);
        }
    return fingerprint == UINT64_C(0xb117ce9e8829eb73);
}
[[noreturn]] void fail(const char* message) {
    std::fprintf(stderr, "NATIVE_VEHICLE_UPDATE_ERROR %s\n", message);
    std::abort();
}

struct Snapshot {
    u128 gpr[128];
    uint8_t ls[MOTORSTORM_VEHICLE_LS_SIZE];
};
thread_local Snapshot saved;       // state of the entry or of the point of take-over
thread_local uint8_t kernel_ls[MOTORSTORM_VEHICLE_LS_SIZE];
thread_local u128 kernel_gpr[128];
thread_local bool inside;          // the original path of the shadow mode nests a drain call
thread_local bool gave_up;         // the kernel stopped in this drain call: do not try again

// Returns 1 when the kernel result stands (ctx->pc is then the return address). Returns 2 when
// the original path ran (shadow mode) and its result stands. Returns 0 when the kernel stopped
// at a block that it does not hold: the state of the start is then restored.
int run(spu_context* ctx, uint32_t address, bool lifted) {
    MotorstormVehicleState state = {};
    std::memcpy(state.gpr, ctx->gpr, sizeof(state.gpr));
    state.ls = ctx->ls;
    const int done = lifted ? motorstorm_vehicle_update_at(&state, address) : motorstorm_vehicle_update(&state);
    if (mode == Mode::shadow || !done) {
        const bool compare = mode == Mode::shadow && done;
        if (compare) {
            std::memcpy(kernel_ls, ctx->ls, sizeof(kernel_ls));
            std::memcpy(kernel_gpr, state.gpr, sizeof(kernel_gpr));
        }
        void (*next)(spu_context*) = g_spu_trampoline_fn;   // lifted path: the block that runs next
        std::memcpy(ctx->ls, saved.ls, sizeof(saved.ls));
        std::memcpy(ctx->gpr, saved.gpr, sizeof(saved.gpr));
        ctx->pc = address;
        if (!done) return 0;
        // Shadow mode: the original path runs on the state of the start.
        if (lifted) {
            const bool outer = inside;
            inside = true;
            ++ctx->host_depth;
            g_spu_trampoline_fn = next;
            spu_drain_call(ctx, epilogue);
            --ctx->host_depth;
            inside = outer;
        } else {
            spu_interp_run_until(ctx, entry, epilogue);
        }
        if (ctx->pc != epilogue) fail("the original path did not return");
        if (compare) {
            const bool ls_differs = std::memcmp(kernel_ls, ctx->ls, sizeof(kernel_ls)) != 0;
            int reg = -1;
            for (int i = 0; i < 128 && reg < 0; ++i)
                if (std::memcmp(&kernel_gpr[i], &ctx->gpr[i], sizeof(u128))) reg = i;
            if (ls_differs || reg >= 0) fail(ls_differs ? "local store comparison" : "register comparison");
        }
        return 2;
    }
    std::memcpy(ctx->gpr, state.gpr, sizeof(state.gpr));
    ctx->pc = epilogue;
    // The walk-in bookkeeping of the policy module uses the address of the block that ran last.
    if (ctx->policy_mode) ctx->wi_prev_pc = state.pc;
    return 1;
}

// Conditions of both paths: the state of the SPU is plain (no stall, no interrupt, no
// reservation) and the module of image 219 is in the local store.
bool guards(const spu_context* ctx) {
    if (!ctx->policy_mode || ctx->ls != ctx->ls_store || ctx->status != SPU_STATUS_RUNNING ||
        ctx->list_stall_mask || !ctx->int_enable || (ctx->event_mask & ~2u) ||
        (__atomic_load_n(&ctx->event_status, __ATOMIC_ACQUIRE) & ctx->event_mask) || ctx->irq_saved ||
        __atomic_load_n(&ctx->resv_valid, __ATOMIC_ACQUIRE) || !recognized_image(ctx->ls))
        return false;
    for (const auto& span : ctx->resident_code) if (span.size) {
        const uint64_t end = uint64_t(span.lsa) + span.size;
        if ((span.lsa > entry && span.lsa < epilogue) || (end > entry && end < epilogue)) return false;
    }
    return !(ctx->wi_span_lo > entry && ctx->wi_span_lo < epilogue) &&
           !(ctx->wi_span_hi > entry && ctx->wi_span_hi < epilogue);
}

void count(int result) {
    static std::atomic<uint64_t> completed{0}, compared{0}, bailed{0};
    const auto calls = completed.fetch_add(1, std::memory_order_relaxed) + 1;
    if (result == 2) compared.fetch_add(1, std::memory_order_relaxed);
    if (!result) bailed.fetch_add(1, std::memory_order_relaxed);
    // The line comes at call 1 and after each 256 calls. `calls` is the number of runs of the
    // kernel from the start of the process, not the number of calls in one frame.
    if (calls == 1 || calls % 256 == 0)
        std::fprintf(stderr, "[native-vehicle-update] calls=%llu compared=%llu bailed=%llu (next line after 256 calls)\n",
            static_cast<unsigned long long>(calls),
            static_cast<unsigned long long>(compared.load(std::memory_order_relaxed)),
            static_cast<unsigned long long>(bailed.load(std::memory_order_relaxed)));
}

// Native leaf of the interpreter path. The interpreter reaches the entry of the extent.
void execute(spu_context* ctx, const spu_native_leaf_plan* plan) {
    if (plan->cookie != &saved) fail("plan ownership");
    const int result = run(ctx, entry, false);
    if (!result) {
        // The kernel does not hold a block of this call. The original path runs here: the leaf
        // must end at its resume address.
        ctx->pc = entry;
        spu_interp_run_until(ctx, entry, epilogue);
        if (ctx->pc != epilogue) fail("the original path did not return");
    }
    count(result ? 1 : 0);
}

int prepare(const spu_context* ctx, uint64_t, spu_native_leaf_plan* plan) {
    if (mode == Mode::reference || ctx->pc != entry || !guards(ctx)) return 0;
    // The kernel works in place. A stop restores the state of the entry, so keep a copy.
    std::memcpy(saved.gpr, ctx->gpr, sizeof(saved.gpr));
    std::memcpy(saved.ls, ctx->ls, sizeof(saved.ls));
    *plan = {0, epilogue, 0, execute, &saved};
    return 1;
}

struct Register {
    Register() {
        const char* value = std::getenv("MS_NATIVE_VEHICLE_UPDATE");
        if (!value || !std::strcmp(value, "0")) return;
        if (!std::strcmp(value, "shadow")) mode = Mode::shadow;
        else if (!std::strcmp(value, "1")) mode = Mode::native;
        else fail("invalid mode");
        const spu_native_leaf leaf{entry, epilogue, prepare};
        if (spu_native_leaf_register_unbudgeted(&leaf)) fail("registration");
        g_spu_lifted_leaf_try = motorstorm_vehicle_update_lifted;
        std::fprintf(stderr, "[native-vehicle-update] mode=%s\n", value);
    }
} register_vehicle_update;
}

// Entry of the lifted path. The drain loop calls it at the top of its block loop. The first
// block of the extent has run at that point. Returns 1 or 2: ctx->pc is then the return address.
// Returns 0: nothing changed.
int motorstorm_vehicle_update_lifted(spu_context* ctx, uint32_t return_pc) {
    if (gave_up) {
        if (ctx->drain_ret_pc != epilogue) gave_up = false;
        else return 0;
    }
    if (mode == Mode::reference || inside || return_pc != epilogue || ctx->pc == epilogue || !guards(ctx))
        return 0;
    std::memcpy(saved.gpr, ctx->gpr, sizeof(saved.gpr));
    std::memcpy(saved.ls, ctx->ls, sizeof(saved.ls));
    const int result = run(ctx, ctx->pc & SPU_LS_MASK, true);
    if (result)
        g_spu_trampoline_fn = spu_indirect_branch;   // the drain loop then sees its return address
    else
        gave_up = true;
    count(result);
    return result;
}
