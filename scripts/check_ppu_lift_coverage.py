#!/usr/bin/env python3
"""Lift coverage: a regenerated PPU tree must not drop guest code.

Two lifter defects left no build error and broke the boot of the game:

* a static call or branch to code outside every listed function became a
  comment (``/* bl -> non-code 0x00010200 */;``) and the call was gone;
* without function names, the C++ setjmp/longjmp lowering produced no throw
  line and no resume point.

The check reads the units of a tree and the ELF that the tree was lifted from.

Rule 1: a ``bl``, ``b`` or ``bc -> non-code`` comment whose target lies in an
        executable section of the ELF fails.
Rule 2: a lifted function that the ELF names ``longjmp`` must hold a
        ``throw ppu_nonlocal_jump`` line. Each call to a lifted function that
        the ELF names ``setjmp`` must sit between a ``_nonlocal_sp_`` line and
        its ``loc_nonlocal_`` resume label.

Local gate of ``project.py generate --stage ppu``. Not a CI job: it needs the
private ELF. ``--selftest`` plants the defects on a fixture ELF and checks that
the check finds each one.
"""
import argparse
from pathlib import Path
import re
import sys
import time

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from elftools.elf.elffile import ELFFile                 # noqa: E402

import project                                            # noqa: E402
from fixtures.debug_elf_fixture import Section, Symbol, build_elf   # noqa: E402

SETJMPS = ('setjmp', '_setjmp')
LONGJMPS = ('longjmp', '_longjmp')
DROP = re.compile(rb'/\* (bl|b|bc) -> non-code 0x([0-9A-F]{8}) \*/')
DEFINITION = re.compile(rb'^void func_([0-9A-F]{8})\(ppu_context\* ctx\) \{')
CALL = re.compile(rb'ctx->lr = 0x([0-9A-F]{8}); func_([0-9A-F]{8})\(ctx\);')
THROW = b'throw ppu_nonlocal_jump{'


def read_elf(path):
    """Executable ranges (sorted, merged) and {address: name} of the ELF
    functions that the ELF names setjmp, _setjmp, longjmp or _longjmp. The
    name can have one leading dot."""
    ranges, names = [], {}
    with open(path, 'rb') as stream:
        elf = ELFFile(stream)
        for section in elf.iter_sections():
            if section['sh_flags'] & 0x4 and section['sh_type'] != 'SHT_NOBITS' and section['sh_size']:
                ranges.append((section['sh_addr'], section['sh_addr'] + section['sh_size']))
            if section['sh_type'] != 'SHT_SYMTAB':
                continue
            for symbol in section.iter_symbols():
                name = symbol.name
                if (symbol['st_info']['type'] == 'STT_FUNC' and name
                        and name.lstrip('.') in SETJMPS + LONGJMPS):
                    names.setdefault(symbol['st_value'], name)
    merged = []
    for lo, hi in sorted(ranges):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [tuple(pair) for pair in merged], names


def scan(units, ranges, standard):
    """Problems of the lifted unit files. ``standard`` is {address: name}."""
    setjmp = {a for a, name in standard.items() if name.lstrip('.') in SETJMPS}
    longjmp = {a: name for a, name in standard.items() if name.lstrip('.') in LONGJMPS}
    problems = []
    stats = {'drops': 0, 'setjmp': 0, 'longjmp': 0, 'throws': 0, 'resumes': 0}
    for unit in units:
        current, throws, pending, previous = None, 0, None, b''
        with unit.open('rb') as stream:
            for number, line in enumerate(stream, 1):
                if pending is not None:
                    if line.strip() != b'loc_nonlocal_%08X: ;' % pending:
                        problems.append(f'{unit.name}:{number}: call at 0x{pending:08X} has no '
                                        f'resume label loc_nonlocal_{pending:08X}')
                    pending = None
                drop = DROP.search(line)
                if drop:
                    stats['drops'] += 1
                    target = int(drop[2], 16)
                    if any(lo <= target < hi for lo, hi in ranges):
                        problems.append(f'{unit.name}:{number}: {drop[1].decode()} to code that '
                                        f'is not lifted: 0x{target:08X} (non-code comment)')
                definition = DEFINITION.match(line)
                if definition:
                    address = int(definition[1], 16)
                    current = address if address in longjmp else None
                    throws = 0
                    stats['longjmp'] += address in longjmp
                    stats['setjmp'] += address in setjmp
                elif current is not None:
                    if THROW in line:
                        throws += 1
                        stats['throws'] += 1
                    elif line.rstrip() == b'}':
                        if not throws:
                            problems.append(f'{unit.name}:{number}: lifted longjmp '
                                            f'{longjmp[current]} func_{current:08X} has no '
                                            'throw ppu_nonlocal_jump line')
                        current = None
                call = CALL.search(line)
                if call and int(call[2], 16) in setjmp:
                    point = int(call[1], 16)
                    saved = b'_nonlocal_sp_%08X = ctx->gpr[1];' % point in previous
                    stats['resumes'] += saved
                    if not saved:
                        problems.append(f'{unit.name}:{number}: call to setjmp '
                                        f'func_{int(call[2], 16):08X} at 0x{point:08X} has no '
                                        'resume point (_nonlocal_sp_ line)')
                    pending = point
                previous = line
    return problems, stats


def check(tree, elf_path):
    units = sorted(Path(tree).glob('ppu_recomp.cpp_*.cpp'))
    if not units:
        raise SystemExit(f'{tree}: no ppu_recomp.cpp_*.cpp unit')
    ranges, standard = read_elf(elf_path)
    problems, stats = scan(units, ranges, standard)
    print(f'tree {tree}, {len(units)} units; ELF {elf_path}: {len(ranges)} executable range(s), '
          f'{len(standard)} setjmp/longjmp function symbol(s)')
    print(f'non-code comments {stats["drops"]}, lifted setjmp {stats["setjmp"]}, lifted longjmp '
          f'{stats["longjmp"]}, throw lines {stats["throws"]}, resume points {stats["resumes"]}')
    return problems


def function(label, name, body):
    return (f'/* {label} */\nvoid func_{name:08X}(ppu_context* ctx) {{\n'
            + ''.join(f'    {line}\n' for line in body) + '}\n')


SETJMP_CALL = ['_nonlocal_sp_00002048 = ctx->gpr[1];',
               'ctx->lr = 0x00002048; func_00002000(ctx); DRAIN_TRAMPOLINE(ctx);',
               'loc_nonlocal_00002048: ;',
               'ctx->lr = 0x0000204C; func_00002020(ctx); DRAIN_TRAMPOLINE(ctx);',
               'return;']
THROW_LINE = ['throw ppu_nonlocal_jump{ctx, (uint32_t)ctx->lr, ctx->gpr[1]};']
QUIET = ['return;']
FIXTURE_ELF = ([Section('.init', 0x1000, 0x10), Section('.text', 0x2000, 0x100),
                Section('.rodata', 0x3000, 0x40, flags=2)],
               [Symbol('.setjmp', '.text', 0x2000, 0x10), Symbol('.longjmp', '.text', 0x2020, 0x10),
                Symbol('.main', '.text', 0x2040, 0x40)])
FIXTURE_RANGES = [(0x1000, 0x1010), (0x2000, 0x2100)]


def selftest():
    root = SCRIPTS.parent / 'temp/self-tests/ppu-lift-coverage'
    root.mkdir(parents=True, exist_ok=True)
    elf = root / 'fixture.elf'
    elf.write_bytes(build_elf(*FIXTURE_ELF).data)
    ranges, standard = read_elf(elf)
    setjmp = function('.setjmp', 0x2000, QUIET)

    def tree(name, main=SETJMP_CALL, longjmp_body=THROW_LINE, extra=()):
        folder = root / name
        folder.mkdir(exist_ok=True)
        unit = function('.main', 0x2040, main) + setjmp
        if longjmp_body is not None:
            unit += function('.longjmp', 0x2020, longjmp_body)
        (folder / 'ppu_recomp.cpp_000.cpp').write_text(unit, encoding='utf-8')
        for index, text in enumerate(extra, 1):
            (folder / f'ppu_recomp.cpp_{index:03d}.cpp').write_text(text, encoding='utf-8')
        return sorted(folder.glob('ppu_recomp.cpp_*.cpp'))

    second_unit = ['/* .other */\nvoid func_00002080(ppu_context* ctx) {\n'
                   '    /* bl -> non-code 0x00001000 */;\n}\n']
    cases = [
        ('clean tree', tree('clean'), 0),
        ('bl drop into .text', tree('m1', SETJMP_CALL + ['/* bl -> non-code 0x00002000 */;']), 1),
        ('b drop into .init', tree('m2', ['return; /* b -> non-code 0x00001004 */']), 1),
        ('bc drop to the last word of .text',
         tree('m3', ['if (ctx->cr) return; /* bc -> non-code 0x000020FC */']), 1),
        ('drop in the second unit', tree('m4', extra=second_unit), 1),
        ('longjmp without throw line', tree('m5', longjmp_body=QUIET), 1),
        ('setjmp call without resume point', tree('m6', SETJMP_CALL[1:]), 1),
        ('no throw line and no resume point', tree('m7', SETJMP_CALL[1:], QUIET), 2),
        ('resume label after the call missing', tree('m8', SETJMP_CALL[:2] + SETJMP_CALL[3:]), 1),
        ('control: target in .rodata',
         tree('c1', SETJMP_CALL + ['/* bl -> non-code 0x00003000 */;']), 0),
        ('control: target one past .text',
         tree('c2', SETJMP_CALL + ['/* bl -> non-code 0x00002100 */;']), 0),
        ('control: target before .init',
         tree('c3', SETJMP_CALL + ['/* bl -> non-code 0x00000FFC */;']), 0),
        ('control: setjmp and longjmp not lifted or called',
         tree('c4', ['ctx->gpr[3] = 1;', 'return;'], None), 0),
    ]
    failed = 0
    if ranges != FIXTURE_RANGES or standard != {0x2000: '.setjmp', 0x2020: '.longjmp'}:
        print(f'FAIL fixture ELF: ranges {ranges}, symbols {standard}')
        failed += 1
    for name, units, expected in cases:
        problems, _ = scan(units, ranges, standard)
        ok = len(problems) == expected
        failed += not ok
        print(('PASS' if ok else 'FAIL') + f' {name}: {len(problems)} problem(s), expected {expected}')
        for problem in problems:
            print('     ' + problem)
    print(f'{"FAIL" if failed else "PASS"}: lift coverage, {len(cases)} trees, '
          f'{failed} unexpected result(s)')
    return int(failed != 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--tree', type=Path,
                        help='directory of the lifted PPU units (default: <generated>/ppu)')
    parser.add_argument('--elf', type=Path, help='debug ELF (default: key "elf" of config/local.json)')
    parser.add_argument('--selftest', action='store_true',
                        help='plant the defects on a fixture ELF and check that the check finds them')
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    config = project.config()
    tree, elf_path = args.tree or config['generated'] / 'ppu', args.elf or config['elf']
    began = time.time()
    problems = check(tree, elf_path)
    for problem in problems:
        print('FAIL ' + problem)
    if problems:
        print(f'FAIL {len(problems)} problem(s), elapsed {time.time() - began:.1f} s')
        return 1
    print(f'PASS, elapsed {time.time() - began:.1f} s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
