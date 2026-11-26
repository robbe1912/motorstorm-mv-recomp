/* Private CPU-only replay of one dumped SPU job (image 213, spuparticlesystem).
 *
 * Engine: the runtime's instruction helper (spu_step of spu_interp.c) one
 * instruction at a time over the local store of the dump. The lifted code calls
 * the same spu_<op> helpers; only the dispatch differs. Every instruction that
 * touches external state is modeled here from the dump records and never reaches
 * the runtime channel code:
 *   DMA GET (0x20) and GETLLAR (0x40): the next DMA record of the dump must match
 *     command, LSA, EA and size; its bytes are copied into the local store.
 *   DMA PUT (0x21): the next DMA record must match; the local store bytes are
 *     compared with the stored record bytes.
 *   PUTLLC (0x50) / PUTLLUC (0x51): not in the dump. The model always succeeds and
 *     keeps the line in a private table.
 *   MFC_RdTagStat returns the tag mask (the runtime completes DMA synchronously).
 *   SPU_RdDec returns a deterministic counter: -(steps / 40).
 *   stop is a wait (no-op). stopd, iret, mfspr and unknown channels stop the replay.
 * Output: a profile file with, per region, executed instructions, host time,
 * inclusive instructions and call counts, the caller -> callee edge matrix, and
 * the executed-instruction count of every local store word.
 *
 * Usage: replay.exe <job.bin> <regions.txt> <profile.bin>
 *        [--r0 hex] [--r1 hex] [--stop hex] [--max steps] [--trace N]
 *        [--snap pc:nth:file]... [--jobinfo]
 */
#include <windows.h>
#include <setjmp.h>
#define main existing_fixture_main
/* The build sets these two names when the source file is not in scripts/fixtures. */
#ifndef MOTORSTORM_REPLAY_HANDOFF
#define MOTORSTORM_REPLAY_HANDOFF "spu_interpreter_handoff.c"
#endif
#include MOTORSTORM_REPLAY_HANDOFF
#undef main
#ifndef MOTORSTORM_REPLAY_INTERP
#define MOTORSTORM_REPLAY_INTERP "../../vendor/ps3recomp/runtime/spu/spu_interp.c"
#endif
#include MOTORSTORM_REPLAY_INTERP

#define LS_WORDS 0x10000
#define MAX_REGIONS 1024
#define MAX_FRAMES 512
#define BUCKET 256

typedef struct {
    uint32_t magic, version, header_size, seq, image, entry, ctx_image, spu_id, thread, spans;
    uint64_t ctx;
    uint32_t r3[4], r4[4];
    uint64_t t_entry, t_close, t_exit;
    uint32_t exit_pc, close_reason;
    uint32_t resident[12], reserved[8];
} DumpHead;

typedef struct {
    uint32_t is_get, cmd, lsa, ea, size, pc, image, exits_before, in_span, flags, index;
    uint64_t time;
    const uint8_t* bytes;
    int stored;
} Dma;

typedef struct { uint32_t index, pc, r0, r1, r3, r4, checked; uint64_t time; } Exit;

typedef struct { uint32_t start, end; char name[48]; } Region;
typedef struct { uint32_t ret, link, callee, caller; uint64_t start; } Frame;

static DumpHead head;
static Dma dma[4096];
static Exit exits[256];
static int dma_n, exit_n, next_dma, next_exit;
static const uint8_t* entry_ls;
static const uint8_t* exit_ls;
static Region regions[MAX_REGIONS];
static int region_n;
static uint16_t region_of[LS_WORDS];
static uint64_t steps_r[MAX_REGIONS], ns_r[MAX_REGIONS], incl_r[MAX_REGIONS], calls_r[MAX_REGIONS];
static uint64_t* edges;
static unsigned getllar_n, getllar_norec, put_diff_n, put_diff_bytes;
static jmp_buf fail_jmp;
static FILE* klog;
static uint32_t count[LS_WORDS];
static Frame frames[MAX_FRAMES];
static int depth;
static uint64_t step_no, total_ns;
static uint32_t bucket_steps[MAX_REGIONS], bucket_touched[MAX_REGIONS], bucket_n;
static LARGE_INTEGER bucket_t0, freq;
static uint32_t tag_status, atomic_stat, stall_stat, stop_n, wr_other[128];
static int resv_valid;
static unsigned dec_reads, putllc_n, putlluc_n, unrecorded_pass, exit_checked;
static int failed;
static void fail(const char* what, uint32_t pc) {
    failed = 1;
    fprintf(stderr, "REPLAY FAIL %s at LS 0x%05X step %llu r0=%05X r1=%05X depth %d dma %d of %d\n", what, pc,
            (unsigned long long)step_no, spu_preferred_u32(&ctx.gpr[0]), spu_preferred_u32(&ctx.gpr[1]), depth,
            next_dma, dma_n);
    longjmp(fail_jmp, 1);
}
static int snap_n;

static uint64_t total_steps_limit;
static int trace_n, jobinfo;
static uint32_t stop_pc;

typedef struct { uint32_t pc; unsigned nth, seen; char path[260]; } SnapSpec;
static SnapSpec snaps[64];
static char final_path[260];
/* --snapfn pc:nth:file: local store and registers at the entry (file.in) and at the exit (file.out) of the nth call of the function at pc. */
typedef struct { uint32_t pc; unsigned nth, seen, active, depth; char path[260]; } FnSnap;
static FnSnap fnsnaps[16];
static int fnsnap_n;
static uint32_t be32(const uint8_t* p) {
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}

static void load_regions(const char* path) {
    FILE* f = fopen(path, "r");
    if (!f) { fprintf(stderr, "no regions file %s\n", path); exit(2); }
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        Region* r = &regions[region_n];
        char dummy;
        if (sscanf(line, "%x %x %47s", &r->start, &r->end, r->name) != 3) continue;
        if (r->start >= LS_WORDS * 4 || r->end > LS_WORDS * 4 || r->start >= r->end) { fprintf(stderr, "bad region %s", line); exit(2); }
        region_n++;
        (void)dummy;
        if (region_n == MAX_REGIONS) break;
    }
    fclose(f);
    for (int i = 1; i < region_n; ++i)
        if (regions[i].start < regions[i - 1].end) { fprintf(stderr, "regions overlap or are not sorted at %s\n", regions[i].name); exit(2); }
    /* The file lists every range in order. The first range is region 0. */
    for (uint32_t a = 0; a < LS_WORDS; ++a) region_of[a] = 0;
    for (int i = 0; i < region_n; ++i)
        for (uint32_t a = regions[i].start >> 2; a < regions[i].end >> 2; ++a) region_of[a] = (uint16_t)i;
}

static void load_dump(const char* path, uint8_t** data, size_t* size) {
    FILE* f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "no dump %s\n", path); exit(2); }
    fseek(f, 0, SEEK_END);
    *size = (size_t)ftell(f);
    fseek(f, 0, SEEK_SET);
    *data = (uint8_t*)malloc(*size);
    if (!*data || fread(*data, 1, *size, f) != *size) { fprintf(stderr, "short read\n"); exit(2); }
    fclose(f);
    if (*size < sizeof(head) || memcmp(*data, "SJDU", 4) != 0) { fprintf(stderr, "bad dump magic\n"); exit(2); }
    memcpy(&head, *data, sizeof(head));
    size_t pos = sizeof(head);
    int number = 0;
    while (pos + 16 <= *size) {
        const uint8_t* h = *data + pos;
        uint32_t tag, payload, recno;
        memcpy(&tag, h, 4); memcpy(&payload, h + 4, 4); memcpy(&recno, h + 8, 4);
        const uint8_t* body = h + 16;
        if (recno != (uint32_t)number++ || payload % 16 || pos + 16 + payload > *size) { fprintf(stderr, "bad record at %zu\n", pos); exit(2); }
        if (tag == 1) {
            if (dma_n == 4096) { fprintf(stderr, "too many DMA records\n"); exit(2); }
            Dma* d = &dma[dma_n++];
            memcpy(d, body, 40);
            memcpy(&d->time, body + 40, 8);
            memcpy(&d->index, body + 48, 4);
            d->stored = !(d->flags & 1);
            d->bytes = body + 64;
        } else if (tag == 2) {
            Exit* e = &exits[exit_n++];
            memcpy(e, body, 24);
            memcpy(&e->time, body + 24, 8);
        } else if (tag == 3) {
            entry_ls = body;
        } else if (tag == 4) {
            exit_ls = body + 32;
        } else if (tag == 5) {
            break;
        } else {
            fprintf(stderr, "unknown tag %u\n", tag); exit(2);
        }
        pos += 16 + payload;
    }
}

typedef struct { uint32_t ea; uint8_t line[128]; int used, known, src; } Line;
static Line lines[1024];
static Line* line_for(uint64_t ea) {
    uint32_t key = (uint32_t)(ea >> 7);
    for (unsigned i = 0; i < 1024; ++i) {
        Line* l = &lines[(key + i) & 1023];
        if (!l->used) { l->used = 1; l->ea = key; memset(l->line, 0, 128); return l; }
        if (l->ea == key) return l;
    }
    fail("line table full", ctx.pc);
    return 0;
}

/* --seed: value of the decrementer read at 0x1695C. The job module uses it as the seed of its random generator. */
static uint32_t seed_value;
static int seed_set;
static uint32_t rdch_value(uint32_t ch, uint32_t pc) {
    switch (ch) {
    case MFC_RdTagStat: return tag_status;
    case MFC_RdTagMask: return ctx.mfc_tag_mask;
    case MFC_RdAtomicStat: return atomic_stat;
    case MFC_RdListStallStat: { uint32_t v = stall_stat; stall_stat = 0; return v; }
    case SPU_RdDec:
        ++dec_reads;
        if (pc == 0x1695C && seed_set) {
            printf("  dec read %u at %05X step %llu: %08X (seed given)\n", dec_reads, pc, (unsigned long long)step_no, seed_value);
            return seed_value;
        }
        printf("  dec read %u at %05X step %llu: %08X (model)\n", dec_reads, pc, (unsigned long long)step_no,
               (uint32_t)0 - (uint32_t)(step_no / 40));
        return (uint32_t)0 - (uint32_t)(step_no / 40);
    case SPU_RdEventMask: return ctx.event_mask;
    case SPU_RdEventStat: return ctx.event_status;
    case SPU_RdMachStat: return 1;
    case SPU_RdSRR0: return ctx.srr0;
    default:
        fprintf(stderr, "unmodeled channel read %u\n", ch);
        fail("rdch", pc);
    }
    return 0;
}

static uint32_t rchcnt_value(uint32_t ch, uint32_t pc) {
    switch (ch) {
    case MFC_RdTagStat: case MFC_RdAtomicStat: case SPU_RdDec: case MFC_RdListStallStat:
    case SPU_RdEventMask: case SPU_RdMachStat: case MFC_RdTagMask: return 1;
    case SPU_RdEventStat: return (ctx.event_status & ctx.event_mask) != 0;
    case SPU_WrOutMbox: return 1;
    case SPU_WrOutIntrMbox: return 1;
    default:
        fprintf(stderr, "unmodeled channel count %u\n", ch);
        fail("rchcnt", pc);
    }
    return 0;
}

/* The dump has no atomic record (spu_mfc_atomic has no dump hook). The model takes
   the line from the first recorded 128-byte GET of the same line that is next in time,
   or from the last one before. A line without a record stays zero. */
static const Dma* recorded_line(uint32_t ea_line) {
    for (int i = next_dma; i < dma_n; ++i)
        if (dma[i].is_get && dma[i].stored && dma[i].size == 128 && (dma[i].ea & ~127u) == ea_line) return &dma[i];
    for (int i = dma_n - 1; i >= 0; --i)
        if (dma[i].is_get && dma[i].stored && dma[i].size == 128 && (dma[i].ea & ~127u) == ea_line) return &dma[i];
    return 0;
}

/* Bytes of an atomic line that no dump record holds. The dump does not record atomics.
   Source: a text file with lines "ea offset value" in hex (offset 0..127 in the aligned line).
   The file is an input of the model. Each job report names it. */
typedef struct { uint32_t ea; unsigned off, val; } Patch;
static Patch patches[64];
static int patch_n;
static void load_patches(const char* path) {
    FILE* f = fopen(path, "r");
    unsigned ea, off, val;
    if (!f) { fprintf(stderr, "cannot open patch file %s\n", path); exit(2); }
    while (fscanf(f, "%x %x %x", &ea, &off, &val) == 3 && patch_n < 64) {
        patches[patch_n].ea = ea & ~127u; patches[patch_n].off = off & 127; patches[patch_n].val = val & 255; ++patch_n;
    }
    fclose(f);
}
static Line* mem_line(uint64_t ea) {
    Line* l = line_for(ea);
    if (!l->known) {
        const Dma* src = recorded_line((uint32_t)ea & ~127u);
        if (src) { memcpy(l->line, src->bytes, 128); l->known = 1; l->src = src->index; }
        else ++getllar_norec;
        for (int i = 0; i < patch_n; ++i)
            if (patches[i].ea == ((uint32_t)ea & ~127u)) {
                printf("  patch: line %08X +%u = %02X (record would give %02X) at step %llu\n", patches[i].ea, patches[i].off,
                       patches[i].val, l->line[patches[i].off], (unsigned long long)step_no);
                l->line[patches[i].off] = (uint8_t)patches[i].val; l->known = 1;
            }
    }
    return l;
}

static void command(uint32_t cmd, uint32_t pc) {
    const uint64_t ea = ((uint64_t)ctx.mfc_eah << 32) | ctx.mfc_eal;
    Dma* d = next_dma < dma_n ? &dma[next_dma] : 0;
    if (ctx.mfc_size == 0 && (cmd == 0x20 || cmd == 0x40)) {
        /* The runtime makes no transfer for a size of 0, so the dump has no record. */
        static unsigned zero_n;
        if (++zero_n <= 4) printf("  %s size 0 at %05X: no transfer, no record\n", cmd == 0x40 ? "GET" : "PUT", pc);
        ctx.pc = pc + 4;
        return;
    }
    /* Runtime command codes (spu_context.h): PUT 0x20, GET 0x40, GETLLAR 0xD0,
       PUTLLC 0xB4, PUTLLUC 0xB0, PUTQLLUC 0xB8. PUT and GET go through
       mfc_do_transfer, which the dump records. */
    if (cmd == 0x20 || cmd == 0x40) {
        if (!d || (cmd == 0x40) != (d->is_get != 0) || d->cmd != cmd || d->lsa != ctx.mfc_lsa || d->ea != (uint32_t)ea ||
            d->size != ctx.mfc_size) {
            fprintf(stderr, "DMA record mismatch: replay cmd=%02X lsa=%05X ea=%016llX size=%u pc=%05X; dump record %d of %d: %s\n",
                    cmd, ctx.mfc_lsa, (unsigned long long)ea, ctx.mfc_size, pc, next_dma + 1, dma_n,
                    d ? "" : "none left");
            if (d) fprintf(stderr, "  dump: %s cmd=%02X lsa=%05X ea=%08X size=%u pc=%05X exits=%u span=%u\n", d->is_get ? "GET" : "PUT",
                           d->cmd, d->lsa, d->ea, d->size, d->pc, d->exits_before, d->in_span);
            fail(cmd == 0x40 ? "DMA get" : "DMA put", pc);
        }
        if (d->stored && d->size) {
            if (ctx.mfc_lsa + d->size > 0x40000) fail("dma bounds", pc);
            if (cmd == 0x40) {
                memcpy(ctx.ls + ctx.mfc_lsa, d->bytes, d->size);
                if (d->size == 128) {
                    Line* l = line_for(ea);
                    memcpy(l->line, d->bytes, 128); l->known = 1; l->src = d->index;
                }
            } else {
                unsigned diff = 0, first = 0;
                for (uint32_t i = 0; i < d->size; ++i)
                    if (ctx.ls[ctx.mfc_lsa + i] != d->bytes[i]) { if (!diff) first = i; ++diff; }
                printf("  PUT record %u: lsa=%05X ea=%08X size=%u pc=%05X differing bytes %u (first +%u)\n", d->index, d->lsa, d->ea,
                       d->size, pc, diff, first);
                if (diff) { ++put_diff_n; put_diff_bytes += diff; }
            }
        } else if (!d->stored)
            printf("  %s record %u: lsa=%05X size=%u pc=%05X bytes not stored in the dump: local store not changed\n",
                   cmd == 0x40 ? "GET" : "PUT", d->index, d->lsa, d->size, pc);
        ++next_dma;
    } else if (cmd == 0xD0) {
        Line* l = mem_line(ea);
        memcpy(ctx.ls + (ctx.mfc_lsa & 0x3FFFF), l->line, 128);
        atomic_stat = 4; ctx.resv_ea = (uint32_t)ea & ~127u; ctx.resv_valid = 1; resv_valid = 1;
        ++getllar_n;
        if (klog) fprintf(klog, "%llu GETLLAR pc=%05X ea=%08X lsa=%05X known=%d src=%d\n", (unsigned long long)step_no, pc,
                          (uint32_t)ea & ~127u, ctx.mfc_lsa & 0x3FFFF, l->known, l->src);
    } else if (cmd == 0xB4 || cmd == 0xB0 || cmd == 0xB8) {
        Line* l = mem_line(ea);
        unsigned diff = 0;
        for (unsigned i = 0; i < 128; ++i) if (l->line[i] != ctx.ls[ctx.mfc_lsa + i]) ++diff;
        memcpy(l->line, ctx.ls + ctx.mfc_lsa, 128);
        atomic_stat = cmd == 0xB4 ? 0 : 2;
        ctx.resv_valid = 0; resv_valid = 0;
        if (cmd == 0xB4) ++putllc_n; else ++putlluc_n;
        if (klog) fprintf(klog, "%llu %s pc=%05X ea=%08X lsa=%05X line bytes changed %u known=%d src=%d\n", (unsigned long long)step_no,
                          cmd == 0xB4 ? "PUTLLC" : cmd == 0xB0 ? "PUTLLUC" : "PUTQLLUC", pc, (uint32_t)ea & ~127u, ctx.mfc_lsa & 0x3FFFF,
                          diff, l->known, l->src);
    } else {
        fprintf(stderr, "unmodeled MFC command %02X\n", cmd);
        fail("MFC command", pc);
    }
    ctx.pc = pc + 4;
}

static void wrch_value(uint32_t ch, uint32_t v, uint32_t pc) {
    switch (ch) {
    case MFC_LSA: ctx.mfc_lsa = v; break;
    case MFC_EAH: ctx.mfc_eah = v; break;
    case MFC_EAL: ctx.mfc_eal = v; break;
    case MFC_Size: ctx.mfc_size = v; break;
    case MFC_TagID: ctx.mfc_tag = v & 0x1F; break;
    case MFC_WrTagMask: ctx.mfc_tag_mask = v; break;
    case MFC_WrTagUpdate: if (v) tag_status = ctx.mfc_tag_mask; break;
    case MFC_WrListStallAck: stall_stat = 0; break;
    case MFC_Cmd: command(v, pc); return;
    case SPU_WrOutMbox: case SPU_WrOutIntrMbox: ++wr_other[ch & 127]; break;
    default:
        /* The runtime ignores an unknown channel write (spu_wrch, default case). */
        ++wr_other[ch & 127];
        if (wr_other[ch & 127] <= 2) printf("  channel write %u value %08X at %05X: ignored (runtime default)\n", ch, v, pc);
    }
    ctx.pc = pc + 4;
}

static void write_snapshot_file(const char* path) {
    FILE* f = fopen(path, "wb");
    if (!f) fail("snapshot open", ctx.pc);
    uint32_t extra[6] = {tag_status, atomic_stat, dec_reads, ctx.mfc_tag_mask, ctx.mfc_lsa, ctx.mfc_eal};
    if (fwrite("PJSP", 1, 4, f) != 4 || fwrite(&ctx.pc, 4, 1, f) != 1 || fwrite(ctx.gpr, sizeof(ctx.gpr), 1, f) != 1 ||
        fwrite(ctx.ls, 0x40000, 1, f) != 1 || fwrite(extra, sizeof(extra), 1, f) != 1 || fclose(f) != 0)
        fail("snapshot write", ctx.pc);
    printf("  snapshot %s at %05X step %llu\n", path, ctx.pc, (unsigned long long)step_no);
}
static void write_snapshot(const SnapSpec* s) { write_snapshot_file(s->path); }

static void flush_bucket(void) {
    LARGE_INTEGER t1;
    QueryPerformanceCounter(&t1);
    const uint64_t elapsed = (uint64_t)((t1.QuadPart - bucket_t0.QuadPart) * 1000000000ull / freq.QuadPart);
    uint32_t sum = 0;
    for (uint32_t i = 0; i < bucket_n; ++i) sum += bucket_steps[bucket_touched[i]];
    if (sum) {
        for (uint32_t i = 0; i < bucket_n; ++i) {
            const uint32_t r = bucket_touched[i];
            ns_r[r] += elapsed * bucket_steps[r] / sum;
            bucket_steps[r] = 0;
        }
    }
    bucket_n = 0;
    total_ns += elapsed;
    bucket_t0 = t1;
}

/* Native kernel check of the random generator (src/motorstorm/particle_random.c).
   --native: run the kernel at each call of the generator instead of the lifted code.
   --pairs <file>: the lifted run writes one record per call (entry, exit). The native run
   reads the file and compares each record. --mutant <n> damages the native result; the
   replay must then fail. */
#include "particle_random.h"
typedef struct { uint32_t entry, kind; uint32_t gpr[512]; uint8_t state[160], seed[16]; } Pair;
static const uint32_t random_entry[2] = {0x170D0, 0x17248};
static int native_on, mutant, pair_fail;
static const char* pairs_path;
static FILE* pairs;
static unsigned pair_n;
static uint32_t frame_random[MAX_FRAMES];
static const char* pairs_out_path;
static FILE* pairs_out;

static int is_random_entry(uint32_t target) { return target == random_entry[0] || target == random_entry[1]; }

static void capture(Pair* p, uint32_t entry, uint32_t kind) {
    p->entry = entry; p->kind = kind;
    memcpy(p->gpr, ctx.gpr, sizeof p->gpr);
    memcpy(p->state, ctx.ls + 0x17DD0, sizeof p->state);
    memcpy(p->seed, ctx.ls + 0x174A0, sizeof p->seed);
}

static FILE* pairs_open(void) {
    if (!pairs && pairs_path) {
        pairs = fopen(pairs_path, native_on ? "rb" : "wb");
        FIXTURE_CHECK(pairs);
    }
    return pairs;
}

static void pair_write(uint32_t entry, uint32_t kind) {
    Pair p;
    capture(&p, entry, kind);
    FIXTURE_CHECK(fwrite(&p, sizeof p, 1, pairs_open()) == 1);
}

static void pair_compare(const Pair* now, const char* what) {
    Pair p;
    if (!pairs_path) return;
    if (fread(&p, sizeof p, 1, pairs_open()) != 1) fail("pairs file is too short", ctx.pc);
    if (p.entry == now->entry && p.kind == now->kind && !memcmp(p.gpr, now->gpr, sizeof p.gpr) &&
        !memcmp(p.state, now->state, sizeof p.state) && !memcmp(p.seed, now->seed, sizeof p.seed)) return;
    ++pair_fail;
    if (pair_fail <= 5)
        printf("  PAIR DIFFERS record %u (%s) at entry %05X: entry address %s, registers %s, state %s, seed %s\n", pair_n, what,
               now->entry, p.entry == now->entry ? "equal" : "differs",
               memcmp(p.gpr, now->gpr, sizeof p.gpr) ? "differ" : "equal",
               memcmp(p.state, now->state, sizeof p.state) ? "differ" : "equal",
               memcmp(p.seed, now->seed, sizeof p.seed) ? "differs" : "equal");
}

static void step_seed_once(void) {
    for (unsigned lane = 0; lane < 4; ++lane) {
        uint8_t* p = ctx.ls + 0x174A0 + 4 * lane;
        const uint32_t s = (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
        const uint32_t v = s * 1664525u + 1013904223u;
        for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(v >> (24 - 8 * i));
    }
}

/* Each mutant changes one result of the kernel. The check must reject each one. */
static void apply_mutant(const Pair* entry_state) {
    switch (mutant) {
    case 1: ctx.gpr[3]._u32[0] ^= 1; break;                                         /* result bit 0 */
    case 2: memcpy(ctx.ls + 0x174A0, entry_state->seed, 16); break;                  /* seed not advanced */
    case 3: memcpy(ctx.ls + 0x17DF0, entry_state->state + 0x20, 128); break;         /* table word not replaced */
    case 4: memcpy(ctx.ls + 0x17DE0, entry_state->state + 0x10, 16); break;          /* index quadword not replaced */
    case 5: memcpy(ctx.ls + 0x17DD0, entry_state->state, 16); break;                 /* marker not written */
    case 6: step_seed_once(); break;                                                 /* seed advanced twice */
    case 7: ctx.gpr[3]._u32[0] |= UINT32_C(0xC0000000); break;                       /* result without the mask */
    default: break;
    }
}

static void pair_out(const Pair* p) {
    if (!pairs_out_path) return;
    if (!pairs_out) pairs_out = fopen(pairs_out_path, "wb");
    FIXTURE_CHECK(pairs_out && fwrite(p, sizeof *p, 1, pairs_out) == 1);
}
static void native_random(uint32_t pc, uint32_t target) {
    Pair now, after;
    capture(&now, target, 0);
    pair_out(&now);
    pair_compare(&now, "entry");
    if (!motorstorm_particle_random_call(ctx.ls, (uint32_t*)ctx.gpr, target)) fail("native kernel declined", pc);
    apply_mutant(&now);
    ctx.gpr[0] = spu_link(pc + 4);
    ctx.pc = pc + 4;
    ++pair_n;
    capture(&after, target, 1);
    pair_out(&after);
    pair_compare(&after, "exit");
}

int main(int argc, char** argv) {
    _set_error_mode(_OUT_TO_STDERR); _set_abort_behavior(0, _WRITE_ABORT_MSG | _CALL_REPORTFAULT);
    FIXTURE_CHECK(argc >= 4);
    uint32_t r0_init = 0xFFFFFFFF, r1_init = 0x3FFD0;
    total_steps_limit = 400000000ull;
    for (int i = 4; i < argc; ++i) {
        if (!strcmp(argv[i], "--r0") && i + 1 < argc) r0_init = (uint32_t)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--r1") && i + 1 < argc) r1_init = (uint32_t)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--stop") && i + 1 < argc) stop_pc = (uint32_t)strtoul(argv[++i], 0, 16);
        else if (!strcmp(argv[i], "--max") && i + 1 < argc) total_steps_limit = _strtoui64(argv[++i], 0, 10);
        else if (!strcmp(argv[i], "--trace") && i + 1 < argc) trace_n = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--jobinfo")) jobinfo = 1;
        else if (!strcmp(argv[i], "--klog") && i + 1 < argc) klog = fopen(argv[++i], "w");
        else if (!strcmp(argv[i], "--patch") && i + 1 < argc) load_patches(argv[++i]);
        else if (!strcmp(argv[i], "--final") && i + 1 < argc) strcpy(final_path, argv[++i]);
        else if (!strcmp(argv[i], "--seed") && i + 1 < argc) { seed_value = (uint32_t)strtoul(argv[++i], 0, 16); seed_set = 1; }
        else if (!strcmp(argv[i], "--native")) native_on = 1;
        else if (!strcmp(argv[i], "--pairs") && i + 1 < argc) pairs_path = argv[++i];
        else if (!strcmp(argv[i], "--mutant") && i + 1 < argc) mutant = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--pairsout") && i + 1 < argc) pairs_out_path = argv[++i];
        else if (!strcmp(argv[i], "--snapfn") && i + 1 < argc) {
            FnSnap* s = &fnsnaps[fnsnap_n++];
            char* c = strchr(argv[++i], ':');
            FIXTURE_CHECK(c && strlen(argv[i]) < 250);
            *c = 0;
            s->pc = (uint32_t)strtoul(argv[i], 0, 16);
            s->nth = (unsigned)strtoul(c + 1, 0, 10);
            strcpy(s->path, strchr(c + 1, ':') + 1);
        }
        else if (!strcmp(argv[i], "--snap") && i + 1 < argc) {
            SnapSpec* s = &snaps[snap_n++];
            char* c = strchr(argv[++i], ':');
            FIXTURE_CHECK(c && strlen(argv[i]) < 250);
            *c = 0;
            s->pc = (uint32_t)strtoul(argv[i], 0, 16);
            s->nth = (unsigned)strtoul(c + 1, 0, 10);
            strcpy(s->path, strchr(c + 1, ':') + 1);
        } else { fprintf(stderr, "bad argument %s\n", argv[i]); return 2; }
    }
    uint8_t* data; size_t size;
    load_dump(argv[1], &data, &size);
    load_regions(argv[2]);
    if (jobinfo)
        printf("job %u entry=%05X r3=%08X r4=%08X,%08X dma=%d exits=%d exit_ls=%s exit_pc=%05X word[3FFE0]=%08X word[3FF70]=%08X word[3FF80]=%08X\n",
               head.seq, head.entry, head.r3[0], head.r4[0], head.r4[1], dma_n, exit_n, exit_ls ? "yes" : "no", head.exit_pc,
               exit_ls ? be32(exit_ls + 0x3FFE0) : 0, exit_ls ? be32(exit_ls + 0x3FF70) : 0, exit_ls ? be32(exit_ls + 0x3FF80) : 0);
    if (stop_pc == 0) stop_pc = r0_init != 0xFFFFFFFF ? r0_init : (exit_ls ? be32(exit_ls + 0x3FFE0) : 0);

    spu_context_init(&ctx, 0);
    ctx.policy_mode = 1;
    ctx.status = SPU_STATUS_RUNNING;
    ctx.pc = head.entry;
    memcpy(ctx.ls, entry_ls, 0x40000);
    memset(ctx.gpr, 0, sizeof(ctx.gpr));
    for (unsigned i = 0; i < 4; ++i) { ctx.gpr[3]._u32[i] = head.r3[i]; ctx.gpr[4]._u32[i] = head.r4[i]; }
    ctx.gpr[0] = spu_splat_u32(stop_pc);
    ctx.gpr[1] = spu_splat_u32(r1_init);
    ctx.int_enable = 1;
    ctx.event_mask = 2;
    ctx.image_id = 213;
    edges = (uint64_t*)calloc((size_t)region_n * region_n, sizeof(uint64_t));
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&bucket_t0);

    int traced = 0;
    if (setjmp(fail_jmp)) goto done;
    for (;;) {
        const uint32_t pc = ctx.pc;
        if (pc == stop_pc) {
            /* The stop PC is the last exit point of the job: check it like the other exit points. */
            for (int i = 0; i < exit_n; ++i)
                if (exits[i].pc == pc && !exits[i].checked && exits[i].r0 == spu_preferred_u32(&ctx.gpr[0])) {
                    ++exit_checked; exits[i].checked = 1;
                    printf("  exit %u at %05X r0=%05X agrees at step %llu (stop PC)\n", exits[i].index, pc, exits[i].r0,
                           (unsigned long long)step_no);
                }
            if (final_path[0]) write_snapshot_file(final_path);
            break;
        }
        if ((pc & 3) || pc >= 0x40000) fail("pc out of range", pc);
        if (step_no >= total_steps_limit) fail("step limit", pc);
        if (trace_n && traced < trace_n) { printf("%llu %05X %08X r1=%05X depth=%d\n", (unsigned long long)step_no, pc, spu_ls_read32(&ctx, pc), spu_preferred_u32(&ctx.gpr[1]), depth); ++traced; }
        for (int i = 0; i < exit_n; ++i)
            if (exits[i].pc == pc && !exits[i].checked) {
                if (exits[i].r0 == spu_preferred_u32(&ctx.gpr[0])) {
                    ++exit_checked; exits[i].checked = 1;
                    printf("  exit %u at %05X r0=%05X agrees at step %llu\n", exits[i].index, pc, exits[i].r0, (unsigned long long)step_no);
                    if (exits[i].r1 != spu_preferred_u32(&ctx.gpr[1]) || exits[i].r3 != spu_preferred_u32(&ctx.gpr[3]) ||
                        exits[i].r4 != spu_preferred_u32(&ctx.gpr[4]))
                        printf("  exit %u at %05X: r0 agrees, r1 %05X/%05X r3 %08X/%08X r4 %08X/%08X (replay/dump)\n", exits[i].index, pc,
                               spu_preferred_u32(&ctx.gpr[1]), exits[i].r1, spu_preferred_u32(&ctx.gpr[3]), exits[i].r3,
                               spu_preferred_u32(&ctx.gpr[4]), exits[i].r4);
                } else ++unrecorded_pass;
                break;
            }
        for (int i = 0; i < snap_n; ++i)
            if (snaps[i].pc == pc && snaps[i].seen == snaps[i].nth) { write_snapshot(&snaps[i]); }
        for (int i = 0; i < snap_n; ++i) if (snaps[i].pc == pc) ++snaps[i].seen;

        const uint32_t insn = spu_ls_read32(&ctx, pc);
        spu_ins d;
        spu_decode1(insn, pc, &d);
        const uint16_t r = region_of[pc >> 2];
        ++count[pc >> 2]; ++steps_r[r]; ++step_no;
        if (!bucket_steps[r]) bucket_touched[bucket_n++] = r;
        ++bucket_steps[r];
        if ((step_no & (BUCKET - 1)) == 0) flush_bucket();

        switch (d.op) {
        case SPU_wrch: wrch_value(d.ch, spu_preferred_u32(&ctx.gpr[d.rt]), pc); continue;
        case SPU_rdch: ctx.gpr[d.rt] = spu_make_preferred_u32(rdch_value(d.ch, pc)); ctx.pc = pc + 4; continue;
        case SPU_rchcnt: ctx.gpr[d.rt] = spu_splat_u32(rchcnt_value(d.ch, pc)); ctx.pc = pc + 4; continue;
        case SPU_sync: case SPU_dsync: ctx.pc = pc + 4; continue;
        case SPU_stop: ++stop_n; ctx.pc = pc + 4; continue;
        case SPU_stopd: case SPU_iret: case SPU_mfspr: case SPU_mtspr: case SPU_fscrrd: case SPU_fscrwr:
            fail("external-state instruction", pc);
        case SPU_brsl: case SPU_brasl: case SPU_bisl: case SPU_bisled: {
            if (depth == MAX_FRAMES) fail("frame stack", pc);
            const uint32_t target = (d.op == SPU_bisled || d.op == SPU_bisl) ? spu_preferred_u32(&ctx.gpr[d.ra]) & 0x3FFFC : d.tgt;
            if (native_on && is_random_entry(target)) { native_random(pc, target); continue; }
            Frame* fr = &frames[depth++];
            fr->ret = pc + 4; fr->link = d.rt; fr->callee = region_of[(target >> 2) & (LS_WORDS - 1)];
            if (klog && ((target < 0x4000) != (pc < 0x4000)))
                fprintf(klog, "%llu call %05X -> %05X r0=%05X r1=%05X r3=%08X\n", (unsigned long long)step_no, pc, target,
                        spu_preferred_u32(&ctx.gpr[0]), spu_preferred_u32(&ctx.gpr[1]), spu_preferred_u32(&ctx.gpr[3]));
            fr->caller = r; fr->start = step_no;
            frame_random[depth - 1] = is_random_entry(target) ? target : 0;
            if (pairs_path && frame_random[depth - 1]) pair_write(target, 0);
            for (int i = 0; i < fnsnap_n; ++i) {
                FnSnap* s = &fnsnaps[i];
                if (s->pc != target) continue;
                if (s->seen == s->nth) {
                    char p[300];
                    snprintf(p, sizeof p, "%s.in", s->path);
                    write_snapshot_file(p);
                    s->depth = depth - 1; s->active = 1;
                }
                ++s->seen;
            }
            ++edges[(size_t)r * region_n + fr->callee]; ++calls_r[fr->callee];
            break;
        }
        case SPU_bi: case SPU_biz: case SPU_binz: case SPU_bihz: case SPU_bihnz: {
            const uint32_t w = ctx.gpr[d.ra]._u32[0];
            if (klog && ((pc < 0x4000) != ((w & 0x3FFFF) < 0x4000)))
                fprintf(klog, "%llu jump %05X -> %05X r0=%05X r1=%05X r3=%08X\n", (unsigned long long)step_no, pc, w & 0x3FFFF,
                        spu_preferred_u32(&ctx.gpr[0]), spu_preferred_u32(&ctx.gpr[1]), spu_preferred_u32(&ctx.gpr[3]));
            int taken = d.op == SPU_bi;
            if (d.op == SPU_biz) taken = spu_preferred_u32(&ctx.gpr[d.rt]) == 0;
            if (d.op == SPU_binz) taken = spu_preferred_u32(&ctx.gpr[d.rt]) != 0;
            if (d.op == SPU_bihz) taken = (spu_preferred_u32(&ctx.gpr[d.rt]) & 0xFFFF) == 0;
            if (d.op == SPU_bihnz) taken = (spu_preferred_u32(&ctx.gpr[d.rt]) & 0xFFFF) != 0;
            if (taken && depth && frames[depth - 1].ret == w && (frames[depth - 1].link == d.ra || frames[depth - 1].link == 0)) {
                --depth;
                incl_r[frames[depth].callee] += step_no - frames[depth].start;
                if (pairs_path && frame_random[depth]) pair_write(frame_random[depth], 1);
                for (int i = 0; i < fnsnap_n; ++i)
                    if (fnsnaps[i].active && fnsnaps[i].depth == depth) {
                        char p[300];
                        snprintf(p, sizeof p, "%s.out", fnsnaps[i].path);
                        write_snapshot_file(p);
                        fnsnaps[i].active = 0;
                    }
            }
            break;
        }
        default: break;
        }
        if (spu_step(&ctx) != 0) fail("spu_step stopped", pc);
    }
done:
    flush_bucket();

    /* final report */
    printf("job %u: steps %llu host %.1f ms dma consumed %d of %d exits checked %d of %d unrecorded passes %u stop %u getllar %u (no record %u) putllc %u putlluc %u put records with differing bytes %u (%u bytes) dec reads %u final depth %d\n",
           head.seq, (unsigned long long)step_no, total_ns / 1e6, next_dma, dma_n, exit_checked, exit_n, unrecorded_pass, stop_n,
           getllar_n, getllar_norec, putllc_n, putlluc_n, put_diff_n, put_diff_bytes, dec_reads, depth);
    if (exit_ls) {
        unsigned diff = 0, first = 0, last = 0, run_start = 0, in_run = 0, runs = 0;
        for (unsigned a = 0; a < 0x40000; ++a)
            if (ctx.ls[a] != exit_ls[a]) {
                if (!diff) first = a;
                last = a; ++diff;
                if (!in_run) { run_start = a; in_run = 1; }
            } else if (in_run) {
                if (runs < 40) printf("  LS differs %05X-%05X (%u bytes)\n", run_start, a, a - run_start);
                ++runs; in_run = 0;
            }
        printf("  final LS against dump exit LS: %u differing bytes in %u ranges (first %05X last %05X) of 262144\n", diff, runs, first, last);
    }
    /* Addresses that the dump does not record: the atomic line buffers of the kernel
       (0x00080 to 0x0017F), a count after the last exit point (0x3FF40 to 0x3FF43), a
       dead stack slot (0x3FC90 to 0x3FC93), a counter of the policy module that comes
       from an atomic line without a record (0x14D0 to 0x14D3), and slots 1 to 3 of
       quadwords above 0x24000 (the lifted code splats address registers; the hardware
       leaves the other slots). */
    if (exit_ls) {
        unsigned outside = 0, first_out = 0;
        for (unsigned a = 0; a < 0x40000; ++a)
            if (ctx.ls[a] != exit_ls[a] && !(a >= 0x24000 && (a & 15) >= 4) && !(a >= 0x80 && a < 0x180) &&
                !(a >= 0x3FF40 && a < 0x3FF44) && !(a >= 0x3FC90 && a < 0x3FC94) && !(a >= 0x14D0 && a < 0x14D4)) {
                if (!outside) first_out = a;
                ++outside;
            }
        printf("  final LS outside the allowed set: %u bytes (first %05X)\n", outside, first_out);
    }
    FILE* f = fopen(argv[3], "wb");
    FIXTURE_CHECK(f);
    FIXTURE_CHECK(fwrite("PJPR", 1, 4, f) == 4);
    uint32_t one = 1;
    FIXTURE_CHECK(fwrite(&one, 4, 1, f) == 1 && fwrite(&region_n, 4, 1, f) == 1);
    FIXTURE_CHECK(fwrite(steps_r, sizeof(steps_r), 1, f) == 1 && fwrite(ns_r, sizeof(ns_r), 1, f) == 1);
    FIXTURE_CHECK(fwrite(incl_r, sizeof(incl_r), 1, f) == 1 && fwrite(calls_r, sizeof(calls_r), 1, f) == 1);
    FIXTURE_CHECK(fwrite(edges, sizeof(uint64_t) * (size_t)region_n * region_n, 1, f) == 1);
    FIXTURE_CHECK(fwrite(count, sizeof(count), 1, f) == 1 && fclose(f) == 0);
    printf("native kernel: calls %u, pair differences %u\n", pair_n, pair_fail);
    return failed || pair_fail ? 3 : 0;
}
