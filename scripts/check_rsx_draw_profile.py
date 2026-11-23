#!/usr/bin/env python3
"""Game-free checks for the per-draw GPU record (rsx_draws.csv).

1. Audits rsx_d3d12_backend.c and scripts/run.py: the record starts only with
   the per-draw timestamp switch and a phase CSV path. The call sites of the
   record sit next to the state changes, the draw and the timestamp readback
   that they observe. Mutants must fail.
2. Compiles the production record block with an authored fixture: off by
   default; path derivation; row facts, flags, barrier count, draw time and
   the time before the draw; a row without an end timestamp; a failed
   readback; the row limit with one log line.
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
HEADER = ("batch,draw,verts,idx,prim,rt0,rt1,rt2,rt3,zeta,vp_w,vp_h,vs,fp,fp_snap,"
          "rt_chg,vp_chg,pso_chg,srv_chg,barriers,gap_us,gpu_us")
ROW_CALL = "phase_draw_row(dr, d, row_flags, s_rt_barriers - row_barriers);\n"
WRITE_CALL = "phase_draw_rows_write(ticks, s_phase_query_n, s_phase_gpu_frame, s_phase_frequency);"
RESET = "phase_draw_batch_begin();"
RESET_ROWS = "u32 row_flags = 0, row_barriers = s_rt_barriers;"
LIMIT = 5

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
typedef struct {
    u32 vertex_count, topology, rt_off, zeta_off, rt_mrt[3], vp_w, vp_h, fp_addr, fp_snap;
    int vs_idx;
    u32 depth_sample_mask;
    u8 depth_sampled_slot[16];
} D3D12DrawRecord;
static int s_phase_gpu_draws;
static void* s_phase_readback;
static u32 s_phase_query_n;
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
/* Draw A: display target, full viewport, no state change. */
static void row_a(void)
{
    D3D12DrawRecord dr = {0};
    dr.vertex_count = 12; dr.topology = 4; dr.rt_off = 0x1BE0000; dr.rt_mrt[0] = 0xAB00;
    dr.zeta_off = 0x0C000000; dr.vp_w = 1280; dr.vp_h = 720; dr.vs_idx = 2;
    dr.fp_addr = 0x036CC2C1; dr.fp_snap = 9;
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
    phase_draw_row(&dr, 4, PHASE_DRAW_TARGETS | PHASE_DRAW_PSO, 3);
}
/* Draw C: viewport and SRV table change. */
static void row_c(void)
{
    D3D12DrawRecord dr = {0};
    dr.vertex_count = 6; dr.topology = 4;
    phase_draw_row(&dr, 5, PHASE_DRAW_VIEWPORT | PHASE_DRAW_SRV, 0);
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
    /* Microseconds. Index 0 is the batch timestamp, then one pair per draw. */
    u64 ticks[16] = {1000, 1100, 1200, 1300, 1500, 1700, 1900, 2000, 2100};
    if (strcmp(mode, "off") == 0) {
        check(phase_draw_csv_on() == 0, "no record without per-draw timestamps");
        s_phase_query_n = 1;
        phase_draw_batch_begin();
        check(phase_draw_viewport(0, 0, 1, 1, 0, 0, 1, 1) == 0, "no viewport tracking when off");
        draw(row_a, 1);
        check(s_draw_rows_n == 0, "no row when off");
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
        /* Batch 7: three draws with an end timestamp, one without. */
        s_phase_query_n = 1;
        draw(row_a, 1); draw(row_b, 1); draw(row_c, 1);
        draw(row_a, 0);
        check(s_draw_rows_n == 4, "four rows held");
        phase_draw_rows_write(ticks, 9, 7, 1000000);
        check(s_draw_rows_n == 0 && s_draw_csv_rows == 3, "three rows written, the fourth has no end timestamp");
        s_phase_query_n = 1;
        draw(row_b, 1);
        phase_draw_rows_write(NULL, 4, 8, 1000000);
        check(s_draw_rows_n == 0 && s_draw_csv_rows == 3, "failed readback drops the rows");
        /* Batch 8 writes again. */
        s_phase_query_n = 1;
        draw(row_c, 1);
        phase_draw_rows_write(ticks, 4, 8, 1000000);
        check(s_draw_csv_rows == 4, "the next batch writes after a failed readback");
        /* Batch 9 holds three rows. The limit lets one through. */
        s_phase_query_n = 1;
        draw(row_a, 1); draw(row_b, 1); draw(row_c, 1);
        phase_draw_rows_write(ticks, 8, 9, 1000000);
        check(s_draw_csv_rows == PHASE_DRAW_ROWS_MAX && s_draw_csv_stopped == 1, "the file stops at the row limit");
        s_phase_query_n = 1;
        draw(row_a, 1);
        phase_draw_rows_write(ticks, 4, 10, 1000000);
        check(s_draw_csv_rows == PHASE_DRAW_ROWS_MAX && s_draw_rows_n == 0, "a stopped file takes no rows");
        const char* expected[] = {
            "@HEADER@",
            "7,3,12,0,4,01BE0000,0000AB00,00000000,00000000,0C000000,1280,720,2,036CC2C1,9,0,0,0,0,0,100.000,100.000",
            "7,4,300,0,4,00000000,00000000,00000000,00000000,00000000,320,180,-1,00000010,0,1,0,1,0,7,100.000,200.000",
            "7,5,6,0,4,00000000,00000000,00000000,00000000,00000000,0,0,0,00000000,0,0,1,0,1,0,200.000,200.000",
            "8,5,6,0,4,00000000,00000000,00000000,00000000,00000000,0,0,0,00000000,0,0,1,0,1,0,100.000,100.000",
            "9,3,12,0,4,01BE0000,0000AB00,00000000,00000000,0C000000,1280,720,2,036CC2C1,9,0,0,0,0,0,100.000,100.000"};
        FILE* file = fopen(phase_draw_csv_path(), "r");
        check(file != NULL, "the file exists next to the phase CSV");
        if (file) {
            char line[512];
            size_t n;
            for (n = 0; n < sizeof expected / sizeof *expected && fgets(line, sizeof line, file); n++)
                check(strlen(line) > 0 && line[strlen(line) - 1] == '\n' &&
                      strncmp(line, expected[n], strlen(line) - 1) == 0 &&
                      strlen(expected[n]) == strlen(line) - 1, expected[n]);
            check(n == sizeof expected / sizeof *expected, "header and five rows only");
            check(!fgets(line, sizeof line, file), "no trailing row");
            fclose(file);
        }
    }
    printf("draw profile checks=%d failures=%d\n", checks, failures);
    return failures ? 1 : 0;
}
'''


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
    match = re.search(r"\bstatic\s+(?:void|int|u32|const char\*)\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", source)
    assert match, "missing actual helper: " + name
    return balanced(source, match.start(), name)


def block_at(text, at, pattern):
    return balanced(text, text.index("{", at), pattern)


def record_block(source):
    assert source.count(BEGIN) == 1 and source.count(END) == 1, "one draw CSV block required"
    return source[source.index(BEGIN):source.index(END)]


def audit(source, launcher):
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
    switch = "env['RSX_PHASE_GPU_DRAWS']='1'"
    assert switch in launcher and launcher.index("if args.profile_renderer_draws:") < launcher.index(switch), \
        "the launcher sets RSX_PHASE_GPU_DRAWS with --profile-renderer-draws"


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
    args = parser.parse_args()
    source = args.source.read_text()
    launcher = args.launcher.read_text()
    audit(source, launcher)
    row_line = "                " + ROW_CALL
    text = record_block(source)
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
    ]
    for index, mutant in enumerate(mutants):
        try:
            audit(mutant, launcher)
        except (AssertionError, ValueError):
            pass
        else:
            raise AssertionError("mutant %d accepted" % index)
    for index, mutant in enumerate((launcher.replace("env['RSX_PHASE_GPU_DRAWS']='1'", "", 1),
                                    launcher.replace("if args.profile_renderer_draws:", "if False:", 1))):
        try:
            audit(source, mutant)
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
        c.write_text(code)
        if Path(compiler).stem.lower() in ("cl", "clang-cl"):
            command = [compiler, "/nologo", "/W4", "/WX", "/std:c11", str(c), "/Fe" + str(exe)]
        else:
            command = [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(c), "-o", str(exe)]
        built = subprocess.run(command, cwd=path, env=environment, capture_output=True, text=True,
                               errors="replace", timeout=180)
        assert built.returncode == 0, built.stdout + built.stderr

        def run(mode, phase_csv):
            arguments = [str(exe), mode] + ([str(phase_csv)] if phase_csv is not None else [])
            result = subprocess.run(arguments, cwd=path, env=environment, capture_output=True, text=True,
                                    errors="replace", timeout=30)
            assert result.returncode == 0 and "FAIL" not in result.stderr, mode + ": " + result.stderr
            assert "draw profile checks=" in result.stdout, result.stdout
            return result

        (path / "sub").mkdir()
        (path / "run").mkdir()
        for phase_csv in (path / "off" / "rsx_phases.csv", "rsx_phases.csv"):
            result = run("off", phase_csv)
            assert "[RSXPHASE] Draw CSV" not in result.stderr, "the default run logs no draw CSV"
            assert not (path / phase_csv).with_name("rsx_draws.csv").exists(), "the default run writes no draw CSV"
        for phase_csv in (None, "-"):
            result = run("nopath", phase_csv)
            assert result.stderr.count("[RSXPHASE] Draw CSV off: RSX_PHASE_CSV gives no path\n") == 1, result.stderr
        for phase_csv in (path / "run" / "rsx_phases.csv", "sub/rsx_phases.csv", "rsx_phases.csv"):
            result = run("on", phase_csv)
            # The record keeps the separator and directory of the phase CSV path.
            head, separator, _ = str(phase_csv).rpartition("/")
            expected = str(phase_csv.with_name("rsx_draws.csv")) if isinstance(phase_csv, Path) \
                else head + separator + "rsx_draws.csv"
            assert "[RSXPHASE] Draw CSV %s (stops at %d rows)\n" % (expected, LIMIT) in result.stderr, result.stderr
            assert result.stderr.count("[RSXPHASE] Draw CSV stopped at %d rows: %s\n" % (LIMIT, expected)) == 1, \
                "one stop line: " + result.stderr
            assert "draw profile checks=21 failures=0" in result.stdout, result.stdout
            lines = (path / expected).read_text().splitlines()
            assert lines[0] == HEADER and len(lines) == LIMIT + 1
        if os.name == "nt":
            syntax_only(environment, args.source)
    print("PASS actual draw CSV block: default off, path, rows, flags, barriers, timestamps, readback failure, "
          "row limit, call sites, %d mutants, syntax-only backend" % (len(mutants) + 2))


if __name__ == "__main__":
    main()
