"""Compile actual async dispatch functions with deterministic ownership interleaving."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from project import ROOT, build_environment


def function(source, name):
    masked = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                    lambda m: ' ' * len(m.group()), source, flags=re.S)
    begin = re.search(r'^int ' + name + r'\s*\(', masked, re.M)
    if not begin:
        raise ValueError('Missing dispatcher: ' + name)
    brace = masked.index('{', begin.start())
    depth, end = 1, brace + 1
    while depth:
        depth += (masked[end] == '{') - (masked[end] == '}')
        end += 1
    return source[begin.start():end]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, default=ROOT/'vendor/ps3recomp')
    ap.add_argument('--fixture', type=Path, default=ROOT/'src/task_dispatch_identity_check.c')
    ap.add_argument('--baseline', help='Git revision of the actual dispatcher to compile')
    ap.add_argument('--expect-failure', action='store_true')
    args = ap.parse_args()
    repo = args.source.resolve()
    raw = (subprocess.run(['git', '-C', str(repo), 'show',
                         args.baseline + ':./runtime/spu/spu_workload.c'],
                         check=True, stdout=subprocess.PIPE).stdout if args.baseline else
           (repo/'runtime/spu/spu_workload.c').read_bytes())
    source = raw.decode('utf-8')
    async_body = function(source, 'spu_workload_dispatch_async')
    explicit = bool(re.search(r'^int spu_workload_dispatch_task\s*\(', source, re.M))
    bodies = (function(source, 'spu_workload_dispatch_task') + '\n' if explicit else '') + async_body
    lifecycle = bool(re.search(r'^int spu_workload_dispatch_owned\s*\(', source, re.M))
    if lifecycle: bodies = function(source, 'spu_workload_dispatch_owned') + '\n' + bodies
    end = source.index('} spu_async_job;') + len('} spu_async_job;')
    begin = source.rfind('typedef struct {', 0, end)
    if begin < 0:
        raise ValueError('Actual async job type changed')
    fixture = args.fixture.read_text()
    if (repo/'runtime/platform/thread_name.h').exists():
        fixture = '#include "thread_name.h"\n' + fixture
    compiled = fixture.replace('/* ACTUAL_JOB_TYPE */', source[begin:end]).replace('/* ACTUAL_DISPATCH_APIS */', bodies)
    out = ROOT/'temp/checks'/datetime.datetime.now(datetime.timezone.utc).strftime('task-identity-%Y%m%dT%H%M%S.%fZ')
    out.mkdir(parents=True)
    unit = out/'fixture.c'
    unit.write_text(compiled)
    env = build_environment()
    definitions = []
    if explicit:
        definitions.append('EXPLICIT_TASK_API')
    if lifecycle: definitions.append('LIFECYCLE_API')
    if 'task_arg' in async_body.split('{', 1)[0]:
        definitions.append('ASYNC_HAS_ARGUMENT')
    includes = [repo/'runtime/spu', repo/'runtime/platform', repo/'tests']
    if os.name == 'nt':
        exe = out/'fixture.exe'
        compiler = env['MV_CLANG']
        command = [compiler, '/nologo', '/TC', '/O1', '/D_CRT_SECURE_NO_WARNINGS']
        command += ['/D'+d for d in definitions] + ['/I'+str(p) for p in includes]
        command += ['/Fe'+str(exe), str(unit)]
    else:
        exe = out/'fixture'
        command = [os.environ.get('CC', 'cc'), '-std=gnu17', '-D_GNU_SOURCE', '-O1', '-pthread']
        command += ['-D'+d for d in definitions] + ['-I'+str(p) for p in includes]
        command += [str(unit), '-o', str(exe)]
    build = subprocess.run(command, cwd=out, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    (out/'build.log').write_bytes(build.stdout)
    if build.returncode:
        print(build.stdout.decode(errors='replace')[-5000:]); raise SystemExit(build.returncode)
    run = subprocess.run([str(exe)], cwd=out, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    (out/'run.log').write_bytes(run.stdout)
    (out/'result.json').write_text(json.dumps(dict(source_sha256=hashlib.sha256(raw).hexdigest(),
        fixture_sha256=hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
        exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(), command=command,
        returncode=run.returncode, explicit_api=explicit, baseline=args.baseline,
        scope='Complete dispatch APIs; fingerprint interleaving and spawn adapters, no real threads or guest execution.'), indent=2))
    print('\n'.join(line for line in run.stdout.decode(errors='replace').splitlines()
                    if line.startswith(('FAIL', 'task identity fixture'))))
    print('Evidence:', out)
    if args.expect_failure:
        if run.returncode != 1 or b'FAIL explicit identity' not in run.stdout or b'FAIL generic dispatch' not in run.stdout:
            raise SystemExit('Expected both actual ownership regressions')
    elif run.returncode:
        raise SystemExit(run.returncode)


if __name__ == '__main__':
    main()
