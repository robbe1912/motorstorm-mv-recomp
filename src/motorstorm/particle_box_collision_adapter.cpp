// Bound entry of the particle box collision batch of SPU image 213 (jobmod_556b30b5e654_e12e20).
// The lifted function 0xA700 saves its frame, prepares the box registers and transfers to the
// loop function 0xA87C with r85 = 0 (the record index). scripts/native_game_binding.py renames
// the lifted loop function to game_original_particle_collision_loop and defines its symbol as
// a wrapper of the entry here. The entry runs the whole batch at the first entry (r85 == 0)
// and calls the lifted epilogue 0xABEC, which restores the frame and returns to r0.
// A loop re-entry (r85 != 0), mode 0 and every unsupported state call the renamed original.
#include "particle_bind.h"
#include "particle_box_collision.h"
#include "spu_jobmod_identity.h"

extern "C" {
void game_original_particle_collision_loop(spu_context*);         // lifted 0xA87C
void jobmod_556b30b5e654_e12e20_spu_func_0000ABEC(spu_context*);  // lifted epilogue
int game_particle_collision_code_matches(const spu_context*);
void motorstorm_particle_collision_batch(spu_context* ctx);
void motorstorm_particle_collision_counts(MotorstormParticleBindCounts* out);
}

namespace {
using namespace motorstorm_particle_bind;
constexpr uint32_t epilogue = 0xabec, module_end = 0x174f0;
constexpr const char* OPTION = "MS_NATIVE_PARTICLE_COLLISIONS";
std::atomic<unsigned long long> calls{0}, compared{0}, fallbacks{0}, particles{0}, contacts{0};

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

struct Batch {
    MotorstormCollisionParticle particles[MOTORSTORM_COLLISION_PARTICLES];
    MotorstormCollisionBox box;
    MotorstormCollisionResult result;
    uint32_t header, shape, records, count, stack, event_header, events, used, capacity;
    bool remove_hits;
};
thread_local Batch pending;

// Reads one batch. Returns null, or the reason why the lifted loop must run.
const char* load_inputs(const spu_context* ctx, Batch& out) {
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
        stage_be32(ls + stack + 416) != 0x12188) return "frame or count";
    const uint32_t records = stage_be32(ls + header + 4), event_header = header + 684;
    const uint32_t used = stage_be32(ls + event_header);
    const uint32_t capacity = stage_be32(ls + event_header + 4);
    const uint32_t events = stage_be32(ls + event_header + 8);
    if ((records & 15) || (events & 15) || used > capacity || capacity > 0x4000 ||
        !valid({records, count * 128}) || (capacity && !valid({events, capacity * 16})))
        return "record list or event list";
    const Range ranges[] = {{header, 1784}, {shape, 128}, {stack, 432},
                            {records, count * 128}, {events, capacity * 16}};
    for (unsigned i = 0; i < 5; ++i)
        for (unsigned j = 0; j < i; ++j)
            if (overlaps(ranges[i], ranges[j])) return "overlapping ranges";

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
    if (motorstorm_particle_box_contacts(out.particles, count, &out.box, &out.result)) return nullptr;
    return "kernel declined";
}

void publish(uint8_t* ls, const Batch& batch) {
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

// One call of the lifted loop: the stores of the batch, then the lifted epilogue, which
// restores r80 to r101, r1 and r0 from the frame and returns. The lifted loop ends with
// r85 = count and r80 = -128 in each lane.
void native_step(spu_context* ctx) {
    publish(ctx->ls, pending);
    ctx->gpr[85] = spu_splat_u32(pending.count);
    ctx->gpr[80] = spu_splat_u32(0xffffff80u);
    jobmod_556b30b5e654_e12e20_spu_func_0000ABEC(ctx);
}

// The kernel runs on one copy of the caller, the lifted loop on another copy. The local store,
// the link register, the stack pointer and r80 to r127 must be equal. The lifted function does
// not save r2 to r79: its caller writes each of them before it reads it. A difference stops
// the process.
bool compare(spu_context* ctx) {
    Copies& pair = copies();
    if (!snapshot(ctx, pair)) return false;
    const uint32_t ret = ctx->gpr[0]._u32[0];
    native_step(&pair.candidate);
    if (!run_lifted(&pair.reference, game_original_particle_collision_loop, ret)) return false;
    same_bytes("COLLISION", pair.reference.ls, pair.candidate.ls, sizeof ctx->ls_store, 0);
    for (unsigned r = 0; r < 2; ++r)
        for (unsigned lane = 0; lane < 4; ++lane)
            same_word("COLLISION", r, lane, pair.reference.gpr[r]._u32[lane], pair.candidate.gpr[r]._u32[lane]);
    for (unsigned r = 80; r < 128; ++r)
        for (unsigned lane = 0; lane < 4; ++lane)
            same_word("COLLISION", r, lane, pair.reference.gpr[r]._u32[lane], pair.candidate.gpr[r]._u32[lane]);
    if (pair.reference.pc != pair.candidate.pc)
        mismatch("COLLISION", "pc", 0, pair.reference.pc, pair.candidate.pc);
    ++compared;
    return true;
}
}  // namespace

extern "C" void motorstorm_particle_collision_batch(spu_context* ctx) try {
    const Config& config = motorstorm_particle_bind::config(OPTION);
    if (config.mode == Mode::reference) { game_original_particle_collision_loop(ctx); return; }
    // r85 is the record index. It is 0 only when the lifted prologue enters the loop.
    const char* reason = spu_preferred_u32(&ctx->gpr[85]) ? "loop re-entry" :
        admission(config, ctx, game_particle_collision_code_matches);
    if (!reason) reason = load_inputs(ctx, pending);
    if (!reason && config.mode == Mode::shadow && !compare(ctx)) reason = "shadow state changed";
    if (reason) {
        const auto count = ++fallbacks;
        if (count <= 16 || count % 4096 == 0)
            std::fprintf(stderr, "[native-particle-collision] fallbacks=%llu reason=%s\n",
                         static_cast<unsigned long long>(count), reason);
        game_original_particle_collision_loop(ctx);
        return;
    }
    // Shadow comparisons use private copies. The live caller keeps the state of the original.
    if (config.mode == Mode::shadow) game_original_particle_collision_loop(ctx);
    else native_step(ctx);
    const auto count = ++calls;
    if (count == 1 || count % 1024 == 0)
        std::fprintf(stderr, "[native-particle-collision] completed=%llu compared=%llu particles=%llu contacts=%llu\n",
            static_cast<unsigned long long>(count),
            static_cast<unsigned long long>(config.mode == Mode::shadow ? count : compared.load()),
            static_cast<unsigned long long>(particles.fetch_add(pending.count) + pending.count),
            static_cast<unsigned long long>(contacts.fetch_add(pending.result.contacts) + pending.result.contacts));
} catch (...) {
    std::fputs("NATIVE_PARTICLE_COLLISION_ERROR exception in the native entry\n", stderr);
    std::abort();
}
extern "C" void motorstorm_particle_collision_counts(MotorstormParticleBindCounts* out) {
    out->native_calls = calls.load();
    out->compared = compared.load();
    out->fallbacks = fallbacks.load();
}
namespace {
struct Startup {
    Startup() {
        const Config& config = motorstorm_particle_bind::config(OPTION);
        std::fprintf(stderr, "[native-particle-collision] mode=%s\n", config.text ? config.text : "0");
    }
} startup;
}  // namespace
