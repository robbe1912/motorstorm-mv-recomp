"""Validate production source modifiers and preserve the FXC failure control."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--warp-only', action='store_true')
    parser.add_argument('--source', type=Path, default=VIDEO / 'rsx_fp_decompiler.c')
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('Source-sign GPU test requires Windows')
    from project import build_environment
    env = build_environment()
    with tempfile.TemporaryDirectory(prefix='source-sign-') as directory:
        out = Path(directory)
        common = [env['MV_CLANG'], '/nologo', '/D_CRT_SECURE_NO_WARNINGS',
                  '/I' + str(VIDEO), '/I' + str(ROOT / 'vendor/ps3recomp/include')]
        obj, exe = out / 'decompiler.obj', out / 'source-sign.exe'
        subprocess.run(common + ['/c', str(args.source.resolve()), '/Fo' + str(obj)],
                       cwd=out, env=env, check=True, timeout=120)
        subprocess.run(common + ['/std:c++17', '/EHsc',
                       str(ROOT / 'scripts/fixtures/rsx_fp_source_sign_gpu.cpp'),
                       str(obj), '/Fe' + str(exe), '/link',
                       'd3d11.lib', 'dxgi.lib', 'd3dcompiler.lib'],
                       cwd=out, env=env, check=True, timeout=120)
        for hardware in ([False] if args.warp_only else [False, True]):
            for legacy in [False, True]:
                result = subprocess.run([str(exe), *(['--hardware'] if hardware else []),
                                         *(['--legacy-negate'] if legacy else [])],
                                        capture_output=True, text=True, timeout=40)
                label = ('hardware' if hardware else 'WARP') + (' historical control' if legacy else '')
                if legacy:
                    assert result.returncode == 2 and 'Invalid Bytecode' in result.stderr and \
                        'Negate modifier not allowed' in result.stderr, result
                    print(label + ': reproduces Invalid Bytecode / Negate modifier not allowed')
                else:
                    assert result.returncode == 0 and 'checks=16 failures=0' in result.stdout, result
                    print(label + ': checks=16 failures=0')


if __name__ == '__main__':
    main()
