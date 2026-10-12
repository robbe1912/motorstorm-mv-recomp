"""Compile the real D3D12 target-sizing function with authored RSX states."""
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
    ap.add_argument('--backend-file', type=Path, default=ROOT / 'vendor/ps3recomp/libs/video/rsx_d3d12_backend.c')
    ap.add_argument('--video-dir', type=Path, default=ROOT / 'vendor/ps3recomp/libs/video')
    args = ap.parse_args()
    backend, video = args.backend_file.resolve(), args.video_dir.resolve()
    text = backend.read_text(encoding='utf-8')
    start = text.index('static u32 current_rt_off(')
    end = text.index('/* RSX surface colour format', start)
    function = text[start:end]
    if 'return raw;' not in function or len(function) < 500:
        raise ValueError('Production target function boundary changed')
    fixture = ROOT / 'scripts/fixtures/rsx_surface_layout.c'
    source = fixture.read_text(encoding='utf-8').replace('/* PRODUCTION_TARGET_FUNCTION */', function)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('rsx-surface-layout-' + stamp)
    out.mkdir(parents=True)
    c, exe = out / 'check.c', out / ('check.exe' if os.name == 'nt' else 'check')
    c.write_text(source, encoding='utf-8')
    include = video.parent.parent / 'include'
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        cmd = [env['MV_CLANG'], '/nologo', '/TC', '/O2', '/D_CRT_SECURE_NO_WARNINGS',
               '/I' + str(include), '/I' + str(video), str(c), '/Fe' + str(exe), '/Fo' + str(out / 'check.obj')]
    else:
        cmd = [env.get('CC', 'cc'), '-std=c11', '-O2', '-I' + str(include), '-I' + str(video), str(c), '-o', str(exe)]
    with (out / 'build.log').open('wb') as log:
        build = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    inputs = [backend, fixture, video / 'rsx_commands.h', video / 'rsx_surface_samples.h',
              Path(__file__).resolve()]
    result = dict(source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
                  build_returncode=build.returncode, game_inputs=False,
                  production_functions=['current_rt_off', 'rsx_surface_sample_grid', 'rsx_surface_sample_extent'])
    if build.returncode == 0:
        with (out / 'run.log').open('wb') as log:
            run = subprocess.run([str(exe)], stdout=log, stderr=subprocess.STDOUT, timeout=30)
        result['run_returncode'] = run.returncode
        result['exe_sha256'] = hashlib.sha256(exe.read_bytes()).hexdigest()
        print((out / 'run.log').read_text(encoding='utf-8', errors='replace'))
    else:
        print((out / 'build.log').read_text(encoding='utf-8', errors='replace'))
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('Evidence:', out)
    return build.returncode or result.get('run_returncode', 1)


if __name__ == '__main__':
    sys.exit(main())
