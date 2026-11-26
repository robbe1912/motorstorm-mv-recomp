"""Check standalone particle collision math and its bounded publication adapter."""
import os
from pathlib import Path
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / 'build/self-tests/native-particle-collision'
    output.mkdir(parents=True, exist_ok=True)
    source = root / 'src/motorstorm'
    spu = root / 'vendor/ps3recomp/runtime/spu'
    sdk = root / 'vendor/ps3recomp/include'
    windows = os.name == 'nt'
    cc = os.environ.get('MV_CLANG') or os.environ.get('CC') or shutil.which('clang-cl' if windows else 'cc')
    cxx = cc if windows else os.environ.get('CXX') or shutil.which('c++')
    if not cc or not cxx:
        raise RuntimeError('Set native C and C++ compilers')
    includes = [('/I' if windows else '-I') + str(p) for p in (source, spu, sdk)]
    objects = []
    for file in (source / 'particle_box_collision.c', spu / 'spu_float_simd.c'):
        obj = output / (file.stem + ('.obj' if windows else '.o'))
        options = ['/nologo', '/TC', '/std:c17', '/O2', '/UNDEBUG', '/fp:strict', '/c', '/Fo' + str(obj)] if windows else ['-std=gnu17', '-O2', '-UNDEBUG', '-ffp-contract=off', '-frounding-math', '-c', '-o', str(obj)]
        with (output / (file.stem + '.log')).open('w', encoding='utf-8') as log:
            subprocess.run([cc, *options, *includes, str(file)], cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True)
        objects.append(str(obj))
    for name, compiler, cpp in [('native_particle_collision', cc, False), ('native_particle_collision_adapter', cxx, True)]:
        fixture = root / 'scripts/fixtures' / (name + ('.cpp' if cpp else '.c'))
        executable = output / (name + ('.exe' if windows else ''))
        if windows:
            # The bound adapter uses try and catch for the shadow comparison, as the game build does (/EHsc).
            # The adapter fixture replaces the environment and switches the mode while it runs.
            adapter = ['-EHsc', '-DMOTORSTORM_PARTICLE_FIXTURE'] if cpp else []
            options = ['/nologo', '/std:c++17' if cpp else '/std:c17', '/O2', '/UNDEBUG', *adapter,
                       '/Fe' + str(executable), str(fixture), '/link', *objects]
        else:
            adapter = ['-DMOTORSTORM_PARTICLE_FIXTURE'] if cpp else []
            options = ['-std=c++17' if cpp else '-std=gnu17', '-O2', '/UNDEBUG', *adapter, '-o', str(executable),
                       str(fixture), *objects, '-lm']
        with (output / (name + '.log')).open('w', encoding='utf-8') as log:
            subprocess.run([compiler, *includes, *options], cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run([str(executable)], cwd=output, check=True)


if __name__ == '__main__':
    main()
