/* Runtime context of the vehicle update binding check. The handoff fixture defines the SPU context
   that the runtime uses. Its main gets another name here. The interpreter is the file of the
   vendor runtime. vehicle_binding_context() gives the context. */
#define main handoff_fixture_main
#define FIXTURE_REAL_SPU_ALIAS 1
#include "spu_interpreter_handoff.c"
#undef main
#include "../../vendor/ps3recomp/runtime/spu/spu_interp.c"

void ppu_fm_window_begin(unsigned page) { (void)page; }
void ppu_fm_window_end(unsigned page, int state) { (void)page; (void)state; }

spu_context* vehicle_binding_context(void) { return &ctx; }
