"""Authored depth/stencil pixels, stale-zeta capacity and fallback PSO controls."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--warp-only', action='store_true')
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('Depth attachment GPU tests require Windows')
    from project import build_environment
    env = build_environment()
    with tempfile.TemporaryDirectory(prefix='depth-admission-') as directory:
        out = Path(directory)
        exe = out / 'depth.exe'
        runtime = ROOT / 'vendor/ps3recomp'
        command = [env['MV_CLANG'], '/nologo', '/D_CRT_SECURE_NO_WARNINGS',
                   '/I' + str(runtime / 'libs/video'), '/I' + str(runtime / 'include'),
                   str(ROOT / 'scripts/fixtures/rsx_depth_surfaces_gpu.c'),
                   str(runtime / 'libs/video/rsx_commands.c'), '/Fe' + str(exe),
                   '/link', 'd3d12.lib', 'dxgi.lib', 'dxguid.lib', 'd3dcompiler.lib']
        subprocess.run(command, cwd=out, env=env, check=True, timeout=120)
        for mode in ([[]] if args.warp_only else [[], ['--hardware']]):
            controls = [([], 0, 0), (['--eager-depth'], 1, 1),
                        (['--legacy-fallback-depth'], 1, 2)]
            for control, code, failures in controls:
                result = subprocess.run([str(exe), *mode, *control], cwd=out, env=env,
                                        capture_output=True, text=True, timeout=40)
                print(result.stdout, end='')
                assert result.returncode == code and f'checks=18 failures={failures}' in result.stdout, result
                if control == ['--legacy-fallback-depth']:
                    assert result.stderr.count('GPU validation:') == 2, result
                    assert 'null depth stencil view' in result.stderr, result
                elif not control:
                    assert 'GPU validation:' not in result.stderr, result


if __name__ == '__main__':
    main()
