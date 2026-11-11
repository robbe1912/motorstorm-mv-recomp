"""Check production baseline-ISA shuffle values, host admission and fallback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
SPU = ROOT/'vendor/ps3recomp/runtime/spu'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-simd-code', action='store_true',
                        help='Require an SSSE3 host and actual pshufb emission')
    parser.add_argument('--historical-helper', type=Path,
                        help='Actual old spu_helpers.h: values must pass but admission must fail')
    args = parser.parse_args()
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        compiler = env['MV_CLANG']
    else:
        compiler = shutil.which(env.get('CC', 'cc'))
        if not compiler:
            raise SystemExit('A C/C++ compiler is required')
    disassembler = (shutil.which('llvm-objdump', path=env.get('PATH')) or
                    shutil.which('objdump', path=env.get('PATH')) or
                    str(Path(compiler).with_name('llvm-objdump.exe')))
    out = ROOT/'temp/checks'/('spu-shuffle-'+str(time.time_ns()))
    out.mkdir(parents=True)
    fixture = ROOT/'scripts/fixtures/spu_shufb_dispatch.c'
    records = []
    cases = ['dispatch', 'scalar', 'cpp'] + (['historical'] if args.historical_helper else [])
    for name in cases:
        folder = out/name
        folder.mkdir()
        source = folder/'caller.c'
        source.write_bytes(fixture.read_bytes())
        includes = [SPU]
        if name == 'historical':
            (folder/'spu_helpers.h').write_bytes(args.historical_helper.read_bytes())
            includes.insert(0, folder)
        obj = folder/('caller.obj' if os.name == 'nt' else 'caller.o')
        exe = folder/('check.exe' if os.name == 'nt' else 'check')
        if os.name == 'nt':
            compile_cmd = [compiler, '/nologo', '/c', '/O2', '/UNDEBUG',
                           '/TP' if name == 'cpp' else '/TC']
            compile_cmd += ['/I'+str(p) for p in includes]
            if name == 'scalar':
                compile_cmd += ['/DSPU_SHUFB_FORCE_SCALAR']
            compile_cmd += [str(source), '/Fo'+str(obj)]
            link_cmd = [compiler, '/nologo', str(obj), '/Fe'+str(exe)]
        else:
            compile_cmd = [compiler, '-x', 'c++' if name == 'cpp' else 'c',
                           '-std=c++17' if name == 'cpp' else '-std=c11', '-O2', '-UNDEBUG']
            if platform.machine().lower() in ('x86_64', 'amd64'):
                compile_cmd += ['-march=x86-64', '-mtune=generic']
            compile_cmd += [part for p in includes for part in ('-I', str(p))]
            if name == 'scalar':
                compile_cmd += ['-DSPU_SHUFB_FORCE_SCALAR']
            compile_cmd += ['-c', str(source), '-o', str(obj)]
            link_cmd = [compiler, str(obj), '-lm', '-o', str(exe)]
        for label, command in [('compile', compile_cmd), ('link', link_cmd)]:
            result = subprocess.run(command, env=env, cwd=folder, capture_output=True, timeout=120)
            (folder/(label+'.log')).write_bytes(result.stdout+result.stderr)
            if result.returncode:
                raise SystemExit((result.stdout+result.stderr).decode(errors='replace'))
        run = subprocess.run([str(exe)], env=env, capture_output=True, text=True, timeout=30)
        (folder/'check.log').write_text(run.stdout+run.stderr)
        if run.returncode or '204096 value cases passed' not in run.stdout:
            raise SystemExit('Shuffle value oracle failed: '+run.stdout+run.stderr)
        admission = 'simd=1' in run.stdout
        has_shuffle = None
        if args.require_simd_code:
            assembly = subprocess.check_output([disassembler, '-d', str(obj)], env=env, text=True, timeout=30)
            (folder/'caller.asm').write_text(assembly)
            has_shuffle = bool(re.search(r'\bpshufb\b', assembly))
            expected = name in ('dispatch', 'cpp')
            if admission != expected or has_shuffle != expected:
                raise SystemExit(name+': use production spu_shuffle.h checked dispatch; '
                                 'baseline C/C++ require positive admission, forced scalar and historical do not')
        records.append(dict(name=name, admission=admission, pshufb=has_shuffle,
                            value_cases=204096, compile=compile_cmd))
        print(name+': '+run.stdout.strip().replace('\n', '; '))
    (out/'result.json').write_text(json.dumps(dict(game_inputs=False, records=records,
        sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (fixture, SPU/'spu_helpers.h', SPU/'spu_shuffle.h')}), indent=2))
    print('Evidence:', out)


if __name__ == '__main__':
    main()
