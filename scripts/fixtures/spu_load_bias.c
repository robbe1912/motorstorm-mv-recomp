/* Authored instruction bytes, actual lifter output and production runtime. */
#define main existing_handoff_main
#include "spu_interpreter_handoff.c"
#undef main
#include "load_bias_programs.h"
#include <assert.h>
#include <fenv.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <crtdbg.h>
#endif

extern void spu_begin_image(int);
extern void spu_register_function(uint32_t, void (*)(spu_context*));
extern int spu_run_with_halt(void (*)(spu_context*), spu_context*);
static u128 expected[128];
static uint8_t original_ls[SPU_LS_SIZE];
static int native_targets, ends, variant;
static uint32_t table_address;

static void table_target(spu_context *c) {
    native_targets++;
    if (table_address == 0x1020) table_spu_func_00001020(c);
    else table_spu_func_00001028(c);
}

static void target(spu_context *c) {
    native_targets++;
    targets[variant](c);
}
static void end(spu_context *c) { assert(c->pc == 0x8000); ends++; }

static void initialize(void) {
    spu_context_init(&ctx, 0);
    ctx.image_id = 77 + variant;
    ctx.status = SPU_STATUS_RUNNING;
    ctx.int_enable = variant == 1; /* disable must actually change it */
    for (unsigned r = 0; r < 128; r++)
        for (unsigned lane = 0; lane < 4; lane++)
            ctx.gpr[r]._u32[lane] = 0x12340000 + r * 16 + lane;
    ctx.gpr[0] = spu_link(0x8000);
    for (unsigned i = 0; i < sizeof programs[0] / sizeof programs[0][0]; i++) {
        uint32_t w = programs[variant][i];
        for (unsigned j = 0; j < 4; j++) ctx.ls[0x4030 + i * 4 + j] = w >> (24 - j * 8);
    }
    memcpy(expected, ctx.gpr, sizeof expected);
    for (unsigned lane = 0; lane < 4; lane++) {
        expected[2]._u32[lane] = 0x4040;
        expected[3]._u32[lane] = 123;
    }
    memcpy(original_ls, ctx.ls, sizeof original_ls);
}

static void check_state(void) {
    assert(memcmp(ctx.gpr, expected, sizeof expected) == 0);
    assert(memcmp(ctx.ls, original_ls, sizeof original_ls) == 0);
    assert(ctx.pc == 0x8000 && ctx.status == SPU_STATUS_RUNNING);
    assert(ctx.int_enable == (variant == 2));
    assert(!ctx.irq_frame && !ctx.irq_saved && !ctx.host_depth && !ctx.drain_ret_pc);
    assert(fegetround() == FE_UPWARD && fetestexcept(FE_ALL_EXCEPT) == 0);
}

int main(void) {
#ifdef _WIN32
    /* Report assertion failures to the captured stream, without a modal UI. */
    _set_error_mode(_OUT_TO_STDERR);
    _CrtSetReportMode(_CRT_ASSERT, _CRTDBG_MODE_FILE);
    _CrtSetReportFile(_CRT_ASSERT, _CRTDBG_FILE_STDERR);
    _set_abort_behavior(0, _WRITE_ABORT_MSG | _CALL_REPORTFAULT);
#endif
    assert(fesetround(FE_UPWARD) == 0 && feclearexcept(FE_ALL_EXCEPT) == 0);
    for (variant = 0; variant < 3; variant++) {
        initialize();
        spu_begin_image(77 + variant);
        /* The registry preserves first-match ownership. Wrap this one entry
         * before the generated table solely to count native execution. */
        spu_register_function(0x4040, target);
        registrations[variant]();
        spu_register_function(0x8000, end);
        native_targets = ends = 0;
        assert(spu_run_with_halt(entries[variant], &ctx) == 0);
        fprintf(stderr, "variant=%d native-target=%d end=%d pc=%x\n", variant, native_targets, ends, ctx.pc);
        assert(native_targets == 1 && ends == 1);
        check_state();
        initialize();
        /* A separate, empty positive registry retains the explicit stop API;
         * negative-image pure mode historically ignores that stop argument. */
        ctx.image_id = 997 + variant;
        uint32_t reference_pc = spu_interp_run_until_budget(&ctx, 0x4030, 0x8000, 32);
        fprintf(stderr, "reference pc=%x status=%x steps=%llu\n", reference_pc, ctx.status, (unsigned long long)ctx.steps);
        assert(reference_pc == 0x8000);
        assert(native_targets == 1 && ends == 1);
        check_state();
    }
    puts("PASS 3 actual generated native continuations and pure reference: GPR/LS/PC/status/IRQ/FP oracle");
    variant = 0;
    for (unsigned choice = 0; choice < 2; choice++) {
        table_address = choice ? 0x1028 : 0x1020;
        spu_begin_image(300 + choice);
        spu_register_function(table_address, table_target);
        table_spu_recomp_register();
        spu_register_function(0x8000, end);
        for (unsigned reference = 0; reference < 2; reference++) {
            initialize();
            ctx.image_id = (reference ? 400 : 300) + choice;
            for (unsigned lane = 0; lane < 4; lane++) ctx.gpr[2]._u32[lane] = table_address;
            memcpy(expected, ctx.gpr, sizeof expected);
            for (unsigned lane = 0; lane < 4; lane++) {
                expected[3]._u32[lane] = 0x1010;
                expected[4]._u32[lane] = choice ? 22 : 11;
            }
            for (unsigned i = 0; i < sizeof table_program / sizeof table_program[0]; i++)
                for (unsigned byte = 0; byte < 4; byte++)
                    ctx.ls[0x1000 + i * 4 + byte] = table_program[i] >> (24 - byte * 8);
            memcpy(original_ls, ctx.ls, sizeof original_ls);
            if (!reference) {
                native_targets = ends = 0;
                assert(spu_run_with_halt(table_spu_func_00001000, &ctx) == 0);
            } else {
                assert(spu_interp_run_until_budget(&ctx, 0x1000, 0x8000, 32) == 0x8000);
            }
            assert(native_targets == 1 && ends == 1);
            check_state();
        }
    }
    puts("PASS 2 actual sized-symbol computed entries and pure reference: GPR/LS/PC/status/IRQ/FP oracle");
    return 0;
}
