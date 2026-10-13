"""Extract complete actual cleanup; test EXIT, normal return and stale ownership."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from project import ROOT, build_environment

def extract(source):
    masked = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                    lambda m: ' '*len(m.group()), source, flags=re.S)
    start = re.search(r'^static void spu_taskset_task_exited\s*\(', masked, re.M).start()
    brace = masked.index('{', start); depth = 1; end = brace+1
    while depth:
        depth += (masked[end] == '{') - (masked[end] == '}'); end += 1
    return source[start:end]

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, default=ROOT/'vendor/ps3recomp')
    ap.add_argument('--baseline')
    ap.add_argument('--expect-failure', action='store_true')
    args = ap.parse_args(); repo = args.source.resolve()
    path = 'runtime/spu/spu_workload.c'
    raw = subprocess.run(['git','-C',str(repo),'show',args.baseline+':./'+path],capture_output=True,check=True).stdout if args.baseline else (repo/path).read_bytes()
    body = extract(raw.decode('utf8'))
    out = ROOT/'temp/checks'/datetime.datetime.now(datetime.timezone.utc).strftime('task-exit-%Y%m%dT%H%M%S.%fZ'); out.mkdir(parents=True)
    fixture = ROOT/'src/task_exit_source_check.c'
    (out/'fixture.c').write_text(fixture.read_text(encoding='utf8').replace('/* ACTUAL_COMPLETION */',body),encoding='utf8')
    definitions = ['TOKEN_COMPLETION'] if 'const spu_task_owner* owner' in body else []
    includes = [ROOT/'src',repo/'include',repo/'runtime/spu',repo/'runtime/platform']
    if os.name == 'nt':
        compiler = os.environ.get('MV_CLANG','clang-cl')
        command = [compiler,'/nologo','/TC','/O1',*[f'/I{p}' for p in includes],*[f'/D{d}' for d in definitions],str(out/'fixture.c'),str(repo/'runtime/spu/spu_task_lifecycle.c'),f'/Fo{out}/',f'/Fe{out}/fixture.exe']
        exe = out/'fixture.exe'
    else:
        command = [os.environ.get('CC','cc'),'-std=gnu17','-D_GNU_SOURCE','-pthread',*[f'-I{p}' for p in includes],*[f'-D{d}' for d in definitions],str(out/'fixture.c'),str(repo/'runtime/spu/spu_task_lifecycle.c'),'-o',str(out/'fixture')]
        exe = out/'fixture'
    env=build_environment(); command[0]=env.get('MV_CLANG',command[0]) if os.name=='nt' else command[0]
    build = subprocess.run(command,env=env,capture_output=True,timeout=120); (out/'build.log').write_bytes(build.stdout+build.stderr)
    if build.returncode:
        print('\n'.join(x for x in (build.stdout+build.stderr).decode(errors='replace').splitlines() if 'error:' in x)); print('Build log:',out/'build.log'); raise SystemExit(build.returncode)
    run = subprocess.run([str(exe)],capture_output=True,timeout=30); log = run.stdout+run.stderr; (out/'run.log').write_bytes(log)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    (out/'result.json').write_text(json.dumps({'baseline':args.baseline,'source_sha256':hashlib.sha256(raw).hexdigest(),'fixture_sha256':sha(fixture),'module_sha256':sha(repo/'runtime/spu/spu_task_lifecycle.c'),'exe_sha256':sha(exe),'command':command,'returncode':run.returncode},indent=2))
    print(log.decode(errors='replace')[:1500]); print('Evidence:',out)
    if args.expect_failure:
        if run.returncode != 1 or b'FAIL stale owner' not in log or not (b'FAIL return ownership' in log or b'FAIL EXIT retirement' in log): raise SystemExit('Expected historical lifecycle failures absent')
    elif run.returncode: raise SystemExit(run.returncode)
if __name__ == '__main__': main()
