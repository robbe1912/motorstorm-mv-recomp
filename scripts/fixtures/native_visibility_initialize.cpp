// Authored state exercises the production adapter without original game bytes.
#include "../../src/motorstorm/visibility_batch_adapter.cpp"
#include <cassert>

SPU_THREAD_LOCAL uint32_t g_spu_interp_last_pc;
extern "C" void game_original_visibility_batch(spu_context*) {}
extern "C" int game_visibility_batch_code_matches(const spu_context*) { return 0; }
int g_spu_ls_watch_n = -1;
extern "C" int spu_native_leaf_register(const spu_native_leaf*) { return 0; }
extern "C" int spu_native_leaf_register_unbudgeted(const spu_native_leaf*) { return 0; }
extern "C" int motorstorm_us_visibility_nonflushing(const uint8_t*, unsigned) { return 0; }
extern "C" int motorstorm_us_visibility_classify(uint8_t*, unsigned, uint32_t,
                                                MotorstormVisibilityPublish, void*) { return 0; }
extern "C" int motorstorm_us_visibility_occluder_supported(const uint8_t*, unsigned, unsigned) { return 0; }
extern "C" int motorstorm_us_visibility_occluder(uint8_t*, unsigned, unsigned) { return 0; }

static spu_context state, expected;

int main() {
    auto* bytes = reinterpret_cast<uint8_t*>(&state);
    for (size_t i = 0; i < sizeof(state); ++i) bytes[i] = uint8_t(i * 73 + i / 17);
    state.ls = state.ls_store;
    std::memcpy(&expected, &state, sizeof(state));
    std::memset(expected.ls_store + workspace_begin, 0, workspace_end - workspace_begin);
    for (unsigned lane = 0; lane < 4; ++lane) {
        expected.gpr[3]._u32[lane] = workspace_end;
        expected.gpr[5]._u32[lane] = expected.gpr[6]._u32[lane] = 0;
    }
    expected.pc = initialize_return;
    initialize(&state, nullptr);
    assert(std::memcmp(&state, &expected, sizeof(state)) == 0);
    assert(initialize_instructions == 17006);

    // Correct register ranges alone cannot admit an unqualified job image.
    state.policy_mode = state.int_enable = 1;
    state.event_mask = list_stall_event;
    state.irq_saved = state.resv_valid = 0;
    g_spu_interp_last_pc = 0x162b8;
    for (unsigned lane = 0; lane < 4; ++lane) {
        state.gpr[3]._u32[lane] = workspace_begin;
        state.gpr[4]._u32[lane] = workspace_end;
        state.gpr[126]._u32[lane] = 0;
    }
    std::memcpy(&expected, &state, sizeof(state));
    spu_native_leaf_plan plan{};
    assert(!prepare_initialize(&state, UINT64_MAX, &plan));
    assert(std::memcmp(&state, &expected, sizeof(state)) == 0);
    std::puts("PASS visibility workspace bounds, full context preservation and foreign-image rejection");
}
