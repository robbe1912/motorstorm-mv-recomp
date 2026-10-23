"""Check the typed scan against an independent scalar oracle and unsafe mutants."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--compiler', default=os.environ.get('MV_CLANG') or os.environ.get('CXX') or
                    shutil.which('clang-cl' if os.name == 'nt' else 'c++'))
args = parser.parse_args()
assert args.compiler, 'Set CXX/MV_CLANG or --compiler'
out = root / 'build/self-tests/native-threshold-scan'
source = root / 'src/motorstorm/threshold_scan.cpp'
fixture = root / 'scripts/fixtures/native_threshold_scan.cpp'


def check(name, contents):
    directory = out / name
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / 'scan.cpp'
    candidate.write_text(contents)
    exe = directory / ('fixture.exe' if os.name == 'nt' else 'fixture')
    if os.name == 'nt':
        command = [args.compiler, '/nologo', '/std:c++17', '/O2', '/UNDEBUG', '/EHsc', '/fp:strict',
                   '/I' + str(source.parent), str(candidate), str(fixture),
                   '/Fo' + str(directory) + os.sep, '/Fe' + str(exe)]
    else:
        command = [args.compiler, '-std=c++17', '-O2', '-UNDEBUG', '-ffp-contract=off',
                   '-frounding-math', '-I' + str(source.parent), str(candidate), str(fixture), '-o', str(exe)]
    (directory / 'command.json').write_text(json.dumps(command, indent=2))
    built = subprocess.run(command, capture_output=True, text=True)
    (directory / 'build.log').write_text(built.stdout + built.stderr)
    assert built.returncode == 0, built.stdout + built.stderr
    ran = subprocess.run([str(exe)], cwd=directory, capture_output=True, text=True, timeout=30)
    (directory / 'run.log').write_text(ran.stdout + ran.stderr)
    return ran.returncode


text = source.read_text()
assert check('production', text) == 0, 'Production threshold scan failed'
mutations = {
    'wrong-reduction': ('const auto largest = std::max(std::max(values[0], values[1]),\n'
                        '                                          std::max(values[2], values[3]));',
                        'const auto largest = std::min(std::min(values[0], values[1]),\n'
                        '                                          std::min(values[2], values[3]));'),
    'missing-rotation': ('values[(c + view) % 4]', 'values[c % 4]'),
    'unchecked-saturated-input': ('const auto used =', 'if (complete(flags)) return flags;\n    const auto used ='),
    'lost-initial-flags': ('std::size_t remaining = sample_count;',
                           'flags = {};\n    std::size_t remaining = sample_count;'),
}
for name, (before, after) in mutations.items():
    assert text.count(before) == 1, name
    assert check(name, text.replace(before, after)) != 0, name + ' escaped'
print('PASS: typed threshold oracle, 8192 randomized cases, boundaries/FP/immutable inputs; four unsafe mutants rejected')
