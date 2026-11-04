"""Execute the production private MFC registry and historical warm-lock control."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT/'vendor/ps3recomp/runtime/spu'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical-source', type=Path,
                        help='Actual pre-cache spu_channels.c; must fail the warm-lock contract')
    args = parser.parse_args()
    out = ROOT/'temp/checks'/('mfc-registry-'+datetime.datetime.now(
        datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
    out.mkdir(parents=True)
    source = ROOT/'scripts/fixtures/spu_mfc_registry.c'
    header = RUNTIME/'spu_mfc_registry.h'
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        compiler = env['MV_CLANG']
    else:
        env = os.environ.copy()
        compiler = shutil.which(env.get('CC', 'cc'))
        if not compiler:
            raise SystemExit('A C11 compiler is required')
    cases = [('production', header.read_text(), True),
             ('cache-disabled', header.read_text().replace(
                 'if (s_mfc_cached.ctx == ctx && s_mfc_cached.generation == generation)',
                 'if (0)'), False)]
    if args.historical_source:
        text = args.historical_source.read_text()
        start = text.index('#define SPU_MAX_CONTEXTS 8')
        end = text.index('/* ===========================================================================\n * Atomic reservation', start)
        cases.append(('historical', text[start:end], False))
    results = []
    for name, code, accepted in cases:
        folder = out/name
        folder.mkdir()
        (folder/source.name).write_bytes(source.read_bytes())
        (folder/header.name).write_text(code)
        exe = folder/('check.exe' if os.name == 'nt' else 'check')
        include = ROOT/'vendor/ps3recomp/runtime/platform'
        if os.name == 'nt':
            command = [compiler, '/nologo', '/std:c17', '/TC', '/O2', '/UNDEBUG',
                       '/I'+str(include), str(folder/source.name), '/Fe'+str(exe)]
        else:
            command = [compiler, '-std=c11', '-D_GNU_SOURCE', '-O2', '-UNDEBUG', '-pthread',
                       '-I'+str(include), str(folder/source.name),
                       str(include/'win32_compat.c'), '-o', str(exe)]
        compiled = subprocess.run(command, cwd=folder, env=env, capture_output=True, timeout=120)
        (folder/'compile.log').write_bytes(compiled.stdout+compiled.stderr)
        if compiled.returncode:
            raise SystemExit((compiled.stdout+compiled.stderr).decode(errors='replace'))
        run = subprocess.run([str(exe)], cwd=folder, env=env, capture_output=True, timeout=30)
        output = (run.stdout+run.stderr).decode(errors='replace')
        (folder/'check.log').write_text(output)
        passed = (run.returncode == 0 and 'checks=11 failures=0 warm_locks=0' in output
                  if accepted else run.returncode == 1 and
                  'FAIL 32000 warm lookups acquire no registry locks' in output and
                  'checks=11 failures=1 warm_locks=24000' in output)
        results.append(dict(name=name, passed=passed, returncode=run.returncode))
        print(name+': '+output.strip())
    (out/'result.json').write_text(json.dumps(dict(game_inputs=False, results=results,
        sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, header)}), indent=2))
    print('Evidence:', out)
    if not all(row['passed'] for row in results):
        raise SystemExit('MFC registry contract or historical control failed')


if __name__ == '__main__':
    main()
