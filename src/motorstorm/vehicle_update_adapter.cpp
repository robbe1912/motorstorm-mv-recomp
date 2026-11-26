/* Native entry of the vehicle update of SPU image 219 ("spuvehicle"): the code from LS 0x11FE0 up
   to its return address 0x20CE0.

   scripts/native_game_binding.py binds the entry to the lifted function
   jobmod_8de1770ee613_e1cd40_spu_func_00011FE0 of the generated unit. The binding gives the lifted
   function the name game_original_vehicle_update. A wrapper with the lifted name calls
   motorstorm_vehicle_update_entry. game_vehicle_update_code_matches compares the code in the local
   store with the bytes of the original ELF.

   The kernel (vehicle_update.c) runs the statements of the lifted function and of the functions
   that it calls. The entry puts the registers of the return into the context and sets pc. That is
   the state that SPU_RET of the lifted path leaves at 0x20CE0. The entry does not change
   g_spu_trampoline_fn, host_depth or drain_ret_pc. The call bracket of the lifted code then runs
   spu_drain_call(ctx, 0x20CE0), which returns on its normal path.

   The lifted code runs when the mode is off, when the admission refuses the context, or when the
   kernel stops before the return address. A stop puts back the local store pages that the kernel
   changed (copy on write).

   MS_NATIVE_VEHICLE_UPDATE selects the mode. Absent or "0": lifted code only. "1": kernel.
   "shadow": the kernel and the lifted code run on two copies of the context. A difference stops
   the program. The game state comes from the lifted code. */
#include "spu_context.h"
#include "vehicle_update.h"

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <new>

extern "C" {
void game_original_vehicle_update(spu_context* ctx);
int game_vehicle_update_code_matches(const spu_context* ctx);
extern int g_spu_pm_svc_on; /* the PM service switch of the SPU runtime (spu_native_owned.h) */
void motorstorm_vehicle_update_entry(spu_context* ctx) noexcept;
uint64_t motorstorm_vehicle_update_native_runs() noexcept;
}

namespace {

constexpr uint32_t kImage = 0x4000; /* image 219 fills 0x4000..0x21400 of the local store */
constexpr uint32_t kImageEnd = 0x21400;
constexpr uint32_t kPage = 0x1000;
constexpr uint32_t kPages = MOTORSTORM_VEHICLE_LS_SIZE / kPage;

enum class Mode { reference, shadow, native };

Mode mode() {
    static const Mode value = [] {
        const char* text = std::getenv("MS_NATIVE_VEHICLE_UPDATE");
        if (text && !std::strcmp(text, "1")) return Mode::native;
        return text && !std::strcmp(text, "shadow") ? Mode::shadow : Mode::reference;
    }();
    return value;
}

std::atomic<uint64_t> g_calls, g_native, g_compared, g_fallbacks;

struct alignas(64) Box {
    spu_context context;
};

/* Storage of one thread. A thread runs one SPU context at a time. The thread frees the storage
   when it ends. */
struct Storage {
    uint8_t* saved = static_cast<uint8_t*>(std::calloc(MOTORSTORM_VEHICLE_LS_SIZE, 1));
    Box* boxes = nullptr;
    unsigned depth = 0; /* 1 while a shadow compare runs on this thread */
    ~Storage() {
        std::free(saved);
        delete[] boxes;
    }
};

Storage& storage() {
    static thread_local Storage value;
    return value;
}

void report() {
    const uint64_t calls = g_calls.load(std::memory_order_relaxed);
    if (calls != 1 && calls % 256 != 0) return;
    std::fprintf(stderr, "[native-vehicle-update] completed=%llu compared=%llu fallbacks=%llu\n",
                 (unsigned long long)g_native.load(std::memory_order_relaxed),
                 (unsigned long long)g_compared.load(std::memory_order_relaxed),
                 (unsigned long long)g_fallbacks.load(std::memory_order_relaxed));
}

/* Only the plain image at its link base may be resident inside the image range: no span of
   another image, no shifted copy of the image, no interpreter span. They change the code. */
bool image_is_plain(const spu_context* ctx) {
    for (const auto& span : ctx->resident_code) {
        const uint64_t end = uint64_t(span.lsa) + span.size;
        const bool inside = span.size && span.lsa < kImageEnd && end > kImage;
        if (inside && (span.image_id != ctx->image_id || span.lsa != kImage || span.rel != 0)) return false;
    }
    return !(ctx->wi_span_lo > kImage && ctx->wi_span_lo < kImageEnd) &&
           !(ctx->wi_span_hi > kImage && ctx->wi_span_hi < kImageEnd);
}

/* The kernel runs only in the state of the kernel pairs: the call bracket of the job, image 219
   alone in the local store, no pending event, no PM service, no local store probe. The kernel
   loads and stores without the probe path of the lifted accessors. Returns the reason of a refusal. */
const char* admission(const spu_context* ctx) {
    if (!game_vehicle_update_code_matches(ctx)) return "code identity";
    if (!ctx->host_depth) return "not inside a call";
    if ((ctx->gpr[0]._u32[0] & 0x3ffffu) != MOTORSTORM_VEHICLE_RETURN) return "return address";
    if (!ctx->policy_mode || ctx->ls != ctx->ls_store || ctx->status != SPU_STATUS_RUNNING)
        return "context policy";
    if (ctx->list_stall_mask || !ctx->int_enable || (ctx->event_mask & ~2u) || ctx->irq_saved)
        return "interrupt state";
    if ((*(const volatile uint32_t*)&ctx->event_status & ctx->event_mask) ||
        *(const volatile int*)&ctx->resv_valid)
        return "pending event";
    if (g_spu_pm_svc_on) return "PM service";
    if (g_spu_ls_gate < 0) spu_ls_gate_init();
    if (g_spu_ls_gate != 0) return "local store probe";
    if (!image_is_plain(ctx)) return "resident overlay";
    return nullptr;
}

/* Runs the kernel on the local store of ctx. Returns true: the registers of the return are in
   ctx->gpr and ctx->pc is set. Returns false: the kernel stopped. The local store is then as it
   was at the entry. */
bool run_kernel(spu_context* ctx) {
    MotorstormVehicleState state;
    std::memset(&state, 0, sizeof state);
    state.ctx = ctx;
    state.ls = ctx->ls;
    state.saved = storage().saved;
    std::memcpy(state.gpr, ctx->gpr, sizeof state.gpr);
    if (!motorstorm_vehicle_update(&state)) {
        const uint8_t* saved = state.saved;
        for (uint32_t page = 0; page < kPages; ++page)
            if (state.dirty & (1ull << page))
                std::memcpy(ctx->ls + kPage * page, saved + kPage * page, kPage);
        return false;
    }
    std::memcpy(ctx->gpr, state.gpr, sizeof ctx->gpr);
    ctx->pc = state.gpr[0]._u32[0]; /* SPU_RET of the lifted path: pc is word 0 of r0 */
    return true;
}

/* Shadow mode: the kernel and the lifted code on two copies of the context. The context takes the
   state of the lifted copy. Returns false when the kernel stopped on its copy, or when the lifted
   code of the reference copy enters the function a second time. */
bool shadow(spu_context* ctx) {
    Storage& store = storage();
    if (store.depth) return false;
    if (!store.boxes) store.boxes = new Box[2];
    const struct Leave {
        Storage& store;
        ~Leave() { store.depth = 0; }
    } leave{store};
    store.depth = 1;
    for (unsigned i = 0; i < 2; ++i) {
        std::memcpy(&store.boxes[i].context, ctx, sizeof(spu_context));
        store.boxes[i].context.ls = store.boxes[i].context.ls_store;
    }
    spu_context* reference = &store.boxes[0].context;
    spu_context* candidate = &store.boxes[1].context;
    if (!run_kernel(candidate)) return false;
    ++reference->host_depth;
    game_original_vehicle_update(reference);
    spu_drain_call(reference, MOTORSTORM_VEHICLE_RETURN);
    --reference->host_depth;
    /* The drain of the call bracket, on the copy with the kernel result. It returns at once. It
       puts the copy in the same drain state as the reference copy. */
    spu_drain_call(candidate, MOTORSTORM_VEHICLE_RETURN);
    /* Two fields cannot be equal. ls: each copy has its own local store. steps: it counts the
       lifted dispatches of the drain, and the candidate makes fewer of them by design. */
    constexpr size_t kLs = __builtin_offsetof(spu_context, ls);
    constexpr size_t kSteps = __builtin_offsetof(spu_context, steps);
    const unsigned char* a = reinterpret_cast<const unsigned char*>(reference);
    const unsigned char* b = reinterpret_cast<const unsigned char*>(candidate);
    for (size_t i = 0; i < sizeof(spu_context); ++i)
        if ((i < kLs || i >= kLs + sizeof reference->ls) && (i < kSteps || i >= kSteps + sizeof reference->steps) &&
            a[i] != b[i]) {
            std::fprintf(stderr, "NATIVE_VEHICLE_UPDATE_SHADOW_MISMATCH byte=%zu reference=%02x native=%02x\n",
                         i, a[i], b[i]);
            std::abort();
        }
    /* The context takes the state of the lifted copy. The drain of the call bracket then returns
       at once. The kernel result alone is not enough for that: the drain would find the context
       at its entry state and would enter the function again. */
    uint8_t* const ls = ctx->ls;
    std::memcpy(ctx, reference, sizeof(spu_context));
    ctx->ls = ls;
    return true;
}

}  // namespace

extern "C" void motorstorm_vehicle_update_entry(spu_context* ctx) noexcept {
    try {
        if (mode() == Mode::reference) {
            game_original_vehicle_update(ctx);
            return;
        }
        ++g_calls;
        const char* reason = admission(ctx);
        if (!reason) {
            const bool done = mode() == Mode::native ? run_kernel(ctx) : shadow(ctx);
            if (done) ++g_native;
            if (mode() == Mode::shadow && done) ++g_compared;
            if (!done) reason = "kernel stopped";
        }
        if (reason) {
            ++g_fallbacks;
            std::fprintf(stderr, "[native-vehicle-update] ORIGINAL fallback=%llu reason=%s\n",
                         (unsigned long long)g_fallbacks.load(std::memory_order_relaxed), reason);
        }
        report();
        if (reason) game_original_vehicle_update(ctx);
    } catch (const std::exception& error) {
        std::fprintf(stderr, "NATIVE_VEHICLE_UPDATE_ERROR %s\n", error.what());
        std::abort();
    } catch (...) {
        std::fputs("NATIVE_VEHICLE_UPDATE_ERROR unknown exception\n", stderr);
        std::abort();
    }
}

/* The number of calls that the kernel completed. The checks read it. */
extern "C" uint64_t motorstorm_vehicle_update_native_runs() noexcept {
    return g_native.load(std::memory_order_relaxed);
}
