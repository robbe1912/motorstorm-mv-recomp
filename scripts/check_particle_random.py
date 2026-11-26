"""Check the native random generator of job image 213 (0x170D0 to 0x17258) on dumped jobs.

The replay program (scripts/fixtures/particle_random_replay.c) runs a dumped SPU job with
the lifted code. DMA and channel access come from the dump records. The lifted replay must
pass the dump: equal exit points, equal DMA records, byte-equal PUT data, and an equal
final local store outside the addresses that the dump does not record.

The native replay replaces each call of the generator with the kernel
(src/motorstorm/particle_random.c). Each call must leave the same registers and the same
bytes as the lifted code. Each mutant damages one result of the kernel. The check must
reject every mutant.

The dumps are in temp/jobdump/particles213 (job_0000NN.bin). They are not in git.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
DUMPS = ROOT / 'temp/jobdump/particles213'
OUTPUT = ROOT / 'build/self-tests/native-particle-random'
SEEDS = ROOT / 'scripts/fixtures/particle_random_seeds.json'
JOBS = (11, 12, 16, 17, 18, 19, 22, 23)  # complete jobs that pass the lifted replay
CALLING = (12, 16, 17, 18, 19)           # jobs that call the generator
MUTANTS = 7
MASK = (1 << 32) - 1
INVERSE = pow(1664525, -1, 1 << 32)


def previous(seed):
    return (seed - 1013904223) * INVERSE & MASK


def back(seed, count):
    for _ in range(count):
        seed = previous(seed)
    return seed


def build():
    from check_spu_pm_services import SDK, SPU, NAMES, EXTRA
    from project import build_environment
    windows = os.name == 'nt'
    env = build_environment()
    cc = env.get('MV_CLANG') or os.environ.get('CC')
    if not cc:
        raise RuntimeError('Set MV_CLANG or CC')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    exe = OUTPUT / ('replay.exe' if windows else 'replay')
    source = ROOT / 'src/motorstorm'
    engine = ROOT / 'scripts/fixtures/particle_random_replay.c'
    sources = [engine, source / 'particle_random.c', source / 'particle_random_adapter.cpp']
    sources += [SPU / name for name in NAMES if name != 'spu_interp.c']
    sources += [SDK / name for name in EXTRA if name != 'runtime/syscalls/spu_ea_alias.c']
    sources.append(SPU / 'spu_dispatch_mt.c')
    if exe.exists() and all(exe.stat().st_mtime >= p.stat().st_mtime for p in sources):
        return exe
    includes = [('/I' if windows else '-I') + str(p) for p in (SDK / 'include', SPU, SDK / 'runtime/platform', source)]
    objects = []
    groups = [
        ('engine', '/TC' if windows else '-x', 'c', ['/O1'], [engine] + sources[3:], '/std:c17' if windows else '-std=gnu17'),
        ('kernel', '/TC' if windows else '-x', 'c', ['/O2', '/fp:strict'], [sources[1]], '/std:c17' if windows else '-std=gnu17'),
        ('adapter', '/TP' if windows else '-x', 'c++', ['/O2'], [sources[2]], '/std:c++17' if windows else '-std=c++17'),
    ]
    for name, flag, language, optimize, files, std in groups:
        if windows:
            options = ['/nologo', flag, std, *optimize, '/UNDEBUG', '/MDd', '/D_CRT_SECURE_NO_WARNINGS', '/c']
        else:
            options = [flag, language, std, *[o.replace('/O', '-O') for o in optimize], '-UNDEBUG', '-ffp-contract=off', '-c']
        single = len(files) == 1
        if windows:
            output_option = ['/Fo' + str(OUTPUT / (name + '.obj'))] if single else ['/Fo' + str(OUTPUT) + os.sep]
        else:
            output_option = ['-o', str(OUTPUT / (name + '.o'))] if single else []
        with (OUTPUT / (name + '.log')).open('w', encoding='utf-8') as log:
            subprocess.run([cc, *options, *includes, *map(str, files), *output_option], stdout=log,
                           stderr=subprocess.STDOUT, env=env, cwd=None if single else OUTPUT, check=True, timeout=180)
        suffix = '.obj' if windows else '.o'
        objects += ([str(OUTPUT / (name + suffix))] if single else
                    [str(OUTPUT / (path.stem + suffix)) for path in files])
    command = ([cc, '/nologo', '/Fe' + str(exe), *objects, '/link', 'Synchronization.lib'] if windows
               else [cc, *objects, '-o', str(exe), '-lpthread'])
    with (OUTPUT / 'link.log').open('w', encoding='utf-8') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env, check=True, timeout=120)
    return exe


def replay(exe, job, regions, output, extra=()):
    cmd = [sys.executable, str(ROOT / 'scripts/quiet_run.py'), '--timeout', '300', '--', str(exe),
           str(DUMPS / ('job_%06d.bin' % job)), str(regions), str(OUTPUT / ('profile_%s_%d.bin' % (output, job))),
           '--r0', '16ECC', '--stop', '3098', '--final', str(OUTPUT / ('final_%s_%d.pjsp' % (output, job))), *extra]
    for suffix in ('final_%s_%d.pjsp', 'profile_%s_%d.bin'):
        path = OUTPUT / (suffix % (output, job))
        if path.exists():
            path.unlink()
    text = subprocess.run(cmd, capture_output=True, text=True).stdout
    (OUTPUT / ('run_%s_%d.txt' % (output, job))).write_text(text, encoding='utf-8')
    return text


def passed(text):
    report = [line for line in text.splitlines() if line.startswith('job ')]
    if not report or 'REPLAY FAIL' in text or 'PAIR DIFFERS' in text:
        return False
    report = report[0]
    checked, total = report.split('exits checked ')[1].split(' of ')[:2]
    if checked != total.split()[0] or 'differing bytes 0 (' not in report:
        return False
    outside = [line for line in text.splitlines() if 'final LS outside the allowed set' in line]
    pairs = [line for line in text.splitlines() if line.startswith('native kernel:')]
    return bool(outside) and outside[0].split('set: ')[1].startswith('0 ') and bool(pairs) and pairs[0].endswith('pair differences 0')


def calls(text):
    return int([line for line in text.splitlines() if line.startswith('native kernel:')][0].split('calls ')[1].split(',')[0])


def exit_seed(job):
    import spu_job_dump
    raw = bytes(spu_job_dump.Job(str(DUMPS / ('job_%06d.bin' % job))).exit_ls or b'')
    return int.from_bytes(raw[0x174a0:0x174a4], 'big')


def final_seed(job, output):
    path = OUTPUT / ('final_%s_%d.pjsp' % (output, job))
    if not path.exists():
        return None
    raw = path.read_bytes()
    assert raw[:4] == b'PJSP'
    return int.from_bytes(raw[8 + 2048 + 0x174a0:8 + 2048 + 0x174a4], 'big')


def recover_seed(exe, job, regions):
    """The dump does not record the decrementer read at 0x1695C that seeds the generator.
    The exit seed and the round count give the value: seed0 = generator^-rounds(exit seed)."""
    text = replay(exe, job, regions, 'model')
    seed_d = exit_seed(job)
    seed_r = final_seed(job, 'model')
    model = [line for line in text.splitlines() if ' at 1695C ' in line and '(model)' in line]
    if seed_r is not None and model:
        seed, count = seed_r, 0
        while seed != int(model[0].split(': ')[1].split(' ')[0], 16) and count < 65536:
            seed, count = previous(seed), count + 1
        if count < 65536 and verify(exe, job, regions, back(seed_d, count)):
            return back(seed_d, count)
    for count in range(0, 512):
        seed = back(seed_d, count)
        if verify(exe, job, regions, seed):
            return seed
    raise RuntimeError('job %d: no seed found' % job)


def verify(exe, job, regions, seed):
    final = OUTPUT / ('final_seed_%d.pjsp' % job)
    final.unlink(missing_ok=True)
    text = subprocess.run([sys.executable, str(ROOT / 'scripts/quiet_run.py'), '--timeout', '300', '--', str(exe),
                           str(DUMPS / ('job_%06d.bin' % job)), str(regions), str(OUTPUT / 'profile_seed.bin'),
                           '--r0', '16ECC', '--stop', '3098', '--final', str(final), '--seed', '%08X' % seed],
                          capture_output=True, text=True).stdout
    ok = 'REPLAY FAIL' not in text and 'differing bytes 0 (' in text and final.exists()
    if ok:
        raw = final.read_bytes()
        ok = int.from_bytes(raw[8 + 2048 + 0x174a0:8 + 2048 + 0x174a4], 'big') == exit_seed(job)
    final.unlink(missing_ok=True)
    return ok


def local_store_difference(job):
    """Bytes of the final local store in which the native replay and the lifted replay differ.
    The registers at the final PC are not compared: they hold decrementer values, and the
    replay model derives the decrementer from the instruction count."""
    raw = []
    for output in ('lifted', 'native'):
        data = (OUTPUT / ('final_%s_%d.pjsp' % (output, job))).read_bytes()
        assert data[:4] == b'PJSP'
        raw.append(data[8 + 2048:8 + 2048 + 0x40000])
    return sum(a != b for a, b in zip(*raw))


def main():
    if not DUMPS.is_dir():
        raise RuntimeError('Dump directory missing: %s' % DUMPS)
    exe = build()
    regions = OUTPUT / 'regions.txt'
    regions.write_text('0000 04000 kernel\n04000 17498 module\n17498 40000 data\n', encoding='utf-8')
    seeds = {int(k): v for k, v in json.loads(SEEDS.read_text(encoding='utf-8')).items()} if SEEDS.exists() else {}
    for job in JOBS:
        if job not in seeds:
            seeds[job] = recover_seed(exe, job, regions)
            SEEDS.write_text(json.dumps(seeds, sort_keys=True) + '\n', encoding='utf-8')
            print('seed job %d: %08X' % (job, seeds[job]))
    total_calls = 0
    for job in JOBS:
        extra = ['--pairs', str(OUTPUT / ('pairs_%d.bin' % job))] if job in CALLING else []
        text = replay(exe, job, regions, 'lifted', ['--seed', '%08X' % seeds[job], *extra])
        if not passed(text):
            raise RuntimeError('lifted replay of job %d does not pass:\n%s' % (job, text[-2000:]))
        native = replay(exe, job, regions, 'native', ['--seed', '%08X' % seeds[job], '--native', *extra])
        if not passed(native) or (job in CALLING and not calls(native)):
            raise RuntimeError('native replay of job %d does not pass:\n%s' % (job, native[-2000:]))
        total_calls += calls(native)
        differing = local_store_difference(job)
        if differing:
            raise RuntimeError('native replay of job %d: %d bytes of the final local store differ from the lifted replay' % (
                job, differing))
        lifted_pairs = [line for line in text.splitlines() if line.startswith('job ')][0].split('steps ')[1].split()[0]
        print('job %d: lifted PASS, native PASS, %d calls, lifted %s instructions' % (job, calls(native), lifted_pairs))
    for mutant in range(1, MUTANTS + 1):
        rejected = 0
        for job in CALLING:
            text = replay(exe, job, regions, 'mutant%d' % mutant,
                          ['--seed', '%08X' % seeds[job], '--native', '--pairs', str(OUTPUT / ('pairs_%d.bin' % job)),
                           '--mutant', str(mutant)])
            rejected += not passed(text)
        if rejected != len(CALLING):
            raise RuntimeError('mutant %d is not rejected: %d of %d jobs' % (mutant, rejected, len(CALLING)))
        print('mutant %d: rejected in %d of %d jobs' % (mutant, rejected, len(CALLING)))
    print('PASS: %d jobs, %d native calls equal to the lifted code, %d mutants rejected' % (
        len(JOBS), total_calls, MUTANTS))


if __name__ == '__main__':
    main()
