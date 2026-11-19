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
        std::fputs("[native-visibility-batch] registered\n", stderr);
    }
} register_batch;
}
