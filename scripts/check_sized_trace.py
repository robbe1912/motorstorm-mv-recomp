"""Run actual sized storage with complete authored atomic payloads and faults."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
toolkit = root / 'vendor/ps3recomp'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--compiler', default=os.environ.get('CC') or
                    (shutil.which('clang-cl') or shutil.which('cl') if os.name == 'nt' else None) or shutil.which('cc'))
parser.add_argument('--mutants', action='store_true')
args = parser.parse_args()
assert args.compiler
msvc = Path(args.compiler).stem.lower() in ('cl', 'clang-cl')
out = root / 'build/self-tests/sized-trace'
out.mkdir(parents=True, exist_ok=True)
source = toolkit / 'runtime/diag/sized_trace.c'
fixture = root / 'scripts/fixtures/sized_trace.c'

def command(args_, directory, label, timeout=60):
    (directory / (label + '-command.json')).write_text(json.dumps(args_, indent=2))
    result = subprocess.run(args_, cwd=directory, capture_output=True, text=True, timeout=timeout)
    (directory / (label + '.log')).write_text(result.stdout + result.stderr)
    return result

def run(directory, implementation=None):
    directory.mkdir(parents=True, exist_ok=True)
    exe = directory / ('fixture.exe' if os.name == 'nt' else 'fixture')
    cmd = [args.compiler, str(fixture)]
    if msvc:
        cmd += ['/nologo', '/std:c17', '/O2', '/UNDEBUG', '/W4', '/WX',
                '/I' + str(toolkit/'include'), '/Fo' + str(directory) + os.sep, '/Fe' + str(exe)]
        if implementation: cmd += ['/DSIZED_TRACE_IMPLEMENTATION="' + implementation.as_posix() + '"']
    else:
        cmd += ['-std=c17', '-O2', '-UNDEBUG', '-Wall', '-Wextra', '-Werror',
                '-I' + str(toolkit/'include'), '-pthread', '-o', str(exe)]
        if implementation: cmd += ['-DSIZED_TRACE_IMPLEMENTATION="' + implementation.as_posix() + '"']
    built = command(cmd, directory, 'build')
    assert built.returncode == 0, built.stdout + built.stderr
    return command([str(exe)], directory, 'run', 20)

obj = out / ('production.obj' if msvc else 'production.o')
cmd = [args.compiler, str(source)] + (
    ['/nologo', '/std:c17', '/O2', '/W4', '/WX', '/c', '/I'+str(toolkit/'include'), '/Fo'+str(obj)]
    if msvc else ['-std=c17', '-O2', '-Wall', '-Wextra', '-Werror', '-c', '-I'+str(toolkit/'include'), '-o', str(obj)])
result = command(cmd, out, 'production-build')
assert result.returncode == 0, result.stdout + result.stderr
cpp = out/'header.cpp'
cpp.write_text('#include "ps3emu/sized_trace.h"\nint consumer(ps3_sized_trace* p) { ps3_sized_trace_info x{}; return ps3_sized_trace_describe(p, &x); }\n')
header_obj = out/('header.obj' if msvc else 'header.o')
cmd = [args.compiler, str(cpp)] + (
    ['/nologo', '/std:c++17', '/W4', '/WX', '/c', '/I'+str(toolkit/'include'), '/Fo'+str(header_obj)]
    if msvc else ['-std=c++17', '-Wall', '-Wextra', '-Werror', '-c', '-I'+str(toolkit/'include'), '-o', str(header_obj)])
result = command(cmd, out, 'header-build')
assert result.returncode == 0, result.stdout + result.stderr
result = run(out)
assert result.returncode == 0 and 'PASS complete atomic payloads' in result.stdout, result.stdout + result.stderr
print(result.stdout, end='')
rejected = []
if args.mutants:
    original = source.read_text()
    publish = '    atomic_store_explicit(&record->sequence, index + 1, memory_order_release);'
    seam = '    PS3_SIZED_TRACE_BEFORE_COPY(trace, index);'
    drop = '        increment_saturating(&trace->dropped);'
    copy = '    memcpy(record->bytes, payload, size);'
    saturate = '    while (previous != UINT64_MAX &&'
    for item in (publish, seam, drop, copy, saturate): assert original.count(item) == 1
    variants = {
        'premature': (original.replace(publish, '').replace(seam, publish + '\n' + seam),
                      'ps3_sized_trace_read(trace, 0, &out, sizeof(out)) == 0 && out.address == 42'),
        'lost-drop': (original.replace(drop, ''), 'info.attempted == 2 && info.dropped == 1'),
        'truncated': (original.replace(copy, '    memcpy(record->bytes, payload, size / 2);'),
                      'out.before[j] == before && out.after[j] == (unsigned char)~before'),
        'wrap-counter': (original.replace(saturate, '    while ('),
                         'info.attempted == UINT64_MAX && info.dropped == UINT64_MAX'),
    }
    for name, (variant, assertion) in variants.items():
        folder = out / name
        folder.mkdir(parents=True, exist_ok=True)
        implementation = folder / 'implementation.c'
        implementation.write_text(variant)
        result = run(folder, implementation)
        assert result.returncode != 0 and assertion in result.stdout + result.stderr, (
            name + ' did not fail its intended assertion: ' + result.stdout + result.stderr)
        rejected.append(name)
        print('PASS rejected ' + name)
(out/'result.json').write_text(json.dumps({'compiler': args.compiler, 'rejected_mutants': rejected,
    'sources': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (source, fixture, toolkit/'include/ps3emu/sized_trace.h')},
    'scope': 'Storage-only authored payloads; no game binding, measured overhead or FPS.'}, indent=2))
