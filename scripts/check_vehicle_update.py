"""Checks the native vehicle update kernel against the kernel pairs of the lifted code and
rejects behavior mutants.

Usage: python scripts/check_vehicle_update.py [--no-mutants] [<pairs directory>]

A kernel pair file holds the SPU registers and the local store at the entry of 0x11FE0 and at its
return address 0x20CE0. The private replay of the lifted code writes the files (format: see
scripts/fixtures/native_vehicle_update.c). The kernel result must equal the return state of each
pair in all 128 registers and in the whole local store (262144 bytes: the 7712-byte Vehicle object
at 0x21400 and the other ranges that the extent writes).

Each mutant changes one statement at one site. The check tries the sites of the function in order
until a site rejects the mutant. Default pairs directory: temp/vehicleport/run3/p3all/pairs3.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/motorstorm'
SPU = ROOT / 'vendor/ps3recomp/runtime/spu'
SDK = ROOT / 'vendor/ps3recomp/include'
KERNEL = SOURCE / 'vehicle_update.c'
FIXTURE = ROOT / 'scripts/fixtures/native_vehicle_update.c'
# Functions with the most executed instructions inside the extent (profile of the replay).
HOT = ['144B4', '1CA30', '0F8A0', '05438', '1F310', '1CFC8', '0BD88', '1FE98', '14900', '1F4A8', '05900', '129E0', '13C90']
# (name, functions or None for HOT or 'file', pattern, replacement, description)
# 0x11FE0 is the entry function of the extent: its statement saves the return address at
# 0x10($r1), and its loop is the wheel loop.
MUTANTS = [
    ('constant_plus_four', ['011FE0'], r'spu_csflt\((s->gpr\[\d+\]), (\d+)\)', r'spu_csflt(\1, (\2 + 4))',
     'changed constant'),
    ('store_address_plus_16', ['011FE0'], r'vu_write\(s, (s->gpr\[1\]\._u32\[0\] \+ )0x10(, s->gpr\[0\])\);',
     r'vu_write(s, \1 0x20\2);', 'changed store address'),
    ('return_address_store_dropped', ['011FE0'], r'vu_write\(s, s->gpr\[1\]\._u32\[0\] \+ 0x10, s->gpr\[0\]\);', ';',
     'dropped store'),
    ('loop_bound_plus_one', ['011FE0'], r'spu_cgti\((s->gpr\[\d+\]), 0\)', r'spu_cgti(\1, 1)', 'changed loop bound'),
    ('load_byte_order_swapped', 'file', r'\(\(uint32_t\)p\[4 \* i\] << 24\)', r'((uint32_t)p[4 * i + 3] << 24)',
     'changed byte order of a load'),
    ('branch_flipped', ['011FE0'], r'(if \(s->gpr\[\d+\]\._u32\[0\]) == 0\)', r'\1 != 0)', 'changed branch'),
    ('fma_to_fm', ['01CA30'], r'spu_fma\((s->gpr\[\d+\]), (s->gpr\[\d+\]), s->gpr\[\d+\]\)', r'spu_fm(\1, \2)',
     'changed float operation'),
    ('fm_to_fa', ['01CA30'], r'spu_fm\(', r'spu_fa(', 'changed float operation'),
]
SEGMENT = r'static vu_block (?:vu_b_%s|vu_c_%s_[0-9A-F]+)\(MotorstormVehicleState\* s\) \{\n(.*?)\n\}\n'


def build(output: Path, name: str, kernel: Path):
    """Compiles the kernel with clang-cl or cc and links the fixture. Returns the executable path."""
    windows = os.name == 'nt'
    cc = os.environ.get('MV_CLANG') or os.environ.get('CC') or shutil.which('clang-cl' if windows else 'cc')
    if not cc:
        raise RuntimeError('Set a C compiler (MV_CLANG or CC)')
    includes = [('/I' if windows else '-I') + str(p) for p in (SOURCE, SPU, SDK)]
    common = ['/nologo', '/TC', '/std:c17', '/O2', '/UNDEBUG', '/fp:strict'] if windows else \
             ['-std=gnu17', '-O2', '-UNDEBUG', '-ffp-contract=off', '-frounding-math']
    objects = []
    for file in (SPU / 'spu_float_simd.c', kernel):
        obj = output / (file.stem + ('.obj' if windows else '.o'))
        if file == SPU / 'spu_float_simd.c' and obj.exists():
            objects.append(str(obj))
            continue
        with (output / (file.stem + '.log')).open('w', encoding='utf-8') as log:
            subprocess.run([cc, *common, *includes, '/c' if windows else '-c', file, '/Fo' + str(obj)] if windows else
                           [cc, *common, *includes, '-c', str(file), '-o', str(obj)], cwd=output, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
        objects.append(str(obj))
    exe = output / (name + ('.exe' if windows else ''))
    if windows:
        command = [cc, '/nologo', '/TC', '/std:c17', '/O2', '/UNDEBUG', '/Fe' + str(exe), *includes, str(FIXTURE), *objects]
    else:
        command = [cc, '-std=gnu17', '-O2', '-UNDEBUG', '-o', str(exe), *includes, str(FIXTURE), *objects, '-lm']
    with (output / (name + '.log')).open('w', encoding='utf-8') as log:
        subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True)
    return exe


def run(exe: Path, pairs, output: Path, name: str):
    """Runs the executable on the pairs. The reference needs under 5 seconds. A run past the time
    limit (a mutant that sends the kernel into a loop) counts as a rejection."""
    lines = []
    try:
        with (output / (name + '_run.log')).open('w', encoding='utf-8') as log:
            rc = subprocess.run([str(exe), *map(str, pairs)], cwd=output, stdout=log, stderr=subprocess.STDOUT,
                                timeout=120).returncode
    except subprocess.TimeoutExpired:
        rc = -1
    if (output / (name + '_run.log')).exists():
        lines = (output / (name + '_run.log')).read_text(encoding='utf-8', errors='replace').splitlines()
    return rc, lines


def sites(text: str, functions, pattern: str, repl: str):
    """Changed copies of the kernel, one per site of the pattern, in the order of the functions."""
    if functions == 'file':
        for m in re.finditer(pattern, text):
            yield text[:m.start()] + re.sub(pattern, repl, m.group(0)) + text[m.end():], 'file'
        return
    for function in functions or HOT:
        for segment in re.finditer(SEGMENT % (function, function), text, re.S):
            for m in re.finditer(pattern, segment.group(1)):
                new = segment.group(1)[:m.start()] + re.sub(pattern, repl, m.group(0)) + segment.group(1)[m.end():]
                yield text[:segment.start(1)] + new + text[segment.end(1):], function


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    mutants_on = '--no-mutants' not in sys.argv
    pairs_dir = Path(args[0]) if args else ROOT / 'temp/vehicleport/run3/p3all/pairs3'
    pairs = sorted(pairs_dir.glob('job_*.bin'))
    if not pairs:
        raise SystemExit('CHECK_ERROR no kernel pair files in ' + str(pairs_dir))
    output = ROOT / 'build/self-tests/native-vehicle-update'
    output.mkdir(parents=True, exist_ok=True)
    exe = build(output, 'native_vehicle_update', KERNEL)
    rc, lines = run(exe, pairs, output, 'reference')
    ok = sum(l.startswith('OK ') for l in lines)
    bails = sum(l.startswith('BAIL ') for l in lines)
    diffs = sum(l.startswith('DIFF ') for l in lines)
    print('reference: pairs %d ok %d bail %d diff %d' % (len(pairs), ok, bails, diffs), flush=True)
    for l in lines:
        if l.startswith(('EXTENT', '   0x')):
            print(l, flush=True)
    if rc or ok != len(pairs):
        for l in lines:
            if not l.startswith('OK '):
                print(l)
        print('CHECK FAILED: the kernel is not bit-exact')
        return 1
    if not mutants_on:
        print('CHECK PASSED (reference only)')
        return 0
    text = KERNEL.read_text(encoding='utf-8')
    rejected = 0
    for name, functions, pattern, repl, description in MUTANTS:
        verdict = 'CHECK_ERROR the mutant has no site'
        for number, (changed, block) in enumerate(sites(text, functions, pattern, repl)):
            if number == 6:
                break
            source = output / ('vehicle_update_%s.c' % name)
            source.write_text(changed, encoding='utf-8', newline='\n')
            exe = build(output, 'mutant_' + name, source)
            rc, lines = run(exe, pairs, output, 'mutant_' + name)
            if rc == -1:
                rejected += 1
                print('mutant %-30s %-32s function 0x%s site %d: rejected, the run passed the time limit'
                      % (name, '(' + description + ')', block, number + 1), flush=True)
                verdict = ''
                break
            bad = sum(not l.startswith('OK ') for l in lines if l[:3] in ('OK ', 'DIF', 'BAI'))
            if rc == 0 or not bad:
                continue
            rejected += 1
            print('mutant %-30s %-32s function 0x%s site %d: rejected, %d of %d pairs differ'
                  % (name, '(' + description + ')', block, number + 1, bad, len(pairs)), flush=True)
            verdict = ''
            break
        if verdict:
            print('CHECK FAILED: mutant %s is NOT rejected' % name, flush=True)
            return 1
    print('CHECK PASSED: %d pairs bit-exact, %d of %d mutants rejected' % (ok, rejected, len(MUTANTS)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
