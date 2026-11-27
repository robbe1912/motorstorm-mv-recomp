"""Check the vp_get_vs lookup memo against the microcode it must follow, no GPU.

Compiles the production vp_get_vs, vp_hash_ucode and VPVSEntry from
rsx_d3d12_backend.c with the production NV4097_SET_TRANSFORM_PROGRAM write
from rsx_commands.c, and stubs only the decompiler and shader compiler.
A random schedule of microcode writes (new and identical words), start-slot
changes, state copies and resets, frame ends and cache evictions in a 4-slot
cache checks every draw: the returned slot holds the hash of the program the
state selects now, takes one reference and is stamped this frame. Repeated
draws must not walk the program again. Five source mutants must fail.
No game input; no performance claim.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'

PREFIX = r'''
#include "rsx_commands.h"
#include "rsx_vp_decompiler.h"
#include "rsx_vp_layout.h"
#include "rsx_env_once.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef long HRESULT;
#define FAILED(h) ((h) < 0)
typedef struct ID3DBlob ID3DBlob;
typedef struct { unsigned long (*Release)(ID3DBlob*); } ID3DBlobVtbl;
struct ID3DBlob { const ID3DBlobVtbl* lpVtbl; };
static unsigned long blob_release(ID3DBlob* b) { free(b); return 0; }
static const ID3DBlobVtbl blob_vtbl = { blob_release };
@VPVSENTRY@
#define VP_VS_CACHE 4
static struct {
    VPVSEntry vp_vs[VP_VS_CACHE]; int vp_vs_n; u64 frame_count;
    const rsx_state* current_rsx_state; int vp_ready; struct { u32 raw; } cur_texs[16];
} s_d3d;
static size_t s_vs_disk_source_bytes;
static unsigned extent_calls, compiles;
/* Program extent: through the first instruction whose first byte is 0xEE. */
static u32 ref_extent(const u8* uc, u32 max)
{ u32 n = 0; while ((n + 1) * 16 <= max) { ++n; if (uc[(n - 1) * 16] == 0xEE) break; } return n; }
u32 rsx_vp_program_extent_instrs(const u8* uc, u32 max, u32 start)
{ (void)start; ++extent_calls; return ref_extent(uc, max); }
int rsx_vp_decompile(const u8* uc, u32 n, char* out, u32 size)
{ (void)uc; (void)n; snprintf(out, size, "float4 main() : SV_Position { return 0; }"); return 1; }
int rsx_vp_decompile_compact_ex(const u8* a, u32 b, u32 c, u32 d, char* e, u32 f)
{ (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; abort(); }
int rsx_vp_analyze_inputs(const u8* a, u32 b, rsx_vp_input_analysis* c)
{ (void)a; (void)b; (void)c; abort(); }
void rsx_vp_set_branch_base(u32 s) { (void)s; }
static int vp_compact_on(void) { return 0; }
static HRESULT shader_compile_vs(const char* h, ID3DBlob** vb, ID3DBlob** e, char** src)
{
    (void)h; ++compiles; *e = NULL; *src = NULL;
    *vb = (ID3DBlob*)malloc(sizeof **vb); if (!*vb) abort();
    (*vb)->lpVtbl = &blob_vtbl; return 0;
}
static void shader_forget_vs_source(char* s) { free(s); }
static void compile_vp(void) { s_d3d.vp_ready = 1; }
static int ucode_method(rsx_state* state, u32 method, u32 data)
{
@UCODE_METHOD@
    return 1;
}
@VP_HASH@
@VP_GET_VS@
'''

CHECK = r'''
#define CHECK(x, m) do { if (!(x)) { fprintf(stderr, "FAIL %s (step %u, line %d)\n", m, step, __LINE__); exit(1); } } while (0)
static rsx_state states[2];
static unsigned step;
static u32 rng = 12345u;
static u32 next(void) { rng = rng * 1664525u + 1013904223u; return rng >> 8; }
/* Program k at instruction slot s: len instructions, the last marked 0xEE. */
static void load(rsx_state* s, u32 slot, u32 k, u32 len)
{
    s->vp_ucode_write = slot * 16;
    for (u32 i = 0; i < len * 4; ++i) {
        u32 w = (k * 2654435761u) ^ (i * 40503u);
        if (i % 4 == 0) w = (w & ~0xFFu) | (i / 4 + 1 == len ? 0xEEu : (w & 0x7Fu));
        CHECK(!ucode_method(s, NV4097_SET_TRANSFORM_PROGRAM + 4 * (i % 32), w), "ucode write not handled");
    }
}
static u32 expected_hash(const rsx_state* s)
{
    u32 vstart = s->transform_program_start * 16u;
    if (vstart >= s->vp_ucode_bytes) vstart = 0;
    u32 n = ref_extent(s->vp_ucode + vstart, s->vp_ucode_bytes - vstart);
    return vp_hash_ucode(s->vp_ucode + vstart, n * 16u);
}
static void draw(rsx_state* s)
{
    u32 refs[VP_VS_CACHE]; int n_before = s_d3d.vp_vs_n;
    for (int i = 0; i < VP_VS_CACHE; ++i) refs[i] = s_d3d.vp_vs[i].refs;
    s_d3d.current_rsx_state = s;
    int r = vp_get_vs(s);
    if (s->vp_ucode_bytes < 16) { CHECK(r == -1, "empty store drew"); return; }
    if (r < 0) {
        int busy = 1; for (int i = 0; i < s_d3d.vp_vs_n; ++i) busy &= refs[i] != 0;
        CHECK(busy && s_d3d.vp_vs_n == VP_VS_CACHE, "lookup failed with a free slot");
        return;
    }
    CHECK(r < s_d3d.vp_vs_n && s_d3d.vp_vs[r].hash == expected_hash(s), "stale program");
    const int fresh = r >= n_before || s_d3d.vp_vs[r].refs == 1;
    CHECK(fresh || s_d3d.vp_vs[r].refs == refs[r] + 1, "reference not taken");
    for (int i = 0; i < VP_VS_CACHE; ++i)
        if (i != r && i < n_before) CHECK(s_d3d.vp_vs[i].refs == refs[i], "reference taken on another slot");
    CHECK(s_d3d.vp_vs[r].last_frame == s_d3d.frame_count, "slot not stamped this frame");
}
static void end_frame(void)
{ for (int i = 0; i < VP_VS_CACHE; ++i) s_d3d.vp_vs[i].refs = 0; s_d3d.frame_count++; }
int main(void)
{
    static const u32 starts[] = {0, 8, 16, 24, 1, 9};
    for (step = 0; step < 200000; ++step) {
        rsx_state* s = &states[next() % 2];
        u32 op = next() % 100;
        if (op < 55) draw(s);
        else if (op < 70) load(s, starts[next() % 6], next() % 6, 1 + next() % 4);
        else if (op < 82) s->transform_program_start = starts[next() % 6];
        else if (op < 88) end_frame();
        else if (op < 91) states[1] = states[0];
        else if (op < 94) states[0] = states[1];
        else if (op < 95) memset(s, 0, sizeof *s);
        else if (op < 96) { end_frame(); s_d3d.vp_vs_n = 0; }
        else { u32 w = s->vp_ucode_write; load(s, starts[next() % 6], 1, 2); s->vp_ucode_write = w; }
    }
    /* Repeats of one program must not walk or hash it again. */
    end_frame(); memset(&states[0], 0, sizeof states[0]);
    load(&states[0], 8, 3, 3); states[0].transform_program_start = 8;
    draw(&states[0]); unsigned walked = extent_calls, built = compiles;
    for (int i = 0; i < 100; ++i) draw(&states[0]);
    CHECK(extent_calls == walked && compiles == built, "memo unused");
    load(&states[0], 8, 3, 3); draw(&states[0]);
    CHECK(extent_calls == walked + 1 && compiles == built, "rewrite did not revalidate");
    printf("PASS vp_get_vs memo: %u steps, %u compiles, %u extent walks\n", step, compiles, extent_calls);
    return 0;
}
'''

MUTANTS = [
    # Epoch set by a state's first write only: a later rewrite keeps it.
    ('epoch-first-write-only', 'rsx_commands.c',
     '{ static u64 s_vp_ucode_epoch; state->vp_ucode_epoch = ++s_vp_ucode_epoch; }',
     '{ static u64 s_vp_ucode_epoch; if (!state->vp_ucode_epoch) state->vp_ucode_epoch = ++s_vp_ucode_epoch; }',
     'stale program'),
    ('memo-ignores-start', 'rsx_d3d12_backend.c',
     'memo[memo_i].vstart == vstart && ', '', 'stale program'),
    ('memo-ignores-eviction', 'rsx_d3d12_backend.c',
     'm >= 0 && m < s_d3d.vp_vs_n &&\n            s_d3d.vp_vs[m].hash == memo[memo_i].hash) {',
     'm >= 0 && m < s_d3d.vp_vs_n) {', 'stale program'),
    ('memo-hit-no-reference', 'rsx_d3d12_backend.c',
     '            s_d3d.vp_vs[m].refs++;\n            s_d3d.vp_vs[m].last_frame', '            s_d3d.vp_vs[m].last_frame',
     'reference not taken'),
    ('no-memo', 'rsx_d3d12_backend.c',
     'const int use_memo = !pick && st->vp_ucode_epoch != 0;', 'const int use_memo = 0;', 'memo unused'),
]


def function(text, signature):
    start = text.index(signature)
    return text[start:text.index('\n}\n', start) + 3]


def compose(backend, commands):
    entry_start = backend.index('typedef struct {\n    u32 hash;')
    entry = backend[entry_start:backend.index('} VPVSEntry;', entry_start) + len('} VPVSEntry;')]
    method_start = commands.index('    if (method >= NV4097_SET_TRANSFORM_PROGRAM &&')
    method = commands[method_start:commands.index('\n        return 0;\n    }\n', method_start) + len('\n        return 0;\n    }\n')]
    return (PREFIX.replace('@VPVSENTRY@', entry).replace('@UCODE_METHOD@', method)
            .replace('@VP_HASH@', function(backend, 'static u32 vp_hash_ucode('))
            .replace('@VP_GET_VS@', function(backend, 'static int vp_get_vs(')) + CHECK)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default=os.environ.get('CC'))
    args = parser.parse_args()
    sources = {name: (VIDEO / name).read_text(encoding='utf-8').replace('\r\n', '\n')
               for name in ('rsx_d3d12_backend.c', 'rsx_commands.c')}
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('vp-get-memo-' + stamp)
    out.mkdir(parents=True)
    env = os.environ.copy()
    msvc = os.name == 'nt' and not args.cc
    if msvc:
        from project import build_environment
        env = build_environment()
        compiler = env['MV_CLANG']
    else:
        compiler = shutil.which(args.cc or 'cc')
        if not compiler:
            raise SystemExit('Select a C11 compiler with --cc or CC')
    for key in list(env):
        if key.startswith(('RSX_', 'VP_', 'VTX_', 'FP_')):
            env.pop(key)
    inputs = [VIDEO / n for n in ('rsx_d3d12_backend.c', 'rsx_commands.c', 'rsx_commands.h',
                                 'rsx_vp_decompiler.h', 'rsx_vp_layout.h', 'rsx_env_once.h')] + [Path(__file__)]
    result = dict(game_inputs=False, gpu_execution=False, compiler=compiler, checks=[],
                  production_functions=['vp_get_vs', 'vp_hash_ucode', 'NV4097_SET_TRANSFORM_PROGRAM write'],
                  source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs})

    def build_run(name, code, expected):
        c = out / (name + '.c')
        exe = out / (name + ('.exe' if os.name == 'nt' else ''))
        c.write_text(code, encoding='utf-8')
        includes = [VIDEO, ROOT / 'vendor/ps3recomp/include']
        if msvc:
            command = [compiler, '/nologo', '/std:c17', '/O2', *['/I' + str(p) for p in includes],
                       str(c), '/Fe' + str(exe), '/Fo' + str(out / (name + '.obj'))]
        else:
            command = [compiler, '-std=c11', '-O2', *['-I' + str(p) for p in includes], str(c), '-o', str(exe)]
        built = subprocess.run(command, env=env, cwd=out, capture_output=True, timeout=120)
        (out / (name + '-build.log')).write_bytes(built.stdout + built.stderr)
        if built.returncode:
            raise RuntimeError(name + ': ' + (built.stdout + built.stderr).decode(errors='replace'))
        ran = subprocess.run([str(exe)], env=env, cwd=out, capture_output=True, timeout=120)
        output = (ran.stdout + ran.stderr).decode(errors='replace')
        (out / (name + '-run.log')).write_text(output, encoding='utf-8')
        result['checks'].append(dict(name=name, returncode=ran.returncode, expected=expected or 'PASS'))
        if expected:
            if ran.returncode == 0 or 'FAIL ' + expected not in output:
                raise RuntimeError(name + ' was not rejected for ' + expected + ': ' + output)
            print(name + ': rejected: ' + output.strip())
        else:
            if ran.returncode or 'PASS' not in output:
                raise RuntimeError(name + ': ' + output)
            print(name + ': ' + output.strip())

    try:
        build_run('actual', compose(sources['rsx_d3d12_backend.c'], sources['rsx_commands.c']), None)
        for name, file, before, after, why in MUTANTS:
            changed = dict(sources)
            if changed[file].count(before) != 1:
                raise RuntimeError('mutant anchor changed: ' + name)
            changed[file] = changed[file].replace(before, after)
            build_run(name, compose(changed['rsx_d3d12_backend.c'], changed['rsx_commands.c']), why)
        result['passed'] = True
        print('PASS: production vp_get_vs memo follows microcode, start, copies, resets and eviction; 5 mutants caught')
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print('Evidence:', out)


if __name__ == '__main__':
    main()
