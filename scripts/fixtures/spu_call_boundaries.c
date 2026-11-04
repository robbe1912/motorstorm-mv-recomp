/* Real runtime and actual generated call brackets; no guest data or services. */
#define main existing_handoff_main
#include "spu_interpreter_handoff.c"
#undef main
#include "spu_call_brackets.h"
#include <fenv.h>
#define CHECK(expr) do { if (!(expr)) { fprintf(stderr,"FAIL %s\n",#expr); exit(1); } } while(0)
static int select_call;
static void forbidden_return(spu_context* c) { (void)c; CHECK(0 && "compiled return entered while native caller owns it"); }
static void spu_func_00004000(spu_context* c) {
    CHECK(c->drain_ret_pc==(select_call>=4 ? SPU_LS_SIZE : 0x204) && "return boundary not published before callee");
    c->pc=0x4000;spu_indirect_branch(c);
}
static void call_entry(spu_context* ctx) {
    ctx->drain_ret_pc=0xABC;
    ctx->gpr[2]=spu_link(0x4000);ctx->gpr[6]=spu_link(0x4000);
    switch(select_call) {
        case 0: { EMIT_DIRECT } break;
        case 1: { EMIT_RELATIVE } break;
        case 2: { EMIT_INDIRECT } break;
        case 3: { EMIT_ALIAS } break;
        case 4: { EMIT_DIRECT_ZERO } break;
        case 5: { EMIT_RELATIVE_ZERO } break;
        case 6: { EMIT_INDIRECT_ZERO } break;
        default: { EMIT_ALIAS_ZERO } break;
    }
    CHECK(g_spu_trampoline_fn==NULL && "return boundary queued compiled dispatch");
    CHECK(ctx->drain_ret_pc==0xABC && "outer return boundary not restored");
    ctx->gpr[20]._u32[0]++;finish(ctx);
}
int main(int argc,char** argv) {
#ifdef _WIN32
    _set_error_mode(_OUT_TO_STDERR);
    _set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
#endif
    CHECK(argc==2);int variant=atoi(argv[1]);CHECK(variant>=0 && variant<17);int stopped_before_return=variant==16;select_call=stopped_before_return ? 4 : (variant&7);
    spu_context_init(&ctx,0);ctx.image_id=77;ctx.policy_mode=1;ctx.status=SPU_STATUS_RUNNING;
    spu_begin_image(77);spu_register_function(0x240,finish);
    if (variant>=8 && variant<16) spu_register_function(select_call>=4 ? 0 : 0x204,forbidden_return);
    word(0x4000,0x04000082); /* original ori: full interpreter */
    word(0x4004,stopped_before_return ? 0 : 0x35000300); /* bi r6: non-r0 link */
    word(0x204,0x1C004A95); /* ai r21,r21,1: native caller owns this continuation */
    word(0,0x1C004A95);word(4,0x30004800); /* unlifted return at LS zero */
    word(0x208,0x30004800); /* bra finish if interpreter overruns the return */
    CHECK(fesetround(FE_UPWARD)==0);int flags=fetestexcept(FE_ALL_EXCEPT);
    int halted=spu_run_with_halt(call_entry,&ctx);
    printf("case%d halted=%d host-cont=%u wrong-cont=%u\n",select_call,halted,ctx.gpr[20]._u32[0],ctx.gpr[21]._u32[0]);fflush(stdout);
    CHECK(halted==1 && ctx.gpr[20]._u32[0]==(stopped_before_return ? 0u : 1u) && ctx.gpr[21]._u32[0]==0 &&
           "interpreter passed native return boundary");
    CHECK(ctx.drain_ret_pc==0); /* halted native callers are no longer live */
    /* An explicit canonical stop belongs to its caller even if that PC also
     * has a compiled entry. Ordinary compiled rejoin is tested separately. */
    if (variant>=8 && variant<16) {
        spu_context_init(&ctx,0);ctx.image_id=77;ctx.policy_mode=1;
        ctx.status=SPU_STATUS_RUNNING;ctx.gpr[6]=spu_link(select_call>=4 ? 0 : 0x204);
        word(0x4000,0x04000082);word(0x4004,stopped_before_return ? 0 : 0x35000300);
        uint32_t boundary=select_call>=4 ? SPU_LS_SIZE : 0x204;
        CHECK(spu_interp_run_until(&ctx,0x4000,boundary)==(boundary&SPU_LS_MASK));
        CHECK(g_spu_trampoline_fn==NULL && "explicit canonical return queued compiled dispatch");
    }

    CHECK(fegetround()==FE_UPWARD && fetestexcept(FE_ALL_EXCEPT)==flags);
    puts("PASS exact call boundary, non-r0 link, outer boundary and FP");return 0;
}
