#include "../../src/motorstorm/particle_box_collision_adapter.cpp"
#include <cassert>
#include <initializer_list>

extern "C" {
SPU_THREAD_LOCAL uint32_t g_spu_interp_last_pc;
int spu_native_leaf_register_unbudgeted(const spu_native_leaf*) { return 0; }
uint32_t spu_interp_run_until(spu_context*, uint32_t, uint32_t) { std::abort(); }
}
// Bytewise preservation includes the padding poisoned by setup.
static spu_context ctx, before, expected;

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
int main() {
    for (bool remove : {false, true}) for (bool full : {false, true}) {
        setup(full ? 1 : 0, full ? 1 : 16, remove);
        std::memcpy(&before, &ctx, sizeof(ctx)); Pending batch;
        assert(load_inputs(&ctx, batch));
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
    setup(0, 16, false); store(ctx.ls, 0x24000 + 692, 0x18000);
    std::memcpy(&before, &ctx, sizeof(ctx)); Pending batch;
    assert(!load_inputs(&ctx, batch)); assert(!std::memcmp(&ctx, &before, sizeof(ctx)));
    setup(0, 16, false); mode = Mode::native;
    ctx.pc = entry; ctx.status = SPU_STATUS_RUNNING; ctx.list_stall_mask = 0; ctx.event_status = 0;
    ctx.policy_mode = 1; ctx.int_enable = 1; ctx.event_mask = 2;
    ctx.irq_saved = 0; ctx.resv_valid = 0; g_spu_interp_last_pc = 0xa868;
    std::memcpy(&before, &ctx, sizeof(ctx)); spu_native_leaf_plan plan{};
    assert(!prepare(&ctx, 0, &plan)); assert(!std::memcmp(&ctx, &before, sizeof(ctx)));
    std::puts("PASS backwards publication/removal, full lists, whole-context preservation and foreign-image decline");
}
