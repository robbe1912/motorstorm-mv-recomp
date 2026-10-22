"""Check the handwritten plane operation; original-AOT/game admission is separate."""
from pathlib import Path
import json
import os
import platform
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    assert platform.machine().lower() in ('amd64', 'x86_64'), 'Requires x86-64'
    out = root / 'build/self-tests/native-visibility-planes'
    out.mkdir(parents=True, exist_ok=True)
    source = root / 'src/motorstorm/visibility_planes.cpp'
    fixture = root / 'scripts/fixtures/native_visibility_planes.cpp'
    baseline = root / 'src/motorstorm/native_cpu.cpp'
    compiler = os.environ.get('MV_CLANG') or os.environ.get('CXX') or shutil.which('clang-cl' if os.name == 'nt' else 'c++')
    assert compiler, 'Set MV_CLANG/CXX to a C++ compiler path'

    def run(label, implementation):
        folder = out / label
        folder.mkdir(exist_ok=True)
        objects = []
        commands = []
        log = ''
        for i, path in enumerate([baseline, fixture, implementation]):
            obj = folder / f'source{i}{".obj" if os.name == "nt" else ".o"}'
            objects.append(str(obj))
            if os.name == 'nt':
                command = [compiler, '/nologo', '/std:c++17', '/O2', '/UNDEBUG', '/EHsc', '/fp:strict',
                           '/I' + str(source.parent), '/c', str(path), '/Fo' + str(obj)]
                if i == 2: command.append('/arch:AVX2')
            else:
                command = [compiler, '-std=c++17', '-O2', '-UNDEBUG', '-ffp-contract=off', '-frounding-math',
                           '-I' + str(source.parent), '-c', str(path), '-o', str(obj)]
                if i == 2: command += ['-mavx2', '-mfma']
            result = subprocess.run(command, text=True, capture_output=True)
            log += result.stdout + result.stderr
            commands.append(command)
            (folder / 'build.log').write_text(log)
            result.check_returncode()
        exe = folder / ('fixture.exe' if os.name == 'nt' else 'fixture')
        command = ([compiler, '/nologo', *objects, '/Fe:' + str(exe)] if os.name == 'nt'
                   else [compiler, *objects, '-o', str(exe)])
        commands.append(command)
        (folder / 'commands.json').write_text(json.dumps(commands, indent=2))
        result = subprocess.run(command, text=True, capture_output=True)
        (folder / 'build.log').write_text(log + result.stdout + result.stderr)
        result.check_returncode()
        result = subprocess.run([str(exe)], text=True, capture_output=True)
        (folder / 'run.log').write_text(result.stdout + result.stderr)
        return result

    positive = run('production', source)
    print(positive.stdout + positive.stderr, end='')
    positive.check_returncode()
    text = source.read_text()
    mutations = [
        ('rounding', '| 0x6000u', '| 0u', 'Independent toward-zero plane product'),
        ('comparison', '_CMP_LT_OQ', '_CMP_LE_OQ', 'Boundary equality'),
        ('corners', '_mm256_movemask_ps(outside) != 0', '_mm256_movemask_ps(outside) == 255', 'any failing corner'),
        ('fusion', '_mm256_fmadd_ps(y, _mm256_set1_ps(plane.y), distance)',
         '_mm256_add_ps(_mm256_mul_ps(y, _mm256_set1_ps(plane.y)), distance)', 'Independent fused plane cancellation'),
    ]
    for label, old, new, error in mutations:
        assert text.count(old) == 1
        mutant = out / f'{label}.cpp'
        mutant.write_text(text.replace(old, new, 1))
        result = run(label, mutant)
        assert result.returncode == 1 and error in result.stderr, result.stdout + result.stderr
    print('PASS: wrong rounding/comparison/corner reduction/fusion mutants rejected')


if __name__ == '__main__':
    main()
