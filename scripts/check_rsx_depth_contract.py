"""Extract actual fallback descriptors and draw selection; reject old selection."""
import os
import re
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def main():
    if os.name != 'nt':
        raise SystemExit('Production D3D12 descriptor tests require Windows')
    from project import build_environment
    env = build_environment()
    source = (VIDEO / 'rsx_d3d12_backend.c').read_text(encoding='utf-8')
    compile_vp = function(source, 'static void compile_vp(')
    start = compile_vp.index('    D3D12_GRAPHICS_PIPELINE_STATE_DESC pd = {0};')
    creation = compile_vp[start:compile_vp.index('    /* Second PSO:', start)]
    selector = function(source, 'static ID3D12PipelineState* vp_select_draw_pso(')
    draw = re.search(r'gpu_pso_draw\([^;]+dr->vb_byte_offset / 256\);', source).group(0)
    start = source.index('    pd.DSVFormat = DXGI_FORMAT_D24_UNORM_S8_UINT;',
                         source.index('static ID3D12PipelineState* vp_get_fp_pso('))
    dynamic = source[start:source.index('    if (pd.DepthStencilState.StencilEnable) {', start)]
    assert 'ID3D12PipelineState* next_pso = vp_select_draw_pso(dr, dpso);' in source
    assert 'FALSE, NULL);\n                D3D12_VIEWPORT vp = ' in source
    template = (ROOT / 'scripts/fixtures/rsx_depth_contract.c.in').read_text()
    keys = '\n'.join(line for line in source.splitlines() if line.startswith('#define RSX_DSK_'))
    actual = template.replace('@SELECTOR@', selector).replace('@CREATION@', creation).replace('@DYNAMIC@', dynamic).replace('@DEPTH_KEYS@', keys).replace('@DRAW@', draw)
    with tempfile.TemporaryDirectory(prefix='depth-contract-') as directory:
        out = Path(directory)
        for name, body, expected_error in [
            ('actual', actual, None),
            ('old-selection', actual.replace('dr->depth_slot != 0', '1'), 'attachment-compatible fallback'),
            ('old-owner', actual.replace('gpu_pso_draw(next_pso,', 'gpu_pso_draw(dpso ? dpso : vpso,'), 'draw holds selected pipeline'),
        ]:
            unit = out / (name + '.c'); unit.write_text(body, encoding='utf-8')
            exe = out / (name + '.exe')
            subprocess.run([env['MV_CLANG'], '/nologo', '/D_CRT_SECURE_NO_WARNINGS',
                            '/I' + str(VIDEO), '/I' + str(ROOT / 'vendor/ps3recomp/include'),
                            str(unit), '/Fe' + str(exe), '/link', 'dxguid.lib'],
                           cwd=out, env=env, check=True, timeout=60)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            if expected_error:
                assert result.returncode and expected_error in result.stderr, result
            else:
                assert result.returncode == 0 and 'failures=0' in result.stdout, result
    print('PASS actual production fallback descriptors/selection, draw owner and dynamic guest depth state; old selection/owner rejected')


if __name__ == '__main__':
    main()
