"""Execute the actual guest sampler decoder, table owner and retirement adapter.

Compiles the production rsx_d3d12_guest_sampler.h and
rsx_d3d12_sampler_tables.inc, plus vp_upload_retire extracted from the backend,
against authored owner-tagged COM objects (scripts/fixtures). Covers checked
retirement (device error, incomplete fence, removed sentinel), shutdown and
re-initialization on a new device, the compiled pixel-shader sampler mask for
tables and draw merging, and live mutants of each fix.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
FIX = ROOT / 'scripts/fixtures'
INC = 'rsx_d3d12_sampler_tables.inc'


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    clean = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"',
                   lambda match: ' ' * len(match[0]), source)
    depth, end = 1, opening + 1
    while depth:
        depth += (clean[end] == '{') - (clean[end] == '}')
        end += 1
    return source[start:end]


def source_checks(source):
    render = function(source, 'static void render_frame(')
    assert render.index('gpu_pso_retire();') < render.index('guest_sampler_retire();') \
        < render.index('phase_gpu_collect();'), 'retire sampler tables after checked PSO retirement'
    assert 'guest_sampler_bind(dr, dpso ? dsampler_mask : 0u)' in render, \
        'bind with the active compiled pixel-shader sampler mask'
    assert render.index('dsampler_mask = s_pso_sampler_mask;') < render.index('guest_sampler_bind('), \
        'capture the mask from this draw\'s vp_get_fp_pso result'
    shutdown = function(source, 'void rsx_d3d12_backend_shutdown(')
    assert shutdown.index('gpu_working_sets_release();') < shutdown.index('guest_sampler_shutdown();'), \
        'shutdown releases sampler owners after checked working-set retirement'
    start = source.index('static ID3D12PipelineState* vp_get_fp_pso(int vs_idx')
    pso = source[start:source.index('\n}\n', start)]   # char literals defeat brace matching
    assert 'key.sampler_mask = rsx_guest_sampler_mask(hlsl);' in pso
    assert 'guest_sampler_note_mask(key.ucode_hash, key.sampler_mask);' in pso
    assert 's_pso_sampler_mask = s_d3d.vp_fp[i].pso ? s_d3d.vp_fp[i].sampler_mask : 0;' in pso
    merge = function(source, 'static int vp_triangle_can_merge(')
    assert 'guest_sampler_matches(pv)' in merge
    assert 'rsx_guest_sampler_regs sampler[16];' in source and 'u32 fp_snap;' in source
    assert 'u32 sampler_mask;' in source and '#define VP_FPSNAP_MAX 512' in source
    # Static samplers are gone: every VP draw binds a root-parameter-3 table.
    assert 'rd.NumStaticSamplers = 0;' in source and 'rp[3].ParameterType = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;' in source


def main():
    source = (VIDEO / 'rsx_d3d12_backend.c').read_text(encoding='utf-8')
    source_checks(source)
    retire = function(source, 'static int vp_upload_retire(')
    template = (FIX / 'rsx_sampler_tables.c.in').read_text(encoding='utf-8')
    unit_text = template.replace('@VP_UPLOAD_RETIRE@', retire)
    inc = (VIDEO / INC).read_text(encoding='utf-8')
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
    with tempfile.TemporaryDirectory(prefix='rsx-sampler-tables-') as directory:
        out = Path(directory)

        def build(name, inc_text):
            include = out / (name + '-src')
            include.mkdir()
            shutil.copy(FIX / 'rsx_sampler_d3d12_mock.h', include / 'd3d12.h')
            shutil.copy(VIDEO / 'rsx_d3d12_guest_sampler.h', include / 'rsx_d3d12_guest_sampler.h')
            (include / INC).write_text(inc_text, encoding='utf-8')
            unit = include / 'test.c'
            unit.write_text(unit_text, encoding='utf-8')
            exe = out / (name + ('.exe' if os.name == 'nt' else ''))
            if os.name == 'nt':
                command = [env['MV_CLANG'], '/nologo', '/I' + str(include), str(unit),
                           '/Fe' + str(exe), '/Fo' + str(include) + os.sep]
            else:
                command = [env.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                           '-Wno-unused-function', '-I' + str(include), str(unit), '-o', str(exe)]
            subprocess.run(command, cwd=out, env=env, check=True, timeout=60)
            return exe

        def run(exe, args=()):
            return subprocess.run([str(exe), *args], capture_output=True, text=True, timeout=15)

        actual = build('actual', inc)
        for args in [[], ['device'], ['incomplete'], ['removed-sentinel'], ['shutdown-failed']]:
            result = run(actual, args)
            assert result.returncode == 0 and 'failures=0' in result.stdout, (args, result)
            print('actual', ' '.join(args) or 'default', result.stdout.strip().splitlines()[-1])

        # Each review finding, reintroduced into the production include, must fail.
        mutants = [
            ('unchecked-retire', '    if (!vp_upload_retire(NULL)) {', '    if (0) {',
             ['incomplete'], 'failed retirement keeps overflow heaps'),
            ('unchecked-retire-device', '    if (!vp_upload_retire(NULL)) {', '    if (0) {',
             ['device'], 'failed retirement keeps overflow heaps'),
            ('every-bound-unit', 'rsx_guest_sampler_table(dr->sampler, set, mask, desc)',
             'rsx_guest_sampler_table(dr->sampler, set, mask | 0xFFFFu, desc)', [],
             'unused unit changes create no sampler identities'),
            ('merge-every-unit', '        if (!(mask & (1u << u))) continue;\n', '        (void)mask;\n', [],
             'unsampled unit change does not split a merge'),
            ('merge-disabled-units', '        if (!rsx_guest_sampler_same(&dr->sampler[u], &now)) return 0;',
             '        if (memcmp(&dr->sampler[u], &now, sizeof now)) return 0;', [],
             'unit disabled on both sides does not split a merge'),
            ('shutdown-keeps-owners', '    s_sampler_base = s_sampler_overflow = NULL;\n', '', [],
             'shutdown clears every owner'),
            ('shutdown-releases-unchecked', '            if (retired && h->heap) h->heap->lpVtbl->Release(h->heap);',
             '            if (h->heap) h->heap->lpVtbl->Release(h->heap);', ['shutdown-failed'],
             'failed shutdown retirement never releases heaps'),
        ]
        for name, before, after, args, failure in mutants:
            assert inc.count(before) == 1, name
            result = run(build(name, inc.replace(before, after)), args)
            assert result.returncode != 0 and 'FAIL ' + failure in result.stdout, (name, result)
            print('mutant', name, 'caught:', failure)
    print('PASS: sampler decoder, compiled-PS mask, checked retirement, shutdown/re-init and mutants')


if __name__ == '__main__':
    main()
