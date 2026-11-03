"""Check exact fork texture/pipeline storage and historical capacity controls."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'


def main():
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
    with tempfile.TemporaryDirectory(prefix='rsx-working-sets-') as directory:
        out = Path(directory)
        for name, control, checks, failure in [
            ('rsx_slot_pool', '--fixed96', 9, 'all100 requested textures admitted'),
            ('rsx_pipeline_cache', '--legacy', 10, 'repeated 600-key working set stays resident'),
        ]:
            fixture = ROOT / 'scripts/fixtures' / (name + '.c')
            exe = out / (name + ('.exe' if os.name == 'nt' else ''))
            if os.name == 'nt':
                command = [env['MV_CLANG'], '/nologo', '/I' + str(VIDEO), str(fixture),
                           '/Fe' + str(exe), '/Fo' + str(out) + os.sep]
            else:
                command = [env.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                           '-I' + str(VIDEO), str(fixture), '-o', str(exe)]
            subprocess.run(command, cwd=out, env=env, check=True, timeout=60)
            for args in [[], [control]]:
                result = subprocess.run([str(exe), *args], capture_output=True, text=True, timeout=15)
                if not args:
                    assert result.returncode == 0 and f'checks={checks} failures=0' in result.stdout, result
                else:
                    assert result.returncode == 1 and failure in result.stdout + result.stderr, result
                print(name + (' historical control: ' if args else ': ') + result.stdout.strip())
    print('PASS: working-set growth, resource identity, allocation failure, hard caps and historical controls')


if __name__ == '__main__':
    main()
