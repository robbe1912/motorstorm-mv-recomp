"""Native D24 depth textures and packed-depth reads: actual decompiler, view and remap code.

Compiles the production rsx_fp_decompiler.c with authored TEX/TXP/TXB
instruction words (no game programs) and checks the HLSL the native depth path
emits; extracts the backend's B8 remap helper and runs it against the actual
crossbar decoder. Live mutants of each rule must fail. The D3D12 resource,
barrier and compute paths need Windows and a native run; they are not executed
here.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
INCLUDE = ROOT / 'vendor/ps3recomp/include'

DECOMPILER = r'''
#include <stdio.h>
#include <string.h>
#include "rsx_fp_decompiler.h"
static unsigned failures;
static void check(int ok, const char* name) { if (!ok) { printf("FAIL %s\n", name); ++failures; } }
static void word(unsigned char* b, unsigned v) { unsigned s = (v << 16) | (v >> 16); b[0]=s>>24; b[1]=s>>16; b[2]=s>>8; b[3]=s; }
/* op R0.xyzw, f[TEX0] (input 4), unit; then op2 R1, f[TEX1], unit2; END */
static unsigned program(unsigned char* code, unsigned op, unsigned unit, unsigned op2, unsigned unit2)
{
    memset(code, 0, 64);
    const unsigned src = 1u | (0xE4u << 9) | (7u << 18);     /* input register, xyzw, unconditional */
    word(code + 0, (op << 24) | (unit << 17) | (4u << 13) | (15u << 9) | (op2 ? 0u : 1u));
    word(code + 4, src); word(code + 8, 0xE4u << 9); word(code + 12, 0xE4u << 9);
    if (!op2) return 16;
    word(code + 16, (op2 << 24) | (unit2 << 17) | (5u << 13) | (15u << 9) | (1u << 1) | 1u);
    word(code + 20, src); word(code + 24, 0xE4u << 9); word(code + 28, 0xE4u << 9);
    return 32;
}
int main(void)
{
    static char hlsl[65536];
    unsigned char code[64];
    rsx_fp_constant_block constants; u32 count;
    rsx_depth_sample_view views[16];
    const u32 on = 0x80000000u | (3072u << 7), clamp = 0x00030303u;
    memset(views, 0, sizeof views);
    check(rsx_depth_sample_view_init(&views[13], 0xB0, 1024, 1024, 1, 0, 0, (6u << 28) | clamp,
                                     0x02020000u, on, 2048, 2048) == 1 && views[13].compare,
          "MotorStorm shadow map view: D24 LN, GEQUAL, linear");

    unsigned n = program(code, 0x18, 13, 0x17, 2);              /* TXP unit 13, TEX unit 2 */
    check(rsx_fp_texture_units(code, n) == ((1u << 13) | (1u << 2)), "texture units read");
    int r = rsx_fp_decompile_buffered_native_depth(code, n, 0x40, 0, views, hlsl, sizeof hlsl, &count, &constants);
    check(r == 2, "native program decompiles");
    check(strstr(hlsl, "SamplerComparisonState rsx_cmp13 : register(s13);") != NULL, "comparison sampler at the unit register");
    check(strstr(hlsl, "SamplerState rsx_samp2 : register(s2);") != NULL, "other units declared individually");
    check(strstr(hlsl, "SamplerState rsx_samp[16]") == NULL, "no array declaration overlaps s13");
    check(strstr(hlsl, "_rsx_depth13(((input.tc0).xyzw).xyz / ((input.tc0).xyzw).w)") != NULL, "TXP divides xyz by w");
    check(strstr(hlsl, "rsx_tex13.SampleCmpLevelZero(rsx_cmp13,uv,saturate(p.z))") != NULL, "helper compares the clamped reference");
    check(strstr(hlsl, "rsx_tex2.Sample(rsx_samp2,") != NULL, "ordinary unit renamed to its own sampler");
    check(strstr(hlsl, "rsx_samp[") == NULL, "no array sampler reference remains");

    /* The unnormalized-scale pass still finds the renamed ordinary unit. */
    u32 dims[16][2]; memset(dims, 0, sizeof dims); dims[2][0] = 64; dims[2][1] = 32;
    check(rsx_fp_apply_unnorm_scale(hlsl, sizeof hlsl, 1u << 2, (const u32 (*)[2])dims, 0) == 1,
          "unnormalized scale patches individually named samplers");

    /* Biased/explicit-LOD reads of a native unit are not expressed: fallback. */
    n = program(code, 0x31, 13, 0, 0);                           /* TXB unit 13 */
    check(rsx_fp_decompile_buffered_native_depth(code, n, 0x40, 0, views, hlsl, sizeof hlsl, &count, &constants) < 0,
          "TXB on a native unit rejects the native program");
    /* Without native views the output is the unchanged legacy text. */
    n = program(code, 0x17, 2, 0, 0);
    check(rsx_fp_decompile_buffered_ex(code, n, 0x40, 0, hlsl, sizeof hlsl, &count, &constants) == 1 &&
          strstr(hlsl, "SamplerState rsx_samp[16] : register(s0);") && strstr(hlsl, "rsx_tex[2].Sample(rsx_samp[2],"),
          "programs without native units are unchanged");
    printf("failures=%u\n", failures);
    return failures ? 1 : 0;
}
'''

REMAP = r'''
#include <stdio.h>
#include "rsx_texture_layout.h"
@FUNCTION@
int main(void)
{
    unsigned failures = 0;
    if (rsx_remap_b8_to_d3d(0xAAE4u) != 0x1000u) { puts("FAIL identity keeps the replicate mapping"); ++failures; }
    if (rsx_remap_b8_to_d3d(0u) != 0x1000u) { puts("FAIL unset control keeps the replicate mapping"); ++failures; }
    if (rsx_remap_b8_to_d3d(0xA9FFu) != (0u | (0u << 3) | (0u << 6) | (5u << 9) | (1u << 12)))
        { puts("FAIL 0xA9FF forces alpha to one"); ++failures; }
    if (rsx_remap_b8_to_d3d(0x00E4u) != (4u | (4u << 3) | (4u << 6) | (4u << 9) | (1u << 12)))
        { puts("FAIL force-zero operations"); ++failures; }
    printf("failures=%u\n", failures);
    return failures ? 1 : 0;
}
'''


def function(source, signature):
    start = source.index(signature)
    end = source.index('\n}\n', start) + 3
    return source[start:end]


def main():
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
    backend = (VIDEO / 'rsx_d3d12_backend.c').read_text(encoding='utf-8')
    # The binding path must use the B8 helper, and the A5 path must sit before
    # every other per-unit binding rule in the SRV fill.
    assert '(_bf == 0x81) ? rsx_remap_b8_to_d3d(dr->tex[_u].ctrl1)' in backend
    fill = backend[backend.index('dr->tex_rt[_u] = -1;'):]
    assert fill.index('native_depth_bind(dr, (unsigned)_u, wslot)') < fill.index('s_screen_copy'), \
        'depth reads bind before the display-sized screen-copy rule'
    render = backend[backend.index('static void render_frame('):]
    assert render.index('rsx_d3d12_depth_prepare(') < render.index('native_depth_prepare(') \
        < render.index('native_depth_bind('), 'views resolve after every attachment of the batch is prepared'
    assert 'native_depth_begin(dr, next_pso);' in backend and 'native_depth_end(dr);' in backend
    inc = (VIDEO / 'rsx_d3d12_native_depth.inc').read_text(encoding='utf-8')
    assert 'float4((z>>8)&255,z&255,s,(z>>16)&255)/255.0' in inc, 'A5 byte order R=Z[15:8] G=Z[7:0] B=S A=Z[23:16]'
    depth = (VIDEO / 'rsx_d3d12_depth.h').read_text(encoding='utf-8')
    assert 'description.Format = DXGI_FORMAT_R24G8_TYPELESS;' in depth and \
        'view.Format = DXGI_FORMAT_D24_UNORM_S8_UINT;' in depth, 'attachments are typeless with a typed DSV'
    decompiler = (VIDEO / 'rsx_fp_decompiler.c').read_text(encoding='utf-8')
    remap = REMAP.replace('@FUNCTION@', function(backend, 'static u32 rsx_remap_b8_to_d3d(u32 c1)'))
    layout_c = VIDEO / 'rsx_texture_layout.c'
    with tempfile.TemporaryDirectory(prefix='rsx-native-depth-') as directory:
        out = Path(directory)

        def build(name, text, sources):
            unit = out / (name + '.c')
            unit.write_text(text, encoding='utf-8')
            exe = out / (name + ('.exe' if os.name == 'nt' else ''))
            files = [str(unit)] + [str(s) for s in sources]
            if os.name == 'nt':
                command = [env['MV_CLANG'], '/nologo', '/I' + str(INCLUDE), '/I' + str(VIDEO), *files,
                           '/Fe' + str(exe), '/Fo' + str(out) + os.sep]
            else:
                command = [env.get('CC', 'cc'), '-std=c11', '-I' + str(INCLUDE), '-I' + str(VIDEO), *files,
                           '-o', str(exe), '-lm']
            compiled = subprocess.run(command, cwd=out, env=env, capture_output=True, text=True, timeout=120)
            if compiled.returncode:
                raise SystemExit(compiled.stdout + compiled.stderr)
            return subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)

        def mutant_source(name, before, after):
            assert decompiler.count(before) == 1, name
            path = out / (name + '_decompiler.c')
            path.write_text(decompiler.replace(before, after), encoding='utf-8')
            return path

        result = build('decompiler', DECOMPILER, [VIDEO / 'rsx_fp_decompiler.c'])
        assert result.returncode == 0 and 'failures=0' in result.stdout, result.stdout + result.stderr
        print('actual decompiler:', result.stdout.strip())
        result = build('remap', remap, [layout_c])
        assert result.returncode == 0 and 'failures=0' in result.stdout, result.stdout + result.stderr
        print('actual B8 remap:', result.stdout.strip())
        mutants = [
            ('no-rename', '    if (native_mask) {\n        /* Individual sampler declarations: rewrite only the identifiers the',
             '    if (0) {\n        /* Individual sampler declarations: rewrite only the identifiers the',
             'ordinary unit renamed to its own sampler'),
            ('array-samplers', '    if (native_mask) {\n        /* A comparison sampler must be its own declaration',
             '    if (0) {\n        /* A comparison sampler must be its own declaration',
             'comparison sampler at the unit register'),
            ('txb-accepted', '            if ((native_mask >> tex_unit) & 1u) return -1;\n', '',
             'TXB on a native unit rejects the native program'),
        ]
        for name, before, after, failure in mutants:
            result = build('mutant-' + name, DECOMPILER, [mutant_source(name, before, after)])
            assert result.returncode != 0 and 'FAIL ' + failure in result.stdout, (name, result.stdout)
            print('mutant', name, 'caught:', failure)
        old = remap.replace(function(backend, 'static u32 rsx_remap_b8_to_d3d(u32 c1)'),
                            'static u32 rsx_remap_b8_to_d3d(u32 c1) { (void)c1; return 0x1000u; }\n')
        result = build('mutant-fixed-b8', old, [layout_c])
        assert result.returncode != 0 and 'FAIL 0xA9FF forces alpha to one' in result.stdout, result.stdout
        print('mutant fixed-b8 caught: 0xA9FF forces alpha to one')
    print('PASS: native depth HLSL, sampler naming, TXB fallback, B8 remap and live mutants')


if __name__ == '__main__':
    main()
