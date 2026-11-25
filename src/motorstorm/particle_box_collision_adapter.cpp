#include "particle_box_collision.h"
#include "spu_interp.h"
#include "spu_jobmod_identity.h"
#include "spu_native_leaf.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {
constexpr uint32_t entry = 0xa87c, epilogue = 0xabec, module_end = 0x174f0;
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
MotorstormCollisionVector load_vector(const uint8_t* ls, uint32_t address) {
    MotorstormCollisionVector result;
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

struct Pending {
    const spu_context* owner = nullptr;
    MotorstormCollisionParticle particles[MOTORSTORM_COLLISION_PARTICLES];
    MotorstormCollisionBox box;
    MotorstormCollisionResult result;
    uint32_t header, shape, records, count, stack, event_header, events, used, capacity;
    bool remove_hits;
};
thread_local Pending pending;
thread_local uint8_t shadow_ls[0x40000];

bool load_inputs(const spu_context* ctx, Pending& out) {
    const auto* ls = ctx->ls;
    const uint32_t header = spu_preferred_u32(&ctx->gpr[81]);
    const uint32_t shape = spu_preferred_u32(&ctx->gpr[82]);
    const uint32_t stack = spu_preferred_u32(&ctx->gpr[1]);
    const uint32_t count = spu_preferred_u32(&ctx->gpr[86]);
    if (!count || count > MOTORSTORM_COLLISION_PARTICLES || (header & 15) ||
        (shape & 15) || (stack & 15) || stack < 0x3b000 ||
        !valid({header, 1784}) || !valid({shape, 128}) || !valid({stack, 432}) ||
        spu_preferred_u32(&ctx->gpr[85]) != 0 ||
        spu_preferred_u32(&ctx->gpr[80]) != (count - 1) * 128 ||
        stage_be32(ls + header + 8) != count ||
        stage_be32(ls + header + 12) < count ||
        stage_be32(ls + stack + 416) != 0x12188) return false;
    const uint32_t records = stage_be32(ls + header + 4), event_header = header + 684;
    const uint32_t used = stage_be32(ls + event_header);
    const uint32_t capacity = stage_be32(ls + event_header + 4);
    const uint32_t events = stage_be32(ls + event_header + 8);
    if ((records & 15) || (events & 15) || used > capacity || capacity > 0x4000 ||
        !valid({records, count * 128}) || (capacity && !valid({events, capacity * 16})))
        return false;
    const Range ranges[] = {{header, 1784}, {shape, 128}, {stack, 432},
                            {records, count * 128}, {events, capacity * 16}};
    for (unsigned i = 0; i < 5; ++i)
        for (unsigned j = 0; j < i; ++j)
            if (overlaps(ranges[i], ranges[j])) return false;

    out.header = header; out.shape = shape; out.stack = stack; out.count = count;
    out.records = records; out.event_header = event_header; out.events = events;
    out.used = used; out.capacity = capacity; out.remove_hits = ls[shape + 116] != 0;
    for (unsigned i = 0; i < 4; ++i)
        for (unsigned lane = 0; lane < 4; ++lane)
            out.box.columns[i].component[lane] = ctx->gpr[91 - i]._u32[lane];
    out.box.half_extent = load_vector(ls, shape + 80);
    out.box.motion = load_vector(ls, shape + 96);
    out.box.step = stage_be32(ls + header + 1780);
    out.box.contact_metadata = stage_be32(ls + shape + 112);
    for (uint32_t i = 0; i < count; ++i) {
        const uint32_t record = records + i * 128;
        out.particles[i] = {load_vector(ls, record), load_vector(ls, record + 48),
                            stage_be32(ls + record + 100)};
    }
    return motorstorm_particle_box_contacts(out.particles, count, &out.box, &out.result) != 0;
}

void publish(uint8_t* ls, const Pending& batch) {
    uint32_t used = batch.used, remaining = batch.count;
    // The original visits records backwards. A full contact list suppresses
    // only the append, not optional removal or its temporary payload write.
    for (uint32_t i = batch.count; i-- > 0;) {
        if (!batch.result.hit[i]) continue;
        for (unsigned lane = 0; lane < 4; ++lane)
            store(ls, batch.stack + 32 + lane * 4, batch.result.contact[i].component[lane]);
        if (used < batch.capacity) {
            std::memcpy(ls + batch.events + used * 16, ls + batch.stack + 32, 16);
            store(ls, batch.event_header, ++used);
        }
        if (batch.remove_hits) {
            --remaining;
            store(ls, batch.header + 8, remaining);
            std::memmove(ls + batch.records + i * 128,
                         ls + batch.records + remaining * 128, 128);
        }
    }
}

[[noreturn]] void fail(const char* message) {
    std::fprintf(stderr, "NATIVE_PARTICLE_COLLISION_ERROR %s\n", message);
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
            ctx->wi_prev_pc = pending.remove_hits && pending.result.hit[0] ? 0xabe8 : 0xa878;
    }
    pending.owner = nullptr;
    static std::atomic<uint64_t> completed{0}, particles{0}, contacts{0};
    const auto batches = completed.fetch_add(1, std::memory_order_relaxed) + 1;
    const auto tested = particles.fetch_add(pending.count, std::memory_order_relaxed) + pending.count;
    const auto hits = contacts.fetch_add(pending.result.contacts, std::memory_order_relaxed) + pending.result.contacts;
    if (batches == 1 || batches % 1024 == 0)
        std::fprintf(stderr, "[native-particle-collision] completed=%llu compared=%llu particles=%llu contacts=%llu\n",
            static_cast<unsigned long long>(batches),
            static_cast<unsigned long long>(mode == Mode::shadow ? batches : 0),
            static_cast<unsigned long long>(tested), static_cast<unsigned long long>(hits));
}

int prepare(const spu_context* ctx, uint64_t, spu_native_leaf_plan* plan) {
    pending.owner = nullptr;
    if (mode == Mode::reference || !ctx->policy_mode || ctx->ls != ctx->ls_store ||
        ctx->pc != entry || ctx->status != SPU_STATUS_RUNNING || ctx->list_stall_mask ||
        g_spu_interp_last_pc != 0xa868 || !ctx->int_enable || (ctx->event_mask & ~2u) ||
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
        const char* value = std::getenv("MS_NATIVE_PARTICLE_COLLISIONS");
        if (!value || !std::strcmp(value, "0")) return;
        if (!std::strcmp(value, "shadow")) mode = Mode::shadow;
        else if (!std::strcmp(value, "1")) mode = Mode::native;
        else fail("invalid mode");
        const spu_native_leaf leaf{entry, epilogue, prepare};
        if (spu_native_leaf_register_unbudgeted(&leaf)) fail("registration");
        std::fprintf(stderr, "[native-particle-collision] mode=%s\n", value);
    }
} register_collision;
}
