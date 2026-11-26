// Bound entries of the random generator of SPU image 213 (jobmod_556b30b5e654_e12e20).
// scripts/native_game_binding.py renames the lifted functions 0x170D0 (run) and 0x17248
// (init) to game_original_... and defines their symbols as wrappers of the entries here.
// One native execution is one call of the original code: it leaves the generator state, the
// seed and r2 to r11 as the lifted code leaves them, and it returns to r0.
// Mode 0 or an unsupported state calls the renamed original.
#include "particle_bind.h"
#include "particle_random.h"

extern "C" {
void game_original_particle_random_run(spu_context*);   // lifted 0x170D0
void game_original_particle_random_init(spu_context*);  // lifted 0x17248
int game_particle_random_code_matches(const spu_context*);
int game_particle_random_init_code_matches(const spu_context*);
void motorstorm_particle_random_run(spu_context* ctx);
void motorstorm_particle_random_init(spu_context* ctx);
void motorstorm_particle_random_counts(MotorstormParticleBindCounts* out);
}

namespace {
using namespace motorstorm_particle_bind;
constexpr const char* OPTION = "MS_NATIVE_PARTICLE_RANDOM";
std::atomic<unsigned long long> calls{0}, compared{0}, fallbacks{0};

// SPU_RET returns to r0 as the lifted function does. The entry functions pass the two addresses
// of the header, so the kernel knows each address.
void native_step(spu_context* ctx, uint32_t address) {
    if (!motorstorm_particle_random_call(ctx->ls, reinterpret_cast<uint32_t*>(ctx->gpr), address)) {
        std::fputs("NATIVE_PARTICLE_RANDOM_ERROR unknown generator entry\n", stderr);
        std::abort();
    }
    SPU_RET(ctx);
}

// The kernel runs on one copy of the caller, the lifted original on another copy. The local
// store and all registers must be equal. A difference stops the process.
bool compare(spu_context* ctx, uint32_t address, Function original) {
    Copies& pair = copies();
    if (!snapshot(ctx, pair)) return false;
    const uint32_t ret = ctx->gpr[0]._u32[0];
    native_step(&pair.candidate, address);
    if (!run_lifted(&pair.reference, original, ret)) return false;
    same_bytes("RANDOM", pair.reference.ls, pair.candidate.ls, sizeof ctx->ls_store, 0);
    for (unsigned r = 0; r < 128; ++r)
        for (unsigned lane = 0; lane < 4; ++lane)
            same_word("RANDOM", r, lane, pair.reference.gpr[r]._u32[lane], pair.candidate.gpr[r]._u32[lane]);
    if (pair.reference.pc != pair.candidate.pc)
        mismatch("RANDOM", "pc", 0, pair.reference.pc, pair.candidate.pc);
    ++compared;
    return true;
}

void entry(spu_context* ctx, uint32_t address, Function original, int (*matches)(const spu_context*)) try {
    const Config& config = motorstorm_particle_bind::config(OPTION);
    if (config.mode == Mode::reference) { original(ctx); return; }
    const char* reason = admission(config, ctx, matches);
    if (!reason && config.mode == Mode::shadow && !compare(ctx, address, original)) reason = "shadow state changed";
    if (reason) {
        const auto count = ++fallbacks;
        if (count == 1 || count % 4096 == 0)
            std::fprintf(stderr, "[native-particle-random] fallbacks=%llu reason=%s\n",
                         static_cast<unsigned long long>(count), reason);
        original(ctx);
        return;
    }
    // Shadow comparisons use private copies. The live caller keeps the state of the original.
    if (config.mode == Mode::shadow) original(ctx);
    else native_step(ctx, address);
    const auto count = ++calls;
    if (count == 1 || count % 4096 == 0)
        std::fprintf(stderr, "[native-particle-random] calls=%llu compared=%llu\n",
                     static_cast<unsigned long long>(count),
                     static_cast<unsigned long long>(config.mode == Mode::shadow ? count : compared.load()));
} catch (...) {
    std::fputs("NATIVE_PARTICLE_RANDOM_ERROR exception in the native entry\n", stderr);
    std::abort();
}
struct Startup {
    Startup() {
        const Config& config = motorstorm_particle_bind::config(OPTION);
        std::fprintf(stderr, "[native-particle-random] mode=%s\n", config.text ? config.text : "0");
    }
} startup;
}  // namespace

extern "C" void motorstorm_particle_random_run(spu_context* ctx) {
    entry(ctx, MOTORSTORM_RANDOM_ENTRY_RUN, game_original_particle_random_run, game_particle_random_code_matches);
}
extern "C" void motorstorm_particle_random_init(spu_context* ctx) {
    entry(ctx, MOTORSTORM_RANDOM_ENTRY_INIT, game_original_particle_random_init, game_particle_random_init_code_matches);
}
extern "C" void motorstorm_particle_random_counts(MotorstormParticleBindCounts* out) {
    out->native_calls = calls.load();
    out->compared = compared.load();
    out->fallbacks = fallbacks.load();
}
