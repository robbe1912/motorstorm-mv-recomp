/* Entry of the native kernel of the PVS job (SPU image 210, spupvs). PvsKernel-5.

   scripts/native_game_binding.py binds each entry to one lifted function head of the generated
   unit jobmod_056ac0eea1a6_e12270. The binding gives the lifted function the name
   game_original_pvs_XXXX. A wrapper with the lifted name calls motorstorm_pvs_entry_XXXX
   (pvs_kernel.c). game_pvs_XXXX_code_matches compares the code in the local store with the bytes
   of the original ELF.

   The kernel (pvs_kernel.c, made by temp/pvskernel/p5_gen.py) runs the statements of the lifted
   functions of the job image. A direct call is a C call. A jump is a tail call. The lifted functions
   with a channel, a DMA command, a stop or a halt stay lifted, and the kernel runs them in the
   lifted call bracket (vu_lcall, vu_icall_lifted of pvs_kernel.c).

   The kernel ends in one of four ways, and ctx then holds the state of the lifted path at that point:
     RETURN    a return at kernel depth 0. pc is the return address. The trampoline is
               spu_indirect_branch when host_depth is 0 (the state of SPU_RET).
     JUMP      a jump to lifted code at depth 0. The lifted function of the target is the trampoline.
     INDIRECT  a jump through a register with a change of the interrupt state. spu_indirect_branch is
               the trampoline.
     DONE      the code reached the return address of the drain. That drain returns.
   The drain that called the entry (spu_drain_call) goes on from that state on its normal path.

   The lifted code runs when the mode is off, when the admission refuses the context, or when the
   kernel stops. A stop puts back the local store pages that the kernel changed (copy on write),
   then the lifted function of the entry runs from its start.

   MS_NATIVE_PVS selects the mode. Absent or "0": lifted code only. "1": kernel. "shadow": the
   kernel and the lifted code run on two copies of the context up to the return address of the
   drain. A difference stops the program. The game state comes from the lifted code. */
#include "spu_context.h"
#include "pvs_kernel.h"
#include "spu_native_owned.h"

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <new>
#include <utility>

extern "C" {
void game_original_pvs_4030(spu_context* ctx);
int game_pvs_4030_code_matches(const spu_context* ctx);
extern int g_spu_pm_svc_on; /* the PM service switch of the SPU runtime (spu_native_owned.h) */
}

namespace {

constexpr uint32_t kImage = 0x4000;       /* image 210 is at 0x4000..0x164F0 of the local store */
constexpr uint32_t kImageEnd = 0x16500;
constexpr uint32_t kLsSize = 0x40000;
constexpr uint32_t kLsMask = kLsSize - 1u;
constexpr uint32_t kPage = 0x1000;
constexpr uint32_t kPages = kLsSize / kPage;

struct Entry {
    uint32_t address;
    void (*original)(spu_context* ctx);
    int (*matches)(const spu_context* ctx);
};

const Entry kEntries[] = {
    {0x4030u, game_original_pvs_4030, game_pvs_4030_code_matches},
};

uint32_t env_mode() {
    const char* text = std::getenv("MS_NATIVE_PVS");
    if (text && !std::strcmp(text, "1")) return MOTORSTORM_PVS_NATIVE;
    return text && !std::strcmp(text, "shadow") ? MOTORSTORM_PVS_SHADOW : MOTORSTORM_PVS_REFERENCE;
}

std::atomic<uint32_t> g_mode{env_mode()};
std::atomic<uint64_t> g_calls, g_native, g_compared, g_fallbacks, g_bails;

/* The exit of the last kernel run of the thread. */
thread_local uint32_t t_exit_kind = 0, t_bail_pc = 0;

struct alignas(64) Box {
    spu_context context;
};

/* Storage of one thread. A thread runs one SPU context at a time. The thread frees the storage
   when it ends. */
struct Storage {
    uint8_t* saved = static_cast<uint8_t*>(std::calloc(kLsSize, 1));
    Box* boxes = nullptr;
    ~Storage() {
        std::free(saved);
        delete[] boxes;
    }
};

thread_local Storage value;

/* The job image in the local store is the plain image: no overlay and no walk-in span covers it. */
bool image_is_plain(const spu_context* ctx) {
    for (const auto& span : ctx->resident_code) {
        if (span.image_id && span.lsa < kImageEnd && span.lsa + span.size > kImage &&
            (span.image_id != ctx->image_id || span.rel != 0))
            return false;
    }
    if (ctx->resident_ovl) return false;
    return !(ctx->wi_span_lo < ctx->wi_span_hi && ctx->wi_span_lo < kImageEnd && ctx->wi_span_hi > kImage);
}

/* The reason why the lifted code must run, or 0. The kernel is exact for the states that pass. */
const char* admission(spu_context* ctx, uint32_t index, uint32_t mode) {
    if (!kEntries[index].matches(ctx)) return "code identity";
    if (!ctx->policy_mode || ctx->ls != ctx->ls_store || ctx->status != SPU_STATUS_RUNNING) return "context policy";
    if (ctx->irq_frame || ctx->irq_saved) return "interrupt state";
    if (ctx->list_stall_mask || (ctx->int_enable && (ctx->event_status & ctx->event_mask))) return "pending event";
    if (ctx->interp_span_lo < ctx->interp_span_hi) return "interpreter span";
    if (g_spu_pm_svc_on) return "PM service";
    if (g_spu_ls_gate < 0) spu_ls_gate_init();
    if (g_spu_ls_gate != 0 || g_spu_smc_watch > 0 || g_spu_ls_watch_n > 0) return "local store probe";
    if (!spu_native_owned_run_ok(ctx, kEntries[index].address)) return "owned stop list";
    if (!image_is_plain(ctx)) return "resident overlay";
    if (mode == MOTORSTORM_PVS_SHADOW && !(ctx->drain_ret_pc & kLsMask)) return "no drain return address";
    return nullptr;
}

void put_back(spu_context* ctx, const MotorstormPvsState* state) {
    for (uint32_t page = 0; page != kPages; ++page)
        if (state->dirty & (1ull << page))
            memcpy(ctx->ls_store + page * kPage, state->saved + page * kPage, kPage);
}

/* The lifted function of the entry runs. `bail`: the kernel stopped before. */
void lifted(spu_context* ctx, uint32_t index, const char* reason, bool bail) {
    const uint64_t n = ++g_fallbacks;
    if (bail) ++g_bails;
    if (n <= 8 || n % 4096 == 0)
        fprintf(stderr, "[native-pvs] entry=%05X fallback=%llu bails=%llu reason=%s pc=%05X\n", kEntries[index].address,
                static_cast<unsigned long long>(n), static_cast<unsigned long long>(g_bails.load(std::memory_order_relaxed)),
                reason, bail ? t_bail_pc : 0u);
    kEntries[index].original(ctx);
}

void report() {
    const uint64_t calls = g_calls.load(std::memory_order_relaxed);
    if (calls == 1 || calls % 4096 == 0)
        fprintf(stderr, "[native-pvs] calls=%llu native=%llu compared=%llu fallbacks=%llu bails=%llu\n",
                static_cast<unsigned long long>(calls), static_cast<unsigned long long>(g_native.load(std::memory_order_relaxed)),
                static_cast<unsigned long long>(g_compared.load(std::memory_order_relaxed)),
                static_cast<unsigned long long>(g_fallbacks.load(std::memory_order_relaxed)),
                static_cast<unsigned long long>(g_bails.load(std::memory_order_relaxed)));
}

/* spu_context without the pointer `ls` and without the counter `steps`. */
bool same_state(const spu_context* a, const spu_context* b, size_t& offset) {
    const auto* pa = reinterpret_cast<const uint8_t*>(a);
    const auto* pb = reinterpret_cast<const uint8_t*>(b);
    const auto range = [&](size_t first, size_t last) {
        for (size_t k = first; k < last; ++k)
            if (pa[k] != pb[k]) {
                offset = k;
                return false;
            }
        return true;
    };
    const size_t ls = offsetof(spu_context, ls), st = offsetof(spu_context, steps);
    return range(0, ls) && range(ls + sizeof(void*), st) && range(st + sizeof(uint32_t), sizeof(spu_context));
}

void copy_in(Box* box, const spu_context* ctx) {
    memcpy(&box->context, ctx, sizeof(spu_context));
    box->context.ls = box->context.ls_store;
}

/* The kernel and the lifted code run on two copies of the context. Both go on to the return
   address of the drain with the lifted drain. A difference stops the program. */
void shadow(spu_context* ctx, uint32_t index, const MotorstormPvsState& state) {
    Storage& st = value;
    if (!st.boxes) st.boxes = new Box[2];
    Box* cand = &st.boxes[0];
    Box* ref = &st.boxes[1];
    uint8_t* const ls = ctx->ls;
    copy_in(cand, ctx);
    copy_in(ref, ctx);
    const uint32_t r0 = state.r0;
    MotorstormPvsState s = state;
    s.saved = st.saved;
    const bool left = motorstorm_pvs_run(&cand->context, &s, index) != 0;
    if (!left) {
        put_back(&cand->context, &s);
        kEntries[index].original(&cand->context);
    }
    spu_drain_call(&cand->context, r0);
    kEntries[index].original(&ref->context);
    spu_drain_call(&ref->context, r0);
    size_t offset = 0;
    const bool ok = left && (cand->context.pc & kLsMask) == r0 && (ref->context.pc & kLsMask) == r0 &&
                    !g_spu_trampoline_fn && same_state(&ref->context, &cand->context, offset) &&
                    !memcmp(ref->context.ls_store, cand->context.ls_store, kLsSize);
    if (!ok) {
        fprintf(stderr, "NATIVE_PVS_SHADOW_MISMATCH entry=%05X left=%d pc=%05X reference_pc=%05X byte=%zu\n",
                kEntries[index].address, left ? 1 : 0, cand->context.pc & kLsMask, ref->context.pc & kLsMask, offset);
        std::abort();
    }
    ++g_compared;
    memcpy(ctx, &ref->context, sizeof(spu_context));
    ctx->ls = ls;
    memcpy(ls, ref->context.ls_store, kLsSize);
}

void enter(spu_context* ctx, uint32_t index) {
    ++g_calls;
    const uint32_t mode = g_mode.load(std::memory_order_relaxed);
    if (index >= motorstorm_pvs_extent_count || mode == MOTORSTORM_PVS_REFERENCE) {
        kEntries[index < motorstorm_pvs_extent_count ? index : 0].original(ctx);
        return;
    }
    const char* reason = admission(ctx, index, mode);
    if (reason) {
        lifted(ctx, index, reason, false);
        return;
    }
    MotorstormPvsState state{};
    state.r0 = ctx->drain_ret_pc & kLsMask;
    state.owned = spu_native_owned_policy(ctx) ? 1u : 0u;
    state.host_depth0 = ctx->host_depth;
    if (mode == MOTORSTORM_PVS_NATIVE) {
        state.saved = value.saved;
        if (motorstorm_pvs_run(ctx, &state, index)) {
            ++g_native;
            t_exit_kind = state.exit_kind;
            t_bail_pc = 0;
            report();
            return;
        }
        t_exit_kind = 0;
        t_bail_pc = state.bail_pc;
        put_back(ctx, &state);
        lifted(ctx, index, "kernel stop", true);
        report();
        return;
    }
    shadow(ctx, index, state);
    report();
}

} // namespace

extern "C" {

void motorstorm_pvs_enter(spu_context* ctx, uint32_t index) noexcept {
    try {
        enter(ctx, index);
    } catch (const std::exception& error) {
        fprintf(stderr, "NATIVE_PVS_ERROR entry=%05X what=%s\n", kEntries[index < motorstorm_pvs_extent_count ? index : 0].address,
                error.what());
        std::abort();
    } catch (...) {
        fprintf(stderr, "NATIVE_PVS_ERROR entry=%05X\n", kEntries[index < motorstorm_pvs_extent_count ? index : 0].address);
        std::abort();
    }
}

void motorstorm_pvs_entry_00004030(spu_context* ctx) noexcept { motorstorm_pvs_enter(ctx, 0u); }

void motorstorm_pvs_set_mode(uint32_t mode) { g_mode.store(mode, std::memory_order_relaxed); }

uint32_t motorstorm_pvs_mode(void) { return g_mode.load(std::memory_order_relaxed); }

void motorstorm_pvs_counters(uint64_t out[5]) {
    out[0] = g_calls.load(std::memory_order_relaxed);
    out[1] = g_native.load(std::memory_order_relaxed);
    out[2] = g_compared.load(std::memory_order_relaxed);
    out[3] = g_fallbacks.load(std::memory_order_relaxed);
    out[4] = g_bails.load(std::memory_order_relaxed);
}

uint32_t motorstorm_pvs_last_exit(uint32_t* bail_pc) {
    if (bail_pc) *bail_pc = t_bail_pc;
    return t_exit_kind;
}

} // extern "C"
