"""Compile the actual baseline adapter against an independent authored ABI seam."""
from pathlib import Path
import json
import os
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    out = root / 'build/self-tests/native-visibility-adapter'
    out.mkdir(parents=True, exist_ok=True)
    source = root / 'src/motorstorm/visibility_adapter.cpp'
    fixture = root / 'scripts/fixtures/native_visibility_adapter.cpp'
    compiler = os.environ.get('MV_CLANG') or os.environ.get('CXX') or shutil.which('clang-cl' if os.name == 'nt' else 'c++')
    assert compiler, 'Set MV_CLANG/CXX'

    def build(label, adapter):
        folder = out / label
        folder.mkdir(exist_ok=True)
        objects, commands, log = [], [], ''
        for i, path in enumerate([root / 'src/motorstorm/native_cpu.cpp', fixture, adapter,
                                  root / 'src/motorstorm/visibility_planes.cpp']):
            obj = folder / f'source{i}{".obj" if os.name == "nt" else ".o"}'
            objects.append(str(obj))
            if os.name == 'nt':
                command = [compiler, '/nologo', '/std:c++17', '/O2', '/UNDEBUG', '/EHsc', '/fp:strict',
                           '/DMOTORSTORM_VISIBILITY_FIXTURE', '/I' + str(source.parent),
                           '/I' + str(fixture.parent), '/c', str(path), '/Fo' + str(obj)]
                if i == 3: command += ['/arch:AVX2']
            else:
                command = [compiler, '-std=c++17', '-O2', '-UNDEBUG', '-ffp-contract=off', '-frounding-math',
                           '-DMOTORSTORM_VISIBILITY_FIXTURE', '-I' + str(source.parent),
                           '-I' + str(fixture.parent), '-c', str(path), '-o', str(obj)]
                if i == 3: command += ['-mavx2', '-mfma']
            commands.append(command)
            result = subprocess.run(command, text=True, capture_output=True)
            log += result.stdout + result.stderr
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
        return exe

    def run(exe, mode, command='all', extra=None):
        env = dict(os.environ, MS_NATIVE_VISIBILITY=mode)
        for name in ['SPU_LS_LOWREAD', 'SPU_LS_WATCH', 'SPU_SMC_WATCH', 'SPU_PCHIST']:
            env.pop(name, None)
        env.update(extra or {})
        result = subprocess.run([str(exe), command], env=env, text=True, capture_output=True)
        (exe.parent / f'{mode}-{command}.log').write_text(result.stdout + result.stderr)
        return result

    exe = build('production', source)
    for mode in ['0', 'shadow', '1']:
        result = run(exe, mode)
        print(result.stdout, end='')
        result.check_returncode()
    for mode in ['0','1']:
        result=run(exe,mode,'leaf_only');print(result.stdout,end='');result.check_returncode()
    result=run(exe,'shadow','snapshot_only');print(result.stdout,end='');result.check_returncode()
    for mode, command, extra in [('1', 'unsupported', None), ('1', 'instrumented', {'SPU_PCHIST': '1'})]:
        result = run(exe, mode, command, extra)
        result.check_returncode()
    result = run(exe, 'bad', 'invalid')
    assert result.returncode != 0 and 'NATIVE_VISIBILITY_ERROR MS_NATIVE_VISIBILITY must be' in result.stderr, result.stderr
    text = source.read_text()
    mutant = out / 'preferred-only.cpp'
    before = 'for (unsigned lane = 0; lane < 4; ++lane) {\n        ctx->gpr[13]'
    assert text.count(before) == 1
    mutant.write_text(text.replace(before, before.replace('lane < 4', 'lane < 1')))
    exe = build('preferred-only', mutant)
    result = run(exe, '1')
    assert result.returncode == 1 and 'Adapter full-context parity' in result.stderr, result.stderr
    result = run(exe, 'shadow')
    assert result.returncode != 0 and 'NATIVE_VISIBILITY_SHADOW_MISMATCH' in result.stderr, result.stderr
    mutant=out/'racy-shadow-snapshot.cpp'
    before='std::memcpy(candidate,reference,sizeof(*ctx));'
    assert text.count(before)==1
    mutant.write_text(text.replace(before,'std::memcpy(candidate,ctx,sizeof(*ctx));'))
    exe=build('racy-shadow-snapshot',mutant)
    result=run(exe,'shadow','snapshot_only')
    assert result.returncode!=0 and 'NATIVE_VISIBILITY_SHADOW_MISMATCH' in result.stderr,result.stderr
    mutant = out / 'wrong-instruction-count.cpp'
    before='84 * prepared.result.tested + (prepared.result.rejected ? 62 : 63)'
    assert text.count(before)==1
    mutant.write_text(text.replace(before,before.replace('62 : 63','61 : 62')))
    exe=build('wrong-instruction-count',mutant)
    result=run(exe,'1','leaf_only')
    assert result.returncode==1 and 'Exact interpreter leaf plan accounting' in result.stderr,result.stderr
    mutant=out/'missing-policy-fetch.cpp'
    before='if (ctx->policy_mode) ctx->wi_prev_pc=last_pc(prepared);'
    assert text.count(before)==1
    mutant.write_text(text.replace(before,''))
    exe=build('missing-policy-fetch',mutant)
    result=run(exe,'1','leaf_only')
    assert result.returncode==1 and 'Interpreter leaf full-context parity' in result.stderr,result.stderr
    mutant = out / 'premature-write.cpp'
    before = 'native_visibility_fixture_after_math(const_cast<spu_context*>(ctx));'
    assert text.count(before) == 1
    mutant.write_text(text.replace(before, 'commit(const_cast<spu_context*>(ctx), prepared); ' + before))
    exe = build('premature-write', mutant)
    result = run(exe, '1', 'guard_only')
    assert result.returncode == 1 and 'Original fallback has no partial guest writes' in result.stderr, result.stderr
    mutant = out / 'missing-corner-guard.cpp'
    before = 'if (!supported_corners(prepared.corners))'
    assert text.count(before) == 1
    mutant.write_text(text.replace(before, 'if (false)'))
    exe = build('missing-corner-guard', mutant)
    result = run(exe, '1', 'numeric_only')
    assert result.returncode == 1 and 'Original fallback has no partial guest writes' in result.stderr, result.stderr
    mutant = out / 'wrong-coefficient.cpp'
    before = 'const float values[] = {point.x,point.y,point.z,1.0f};'
    assert text.count(before) == 1
    mutant.write_text(text.replace(before, before.replace('1.0f', '0.0f')))
    exe = build('wrong-coefficient', mutant)
    result = run(exe, '1')
    assert result.returncode == 1 and 'Adapter full-context parity' in result.stderr, result.stderr
    result = run(exe, 'shadow')
    assert result.returncode != 0 and 'NATIVE_VISIBILITY_SHADOW_MISMATCH' in result.stderr, result.stderr
    print('PASS: full-state/transaction mutants rejected; shadow mismatch fatal; original fallback and baseline admission verified')


if __name__ == '__main__':
    main()
