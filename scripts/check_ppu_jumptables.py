#!/usr/bin/env python3
"""Lifted jump tables of a PPU tree against the tables the lifter discovers.

ppu_lifter.py emits ``switch ((uint32_t)ctx->ctr)`` with one ``case`` per
table target for each computed jump whose table ``discover_jump_tables``
resolves. This check runs that discovery on the ELF again and requires:

* each dispatcher inside a lifted function: one lifted switch with the same
  case targets in the function that holds the dispatcher;
* each lifted switch: a ``loc_`` label in the same unit for each ``goto`` arm,
  and a definition in the tree for each trampoline arm;
* no table-less computed jump that still carries its table words;
* the first word of an inline table after a dispatcher: its ``TODO`` word
  line follows the switch (an inline table is data in the text segment);
* a definition in a unit for each function of the header.

The defect this pins is the Havok worker freeze. The units of that tree were
lifted before the lifter resolved spilled table bases, so the first dispatch
of the solver switch in hkExportImpulsesAndRhs returned to processNextJob
without the callee epilogue (issue #155;
scripts/check_ppu_spilled_jumptables.py holds the lifter unit vectors).
This check needs the game ELF and a lifted tree. It is a local gate of
``project.py generate --stage ppu``, not a CI job.

Run: python scripts/check_ppu_jumptables.py [--tree DIR] [--elf FILE]
         [--functions FILE] [--toc HEX ...] [--only FUNC,FUNC]
"""

import argparse
import bisect
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor/ps3recomp/tools'))
sys.path.insert(0, str(ROOT / 'scripts'))

from elf_parser import ELFFile, PT_LOAD                  # noqa: E402
from ppu_disasm import disassemble_bytes                 # noqa: E402
import ppu_disasm                                       # noqa: E402
import ppu_lifter                                       # noqa: E402
import project                                           # noqa: E402

SWITCH = 'switch ((uint32_t)ctx->ctr) {'
UNRESOLVED = 'ps3_indirect_call(ctx); return;'
ARM = re.compile(r'case 0x([0-9A-F]{8})u: (?:goto (loc_[0-9A-F]{8});'
                 r'|\{ g_trampoline_fn = \(void\(\*\)\(void\*\)\)(func_[0-9A-F]{8}); return; \})')
TABLE_WORD = re.compile(r'\s*/\* TODO: \.(?:word|long) 0x[0-9A-F]{8} \*/;$')
LABEL = re.compile(r'\s*(loc_[0-9A-F]{8}):')
DEFINITION = re.compile(r'void (func_[0-9A-F]{8})\(ppu_context\* ctx\) \{$')
DECLARATION = re.compile(r'(?m)^void (func_[0-9A-F]{8})\(ppu_context\* ctx\);(?![ /\w])')
GAP_LOOKBACK = 3          # a lifted switch carries its arms on its own line


def read_text(path):
    return path.read_bytes().decode('utf-8', errors='replace')


def load_elf(path):
    """The ELF path of ppu_lifter.main(): instructions of the executable
    segments, the loaded segments, a word reader, the entry descriptor."""
    elf = ELFFile(str(path))
    elf.load()
    big_endian = elf.elf_header.big_endian
    seg_map, all_insns, code_hi = [], [], 0
    for index, header in enumerate(elf.program_headers):
        if header.p_type != PT_LOAD:
            continue
        data = elf.get_segment_data(index)
        if header.p_filesz > 0:
            seg_map.append((header.p_vaddr, header.p_vaddr + header.p_filesz, data))
        if header.p_flags & 1:
            all_insns.extend(disassemble_bytes(data, header.p_vaddr, big_endian))
            code_hi = max(code_hi, header.p_vaddr + header.p_filesz)

    def read_u32(address):
        for lo, hi, data in seg_map:
            if lo <= address and address + 4 <= hi:
                return int.from_bytes(data[address - lo:address - lo + 4],
                                      'big' if big_endian else 'little')
        return None

    toc = read_u32((elf.elf_header.e_entry + 4) & 0xFFFFFFFF) or 0
    code = read_u32(elf.elf_header.e_entry & 0xFFFFFFFF) or 0
    if toc in (0, code):
        # The entry descriptor does not hold a TOC: use the ELFv1 bias of .got.
        for section in getattr(elf, 'section_headers', []) or []:
            if getattr(section, 'name_str', '') == '.got':
                toc = (section.sh_addr + 0x8000) & 0xFFFFFFFF
    return all_insns, seg_map, read_u32, toc, code_hi


def discover(all_insns, seg_map, read_u32, toc, starts, text_hi, tocs):
    """{dispatcher: case targets} for the inputs the lifter passes."""
    text_lo = starts[0]
    candidates = list(tocs) if tocs else ppu_lifter.collect_toc_candidates(
        seg_map, text_lo, text_hi, toc)
    tables = ppu_lifter.discover_jump_tables(
        all_insns, read_u32, candidates, text_lo, text_hi, func_starts=starts)
    return tables, candidates


class Switch:
    def __init__(self, unit, line, function, line_text, after):
        arms = ARM.findall(line_text)
        self.unit, self.line, self.function = unit, line, function
        self.cases = frozenset(int(target, 16) for target, _, _ in arms)
        self.labels = [label for _, label, _ in arms if label]
        self.callees = [name for _, _, name in arms if name]
        self.complete = (line_text.count('case 0x') == len(arms)
                         and ' default: ' + UNRESOLVED in line_text)
        self.dispatcher = None
        self.after = after               # the line that follows the switch


class Tree:
    """The lifted units: definitions, labels, switches and table-less jumps."""

    def __init__(self, folder):
        header = read_text(folder / 'ppu_recomp.h')
        self.declared = sorted({int(name[5:], 16) for name in DECLARATION.findall(header)})
        self.definitions = {}                # function name -> unit name
        self.labels = defaultdict(set)       # unit name -> label names
        self.switches, self.gaps = [], []    # gaps: (unit, line, function, words)
        self.units = sorted(path for path in folder.glob('ppu_recomp*.cpp*'))
        for path in self.units:
            self._scan(path)

    def _scan(self, path):
        lines = read_text(path).splitlines()
        jumps, switches = [], []
        function = None
        for index, line in enumerate(lines):
            if SWITCH in line or UNRESOLVED in line:
                if SWITCH in line:
                    switches.append((index + 1, function, line,
                                     lines[index + 1] if index + 1 < len(lines) else ''))
                elif not any(SWITCH in lines[back]
                             for back in range(max(0, index - GAP_LOOKBACK), index)):
                    jumps.append((index, function))
            elif line.startswith('void func_'):
                match = DEFINITION.match(line)
                if match:
                    function = match.group(1)
                    self.definitions[function] = path.name
            elif line[:1] == 'l' or line[:8] == '    loc_':
                match = LABEL.match(line)
                if match:
                    self.labels[path.name].add(match.group(1))
        for line, function, text, after in switches:
            self.switches.append(Switch(path.name, line, function, text, after))
        for index, function in jumps:
            words = 0
            while (index + words + 1 < len(lines)
                   and TABLE_WORD.match(lines[index + words + 1])):
                words += 1
            if words:
                self.gaps.append((path.name, index + 1, function, words))


def check(tree, tables, listed, only, read_u32):
    """One line per dispatcher in lifted code, then the failures."""
    rows, failures = [], []
    starts = tree.declared
    defined = {int(name[5:], 16) for name in tree.definitions}
    listed_starts = [start for start, _ in listed] if listed else []
    listed_ends = [end for _, end in listed] if listed else []
    by_cases = defaultdict(list)
    for dispatcher, cases in sorted(tables.items()):
        by_cases[frozenset(cases)].append(dispatcher)
    in_function = defaultdict(list)
    for switch in tree.switches:
        if switch.function is None:
            failures.append(f'{switch.unit}:{switch.line}: switch outside a function')
        elif not only or switch.function in only:
            in_function[switch.function].append(switch)
    lifted = 0
    for dispatcher, cases in sorted(tables.items()):
        # The function that holds the dispatcher is the lifted function with
        # the greatest start at or before it. With a function list, the listed
        # function of the dispatcher counts too (a switch can extend the
        # function before it), and a dispatcher of a function that the tree
        # does not define is not lifted code.
        holders = []
        k = bisect.bisect_right(starts, dispatcher) - 1
        if k >= 0 and starts[k] in defined:
            holders.append(starts[k])
        if listed is not None:
            j = bisect.bisect_right(listed_starts, dispatcher) - 1
            if j < 0 or dispatcher >= listed_ends[j] or listed_starts[j] not in defined:
                continue
            if listed_starts[j] not in holders:
                holders.append(listed_starts[j])
        holders = [start for start in holders if not only or 'func_%08X' % start in only]
        if not holders:
            continue
        lifted += 1
        wanted = frozenset(cases)
        switch = None
        for start in holders:
            switch = next((item for item in in_function.get('func_%08X' % start, ())
                           if item.cases == wanted and item.dispatcher is None), None)
            if switch is not None:
                break
        if switch is None:
            failures.append(f'dispatcher 0x{dispatcher:08X} func_{holders[0]:08X}: no lifted switch '
                            f'with {len(cases)} case targets (table not resolved)')
            continue
        switch.dispatcher = dispatcher
        # The lines after the switch lift the words after the jump. The first
        # word of an inline table is not an instruction, so its line must exist.
        after = read_u32(dispatcher + 4)
        if after is not None and ppu_disasm.decode(after, dispatcher + 4).mnemonic == '.word' \
                and not switch.after.strip().startswith('/* TODO: .word 0x%08X */' % after):
            failures.append(f'{switch.unit}:{switch.line} {switch.function}: word 0x{after:08X} '
                            'after dispatcher 0x%08X is not lifted after the switch' % dispatcher)
        rows.append('dispatcher 0x%08X func_%08X cases %d switch %s:%d'
                    % (dispatcher, start, len(cases), switch.unit, switch.line))
    if not lifted:
        failures.append('no dispatcher of the ELF lies in a lifted function')
    for switch in tree.switches:
        if switch.function is None or (only and switch.function not in only):
            continue
        where = f'{switch.unit}:{switch.line} {switch.function}'
        if not switch.complete:
            failures.append(f'{where}: switch line is not complete')
        for label in switch.labels:
            if label not in tree.labels[switch.unit]:
                failures.append(f'{where}: arm {label} has no label in the unit')
        for callee in switch.callees:
            if callee not in tree.definitions:
                failures.append(f'{where}: arm {callee} has no definition in the tree')
        if switch.dispatcher is None and not any(
                int(switch.function[5:], 16) <= dispatcher
                for dispatcher in by_cases.get(switch.cases, ())):
            failures.append(f'{where}: lifted switch with {len(switch.cases)} cases and '
                            'no discovered table')
    gaps = [gap for gap in tree.gaps if not only or gap[2] in only]
    for unit, line, function, words in gaps:
        failures.append(f'{unit}:{line} {function}: table-less jump followed by {words} table words')
    for start in tree.declared:
        name = 'func_%08X' % start
        if (not only or name in only) and name not in tree.definitions:
            failures.append(f'{name}: declared in the header, defined in no unit')
    return rows, failures, len(gaps), lifted


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--tree', type=Path,
                        help='directory of the lifted PPU units (default: <generated>/ppu)')
    parser.add_argument('--elf', type=Path, help='debug ELF (default: key "elf" of config/local.json)')
    parser.add_argument('--functions', type=Path,
                        help='function list of the lift (named.functions.json); default: the header')
    parser.add_argument('--toc', nargs='+', type=lambda value: int(value, 16),
                        help='TOC candidates in place of the ones collected from the ELF')
    parser.add_argument('--only', help='comma list of functions to check, for example func_00CD8FBC')
    args = parser.parse_args()
    config = project.config()
    folder = args.tree or config['generated'] / 'ppu'
    elf_path = args.elf or config['elf']
    only = set(args.only.split(',')) if args.only else None
    began = time.time()
    tree = Tree(folder)
    if not tree.declared:
        raise SystemExit(f'{folder}: the header declares no function')
    all_insns, seg_map, read_u32, toc, code_hi = load_elf(elf_path)
    listed = None
    if args.functions:
        listed = sorted((int(str(entry['start']), 0), int(str(entry['end']), 0))
                        for entry in json.loads(args.functions.read_text()))
        starts = [start for start, _ in listed]
        text_hi = max(end for _, end in listed)
    else:
        starts, text_hi = tree.declared, code_hi
    started = time.time()
    tables, candidates = discover(all_insns, seg_map, read_u32, toc, starts, text_hi, args.toc)
    print(f'ELF: {len(all_insns)} instructions, TOC candidates '
          + ' '.join('0x%08X' % value for value in candidates)
          + f', {len(tables)} dispatchers, ELF load and discovery {time.time() - began:.1f} s')
    rows, failures, gaps, lifted = check(tree, tables, listed, only, read_u32)
    for row in rows:
        print(row)
    print(f'lifted dispatchers {lifted}, lifted switches {len(tree.switches)}, '
          f'table-less jumps with table words {gaps}, elapsed {time.time() - began:.1f} s')
    for failure in failures:
        print('FAIL ' + failure)
    if failures:
        print(f'FAIL {len(failures)} problem(s), gaps {gaps}')
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
