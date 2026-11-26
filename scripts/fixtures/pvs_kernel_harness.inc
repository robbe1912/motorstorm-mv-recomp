/* Harness of PvsKernel-5 (native kernel of the PVS job, SPU image 210).
   temp/pvskernel/k5_build.py composes the main of each engine from temp/pvs/p2_oracle_main.cpp
   (the replay engine of PvsPort-2) and includes this file after the definitions of that file.
   The names Dump, Dma, Engine, LS_SIZE, oracle_context, p2_entry and spu_run_with_halt come
   from it.

   K5_HOOKS 1: the lifted unit calls p5_enter, p5_call, p5_after and p5_ret. The hooks make the
                cost table (frames by host depth and return address, self time per block, call
                edges) and capture the pairs (entry state, exit state) of the kernel entries.
   K5_ADAPTER 1: the engine links pvs_kernel.c and pvs_kernel_adapter.cpp.

   A pair is the state of the lifted path when it dispatches an entry (A) and the state when the
   code of the entry has left (B): a return at the host depth of A, or a dispatch of lifted code
   that the kernel does not continue (a leaf with more than one exit). The kernel pass puts A into
   the context, calls the bound entry with mode native, and compares the context, the local store
   and the DMA records with B. */
#pragma once
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <memory>
#include <string>
#include <vector>
#include <intrin.h>
#include "pvs_kernel.h"
#include "spu_float_simd.h"

#ifndef K5_ADAPTER
#define K5_ADAPTER 0
#endif
#ifndef K5_HOOKS
#define K5_HOOKS 0
#endif

namespace k5 {

constexpr uint32_t kMask = 0x3ffffu;

inline uint64_t ticks() { return __rdtsc(); }

inline std::vector<uint32_t> parse_hex(const std::string& text) {
    std::vector<uint32_t> out;
    size_t p = 0;
    while (p < text.size()) {
        size_t q = text.find(',', p);
        if (q == std::string::npos) q = text.size();
        if (q > p) out.push_back((uint32_t)strtoul(text.substr(p, q - p).c_str(), nullptr, 16));
        p = q + 1;
    }
    return out;
}

struct Config {
    std::vector<uint32_t> marks, pair_entries;
    std::string tables, pairs_out, pairs_in;
    uint32_t pair_every = 1, pair_max = 2, passes = 7;
    bool capture = false; /* the lifted run captures pairs */
    int kernel = 0;       /* the kernel pass runs on each captured pair */
} cfg;

int pass = 0; /* 0: the lifted job runs; 1: a kernel pass or a bench run is in progress */
uint32_t seq = 0;

#if K5_HOOKS
struct Frame {
    uint32_t entry, cur, ret, h;
    uint64_t start, self, leaf, pm, bstart;
    uint32_t dma;
    int bchild, leaf_on;
};
struct Row {
    uint64_t n = 0, self = 0, incl = 0, leaf = 0, pm = 0, dma = 0;
};
std::vector<Frame> stack;
uint64_t last = 0, ms1000 = 0;
uint32_t jobs = 0, jobs_ok = 0;
std::map<uint64_t, Row> frames; /* key: entry | ret << 20 | h << 40 */
std::map<uint32_t, Row> fns;    /* dispatches and self time per block */
std::map<std::string, uint32_t> edges;

/* 1: the kernel holds the block. 2: lifted leaf with one exit (the kernel goes on after it).
   0: lifted code that ends the kernel at depth 0. */
extern const unsigned char k5_blocks[0x40000 / 4];

inline int block_kind(uint32_t a) {
    const uint32_t i = a >> 2;
    return i < 0x40000 / 4 ? k5_blocks[i] : 0;
}

inline bool is_mark(uint32_t a) { return std::find(cfg.marks.begin(), cfg.marks.end(), a) != cfg.marks.end(); }

inline void charge(uint64_t now) {
    if (stack.empty()) {
        last = now;
        return;
    }
    Frame& f = stack.back();
    if (f.leaf_on)
        f.leaf += now - last;
    else {
        f.self += now - last;
        fns[f.cur].self += now - last;
    }
    last = now;
}

inline void open(uint32_t a, uint32_t ret, uint32_t h, uint64_t now) {
    const int leaf = block_kind(a) != 1;
    stack.push_back(Frame{a, a, ret, h, now, 0, 0, 0, 0, 0, 0, leaf});
}

inline void close(uint64_t now) {
    const Frame f = stack.back();
    stack.pop_back();
    Row& row = frames[(uint64_t)f.entry | ((uint64_t)f.ret << 20) | ((uint64_t)f.h << 40)];
    ++row.n;
    row.incl += now - f.start;
    row.self += f.self;
    row.leaf += f.leaf;
    row.pm += f.pm;
    row.dma += f.dma;
    if (!stack.empty() && block_kind(f.entry) != 1) {
        Frame& p = stack.back(); /* a lifted leaf: its whole time is leaf time of the caller */
        p.leaf += now - f.start;
        p.dma += f.dma;
    }
}

inline void dma_note() {
    if (pass == 0 && !stack.empty()) ++stack.back().dma;
}
#endif /* K5_HOOKS */

struct Pair {
    uint32_t seq = 0, entry = 0, kind = 0, n = 0, h0 = 0, r0 = 0;
    spu_context a;              /* the entry state */
    std::vector<uint8_t> b;     /* the exit state, before the step of the lifted loop */
    std::vector<Dma> dma;       /* DMA records of the lifted path between A and B */
};
std::vector<std::unique_ptr<Pair>> pairs;
struct Cap {
    bool on = false;
    uint32_t seq = 0, entry = 0, h0 = 0, r0 = 0;
    size_t d0 = 0;
} cap;
std::map<uint64_t, uint32_t> hits; /* seq << 32 | entry: dispatches of the entry in the job */
uint64_t pair_total = 0;

#if K5_HOOKS
inline void pair_finish(uint32_t kind, uint32_t n, spu_context* ctx) {
    std::unique_ptr<Pair> p(new Pair);
    memcpy(&p->a, ctx, sizeof(spu_context));
    p->seq = cap.seq;
    p->entry = cap.entry;
    p->h0 = cap.h0;
    p->r0 = cap.r0;
    p->kind = kind;
    p->n = n;
    p->b.assign(reinterpret_cast<const uint8_t*>(ctx), reinterpret_cast<const uint8_t*>(ctx) + sizeof(spu_context));
    p->dma.assign(g.dma.begin() + cap.d0, g.dma.end());
    pairs.push_back(std::move(p));
    cap.on = false;
}

inline void pair_enter(spu_context* ctx, uint32_t a) {
        /* The lifted loop dispatched the function of the jump target. The trampoline is spent, so
           the form of the jump (plain or through spu_indirect_branch) is not visible here: kind 0
           accepts both. */
        pair_finish(0, 0, ctx);
        return;
    }
    if (cap.on || !cfg.capture || std::find(cfg.pair_entries.begin(), cfg.pair_entries.end(), a) == cfg.pair_entries.end()) return;
    uint32_t& count = hits[((uint64_t)seq << 32) | a];
    ++count;
    size_t mine = 0;
    for (const auto& p : pairs) mine += p->seq == seq;
    if (count % cfg.pair_every != 1 || mine >= cfg.pair_max) return;
    cap.on = true;
    cap.seq = seq;
    cap.entry = a;
    cap.h0 = ctx->host_depth;
    cap.r0 = ctx->drain_ret_pc & kMask;
    cap.d0 = g.dma.size();
}

inline void pair_ret(spu_context* ctx, uint32_t n) {
    if (cap.on && ctx->host_depth == cap.h0) pair_finish(MOTORSTORM_PVS_EXIT_RETURN, n, ctx);
}
#endif

inline void restore(spu_context* c, const Pair& p) {
    uint8_t* ls = c->ls;
    memcpy(c, &p.a, sizeof(spu_context));
    c->ls = ls;
    memcpy(ls, p.a.ls_store, LS_SIZE);
    g_spu_trampoline_fn = 0; /* the lifted loop spent the trampoline before it called the function */
}

struct Diff {
    size_t ctx_bytes = 0, ls_bytes = 0, dma_bad = 0;
    uint32_t kind = 0, bail = 0;
    uint64_t fallbacks = 0;
};

inline size_t count_diff(const uint8_t* a, const uint8_t* b, size_t n) {
    size_t k = 0;
    for (size_t i = 0; i < n; ++i) k += a[i] != b[i];
    return k;
}

/* The context without the pointer `ls` and without the counter `steps`. */
inline size_t context_diff(const spu_context& b, const spu_context& c) {
    const size_t ls = offsetof(spu_context, ls), st = offsetof(spu_context, steps);
    const auto* pb = reinterpret_cast<const uint8_t*>(&b);
    const auto* pc = reinterpret_cast<const uint8_t*>(&c);
    return count_diff(pb, pc, ls) + count_diff(pb + ls + sizeof(void*), pc + ls + sizeof(void*), st - ls - sizeof(void*)) +
           count_diff(pb + st + sizeof(uint32_t), pc + st + sizeof(uint32_t), sizeof(spu_context) - st - sizeof(uint32_t));
}

/* B after the step of the lifted loop at the exit. */
inline bool compare(const Pair& p, const spu_context* c, Diff& d) {
    static thread_local std::vector<uint8_t> room(sizeof(spu_context));
    spu_context& b = *reinterpret_cast<spu_context*>(room.data());
    memcpy(&b, p.b.data(), sizeof(spu_context));
    if (p.kind == MOTORSTORM_PVS_EXIT_RETURN) b.pc = b.gpr[p.n]._u32[0];
    d.ctx_bytes = context_diff(b, *c);
    d.ls_bytes = count_diff(b.ls_store, c->ls_store, LS_SIZE);
    d.dma_bad = p.dma.size() != g.dma.size() ? (p.dma.size() > g.dma.size() ? p.dma.size() - g.dma.size() : g.dma.size() - p.dma.size()) : 0;
    const size_t n = std::min(p.dma.size(), g.dma.size());
    for (size_t i = 0; i < n; ++i) {
        const Dma& x = p.dma[i];
        const Dma& y = g.dma[i];
        /* The guest memory changed after the lifted run: the bytes of a GET can differ. */
        const bool same = x.is_get == y.is_get && x.cmd == y.cmd && x.lsa == y.lsa && x.ea == y.ea && x.size == y.size &&
                          (x.is_get || x.bytes == y.bytes);
        if (!same) ++d.dma_bad;
    }
    const bool kind_ok = d.kind == p.kind || (p.kind == 0 && (d.kind == MOTORSTORM_PVS_EXIT_JUMP || d.kind == MOTORSTORM_PVS_EXIT_INDIRECT));
    return kind_ok && d.fallbacks == 0 && d.ctx_bytes == 0 && d.ls_bytes == 0 && d.dma_bad == 0;
}

inline bool write_pairs(const std::string& folder, uint32_t job) {
    char name[64];
    snprintf(name, sizeof name, "/pairs_%u.bin", job);
    FILE* f = fopen((folder + name).c_str(), "wb");
    if (!f) return false;
    for (const auto& p : pairs) {
        if (p->seq != job) continue;
        const uint32_t head[8] = {0x4b355052u, p->seq, p->entry, p->kind, p->h0, p->r0, p->n, (uint32_t)sizeof(spu_context)};
        if (fwrite(head, 1, sizeof head, f) != sizeof head || fwrite(&p->a, 1, sizeof(spu_context), f) != sizeof(spu_context)) break;
    }
    fclose(f);
    return true;
}

inline std::vector<std::unique_ptr<Pair>> read_pairs(const std::string& folder, uint32_t job) {
    std::vector<std::unique_ptr<Pair>> out;
    char name[64];
    snprintf(name, sizeof name, "/pairs_%u.bin", job);
    FILE* f = fopen((folder + name).c_str(), "rb");
    if (!f) return out;
    for (;;) {
        std::unique_ptr<Pair> p(new Pair);
        uint32_t head[8];
        if (fread(head, 1, sizeof head, f) != sizeof head || head[0] != 0x4b355052u || head[7] != sizeof(spu_context)) break;
        p->seq = head[1];
        p->entry = head[2];
        p->kind = head[3];
        p->h0 = head[4];
        p->r0 = head[5];
        p->n = head[6];
        if (fread(&p->a, 1, sizeof(spu_context), f) != sizeof(spu_context)) break;
        out.push_back(std::move(p));
    }
    fclose(f);
    return out;
}

/* The kernel pass of one pair: A into the context, then the bound entry with mode native. The
   wrapper returns when the kernel has left. */
inline bool kernel_pass(Pair& p, Diff& d) {
#if K5_ADAPTER
    spu_context* c = oracle_context();
    restore(c, p);
    g.dma.clear();
    g.in_span = false;
    void (*fn)(spu_context*) = spu_lifted_lookup(c, p.entry);
    if (!fn) {
        d.kind = 0xffffu;
        return false;
    }
    pass = 1;
    motorstorm_pvs_set_mode(MOTORSTORM_PVS_NATIVE);
    uint64_t c0[5], c1[5];
    motorstorm_pvs_counters(c0);
    fn(c);
    motorstorm_pvs_counters(c1);
    d.kind = motorstorm_pvs_last_exit(&d.bail);
    d.fallbacks = c1[3] - c0[3];
    if (g_spu_trampoline_fn) g_spu_trampoline_fn = 0; /* the lifted loop takes the function */
    pass = 0;
    return compare(p, c, d);
#else
    (void)p;
    (void)d;
    return false;
#endif
}

/* Called after the comparisons of one job. */
inline void job_end(uint32_t job, int ok, double ms) {
    seq = job;
#if K5_HOOKS
    if (!stack.empty()) {
        const uint64_t now = ticks();
        charge(now);
        while (!stack.empty()) close(now);
    }
    ++jobs;
    jobs_ok += ok != 0;
    ms1000 += (uint64_t)(ms * 1000.0);
    size_t good = 0, bad = 0;
    if (cfg.kernel)
        for (auto& p : pairs) {
            Diff d;
            const bool same = kernel_pass(*p, d);
            good += same;
            bad += !same;
            printf("K5 PAIR seq=%u entry=%05X kind=%u ok=%d kind_kernel=%u fallbacks=%llu bail=%05X ctx_bytes=%zu ls_bytes=%zu dma_bad=%zu ref_dma=%zu\n",
                   p->seq, p->entry, p->kind, same ? 1 : 0, d.kind, (unsigned long long)d.fallbacks, d.bail, d.ctx_bytes, d.ls_bytes,
                   d.dma_bad, p->dma.size());
        }
    pair_total += pairs.size();
    if (cfg.capture && !cfg.pairs_out.empty()) write_pairs(cfg.pairs_out, job);
    printf("K5 JOB seq=%u ok=%d pairs=%zu good=%zu bad=%zu ms=%.3f\n", job, ok, pairs.size(), good, bad, ms);
#else
    (void)ok;
    (void)ms;
#endif
    pairs.clear();
    hits.clear();
    cap.on = false;
}

inline void dump(const std::string& folder) {
#if K5_HOOKS
    const auto write = [&](const char* name, const auto& body) {
        const std::string path = folder + "/" + name;
        if (FILE* f = fopen(path.c_str(), "wb")) {
            body(f);
            fclose(f);
        }
    };
    write("frames.txt", [&](FILE* f) {
        for (const auto& [key, r] : frames)
            fprintf(f, "%05X %05X %u %llu %llu %llu %llu %llu %llu\n", (uint32_t)(key & 0xfffffu), (uint32_t)((key >> 20) & 0xfffffu),
                    (uint32_t)(key >> 40), (unsigned long long)r.n, (unsigned long long)r.incl, (unsigned long long)r.self,
                    (unsigned long long)r.leaf, (unsigned long long)r.pm, (unsigned long long)r.dma);
    });
    write("fn.txt", [&](FILE* f) {
        for (const auto& [a, r] : fns) fprintf(f, "%05X %llu %llu\n", a, (unsigned long long)r.n, (unsigned long long)r.self);
    });
    write("edges.txt", [&](FILE* f) {
        for (const auto& [k, n] : edges) fprintf(f, "%s %u\n", k.c_str(), n);
    });
    write("sum.txt", [&](FILE* f) {
        fprintf(f, "jobs %u ok %u ms1000 %llu pairs %llu\n", jobs, jobs_ok, (unsigned long long)ms1000, (unsigned long long)pair_total);
    });
#else
    (void)folder;
#endif
}

/* Bench of one job from its first pair: the pair starts at the first dispatch of the entry, so
   it holds the whole code of the entry. Sides: 0 lifted, 1 kernel. The float scope is on both
   sides. The order of the sides changes with every pass and from job to job. */
inline void bench_job(uint32_t job) {
#if K5_ADAPTER && !K5_HOOKS
    const auto list = read_pairs(cfg.pairs_in, job);
    if (list.empty()) {
        printf("K5 BENCH seq=%u error=no_pairs\n", job);
        return;
    }
    const Pair& p = *list[0];
    spu_context* c = oracle_context();
    void (*fn)(spu_context*) = spu_lifted_lookup(c, p.entry);
    if (!fn) {
        printf("K5 BENCH seq=%u error=no_entry\n", job);
        return;
    }
    for (uint32_t i = 0; i < cfg.passes; ++i) {
        const int first = (int)((i + job) & 1u);
        uint64_t sum[2] = {0, 0}, falls[2] = {0, 0};
        for (int k = 0; k != 2; ++k) {
            const int side = first ^ k;
            restore(c, p);
            pass = 1;
            motorstorm_pvs_set_mode(side ? MOTORSTORM_PVS_NATIVE : MOTORSTORM_PVS_REFERENCE);
            uint64_t c0[5], c1[5];
            motorstorm_pvs_counters(c0);
            c->pc = p.entry;
            const uint64_t scope = spu_sf_simd_enter();
            const uint64_t t0 = ticks();
            spu_run_with_halt(p2_entry, c);
            const uint64_t t1 = ticks();
            spu_sf_simd_leave(scope);
            pass = 0;
            motorstorm_pvs_counters(c1);
            sum[side] = t1 - t0;
            falls[side] = c1[3] - c0[3];
        }
        printf("K5 BENCH seq=%u entry=%05X pass=%u lifted=%llu kernel=%llu lifted_fallbacks=%llu kernel_fallbacks=%llu status=%X\n", job,
               p.entry, i, (unsigned long long)sum[0], (unsigned long long)sum[1], (unsigned long long)falls[0],
               (unsigned long long)falls[1], (unsigned)c->status);
    }
#else
    (void)job;
#endif
}

} // namespace k5

#if K5_HOOKS
extern "C" void p5_enter(spu_context* ctx, uint32_t a) {
    if (k5::pass) return;
    const uint64_t now = k5::ticks();
    k5::charge(now);
    const uint32_t h = ctx->host_depth, ret = ctx->drain_ret_pc & k5::kMask;
    if (k5::stack.empty()) {
        k5::open(a, ret, h, now);
    } else {
        k5::Frame& top = k5::stack.back();
        if (h > top.h || (h == top.h && ret != top.ret)) {
            top.bchild = 1; /* the bracket of this frame called into the job image */
            k5::open(a, ret, h, now);
        } else if (a != top.cur && k5::is_mark(a)) {
            k5::close(now); /* a marked entry splits the frame */
            k5::open(a, ret, h, now);
        } else {
            top.cur = a;
            top.leaf_on = k5::block_kind(a) != 1;
        }
    }
    ++k5::fns[a].n;
    k5::pair_enter(ctx, a);
    k5::last = now;
}

extern "C" void p5_call(spu_context* ctx, uint32_t target, uint32_t ret) {
    if (k5::pass || k5::stack.empty()) return;
    const uint64_t now = k5::ticks();
    k5::charge(now);
    k5::Frame& top = k5::stack.back();
    top.bstart = now;
    top.bchild = 0;
    char key[64];
    snprintf(key, sizeof key, "%05X>%05X %05X", top.cur, target, ret);
    ++k5::edges[key];
    k5::last = now;
    (void)ctx;
}

extern "C" void p5_after(spu_context* ctx, uint32_t callee, uint32_t ret) {
    if (k5::pass || k5::stack.empty()) return;
    const uint64_t now = k5::ticks();
    k5::charge(now);
    while (k5::stack.size() > 1) {
        const k5::Frame& top = k5::stack.back();
        const k5::Frame& below = k5::stack[k5::stack.size() - 2];
        if (top.h > below.h || (top.h == below.h && top.ret != below.ret))
            k5::close(now); /* the frames of the bracket end here */
        else
            break;
    }
    k5::Frame& top = k5::stack.back();
    if (!top.bchild) top.pm += now - top.bstart; /* lifted code of another unit: the policy module */
    k5::last = now;
    (void)ctx;
    (void)callee;
    (void)ret;
}

extern "C" void p5_ret(spu_context* ctx, uint32_t n) {
    if (k5::pass) return;
    const uint64_t now = k5::ticks();
    k5::charge(now);
    k5::pair_ret(ctx, n);
}
#endif
