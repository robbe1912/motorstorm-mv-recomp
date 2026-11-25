#include "particle_surfaces.h"
#include "spu_interp.h"
#include "spu_jobmod_identity.h"
#include "spu_native_leaf.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {
// The interpreted prologue saved the caller's registers and resolved the
// slot selector. The leaf replaces the selected case body up to the epilogue.
constexpr uint32_t entry = 0xee84, epilogue = 0xefe8, last_branch = 0xf014, module_end = 0x174f0;
enum class Mode { reference, shadow, native };
Mode mode = Mode::reference;

struct Range { uint32_t begin, size; };
bool valid(Range range) {
    return range.begin >= module_end && range.begin <= 0x40000 &&
           range.size <= 0x40000 - range.begin;
}
bool overlaps(Range a, Range b) {
    return a.size && b.size && a.begin < b.begin + b.size && b.begin < a.begin + a.size;
}
void store(uint8_t* ls, uint32_t address, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) ls[address + i] = uint8_t(value >> (24 - i * 8));
}
MotorstormSurfaceVector load_vector(const uint8_t* ls, uint32_t address) {
    MotorstormSurfaceVector result;
    for (unsigned i = 0; i < 4; ++i) result.component[i] = stage_be32(ls + address + i * 4);
    return result;
}
bool recognized_image(const uint8_t* ls) {
    if (stage_be32(ls + 0x1330) != 0x4000 || stage_be32(ls + 0x4010) != 0x12e20)
        return false;
    // The original job updates three bookkeeping quadwords. Qualify every
    // other module word on every batch; no cached identity survives LS reuse.
    constexpr uint32_t ranges[][2] = {{0x4000, 0x174a0}, {0x174b0, 0x174d0}};
    uint64_t fingerprint = UINT64_C(1469598103934665603);
    for (const auto& range : ranges)
        for (uint32_t address = range[0]; address < range[1]; address += 8) {
            uint64_t word;
            std::memcpy(&word, ls + address, sizeof(word));
            fingerprint = (fingerprint ^ word) * UINT64_C(1099511628211);
        }
    return fingerprint == UINT64_C(0x7b8e3b18781120ef);
}
uint32_t case_address(uint32_t selector) {
    switch (selector) {
    case 2: return 0xeeb8;
    case 3: return 0xf718;
    case 5: return 0xf630;
    case 9: return 0xf37c;
    case 10: return 0xf018;
    default: return 0;
    }
}

struct Pending {
    const spu_context* owner = nullptr;
    MotorstormSurface surface;
    MotorstormSurfaceRecord records[MOTORSTORM_SURFACE_PARTICLES];
    uint32_t header, records_address, count;
};
thread_local Pending pending;
thread_local uint8_t shadow_ls[0x40000];

bool load_inputs(const spu_context* ctx, Pending& out) {
    const auto* ls = ctx->ls;
    const uint32_t header = spu_preferred_u32(&ctx->gpr[83]);
    const uint32_t data = spu_preferred_u32(&ctx->gpr[86]);
    const uint32_t count = stage_be32(ls + header + 8);
    if (spu_preferred_u32(&ctx->gpr[82]) != header + 704 ||
        spu_preferred_u32(&ctx->gpr[87]) != header + 992 || (header & 15) || (data & 15) ||
        !count || count > MOTORSTORM_SURFACE_PARTICLES ||
        !valid({header, 1784}) || !valid({data, 64}))
        return false;
    const uint32_t selector = stage_be32(ls + header + 768);
    const uint32_t target = case_address(selector);
    const uint32_t records = stage_be32(ls + header + 4);
    if (!target || spu_preferred_u32(&ctx->gpr[2]) != target || (records & 15) ||
        !valid({records, count * 128}))
        return false;
    const Range ranges[] = {{header, 1784}, {data, 64}, {records, count * 128}};
    for (unsigned i = 0; i < 3; ++i)
        for (unsigned j = 0; j < i; ++j)
            if (overlaps(ranges[i], ranges[j])) return false;

    out.header = header; out.records_address = records; out.count = count;
    MotorstormSurface& surface = out.surface;
    surface.slot.origin = load_vector(ls, header + 704);
    surface.slot.axis_x = load_vector(ls, header + 720);
    surface.slot.axis_y = load_vector(ls, header + 736);
    surface.slot.axis_z = load_vector(ls, header + 752);
    surface.slot.parameter[0] = load_vector(ls, header + 768);
    surface.slot.parameter[1] = load_vector(ls, header + 784);
    for (unsigned i = 0; i < 16; ++i) surface.data[i] = stage_be32(ls + data + i * 4);
    surface.step = stage_be32(ls + header + 1780);
    surface.wind = load_vector(ls, header + 992);
    for (uint32_t i = 0; i < count; ++i)
        for (unsigned w = 0; w < 32; ++w)
            out.records[i].word[w] = stage_be32(ls + records + i * 128 + w * 4);
    return motorstorm_particle_surfaces(&surface, out.records, count) != 0;
}

// The operation only writes motion, frame, size and enabled words.
constexpr unsigned written[] = {8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 25};

void publish(uint8_t* ls, const Pending& batch) {
    for (uint32_t i = 0; i < batch.count; ++i)
        for (const unsigned w : written)
            store(ls, batch.records_address + i * 128 + w * 4, batch.records[i].word[w]);
}

[[noreturn]] void fail(const char* message) {
    std::fprintf(stderr, "NATIVE_PARTICLE_SURFACES_ERROR %s\n", message);
    std::abort();
}
void execute(spu_context* ctx, const spu_native_leaf_plan* plan) {
    if (plan->cookie != &pending || pending.owner != ctx) fail("plan ownership");
    if (mode == Mode::shadow) {
        std::memcpy(shadow_ls, ctx->ls, sizeof(shadow_ls));
        publish(shadow_ls, pending);
        spu_interp_run_until(ctx, entry, epilogue);
        if (ctx->pc != epilogue || std::memcmp(shadow_ls, ctx->ls, sizeof(shadow_ls)))
            fail("original LS comparison");
    } else {
        publish(ctx->ls, pending);
        // The original epilogue restores the caller's saved registers/link.
        // No volatile result from this void operator is live at its caller.
        ctx->pc = epilogue;
        if (ctx->policy_mode)
            ctx->wi_prev_pc = last_branch;
    }
    pending.owner = nullptr;
    static std::atomic<uint64_t> completed{0}, records{0};
    const auto batches = completed.fetch_add(1, std::memory_order_relaxed) + 1;
    const auto tested = records.fetch_add(pending.count, std::memory_order_relaxed) + pending.count;
    if (batches == 1 || batches % 1024 == 0)
        std::fprintf(stderr, "[native-particle-surfaces] completed=%llu compared=%llu records=%llu\n",
            static_cast<unsigned long long>(batches),
            static_cast<unsigned long long>(mode == Mode::shadow ? batches : 0),
            static_cast<unsigned long long>(tested));
}

int prepare(const spu_context* ctx, uint64_t, spu_native_leaf_plan* plan) {
    pending.owner = nullptr;
    if (mode == Mode::reference || !ctx->policy_mode || ctx->ls != ctx->ls_store ||
        ctx->pc != entry || ctx->status != SPU_STATUS_RUNNING || ctx->list_stall_mask ||
        g_spu_interp_last_pc != 0xee80 || !ctx->int_enable || (ctx->event_mask & ~2u) ||
        (__atomic_load_n(&ctx->event_status, __ATOMIC_ACQUIRE) & ctx->event_mask) ||
        ctx->irq_saved || __atomic_load_n(&ctx->resv_valid, __ATOMIC_ACQUIRE) ||
        !recognized_image(ctx->ls) || !load_inputs(ctx, pending)) return 0;
    for (const auto& span : ctx->resident_code) if (span.size) {
        const uint64_t end = uint64_t(span.lsa) + span.size;
        if ((span.lsa > entry && span.lsa < epilogue) || (end > entry && end < epilogue))
            return 0;
    }
    if ((ctx->wi_span_lo > entry && ctx->wi_span_lo < epilogue) ||
        (ctx->wi_span_hi > entry && ctx->wi_span_hi < epilogue)) return 0;
    pending.owner = ctx;
    *plan = {0, epilogue, 0, execute, &pending};
    return 1;
}

struct Register {
    Register() {
        const char* value = std::getenv("MS_NATIVE_PARTICLE_SURFACES");
        if (!value || !std::strcmp(value, "0")) return;
        if (!std::strcmp(value, "shadow")) mode = Mode::shadow;
        else if (!std::strcmp(value, "1")) mode = Mode::native;
        else fail("invalid mode");
        const spu_native_leaf leaf{entry, epilogue, prepare};
        if (spu_native_leaf_register_unbudgeted(&leaf)) fail("registration");
        std::fprintf(stderr, "[native-particle-surfaces] mode=%s\n", value);
    }
} register_surfaces;
}
