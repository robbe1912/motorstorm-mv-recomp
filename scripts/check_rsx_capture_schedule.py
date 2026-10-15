"""Check the actual frame capture selector with authored, game-free inputs."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', type=Path, default=ROOT/'vendor/ps3recomp')
    args = parser.parse_args()
    out = ROOT/'temp/checks'/('capture-schedule-'+datetime.datetime.now(
        datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
    out.mkdir(parents=True)
    source = ROOT/'scripts/fixtures/rsx_capture_schedule.c'
    header = args.vendor.resolve()/'libs/video/rsx_capture_schedule.h'
    event = args.vendor.resolve()/'libs/video/rsx_capture_event.c'
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        exe = out/'check.exe'
        command = [env['MV_CLANG'], '/nologo', '/std:c17', '/TC',
                   '/I'+str(header.parent), str(source), str(event), '/Fe'+str(exe)]
    else:
        env = os.environ.copy()
        compiler = shutil.which(env.get('CC', 'cc'))
        if not compiler:
            raise SystemExit('A C17 compiler is required')
        exe = out/'check'
        command = [compiler, '-std=c17', '-I'+str(header.parent), str(source), str(event), '-o', str(exe)]
    with (out/'compile.log').open('wb') as log:
        compiled = subprocess.run(command, cwd=out, env=env, stdout=log,
                                  stderr=subprocess.STDOUT, timeout=120)
    if compiled.returncode:
        print((out/'compile.log').read_text(errors='replace'))
        raise SystemExit(compiled.returncode)
    result = subprocess.run([str(exe)], capture_output=True, timeout=15)
    (out/'check.log').write_bytes(result.stdout+result.stderr)
    guards = []
    # A second independent duration guard prevents launching even if a burst
    # preflight regresses. Assert which validation rejects the invocation.
    for name, options, message in [
        ('too-large', ['--capture-menu', '--capture-burst-frames', '121'], 'Capture burst must be'),
        ('negative', ['--capture-menu', '--capture-burst-frames', '-1'], 'Capture burst must be'),
        ('no-menu', ['--capture-burst-frames', '64'], 'Capture burst requires'),
        ('bad-event', ['--capture-on-pad', '0x10000'], 'Capture event mask must be'),
        ('event-no-burst', ['--capture-on-pad', '0x10'], 'Capture input event requires'),
    ]:
        check = subprocess.run([sys.executable, str(ROOT/'scripts/run.py'), '--seconds', '0']+options,
                               capture_output=True, timeout=15)
        passed = check.returncode != 0 and message in (check.stdout+check.stderr).decode(errors='replace')
        guards.append(dict(name=name, passed=passed))
    (out/'result.json').write_text(json.dumps(dict(game_inputs=False,
        sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, header, event, event.with_suffix('.h'), exe)},
        returncode=result.returncode, launch_preflight=guards), indent=2))
    print(result.stdout.decode(errors='replace').strip())
    print(result.stderr.decode(errors='replace').strip())
    print('Evidence:', out)
    if not all(check['passed'] for check in guards):
        raise SystemExit('FAIL: burst preflight did not reject before launch validation')
    print('PASS: invalid burst budgets and missing menu capture rejected before launch')
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
