"""Check the actual frame capture selector with authored, game-free inputs."""
import argparse
import ast
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def screen_launch(tree, out):
    """Execute only the real capture selection/record expressions; never launch."""
    out.mkdir()
    selections = [node for node in ast.walk(tree) if isinstance(node, ast.If)
                  and ast.unparse(node.test) == 'args.capture_menu or args.menu_replay']
    assert len(selections) == 1, 'ambiguous capture selection'
    records = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == 'record'
                       for target in node.targets)]
    assert len(records) == 1 and isinstance(records[0], ast.Dict), 'ambiguous launch record'
    fields = {key.value: value for key, value in zip(records[0].keys, records[0].values)}
    receipts = []
    for label, menu, replay in [('raw', False, None), ('menu', True, None),
                                ('replay', False, 'observed-profile.json')]:
        case = out / label
        case.mkdir()
        env = {'RSX_CAP': 'authored-raw-config'}
        namespace = {'env': env, 'out': case,
                     'args': SimpleNamespace(capture_menu=menu, menu_replay=replay)}
        exec(compile(ast.Module(body=selections, type_ignores=[]),
                     'actual capture selection', 'exec'), namespace)
        recorded = eval(compile(ast.Expression(fields['environment']),
                                'actual launch environment', 'eval'), namespace)
        if label == 'raw':
            assert env == {'RSX_CAP': 'authored-raw-config'}, 'raw diagnostic selection changed'
        else:
            assert env.get('RSX_CAP_SCREEN_ONLY') == '1', 'screen mode not selected'
            assert recorded.get('RSX_CAP_SCREEN_ONLY') == '1', 'screen mode not recorded'
            assert env['RSX_CAP'] == '1:100:120', 'capture budget changed'
        receipts.append(dict(case=label, environment=recorded))
    return receipts


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
    if result.returncode or b'screen_checks=14 failures=0' not in result.stdout:
        raise SystemExit((result.stdout+result.stderr).decode(errors='replace'))
    control = subprocess.run([str(exe), '--ignore-screen'], capture_output=True, timeout=15)
    (out/'screen-control.log').write_bytes(control.stdout+control.stderr)
    assert control.returncode == 1 and b'screen_checks=14 failures=1' in control.stdout
    assert b'periodic offscreen alias' in control.stderr, 'historical alias control failed elsewhere'
    tree = ast.parse((ROOT/'scripts/run.py').read_text())
    launch_receipts = screen_launch(tree, out/'launcher')
    old = copy.deepcopy(tree)
    for node in ast.walk(old):
        if isinstance(node, ast.Call):
            node.keywords = [kw for kw in node.keywords if kw.arg != 'RSX_CAP_SCREEN_ONLY']
    try:
        screen_launch(old, out/'historical-launcher')
    except AssertionError as error:
        assert str(error) == 'screen mode not selected', error
    else:
        raise AssertionError('historical launcher omission accepted')
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
        returncode=result.returncode, screen_control=control.returncode,
        screen_launch=launch_receipts, launch_preflight=guards), indent=2))
    print(result.stdout.decode(errors='replace').strip())
    print(result.stderr.decode(errors='replace').strip())
    print('Evidence:', out)
    if not all(check['passed'] for check in guards):
        raise SystemExit('FAIL: burst preflight did not reject before launch validation')
    print('PASS: invalid burst budgets and missing menu capture rejected before launch')
    print('PASS: screen selection, launch record and historical alias/launcher controls')
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
