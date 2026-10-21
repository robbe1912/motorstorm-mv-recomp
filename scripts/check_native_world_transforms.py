"""Build the actual native matrix operation and independent arithmetic controls."""
from pathlib import Path
import os
import platform
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    assert platform.machine().lower() in ('amd64', 'x86_64'), 'Requires an x86-64 AVX/FMA host'
    out = root / 'build/self-tests/native-world-transforms'
    out.mkdir(parents=True, exist_ok=True)
    source = root / 'src/motorstorm/world_transforms.cpp'
    fixture = root / 'scripts/fixtures/native_world_transforms.cpp'
    compiler = os.environ.get('MV_CLANG') or os.environ.get('CXX') or shutil.which('clang-cl' if os.name == 'nt' else 'c++')
    assert compiler, 'Set MV_CLANG/CXX to a C++ compiler path'

    def build_and_run(label, implementation):
        folder = out / label
        folder.mkdir(exist_ok=True)
        exe = folder / ('fixture.exe' if os.name == 'nt' else 'fixture')
        if os.name == 'nt':
            command = [compiler, '/nologo', '/std:c++17', '/O2', '/UNDEBUG', '/EHsc', '/arch:AVX2', '/fp:strict',
                       '/I' + str(source.parent), str(implementation), str(fixture),
                       '/Fo' + str(folder) + os.sep, '/Fe:' + str(exe)]
        else:
            command = [compiler, '-std=c++17', '-O2', '-UNDEBUG', '-mavx2', '-mfma', '-ffp-contract=off',
                       '-frounding-math', '-I' + str(source.parent), str(implementation), str(fixture), '-o', str(exe)]
        result = subprocess.run(command, text=True, capture_output=True)
        (folder / 'build.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        result = subprocess.run([str(exe)], text=True, capture_output=True)
        (folder / 'run.log').write_text(result.stdout + result.stderr)
        return result

    positive = build_and_run('production', source)
    print(positive.stdout + positive.stderr, end='')
    positive.check_returncode()
    # A real historical failure: nearest rounding differs from the job outputs.
    text = source.read_text()
    assert text.count('| 0x6000u') == 1
    mutant = out / 'wrong_rounding.cpp'
    mutant.write_text(text.replace('| 0x6000u', '| 0u', 1))
    negative = build_and_run('wrong-rounding', mutant)
    assert negative.returncode == 1 and 'Independent toward-zero product oracle' in negative.stderr, negative.stdout + negative.stderr
    print('PASS: wrong-rounding implementation rejected by independent oracle')


if __name__ == '__main__':
    main()
