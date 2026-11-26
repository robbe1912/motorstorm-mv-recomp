/* Checks the bound native entry of the vehicle update through the real lifted entry. The wrapper
   that scripts/native_game_binding.py makes (the lifted name) calls the native entry. The check
   runs the lifted function and the wrapper from the same state of each kernel pair. It compares
   the whole context before the drain of the call bracket and after it. It also compares both
   results with the return state of the pair.

   Arguments: --mode native|shadow|reference (default native), --corrupt (change one byte of the
   code window at LS 0x20CB0 before the wrapper runs: the admission must refuse the context),
   --expect-stopped (the kernel must stop: its native runs must be 0), <pairs directory>.

   Usage: python scripts/check_vehicle_update_binding.py */
#include "../../src/motorstorm/no_dialogs.h"

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "spu_context.h"
#include "spu_float_simd.h"
#include "vehicle_update.h"

extern "C" {
void spu_begin_image(int);
void jobmod_8de1770ee613_e1cd40_spu_func_00011FE0(spu_context*);
void jobmod_8de1770ee613_e1cd40_spu_recomp_register(void);
void game_original_vehicle_update(spu_context*);
uint64_t motorstorm_vehicle_update_native_runs();
spu_context* vehicle_binding_context(void);
}

namespace {

constexpr uint32_t LS_SIZE = MOTORSTORM_VEHICLE_LS_SIZE;
constexpr uint32_t ENTRY = MOTORSTORM_VEHICLE_ENTRY, RETURN = MOTORSTORM_VEHICLE_RETURN;
constexpr uint32_t CORRUPT = 0x20CB8; /* inside the third code window, after the extent */

struct Pair {
    std::vector<unsigned char> file;
    std::string name;
    const unsigned char *entry_regs, *return_regs, *entry_ls, *return_ls;
};

std::vector<unsigned char> read_file(const std::string& path) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) {
        std::fprintf(stderr, "BINDING_ERROR cannot open %s\n", path.c_str());
        std::exit(2);
    }
    std::vector<unsigned char> data;
    unsigned char buffer[1 << 16];
    size_t n;
    while ((n = std::fread(buffer, 1, sizeof buffer, f)) != 0) data.insert(data.end(), buffer, buffer + n);
    std::fclose(f);
    return data;
}

Pair load(const std::string& path) {
    Pair p;
    p.file = read_file(path);
    p.name = path.substr(path.find_last_of("/\\") + 1);
    if (p.file.size() != 40 + 2048 + 2048 + 2 * size_t(LS_SIZE) + 8192) {
        std::fprintf(stderr, "BINDING_ERROR bad pair size %s\n", path.c_str());
        std::exit(2);
    }
    const unsigned char* f = p.file.data();
    p.entry_regs = f + 40;
    p.return_regs = p.entry_regs + 2048;
    p.entry_ls = p.return_regs + 2048;
    p.return_ls = p.entry_ls + LS_SIZE;
    return p;
}

std::vector<std::string> list_pairs(const std::string& dir) {
    std::vector<std::string> out;
#if defined(_WIN32)
    WIN32_FIND_DATAA found;
    HANDLE handle = FindFirstFileA((dir + "\\job_*.bin").c_str(), &found);
    if (handle != INVALID_HANDLE_VALUE) {
        do {
            out.push_back(dir + "\\" + found.cFileName);
        } while (FindNextFileA(handle, &found));
        FindClose(handle);
    }
#endif
    std::sort(out.begin(), out.end());
    return out;
}

}  // namespace

int main(int argc, char** argv) {
    motorstorm::no_dialogs();
    const char* mode = "native";
    bool corrupt = false, expect_stopped = false;
    std::string dir;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--mode" && i + 1 < argc) mode = argv[++i];
        else if (arg == "--corrupt") corrupt = true;
        else if (arg == "--expect-stopped") expect_stopped = true;
        else dir = arg;
    }
    if (dir.empty()) {
        std::fputs("BINDING_ERROR no pairs directory\n", stderr);
        return 2;
    }
    _putenv_s("MS_NATIVE_VEHICLE_UPDATE", !std::strcmp(mode, "native") ? "1" : mode);
    _putenv_s("SPU_WP", "0");
    _putenv_s("SPU_PM_GATE_TRACE", "0");
    _putenv_s("SPU_PM_RETIRE_GUARD", "0");
    _putenv_s("SPU_PM_PC_RESUME", "0");
    _putenv_s("SPU_PM_FLOW_RESUME", "0");
    _putenv_s("SPU_PM_YIELD_RESUME", "0");
    _putenv_s("SPU_NATIVE_OWNED_JOBS", "1");
    _putenv_s("SPU_PROBE_INTERP", "0");

    spu_context* c = vehicle_binding_context();
    std::memset(c, 0, sizeof *c);
    spu_context_init(c, 0);
    c->image_id = 219;
    c->policy_mode = 1;
    c->img_ls_base = 0xa00;
    c->status = SPU_STATUS_RUNNING;
    c->int_enable = 1; /* the job of the pairs runs with interrupts enabled */
    c->resident_code[0].image_id = 219;
    c->resident_code[0].lsa = 0x4000;
    c->resident_code[0].size = 0x1d250;
    c->resident_code[0].rel = 0;
    c->resident_code[0].source_ea = 0;
    spu_begin_image(219);
    jobmod_8de1770ee613_e1cd40_spu_recomp_register();

    const std::vector<std::string> paths = list_pairs(dir);
    /* All runs start from the same context bytes. */
    std::vector<unsigned char> base(sizeof *c), lifted(sizeof *c), native(sizeof *c);
    unsigned long long differences_post = 0, trampoline_differences = 0, pre_state_differences = 0;
    unsigned long long pair_differences = 0, lifted_pair_mismatches = 0, steps_differences = 0;
    size_t first_post = 0;
    /* steps counts the lifted dispatches of the drain. A native run has fewer of them by design. */
    constexpr size_t kSteps = __builtin_offsetof(spu_context, steps);

    for (const std::string& path : paths) {
        const Pair p = load(path);
        if (paths[0] == path) {
            std::memcpy(c->ls, p.entry_ls, LS_SIZE);
            std::memcpy(base.data(), c, base.size());
            c->host_depth = 0;
        }
        /* The lifted function, then the wrapper. Each runs in the form of the call bracket of the
           job: the registers and the link register of the pair, the return address in
           drain_ret_pc, one host depth level. The drain follows as in the bracket. */
        const void* trampolines[2] = {};
        for (int side = 0; side < 2; ++side) {
            std::memcpy(c, base.data(), base.size());
            std::memcpy(c->ls, p.entry_ls, LS_SIZE);
            std::memcpy(c->gpr, p.entry_regs, sizeof c->gpr);
            c->host_depth = 0;
            c->pc = ENTRY;
            c->drain_ret_pc = RETURN;
            if (side == 1 && corrupt) c->ls[CORRUPT] ^= 0xFF;
            const uint64_t scope = spu_sf_simd_enter();
            ++c->host_depth;
            const uint64_t native_before = motorstorm_vehicle_update_native_runs();
            if (side == 0) game_original_vehicle_update(c);
            else jobmod_8de1770ee613_e1cd40_spu_func_00011FE0(c);
            if (side == 1 && corrupt) c->ls[CORRUPT] ^= 0xFF;
            /* After a native run the context is at the return address with no trampoline, as the
               lifted context is when its last function returns inside the bracket. The native mode
               leaves drain_ret_pc as the bracket set it. The shadow mode leaves the lifted state
               after its drain: drain_ret_pc is 0. */
            const uint32_t expected_drain_ret_pc = !std::strcmp(mode, "shadow") ? 0u : RETURN;
            if (motorstorm_vehicle_update_native_runs() != native_before &&
                !(c->pc == RETURN && !g_spu_trampoline_fn && c->drain_ret_pc == expected_drain_ret_pc &&
                  c->host_depth == 1))
                ++pre_state_differences;
            spu_drain_call(c, RETURN);
            --c->host_depth;
            spu_sf_simd_leave(scope);
            trampolines[side] = reinterpret_cast<const void*>(g_spu_trampoline_fn);
            std::memcpy(side == 0 ? lifted.data() : native.data(), c, base.size());
            if (side == 1) trampoline_differences += trampolines[0] != trampolines[1];
            const bool pair_ok = !std::memcmp(c->ls, p.return_ls, LS_SIZE) &&
                                 !std::memcmp(c->gpr, p.return_regs, sizeof c->gpr);
            if (side == 0) lifted_pair_mismatches += !pair_ok;
            else pair_differences += !pair_ok;
        }
        for (size_t i = 0; i < base.size(); ++i) {
            if (i >= kSteps && i < kSteps + sizeof c->steps) continue;
            if (lifted[i] != native[i]) { if (!differences_post) first_post = i; ++differences_post; }
        }
        steps_differences += std::memcmp((const char*)lifted.data() + kSteps, (const char*)native.data() + kSteps,
                                         sizeof c->steps) != 0;
        if (corrupt) c->ls[CORRUPT] ^= 0xFF;
    }
    const unsigned long long runs = motorstorm_vehicle_update_native_runs();
    std::printf("BINDING mode=%s corrupt=%d pairs=%d native_runs=%llu differences_after_drain=%llu "
                "trampoline_differences=%llu pre_state_differences=%llu pair_differences=%llu "
                "lifted_pair_mismatches=%llu steps_differences=%llu\n",
                mode, int(corrupt), int(paths.size()), (unsigned long long)runs, differences_post,
                trampoline_differences, pre_state_differences, pair_differences, lifted_pair_mismatches,
                steps_differences);
    const unsigned long long wanted = (!std::strcmp(mode, "native") || !std::strcmp(mode, "shadow")) && !expect_stopped ?
        paths.size() : 0;
    const bool ok = !paths.empty() && !differences_post && !trampoline_differences && !pre_state_differences &&
                    !pair_differences && !lifted_pair_mismatches && runs == wanted;
    if (differences_post)
        std::printf("   first difference after the drain: context byte %zu\n", first_post);
    if (!ok) std::printf("CHECK FAILED: binding mode %s corrupt %d stopped %d native runs %llu, expected %llu\n",
                         mode, int(corrupt), int(expect_stopped), runs, wanted);
    return ok ? 0 : 1;
}
