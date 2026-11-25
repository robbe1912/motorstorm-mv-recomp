/* Real spu_run_with_halt, spu_halt and spu_restart_dispatch: jump out of a
 * drain scope and read the MXCSR and scope state where the jump lands. */
#define main existing_handoff_main
#include "spu_interpreter_handoff.c"
#undef main
#include "spu_float_simd.h"
extern void spu_restart_dispatch(spu_context*);
/* Round up, flush nothing, all exceptions masked: no bit pattern SPU mode has. */
#define HOST_CSR 0x5f80u
#define LANDING(expr) do { if (!(expr)) { \
    fprintf(stderr,"FAIL landing %s line%d csr=%04x scope=%d\n",#expr,__LINE__,_mm_getcsr(),g_spu_sf_simd_scope); \
    exit(1); } } while(0)
#define CONTROL(csr) ((csr) & 0xffc0u)
static int want_halt, resets_left, in_scope, resumed, after_halt_lost;

static void jump_out(spu_context* c) {
    FIXTURE_CHECK(spu_sf_csr_is_spu(_mm_getcsr()) && g_spu_sf_simd_scope>0); /* the jump leaves a held scope */
    in_scope++;
    if (want_halt) finish(c);
    c->pc=0x300;
    spu_restart_dispatch(c);
    after_halt_lost=1; /* both jumps must not return */
}
static void scoped_call(spu_context* c) {
    c->host_depth++;
    c->pc=0x200;g_spu_trampoline_fn=jump_out;
    spu_drain_call(c,0x204);
    c->host_depth--;
    after_halt_lost=1;
}
/* Case 2 target: the resumed job code. */
static void resume_target(spu_context* c) {
    resumed++;
    LANDING(spu_sf_csr_is_spu(_mm_getcsr()));
    LANDING(g_spu_sf_simd_scope>0);
    LANDING(CONTROL(g_spu_sf_host_csr)==CONTROL(HOST_CSR));
    /* 1 + 2^-24 truncates to 1 in SPU mode; the host mode above rounds it up. */
    u128 one,tiny;for(int i=0;i<4;i++){one._u32[i]=0x3f800000u;tiny._u32[i]=0x33800000u;}
    LANDING(spu_fa(one,tiny)._u32[0]==0x3f800000u);
    if (resets_left-- > 0) scoped_call(c);
    else if (want_halt) { finish(c); }
    /* otherwise return normally: spu_run_with_halt leaves the new scope */
}
static int nested_seen;
static void nested_outer(spu_context* c) {
    static spu_context inner;
    uint64_t token=spu_sf_simd_enter();uint32_t held=_mm_getcsr();int scope=g_spu_sf_simd_scope;
    spu_context_init(&inner,0);inner.image_id=77;inner.policy_mode=1;inner.status=SPU_STATUS_RUNNING;
    LANDING(spu_run_with_halt(scoped_call,&inner)==1);
    LANDING(CONTROL(_mm_getcsr())==CONTROL(held) && g_spu_sf_simd_scope==scope); /* still the outer scope */
    nested_seen=1;spu_sf_simd_leave(token);
    (void)c;
}
int main(int argc,char** argv) {
#ifdef _WIN32
    _set_error_mode(_OUT_TO_STDERR);_set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
#endif
    FIXTURE_CHECK(argc==2);const char* mode=argv[1];
    int nested=!strcmp(mode,"nested"),reset=!strncmp(mode,"reset",5);
    want_halt=!strcmp(mode,"halt")||nested;
    resets_left=!strcmp(mode,"reset-reset");
    spu_context_init(&ctx,0);ctx.image_id=77;ctx.policy_mode=1;ctx.status=SPU_STATUS_RUNNING;
    spu_begin_image(77);spu_register_function(0x300,resume_target);
    _mm_setcsr(HOST_CSR);FIXTURE_CHECK(g_spu_sf_simd_scope==0);
    int halt_after_resume=!strcmp(mode,"reset-halt");
    if (halt_after_resume) resets_left=-1;
    int halted;
    if (nested) halted=spu_run_with_halt(nested_outer,&ctx);
    else if (halt_after_resume) {
        /* the first jump is the reset; the resumed code then halts */
        extern void reset_then_halt(spu_context*);
        halted=spu_run_with_halt(reset_then_halt,&ctx);
    } else halted=spu_run_with_halt(scoped_call,&ctx);
    uint32_t csr=_mm_getcsr();
    LANDING(CONTROL(csr)==CONTROL(HOST_CSR));
    LANDING(g_spu_sf_simd_scope==0);
    FIXTURE_CHECK(!after_halt_lost && in_scope>=1 && nested_seen==nested);
    FIXTURE_CHECK(halted==((want_halt && !nested) || halt_after_resume));
    FIXTURE_CHECK(resumed==(!reset ? 0 : !strcmp(mode,"reset-reset") ? 2 : 1));
    FIXTURE_CHECK(in_scope==(!strcmp(mode,"reset-reset") ? 2 : 1));
    printf("PASS %s csr=%04x scope=%d resumed=%d\n",mode,csr,g_spu_sf_simd_scope,resumed);
    return 0;
}
static void reset_jump(spu_context* c) {
    FIXTURE_CHECK(spu_sf_csr_is_spu(_mm_getcsr()) && g_spu_sf_simd_scope>0);
    in_scope++;want_halt=1;c->pc=0x300;spu_restart_dispatch(c);after_halt_lost=1;
}
void reset_then_halt(spu_context* c) {
    c->host_depth++;c->pc=0x200;g_spu_trampoline_fn=reset_jump;
    spu_drain_call(c,0x204);c->host_depth--;after_halt_lost=1;
}
