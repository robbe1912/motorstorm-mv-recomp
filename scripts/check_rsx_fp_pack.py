"""Exercise the vendored fragment decompiler's PK2H output on D3D11."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
FIXTURES = ROOT / 'scripts/fixtures'

def main():
    if os.name != 'nt':
        raise SystemExit('PK2H GPU test requires Windows')
    from project import build_environment
    env = build_environment()
    with tempfile.TemporaryDirectory(prefix='pk2h-check-') as directory:
        out = Path(directory)
        common = [env['MV_CLANG'], '/nologo', '/D_CRT_SECURE_NO_WARNINGS',
                  '/I' + str(VIDEO), '/I' + str(ROOT / 'vendor/ps3recomp/include')]
        obj = out / 'decompiler.obj'
        exe = out / 'pk2h.exe'
        subprocess.run(common + ['/c', str(VIDEO / 'rsx_fp_decompiler.c'), '/Fo' + str(obj)], cwd=out, env=env, check=True, timeout=120)
        subprocess.run(common + ['/std:c++17', '/EHsc', str(FIXTURES / 'rsx_fp_pack_gpu.cpp'), str(obj), '/Fe' + str(exe), '/link', 'd3d11.lib', 'dxgi.lib', 'd3dcompiler.lib'], cwd=out, env=env, check=True, timeout=120)
        subprocess.run([sys.executable, str(FIXTURES / 'rsx_fp_pack_verify.py'), str(exe), *sys.argv[1:]], cwd=out, env=env, check=True, timeout=180)

if __name__ == '__main__':
    main()
