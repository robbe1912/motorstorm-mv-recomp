#include "visibility_batch.h"
#include "spu_interp.h"
#include "spu_jobmod_identity.h"
#include "spu_native_leaf.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {
constexpr uint32_t post_dma_branch = 0x88f4, entry = 0x88f8, epilogue = 0x8bf0;
constexpr uint32_t module_base = 0x4000, module_limit = 0x16640, mutable_slot = 0x16580;
constexpr uint32_t list_stall_event = 2;
constexpr uint32_t workspace_begin = 0x16660, workspace_end = 0x27010;
constexpr uint32_t initialize_entry = 0x1635c, initialize_return = 0x162bc;
constexpr uint64_t initialize_instructions = 2 + 4 * ((workspace_end - workspace_begin) / 16);

bool debug_us_module(const uint8_t* ls) {
    if (stage_be32(ls + 0x1330) != module_base || stage_be32(ls + 0x4010) != 0x12270)
        return false;
    uint64_t fingerprint = UINT64_C(1469598103934665603);
    for (uint32_t address = module_base; address < mutable_slot; ++address)
        fingerprint = (fingerprint ^ ls[address]) * UINT64_C(1099511628211);
    for (uint32_t address = mutable_slot + 16; address < module_limit; ++address)
        fingerprint = (fingerprint ^ ls[address]) * UINT64_C(1099511628211);
    return fingerprint == UINT64_C(0x0064ac8170f4790f3);
}

bool known_caller(uint32_t continuation) {
    switch (continuation) {
    case 0x9860: case 0xaf34: case 0xafd8: case 0xb068: case 0xb0e0: return true;
    default: return false;
    }
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
        {module_base, mutable_slot}, {mutable_slot + 16, module_limit}
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

void classify(spu_context* ctx, const spu_native_leaf_plan*) {
    if (!motorstorm_us_visibility_classify(ctx->ls, spu_preferred_u32(&ctx->gpr[83]),
                                           ctx->mfc_eah, nullptr, nullptr)) {
        std::fputs("[native-visibility-batch] admitted layout changed\n", stderr);
        std::abort();
    }
    ctx->pc = epilogue;
    static std::atomic<unsigned> completed{0};
    const auto batches = completed.fetch_add(1, std::memory_order_relaxed) + 1;
    if (batches == 1 || batches % 256 == 0)
        std::fprintf(stderr, "[native-visibility-batch] completed=%u\n", batches);
}

int prepare(const spu_context* ctx, uint64_t, spu_native_leaf_plan* plan) {
    if (!ctx->policy_mode || g_spu_interp_last_pc != post_dma_branch || !ctx->int_enable ||
        (ctx->event_mask & ~list_stall_event) || ctx->irq_saved ||
        __atomic_load_n(&ctx->resv_valid, __ATOMIC_ACQUIRE))
        return 0;
    // This worker raises the list-stall event through MFC commands. This
    // slice issues no commands and admission excludes the PUT threshold.
    const unsigned stack = spu_preferred_u32(&ctx->gpr[1]);
    if ((stack & 15) || stack < 0x3b000 || stack > sizeof(ctx->ls_store) - 336 ||
        !known_caller(stage_be32(ctx->ls + stack + 320)) || !debug_us_module(ctx->ls) ||
        !motorstorm_us_visibility_nonflushing(ctx->ls, spu_preferred_u32(&ctx->gpr[83])))
        return 0;
    *plan = {0, epilogue, 0, classify, nullptr};
    return 1;
}

struct Register {
    Register() {
        const char* mode = std::getenv("MS_NATIVE_VISIBILITY_BATCH");
        if (!mode || std::strcmp(mode, "1")) return;
        const spu_native_leaf descriptor{entry, epilogue, prepare};
        if (spu_native_leaf_register_unbudgeted(&descriptor)) std::abort();
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
        std::fputs("[native-visibility-batch] registered\n", stderr);
    }
} register_batch;
}
