"""Run the synthetic capacity contract against real VM/syscall code, without game inputs."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from project import ROOT, build_environment


def main():
    out = ROOT/'temp/checks'/datetime.datetime.now(datetime.timezone.utc).strftime('memory-%Y%m%dT%H%M%S.%fZ')
    out.mkdir(parents=True)
    runtime = ROOT/'vendor/ps3recomp/runtime/syscalls'
    inputs = [ROOT/'src/memory_capacity_check.c', runtime/'sys_memory.c', runtime/'spu_ea_alias.c']
    env = build_environment()
    exe = out/('capacity.exe' if os.name == 'nt' else 'capacity')
    if os.name == 'nt':
        command = [env['MV_CLANG'], '/nologo', '/TC', '/W3', '/Od', '/D_CRT_SECURE_NO_WARNINGS',
                   f'/I{runtime}', f'/Fe{exe}', *map(str, inputs)]
    else:
        compiler = shutil.which(os.environ.get('CC', 'cc'))
        if not compiler:
            raise SystemExit('A C compiler is required')
        command = [compiler, '-std=gnu17', '-pthread', f'-I{runtime}', '-o', str(exe), *map(str, inputs)]
    with (out/'build.log').open('w') as log:
        build = subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    result = {'build_returncode': build.returncode,
              'inputs': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}}
    if build.returncode:
        (out/'result.json').write_text(json.dumps(result, indent=2))
        raise SystemExit(f'Compile failed; inspect {out}/build.log')
    result['exe_sha256'] = hashlib.sha256(exe.read_bytes()).hexdigest()
    with (out/'run.log').open('w') as log:
        run = subprocess.run([str(exe)], cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=30)
    result['run_returncode'] = run.returncode
    (out/'result.json').write_text(json.dumps(result, indent=2))
    print((out/'run.log').read_text())
    print('Evidence:', out)
    raise SystemExit(run.returncode)


if __name__ == '__main__':
    main()
