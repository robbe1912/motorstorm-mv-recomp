"""Check ordered record batches and their negative controls."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
FIXTURE = ROOT / 'scripts/fixtures/rsx_record_batch.c'

def compile_c(source, exe, include, cwd):
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        command = [env['MV_CLANG'], '/nologo', '/I' + str(include), str(source),
                   '/Fe' + str(exe), '/Fo' + str(cwd) + os.sep]
    else:
        command = [env.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra',
                   '-Werror', '-I' + str(include), str(source), '-o', str(exe)]
    subprocess.run(command, cwd=cwd, env=env, check=True, timeout=60)

def main():
    original = (VIDEO / 'rsx_record_batch.h').read_text(encoding='utf-8')
    variants = [('normal', original, False),
                ('forced-present', original.replace('submit(context, 0)', 'submit(context, 1)', 1), True),
                ('repeat-clear', original.replace('int clear = !state->backing_initialized;', 'int clear = 1;', 1), True)]
    with tempfile.TemporaryDirectory(prefix='record-batch-') as directory:
        out = Path(directory)
        for name, header, must_fail in variants:
            if must_fail and header == original:
                raise RuntimeError(name + ': mutation anchor missing')
            (out / 'rsx_record_batch.h').write_text(header, encoding='utf-8')
            exe = out / ('batch.exe' if os.name == 'nt' else 'batch')
            compile_c(FIXTURE, exe, out, out)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
            if (run.returncode != 0) != must_fail:
                raise RuntimeError(f'{name}: {run.returncode}: {run.stdout}{run.stderr}')
            print(name + ': ' + ('expected rejection' if must_fail else run.stdout.strip()))

if __name__ == '__main__':
    main()
