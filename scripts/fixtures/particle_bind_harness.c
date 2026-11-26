/* Runs the bound entries of SPU image 213 against the lifted code of the generated unit.
   The harness links with the bound translation unit that scripts/native_game_binding.py makes
   from the generated unit jobmod_556b30b5e654_e12e20.

   pairs <dump> <pairs.bin>
       Every recorded call state of the generator runs through the bound symbol in mode 0 and
       in mode 1, with the lifted call site form and with the function pointer form. Mode 0
       must equal the recorded exit state, and mode 1 must equal mode 0: all registers, the
       generator bytes, the seed and the return address.
   collision <dump>...
       Particle batches run through the lifted function 0xA700 and the bound loop symbol
       0xA87C, in mode 0 and in mode 1, from equal states. The whole local store and all
       registers must be equal after the return. One case starts at a loop re-entry.
   job <dump> --seed X --random M --collision M --final P
       A dumped job runs as the game runs it: lifted code, the interpreter for the rest.
   bench <dump>... --passes N --pairs <job>:<file>...
       Lifted against native. The sides alternate each pass.
*/
#include <setjmp.h>
#include "particle_random_replay.c"
/* The engine has its own main function and a function capture. This harness defines both. */
#undef main
#define capture bind_capture
#include "particle_box_collision.h"

extern void jobmod_556b30b5e654_e12e20_spu_recomp_register(void);
extern void jobmod_556b30b5e654_e12e20_spu_func_0000A700(spu_context*);
extern void jobmod_556b30b5e654_e12e20_spu_func_0000A87C(spu_context*); /* bound symbol */
extern void jobmod_556b30b5e654_e12e20_spu_func_000170D0(spu_context*); /* bound symbol */
extern void jobmod_556b30b5e654_e12e20_spu_func_00017248(spu_context*); /* bound symbol */
extern void game_original_particle_collision_loop(spu_context*);
typedef struct { unsigned long long native_calls, compared, fallbacks; } BindCounts;
extern void motorstorm_particle_random_counts(BindCounts*);
extern void motorstorm_particle_collision_counts(BindCounts*);

/* ---- mode switch of the fixtures, and the channel model for lifted code ---- */
static const char* mode_text[2] = {"0", "0"};
static unsigned generation;
const char* motorstorm_particle_fixture_option(const char* name) {
    if (!strcmp(name, "MS_NATIVE_PARTICLE_RANDOM")) return mode_text[0];
    if (!strcmp(name, "MS_NATIVE_PARTICLE_COLLISIONS")) return mode_text[1];
    return getenv(name);
}
unsigned motorstorm_particle_fixture_generation(void) { return generation; }
static void set_mode(int port, const char* text) {
    mode_text[port] = text;
    ++generation;
}
/* The lifted code keeps the address of its last transfer in ctx->pc, so the address does not
   identify the seed read. With a seed, every decrementer read returns the seed. The other reads
   do not change the local store outside the allowed set. */
static uint32_t model_pc(const spu_context* c, uint32_t channel) {
    const uint32_t pc = c->pc & 0x3ffff;
    if (channel == SPU_RdDec && seed_set) return 0x1695c;
    return pc;
}
void harness_wrch(spu_context* c, uint32_t channel, u128 value) {
    if (c != &ctx) fail("channel write on a copy", c->pc);
    const uint32_t saved = c->pc;
    wrch_value(channel, spu_preferred_u32(&value), model_pc(c, channel));
    c->pc = saved;
}
u128 harness_rdch(spu_context* c, uint32_t channel) {
    if (c != &ctx) fail("channel read on a copy", c->pc);
    const uint32_t saved = c->pc;
    const uint32_t value = rdch_value(channel, model_pc(c, channel));
    c->pc = saved;
    return spu_make_preferred_u32(value);
}
uint32_t harness_rchcnt(spu_context* c, uint32_t channel) {
    if (c != &ctx) fail("channel count on a copy", c->pc);
    return rchcnt_value(channel, model_pc(c, channel));
}
void harness_stop(spu_context* c) { ++stop_n; }

static void finish_job(spu_context* c) {
    c->status = SPU_STATUS_STOPPED_BY_STOP;
    spu_halt(c);
}
static void runtime_ready(void) {
    spu_context_init(&ctx, 0);
    spu_begin_image(213);
    jobmod_556b30b5e654_e12e20_spu_recomp_register();
    spu_register_function(0x3098, finish_job);
}
static void ready(void) {
    ctx.status = SPU_STATUS_RUNNING;
    ctx.irq_saved = 0;
    ctx.list_stall_mask = 0;
    ctx.int_enable = 1;
    ctx.event_mask = 2;
    ctx.event_status = 0;
    ctx.host_depth = 0;
    ctx.resv_valid = 0;
    ctx.image_id = 213;
    g_spu_trampoline_fn = 0;
}
static long long now_ns(void) {
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    return (long long)(t.QuadPart * 1000000000ll / freq.QuadPart);
}

/* ---- the generator ---- */
typedef struct { uint32_t gpr[512], pc; uint8_t state[160], seed[16]; } GenResult;
static GenResult gen_a, gen_b;
static void gen_capture(GenResult* r) {
    memcpy(r->gpr, ctx.gpr, sizeof r->gpr);
    r->pc = ctx.pc;
    memcpy(r->state, ctx.ls + 0x17dd0, 160);
    memcpy(r->seed, ctx.ls + 0x174a0, 16);
}
static const char* gen_differs(const GenResult* a, const GenResult* b) {
    if (memcmp(a->gpr, b->gpr, sizeof a->gpr)) return "registers";
    if (memcmp(a->state, b->state, 160)) return "generator state";
    if (memcmp(a->seed, b->seed, 16)) return "seed";
    if (a->pc != b->pc) return "return address";
    return 0;
}
static void gen_restore(const Pair* p) {
    memcpy(ctx.gpr, p->gpr, sizeof ctx.gpr);
    memcpy(ctx.ls + 0x17dd0, p->state, 160);
    memcpy(ctx.ls + 0x174a0, p->seed, 16);
    ready();
}
static void gen_load(const Pair* p, const uint8_t* base) {
    memcpy(ctx.ls, base, 0x40000);
    gen_restore(p);
}
/* An entry returns to its caller, or it leaves a transfer to the lifted code of its extent. */
static void drain_after(uint32_t ret, uint32_t begin, uint32_t end) {
    void (*next)(spu_context*) = g_spu_trampoline_fn;
    if (ctx.pc != ret && !(next && next != spu_indirect_branch && ctx.pc >= begin && ctx.pc < end))
        fail("entry left a wrong return state", ctx.pc);
    spu_drain_call(&ctx, ret);
}
/* The lifted call site of brsl and brasl. */
static void gen_call_site(void (*symbol)(spu_context*)) {
    const uint32_t ret = ctx.gpr[0]._u32[0];
    ctx.host_depth++;
    symbol(&ctx);
    drain_after(ret, 0x170d0, 0x1725c);
    ctx.host_depth--;
}
/* The lifted call site of bisl: the resolver finds the function. */
static void gen_call_pointer(uint32_t target) {
    const uint32_t ret = ctx.gpr[0]._u32[0];
    ctx.host_depth++;
    ctx.drain_ret_pc = ret;
    ctx.pc = target;
    g_spu_trampoline_fn = spu_indirect_branch;
    spu_indirect_branch(&ctx);
    drain_after(ret, 0x170d0, 0x1725c);
    ctx.host_depth--;
}
static void (*bound_symbol(uint32_t entry))(spu_context*) {
    if (entry == 0x170d0) return jobmod_556b30b5e654_e12e20_spu_func_000170D0;
    if (entry == 0x17248) return jobmod_556b30b5e654_e12e20_spu_func_00017248;
    fail("not a generator entry", entry);
    return 0;
}
static Pair* read_pairs(const char* path, size_t* count) {
    FILE* f = fopen(path, "rb");
    if (!f) fail("pairs open", 0);
    fseek(f, 0, SEEK_END);
    const long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (size <= 0 || size % sizeof(Pair)) fail("pairs size", (uint32_t)size);
    Pair* pairs = (Pair*)malloc((size_t)size);
    if (!pairs || fread(pairs, (size_t)size, 1, f) != 1) fail("pairs read", 0);
    fclose(f);
    *count = (size_t)size / sizeof(Pair);
    return pairs;
}
/* Prints the words of one call that differ from the recorded exit state. */
static void gen_report(unsigned index, uint32_t entry, int form, const GenResult* a, const GenResult* b,
                       const GenResult* expected) {
    unsigned shown = 0, words = 0, w;
    printf("DIFF pair %u entry %05X form %d\n", index, entry, form);
    for (w = 0; w < 512; ++w) {
        const int differs = a->gpr[w] != expected->gpr[w] || b->gpr[w] != expected->gpr[w];
        words += differs;
        if (differs && shown++ < 6)
            printf("  r%u.%u lifted %08X native %08X recorded %08X\n", w >> 2, w & 3, a->gpr[w], b->gpr[w],
                   expected->gpr[w]);
    }
    GenResult lifted = *a, native = *b; /* the registers are reported above; compare the rest */
    memcpy(lifted.gpr, expected->gpr, sizeof lifted.gpr);
    memcpy(native.gpr, expected->gpr, sizeof native.gpr);
    printf("  differing words %u; lifted %s, native %s\n", words, gen_differs(&lifted, expected) ? "differs" : "equal",
           gen_differs(&native, expected) ? "differs" : "equal");
}
static int pairs_command(int argc, char** argv) {
    FIXTURE_CHECK(argc == 4);
    uint8_t* data; size_t size;
    load_dump(argv[2], &data, &size);
    size_t n;
    Pair* pairs = read_pairs(argv[3], &n);
    runtime_ready();
    unsigned calls = 0, total = 0, lifted_equal = 0, native_equal = 0, differences = 0;
    for (size_t i = 0; i + 1 < n; ++i) {
        const Pair* first = &pairs[i], *second = &pairs[i + 1];
        if (first->kind != 0 || second->kind != 1 || first->entry != second->entry) fail("pairs order", (uint32_t)i);
        GenResult expected;
        memcpy(expected.gpr, second->gpr, sizeof expected.gpr);
        memcpy(expected.state, second->state, 160);
        memcpy(expected.seed, second->seed, 16);
        /* The engine writes the entry record before the call instruction sets r0. The entry leaves
           r0 as it finds it and returns to that address. */
        expected.gpr[0] = first->gpr[0];
        expected.pc = first->gpr[0];
        for (int form = 0; form < 2; ++form) {
            gen_load(first, entry_ls);
            set_mode(0, "0");
            if (form) gen_call_pointer(first->entry); else gen_call_site(bound_symbol(first->entry));
            if (g_spu_trampoline_fn) fail("lifted call left a transfer", ctx.pc);
            gen_capture(&gen_a);
            gen_load(first, entry_ls);
            set_mode(0, "1");
            if (form) gen_call_pointer(first->entry); else gen_call_site(bound_symbol(first->entry));
            if (g_spu_trampoline_fn) fail("native call left a transfer", ctx.pc);
            gen_capture(&gen_b);
            ++total;
            if (!gen_differs(&gen_a, &expected)) ++lifted_equal;
            if (!gen_differs(&gen_b, &expected)) ++native_equal;
            const char* a = gen_differs(&gen_a, &expected), *b = gen_differs(&gen_b, &expected);
            if (a || b) {
                if (differences < 4) gen_report((unsigned)i, first->entry, form, &gen_a, &gen_b, &expected);
                ++differences;
            }
        }
        ++i; /* the exit record belongs to this call */
        ++calls;
    }
    BindCounts counts;
    motorstorm_particle_random_counts(&counts);
    /* pairs counts the recorded calls. Each call runs in the call-site form and in the pointer form. */
    printf("RANDOM pairs=%u lifted_equal=%u native_equal=%u differences=%u native_calls=%llu\n", calls, lifted_equal,
           native_equal, differences, counts.native_calls);
    return differences != 0 || counts.native_calls != total || lifted_equal != total || native_equal != total;
}

/* ---- the collision batch ---- */
#define HEADER 0x24000
#define SHAPE 0x20000
#define RECORDS 0x28000
#define EVENTS 0x38000
#define STACK 0x3e000
#define MAX_JOBS 24
#define SHAPES 4
#define PROBES 64
#define ADMITTED 6

typedef struct { uint32_t gpr[512], pc; uint8_t ls[0x40000]; } State;
typedef struct { uint32_t count, used, capacity; int remove, inactive, nan; } Variant;
/* The first ADMITTED variants run natively. The last two make the native entry decline, so
   the lifted loop runs and re-enters the bound symbol. */
static const Variant variants[] = {
    {1, 0, 1024, 0, 0, 0}, {8, 3, 1024, 0, 0, 0}, {64, 100, 1024, 1, 0, 0}, {256, 64, 64, 1, 0, 0},
    {16, 5, 1024, 0, 1, 0}, {32, 31, 32, 1, 0, 0}, {257, 0, 1024, 1, 0, 0}, {8, 0, 1024, 0, 0, 1},
};
static State state_a, state_b, state_start;
static spu_context probe;
static MotorstormCollisionParticle particles[PROBES];
static uint32_t random_word, best[SHAPES][16], best_contacts[SHAPES];
static unsigned best_n;
static uint8_t job_base[MAX_JOBS][0x40000];
static unsigned job_n;
static const uint8_t* cur_base;
static const uint32_t* cur_rows;
static Variant cur_variant;

static float next_float(float lo, float hi) {
    random_word = random_word * 1664525u + 1013904223u;
    return lo + (hi - lo) * (float)(random_word >> 8) * (1.0f / 16777216.0f);
}
static uint32_t bits_of(float value) { uint32_t w; memcpy(&w, &value, 4); return w; }
static void put32(spu_context* c, uint32_t address, uint32_t value) {
    uint8_t* p = c->ls + address;
    p[0] = (uint8_t)(value >> 24); p[1] = (uint8_t)(value >> 16); p[2] = (uint8_t)(value >> 8); p[3] = (uint8_t)value;
}
/* The shape holds a 4x4 rigid transform in rows at +0x10 (X axis), +0x20 (Y axis), +0x30 (Z axis) and
   +0x40 (translation). The lifted prologue builds the inverse: columns 0 to 2 are the axes and column 3 is
   -(axis . translation) with W = 1. */
static void write_shape(spu_context* c, const uint32_t* matrix) {
    unsigned i;
    for (i = 0; i < 16; ++i) put32(c, SHAPE + 0x10 + 4 * i, matrix[i]);
    for (i = 0; i < 4; ++i) {
        put32(c, SHAPE + 80 + 4 * i, i < 3 ? 0x3f800000u : 0); /* half extent (1, 1, 1) */
        put32(c, SHAPE + 96 + 4 * i, 0);                       /* motion of the box */
    }
}
static void write_record(spu_context* c, uint32_t index, const MotorstormCollisionParticle* p) {
    unsigned i;
    for (i = 0; i < 4; ++i) {
        put32(c, RECORDS + index * 128 + 4 * i, p->position.component[i]);
        put32(c, RECORDS + index * 128 + 48 + 4 * i, p->motion.component[i]);
    }
    put32(c, RECORDS + index * 128 + 100, p->enabled);
}
static void setup(const uint8_t* base, const uint32_t* rows, const Variant* v) {
    uint32_t i;
    unsigned r, lane;
    memcpy(ctx.ls, base, 0x40000);
    write_shape(&ctx, rows);
    put32(&ctx, SHAPE + 112, 0x1234abcdu);
    put32(&ctx, SHAPE + 116, v->remove ? 1u : 0u);
    put32(&ctx, HEADER + 4, RECORDS);
    put32(&ctx, HEADER + 8, v->count);
    put32(&ctx, HEADER + 12, 256);
    put32(&ctx, HEADER + 684, v->used);
    put32(&ctx, HEADER + 688, v->capacity);
    put32(&ctx, HEADER + 692, EVENTS);
    put32(&ctx, HEADER + 1780, 0x40800000u); /* step 4.0 */
    for (i = 0; i < v->capacity * 16; i += 4) put32(&ctx, EVENTS + i, 0x50000000u + i);
    for (i = 0; i < v->count; ++i) {
        MotorstormCollisionParticle p = particles[i % PROBES];
        if (v->inactive && (i & 1)) p.enabled = 0;
        write_record(&ctx, i, &p);
    }
    if (v->nan) put32(&ctx, RECORDS, 0x7fc00000u);
    for (r = 0; r < 128; ++r)
        for (lane = 0; lane < 4; ++lane) ctx.gpr[r]._u32[lane] = 0xd1000000u + r * 16 + lane;
    ctx.gpr[0] = spu_splat_u32(0x12188);
    ctx.gpr[1] = spu_splat_u32(STACK);
    ctx.gpr[3] = spu_splat_u32(HEADER);
    ctx.gpr[4] = spu_splat_u32(SHAPE);
    ctx.pc = 0xa700;
    ready();
}
static void prepare_case(void) { setup(cur_base, cur_rows, &cur_variant); }
/* The lifted call site of bisl with target 0xA700. */
static void run_batch(void) {
    ctx.host_depth++;
    ctx.drain_ret_pc = 0x12188;
    ctx.pc = 0xa700;
    g_spu_trampoline_fn = spu_indirect_branch;
    spu_indirect_branch(&ctx);
    drain_after(0x12188, 0xa700, 0xabec);
    ctx.host_depth--;
}
static void capture(State* s) {
    memcpy(s->gpr, ctx.gpr, sizeof s->gpr);
    s->pc = ctx.pc;
    memcpy(s->ls, ctx.ls, 0x40000);
}
/* The lifted batch writes the caller-saved registers r2 to r20 as scratch (disassembly 0xA700
   to 0xAC50). The caller at 0x12188 writes each register before it reads it. So their values at
   the return are not defined. Every other register, the return address and the local store
   must be equal. */
static int scratch(unsigned r) { return r >= 2 && r <= 20; }
static const char* state_differs(const State* a, const State* b, unsigned* r, unsigned* lane, uint32_t* x, uint32_t* y) {
    unsigned i;
    uint32_t address;
    *r = *lane = 0;
    if (a->pc != b->pc) { *x = a->pc; *y = b->pc; return "return address"; }
    for (i = 0; i < 512; ++i)
        if (!scratch(i / 4) && a->gpr[i] != b->gpr[i]) { *r = i / 4; *lane = i % 4; *x = a->gpr[i]; *y = b->gpr[i]; return "register"; }
    for (address = 0; address < 0x40000; ++address)
        if (a->ls[address] != b->ls[address]) { *x = address; *y = a->ls[address] | (uint32_t)b->ls[address] << 8; return "local store byte"; }
    return 0;
}
static int compare(const char* label, unsigned index) {
    unsigned r, lane;
    uint32_t x = 0, y = 0;
    const char* what = state_differs(&state_a, &state_b, &r, &lane, &x, &y);
    if (!what) return 0;
    printf("DIFF %s %u: %s at r%u.%u: lifted %08X native %08X\n", label, index, what, r, lane, x, y);
    return 1;
}
/* Runs the prepared state in mode 0 and in mode 1 from equal states. */
static int both_modes(void (*prepare)(void), const char* label, unsigned index) {
    prepare();
    set_mode(1, "0");
    run_batch();
    if (g_spu_trampoline_fn) fail("lifted batch left a transfer", ctx.pc);
    capture(&state_a);
    prepare();
    set_mode(1, "1");
    run_batch();
    if (g_spu_trampoline_fn) fail("native batch left a transfer", ctx.pc);
    capture(&state_b);
    return compare(label, index);
}
/* The lifted prologue and the lifted records of one iteration. The loop then re-enters 0xA87C
   with r85 = 1. The bound symbol is pending in the transfer register. */
static void prepare_reentry(void) {
    unsigned steps;
    prepare_case();
    ctx.host_depth = 1;
    jobmod_556b30b5e654_e12e20_spu_func_0000A700(&ctx);
    g_spu_trampoline_fn = 0;
    game_original_particle_collision_loop(&ctx);
    for (steps = 0; g_spu_trampoline_fn != jobmod_556b30b5e654_e12e20_spu_func_0000A87C; ++steps) {
        void (*next)(spu_context*) = g_spu_trampoline_fn;
        if (!next || steps == (1u << 20) || next == spu_indirect_branch) fail("no loop re-entry", ctx.pc);
        g_spu_trampoline_fn = 0;
        next(&ctx);
    }
    ctx.host_depth = 0;
    if (ctx.gpr[85]._u32[0] == 0) fail("re-entry index", ctx.pc);
}
static int reentry_case(void) {
    prepare_reentry();
    set_mode(1, "1");
    spu_drain_call(&ctx, 0x12188); /* the drain loop calls the bound symbol at the re-entry */
    if (g_spu_trampoline_fn) fail("native re-entry left a transfer", ctx.pc);
    capture(&state_a);
    prepare_reentry();
    set_mode(1, "0");
    spu_drain_call(&ctx, 0x12188);
    capture(&state_b);
    return compare("re-entry", 0);
}
/* The lifted prologue computes the box registers of a shape. The kernel reports how many of
   the probe particles make contact. */
static unsigned probe_shape(const uint32_t* rows, MotorstormCollisionBox* box) {
    unsigned i, lane;
    MotorstormCollisionResult result;
    memcpy(probe.ls, job_base[0], 0x40000);
    write_shape(&probe, rows);
    put32(&probe, HEADER + 4, RECORDS);
    put32(&probe, HEADER + 8, 1);
    put32(&probe, HEADER + 12, 256);
    memset(probe.gpr, 0, sizeof probe.gpr);
    probe.gpr[0] = spu_splat_u32(0x12188);
    probe.gpr[1] = spu_splat_u32(STACK);
    probe.gpr[3] = spu_splat_u32(HEADER);
    probe.gpr[4] = spu_splat_u32(SHAPE);
    probe.status = SPU_STATUS_RUNNING;
    probe.host_depth = 1;
    g_spu_trampoline_fn = 0;
    jobmod_556b30b5e654_e12e20_spu_func_0000A700(&probe);
    g_spu_trampoline_fn = 0;
    for (i = 0; i < 4; ++i)
        for (lane = 0; lane < 4; ++lane) box->columns[i].component[lane] = probe.gpr[91 - i]._u32[lane];
    box->half_extent.component[0] = box->half_extent.component[1] = box->half_extent.component[2] = 0x3f800000u;
    box->half_extent.component[3] = 0;
    for (i = 0; i < 4; ++i) box->motion.component[i] = 0;
    box->step = 0x40800000u;
    box->contact_metadata = 0x1234abcdu;
    return motorstorm_particle_box_contacts(particles, PROBES, box, &result) ? result.contacts : 0;
}
/* Four rigid transforms: identity, a 90 degree rotation about Z with a translation, a rotation of about
   53 degrees about Z with a translation, and a 90 degree rotation about X with a translation. Each must make
   contacts with the probe particles. */
static void select_shapes(void) {
    static const float matrix[SHAPES][16] = {
        {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1},
        {0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 0.5f, -0.25f, 0.125f, 1},
        {0.6f, 0.8f, 0, 0, -0.8f, 0.6f, 0, 0, 0, 0, 1, 0, -0.75f, 0.5f, 0.25f, 1},
        {1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0.5f, 0.25f, -0.75f, 1},
    };
    unsigned k, w;
    random_word = 0x12345;
    for (k = 0; k < PROBES; ++k) {
        for (w = 0; w < 3; ++w) {
            particles[k].position.component[w] = bits_of(next_float(-2.0f, 2.0f));
            particles[k].motion.component[w] = bits_of(next_float(-0.5f, 0.5f));
        }
        particles[k].position.component[3] = 0;
        particles[k].motion.component[3] = 0;
        particles[k].enabled = 1;
    }
    for (k = 0; k < SHAPES; ++k) {
        MotorstormCollisionBox box;
        unsigned i;
        for (i = 0; i < 16; ++i) best[k][i] = bits_of(matrix[k][i]);
        best_contacts[k] = probe_shape(best[k], &box);
        printf("shape %u: contacts %u of %u; columns r91 %08X %08X %08X, r90 %08X %08X %08X, r89 %08X %08X %08X, "
               "r88 %08X %08X %08X\n",
               k, best_contacts[k], PROBES, box.columns[0].component[0], box.columns[0].component[1], box.columns[0].component[2],
               box.columns[1].component[0], box.columns[1].component[1], box.columns[1].component[2],
               box.columns[2].component[0], box.columns[2].component[1], box.columns[2].component[2],
               box.columns[3].component[0], box.columns[3].component[1], box.columns[3].component[2]);
        if (best_contacts[k] < 4) fail("a rigid shape makes too few contacts", k);
    }
    best_n = SHAPES;
}
static void load_bases(int argc, char** argv) {
    int i;
    FIXTURE_CHECK(argc - 2 <= MAX_JOBS);
    for (i = 2; i < argc; ++i) {
        uint8_t* data; size_t size;
        load_dump(argv[i], &data, &size);
        memcpy(job_base[job_n++], entry_ls, 0x40000);
    }
    runtime_ready();
    select_shapes();
    if (best_n != SHAPES) fail("a rigid shape is missing", 0);
}
/* Prints the native calls and the fallbacks of one case. */
static void counts_line(const char* label, const BindCounts* before) {
    BindCounts now;
    motorstorm_particle_collision_counts(&now);
    printf("case %s: native +=%llu fallbacks +=%llu\n", label, now.native_calls - before->native_calls,
           now.fallbacks - before->fallbacks);
}
static int collision_command(int argc, char** argv) {
    unsigned s, v, cases = 0, differences = 0;
    char label[64];
    load_bases(argc, argv);
    for (s = 0; s < best_n; ++s)
        for (v = 0; v < ADMITTED; ++v) {
            BindCounts before;
            motorstorm_particle_collision_counts(&before);
            cur_base = job_base[cases % job_n];
            cur_rows = best[s];
            cur_variant = variants[v];
            snprintf(label, sizeof label, "shape %u variant %u", s, v);
            differences += both_modes(prepare_case, label, cases);
            ++cases;
            counts_line(label, &before);
        }
    for (v = ADMITTED; v < sizeof variants / sizeof variants[0]; ++v) {
        BindCounts before;
        motorstorm_particle_collision_counts(&before);
        cur_base = job_base[cases % job_n];
        cur_rows = best[0];
        cur_variant = variants[v];
        snprintf(label, sizeof label, "decline %u", v);
        differences += both_modes(prepare_case, label, cases);
        ++cases;
        counts_line(label, &before);
    }
    cur_base = job_base[0];
    cur_rows = best[0];
    cur_variant = variants[1];
    {
        BindCounts before;
        motorstorm_particle_collision_counts(&before);
        differences += reentry_case();
        ++cases;
        counts_line("re-entry", &before);
    }
    {
        BindCounts counts;
        motorstorm_particle_collision_counts(&counts);
        printf("COLLISION cases=%u differences=%u native_calls=%llu fallbacks=%llu shapes=%u jobs=%u\n", cases, differences,
               counts.native_calls, counts.fallbacks, best_n, job_n);
        return differences != 0 || counts.native_calls != ADMITTED * best_n || counts.fallbacks < 3;
    }
}

/* ---- a dumped job with lifted code ---- */
static int job_command(int argc, char** argv) {
    uint32_t seed = 0;
    int i, seed_given = 0, failed_run = 0;
    unsigned lane, outside = 0, first_outside = 0;
    const char *random = "0", *collision = "0", *final = 0;
    uint8_t* data; size_t size;
    BindCounts r, c;
    FIXTURE_CHECK(argc >= 3);
    for (i = 3; i < argc; ++i) {
        if (!strcmp(argv[i], "--seed") && i + 1 < argc) { seed = (uint32_t)strtoul(argv[++i], 0, 16); seed_given = 1; }
        else if (!strcmp(argv[i], "--random") && i + 1 < argc) random = argv[++i];
        else if (!strcmp(argv[i], "--collision") && i + 1 < argc) collision = argv[++i];
        else if (!strcmp(argv[i], "--final") && i + 1 < argc) final = argv[++i];
        else { fprintf(stderr, "bad argument %s\n", argv[i]); return 2; }
    }
    load_dump(argv[2], &data, &size);
    runtime_ready();
    ctx.pc = head.entry;
    memcpy(ctx.ls, entry_ls, 0x40000);
    memset(ctx.gpr, 0, sizeof ctx.gpr);
    for (lane = 0; lane < 4; ++lane) { ctx.gpr[3]._u32[lane] = head.r3[lane]; ctx.gpr[4]._u32[lane] = head.r4[lane]; }
    ctx.gpr[0] = spu_splat_u32(0x3098);
    ctx.gpr[1] = spu_splat_u32(0x3ffd0);
    ready();
    seed_value = seed;
    seed_set = seed_given;
    tag_status = atomic_stat = stall_stat = 0;
    memset(wr_other, 0, sizeof wr_other);
    memset(lines, 0, sizeof lines);
    dec_reads = put_diff_n = put_diff_bytes = stop_n = 0;
    set_mode(0, random);
    set_mode(1, collision);
    if (setjmp(fail_jmp)) failed_run = 1;
    else spu_run_with_halt(spu_indirect_branch, &ctx);
    motorstorm_particle_random_counts(&r);
    motorstorm_particle_collision_counts(&c);
    /* The dump exit local store is the state of the hardware at the stop address. The allowed set
       is the set of the old replay engine (scripts/fixtures/particle_random_replay.c). */
    {
        uint32_t address;
        for (address = 0; address < 0x40000 && exit_ls; ++address)
            if (ctx.ls[address] != exit_ls[address] && !(address >= 0x24000 && (address & 15) >= 4) &&
                !(address >= 0x80 && address < 0x180) && !(address >= 0x3ff40 && address < 0x3ff44) &&
                !(address >= 0x3fc90 && address < 0x3fc94) && !(address >= 0x14d0 && address < 0x14d4)) {
                if (!outside) first_outside = address;
                ++outside;
            }
    }
    printf("JOB seq=%u failed=%d dma=%d/%d put_diff=%u outside=%u first_outside=%05X final_pc=%05X random_calls=%llu "
           "random_fallbacks=%llu collision_calls=%llu\n", head.seq, failed_run, next_dma, dma_n, put_diff_n, outside,
           first_outside, ctx.pc, r.native_calls, r.fallbacks, c.native_calls);
    if (final) write_snapshot_file(final);
    /* A job can end before the dump records end: the dump holds the records of more than this run. */
    return failed_run || put_diff_n != 0 || outside != 0 || ctx.pc != 0x3098;
}

/* ---- lifted against native ---- */
#define MAX_RANGES 64
typedef struct { uint32_t begin, end; } Range;
static Range ranges[MAX_RANGES];
static unsigned range_n, ranges_exact;

/* The bytes that one batch changes. restore_start copies only these back. When the list is
   full, it copies the whole local store. */
static void find_ranges(void) {
    uint32_t address, end;
    range_n = 0;
    ranges_exact = 1;
    for (address = 0; address < 0x40000; ++address) {
        if (ctx.ls[address] == state_start.ls[address]) continue;
        end = address + 1;
        while (end < 0x40000 && ctx.ls[end] != state_start.ls[end]) ++end;
        if (range_n == MAX_RANGES) { ranges_exact = 0; return; }
        ranges[range_n].begin = address;
        ranges[range_n].end = end;
        ++range_n;
        address = end - 1;
    }
}
static void restore_start(void) {
    unsigned i;
    memcpy(ctx.gpr, state_start.gpr, sizeof ctx.gpr);
    ctx.pc = state_start.pc;
    if (!ranges_exact) memcpy(ctx.ls, state_start.ls, 0x40000);
    else for (i = 0; i < range_n; ++i) memcpy(ctx.ls + ranges[i].begin, state_start.ls + ranges[i].begin, ranges[i].end - ranges[i].begin);
    ready();
}
static void bench_collision(int passes) {
    unsigned s, v, cases = 0;
    int pass, side, iter, iters;
    for (s = 0; s < best_n; ++s)
        for (v = 0; v < ADMITTED; ++v) {
            const unsigned job = cases % job_n;
            cur_base = job_base[job];
            cur_rows = best[s];
            cur_variant = variants[v];
            prepare_case();
            capture(&state_start);
            set_mode(1, "1");
            run_batch();
            find_ranges();
            iters = 200000 / (int)(cur_variant.count + 8);
            if (iters < 50) iters = 50;
            for (pass = 1; pass <= passes; ++pass)
                for (side = 0; side < 2; ++side) {
                    const int native = (pass + side) % 2;
                    const long long t0 = now_ns();
                    set_mode(1, native ? "1" : "0");
                    for (iter = 0; iter < iters; ++iter) { restore_start(); run_batch(); }
                    printf("BENCH COLLISION case=%u job_index=%u count=%u pass=%d side=%s iterations=%d ns=%lld\n", cases, job,
                           cur_variant.count, pass, native ? "native" : "lifted", iters, now_ns() - t0);
                }
            ++cases;
        }
}
static void bench_random(int job, const char* path, int passes) {
    size_t n, i;
    int pass, side, iter, iters;
    Pair* pairs = read_pairs(path, &n);
    memcpy(ctx.ls, job_base[0], 0x40000);
    iters = (int)(20000 / (n / 2) + 1);
    for (pass = 1; pass <= passes; ++pass)
        for (side = 0; side < 2; ++side) {
            const int native = (pass + side) % 2;
            unsigned long long calls = 0;
            const long long t0 = now_ns();
            set_mode(0, native ? "1" : "0");
            for (iter = 0; iter < iters; ++iter)
                for (i = 0; i + 1 < n; i += 2) {
                    gen_restore(&pairs[i]);
                    gen_call_site(bound_symbol(pairs[i].entry));
                    ++calls;
                }
            printf("BENCH RANDOM job=%d pass=%d side=%s calls=%llu ns=%lld\n", job, pass, native ? "native" : "lifted", calls,
                   now_ns() - t0);
        }
    free(pairs);
}
static int bench_command(int argc, char** argv) {
    int passes = 0, i, bases = 0;
    for (i = 2; i < argc; ++i)
        if (!strcmp(argv[i], "--passes") && i + 1 < argc) { bases = i; break; }
    FIXTURE_CHECK(bases > 2);
    load_bases(bases, argv);
    passes = atoi(argv[bases + 1]);
    for (i = bases + 2; i < argc; ++i) {
        char* colon = strchr(argv[i], ':');
        FIXTURE_CHECK(colon && !strncmp(argv[i], "--pairs=", 8));
        *colon = 0;
        bench_random(atoi(argv[i] + 8), colon + 1, passes);
    }
    bench_collision(passes);
    return 0;
}

int main(int argc, char** argv) {
    _set_error_mode(_OUT_TO_STDERR);
    _set_abort_behavior(0, _WRITE_ABORT_MSG | _CALL_REPORTFAULT);
    FIXTURE_CHECK(argc >= 2);
    QueryPerformanceFrequency(&freq);
    total_steps_limit = 4000000000ull;
    probe.ls = probe.ls_store;
    if (setjmp(fail_jmp)) return 3;
    if (!strcmp(argv[1], "pairs")) return pairs_command(argc, argv);
    if (!strcmp(argv[1], "collision")) return collision_command(argc, argv);
    if (!strcmp(argv[1], "job")) return job_command(argc, argv);
    if (!strcmp(argv[1], "bench")) return bench_command(argc, argv);
    fprintf(stderr, "bad command %s\n", argv[1]);
    return 2;
}
