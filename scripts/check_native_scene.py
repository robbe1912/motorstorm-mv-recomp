"""Compile the actual game bridge against authored memory; verify transaction and fallback."""
import os
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    if platform.machine().lower() not in {'amd64', 'x86_64'}:
        raise SystemExit('Native scene regression requires x86-64')
    compiler = os.environ.get('MV_CLANG') or os.environ.get('CXX') or shutil.which('clang-cl' if os.name == 'nt' else 'c++')
    if not compiler:
        raise SystemExit('Set MV_CLANG/CXX to the native C++ compiler')
    out = ROOT/'build/self-tests/native-scene'
    out.mkdir(parents=True, exist_ok=True)
    fixture = ROOT/'scripts/fixtures'
    source = ROOT/'src/motorstorm'
    windows = os.name == 'nt'
    common = (['/nologo','/std:c++17','/O2','/UNDEBUG','/EHsc', '/DMOTORSTORM_SCENE_FIXTURE',
               '/I'+str(source),'/I'+str(fixture)] if windows else
              ['-std=c++17','-O2','-UNDEBUG','-fexceptions','-DMOTORSTORM_SCENE_FIXTURE',
               '-I'+str(source),'-I'+str(fixture)])

    def compile_file(path, name, vector=False):
        obj = out/(name+('.obj' if windows else '.o'))
        flags = (['/arch:AVX2','/fp:strict'] if windows else
                 ['-mavx2','-mfma','-ffp-contract=off','-frounding-math']) if vector else []
        command = [compiler,*common,*flags, '/c' if windows else '-c',str(path)]
        command += ['/Fo'+str(obj)] if windows else ['-o',str(obj)]
        result = subprocess.run(command,cwd=out,capture_output=True,text=True)
        (out/(name+'-build.log')).write_text(result.stdout+result.stderr)
        if result.returncode:
            raise SystemExit(result.stdout+result.stderr)
        return obj

    cpu = compile_file(source/'native_cpu.cpp','cpu-baseline')
    core = compile_file(source/'world_transforms.cpp','world-vector',True)
    fixture_obj = compile_file(fixture/'native_scene.cpp','fixture-baseline')

    def run(adapter, name, reference=False):
        obj = compile_file(adapter,name)
        exe = out/(name+('.exe' if windows else ''))
        command = [compiler,str(cpu),str(core),str(fixture_obj),str(obj)]
        command += ['/Fe'+str(exe)] if windows else ['-o',str(exe)]
        built = subprocess.run(command,cwd=out,capture_output=True,text=True)
        (out/(name+'-link.log')).write_text(built.stdout+built.stderr)
        if built.returncode:
            raise SystemExit(built.stdout+built.stderr)
        env = dict(os.environ,MS_NATIVE_HIERARCHY='0' if reference else '1')
        result = subprocess.run([str(exe),*(['reference'] if reference else [])],env=env,capture_output=True,text=True)
        (out/(name+'-run.log')).write_text(result.stdout+result.stderr)
        return result

    actual = source/'scene_hierarchy.cpp'
    for reference in (False,True):
        result = run(actual,'reference' if reference else 'positive',reference)
        if result.returncode:
            raise SystemExit(result.stdout+result.stderr)
        print(result.stdout.strip())
    text = actual.read_text()
    token = 'native_commit_array(h.world_ea,h.expected_world)'
    assert text.count(token) == 1
    mutant = out/'bad-commit.cpp'
    mutant.write_text(text.replace(token,'native_commit_array(h.world_ea,h.before_world)'))
    result = run(mutant,'bad-commit')
    assert result.returncode == 1 and 'FAIL: Native world/flag transaction' in result.stderr, result.stdout+result.stderr
    print('PASS bad-commit mutant: returning without computed world writes is rejected')


if __name__ == '__main__':
    main()
