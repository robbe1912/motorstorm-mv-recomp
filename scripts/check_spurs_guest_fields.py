"""Check actual SPURS API writes against an authored guest-bitset contract."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from project import ROOT, build_environment


def extract_apis(source):
    # Mask comments/literals without changing offsets; retain complete bodies.
    masked = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                    lambda m: ' ' * len(m.group()), source, flags=re.S)
    bodies = []
    for name in ('cellSpursCreateTask', 'cellSpursDestroyTaskset', 'cellSpursShutdownTaskset'):
        match = re.search(r'^s32 ' + name + r'\s*\(', masked, flags=re.M)
        if not match:
            raise ValueError('Missing actual API definition: ' + name)
        brace = masked.index('{', match.start())
        depth, end = 1, brace + 1
        while depth:
            depth += (masked[end] == '{') - (masked[end] == '}')
            end += 1
        bodies.append(source[match.start():end])
    type_end = source.index('} SpursTask;') + len('} SpursTask;')
    type_begin = source.rfind('typedef struct {', 0, type_end)
    globals_ = '\n'.join(re.findall(r'^static [^\n]*(?:s_tasks\[|s_next_task_id)[^\n]*;', source, flags=re.M))
    if type_begin < 0 or globals_.count('s_tasks[') != 1 or globals_.count('s_next_task_id') != 1:
        raise ValueError('API dependency declarations changed; review extraction')
    prefix = source[:source.index('/* ---------------------------------------------------------------------------')]
    return prefix + '\n' + source[type_begin:type_end] + '\n' + globals_ + '\n' + '\n'.join(bodies)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, default=ROOT/'vendor/ps3recomp')
    ap.add_argument('--fixture', type=Path, default=ROOT/'src/spurs_guest_fields_check.c')
    ap.add_argument('--baseline', help='Read the actual API source from this Git revision')
    ap.add_argument('--expect-failure', action='store_true', help='Require all three original-store regressions')
    args = ap.parse_args()
    repo, fixture = args.source.resolve(), args.fixture.resolve()
    out = ROOT/'temp/checks'/datetime.datetime.now(datetime.timezone.utc).strftime('guest-fields-%Y%m%dT%H%M%S.%fZ')
    out.mkdir(parents=True)
    source_path = repo/'libs/spurs/cellSpurs.c'
    source_bytes = (subprocess.check_output(['git', '-C', str(repo), 'show', args.baseline+':./libs/spurs/cellSpurs.c'])
                    if args.baseline else source_path.read_bytes())
    api = out/'affected_api.c'
    api.write_bytes(extract_apis(source_bytes.decode('utf-8')).encode('utf-8'))
    inputs = [fixture, api, repo/'libs/spurs/spurs_taskset.c']
    if b'spu_task_publish_locked' in source_bytes:
        inputs.append(repo/'runtime/spu/spu_task_lifecycle.c')
    env = build_environment()
    includes = [repo/'include', repo/'libs/spurs', repo/'runtime/spu']
    signature = re.search(r'int spu_workload_dispatch_async\([^;]+;',
                          (repo/'runtime/spu/spu_workload.h').read_text())
    if not signature:
        raise ValueError('Dispatch declaration changed')
    override = 'task_arg' in signature.group()
    if os.name == 'nt':
        exe = out/'fixture.exe'
        command = [env['MV_CLANG'], '/nologo', '/TC', '/O1', '/D_CRT_SECURE_NO_WARNINGS']
        if override:
            command.append('/DSPURS_DISPATCH_HAS_OVERRIDE')
        command += ['/I'+str(p) for p in includes] + ['/Fe'+str(exe), *map(str, inputs)]
    else:
        exe = out/'fixture'
        compiler = shutil.which(os.environ.get('CC', 'cc'))
        if not compiler:
            raise SystemExit('C compiler required')
        command = [compiler, '-std=gnu17', '-O1', '-pthread']
        if override:
            command.append('-DSPURS_DISPATCH_HAS_OVERRIDE')
        command += ['-I'+str(p) for p in includes] + [*map(str, inputs), '-o', str(exe)]
    build = subprocess.run(command, cwd=out, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    (out/'build.log').write_bytes(build.stdout)
    if build.returncode:
        print(build.stdout.decode(errors='replace')[-6000:])
        raise SystemExit(build.returncode)
    run = subprocess.run([str(exe)], cwd=out, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    (out/'run.log').write_bytes(run.stdout)
    report = dict(source=str(source_path), baseline=args.baseline,
                  source_sha256=hashlib.sha256(source_bytes).hexdigest(),
                  inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
                  executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
                  command=command, returncode=run.returncode,
                  scope='Complete affected API definitions and real BE builder; dispatch stubbed, no game/SPU execution.')
    (out/'result.json').write_text(json.dumps(report, indent=2))
    print(run.stdout.decode(errors='replace')[-3000:])
    print('Evidence:', out)
    if args.expect_failure:
        names = [b'FAIL '+n for n in (b'CreateTask', b'DestroyTaskset', b'ShutdownTaskset')]
        if run.returncode != 1 or any(n not in run.stdout for n in names) or b'failures=3' not in run.stdout:
            raise SystemExit('Expected exactly the three actual API-store regressions')
    elif run.returncode:
        raise SystemExit(run.returncode)


if __name__ == '__main__':
    main()
