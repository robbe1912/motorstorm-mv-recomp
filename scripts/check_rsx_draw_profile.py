#!/usr/bin/env python3
"""Game-free checks for the per-draw GPU record (rsx_draws.csv).

1. Audits rsx_d3d12_backend.c, rsx_d3d12_sampler_tables.inc and scripts/run.py:
   the record starts only with the per-draw timestamp switch and a phase CSV
   path. The call sites of the record sit next to the state changes, the draw
   and the timestamp readback that they observe. The cmd, vc_sig, fc_sig and
   state_eq columns have their call sites next to the commands and the
   constant slots that they observe. Mutants must fail.
2. Compiles the production record block with an authored fixture: off by
   default; path derivation; row facts, flags, barrier count, draw time and
   the time before the draw; the commands without a flag, the constant
   signatures and state_eq; a row without an end timestamp; a failed readback;
   the row limit with one log line. Python compares the file with its own
   FNV-1a reference. Controls of the compiled block must fail.
3. Compiles the backend with a syntax-only clang-cl pass.

No game input; no performance claim."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "/* RSX draw CSV."
END = "/* End of the RSX draw CSV block. */"
HEADER = ("batch,draw,verts,idx,prim,rt0,rt1,rt2,rt3,zeta,vp_w,vp_h,vs,vs_hash,fp,fp_snap,"
          "rt_chg,vp_chg,pso_chg,srv_chg,barriers,depth,gap_us,gpu_us,cmd,vc_sig,fc_sig,state_eq")
ROW_CALL = "phase_draw_row(dr, d, row_flags, s_rt_barriers - row_barriers);\n"
WRITE_CALL = "phase_draw_rows_write(ticks, s_phase_query_n, s_phase_gpu_frame, s_phase_frequency);"
RESET = "phase_draw_batch_begin();"
RESET_ROWS = "u32 row_flags = 0, row_barriers = s_rt_barriers;"
SIGN_CALL = "                phase_draw_sign(dr);\n"
SAMPLER_CALL = "                phase_draw_samplers(s_sampler_table);\n"
STENCIL_CALL = "                    phase_draw_stencil(dr->stencil_ref);\n"
LIMIT = 17
FNV_OFFSET, FNV_PRIME = 1469598103934665603, 1099511628211

FIXTURE = r'''
#define _CRT_SECURE_NO_WARNINGS
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned char u8;
typedef unsigned int u32;
typedef unsigned long long u64;
#define MAX_DRAWS 64
#define PHASE_DRAW_ROWS_MAX @LIMIT@u
#define RSX_MAX_VERTEX_CONSTANTS 512
#define VP_CB_STRIDE 8448u
#define VP_FPCB_STRIDE 2304u
#define VP_FPCB_MAX_CONSTS ((VP_FPCB_STRIDE / 16) - 1)
typedef struct {
    u32 vertex_count, topology, rt_off, zeta_off, rt_mrt[3], vp_w, vp_h, fp_addr, fp_snap;
    int vs_idx;
    u32 depth_sample_mask;
    u8 depth_sampled_slot[16];
    u32 cb_slot;      /* constant slot of the record */
    u32 fp_const_n;   /* fragment constants in the b1 slot; 0xFFFF = refused */
} D3D12DrawRecord;
static int s_phase_gpu_draws;
static void* s_phase_readback;
static u32 s_phase_query_n;
/* Vertex program cache of the backend: slot 2 holds a known program. The
 * backend also maps the constant slots b0 and b1 of the records. */
static struct {
    struct { u32 hash; } vp_vs[3];
    int vp_vs_n;
    void* vp_cb_mapped;
    void* vp_fpcb_mapped;
    int vp_parity;
} s_d3d = {{{0u}, {0u}, {0x11223344u}}, 3, NULL, NULL, 0};
static const char* g_phase_csv;
static const char* rsx_env_once(const char* name)
{
    return strcmp(name, "RSX_PHASE_CSV") == 0 ? g_phase_csv : NULL;
}
@BLOCK@
static int checks, failures;
static void check(int good, const char* label)
{
    ++checks;
    if (!good) { ++failures; fprintf(stderr, "FAIL %s\n", label); }
}
/* Constant slots. Word w of slot s holds (s + 1) * 1000003 + w. */
#define B0_WORDS (VP_CB_STRIDE / 8)
#define B1_WORDS (VP_FPCB_STRIDE / 8)
static u64 slot_b0[MAX_DRAWS * B0_WORDS], slot_b1[MAX_DRAWS * B1_WORDS];
static const int sampler_tables[2];
static D3D12DrawRecord record(u32 slot, u32 verts)
{
    D3D12DrawRecord dr = {0};
    dr.vertex_count = verts; dr.topology = 4; dr.rt_off = 0x1BE0000; dr.rt_mrt[0] = 0xAB00;
    dr.zeta_off = 0x0C000000; dr.vp_w = 1280; dr.vp_h = 720; dr.vs_idx = 2;
    dr.fp_addr = 0x036CC2C1; dr.fp_snap = 9; dr.cb_slot = slot;
    return dr;
}
/* Draw A: display target, full viewport, no state change. */
static void row_a(void)
{
    D3D12DrawRecord dr = record(0, 12);
    phase_draw_sign(&dr);
    phase_draw_row(&dr, 3, 0, 0);
}
/* Draw B: target and PSO change, three target transitions, two depth reads
 * over three units. */
static void row_b(void)
{
    D3D12DrawRecord dr = {0};
    dr.vertex_count = 300; dr.topology = 4; dr.vp_w = 320; dr.vp_h = 180;
    dr.vs_idx = -1; dr.fp_addr = 0x10; dr.depth_sample_mask = 0x21;
    dr.depth_sampled_slot[0] = 3; dr.depth_sampled_slot[1] = 3; dr.depth_sampled_slot[5] = 7;
    dr.cb_slot = 1;
    phase_draw_sign(&dr);
    phase_draw_row(&dr, 4, PHASE_DRAW_TARGETS | PHASE_DRAW_PSO, 3);
}
/* Draw C: viewport and SRV table change. */
static void row_c(void)
{
    D3D12DrawRecord dr = {0};
    dr.vertex_count = 6; dr.topology = 4; dr.vs_idx = 9;   /* slot 9 does not exist */
    dr.cb_slot = 2;
    phase_draw_sign(&dr);
    phase_draw_row(&dr, 5, PHASE_DRAW_VIEWPORT | PHASE_DRAW_SRV, 0);
}
/* Draw D: A with the same constant bytes in another slot (slot 3). */
static void row_d(void)
{
    D3D12DrawRecord dr = record(3, 7);
    phase_draw_sign(&dr);
    phase_draw_row(&dr, 7, 0, 0);
}
/* Draw E: the b0 bytes of A in slot 4, other fragment constants. */
static void row_e(void)
{
    D3D12DrawRecord dr = record(4, 8);
    phase_draw_sign(&dr);
    phase_draw_row(&dr, 8, 0, 0);
}
/* Draw F: a refused b1 slot (slot 5). */
static void row_f(void)
{
    D3D12DrawRecord dr = record(5, 9);
    dr.fp_const_n = 0xFFFFu;
    phase_draw_sign(&dr);
    phase_draw_row(&dr, 9, 0, 0);
}
/* Draw G: D without a b1 buffer. main clears s_d3d.vp_fpcb_mapped. */
static void row_g(void)
{
    D3D12DrawRecord dr = record(6, 10);
    phase_draw_sign(&dr);
    phase_draw_row(&dr, 10, 0, 0);
}
/* Draw H: slot 3 after main wrote other bytes into it and into slot 0. */
static void row_h(void)
{
    D3D12DrawRecord dr = record(3, 11);
    phase_draw_sign(&dr);
    phase_draw_row(&dr, 11, 0, 0);
}
/* A row with the bytes of slot 0 (slot 6). main sets row_flags and
 * row_barriers before the draw. */
static u32 row_flags, row_barriers;
static void row_flagged(void)
{
    D3D12DrawRecord dr = record(6, 7);
    phase_draw_sign(&dr);
    phase_draw_row(&dr, 12, row_flags, row_barriers);
}
/* One timestamped draw: start timestamp, row, then the end timestamp. */
static void draw(void (*row)(void), int end)
{
    s_phase_query_n++;
    row();
    if (end) s_phase_query_n++;
}
int main(int argc, char** argv)
{
    const char* mode = argc > 1 ? argv[1] : "off";
    g_phase_csv = argc > 2 && strcmp(argv[2], "-") ? argv[2] : NULL;
    s_phase_readback = (void*)1;
    s_phase_gpu_draws = strcmp(mode, "off") != 0;
    s_d3d.vp_cb_mapped = slot_b0; s_d3d.vp_fpcb_mapped = slot_b1;
    for (u32 s = 0; s < MAX_DRAWS; s++) {
        for (u32 w = 0; w < B0_WORDS; w++) slot_b0[s * B0_WORDS + w] = (u64)(s + 1) * 1000003u + w;
        for (u32 w = 0; w < B1_WORDS; w++) slot_b1[s * B1_WORDS + w] = (u64)(s + 1) * 1000003u + w;
    }
    /* Slots 3 and 6 hold the bytes of slot 0. The b0 of slot 4 too. */
    memcpy(slot_b0 + 3 * B0_WORDS, slot_b0, B0_WORDS * sizeof slot_b0[0]);
    memcpy(slot_b0 + 6 * B0_WORDS, slot_b0, B0_WORDS * sizeof slot_b0[0]);
    memcpy(slot_b0 + 4 * B0_WORDS, slot_b0, B0_WORDS * sizeof slot_b0[0]);
    memcpy(slot_b1 + 3 * B1_WORDS, slot_b1, B1_WORDS * sizeof slot_b1[0]);
    memcpy(slot_b1 + 6 * B1_WORDS, slot_b1, B1_WORDS * sizeof slot_b1[0]);
    /* Microseconds. Index 0 is the batch timestamp, then one pair per draw. */
    u64 ticks[34];
    ticks[0] = 1000;
    for (u32 k = 0; k < 16; k++) { ticks[1 + 2 * k] = 1100 + 200 * k; ticks[2 + 2 * k] = 1200 + 200 * k; }
    ticks[33] = 4300;
    if (strcmp(mode, "off") == 0) {
        check(phase_draw_csv_on() == 0, "no record without per-draw timestamps");
        s_phase_query_n = 1;
        phase_draw_batch_begin();
        check(phase_draw_viewport(0, 0, 1, 1, 0, 0, 1, 1) == 0, "no viewport tracking when off");
        s_draw_sign[0] = s_draw_sign[1] = 1;
        draw(row_a, 1);
        check(s_draw_rows_n == 0, "no row when off");
        check(s_draw_sign[0] == 1 && s_draw_sign[1] == 1, "no signature when off");
        phase_draw_samplers(&sampler_tables[0]); phase_draw_stencil(1u);
        check(s_draw_cmds == 0, "no command bits when off");
        phase_draw_rows_write(ticks, 4, 7, 1000000);
        check(s_draw_csv == NULL && s_draw_csv_rows == 0, "no file when off");
    } else if (strcmp(mode, "nopath") == 0) {
        check(phase_draw_csv_on() == 0, "no record without a phase CSV path");
    } else {
        check(phase_draw_csv_on() == 1, "record with the switch and a path");
        check(phase_draw_viewport(0, 0, 1280, 720, 0, 0, 1280, 720) == 1, "first viewport is a change");
        check(phase_draw_viewport(0, 0, 1280, 720, 0, 0, 1280, 720) == 0, "same viewport is no change");
        check(phase_draw_viewport(0, 0, 1280, 720, 0, 0, 640, 720) == 1, "scissor change is a change");
        check(phase_draw_viewport(0, 0, 1281, 720, 0, 0, 1280, 720) == 1, "viewport change is a change");
        phase_draw_batch_begin();
        check(phase_draw_viewport(1, 2, 3, 4, 1, 2, 3, 4) == 1, "a batch forgets the previous viewport");
        /* Batch 7: fourteen draws with an end timestamp, one without.
         * state_eq is 1 only with the full state of the previous row. */
        phase_draw_batch_begin();
        s_phase_query_n = 1;
        draw(row_a, 1);                                        /* first row of a batch: 0 */
        draw(row_d, 1);                                        /* equal slot bytes: 1 */
        s_draw_cmds |= PHASE_DRAW_CMD_CLEAR; draw(row_d, 1);   /* a clear record: 0 */
        phase_draw_samplers(&sampler_tables[0]); draw(row_d, 1);   /* another sampler table: 0 */
        phase_draw_samplers(&sampler_tables[0]); draw(row_d, 1);   /* the same table again: 1 */
        phase_draw_stencil(5u); draw(row_d, 1);                /* another stencil reference: 0 */
        phase_draw_stencil(5u); draw(row_d, 1);                /* the same reference again: 1 */
        phase_draw_stencil(6u); draw(row_d, 1);                /* another stencil reference: 0 */
        draw(row_e, 1);                                        /* other fragment constants: 0 */
        draw(row_f, 1);                                        /* a refused b1 slot: 0 */
        s_d3d.vp_fpcb_mapped = NULL; draw(row_g, 1);           /* no b1 buffer: 0 */
        draw(row_d, 1);                                        /* no b1 buffer again: 1 */
        row_flags = PHASE_DRAW_PSO | PHASE_DRAW_SRV; row_barriers = 0;
        draw(row_flagged, 1);                                 /* a flag with equal constants: 0 */
        row_flags = 0; row_barriers = 3;
        draw(row_flagged, 1);                                 /* barriers only: 1 */
        check(s_draw_sign[1] == 0, "no b1 buffer gives fc_sig 0");
        s_d3d.vp_fpcb_mapped = slot_b1;
        draw(row_b, 1);                                        /* flags: 0 */
        draw(row_c, 1);                                        /* flags: 0 */
        draw(row_a, 0);
        check(s_draw_rows_n == 17, "seventeen rows held");
        phase_draw_rows_write(ticks, 34, 7, 1000000);
        check(s_draw_rows_n == 0 && s_draw_csv_rows == 16, "sixteen rows written, the seventeenth has no end timestamp");
        /* Equal bytes give one signature. */
        {
            const unsigned char* b0 = (const unsigned char*)slot_b0;
            u64 s0 = phase_draw_sig(b0, NULL, 0, PHASE_DRAW_B0_BYTES);
            u64 s1 = phase_draw_sig(b0 + VP_CB_STRIDE, NULL, 0, PHASE_DRAW_B0_BYTES);
            u64 s3 = phase_draw_sig(b0 + 3 * VP_CB_STRIDE, NULL, 0, PHASE_DRAW_B0_BYTES);
            check(s0 == s3 && s0 != 0, "equal slot bytes give one signature");
            check(s0 != s1, "other slot bytes give another signature");
            check(phase_draw_sig(b0 + 3 * VP_CB_STRIDE, b0, 77, PHASE_DRAW_B0_BYTES) == 77 &&
                  phase_draw_sig(b0 + VP_CB_STRIDE, b0, 77, PHASE_DRAW_B0_BYTES) != 77,
                  "equal bytes take the signature of the previous draw; other bytes do not");
        }
        /* Slots 0 and 3 now hold other bytes: word w is 0xABCDEF00 + w. */
        for (u32 s = 0; s < 4; s += 3) {
            for (u32 w = 0; w < B0_WORDS; w++) slot_b0[s * B0_WORDS + w] = 0xABCDEF00ull + w;
            for (u32 w = 0; w < B1_WORDS; w++) slot_b1[s * B1_WORDS + w] = 0xABCDEF00ull + w;
        }
        /* Batch 8: the readback fails, so its rows are dropped. */
        phase_draw_batch_begin();
        s_phase_query_n = 1;
        draw(row_h, 1);
        phase_draw_rows_write(NULL, 4, 8, 1000000);
        check(s_draw_rows_n == 0 && s_draw_csv_rows == 16, "failed readback drops the rows");
        /* Batch 8 writes again. Its first row has the bytes that slot 0 held
         * for the dropped batch: the batch reset must forget that slot. */
        phase_draw_batch_begin();
        s_phase_query_n = 1;
        draw(row_h, 1);
        phase_draw_rows_write(ticks, 4, 8, 1000000);
        check(s_draw_csv_rows == PHASE_DRAW_ROWS_MAX, "the next batch writes after a failed readback");
        /* Batch 9 holds three rows. The file is at its limit. */
        phase_draw_batch_begin();
        s_phase_query_n = 1;
        draw(row_a, 1); draw(row_b, 1); draw(row_c, 1);
        phase_draw_rows_write(ticks, 8, 9, 1000000);
        check(s_draw_csv_rows == PHASE_DRAW_ROWS_MAX && s_draw_csv_stopped == 1, "the file stops at the row limit");
        s_phase_query_n = 1;
        draw(row_a, 1);
        phase_draw_rows_write(ticks, 4, 10, 1000000);
        check(s_draw_csv_rows == PHASE_DRAW_ROWS_MAX && s_draw_rows_n == 0, "a stopped file takes no rows");
    }
    printf("draw profile checks=%d failures=%d\n", checks, failures);
    return failures ? 1 : 0;
}
'''


def fnv(words):
    """FNV-1a 64 of the 64-bit words, as the record writes it: 16 hex digits."""
    value = FNV_OFFSET
    for word in words:
        value = ((value ^ word) * FNV_PRIME) % (1 << 64)
    return "%016X" % value


def signature(slot, words):
    """Signature of a fixture slot: the fixture fills word w of slot s with (s + 1) * 1000003 + w."""
    return fnv((slot + 1) * 1000003 + word for word in range(words))


B0_WORDS = (512 * 16 + 32) // 8          # the vertex constants and the viewport epilogue
VC, FC = signature(0, B0_WORDS), signature(0, 4)     # fp_const_n = 0: one constant and fp_alpha
VB, FB = signature(1, B0_WORDS), signature(1, 4)
VK, FK = signature(2, B0_WORDS), signature(2, 4)
NONE = "0" * 16                            # no b1 buffer


def line(batch, draw, record, state, cmd, vc, fc, same):
    """One expected row. Every fixture draw has gap 100 us and draw time 100 us."""
    return "%u,%u,%s,%s,100.000,100.000,%u,%s,%s,%u" % (batch, draw, record, state, cmd, vc, fc, same)


def record(verts):
    return "%u,0,4,01BE0000,0000AB00,00000000,00000000,0C000000,1280,720,2,11223344,036CC2C1,9" % verts


A = record(12)
D = record(7)
SAME_STATE = "0,0,0,0,0,0"
EXPECTED = [
    HEADER,
    line(7, 3, A, SAME_STATE, 0, VC, FC, 0),                  # first row of a batch
    line(7, 7, D, SAME_STATE, 0, VC, FC, 1),                  # equal slot bytes
    line(7, 7, D, SAME_STATE, 2, VC, FC, 0),                  # a clear record before the draw
    line(7, 7, D, SAME_STATE, 4, VC, FC, 0),                  # another sampler table
    line(7, 7, D, SAME_STATE, 0, VC, FC, 1),                  # the same sampler table again
    line(7, 7, D, SAME_STATE, 8, VC, FC, 0),                  # another stencil reference
    line(7, 7, D, SAME_STATE, 0, VC, FC, 1),                  # the same stencil reference again
    line(7, 7, D, SAME_STATE, 8, VC, FC, 0),                  # another stencil reference
    line(7, 8, record(8), SAME_STATE, 0, VC, signature(4, 4), 0),     # other fragment constants
    line(7, 9, record(9), SAME_STATE, 0, signature(5, B0_WORDS), signature(5, 2304 // 8), 0),   # refused
    line(7, 10, record(10), SAME_STATE, 0, VC, NONE, 0),      # no b1 buffer
    line(7, 7, D, SAME_STATE, 0, VC, NONE, 1),                # no b1 buffer again
    line(7, 12, D, "0,0,1,1,0,0", 0, VC, NONE, 0),            # a flag with equal constants
    line(7, 12, D, "0,0,0,0,3,0", 0, VC, NONE, 1),            # barriers only: barriers are not part of state_eq
    line(7, 4, "300,0,4,00000000,00000000,00000000,00000000,00000000,320,180,-1,00000000,00000010,0",
         "1,0,1,0,7,2", 0, VB, FB, 0),                        # flags with other constants
    line(7, 5, "6,0,4,00000000,00000000,00000000,00000000,00000000,0,0,9,00000000,00000000,0",
         "0,1,0,1,0,0", 0, VK, FK, 0),
    line(8, 11, record(11), SAME_STATE, 0, fnv(0xABCDEF00 + word for word in range(B0_WORDS)),
         fnv(0xABCDEF00 + word for word in range(4)), 0),      # first row of a batch
]


def balanced(text, at, pattern):
    """Text of the function or block in `text` that starts at `at`."""
    start, state, i = at, "code", text.index("{", at) + 1
    depth = 1
    while i < len(text):
        c, pair = text[i], text[i:i + 2]
        if state == "line":
            if c == "\n":
                state = "code"
        elif state == "block":
            if pair == "*/":
                state = "code"
                i += 1
        elif state in ('"', "'"):
            if c == "\\":
                i += 1
            elif c == state:
                state = "code"
        elif pair in ("//", "/*"):
            state = "line" if pair == "//" else "block"
            i += 1
        elif c in ('"', "'"):
            state = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if not depth:
                return text[start:i + 1]
        i += 1
    raise AssertionError("unterminated " + pattern)


def function(source, name):
    match = re.search(r"\b(?:static\s+)?(?:void|int|u32|u64|const char\*)\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", source)
    assert match, "missing actual helper: " + name
    return balanced(source, match.start(), name)


def block_at(text, at, pattern):
    return balanced(text, text.index("{", at), pattern)


def record_block(source):
    assert source.count(BEGIN) == 1 and source.count(END) == 1, "one draw CSV block required"
    return source[source.index(BEGIN):source.index(END)]


def without(text, part, replacement=""):
    """`text` with its first `part` replaced. The part must be in the text."""
    changed = text.replace(part, replacement, 1)
    assert changed != text, part
    return changed


RULE = ("state_eq is 1 when this draw has the GPU state of the previous draw of the",
        "vc_sig and fc_sig equal those of the", "The first row of a batch has state_eq = 0",
        "barriers is not part of state_eq")
SAME = ("const PhaseDrawRow* prior = i ? &s_draw_rows[i - 1] : NULL;\n"
        "        int same = prior && !row->flags && !row->cmds &&\n"
        "                   row->vc_sig == prior->vc_sig && row->fc_sig == prior->fc_sig;\n")


def audit(source, launcher, samplers):
    text = record_block(source)
    assert "getenv(" not in text, "the record block reads its switch through rsx_env_once"
    on = function(text, "phase_draw_csv_on")
    assert "v = s_phase_gpu_draws && s_phase_readback && path != NULL;" in on, \
        "the record needs the per-draw timestamp switch"
    assert 'rsx_env_once("RSX_PHASE_CSV")' in text, "the file path comes from RSX_PHASE_CSV"
    transition = function(source, "off_rt_transition")
    assert transition.count("s_rt_barriers++;") == 1 and \
        transition.index("s_rt_barriers++;") > transition.index("->ResourceBarrier("), \
        "the transition count follows the issued barrier"
    frame = function(source, "render_frame")
    anchor = frame.index("u32 bound_depth_slot = UINT32_MAX;")
    loop = frame.index("for (u32 d = 0; d < s_d3d.draw_count && d < MAX_DRAWS; d++) {", anchor)
    assert frame.count(RESET) == 1 and anchor < frame.index(RESET) < loop, \
        "the batch reset sits before the replay loop"
    body = frame[loop:]
    assert frame.count(RESET_ROWS) == 1 and body.index(RESET_ROWS) < body.index("if (dr->depth_slot) {"), \
        "each record starts with its own flags and transition count"
    start = body.index("phase_gpu_draw(is_small, 0);")
    row = body.index(ROW_CALL)
    assert start < row < body.index("gpu_pso_draw(next_pso,"), \
        "the row starts with the start timestamp of the draw"
    assert frame.count("phase_draw_row(") == 1, "one row per draw"
    targets = block_at(frame, frame.index("if (want != cur_rt || wantm[0] != cur_m[0] ||"), "target change")
    assert targets.count("row_flags |= PHASE_DRAW_TARGETS;") == 1 and \
        "OMSetRenderTargets(s_d3d.cmd_list, nrt, rh, FALSE, dsv)" in targets, \
        "the target flag sits in the target change block"
    pso = block_at(frame, frame.index("if (!bind_reuse_on() || next_pso != bound_pso) {"), "PSO bind")
    assert pso.count("row_flags |= PHASE_DRAW_PSO;") == 1 and \
        "SetPipelineState(s_d3d.cmd_list, next_pso)" in pso, "the PSO flag sits in the PSO bind block"
    srv = block_at(frame, frame.index("if (!bind_reuse_on() || gh.ptr != bound_srv) {"), "SRV bind")
    assert srv.count("row_flags |= PHASE_DRAW_SRV;") == 1 and \
        "SetGraphicsRootDescriptorTable(s_d3d.cmd_list, 1, gh)" in srv, \
        "the SRV flag sits in the SRV table bind block"
    rect = body.index("D3D12_RECT dsc = {")
    assert rect < body.index("phase_draw_viewport(dvp.TopLeftX", rect) < body.index("row_flags |= PHASE_DRAW_VIEWPORT;") \
        < body.index("RSSetViewports(s_d3d.cmd_list, 1, &dvp);"), \
        "the viewport flag compares the values given to the command list"
    collect = function(source, "phase_gpu_collect")
    assert collect.count(WRITE_CALL) == 1, "one write per readback"
    assert collect.index("->Unmap(") < collect.index(WRITE_CALL) < collect.index("s_phase_query_n = 0;"), \
        "the rows are written with the readback timestamps"
    row_function = function(text, "phase_draw_row")
    assert "row->vs_hash = dr->vs_idx >= 0 && dr->vs_idx < s_d3d.vp_vs_n ? s_d3d.vp_vs[dr->vs_idx].hash : 0;" \
        in row_function, "the row takes the vertex program hash from the slot of the record"
    assert "row->depth = phase_draw_depth_slots(dr);" in row_function and \
        "row->barriers = barriers + 2u * row->depth;" in row_function, \
        "the row counts the depth reads of the draw apart from the other transitions"
    backend = function(source, "rsx_d3d12_backend_shutdown")
    assert backend.count("fclose(s_draw_csv);") == 1 and \
        backend.index("fclose(s_phase_csv);") < backend.index("fclose(s_draw_csv);"), \
        "shutdown closes the draw CSV next to the phase CSV"
    switch = "env['RSX_PHASE_GPU_DRAWS']='1'"
    assert switch in launcher and launcher.index("if args.profile_renderer_draws:") < launcher.index(switch), \
        "the launcher sets RSX_PHASE_GPU_DRAWS with --profile-renderer-draws"

    # The full GPU state of a draw against the previous draw: the call sites.
    replay = balanced(frame, loop, "replay loop")
    assert frame.count(SIGN_CALL) == 1 and body.index(SIGN_CALL) < start, \
        "the signatures of the constant slots precede the start timestamp of the draw"
    for call in ("IASetVertexBuffers(", "IASetIndexBuffer(", "IASetPrimitiveTopology(", "OMSetBlendFactor(",
                 "SetGraphicsRootSignature("):
        assert call not in replay, "the replay loop issues no " + call
    issue = function(source, "gpu_pso_draw")
    assert issue.count("->DrawInstanced(s_d3d.cmd_list, count, 1, first, 0);") == 1, \
        "one draw per record with instance count 1 and the first vertex of the record"
    capture = ("                        s_d3d.cmd_list->lpVtbl->OMSetRenderTargets(\n"
               "                            s_d3d.cmd_list, 1, &rtv_handle, FALSE, dsv);\n"
               "                        s_draw_cmds |= PHASE_DRAW_CMD_CAPTURE;\n")
    assert body.count(capture) == 1, "the mid-batch snapshot reports its target rebind"
    clear = "                if (dr->is_clear) {\n                    s_draw_cmds |= PHASE_DRAW_CMD_CLEAR;\n"
    assert body.count(clear) == 1, "a clear record reports itself before the next row"
    depth_clear = "                        depth_surface->initialized = 1;\n" \
                  "                        s_draw_cmds |= PHASE_DRAW_CMD_DEPTHCLEAR;\n"
    assert body.count(depth_clear) == 1, "the first use of a depth surface reports its clear"
    stencil = block_at(frame, frame.index("if (dpso && (dr->ds_key & RSX_DSK_STENCIL_EN)) {"), "stencil reference")
    assert frame.count(STENCIL_CALL) == 1 and stencil.count(STENCIL_CALL) == 1 and \
        stencil.index("OMSetStencilRef(") < stencil.index(STENCIL_CALL.strip()), \
        "the stencil reference is compared after its issue, in the stencil block"
    bind = "                if (guest_sampler_bind(dr, dpso ? dsampler_mask : 0u)) bound_srv = 0;\n" + SAMPLER_CALL
    assert body.count(bind) == 1, "the sampler table of the draw is compared after its bind"
    store = "    s_sampler_table = h->tables[slot];\n"
    tables = function(samplers, "guest_sampler_bind")
    assert samplers.count("static const D3D12_SAMPLER_DESC* s_sampler_table;") == 1 and \
        tables.count(store) == 1 and tables.index("slot = h->count++;") < tables.index(store) \
        < tables.index("int changed = s_sampler_bound != h->heap;"), \
        "the sampler bind stores the table that it issues"

    # The full GPU state of a draw against the previous draw: the record block.
    begin = function(text, "phase_draw_batch_begin")
    assert begin.count("    s_draw_cmds = 0; s_draw_samplers = NULL; s_draw_stencil = 0;\n"
                       "    s_draw_previous[0] = s_draw_previous[1] = NULL;\n") == 1, \
        "a batch forgets the commands, the sampler table and the slots of the previous batch"
    assert "row->cmds = s_draw_cmds; s_draw_cmds = 0;" in row_function and \
        "row->vc_sig = s_draw_sign[0]; row->fc_sig = s_draw_sign[1];" in row_function, \
        "the row takes the commands and the signatures of its draw"
    writer = function(text, "phase_draw_rows_write")
    assert text.count('gpu_us,cmd,vc_sig,fc_sig,state_eq\\n");') == 1, "the header names the state columns"
    rule = text[:text.index("static void phase_draw_rows_write")]
    for phrase in RULE:
        assert rule.count(phrase) == 1, "the rule of state_eq is in the comment of the writer: " + phrase
    assert writer.count(SAME) == 1, "state_eq needs no flag, no command and the constants of the previous row"
    assert writer.count('"%u,%016llX,%016llX,%u\\n",') == 1 and \
        "(unsigned long long)row->fc_sig, same != 0);" in writer, "the row writes cmd, the signatures and state_eq"
    sign = function(text, "phase_draw_sign")
    assert sign.count("if (!phase_draw_csv_on() || !s_phase_query_n) return;") == 1, \
        "no signature when the record is off"
    slot = "((u64)s_d3d.vp_parity * MAX_DRAWS + dr->cb_slot) * "
    assert sign.count(slot + "VP_CB_STRIDE") == 1 and sign.count(slot + "VP_FPCB_STRIDE : NULL") == 1, \
        "the signatures read the constant slots of the record"
    assert "phase_draw_sig(b0, s_draw_previous[0], s_draw_sign[0], PHASE_DRAW_B0_BYTES);" in sign and \
        "n >= VP_FPCB_MAX_CONSTS ? VP_FPCB_STRIDE : (n ? n + 1u : 2u) * 16u" in sign and \
        "phase_draw_sig(b1, s_draw_previous[1], s_draw_sign[1], bytes) : 0;" in sign, \
        "b0 covers the bytes of vp_record_cb, b1 the bytes that the fragment shader reads"
    assert "s_draw_previous[0] = b0; s_draw_previous[1] = b1;" in sign, \
        "the next draw compares its bytes with the slots of this draw"
    sig = function(text, "phase_draw_sig")
    assert "if (previous && !memcmp(bytes, previous, size)) return previous_sig;" in sig and \
        "u64 h = 1469598103934665603ull;" in sig and "h ^= word; h *= 1099511628211ull;" in sig, \
        "the signature is FNV-1a of the 8-byte words, or that of equal bytes"
    assert text.count("#define PHASE_DRAW_B0_BYTES (RSX_MAX_VERTEX_CONSTANTS * 16 + 32)") == 1, \
        "b0 covers the vertex constants and the 8 floats of the viewport epilogue"
    record_cb = function(source, "vp_record_cb")
    assert "memcpy(dst, st->vertex_constants, RSX_MAX_VERTEX_CONSTANTS * 16);" in record_cb and \
        "float* vpx = (float*)(dst + RSX_MAX_VERTEX_CONSTANTS * 16);" in record_cb, \
        "vp_record_cb writes the vertex constants and the viewport epilogue of b0"
    b1 = function(source, "vp_record_fp_b1")
    assert "if (n) memcpy(ks, fpk.values, (size_t)n * 16u);" in b1 and \
        "u32 shader_n = n ? n : 1u;" in b1 and "memcpy(ks + shader_n * 4u, &ref, 4);" in b1, \
        "vp_record_fp_b1 writes n constants and the alpha reference of b1"
    samplers_helper = function(text, "phase_draw_samplers")
    assert samplers_helper.count("if (!phase_draw_csv_on() || !s_phase_query_n) return;") == 1 and \
        "if (table == s_draw_samplers) return;" in samplers_helper and \
        "s_draw_cmds |= PHASE_DRAW_CMD_SAMPLERS;" in samplers_helper, "another sampler table is a command"
    stencil_helper = function(text, "phase_draw_stencil")
    assert stencil_helper.count("if (!phase_draw_csv_on() || !s_phase_query_n) return;") == 1 and \
        "if (s_draw_stencil != reference) s_draw_cmds |= PHASE_DRAW_CMD_STENCIL;" in stencil_helper and \
        "s_draw_stencil = reference;" in stencil_helper, "another stencil reference is a command"


def moved(text, line, after):
    """`text` without `line`, with `line` put after the first `after`."""
    changed = text.replace(line, "", 1)
    assert changed != text, line
    at = changed.index(after) + len(after)
    return changed[:at] + line + changed[at:]


def syntax_only(environment, source):
    command = [environment["MV_CLANG"], "/nologo", "/Zs", "/clang:-std=c17"]
    vendor = ROOT / "vendor/ps3recomp"
    command += ["/I" + str(vendor / part) for part in ("include", "libs/video", "runtime", "third_party")]
    command.append(str(source.resolve()))
    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                            text=True, errors="replace", timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "vendor/ps3recomp/libs/video/rsx_d3d12_backend.c")
    parser.add_argument("--launcher", type=Path, default=ROOT / "scripts/run.py")
    parser.add_argument("--samplers", type=Path,
                        default=ROOT / "vendor/ps3recomp/libs/video/rsx_d3d12_sampler_tables.inc")
    args = parser.parse_args()
    source = args.source.read_text()
    launcher = args.launcher.read_text()
    samplers = args.samplers.read_text()
    audit(source, launcher, samplers)
    row_line = "                " + ROW_CALL
    text = record_block(source)
    start_line = "                phase_gpu_draw(is_small, 0);\n"
    store = "    s_sampler_table = h->tables[slot];\n"
    mutants = [
        source.replace(row_line, "", 1),
        moved(source, row_line, "gpu_pso_draw(next_pso, dr->vertex_count, dr->vb_byte_offset / 256);\n"),
        moved(source, row_line, "phase_gpu_draw(is_small, 1);\n"),
        source.replace("                    row_flags |= PHASE_DRAW_SRV;\n", "", 1),
        source.replace("                    row_flags |= PHASE_DRAW_PSO;\n", "", 1),
        source.replace("                    row_flags |= PHASE_DRAW_TARGETS;\n", "", 1),
        source.replace("                        row_flags |= PHASE_DRAW_VIEWPORT;\n", "", 1),
        moved(source, "    " + WRITE_CALL + "\n", "    s_phase_query_n = 0;\n"),
        source.replace(WRITE_CALL, "", 1),
        source.replace("v = s_phase_gpu_draws && s_phase_readback && path != NULL;", "v = 1;", 1),
        source.replace("            " + RESET + "\n", "", 1),
        source.replace("    s_rt_barriers++;\n", "", 1),
        moved(source, "    s_rt_barriers++;\n", "    OffRT* r = &s_d3d.off_rt[slot];\n"),
        source.replace(ROW_CALL.strip(), "phase_draw_row(dr, d, row_flags, 0);", 1),
        source.replace(text, text.replace('rsx_env_once("RSX_PHASE_CSV")', 'getenv("RSX_PHASE_CSV")'), 1),
        source.replace("fclose(s_draw_csv); ", "", 1),
        source.replace("dr->vs_idx >= 0 && dr->vs_idx < s_d3d.vp_vs_n ? s_d3d.vp_vs[dr->vs_idx].hash : 0;", "0;", 1),
        source.replace("row->depth = phase_draw_depth_slots(dr);", "row->depth = 0;", 1),
        source.replace("row->barriers = barriers + 2u * row->depth;", "row->barriers = barriers;", 1),
        # The state columns.
        without(source, SIGN_CALL),
        without(source, SIGN_CALL + start_line, start_line + SIGN_CALL),
        without(source, "                        s_draw_cmds |= PHASE_DRAW_CMD_CAPTURE;\n"),
        without(source, "                    s_draw_cmds |= PHASE_DRAW_CMD_CLEAR;\n"),
        without(source, "                        s_draw_cmds |= PHASE_DRAW_CMD_DEPTHCLEAR;\n"),
        without(source, SAMPLER_CALL),
        moved(source, SAMPLER_CALL, "gh.ptr += (u64)s_draw_srv_base[d] * s_d3d.srv_inc;\n"),
        without(source, STENCIL_CALL),
        moved(source, STENCIL_CALL, "row_flags |= PHASE_DRAW_PSO;\n"),
        without(source, "count, 1, first, 0);", "count, 2, first, 0);"),
        without(source, 'gpu_us,cmd,vc_sig,fc_sig,state_eq\\n");', 'gpu_us\\n");'),
    ]
    mutants += [without(source, phrase) for phrase in RULE]
    mutants += [
        without(source, "int same = prior && !row->flags && !row->cmds &&", "int same = prior && !row->flags &&"),
        without(source, "int same = prior && !row->flags && !row->cmds &&", "int same = prior && !row->cmds &&"),
        without(source, "row->vc_sig == prior->vc_sig && row->fc_sig == prior->fc_sig;", "1;"),
        without(source, "const PhaseDrawRow* prior = i ? &s_draw_rows[i - 1] : NULL;",
                "const PhaseDrawRow* prior = &s_draw_rows[i ? i - 1 : 0];"),
        without(source, '"%u,%016llX,%016llX,%u\\n",', '"%u,%u\\n",'),
        without(source, "(unsigned long long)row->fc_sig, same != 0);", "same != 0);"),
        without(source, "    s_draw_previous[0] = s_draw_previous[1] = NULL;\n"),
        without(source, "row->cmds = s_draw_cmds; s_draw_cmds = 0;"),
        without(source, "row->vc_sig = s_draw_sign[0]; row->fc_sig = s_draw_sign[1];"),
        without(source, "if (!phase_draw_csv_on() || !s_phase_query_n) return;\n    const unsigned char* b0",
                "const unsigned char* b0"),
        without(source, "+ dr->cb_slot) * VP_CB_STRIDE;", "+ 0) * VP_CB_STRIDE;"),
        without(source, "+ dr->cb_slot) * VP_FPCB_STRIDE : NULL;", "+ 0) * VP_FPCB_STRIDE : NULL;"),
        without(source, "if (previous && !memcmp(bytes, previous, size)) return previous_sig;"),
        without(source, "h ^= word; h *= 1099511628211ull;", "h ^= word;"),
        without(source, "s_draw_previous[0] = b0; s_draw_previous[1] = b1;"),
        without(source, "#define PHASE_DRAW_B0_BYTES (RSX_MAX_VERTEX_CONSTANTS * 16 + 32)",
                "#define PHASE_DRAW_B0_BYTES (RSX_MAX_VERTEX_CONSTANTS * 16)"),
        without(source, "float* vpx = (float*)(dst + RSX_MAX_VERTEX_CONSTANTS * 16);",
                "float* vpx = (float*)(dst + RSX_MAX_VERTEX_CONSTANTS * 16 + 32);"),
        without(source, "n >= VP_FPCB_MAX_CONSTS ? VP_FPCB_STRIDE : (n ? n + 1u : 2u) * 16u", "VP_FPCB_STRIDE"),
        without(source, "if (table == s_draw_samplers) return;"),
        without(source, "if (s_draw_stencil != reference) s_draw_cmds |= PHASE_DRAW_CMD_STENCIL;",
                "s_draw_cmds |= PHASE_DRAW_CMD_STENCIL;"),
        without(source, "                phase_draw_samplers(s_sampler_table);\n",
                "                s_d3d.cmd_list->lpVtbl->OMSetBlendFactor(s_d3d.cmd_list, blend);\n"
                + SAMPLER_CALL),
    ]
    for index, mutant in enumerate(mutants):
        try:
            audit(mutant, launcher, samplers)
        except (AssertionError, ValueError):
            pass
        else:
            raise AssertionError("mutant %d accepted" % index)
    table_mutants = [
        without(samplers, store),
        moved(samplers, store, "    unsigned long long hash = guest_sampler_hash(desc);\n"),
        without(samplers, store, "    s_sampler_table = s_sampler_base->tables[0];\n"),
        without(samplers, "static const D3D12_SAMPLER_DESC* s_sampler_table;"),
    ]
    for index, mutant in enumerate(table_mutants):
        try:
            audit(source, launcher, mutant)
        except (AssertionError, ValueError):
            pass
        else:
            raise AssertionError("sampler table mutant %d accepted" % index)
    for index, mutant in enumerate((launcher.replace("env['RSX_PHASE_GPU_DRAWS']='1'", "", 1),
                                    launcher.replace("if args.profile_renderer_draws:", "if False:", 1))):
        try:
            audit(source, mutant, samplers)
        except (AssertionError, ValueError):
            pass
        else:
            raise AssertionError("launcher mutant %d accepted" % index)

    environment = os.environ.copy()
    if os.name == "nt":
        sys.path.insert(0, str(ROOT / "scripts"))
        from project import build_environment
        environment = build_environment()
    compiler = os.environ.get("CC") or environment.get("MV_CLANG") or shutil.which("clang") or shutil.which("gcc")
    assert compiler, "C compiler required"
    code = FIXTURE.replace("@BLOCK@", text).replace("@HEADER@", HEADER).replace("@LIMIT@", str(LIMIT))
    with tempfile.TemporaryDirectory(prefix="rsx-draw-profile-") as temporary:
        path = Path(temporary)
        c = path / "fixture.c"
        exe = path / ("fixture.exe" if os.name == "nt" else "fixture")

        def build(name, changed):
            c.write_text(changed)
            if Path(compiler).stem.lower() in ("cl", "clang-cl"):
                command = [compiler, "/nologo", "/W4", "/WX", "/std:c11", str(c), "/Fe" + str(path / name)]
            else:
                command = [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(c), "-o", str(path / name)]
            built = subprocess.run(command, cwd=path, env=environment, capture_output=True, text=True,
                                   errors="replace", timeout=180)
            assert built.returncode == 0, built.stdout + built.stderr
            return path / name

        def run(program, mode, phase_csv):
            arguments = [str(program), mode] + ([str(phase_csv)] if phase_csv is not None else [])
            result = subprocess.run(arguments, cwd=path, env=environment, capture_output=True, text=True,
                                    errors="replace", timeout=30)
            return result

        def passed(result, mode):
            assert result.returncode == 0 and "FAIL" not in result.stderr, mode + ": " + result.stderr
            assert "draw profile checks=" in result.stdout, result.stdout

        fixture = build("fixture.exe" if os.name == "nt" else "fixture", code)
        (path / "sub").mkdir()
        (path / "run").mkdir()
        for phase_csv in (path / "off" / "rsx_phases.csv", "rsx_phases.csv"):
            result = run(fixture, "off", phase_csv)
            passed(result, "off")
            assert "draw profile checks=6 failures=0" in result.stdout, result.stdout
            assert "[RSXPHASE] Draw CSV" not in result.stderr, "the default run logs no draw CSV"
            assert not (path / phase_csv).with_name("rsx_draws.csv").exists(), "the default run writes no draw CSV"
        for phase_csv in (None, "-"):
            result = run(fixture, "nopath", phase_csv)
            passed(result, "nopath")
            assert result.stderr.count("[RSXPHASE] Draw CSV off: RSX_PHASE_CSV gives no path\n") == 1, result.stderr
        on_csv = path / "run" / "rsx_draws.csv"
        for phase_csv in (path / "run" / "rsx_phases.csv", "sub/rsx_phases.csv", "rsx_phases.csv"):
            result = run(fixture, "on", phase_csv)
            passed(result, "on")
            # The record keeps the separator and directory of the phase CSV path.
            head, separator, _ = str(phase_csv).rpartition("/")
            expected = str(phase_csv.with_name("rsx_draws.csv")) if isinstance(phase_csv, Path) \
                else head + separator + "rsx_draws.csv"
            assert "[RSXPHASE] Draw CSV %s (stops at %d rows)\n" % (expected, LIMIT) in result.stderr, result.stderr
            assert result.stderr.count("[RSXPHASE] Draw CSV stopped at %d rows: %s\n" % (LIMIT, expected)) == 1, \
                "one stop line: " + result.stderr
            assert "draw profile checks=16 failures=0" in result.stdout, result.stdout
            # Python holds the expected file: row facts, the state columns and its own FNV-1a.
            written = (path / expected).read_text().splitlines()
            assert written == EXPECTED, "\n".join("got %s\nexp %s" % (got, want) for got, want in zip(written, EXPECTED)
                                                 if got != want) or "row count %d" % len(written)
        # Controls of the compiled block: each must fail a check or write another file.
        controls = [
            (without(code, "h ^= word; h *= 1099511628211ull;", "h ^= word;"), "FNV-1a without the prime"),
            (without(code, "if (previous && !memcmp(bytes, previous, size)) return previous_sig;",
                      "if (previous) return previous_sig;"), "the previous signature without equal bytes"),
            (without(code, "int same = prior && !row->flags && !row->cmds &&", "int same = prior && !row->flags &&"),
             "state_eq ignores the commands"),
            (without(code, "int same = prior && !row->flags && !row->cmds &&", "int same = prior && !row->cmds &&"),
             "state_eq ignores the flags"),
            (without(code, "row->vc_sig == prior->vc_sig && row->fc_sig == prior->fc_sig;", "1;"),
             "state_eq ignores the constants"),
            (without(code, "const PhaseDrawRow* prior = i ? &s_draw_rows[i - 1] : NULL;",
                      "const PhaseDrawRow* prior = &s_draw_rows[i ? i - 1 : 0];"),
             "the first row is equal to itself"),
            (without(code, "s_draw_sign[1] = b1 ? phase_draw_sig(b1, s_draw_previous[1], s_draw_sign[1], bytes) : 0;",
                      "s_draw_sign[1] = b1 ? 123 + bytes * 0 : 0;"), "fc_sig without a b1 buffer"),
            (without(code, "n >= VP_FPCB_MAX_CONSTS ? VP_FPCB_STRIDE : (n ? n + 1u : 2u) * 16u", "VP_FPCB_STRIDE + n * 0"),
             "fc_sig beyond the bytes that the fragment shader reads"),
            (without(code, "phase_draw_sig(b0, s_draw_previous[0], s_draw_sign[0], PHASE_DRAW_B0_BYTES);",
                      "phase_draw_sig(b0, s_draw_previous[0], s_draw_sign[0], VP_CB_STRIDE);"),
             "vc_sig beyond the bytes that vp_record_cb writes"),
            (without(code, "if (table == s_draw_samplers) return;", "if (table != s_draw_samplers) return;"),
             "the same sampler table reported again"),
            (without(code, "if (s_draw_stencil != reference) s_draw_cmds |= PHASE_DRAW_CMD_STENCIL;",
                      "s_draw_cmds |= PHASE_DRAW_CMD_STENCIL;"), "the same stencil reference reported again"),
            (without(code, "row->cmds = s_draw_cmds; s_draw_cmds = 0;", "row->cmds = 0;"), "the commands are lost"),
            (without(code, "    s_draw_previous[0] = s_draw_previous[1] = NULL;\n"), "the slots of the previous batch stay"),
            (without(code, "if (!phase_draw_csv_on() || !s_phase_query_n) return;\n    const unsigned char* b0",
                      "const unsigned char* b0"), "signature when off"),
        ]
        for index, (changed, label) in enumerate(controls):
            name = "control%d.exe" if os.name == "nt" else "control%d"
            control = build(name % index, changed)
            on_csv.unlink(missing_ok=True)
            result = run(control, "off", path / "run" / "rsx_phases.csv") if label == "signature when off" \
                else run(control, "on", path / "run" / "rsx_phases.csv")
            written = on_csv.read_text().splitlines() if on_csv.exists() else None
            assert result.returncode != 0 or "FAIL" in result.stderr or \
                (label != "signature when off" and written != EXPECTED), "control accepted: " + label
        if os.name == "nt":
            syntax_only(environment, args.source)
    print("PASS actual draw CSV block: default off, path, rows, flags, barriers, timestamps, readback failure, "
          "row limit, call sites, commands without a flag, constant signatures, state_eq, sampler table store, "
          "%d mutants, %d fixture controls, syntax-only backend" % (len(mutants) + len(table_mutants) + 2,
                                                                    len(controls)))


if __name__ == "__main__":
    main()
