#include "particle_random.h"
#include "spu_interp.h"
#include "spu_native_leaf.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {
/* Instructions 0x170D0 to 0x17258: the random generator of job image 213. */
constexpr uint32_t begin = 0x170d0, end = 0x1725c;
constexpr uint32_t seed_address = 0x174a0, state_address = 0x17dd0;
/* FNV-1a over the 400 bytes of the extent. The code holds absolute local store
   addresses, so the value also proves the load address of the module. */
constexpr uint64_t code_fingerprint = UINT64_C(0x06f51c396099f22a);
enum class Mode { reference, shadow, native };
Mode mode = Mode::reference;

struct Pending {
    const spu_context* owner = nullptr;
    MotorstormRandomCall call;
    uint32_t entry = 0, resume = 0;
};
thread_local Pending pending;
thread_local uint8_t shadow_ls[0x40000];

uint32_t be32(const uint8_t* p) {
    return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3];
}
bool supported(uint32_t pc) {
    return pc == MOTORSTORM_RANDOM_ENTRY_RUN || pc == MOTORSTORM_RANDOM_ENTRY_INIT;
}
bool recognized_image(const uint8_t* ls) {
    uint64_t fingerprint = UINT64_C(1469598103934665603);
    for (uint32_t address = begin; address < end; address += 8) {
        uint64_t word;
        std::memcpy(&word, ls + address, sizeof word);
        fingerprint = (fingerprint ^ word) * UINT64_C(1099511628211);
    }
    return fingerprint == code_fingerprint;
}
/* The instruction before the entry is the call. r0 holds its return address. */
bool called(const spu_context* ctx, uint32_t entry) {
    const uint32_t call = g_spu_interp_last_pc;
    if ((call & 3) || call < end || call >= 0x40000 || spu_preferred_u32(&ctx->gpr[0]) != call + 4) return false;
    const uint32_t word = be32(ctx->ls + call);
    if ((word >> 25) != 0x19 && (word >> 25) != 0x1a) return false; /* brsl, brasl */
    const uint32_t target = (call + (uint32_t(int32_t(word << 7) >> 14) << 2)) & 0x3fffcu;
    return target == entry;
}

void load_call(const spu_context* ctx, MotorstormRandomCall& call) {
    for (unsigned r = 0; r < MOTORSTORM_RANDOM_REGISTERS; ++r)
        for (unsigned lane = 0; lane < MOTORSTORM_RANDOM_LANES; ++lane)
            call.registers[r].word[lane] = ctx->gpr[r + 2]._u32[lane];
    for (unsigned lane = 0; lane < MOTORSTORM_RANDOM_LANES; ++lane)
        call.seed.word[lane] = be32(ctx->ls + seed_address + 4 * lane);
    std::memcpy(call.state, ctx->ls + state_address, sizeof call.state);
}

/* Stores the bytes that the original instructions write: 0x17DD0 to 0x17E70 and 0x174A0. */
void publish_bytes(uint8_t* ls, const MotorstormRandomCall& call) {
    std::memcpy(ls + state_address, call.state, sizeof call.state);
    for (unsigned lane = 0; lane < MOTORSTORM_RANDOM_LANES; ++lane) {
        uint8_t* p = ls + seed_address + 4 * lane;
        for (unsigned i = 0; i < 4; ++i) p[i] = uint8_t(call.seed.word[lane] >> (24 - 8 * i));
    }
}

[[noreturn]] void fail(const char* message) {
    std::fprintf(stderr, "NATIVE_PARTICLE_RANDOM_ERROR %s\n", message);
    std::abort();
}

void execute(spu_context* ctx, const spu_native_leaf_plan* plan) {
    if (plan->cookie != &pending || pending.owner != ctx) fail("plan ownership");
    const uint32_t entry = pending.entry, resume = pending.resume;
    if (mode == Mode::shadow) {
        std::memcpy(shadow_ls, ctx->ls, sizeof shadow_ls);
        publish_bytes(shadow_ls, pending.call);
        /* The original code returns with `bi r0` to the instruction after the call. */
        spu_interp_run_until(ctx, entry, resume);
        if (ctx->pc != resume || std::memcmp(shadow_ls, ctx->ls, sizeof shadow_ls))
            fail("original LS comparison");
    } else {
        publish_bytes(ctx->ls, pending.call);
        /* r3 is the result. r2 and r4 to r11 are the values that the original code leaves. */
        for (unsigned r = 0; r < MOTORSTORM_RANDOM_REGISTERS; ++r)
            for (unsigned lane = 0; lane < MOTORSTORM_RANDOM_LANES; ++lane)
                ctx->gpr[r + 2]._u32[lane] = pending.call.registers[r].word[lane];
        ctx->pc = resume;
    }
    pending.owner = nullptr;
    static std::atomic<uint64_t> completed{0};
    const auto calls = completed.fetch_add(1, std::memory_order_relaxed) + 1;
    if (calls == 1 || calls % 4096 == 0)
        std::fprintf(stderr, "[native-particle-random] calls=%llu compared=%llu\n",
            static_cast<unsigned long long>(calls),
            static_cast<unsigned long long>(mode == Mode::shadow ? calls : 0));
}

int prepare(const spu_context* ctx, uint64_t, spu_native_leaf_plan* plan) {
    pending.owner = nullptr;
    if (mode == Mode::reference || !supported(ctx->pc) || !ctx->policy_mode || ctx->ls != ctx->ls_store ||
        ctx->status != SPU_STATUS_RUNNING || ctx->list_stall_mask || !ctx->int_enable ||
        (ctx->event_mask & ~2u) || (__atomic_load_n(&ctx->event_status, __ATOMIC_ACQUIRE) & ctx->event_mask) ||
        ctx->irq_saved || __atomic_load_n(&ctx->resv_valid, __ATOMIC_ACQUIRE) || !called(ctx, ctx->pc) ||
        !recognized_image(ctx->ls)) return 0;
    for (const auto& span : ctx->resident_code) if (span.size) {
        const uint64_t last = uint64_t(span.lsa) + span.size;
        if ((span.lsa > begin && span.lsa < end) || (last > begin && last < end)) return 0;
    }
    if ((ctx->wi_span_lo > begin && ctx->wi_span_lo < end) || (ctx->wi_span_hi > begin && ctx->wi_span_hi < end))
        return 0;
    load_call(ctx, pending.call);
    if (!motorstorm_particle_random(ctx->pc, &pending.call)) return 0;
    pending.entry = ctx->pc;
    pending.resume = spu_preferred_u32(&ctx->gpr[0]);
    pending.owner = ctx;
    *plan = {0, pending.resume, 0, execute, &pending};
    return 1;
}

struct Register {
    Register() {
        const char* value = std::getenv("MS_NATIVE_PARTICLE_RANDOM");
        if (!value || !std::strcmp(value, "0")) return;
        if (!std::strcmp(value, "shadow")) mode = Mode::shadow;
        else if (!std::strcmp(value, "1")) mode = Mode::native;
        else fail("invalid mode");
        const spu_native_leaf leaf{begin, end, prepare};
        if (spu_native_leaf_register_unbudgeted(&leaf)) fail("registration");
        std::fprintf(stderr, "[native-particle-random] mode=%s\n", value);
    }
} register_random;
}
