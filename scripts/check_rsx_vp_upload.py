"""Check actual VP upload paths and storage growth with authored data, no GPU.

Run with a C11 compiler. Windows defaults to the normal clang-cl setup; set
CC=clang (or --cc clang) for a GNU-style compiler, including MinGW on Windows.
--baseline REV must fail specifically at the original full-capacity strip.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
NAMES = ('upload_quads_vp', 'upload_tris_vp', 'upload_strip_vp',
         'upload_quads_vp_indexed', 'upload_tris_vp_indexed', 'upload_strip_vp_indexed')


def function(text, signature):
    start = text.index(signature)
    return text[start:text.index('\n}\n', start) + 3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=VIDEO / 'rsx_d3d12_backend.c')
    parser.add_argument('--baseline', help='Git revision with the original dropping uploader')
    parser.add_argument('--cc', default=os.environ.get('CC'))
    args = parser.parse_args()
    source = args.source.resolve()
    video = source.parent
    include = video.parent.parent / 'include'
    text = source.read_text(encoding='utf-8')
    header = (video / 'rsx_upload_buffer.h').read_text(encoding='utf-8')
    fixtures = ROOT / 'scripts/fixtures'
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('vp-upload-' + stamp)
    out.mkdir(parents=True)
    env = os.environ.copy()
    msvc = os.name == 'nt' and not args.cc
    if msvc:
        from project import build_environment
        env = build_environment()
        compiler = env['MV_CLANG']
    else:
        compiler = shutil.which(args.cc or 'cc')
        if not compiler:
            raise SystemExit('Select a C11 compiler with --cc or CC')
    # These real functions include retained diagnostic branches; no inherited
    # switches may write files or alter authored vertex data in the fixture.
    for key in list(env):
        if key.startswith(('RSX_', 'VP_', 'VTX_', 'IDX')) or key in ('VBFULL', 'MVP_BASE'):
            env.pop(key)
    result = dict(game_inputs=False, gpu_execution=False, source=str(source),
                  compiler=compiler, checks=[], production_functions=list(NAMES)+['vp_upload_retire', 'rsx_upload_reserve'])
    paths = [source, video/'rsx_upload_buffer.h', video/'rsx_index_strip.h',
             fixtures/'rsx_vp_upload.c.in', fixtures/'rsx_vp_retire.c.in', fixtures/'rsx_upload_buffer.c', Path(__file__)]
    result['source_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

    def build_run(name, code, *, extra_include=None, options=(), expected=0, diagnostic='PASS:'):
        c = out / (name + '.c')
        exe = out / (name + ('.exe' if os.name == 'nt' else ''))
        c.write_text(code, encoding='utf-8')
        includes = ([extra_include] if extra_include else []) + [video, include]
        if msvc:
            command = [compiler, '/nologo', '/std:c17', '/O2', *['/I'+str(p) for p in includes],
                       str(c), '/Fe'+str(exe), '/Fo'+str(out / (name+'.obj'))]
        else:
            command = [compiler, '-std=c11', '-O2', *['-I'+str(p) for p in includes], str(c), '-o', str(exe)]
        compiled = subprocess.run(command, env=env, cwd=out, capture_output=True, timeout=120)
        (out / (name + '-build.log')).write_bytes(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            raise RuntimeError((compiled.stdout + compiled.stderr).decode(errors='replace'))
        ran = subprocess.run([str(exe), *options], env=env, cwd=out, capture_output=True, timeout=30)
        output = (ran.stdout + ran.stderr).decode(errors='replace')
        (out / (name + '-run.log')).write_text(output, encoding='utf-8')
        result['checks'].append(dict(name=name, command=command, returncode=ran.returncode,
                                     expected=expected, exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest()))
        if ran.returncode != expected or diagnostic not in output:
            raise RuntimeError(name + ': ' + output)
        print(name + ': ' + ('PASS: expected rejection; ' if expected else '') + output.strip())

    try:
        template = (fixtures / 'rsx_vp_upload.c.in').read_text(encoding='utf-8')
        bodies = '\n'.join(function(text, 'static u32 '+name+'(') for name in NAMES)
        build_run('all-uploads', template.replace('@UPLOAD_FUNCTIONS@', bodies))
        buffer = (fixtures / 'rsx_upload_buffer.c').read_text(encoding='utf-8')
        build_run('buffer', buffer)
        retire_template = (fixtures / 'rsx_vp_retire.c.in').read_text(encoding='utf-8')
        retire_body = function(text, 'static int vp_upload_retire(')
        build_run('retirement', retire_template.replace('@RETIRE_FUNCTION@', retire_body))
        mutant = out / 'parity-mutant-include'
        mutant.mkdir()
        needle = '(unsigned char*)next.memory + (size_t)new_bytes,'
        if header.count(needle) != 1:
            raise RuntimeError('Parity relocation control anchor changed')
        (mutant / 'rsx_upload_buffer.h').write_text(header.replace(needle,
            '(unsigned char*)next.memory + (size_t)old_bytes,'), encoding='utf-8')
        build_run('parity-mutant', buffer, extra_include=mutant, expected=1, diagnostic='== 0x62')
        unchecked = 'static int vp_upload_retire(void* context) { (void)context; wait_for_gpu(); return 1; }'
        build_run('retirement-mutant', retire_template.replace('@RETIRE_FUNCTION@', unchecked),
                  expected=1, diagnostic='retirement gate frame=0 mode=1')
        if args.baseline:
            old = subprocess.check_output(['git', '-C', str(ROOT), 'show',
                args.baseline+':vendor/ps3recomp/libs/video/rsx_d3d12_backend.c']).decode('utf-8')
            old_bodies = '\n'.join(function(old, 'static u32 '+name+'(') for name in NAMES)
            build_run('baseline', template.replace('@UPLOAD_FUNCTIONS@', old_bodies),
                      options=['--strip-only'], expected=1,
                      diagnostic='strip expected 6 vertices at capacity, got 0')
            result['baseline'] = args.baseline
        result['passed'] = True
        print('PASS: production VP upload preservation and negative controls')
    finally:
        (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print('Evidence:', out)


if __name__ == '__main__':
    main()
