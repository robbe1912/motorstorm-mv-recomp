"""Check the production indexed uploader with real attribute decoding and authored data."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=VIDEO / 'rsx_d3d12_backend.c')
    args = parser.parse_args()
    source = args.source.resolve()
    text = source.read_text(encoding='utf-8')
    start = text.index('static u32 upload_strip_vp_indexed(')
    end = text.index('static void d3d12_draw_arrays(', start)
    fixture = ROOT / 'scripts/fixtures/rsx_indexed_strip.c.in'
    template = fixture.read_text(encoding='utf-8')
    assert template.count('@INDEXED_STRIP_FUNCTION@') == 1
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('rsx-indexed-strip-' + stamp)
    out.mkdir(parents=True)
    c, exe = out / 'check.c', out / ('check.exe' if os.name == 'nt' else 'check')
    c.write_text(template.replace('@INDEXED_STRIP_FUNCTION@', text[start:end]), encoding='utf-8')
    fetch = VIDEO / 'rsx_vertex_fetch.c'
    include = ROOT / 'vendor/ps3recomp/include'
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        cmd = [env['MV_CLANG'], '/nologo', '/O2', '/I' + str(include), '/I' + str(VIDEO),
               str(c), str(fetch), '/Fe' + str(exe), '/Fo' + str(out) + os.sep]
    else:
        cmd = [env.get('CC', 'cc'), '-std=c11', '-O2', '-I' + str(include), '-I' + str(VIDEO),
               '-o', str(exe), str(c), str(fetch), '-lm']
    with (out / 'build.log').open('wb') as log:
        build = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    inputs = [source, fixture, fetch, VIDEO / 'rsx_vertex_fetch.h', VIDEO / 'rsx_commands.h',
              VIDEO / 'rsx_index_strip.h', Path(__file__)]
    result = dict(command=cmd, build_returncode=build.returncode, game_inputs=False,
                  production_functions=['upload_strip_vp_indexed', 'rsx_fetch_attrib'],
                  source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs})
    if build.returncode:
        print((out / 'build.log').read_text(encoding='utf-8', errors='replace'))
    else:
        with (out / 'run.log').open('wb') as log:
            run = subprocess.run([str(exe)], stdout=log, stderr=subprocess.STDOUT, timeout=30)
        result['run_returncode'] = run.returncode
        result['exe_sha256'] = hashlib.sha256(exe.read_bytes()).hexdigest()
        print((out / 'run.log').read_text(encoding='utf-8', errors='replace'))
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('Evidence:', out)
    return build.returncode or result.get('run_returncode', 1)


if __name__ == '__main__':
    sys.exit(main())
