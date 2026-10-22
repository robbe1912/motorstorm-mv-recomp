#pragma once
#include <cstdint>
// Authored ABI seam, not an original context layout or instruction payload.
union alignas(16) VisibilityRegister { std::uint32_t _u32[4]; };
struct spu_context {
    VisibilityRegister gpr[128];
    unsigned char ls_store[0x40000];
    unsigned char* ls;
    std::uint32_t pc, status, int_enable, event_status, event_mask, list_stall_mask, irq_saved;
    std::uint32_t interp_span_lo, interp_span_hi;
    unsigned policy_mode,wi_prev_pc;
    struct {std::uint32_t lsa,size;} resident_code[4];
    unsigned host_depth;
};
extern "C" {
struct spu_native_leaf_plan {
    std::uint64_t instructions;
    std::uint32_t resume_pc, last_pc;
    void (*execute)(spu_context*, const spu_native_leaf_plan*);
    const void* cookie;
};
struct spu_native_leaf {
    std::uint32_t begin, end;
    int (*prepare)(const spu_context*, std::uint64_t, spu_native_leaf_plan*);
};
int spu_native_leaf_register(const spu_native_leaf*);
std::uint32_t spu_interp_run_until_budget(spu_context*,std::uint32_t,std::uint32_t,std::uint64_t);
extern thread_local std::uint64_t g_spu_interp_steps;
extern thread_local std::uint32_t g_spu_interp_last_pc;
extern thread_local void (*g_spu_trampoline_fn)(spu_context*);
extern int g_spu_ls_watch_n;
void spu_indirect_branch(spu_context*);
void game_original_visibility_box(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_000083A0(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_000083C0(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_000083C8(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_000083E0(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_00008418(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_00008448(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_00008450(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_00008440(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_0000849C(spu_context*);
void jobmod_056ac0eea1a6_e12270_spu_func_000084A0(spu_context*);
void motorstorm_visibility_planes(spu_context*);
int game_visibility_code_matches(const spu_context*);
}
bool native_visibility_fixture_cpu();
void native_visibility_fixture_after_math(spu_context*);
void native_visibility_fixture_after_snapshot(const spu_context*);

const char* native_visibility_fixture_environment(const char*);
