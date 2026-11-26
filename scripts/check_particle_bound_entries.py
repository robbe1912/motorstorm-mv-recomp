"""Checks the bound particle entries of SPU image 213 against the lifted code of the generated unit.

scripts/native_game_binding.py binds three lifted functions of jobmod_556b30b5e654_e12e20: the
random generator 0x170D0, its init 0x17248 and the particle box collision loop 0xA87C. This
check binds a copy of the generated unit with the real binder, compiles it with the flags of the
game, and links it with the runtime and with the two adapters (the harness is
scripts/fixtures/particle_bind_harness.c).

The generator runs on the call states that the interpreter replay of the dumped jobs recorded.
The collision batch runs on constructed batches over the local stores of the dumped jobs.
Mode 0 must equal mode 1. Each mutant damages the native path of one adapter or kernel; the
check must reject every mutant. `--bench N` measures lifted against native with N passes.

The generated unit, the ELF and the dumps are private. They are not in git.
"""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
OUTPUT = ROOT / 'build/self-tests/particle-bound-entries'
RANDOM = ROOT / 'build/self-tests/native-particle-random'
DUMPS = ROOT / 'temp/jobdump/particles213'
SEEDS = ROOT / 'scripts/fixtures/particle_random_seeds.json'
BENCH_LOG = ROOT / 'temp/particleport/bench3.txt'
UNIT = 'jobmod_556b30b5e654_e12e20'
PREFIX = UNIT + '_spu_func_'
CALLING = (12, 16, 17, 18, 19)            # dumped jobs that call the generator
COMPLETE = (11, 12, 16, 17, 18, 19, 22, 23)
# symbol suffix, lifted body sha256, original name, native name, matcher, windows.
# The ELF holds image 213 at file offset 0xF5C000. A local store address is 0x4000 less.
CONTRACTS = (
    # generator 0x170D0 to 0x1725C
    ('000170D0', '84dc7ff8a5a43c9eafed59de63a9e0a61a96fab485ec6a054b7159d0811e99aa',
     'game_original_particle_random_run', 'motorstorm_particle_random_run',
     'game_particle_random_code_matches', ((0xf6f0d0, 0x170d0, 0x18c),)),
    # init 0x17248 to 0x1725C
    ('00017248', '03e488010c467f00db6fcb7a1915d9fc2ce3c6899a8e70aaed7f41a1e8cd9edf',
     'game_original_particle_random_init', 'motorstorm_particle_random_init',
     'game_particle_random_init_code_matches', ((0xf6f248, 0x17248, 0x14),)),
    # collision loop 0xA87C: the function 0xA700 to 0xABEC and its constant pool 0x17360 to 0x173B0
    ('0000A87C', '43aa4cfcc5b35189c616de02afa7e761cb329e415057b5c156c5fa2a8a4abe7f',
     'game_original_particle_collision_loop', 'motorstorm_particle_collision_batch',
     'game_particle_collision_code_matches', ((0xf62700, 0xa700, 0x4ec), (0xf6f360, 0x17360, 0x50))),
)
# name: (source file, (old text, new text)). A wrong resume address, a dropped store, a second run
# of the batch step, a loop re-entry that runs the batch again, a suppressed contact append.
# A second publication of the same batch is an equivalent mutant: publish() writes the same bytes.
MUTANTS = {
    'random-resume': ('particle_random_adapter.cpp', [
        ('    SPU_RET(ctx);\n', '    ctx->pc = ctx->gpr[0]._u32[0] + 4;\n')]),
    'random-store': ('particle_random.c', [
        ('store_word(ls + 0x174a0 + 4 * lane, call.seed.word[lane]);', '(void)0;')]),
    'collision-twice': ('particle_box_collision_adapter.cpp', [
        ('    publish(ctx->ls, pending);\n',
         '    publish(ctx->ls, pending);\n    ctx->gpr[85] = spu_splat_u32(pending.count);\n'
         '    jobmod_556b30b5e654_e12e20_spu_func_0000ABEC(ctx);\n')]),
    'collision-reentry': ('particle_box_collision_adapter.cpp', [
        ('const char* reason = spu_preferred_u32(&ctx->gpr[85]) ? "loop re-entry" :',
         'const char* reason = 0 ? "loop re-entry" :'),
        ('        spu_preferred_u32(&ctx->gpr[85]) != 0 ||\n', ''),
        ('        spu_preferred_u32(&ctx->gpr[80]) != (count - 1) * 128 ||\n', '')]),
    'collision-resume': ('particle_box_collision_adapter.cpp', [
        ('    jobmod_556b30b5e654_e12e20_spu_func_0000ABEC(ctx);\n', '    ctx->pc = ctx->gpr[0]._u32[0];\n')]),
    'collision-store': ('particle_box_collision_adapter.cpp', [
        ('        if (used < batch.capacity) {\n', '        if (used < batch.capacity && batch.count == 0xffffffffu) {\n')]),
}
# Flags of the game build (build/native/build.ninja) without /Zi and /RTC1.
COMMON = ['/nologo', '/DWIN32', '/D_WINDOWS', '/c', '/MDd', '/clang:-O1', '/Ob1', '/clang:-fno-strict-aliasing',
          '/clang:-ffp-contract=off', '/UNDEBUG', '-DMOTORSTORM_DEFORMATION_DEPTH_OBSERVER=1', '-DPPU_FM3=1',
          '-DPS3_ATOMIC_OBSERVATION=0', '-DPS3_EXECUTION_OBSERVATION=0', '-DPS3_SPURS_SCHEDULER_OBSERVATION=0',
          '-DSPU_FLOAT_FAST=1', '-DSPU_SIMD=1']
C = ['/TC', '/std:c17']
CXX = ['/TP', '-std:c++20', '/EHsc', '/EHs', '/EHc-']
# The harness supplies the channel model of the replay engine to lifted code and interpreter.
MODEL = ['-Dspu_wrch=harness_wrch', '-Dspu_rdch=harness_rdch', '-Dspu_rchcnt=harness_rchcnt', '-Dspu_stop=harness_stop']
REGIONS = '0000 04000 kernel\n04000 17498 module\n17498 40000 data\n'


def dump(job):
    return DUMPS / ('job_%06d.bin' % job)


def inputs():
    from project import config
    config = config()
    unit, elf = Path(config['spu_generated']) / UNIT, Path(config['elf'])
    return (unit if unit.is_absolute() else ROOT / unit), (elf if elf.is_absolute() else ROOT / elf)


def contracts():
    from native_game_binding import Contract, PRODUCTION
    return [Contract(PRODUCTION.elf_sha256, body, PREFIX + symbol, original, native, context='spu_context',
                     directory='spu/' + UNIT, matcher=matcher, windows=windows)
            for symbol, body, original, native, matcher, windows in CONTRACTS]


def bind(source, elf):
    """The real binder on a tree that holds the generated unit. Returns the bound unit."""
    from native_game_binding import prepare
    generated, bound = OUTPUT / 'generated', OUTPUT / 'bound'
    if bound.exists():
        shutil.rmtree(bound)
    (generated / 'spu' / UNIT).mkdir(parents=True, exist_ok=True)
    for name in ('spu_recomp.c', 'spu_recomp.h'):
        shutil.copyfile(source / name, generated / 'spu' / UNIT / name)
    # The binder requires this file of a generated tree. No PPU contract is selected.
    (generated / 'ppu').mkdir(parents=True, exist_ok=True)
    (generated / 'ppu' / 'ppu_recomp.h').write_text('/* placeholder of check_particle_bound_entries.py */\n', encoding='utf-8')
    selected = contracts()
    prepare(generated, bound, elf, OUTPUT / 'binding.json', contracts=selected, known_contracts=selected)
    return bound / 'spu' / UNIT
def build(directory, lifted, replacements=()):
    """Compiles the harness with the given adapter or kernel sources. Returns the executable."""
    from check_spu_pm_services import SDK, SPU, NAMES, EXTRA
    from project import build_environment
    env = build_environment()
    cc = env.get('MV_CLANG') or os.environ.get('CC')
    if not cc:
        raise RuntimeError('Set MV_CLANG or CC')
    if os.name != 'nt':
        raise RuntimeError('This check needs clang-cl, as the game build does')
    directory.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'src/motorstorm'
    unit = directory / 'mutant' / 'src'
    replacements = dict(replacements)
    for name, changes in replacements.items():
        text = (source / name).read_text(encoding='utf-8')
        for old, new in changes:
            if text.count(old) != 1:
                raise RuntimeError('%s: the mutant text occurs %d times' % (name, text.count(old)))
            text = text.replace(old, new)
        unit.mkdir(parents=True, exist_ok=True)
        (unit / name).write_text(text, encoding='utf-8')

    def adapter(name):
        return (unit / name) if name in replacements else source / name
    runtime = [SPU / name for name in NAMES if name != 'spu_interp.c']
    runtime += [SDK / name for name in EXTRA if name != 'runtime/syscalls/spu_ea_alias.c']
    runtime.append(SPU / 'spu_dispatch_mt.c')
    sdk = ROOT / 'vendor/ps3recomp'
    includes = ['/I' + str(p) for p in (sdk / 'include', sdk / 'runtime/spu', sdk / 'runtime/platform', source, ROOT / 'src',
                                        sdk / 'runtime/ppu', sdk / 'runtime/memory', sdk / 'runtime/syscalls')]
    fast = ['/O2', '/clang:-O2']
    strict = fast + ['/fp:strict']
    groups = [
        ('lifted', C + COMMON + ['/clang:-O2', '/clang:-mssse3', '-DSPU_USE_DISPATCH_MT', *MODEL], [lifted / 'spu_recomp.c']),
        ('runtime', C + COMMON, runtime),
        ('random_kernel', C + COMMON + fast, [adapter('particle_random.c')]),
        ('collision_kernel', C + COMMON + strict, [source / 'particle_box_collision.c']),
        ('random_adapter', CXX + COMMON + fast + ['-DMOTORSTORM_PARTICLE_FIXTURE'], [adapter('particle_random_adapter.cpp')]),
        ('collision_adapter', CXX + COMMON + strict + ['-DMOTORSTORM_PARTICLE_FIXTURE'],
         [adapter('particle_box_collision_adapter.cpp')]),
        # The harness supplies the program entry (scripts/fixtures/particle_bind_replay.inc).
        ('harness', C + COMMON + fast + MODEL + ['-DMOTORSTORM_REPLAY_INTERP="particle_bind_replay.inc"'],
         [ROOT / 'scripts/fixtures/particle_bind_harness.c']),
    ]
    objects = []
    for name, flags, files in groups:
        (directory / name).mkdir(exist_ok=True)
        for stale in (directory / name).glob('*.obj'):
            stale.unlink()
        try:
            with (directory / (name + '.log')).open('w', encoding='utf-8') as log:
                subprocess.run([cc, *flags, *includes, *map(str, files), '/Fo' + str(directory / name) + os.sep],
                               stdout=log, stderr=subprocess.STDOUT, env=env, check=True, timeout=1800)
        except subprocess.CalledProcessError:
            raise RuntimeError('%s does not compile:\n%s' % (
                name, (directory / (name + '.log')).read_text(encoding='utf-8')[-2000:]))
        objects += sorted(str(p) for p in (directory / name).glob('*.obj'))
    exe = directory / 'particle_bind.exe'
    with (directory / 'link.log').open('w', encoding='utf-8') as log:
        subprocess.run([cc, '/nologo', '/Fe' + str(exe), *objects, '/link', 'Synchronization.lib'],
                       stdout=log, stderr=subprocess.STDOUT, env=env, check=True, timeout=600)
    return exe


def run(exe, *args, timeout=900):
    done = subprocess.run([str(exe), *map(str, args)], capture_output=True, text=True, timeout=timeout)
    return done.returncode, done.stdout, done.stderr


def report(text, tag):
    lines = [line for line in text.splitlines() if line.startswith(tag + ' ')]
    if not lines:
        raise RuntimeError('no %s line:\n%s' % (tag, text[-1500:]))
    return dict(part.split('=', 1) for part in lines[-1].split()[1:])


def seeds():
    if SEEDS.exists():
        return {int(k): v for k, v in json.loads(SEEDS.read_text(encoding='utf-8')).items()}
    return {}


def recorded_calls(jobs):
    """The call states of the generator that the interpreter replay of the dumped jobs recorded."""
    import check_particle_random as previous
    missing = [job for job in jobs if not (RANDOM / ('pairs_%d.bin' % job)).exists()]
    if not missing:
        return
    exe = previous.build()
    regions = RANDOM / 'regions.txt'
    regions.write_text(REGIONS, encoding='utf-8')
    known = seeds()
    for job in missing:
        text = previous.replay(exe, job, regions, 'lifted',
                               ['--seed', '%08X' % known[job], '--pairs', str(RANDOM / ('pairs_%d.bin' % job))])
        if not previous.passed(text):
            raise RuntimeError('lifted replay of job %d does not pass:\n%s' % (job, text[-2000:]))


def failed(code, out, line):
    return code or 'DIFF' in out or int(line['differences'])

def generator(exe, verbose=True):
    """Every recorded call through the bound symbol, in both call forms and both modes."""
    calls = 0
    for job in CALLING:
        code, out, err = run(exe, 'pairs', dump(job), RANDOM / ('pairs_%d.bin' % job))
        line = report(out, 'RANDOM')
        pairs = int(line['pairs'])
        if failed(code, out, line) or int(line['lifted_equal']) != 2 * pairs or int(line['native_equal']) != 2 * pairs \
                or int(line['native_calls']) != 2 * pairs:
            raise RuntimeError('generator of job %d is not equal to the lifted code:\n%s%s' % (job, out[-1500:], err[-500:]))
        calls += 2 * pairs
        if verbose:
            print('generator job %d: %d recorded calls, lifted and native equal in both call forms' % (job, 2 * pairs))
    return calls


def collision(exe, verbose=True):
    code, out, err = run(exe, 'collision', *[dump(job) for job in COMPLETE])
    line = report(out, 'COLLISION')
    if failed(code, out, line) or int(line['native_calls']) != 6 * int(line['shapes']):
        raise RuntimeError('collision batch is not equal to the lifted code:\n%s%s' % (out[-1500:], err[-500:]))
    if verbose:
        print('collision: %s cases on %s local stores, %s native batches, %s fallbacks to the lifted loop' % (
            line['cases'], line['jobs'], line['native_calls'], line['fallbacks']))
        for text in out.splitlines():
            if text.startswith('shape '):
                print('  ' + text)
    return int(line['cases'])


def jobs(exe):
    """Each dumped job runs as the game runs it, lifted against native."""
    known = seeds()
    for job in COMPLETE:
        final = {}
        for mode in ('lifted', 'native'):
            native = mode == 'native'
            path = OUTPUT / ('final_%s_%d.pjsp' % (mode, job))
            code, out, err = run(exe, 'job', dump(job), '--seed', '%08X' % known[job],
                                 '--random', '1' if native else '0', '--collision', '1' if native else '0', '--final', path)
            line = report(out, 'JOB')
            if code or int(line['failed']) or int(line['put_diff']) or int(line['outside']) or not path.exists():
                raise RuntimeError('%s replay of job %d fails:\n%s%s' % (mode, job, out[-1500:], err[-500:]))
            final[mode] = path.read_bytes()
            if native:
                if job in CALLING and not int(line['random_calls']):
                    raise RuntimeError('native replay of job %d makes no native generator call' % job)
                print('job %d: lifted and native replays pass the dump records; native generator calls %s' % (
                    job, line['random_calls']))
        # The file holds a 2056 byte head, then the local store.
        if final['lifted'][2056:] != final['native'][2056:]:
            differing = sum(a != b for a, b in zip(final['lifted'][2056:], final['native'][2056:]))
            raise RuntimeError('job %d: %d bytes of the final local store differ between lifted and native' % (job, differing))


def mutants(lifted):
    for name, (source, replacements) in MUTANTS.items():
        exe = build(OUTPUT / ('mutant-' + name), lifted, {source: replacements})
        if name.startswith('random'):
            code, out, err = run(exe, 'pairs', dump(CALLING[0]), RANDOM / ('pairs_%d.bin' % CALLING[0]))
        else:
            code, out, err = run(exe, 'collision', *[dump(job) for job in COMPLETE])
        # Exit 1: a difference. Exit 3: the harness stopped on an inconsistent state. A mutant that
        # runs the batch where the lifted code does not run it changes the count of native executions.
        proof = [line for line in (out + err).splitlines() if 'DIFF' in line or line.startswith('REPLAY FAIL')]
        if not proof:
            line = report(out, 'RANDOM' if name.startswith('random') else 'COLLISION')
            expected = 2 * int(line['pairs']) if name.startswith('random') else 6 * int(line['shapes'])
            if int(line['native_calls']) != expected:
                proof = ['native executions %s, expected %d' % (line['native_calls'], expected)]
        if code not in (0, 1, 3) or not proof:
            raise RuntimeError('mutant %s is not rejected (exit %d):\n%s' % (name, code, out[-1500:]))
        print('mutant %s: %s' % (name, proof[0]))


def bench(exe, passes):
    args = ['bench', *[dump(job) for job in COMPLETE], '--passes', str(passes)]
    for job in CALLING:
        args.append('--pairs=%d:%s' % (job, RANDOM / ('pairs_%d.bin' % job)))
    code, out, err = run(exe, *args, timeout=3600)
    if code:
        raise RuntimeError('bench fails:\n%s%s' % (out[-1500:], err[-1500:]))
    random, collision_cases, orders = {}, {}, {}
    for line in out.splitlines():
        if not line.startswith('BENCH '):
            continue
        parts = line.split()
        row = dict(part.split('=', 1) for part in parts[2:])
        if parts[1] == 'RANDOM':
            key, unit, work = 'generator job %s' % row['job'], 'call', int(row['calls'])
            table = random
        else:
            key = 'collision case %s, %s particles' % (row['case'], row['count'])
            unit, work = 'batch', int(row['iterations'])
            table = collision_cases
        table.setdefault(key, {'lifted': [], 'native': []})[row['side']].append(int(row['ns']) / work)
        orders.setdefault(key, []).append(row['side'])
    text = []
    for key, row in list(random.items()) + list(collision_cases.items()):
        lifted, native = row['lifted'], row['native']
        if len(lifted) != passes or len(native) != passes:
            raise RuntimeError('bench has %d lifted and %d native passes for %s' % (len(lifted), len(native), key))
        text.append('%-40s passes %d: lifted median %9.1f ns/%s (range %9.1f to %9.1f), '
                    'native median %9.1f ns/%s (range %9.1f to %9.1f), lifted/native %5.2f' % (
                        key, passes, statistics.median(lifted), unit, min(lifted), max(lifted),
                        statistics.median(native), unit, min(native), max(native), statistics.median(lifted) / statistics.median(native)))
        orders[key] = ' '.join('L' if side == 'lifted' else 'N' for side in orders[key])
    text += ['', 'side order of the passes: ' + '; '.join('%s: %s' % item for item in sorted(orders.items())), '', out]
    BENCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    BENCH_LOG.write_text('\n'.join(text) + '\n', encoding='utf-8')
    print('\n'.join(text[:len(random) + len(collision_cases)]))
    print('bench log: %s' % BENCH_LOG)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bench', type=int, default=0, help='measure lifted against native with this many passes')
    args = parser.parse_args()
    if not DUMPS.is_dir():
        raise RuntimeError('Dump directory missing: %s' % DUMPS)
    source, elf = inputs()
    lifted = bind(source, elf)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    exe = build(OUTPUT, lifted)
    recorded_calls(CALLING)
    if args.bench:
        bench(exe, args.bench)
        return
    calls = generator(exe)
    cases = collision(exe)
    jobs(exe)
    mutants(lifted)
    print('PASS: %d generator calls and %d collision cases equal to the lifted code, %d jobs replayed, %d mutants rejected' % (
        calls, cases, len(COMPLETE), len(MUTANTS)))


if __name__ == '__main__':
    main()
