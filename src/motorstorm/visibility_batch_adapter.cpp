#include "visibility_batch.h"
#include "spu_interp.h"
#include "spu_jobmod_identity.h"
#include "spu_native_leaf.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <stdexcept>

extern "C" {
// The binding script renames the lifted entry to the original and makes the
// lifted symbol a wrapper of this entry (scripts/native_game_binding.py).
void game_original_visibility_batch(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_00008BF0(spu_context*);
void motorstorm_visibility_batch(spu_context*);
// Generated in the ignored copied TU; holds the code and constant windows.
int game_visibility_batch_code_matches(const spu_context*);
}

namespace {
using Function = void (*)(spu_context*);
constexpr uint32_t entry = 0x88f8, epilogue = 0x8bf0;
constexpr uint32_t module_base = 0x4000, mutable_slot = 0x16580;
constexpr uint32_t list_stall_event = 2;
constexpr uint32_t workspace_begin = 0x16660, workspace_end = 0x27010;
constexpr uint32_t initialize_entry = 0x1635c, initialize_return = 0x162bc;
constexpr uint64_t initialize_instructions = 2 + 4 * ((workspace_end - workspace_begin) / 16);

enum class Mode { reference, shadow, native };
Mode batch_mode() {
    const char* mode = std::getenv("MS_NATIVE_VISIBILITY_BATCH");
    if (!mode || !std::strcmp(mode, "0")) return Mode::reference;
    if (!std::strcmp(mode, "1")) return Mode::native;
    if (!std::strcmp(mode, "shadow")) return Mode::shadow;
    std::fputs("[native-visibility-batch] MS_NATIVE_VISIBILITY_BATCH must be 0, shadow or 1\n", stderr);
    std::abort();
}

struct State {
    const Mode mode = batch_mode();
    std::atomic<unsigned long long> completed{0}, fallbacks{0}, compared{0};
};
State& batch_state() { static State value; return value; }

bool debug_us_module(const uint8_t* ls) {
    if (stage_be32(ls + 0x1330) != module_base || stage_be32(ls + 0x4010) != 0x12270)
        return false;
    uint64_t fingerprint = UINT64_C(1469598103934665603);
    for (uint32_t address = module_base; address < mutable_slot; ++address)
        fingerprint = (fingerprint ^ ls[address]) * UINT64_C(1099511628211);
    for (uint32_t address = mutable_slot + 16; address < 0x16640; ++address)
        fingerprint = (fingerprint ^ ls[address]) * UINT64_C(1099511628211);
    return fingerprint == UINT64_C(0x0064ac8170f4790f3);
}

bool uniform_register(const spu_context* ctx, unsigned reg, uint32_t value) {
    for (unsigned lane = 0; lane < 4; ++lane)
        if (ctx->gpr[reg]._u32[lane] != value) return false;
    return true;
}

bool occluder_image(const uint8_t* ls) {
    if (stage_be32(ls + 0x1330) != module_base || stage_be32(ls + 0x4010) != 0x12270)
        return false;
    // Qualify the whole module on every object. Folding complete words
    // avoids the byte-at-a-time dependency chain without caching identity.
    constexpr uint32_t ranges[][2] = {
        {module_base, mutable_slot}, {mutable_slot + 16, 0x16640}
    };
    uint64_t fingerprint = UINT64_C(1469598103934665603);
    for (const auto& range : ranges)
        for (uint32_t address = range[0]; address < range[1]; address += 8) {
            uint64_t word;
            std::memcpy(&word, ls + address, sizeof(word));
            fingerprint = (fingerprint ^ word) * UINT64_C(1099511628211);
        }
    return fingerprint == UINT64_C(0xbaf8847ab61eaf62);
}

bool register_matches_quad(const spu_context* ctx, unsigned reg, uint32_t address) {
    for (unsigned lane = 0; lane < 4; ++lane)
        if (ctx->gpr[reg]._u32[lane] != stage_be32(ctx->ls + address + lane * 4)) return false;
    return true;
}

// ---- the occluder leaf seam (interpreter path only) ----

void prepare_occluder_planes(spu_context* ctx, const spu_native_leaf_plan*) {
    const unsigned index = spu_preferred_u32(&ctx->gpr[89]);
    const unsigned temporary = spu_preferred_u32(&ctx->gpr[1]) + 32;
    if (!motorstorm_us_visibility_occluder(ctx->ls, index, temporary)) {
        std::fputs("[native-visibility-occluder] admitted layout changed\n", stderr);
        std::abort();
    }
    // These are the live loop-carried registers. The original next-input
    // path rebuilds temporaries; the original epilogue restores saved registers.
    for (unsigned lane = 0; lane < 4; ++lane) {
        ctx->gpr[86]._u32[lane] += 28;
        ctx->gpr[89]._u32[lane] += 1;
        ctx->gpr[90]._u32[lane] += 304;
    }
    ctx->pc = 0x5404;
    static std::atomic<unsigned> completed{0};
    const auto objects = completed.fetch_add(1, std::memory_order_relaxed) + 1;
    if (objects == 1 || objects % 4096 == 0)
        std::fprintf(stderr, "[native-visibility-occluder] completed=%u\n", objects);
}

int prepare_occluder(const spu_context* ctx, uint64_t, spu_native_leaf_plan* plan) {
    if (!ctx->policy_mode || ctx->ls != ctx->ls_store || g_spu_interp_last_pc != 0x50dc ||
        !ctx->int_enable || (ctx->event_mask & ~list_stall_event) || ctx->irq_saved ||
        __atomic_load_n(&ctx->resv_valid, __ATOMIC_ACQUIRE)) return 0;
    const unsigned index = spu_preferred_u32(&ctx->gpr[89]);
    const unsigned stack = spu_preferred_u32(&ctx->gpr[1]);
    if (index >= 144 || (stack & 15) || stack < 0x3b000 || stack > sizeof(ctx->ls_store) - 48 ||
        !uniform_register(ctx, 86, index * 28) || !uniform_register(ctx, 89, index) ||
        !uniform_register(ctx, 90, index * 304) || !uniform_register(ctx, 82, 0x16740) ||
        !uniform_register(ctx, 87, 4) || !uniform_register(ctx, 93, 8) ||
        !uniform_register(ctx, 100, 0) || !uniform_register(ctx, 101, 0x10203) ||
        !uniform_register(ctx, 102, 0) || !uniform_register(ctx, 103, 0) ||
        !uniform_register(ctx, 105, 0x10203) || !uniform_register(ctx, 108, 0x3f800001) ||
        !uniform_register(ctx, 109, 0x16740) || !occluder_image(ctx->ls) ||
        !register_matches_quad(ctx, 111, 0x163c0) ||
        !register_matches_quad(ctx, 112, 0x163d0) ||
        !register_matches_quad(ctx, 113, 0x163b0) ||
        !motorstorm_us_visibility_occluder_supported(ctx->ls, index, stack + 32)) return 0;
    *plan = {0, 0x5404, 0, prepare_occluder_planes, nullptr};
    return 1;
}

// ---- the workspace clear leaf seam (interpreter path only) ----

void initialize(spu_context* ctx, const spu_native_leaf_plan*) {
    // The selected job clears its own BSS on every dispatch. Keep the real
    // constructor, parameter DMA, output publication and completion after it.
    std::memset(ctx->ls + workspace_begin, 0, workspace_end - workspace_begin);
    for (unsigned lane = 0; lane < 4; ++lane) {
        ctx->gpr[3]._u32[lane] = workspace_end;
        ctx->gpr[5]._u32[lane] = 0;
        ctx->gpr[6]._u32[lane] = 0;
    }
    ctx->pc = initialize_return;
    static std::atomic<unsigned> completed{0};
    const auto jobs = completed.fetch_add(1, std::memory_order_relaxed) + 1;
    if (jobs == 1 || jobs % 256 == 0)
        std::fprintf(stderr, "[native-visibility-initialize] completed=%u\n", jobs);
}

int prepare_initialize(const spu_context* ctx, uint64_t, spu_native_leaf_plan* plan) {
    if (!ctx->policy_mode || g_spu_interp_last_pc != 0x162b8 || !ctx->int_enable ||
        (ctx->event_mask & ~list_stall_event) || ctx->irq_saved ||
        __atomic_load_n(&ctx->resv_valid, __ATOMIC_ACQUIRE) ||
        !uniform_register(ctx, 3, workspace_begin) || !uniform_register(ctx, 4, workspace_end) ||
        spu_preferred_u32(&ctx->gpr[126]) != 0 || !debug_us_module(ctx->ls))
        return 0;
    // Exact original instruction accounting keeps step budgets and stop PCs
    // usable. The shared runtime declines asynchronous events and LS watches.
    *plan = {initialize_instructions, initialize_return, 0x16370, initialize, nullptr};
    return 1;
}

// ---- the bound batch entry (lifted path and interpreter path) ----

bool known_caller(uint32_t continuation) {
    switch (continuation) {
    case 0x9860: case 0xaf34: case 0xafd8: case 0xb068: case 0xb0e0: return true;
    default: return false;
    }
}

bool pending(const spu_context* ctx) {
    const volatile std::uint32_t& events = ctx->event_status;
    return ctx->int_enable && (events & ctx->event_mask);
}

const char* admission(const spu_context* ctx, unsigned& count) {
    if (!ctx || ctx->ls != ctx->ls_store) return "local-store ownership";
    if (ctx->pc != entry) return "entry state";
    if (!ctx->policy_mode) return "owned policy mode";
    if (ctx->irq_saved) return "active interrupt frame";
    if (ctx->status != SPU_STATUS_RUNNING) return "run state";
    if (ctx->list_stall_mask || pending(ctx)) return "pending DMA/event";
    if (g_spu_ls_watch_n > 0) return "active local-store watch";
    const unsigned stack = spu_preferred_u32(&ctx->gpr[1]);
    // This worker raises the list-stall event through MFC commands. This
    // slice issues no commands and admission excludes the PUT threshold.
    if ((stack & 15) || stack < 0x3b000 || stack > sizeof(ctx->ls_store) - 336 ||
        !known_caller(stage_be32(ctx->ls + stack + 320)))
        return "stack frame";
    count = spu_preferred_u32(&ctx->gpr[83]);
    if (!game_visibility_batch_code_matches(ctx)) return "code/data identity";
    if (!motorstorm_us_visibility_nonflushing(ctx->ls, count)) return "flushing batch";
    return nullptr;
}

void original(spu_context* ctx, const char* reason) {
    const auto count = ++batch_state().fallbacks;
    if (count <= 8 || count % 4096 == 0)
        std::fprintf(stderr, "[native-visibility-batch] ORIGINAL fallback=%llu reason=%s\n", count, reason);
    game_original_visibility_batch(ctx);
}

[[noreturn]] void fail(const char* message) {
    std::fprintf(stderr, "NATIVE_VISIBILITY_BATCH_ERROR %s\n", message);
    std::abort();
}

// Run one copy through the lifted code until the caller resumes. The lifted
// blocks return here through g_spu_trampoline_fn (spu_drain_call does the
// same on its loop). The batch body is 0x88F8..0x96xx with helper calls.
void resume(spu_context* copy, uint32_t return_pc, Function first) {
    const Function saved = g_spu_trampoline_fn;
    struct Restore { Function value; ~Restore() { g_spu_trampoline_fn = value; } } restore{saved};
    Function next = first;
    for (unsigned step = 0; step < (1u << 22); ++step) {
        g_spu_trampoline_fn = nullptr;
        next(copy);
        next = g_spu_trampoline_fn;
        const uint32_t pc = copy->pc & SPU_LS_MASK;
        if (pc == return_pc) {
            // SPU_RET sets spu_indirect_branch only at host depth 0. At a deeper
            // host level the drain loop sees a clear trampoline at the return address.
            if (next == spu_indirect_branch || !next) return;
            fail("Visibility batch reference returned without a dispatch");
        }
        if (pc < 0x4000u || pc >= 0x16640u) {
            std::fprintf(stderr, "VISIBILITY_BATCH_ESCAPE pc=0x%08x step=%u\n", pc, step);
            fail("Visibility batch reference left the module");
        }
        if (!next) fail("Visibility batch reference stopped without a dispatch");
    }
    fail("Visibility batch reference exceeded its step limit");
}

bool snapshot(const spu_context* ctx, spu_context* reference, spu_context* candidate) {
    std::memcpy(reference, ctx, sizeof(*ctx));
    if (reference->ls != ctx->ls_store || reference->status != SPU_STATUS_RUNNING || reference->irq_saved ||
        reference->list_stall_mask || pending(reference)) return false;
    // Start both executions from one snapshot. Materialize it: otherwise
    // memcpy forwarding can replace the second copy with another read.
    std::atomic_signal_fence(std::memory_order_seq_cst);
    std::memcpy(candidate, reference, sizeof(*ctx));
    reference->ls = reference->ls_store;
    candidate->ls = candidate->ls_store;
    return true;
}

void execute(spu_context* ctx, unsigned count) {
    if (!motorstorm_us_visibility_classify(ctx->ls, count, ctx->mfc_eah, nullptr, nullptr)) {
        std::fputs("[native-visibility-batch] admitted layout changed\n", stderr);
        std::abort();
    }
    // The caller owns the epilogue: it restores the saved registers and
    // returns to the caller of 0x8790. Its inputs are r83 and r1, unchanged.
    ctx->pc = epilogue;
    g_spu_trampoline_fn = jobmod_056ac0eea1a6_e12270_spu_func_00008BF0;
}

bool compare(const spu_context* ctx, unsigned count) {
    auto reference = std::make_unique<spu_context>();
    auto candidate = std::make_unique<spu_context>();
    if (!snapshot(ctx, reference.get(), candidate.get())) return false;
    const auto return_pc = ctx->gpr[0]._u32[0] & SPU_LS_MASK;
    reference->pc = entry;
    resume(reference.get(), return_pc, game_original_visibility_batch);
    execute(candidate.get(), count);
    resume(candidate.get(), return_pc, jobmod_056ac0eea1a6_e12270_spu_func_00008BF0);
    candidate->ls = reference->ls;
    // r2..r79 are volatile in the SPU ABI: the caller of 0x8790 does not read them
    // after the call. The helpers of the batch write r27 for that reason.
    // r80..r127, r0 and r1 are equal, as is the whole local store, with one
    // known exception: block 0x8A60 of the lifted code holds 4 quadwords of
    // work data at r1+0x20..r1+0x5F (the frame of the caller of 0x8790).
    // The kernel does not write them. No lifted code reads that frame while
    // the batch runs, and the caller's own frame is above its stack pointer.
    const std::size_t scratch = ctx->gpr[1]._u32[0] + 0x20u;
    const std::size_t scratch_end = scratch + 0x40u;
    auto same = [scratch, scratch_end](const spu_context* left, const spu_context* right) {
        if (left->pc != right->pc) return false;
        if (std::memcmp(left->gpr, right->gpr, 2 * sizeof(left->gpr[0]))) return false;
        if (std::memcmp(&left->gpr[80], &right->gpr[80], (128 - 80) * sizeof(left->gpr[0]))) return false;
        for (std::size_t i = 0; i < sizeof(left->ls_store); ++i)
            if (!(i >= scratch && i < scratch_end) && left->ls_store[i] != right->ls_store[i]) return false;
        return true;
    };
    if (!same(reference.get(), candidate.get())) {
        for (unsigned reg = 0; reg < 128; ++reg) {
            if (reg >= 2 && reg <= 79) continue;
            if (std::memcmp(&reference->gpr[reg], &candidate->gpr[reg], sizeof(reference->gpr[0]))) {
                std::fprintf(stderr, "NATIVE_VISIBILITY_BATCH_SHADOW_MISMATCH register=%u\n", reg);
                return false;
            }
        }
        const auto* a = candidate->ls_store;
        const auto* b = reference->ls_store;
        for (std::size_t i = 0; i < sizeof(reference->ls_store); ++i)
            if (!(i >= scratch && i < scratch_end) && a[i] != b[i]) {
                std::fprintf(stderr, "NATIVE_VISIBILITY_BATCH_SHADOW_MISMATCH address=0x%zx native=%02x reference=%02x stack=0x%08x\n",
                             i, a[i], b[i], ctx->gpr[1]._u32[0]);
                return false;
            }
        std::fputs("NATIVE_VISIBILITY_BATCH_SHADOW_MISMATCH pc\n", stderr);
        return false;
    }
    ++batch_state().compared;
    return true;
}

struct Register {
    Register() {
        // The batch runs through the bound lifted symbol. The two leaf seams
        // below serve the interpreter path; they are off in reference mode.
        if (batch_state().mode == Mode::reference) return;
        const char* init_mode = std::getenv("MS_NATIVE_VISIBILITY_INITIALIZE");
        if (!init_mode || std::strcmp(init_mode, "0")) {
            const spu_native_leaf initializer{initialize_entry, 0x16374, prepare_initialize};
            if (spu_native_leaf_register(&initializer)) std::abort();
            std::fputs("[native-visibility-initialize] registered\n", stderr);
        }
        const char* occluder_mode = std::getenv("MS_NATIVE_VISIBILITY_OCCLUDERS");
        if (!occluder_mode || std::strcmp(occluder_mode, "0")) {
            const spu_native_leaf occluder{0x50e0, 0x5404, prepare_occluder};
            if (spu_native_leaf_register_unbudgeted(&occluder)) std::abort();
            std::fputs("[native-visibility-occluder] registered\n", stderr);
        }
    }
} register_batch;
} // namespace

extern "C" void motorstorm_visibility_batch_counts(unsigned long long* completed,
                                                    unsigned long long* compared,
                                                    unsigned long long* fallbacks) {
    *completed = batch_state().completed.load();
    *compared = batch_state().compared.load();
    *fallbacks = batch_state().fallbacks.load();
}

extern "C" void motorstorm_visibility_batch(spu_context* ctx) {
    auto& config = batch_state();
    if (config.mode == Mode::reference) { game_original_visibility_batch(ctx); return; }
    unsigned count = 0;
    if (const char* reason = admission(ctx, count)) { original(ctx, reason); return; }
    if (config.mode == Mode::shadow && !compare(ctx, count)) {
        std::fputs("NATIVE_VISIBILITY_BATCH_SHADOW_MISMATCH\n", stderr);
        std::abort();
    }
    if (config.mode == Mode::shadow) {
        // The kernel ran on the copy. The live context keeps its incoming
        // state and runs the original, as the comparison assumed.
        game_original_visibility_batch(ctx);
        return;
    }
    // One native execution for one call of the original code.
    execute(ctx, count);
    const auto completed = ++config.completed;
    if (completed == 1 || completed % 1024 == 0)
        std::fprintf(stderr, "[native-visibility-batch] completed=%llu compared=%llu fallbacks=%llu\n",
                     completed, config.compared.load(), config.fallbacks.load());
}
