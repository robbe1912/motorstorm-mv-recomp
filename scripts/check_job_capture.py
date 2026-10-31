"""Exercise the actual game capture owner with authored observer dependencies."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--compiler', default=os.environ.get('CC') or
                    (shutil.which('clang-cl') if os.name == 'nt' else None) or shutil.which('cc'))
parser.add_argument('--mutants', action='store_true')
args = parser.parse_args()
assert args.compiler
msvc = Path(args.compiler).stem.lower() in ('cl', 'clang-cl')
out = root / 'build/self-tests/job-capture-owner'
out.mkdir(parents=True, exist_ok=True)
include = root / 'vendor/ps3recomp/include'
source = root / 'src/motorstorm/job_capture.cpp'
fixture = root / 'scripts/fixtures/job_capture_owner.cpp'
storage = root / 'vendor/ps3recomp/runtime/diag/sized_trace.c'
snapshot_source = root / 'src/motorstorm/job_capture_snapshot.cpp'

def command(cmd, label):
    (out / (label + '-command.json')).write_text(json.dumps(cmd, indent=2))
    result = subprocess.run(cmd, cwd=out, capture_output=True, text=True, timeout=60)
    (out / (label + '.log')).write_text(result.stdout + result.stderr)
    return result

obj = out / ('sized.obj' if msvc else 'sized.o')
cc = [args.compiler, str(storage)] + (['/nologo', '/std:c17', '/O2', '/c', '/I'+str(include), '/Fo'+str(obj)]
    if msvc else ['-std=c17', '-O2', '-c', '-I'+str(include), '-o', str(obj)])
result = command(cc, 'storage-build')
assert result.returncode == 0, result.stdout + result.stderr

def run(src, name, snapshot=snapshot_source):
    exe = out / (name + ('.exe' if os.name == 'nt' else ''))
    compiler = args.compiler if msvc else (shutil.which('c++') or args.compiler)
    cmd = [compiler, str(src), str(snapshot), str(fixture), str(obj)]
    if msvc:
        cmd += ['/nologo', '/std:c++17', '/EHsc', '/O2', '/UNDEBUG', '/I'+str(include),
                '/I'+str(source.parent), '/Fe'+str(exe)]
    else:
        cmd += ['-std=c++17', '-O2', '-UNDEBUG', '-Wall', '-Wextra', '-Werror', '-pthread',
                '-I'+str(include), '-I'+str(source.parent), '-o', str(exe)]
    built = command(cmd, name + '-build')
    assert built.returncode == 0, built.stdout + built.stderr
    return command([str(exe)], name + '-run')

result = run(source, 'actual')
assert result.returncode == 0, result.stdout + result.stderr
print('PASS capture owner, concurrent records, rollback, loss and partial visits')
defs = ['PS3_EXECUTION_OBSERVATION=1', 'PS3_SPURS_SCHEDULER_OBSERVATION=1']
objects = []
for name in ('spu_execution_observer', 'spurs_scheduler_observer'):
    observer = root / ('vendor/ps3recomp/runtime/diag/' + name + '.c')
    observer_obj = out / (name + ('.obj' if msvc else '.o'))
    cc = [args.compiler, str(observer)] + (
        ['/nologo', '/std:c17', '/O2', '/c', '/I'+str(include), '/Fo'+str(observer_obj)] + ['/D'+d for d in defs]
        if msvc else ['-std=c17', '-O2', '-c', '-I'+str(include), '-o', str(observer_obj)] + ['-D'+d for d in defs])
    result = command(cc, name + '-build')
    assert result.returncode == 0, result.stdout + result.stderr
    objects.append(observer_obj)
exe = out / ('integration.exe' if os.name == 'nt' else 'integration')
compiler = args.compiler if msvc else (shutil.which('c++') or args.compiler)
cmd = [compiler, str(source), str(root/'scripts/fixtures/job_capture_integration.cpp'), str(obj)] + list(map(str, objects))
cmd += (['/nologo', '/std:c++17', '/EHsc', '/O2', '/UNDEBUG', '/I'+str(include), '/Fe'+str(exe)] + ['/D'+d for d in defs]
        if msvc else ['-std=c++17', '-O2', '-UNDEBUG', '-pthread', '-I'+str(include), '-o', str(exe)] + ['-D'+d for d in defs])
result = command(cmd, 'integration-build')
assert result.returncode == 0, result.stdout + result.stderr
result = command([str(exe)], 'integration-run')
assert result.returncode == 0, result.stdout + result.stderr
print('PASS actual execution and scheduler observer integration')
if args.mutants:
    original = source.read_text()
    variants = {
        'rollback': ('clear_spu:\n    (void)ps3_atomic_observer_install_spu(nullptr);', 'clear_spu:',
                     '!ppu && !spu && !execution && !scheduler'),
        'thread-identity': ('r.flags = r.thread ? 0 : JOB_CAPTURE_THREAD_UNKNOWN;', 'r.flags = 0;',
                            'r.flags == JOB_CAPTURE_THREAD_UNKNOWN'),
        'payload': ('    r.value.atomic = *e;', '    r.value.atomic.context = e->context;',
                    'r.value.atomic.after[j] == static_cast<uint8_t>(~r.value.atomic.before[j])'),
        'visitor-failure': ('snapshot.consumer_failed = 1;', 'snapshot.consumer_failed = 0;',
                            'visited == 7 && snapshot.consumer_failed && snapshot.examined == 7 && snapshot.delivered == 6'),
        'append-failure': ('int result = ps3_sized_trace_append(c->trace, &r, sizeof(r));',
                           '(void)r; int result = PS3_SIZED_TRACE_INVALID;', 'info.unexpected_append_failures == 0'),
        'hidden-exclusions': ('increment(c->excluded_atomic); return 0;', 'return 0;',
                              'info.filter_mask == 7 && info.excluded_atomic == 4001'),
    }
    for name, (old, new, expected) in variants.items():
        assert original.count(old) == 1
        mutant = out / (name + '.cpp')
        mutant.write_text(original.replace(old, new))
        result = run(mutant, name)
        assert result.returncode != 0 and expected in result.stdout + result.stderr, (name, result.stdout, result.stderr)
        print('PASS rejected ' + name)
    original = snapshot_source.read_text()
    variants = {
        'snapshot-header': ('memcmp(header.magic, "MSJOB001", 8)', '0',
            '!job_capture_read_snapshot(file, read_record, &read_count, &loaded) && read_count == 0'),
        'snapshot-consumer': ('!consumer(user, index, &record)', '(static_cast<void>(consumer(user, index, &record)), 0)',
            '!job_capture_read_snapshot(file, reject_record, nullptr, &loaded)'),
    }
    for name, (old, new, expected) in variants.items():
        assert original.count(old) == 1
        mutant = out / (name + '.cpp')
        mutant.write_text(original.replace(old, new))
        result = run(source, name, mutant)
        assert result.returncode != 0 and expected in result.stdout + result.stderr, (name, result.stdout, result.stderr)
        print('PASS rejected ' + name)
