/* Gate diet of the lifted SPU engine, with the production runtime.
 *
 * The scenarios of spu_native_owned.c run unchanged through gate_base_main.
 * This file adds:
 *   - the stop states that an option arms (the lifted code must not run);
 *   - the stop states set directly on the context and on the gate words;
 *   - a lifted function that arms a stop state and names a lifted target:
 *     the drain loop must not run that target (one policy test per iteration);
 *   - the job dump: the probe must see each address that the gate examines.
 * A stop scenario passes when the lifted code did not run and the result
 * equals the interpreted reference. gate_base_main reports that state as
 * "FAIL native calls=0 expected=1", so the check script expects that line. */
/* The build renames the main function of that file to gate_base_main
 * (OWNED_MAIN_NAME); that file renames the main of the transition fixture. */
#include "spu_native_owned.c"
#undef main
static void set_option(const char* text) { /* NAME=VALUE */
#ifdef _WIN32
    _putenv(text);
#else
    putenv(text);
#endif
}

/* The context of the admission scenarios: a policy lane with one resident
 * owner for 0x4000. */
static void admission_context(spu_context* c) {
    spu_context_init(c,0);c->image_id=77;c->policy_mode=1;c->img_ls_base=0x200;
    c->pc=0x4000;c->status=SPU_STATUS_RUNNING;
    c->resident_code[0].lsa=0x4000;c->resident_code[0].size=0x14;
    c->resident_code[0].image_id=25;
}

static void direct_states(void) {
    spu_context c;
    admission_context(&c);
    OWNED_CHECK(spu_native_owned_can_run(&c,0x4000));
    /* each gate word alone stops the lifted code */
    const int probe=g_spu_ls_probe,smc=g_spu_smc_watch;
    g_spu_smc_watch=1;OWNED_CHECK(!spu_native_owned_can_run(&c,0x4000));
    g_spu_smc_watch=smc;
    g_spu_ls_probe=1;OWNED_CHECK(!spu_native_owned_can_run(&c,0x4000));
    g_spu_ls_probe=probe;
    g_spu_ls_watch_n=1;OWNED_CHECK(!spu_native_owned_can_run(&c,0x4000));
    g_spu_ls_watch_n=0;
    /* no local store, no image: no lifted code can run */
    uint8_t* ls=c.ls;c.ls=NULL;OWNED_CHECK(!spu_native_owned_can_run(&c,0x4000));c.ls=ls;
    c.image_id=-1;OWNED_CHECK(!spu_native_owned_can_run(&c,0x4000));c.image_id=77;
    /* the policy test is part of can_run and not part of run_ok */
    c.policy_mode=0;OWNED_CHECK(!spu_native_owned_can_run(&c,0x4000));
    OWNED_CHECK(spu_native_owned_run_ok(&c,0x4000));
    c.policy_mode=1;
    /* an owner that does not hold the address admits nothing */
    c.pc=0x4000;c.resident_code[0].size=4;
    OWNED_CHECK(!spu_native_owned_can_run(&c,0x4010));
    /* the words of the thread hold the option values: a second read makes no call */
    OWNED_CHECK(g_spu_native_owned_mode==2 && g_spu_native_owned_observed==1 && g_spu_native_owned_image==1);
    OWNED_CHECK(g_spu_native_owned_mode==2 && g_spu_native_owned_observed==1 && g_spu_native_owned_image==1);
    OWNED_CHECK(spu_owned_jobs()==1 && spu_owned_observed()==0 && spu_owned_image()==0);
    puts("direct PASS");
}

/* A lifted function that arms a stop state and names a lifted target. */
static void arming_job(spu_context* c) {
    ++native_calls;
    c->gpr[3]=spu_ai(c->gpr[3],3);
    g_spu_smc_watch=1;
    c->pc=0x4004;
    g_spu_trampoline_fn=owned_job;
    spu_drain_call(c,0x204);
    OWNED_CHECK(c->pc==0x204);
    g_spu_trampoline_fn=spu_indirect_branch;
}

/* The reference runs the same guest code without lifted code. */
static void lifted_stop(void) {
    spu_context_init(&ctx,0);ctx.image_id=77;ctx.policy_mode=1;ctx.img_ls_base=0x200;
    ctx.pc=0x200;ctx.status=SPU_STATUS_RUNNING;
    word(0x200,0x31080000); /* brasl r0,0x4000 */
    word(0x204,0x1C008183); /* ai r3,r3,2 */
    word(0x4000,0x1C00C183); /* ai r3,r3,3 */
    word(0x4004,0x35000000); /* bi r0 */
    ctx.resident_code[0].lsa=0x4000;ctx.resident_code[0].size=0x14;
    ctx.resident_code[0].image_id=25;
    spu_begin_image(77);
    spu_register_function(0x200,forbidden_policy);spu_register_function(0x204,forbidden_policy);
    spu_begin_image(25);spu_register_function(0x4000,arming_job);
    memcpy(&reference,&ctx,sizeof ctx);reference.ls=reference.ls_store;
    memset(reference.resident_code,0,sizeof reference.resident_code);
    spu_run_with_halt(forbidden_policy,&reference);
    spu_run_with_halt(forbidden_policy,&ctx);
    const int smc=g_spu_smc_watch;g_spu_smc_watch=0;
    /* arming_job ran; the drain loop stopped lifted code, so owned_job did not */
    printf("stop-in-lifted native=%u pc=0x%05X tramp=%d r3=%u\r\n",native_calls,ctx.pc&SPU_LS_MASK,g_spu_trampoline_fn!=0,ctx.gpr[3]._u32[0]);
    OWNED_CHECK(native_calls==1);
    OWNED_CHECK(!memcmp(ctx.gpr,reference.gpr,sizeof ctx.gpr));
    OWNED_CHECK(!memcmp(ctx.ls,reference.ls,SPU_LS_SIZE));
    g_spu_smc_watch=smc;
    printf("stop-in-lifted PASS native=%u r3=%u\n",native_calls,ctx.gpr[3]._u32[0]);
}

int main(int argc,char** argv) {
#ifdef _WIN32
    _set_error_mode(_OUT_TO_STDERR);_set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
#endif
    OWNED_CHECK(argc==2);const char* mode=argv[1];
    if (!strcmp(mode,"direct")) { direct_states(); return 0; }
    if (!strcmp(mode,"stop-in-lifted")) { lifted_stop(); return 0; }
    if (!strcmp(mode,"stop-watch")) set_option("SPU_LS_WATCH=0x4000");
    else if (!strcmp(mode,"stop-smc")) set_option("SPU_SMC_WATCH=1");
    else if (!strcmp(mode,"stop-lowread")) set_option("SPU_LS_LOWREAD=1");
    else if (!strcmp(mode,"dump")) set_option("SPU_JOB_DUMP=25:16384:4:1:dumpdir");
    else if (strncmp(mode,"stop-",5) && strcmp(mode,"dump")) return gate_base_main(argc,argv);
    char* base[]={(char*)"gate",(char*)"owned",NULL};
    return gate_base_main(2,base);
}
