"""Execute authored D3D12 draws after evicting their original cache owners."""
import os
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--warp-only', action='store_true')
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('PSO GPU test requires Windows')
    from project import build_environment
    env = build_environment()
    with tempfile.TemporaryDirectory(prefix='pso-gpu-') as directory:
        out = Path(directory)
        exe = out / 'pso.exe'
        command = [env['MV_CLANG'], '/nologo', '/std:c++17', '/EHsc',
                   '/I' + str(ROOT / 'vendor/ps3recomp/libs/video'),
                   str(ROOT / 'scripts/fixtures/rsx_gpu_pso_gpu.cpp'),
                   '/Fe' + str(exe), '/link', 'd3d12.lib', 'dxgi.lib', 'd3dcompiler.lib']
        subprocess.run(command, cwd=out, env=env, check=True, timeout=120)
        for hardware in ([False] if args.warp_only else [False, True]):
            result = subprocess.run([str(exe), *(['--hardware'] if hardware else [])],
                                    cwd=out, env=env, capture_output=True, text=True, timeout=40)
            print(('hardware' if hardware else 'WARP') + ': ' + result.stdout, end='')
            assert result.returncode == 0 and 'checks=6 failures=0' in result.stdout, result


if __name__ == '__main__':
    main()
