"""Check device-owned typed guest reads and pitched surface packing using authored bytes."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--fastmem-header', type=Path, default=ROOT / 'vendor/ps3recomp/include/ps3emu/ppu_fastmem.h')
    args = ap.parse_args()
    header = args.fastmem_header.resolve()
    source = ROOT / 'vendor/ps3recomp/runtime/memory/guest_read_sync.c'
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('rsx-cpu-surface-' + stamp)
    out.mkdir(parents=True)
    c, exe = out / 'check.c', out / ('check.exe' if os.name == 'nt' else 'check')
    c.write_text('#define PPU_FASTMEM_HEADER ' + json.dumps(header.as_posix()) + '\n' + (ROOT / 'scripts/fixtures/rsx_cpu_surface_memory.c').read_text(encoding='utf-8'), encoding='utf-8')
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        cmd = [env['MV_CLANG'], '/nologo', '/O2', '/I' + str(ROOT / 'vendor/ps3recomp/include'), '/I' + str(ROOT / 'vendor/ps3recomp/include/ps3emu'), '/I' + str(ROOT / 'vendor/ps3recomp/libs/video'), str(c), str(source), '/Fe' + str(exe), '/Fo' + str(out) + os.sep]
    else:
        cmd = [env.get('CC', 'cc'), '-std=c11', '-O2', '-I' + str(ROOT / 'vendor/ps3recomp/include'), '-I' + str(ROOT / 'vendor/ps3recomp/include/ps3emu'), '-I' + str(ROOT / 'vendor/ps3recomp/libs/video'), '-o', str(exe), str(c), str(source), '-lm']
    with (out / 'build.log').open('wb') as log:
        build = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    inputs = [source, header, ROOT / 'scripts/fixtures/rsx_cpu_surface_memory.c',
              ROOT / 'vendor/ps3recomp/include/ps3emu/guest_read_sync.h',
              ROOT / 'vendor/ps3recomp/libs/video/rsx_surface_readback.h']
    result = dict(source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
                  build_returncode=build.returncode, game_inputs=False,
                  production_functions=['ppu_fm_read8/16/32/64', 'vm_cpu_read_sync', 'rsx_surface_readback_rows'],
                  authored_device_bytes=True)
    if build.returncode != 0:
        print((out / 'build.log').read_text(encoding='utf-8', errors='replace'))
    if build.returncode == 0:
        with (out / 'run.log').open('wb') as log:
            run = subprocess.run([str(exe)], stdout=log, stderr=subprocess.STDOUT, timeout=30)
        result['run_returncode'] = run.returncode
        result['exe_sha256'] = hashlib.sha256(exe.read_bytes()).hexdigest()
        print((out / 'run.log').read_text())
    (out / 'result.json').write_text(json.dumps(result, indent=2))
    print('Evidence:', out)
    return build.returncode or result.get('run_returncode', 1)


if __name__ == '__main__':
    sys.exit(main())
