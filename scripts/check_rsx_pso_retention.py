"""Exercise recorded PSO ownership and the actual backend draw/retire adapters."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
FIX = ROOT / 'scripts/fixtures'


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


def main():
    source = (VIDEO / 'rsx_d3d12_backend.c').read_text(encoding='utf-8')
    signatures = ['static void gpu_pso_add(', 'static void gpu_pso_release(',
                  'static int vp_upload_retire(', 'static void gpu_pso_draw(',
                  'static void gpu_pso_retire(']
    bodies = [function(source, signature) for signature in signatures]
    # New draws must use the ownership adapter, including diagnostic paths.
    draw = bodies[3]
    assert source.count('->DrawInstanced(') == draw.count('->DrawInstanced(') == 1, \
        'Route every draw through gpu_pso_draw so recorded PSOs stay alive'
    render = function(source, 'static void render_frame(')
    shutdown = function(source, 'void rsx_d3d12_backend_shutdown(')
    assert render.index('gpu_pso_retire();') < render.index('phase_gpu_collect();')
    assert shutdown.index('gpu_working_sets_release();') < shutdown.index('shader_pool_finish();')
    assert shutdown.index('gpu_working_sets_release();') < shutdown.index('->Release(')
    with tempfile.TemporaryDirectory(prefix='pso-retention-') as directory:
        out = Path(directory)
        env = os.environ.copy()
        if os.name == 'nt':
            from project import build_environment
            env = build_environment()
        def build(name, text):
            unit = out / (name + '.c')
            exe = out / (name + ('.exe' if os.name == 'nt' else ''))
            unit.write_text(text, encoding='utf-8')
            if os.name == 'nt':
                command = [env['MV_CLANG'], '/nologo', '/I' + str(VIDEO),
                           str(unit), '/Fe' + str(exe), '/Fo' + str(out) + os.sep]
            else:
                command = [env.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra',
                           '-Wno-unused-function', '-Werror', '-I' + str(VIDEO), str(unit), '-o', str(exe)]
            subprocess.run(command, cwd=out, env=env, check=True, timeout=60)
            return exe
        def run(exe, args=(), failure=None, expected_exit=None):
            result = subprocess.run([str(exe), *args], capture_output=True, text=True, timeout=15)
            if failure:
                assert result.returncode and failure in result.stderr, result
            else:
                assert result.returncode == 0 and 'failures=0' in result.stdout, result
            if expected_exit is not None:
                assert result.returncode == expected_exit, result
        collection = build('collection', (FIX / 'rsx_gpu_references.c').read_text())
        run(collection)
        run(collection, ['--no-recorded-reference'], 'recorded PSO survives')
        prefix = (FIX / 'rsx_pso_retention.c.in').read_text()
        limits = '\n'.join(re.search(r'^#define ' + name + r'[^\n]*', source, re.M).group(0)
                           for name in ['MAX_DRAWS', 'RSX_GPU_REFERENCES_MAX'])
        prefix = prefix.replace('#define RSX_GPU_REFERENCES_MAX 2049', limits)
        ops = 'static const rsx_gpu_reference_ops s_gpu_pso_ops = {NULL, gpu_pso_add, gpu_pso_release, vp_upload_retire};'
        adapter = prefix.replace('@FUNCTIONS@', '\n'.join(bodies[:3] + [ops] + bodies[3:]))
        actual = build('actual', adapter)
        run(actual)
        for mode in ['device', 'incomplete', 'removed-sentinel','wait-failed']:
            run(actual, [mode], 'PSO GPU retirement failed', expected_exit=77)
        # Missing hold reproduces the original cache-eviction defect. A failed
        # retirement must never free the recorded command list's borrowed PSOs.
        hold = 'rsx_gpu_reference_hold(&s_gpu_pso_refs, pso, &s_gpu_pso_ops)'
        assert hold in adapter
        run(build('omitted-hold', adapter.replace(hold, '((void)pso, 1)')),
            failure='recorded PSO survives cache eviction')
        before = 'return removed == S_OK && completed != UINT64_MAX &&'
        assert before in adapter
        run(build('unchecked-retire', adapter.replace(before, '(void)removed; return')),
            ['device'], failure='failed retirement released recorded PSO')
        release = function(source, 'static void gpu_working_sets_release(')
        lifecycle = (FIX / 'rsx_working_sets.c.in').read_text()
        slot=re.search(r'typedef struct \{[^}]*\} VPTexSlot;',source).group(0)
        lifecycle=lifecycle.replace('@TEXTURE_SLOT@',slot).replace('@TEXTURE_RETENTION@',function(source,'static int texture_retention_on(void)\n{'))
        def release_unit(body, legacy=False):
            retire = ('int gpu_pso_retire(void) { ++retire_calls; return !failure_mode; }'
                      if legacy else
                      'void gpu_pso_retire(void) { ++retire_calls; if (failure_mode) abort(); }')
            return lifecycle.replace('@FUNCTION@', body).replace('@RETIRE@', retire)
        actual_release = build('working-sets', release_unit(release))
        run(actual_release)
        run(actual_release, ['failed-retirement'], 'retirement failed; all GPU owners preserved', expected_exit=77)
        # Actual historical shutdown published by PR #251 releases textures
        # before checking its failed retirement. Exercise that code, not a
        # hand-written approximation of the old release order.
        baseline = subprocess.run(['git', 'show', '153159c785dff0791e5e3c531f68a613b271cf6d:vendor/ps3recomp/libs/video/rsx_d3d12_backend.c'],
                                  cwd=ROOT, capture_output=True, text=True)
        if baseline.returncode == 0:
            old = function(baseline.stdout, 'void rsx_d3d12_backend_shutdown(')
            old = old[:old.index('    /* Per-draw decompiled VS cache')] + '}\n'
            old = old.replace('void rsx_d3d12_backend_shutdown(', 'static void gpu_working_sets_release(')
            run(build('historical-release', release_unit(old, legacy=True)), ['failed-retirement'],
                'GPU owners released before failed retirement', expected_exit=78)
        # Hosted shallow clones need not retain the historical object; this
        # live mutation proves the same failure assertion on every CI run.
        late = release.replace('    gpu_pso_retire();\n', '', 1)
        late = late[:late.rfind('}')] + '    gpu_pso_retire();\n}'
        run(build('late-retirement', release_unit(late)), ['failed-retirement'],
            'GPU owners released before failed retirement', expected_exit=78)
    print('PASS: actual PSO draw/retirement adapters, cache churn, fences and historical omission controls')


if __name__ == '__main__':
    main()
