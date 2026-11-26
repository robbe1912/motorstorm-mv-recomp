"""Checks the build-time binding of the native vehicle update entry through the real lifted entry
of SPU image 219.

scripts/native_game_binding.py renames the lifted function jobmod_8de1770ee613_e1cd40_spu_func_00011FE0
to game_original_vehicle_update. The lifted name becomes a wrapper of motorstorm_vehicle_update_entry.
This check applies the same contract to the generated unit. It compiles the unit with the SPU
runtime, the adapter and the kernel. It runs scripts/fixtures/native_vehicle_update_binding.cpp on
the kernel pairs. The native entry must run for each pair. The context after the wrapper must
equal the context after the lifted function, before and after the drain of the call bracket.

It also runs these cases:
  mode reference, a changed code byte, a kernel that stops after one store: 0 native runs and
  equal results;
  six adapter mutants on these cases: each must fail.

The check needs local inputs: config/local.json (keys elf and spu_generated) and the kernel pairs.
Without them it prints SKIP and returns 0. Windows with clang-cl only.

Usage: python scripts/check_vehicle_update_binding.py [<pairs directory>]
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import native_game_binding as binding  # noqa: E402
import project  # noqa: E402
from check_spu_pm_services import EXTRA, NAMES, SDK, SPU  # noqa: E402

UNIT = 'jobmod_8de1770ee613_e1cd40'
# sha256 of the body of the lifted function (temp/vehicleport/find_windows4.py). The windows are
# three code ranges of image 219: the entry function, a hot function, the call site after the extent.
VEHICLE_UPDATE = binding.Contract(
    binding.PRODUCTION.elf_sha256,
    '70924550221ba0c8bb06a6a83ad0459f78662c9ccdd541a922613ef4467d17fb',
    UNIT + '_spu_func_00011FE0', 'game_original_vehicle_update', 'motorstorm_vehicle_update_entry',
    context='spu_context', directory='spu/' + UNIT, matcher='game_vehicle_update_code_matches',
    windows=((0xf98d60, 0x11FE0, 416), (0xf9b234, 0x144B4, 1100), (0xfa7a30, 0x20CB0, 64)))
SOURCE = ROOT / 'src/motorstorm'
ADAPTER = SOURCE / 'vehicle_update_adapter.cpp'
KERNEL = SOURCE / 'vehicle_update.c'
FIXTURES = ROOT / 'scripts/fixtures'
OUT = ROOT / 'build/self-tests/native-vehicle-update-binding'
# Options of the lead build: global (CMakeLists.txt), vendor runtime (vendor/ps3recomp/CMakeLists.txt),
# lifted SPU units (CMakeLists.txt and src/guest_optimization.cmake). The kernel has the options of
# a lifted unit. The adapter has the options of a native source with /clang:-O2.
GLOBAL = ['/nologo', '/UNDEBUG', '/MDd', '/D_CRT_SECURE_NO_WARNINGS', '/clang:-O1', '/Ob1',
          '/clang:-fno-strict-aliasing', '/clang:-ffp-contract=off']
RUNTIME = GLOBAL + ['/clang:-msse4.1']
LIFTED = GLOBAL + ['/clang:-O2', '/clang:-mssse3', '/w', '/bigobj', '/Ob2', '/arch:AVX2',
                   '/DSPU_USE_DISPATCH_MT', '/DSPU_SIMD=1', '/DSPU_FLOAT_FAST=1']
NATIVE = GLOBAL + ['/clang:-O2', '/Ob2', '/EHsc', '/DSPU_SIMD=1', '/DSPU_FLOAT_FAST=1']
INCLUDES = [SDK / 'include', SDK / 'runtime/spu', SDK / 'runtime/platform']
LIMIT = 180  # seconds for one run of a case
ZERO = ('differences_after_drain', 'trampoline_differences', 'pre_state_differences',
        'pair_differences', 'lifted_pair_mismatches')
# (name, file, pattern, replacement, arguments of the run)
STOP_KERNEL = (KERNEL, r'(static vu_status vu_b_011FE0\(MotorstormVehicleState\* s\) \{)',
               r'\1 vu_write(s, 0x30000, spu_il(1)); return vu_bail(s, 0x11FE4);')
MUTANTS = [
    ('no_register_commit', ADAPTER, r'std::memcpy\(ctx->gpr, state\.gpr, sizeof ctx->gpr\);', ';', ()),
    ('no_pc', ADAPTER, r'ctx->pc = state\.gpr\[0\]._u32\[0\];', ';', ()),
    ('no_restore', ADAPTER, r'if \(state\.dirty & \(1ull << page\)\)', 'if (false)', ('--expect-stopped',)),
    ('no_code_identity', ADAPTER, r'if \(!game_vehicle_update_code_matches\(ctx\)\) return "code identity";', ';',
     ('--corrupt', '--expect-stopped')),
    ('trampoline_set', ADAPTER, r'ctx->pc = state\.gpr\[0\]._u32\[0\];',
     r'\g<0> g_spu_trampoline_fn = spu_indirect_branch;', ()),
    ('int_enable_cleared', ADAPTER, r'std::memcpy\(ctx->gpr, state\.gpr, sizeof ctx->gpr\);',
     r'\g<0> ctx->int_enable = 0;', ()),
]


def compile_one(env, source: Path, obj: Path, flags: list, includes: list) -> str | None:
    """Compiles one source. An object is reused when its command and the source did not change."""
    command = [env['MV_CLANG'], *flags, *('/I' + str(p) for p in includes),
               '/TP' if source.suffix == '.cpp' else '/TC',
               '/std:c++17' if source.suffix == '.cpp' else '/std:c17', '/c', str(source), '/Fo' + str(obj)]
    if source.suffix == '.cpp':
        command.append('/EHsc')
    stamp = obj.with_suffix('.cmd')
    text = '\n'.join(command)
    if (obj.exists() and stamp.exists() and stamp.read_text(encoding='utf-8') == text
            and obj.stat().st_mtime >= source.stat().st_mtime):
        return None
    obj.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, env=env, cwd=obj.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (obj.parent / (obj.stem + '.log')).write_bytes(result.stdout)
    if result.returncode:
        return f'{source.name}: see {obj.parent / (obj.stem + ".log")}'
    stamp.write_text(text, encoding='utf-8')
    return None


def compile_all(env, jobs) -> list[Path]:
    with ThreadPoolExecutor(max_workers=4) as pool:
        errors = [error for error in pool.map(lambda job: compile_one(env, *job), jobs) if error]
    if errors:
        raise RuntimeError('compile failed: ' + '; '.join(errors))
    return [job[1] for job in jobs]


def link(env, exe: Path, objects: list[Path]) -> None:
    command = [env['MV_CLANG'], *GLOBAL, '/Fe' + str(exe), *sorted(str(o) for o in objects),
               '/link', 'Synchronization.lib']
    result = subprocess.run(command, env=env, cwd=exe.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (exe.parent / (exe.stem + '_link.log')).write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(f'link failed: see {exe.parent / (exe.stem + "_link.log")}')


def run(exe: Path, mode: str, options: tuple, pairs: Path, expected: int) -> list:
    """Runs one case. Returns the problems: an empty list when the case passes. A run that passes
    the time limit is a problem: a failure of a case, and a rejection of a mutant."""
    try:
        result = subprocess.run([str(exe), '--mode', mode, *options, str(pairs)], cwd=exe.parent,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors='replace',
                                timeout=LIMIT)
    except subprocess.TimeoutExpired:
        print('  %-9s %-28s passed the time limit of %d s' % (mode, ' '.join(options) or '-', LIMIT), flush=True)
        return ['passed the time limit']
    line = next((l for l in result.stdout.splitlines() if l.startswith('BINDING ')), '')
    values = dict(re.findall(r'(\w+)=(\S+)', line))
    if not line:
        return ['no BINDING line', result.stdout[-600:], result.stderr[-600:]]
    problems = [key + '=' + values[key] for key in ZERO if int(values[key]) != 0]
    if int(values['native_runs']) != expected:
        problems.append('native runs %s, expected %d' % (values['native_runs'], expected))
    if result.returncode != 0 and not problems:
        problems.append('exit code %d' % result.returncode)
        problems.append(result.stderr[-400:])
    print('  %-9s %-28s native runs %-4s of %s pairs, %s' % (
        mode, ' '.join(options) or '-', values['native_runs'], values['pairs'],
        ' '.join('%s=%s' % (key, values[key]) for key in ZERO)), flush=True)
    return problems


def changed(file: Path, pattern: str, replacement: str) -> str:
    text, count = re.subn(pattern, replacement, file.read_text(encoding='utf-8'))
    if count != 1:
        raise RuntimeError(f'{file.name}: expected one site of {pattern!r}, found {count}')
    return text


def main() -> int:
    config_path = ROOT / 'config/local.json'
    if os.name != 'nt' or not config_path.exists():
        print('SKIP native vehicle update binding: needs Windows and config/local.json')
        return 0
    config = json.loads(config_path.read_text(encoding='utf-8'))
    unit_dir = ROOT / config['spu_generated'] / UNIT
    pairs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'temp/vehicleport/run3/p3all/pairs3'
    pairs = sorted(pairs_dir.glob('job_*.bin'))
    elf = Path(config['elf'])
    if not (unit_dir / 'spu_recomp.c').exists() or not elf.exists() or not pairs:
        print('SKIP native vehicle update binding: needs the generated unit, the ELF and the kernel pairs')
        return 0
    if binding.digest(elf) != VEHICLE_UPDATE.elf_sha256:
        print('CHECK FAILED: the ELF is not the production ELF of the contract')
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    common = OUT / 'common'
    common.mkdir(exist_ok=True)
    # The bound unit: the same transform as the build, with the relative includes made absolute.
    bound = binding.transform((unit_dir / 'spu_recomp.c').read_bytes(), VEHICLE_UPDATE,
                              binding.read_windows(elf, VEHICLE_UPDATE))
    text = bound.decode('utf-8')
    for old, new in (('#include "spu_recomp.h"', '#include "%s/spu_recomp.h"' % unit_dir.as_posix()),
                     ('#include "../../runtime/spu/spu_helpers.h"', '#include "%s/runtime/spu/spu_helpers.h"' % SDK.as_posix())):
        if text.count(old) != 1:
            raise RuntimeError('unexpected include in the generated unit: ' + old)
        text = text.replace(old, new)
    (common / 'spu_recomp_bound.c').write_text(text, encoding='utf-8', newline='\n')
    del text
    shared = compile_all(project.build_environment(), [
        (FIXTURES / 'native_vehicle_update_binding.c', common / 'binding_context.obj', RUNTIME, INCLUDES),
        *[(SPU / name, common / (Path(name).stem + '.obj'), RUNTIME, INCLUDES)
          for name in NAMES if name != 'spu_interp.c'],
        *[(SDK / name, common / (Path(name).stem + '.obj'), RUNTIME, INCLUDES) for name in EXTRA],
        (common / 'spu_recomp_bound.c', common / 'spu_recomp_bound.obj', LIFTED, INCLUDES),
        (SPU / 'spu_dispatch_mt.c', common / 'spu_dispatch_mt.obj', LIFTED, INCLUDES),
        (FIXTURES / 'native_vehicle_update_binding.cpp', common / 'binding_main.obj', NATIVE, INCLUDES + [SOURCE]),
    ])
    failed: list[str] = []
    count = len(pairs)

    def build(name: str, adapter: str, kernel: str) -> Path:
        out = OUT / name
        out.mkdir(exist_ok=True)
        (out / 'adapter.cpp').write_text(adapter, encoding='utf-8', newline='\n')
        (out / 'vehicle_update.c').write_text(kernel, encoding='utf-8', newline='\n')
        own = compile_all(project.build_environment(), [
            (out / 'adapter.cpp', out / 'adapter.obj', NATIVE, INCLUDES + [SOURCE]),
            (out / 'vehicle_update.c', out / 'vehicle_update.obj', LIFTED, INCLUDES + [SOURCE])])
        exe = out / 'binding.exe'
        link(project.build_environment(), exe, shared + own)
        return exe

    adapter = ADAPTER.read_text(encoding='utf-8')
    kernel = KERNEL.read_text(encoding='utf-8')
    exe = build('base', adapter, kernel)
    for mode, options, expected in (('native', (), count), ('shadow', (), count), ('reference', (), 0),
                                    ('native', ('--corrupt', '--expect-stopped'), 0)):
        problems = run(exe, mode, options, pairs_dir, expected)
        if problems:
            failed.append('%s %s: %s' % (mode, ' '.join(options), '; '.join(problems)))
    stop = build('stop', adapter, changed(*STOP_KERNEL))
    problems = run(stop, 'native', ('--expect-stopped',), pairs_dir, 0)
    if problems:
        failed.append('stopped kernel: ' + '; '.join(problems))
    rejected = 0
    for name, file, pattern, replacement, options in MUTANTS:
        mutated = changed(file, pattern, replacement)
        exe = build(name, mutated, changed(*STOP_KERNEL) if name == 'no_restore' else kernel)
        problems = run(exe, 'native', options, pairs_dir, 0 if options else count)
        if problems:
            rejected += 1
            print('  mutant %s rejected: %s' % (name, '; '.join(problems)[:300]), flush=True)
        else:
            failed.append('mutant %s is NOT rejected' % name)
    if failed:
        print('CHECK FAILED: native vehicle update binding')
        for line in failed:
            print('  ' + line)
        return 1
    print('PASS native vehicle update binding: %d pairs, %d native runs in mode native and in mode shadow, '
          'the context after the drain equals the lifted context in all bytes outside the step counter, '
          'the state after a native run is the return address with no trampoline; reference mode, a changed '
          'code byte and a stopped kernel: 0 native runs; %d of %d adapter mutants rejected' % (
              count, count, rejected, len(MUTANTS)))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, KeyError, OSError, subprocess.SubprocessError) as error:
        print('CHECK ERROR native vehicle update binding: %s' % error)
        sys.exit(1)
