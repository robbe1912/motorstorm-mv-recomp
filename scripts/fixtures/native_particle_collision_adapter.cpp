#include "../../src/motorstorm/particle_box_collision_adapter.cpp"
#include <cassert>
#include <initializer_list>

static bool matcher = true;
static unsigned original_calls, live_calls, epilogue_calls, generation;
static const char* option_text;
// Bytewise preservation includes the padding poisoned by setup.
static spu_context ctx, before, expected;
static MotorstormParticleBindCounts counts;
// Stands in for the three symbols that the bound generated unit defines.
extern "C" {
void game_original_particle_collision_loop(spu_context* c) {
    // The lifted loop computes the batch, stores its result and ends with the index equal to the
    // count and the record offset below zero. Shadow mode runs one more call on its private copy.
    ++original_calls;
    live_calls += c == &ctx;
    Batch batch;
    if (!load_inputs(c, batch)) publish(c->ls, batch);
    c->gpr[85] = spu_splat_u32(c->gpr[86]._u32[0]);
    c->gpr[80] = spu_splat_u32(0xffffff80u);
    c->pc = c->gpr[0]._u32[0];
}
void jobmod_556b30b5e654_e12e20_spu_func_0000ABEC(spu_context* c) { ++epilogue_calls; c->pc = c->gpr[0]._u32[0]; }
int game_particle_collision_code_matches(const spu_context*) { return matcher; }
const char* motorstorm_particle_fixture_option(const char* name) {
    return std::strcmp(name, OPTION) ? nullptr : option_text;
}
unsigned motorstorm_particle_fixture_generation() { return generation; }
// The three runtime symbols of spu_context.h. The lifted return of the bound entry reads them.
thread_local void (*g_spu_trampoline_fn)(spu_context*) = nullptr;
int g_spu_ls_watch_n = 0;
void spu_indirect_branch(spu_context*) { assert(!"Unexpected caller dispatch"); std::abort(); }
}

static void setup(unsigned used, unsigned capacity, bool remove) {
    std::memset(&ctx, 0x5a, sizeof(ctx));
    ctx.ls = ctx.ls_store;
    constexpr uint32_t header = 0x24000, shape = 0x20000, stack = 0x3e000;
    ctx.gpr[81]._u32[0] = header; ctx.gpr[82]._u32[0] = shape;
    ctx.gpr[1]._u32[0] = stack; ctx.gpr[86]._u32[0] = 4;
    ctx.gpr[85]._u32[0] = 0; ctx.gpr[80]._u32[0] = 384;
    store(ctx.ls, stack + 416, 0x12188);
    store(ctx.ls, header + 4, 0x18000); store(ctx.ls, header + 8, 4);
    store(ctx.ls, header + 12, 4); store(ctx.ls, header + 1780, 0x40800000);
    store(ctx.ls, header + 684, used); store(ctx.ls, header + 688, capacity);
    store(ctx.ls, header + 692, 0x30000);
    std::memset(ctx.ls + shape, 0, 128);
    for (unsigned i = 0; i < 4; ++i)
        for (unsigned lane = 0; lane < 4; ++lane)
            ctx.gpr[91 - i]._u32[lane] = i == lane ? 0x3f800000 : 0;
    for (unsigned lane = 0; lane < 3; ++lane) store(ctx.ls, shape + 80 + lane * 4, 0x3f800000);
    ctx.ls[shape + 116] = remove;
    for (unsigned i = 0; i < 4; ++i) {
        std::memset(ctx.ls + 0x18000 + i * 128, int(i + 1), 128);
        for (unsigned offset : {0u, 48u})
            for (unsigned lane = 0; lane < 4; ++lane) store(ctx.ls, 0x18000 + i * 128 + offset + lane * 4, 0);
        store(ctx.ls, 0x18000 + i * 128 + 100, 0);
    }
}
static MotorstormParticleBindCounts read() {
    std::memset(&counts, 0, sizeof(counts));
    motorstorm_particle_collision_counts(&counts);
    return counts;
}
// One call of the bound loop symbol. Returns the number of times the lifted loop stand-in runs
// on the live caller.
static unsigned call(unsigned index, unsigned offset) {
    ctx.gpr[85] = spu_splat_u32(index); ctx.gpr[80] = spu_splat_u32(offset);
    ctx.gpr[0] = spu_splat_u32(0x12188); ctx.pc = 0xa87c;
    ctx.status = SPU_STATUS_RUNNING; ctx.list_stall_mask = 0; ctx.event_status = 0;
    ctx.int_enable = 1; ctx.event_mask = 2; ctx.irq_saved = 0; ctx.resv_valid = 0;
    g_spu_trampoline_fn = 0;
    const unsigned before_live = live_calls, before_epilogue = epilogue_calls;
    motorstorm_particle_collision_batch(&ctx);
    const unsigned live = live_calls - before_live;
    // Only a native batch reaches the lifted epilogue on the live caller. Shadow mode reaches
    // it on its private copy.
    assert(epilogue_calls - before_epilogue == (live == (config(OPTION).mode == Mode::shadow ? 1u : 0u)));
    return live;
}
int main() {
    for (bool remove : {false, true}) for (bool full : {false, true}) {
        setup(full ? 1 : 0, full ? 1 : 16, remove);
        std::memcpy(&before, &ctx, sizeof(ctx)); Batch batch;
        assert(!load_inputs(&ctx, batch));
        assert(!std::memcmp(&ctx, &before, sizeof(ctx)));
        batch.result.hit[0] = batch.result.hit[3] = 1;
        batch.result.contact[0] = {{1, 2, 3, 4}};
        batch.result.contact[3] = {{5, 6, 7, 8}};
        std::memcpy(&expected, &before, sizeof(expected));
        for (unsigned lane = 0; lane < 4; ++lane) {
            store(expected.ls_store, 0x3e020 + lane * 4, lane + 1);
            if (!full) {
                store(expected.ls_store, 0x30000 + lane * 4, lane + 5);
                store(expected.ls_store, 0x30010 + lane * 4, lane + 1);
            }
        }
        if (!full) store(expected.ls_store, 0x24000 + 684, 2);
        if (remove) {
            store(expected.ls_store, 0x24008, 2);
            std::memcpy(expected.ls_store + 0x18000, before.ls_store + 0x18100, 128);
        }
        publish(ctx.ls, batch);
        assert(!std::memcmp(&ctx, &expected, sizeof(ctx)));
    }
    // An event list inside the record list is declined: an appended contact would change a record.
    setup(0, 16, false); store(ctx.ls, 0x24000 + 692, 0x18000);
    std::memcpy(&before, &ctx, sizeof(ctx)); Batch batch;
    const char* reason = load_inputs(&ctx, batch);
    assert(reason && !std::strcmp(reason, "overlapping ranges"));
    assert(!std::memcmp(&ctx, &before, sizeof(ctx)));

    // The bound symbol. Mode 0, a loop re-entry and a declined batch call the lifted loop. The
    // first entry of an admitted batch runs the kernel and then the lifted epilogue. Shadow mode
    // compares both paths on copies and then runs the lifted loop.
    option_text = "0"; ++generation;
    setup(0, 16, false);
    assert(config(OPTION).mode == Mode::reference);
    assert(call(0, 384) == 1 && read().native_calls == 0);
    option_text = "1"; ++generation;
    setup(0, 16, false);
    assert(config(OPTION).mode == Mode::native);
    assert(call(0, 384) == 0);
    assert(ctx.pc == 0x12188 && ctx.gpr[85]._u32[0] == 4 && ctx.gpr[80]._u32[0] == 0xffffff80u);
    counts = read(); assert(counts.native_calls == 1 && counts.fallbacks == 0);
    setup(0, 16, false);
    assert(call(2, 128) == 1); counts = read();
    assert(counts.native_calls == 1 && counts.fallbacks == 1);
    matcher = false;
    setup(0, 16, false);
    assert(call(0, 384) == 1); counts = read();
    assert(counts.native_calls == 1 && counts.fallbacks == 2);
    matcher = true;
    setup(0, 16, false);
    store(ctx.ls, 0x24000 + 8, 9);
    assert(call(0, 384) == 1); counts = read();
    assert(counts.native_calls == 1 && counts.fallbacks == 3);
    option_text = "shadow"; ++generation;
    setup(0, 16, false);
    assert(config(OPTION).mode == Mode::shadow);
    assert(call(0, 384) == 1); counts = read();
    assert(counts.native_calls == 2 && counts.compared == 1 && counts.fallbacks == 3);
    std::puts("PASS backwards publication/removal, full lists, whole-context preservation, bound entry in three modes");
}
