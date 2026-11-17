"""Check owned policy observations and reject address, register and backing errors."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--compiler')
args = parser.parse_args()
env = os.environ.copy()
if os.name == 'nt' and not args.compiler:
    from project import build_environment
    env = build_environment()
compiler = args.compiler or env.get('MV_CLANG') or shutil.which('c++')
assert compiler
msvc = Path(compiler).stem.lower() in ('cl', 'clang-cl')
source = ROOT / 'src/motorstorm/job_policy_observation.h'
fixture = ROOT / 'scripts/fixtures/job_policy_observation.cpp'
out = ROOT / 'build/self-tests/job-policy-observation'
out.mkdir(parents=True, exist_ok=True)
text = source.read_text(encoding='utf-8')
# Header overrides keep the actual SDK context definition through an absolute include.
text = text.replace('../../vendor/ps3recomp/runtime/spu/spu_context.h',
                    (ROOT / 'vendor/ps3recomp/runtime/spu/spu_context.h').as_posix())
report = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
          'commands': [], 'mutants_rejected': []}

def run(variant, name):
    directory = out / name
    directory.mkdir(exist_ok=True)
    (directory / source.name).write_text(variant, encoding='utf-8')
    exe = directory / ('fixture.exe' if os.name == 'nt' else 'fixture')
    cmd = [compiler, str(fixture)]
    if msvc:
        cmd += ['/nologo', '/std:c++17', '/EHsc', '/O1', '/UNDEBUG',
                '/D_CRT_SECURE_NO_WARNINGS', '/I'+str(directory),
                '/I'+str(ROOT/'vendor/ps3recomp/include'), '/Fe'+str(exe)]
    else:
        cmd += ['-std=c++17', '-O1', '-UNDEBUG', '-Wall', '-Wextra', '-Werror',
                '-I'+str(directory), '-I'+str(ROOT/'vendor/ps3recomp/include'), '-o', str(exe)]
    for phase, command in [('build', cmd), ('run', [str(exe)])]:
        result = subprocess.run(command, cwd=directory, env=env, capture_output=True,
                                text=True, timeout=60)
        (directory/(phase+'.log')).write_text(result.stdout+result.stderr, encoding='utf-8')
        report['commands'].append({'command': command, 'returncode': result.returncode})
        if phase == 'build':
            assert result.returncode == 0, result.stdout+result.stderr
    return result

assert run(text, 'production').returncode == 0
mutants = {
    'wrong-running-slot': ('ls + 0x12e0', 'ls + 0x1410'),
    'wrong-lane': ('ls + 0x1340', 'ls + 0x1330'),
    'wrong-record-base': ('ls + 0x1430', 'ls + 0x1450'),
    'wrong-register-lane': ('._u32[3]', '._u32[0]'),
    'mapped-backing': ('ls != context->ls_store', 'false && ls != context->ls_store'),
    'unchecked-clock': ('!result.before_tick || result.after_tick < result.before_tick', 'false'),
    'mutates-local-store': ('result.flags = JOB_POLICY_PRIVATE_LS;',
                          'result.flags = JOB_POLICY_PRIVATE_LS; const_cast<uint8_t*>(ls)[0x1430] ^= 1;'),
}
for name, (old, new) in mutants.items():
    assert text.count(old) == 1, name
    assert run(text.replace(old, new), name).returncode != 0, name+' survived'
    report['mutants_rejected'].append(name)
report['passed'] = True
(out/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('PASS owned policy observation and seven semantic controls')
