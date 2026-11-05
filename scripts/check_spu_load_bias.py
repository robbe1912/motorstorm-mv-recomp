#!/usr/bin/env python3
"""Authored ELF address contracts and actual emitted native-continuation execution."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/ps3recomp'
if os.name == 'nt':
    from project import build_environment
    os.environ.update(build_environment())
sys.path.insert(0, str(VENDOR / 'tools'))
from find_spu_functions import detect_functions, parse_elf
from wrap_spu_elf import wrap

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--output', type=Path)
ap.add_argument('--historical-lifter', type=Path)
args = ap.parse_args()
out = (args.output or ROOT / 'temp/checks' / ('load-bias-' + str(time.time_ns()))).resolve()
out.mkdir(parents=True, exist_ok=False)
report = {'contracts': [], 'commands': []}


def record(name):
    report['contracts'].append(name)
    print('PASS ' + name, flush=True)


def discover(data, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return detect_functions(data, verbose=False, **kw)


def starts(data, **kw):
    return {s for s, _ in discover(data, **kw)[0]}


def blob(words):
    return struct.pack('>' + 'I' * len(words), *words)


def registered(source):
    return {int(m, 16) for m in re.findall(r'\{\s*0x([0-9A-Fa-f]+)u?\s*,\s*\w*spu_func_[0-9A-Fa-f]+\s*,', source)}


def command(argv, **kw):
    result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=120, **kw)
    report['commands'].append({'argv': list(map(str, argv)), 'returncode': result.returncode,
                               'stdout': result.stdout, 'stderr': result.stderr})
    (out / 'result.json').write_text(json.dumps(report, indent=2))
    assert result.returncode == 0, 'Command failed; complete diagnostics: ' + str(out / 'result.json')
    return result


# Independent encoder constants; no proprietary inputs or disassembler oracle.
plain = [0x42000000 | (0x4040 << 7) | 2, 0x35000100,
         0x40200000, 0x40200000, 0x40800000 | (123 << 7) | 3, 0x35000000]
relative_elf = wrap(blob(plain))
assert starts(relative_elf, load_bias=0x4030) == {0x4030, 0x4040}
record('absolute immediate continuation discovered in actual LS coordinates')
large = [0x40200000] * (0x6000 // 4)
large[0] = 0x42000000 | (0x5040 << 7) | 2
assert 0x5040 in starts(wrap(blob(large)), load_bias=0x4030)
assert 0x9070 not in starts(wrap(blob(large)), load_bias=0x4030)
record('absolute target inside old window is not biased twice')
assert discover(relative_elf) == discover(relative_elf, load_bias=0)
assert discover(blob(plain), raw=True, base_override=0x4030)[0] == discover(relative_elf, load_bias=0x4030)[0]
record('zero-bias and historical raw-origin compatibility')

# Relative BR and absolute BRA must reach the same execution address. The
# displacement is relative to PC; the BRA immediate is already an LS address.
for word, label in [(0x32000000 | (4 << 7), 'relative'),
                    (0x30000000 | ((0x4040 >> 2) << 7), 'absolute')]:
    data = wrap(blob([word, *plain[1:]]))
    assert 0x4040 in starts(data, load_bias=0x4030), label
    record(label + ' branch coordinate')

symbols = [{'name': 'interior', 'addr': 0x100C, 'size': 4}]
data = wrap(blob(plain), base=0x1000, entry=0x1008, symbols=symbols)
found, segment = discover(data, load_bias=0x3030)
assert {0x4038, 0x403C, 0x4040} <= {s for s, _ in found}
assert (0x403C, 0x4040) in found and segment[1] == 0x4030
record('nonzero ELF vaddr plus bias, entry and sized symbol')
special = bytearray(wrap(blob([0x40200000] * 4 + [0x40803D83, 0x35000000]),
                        symbols=[{'name': 'absolute', 'addr': 0x4040, 'size': 4},
                                 {'name': 'undefined', 'addr': 0x14, 'size': 4}]))
symtab = next(s for s in parse_elf(special)['shs'] if s['type'] == 2)
struct.pack_into('>H', special, symtab['off'] + 16 + 14, 0xFFF1)
struct.pack_into('>H', special, symtab['off'] + 32 + 14, 0)
assert 0x4040 in starts(special, load_bias=0x4030)
assert 0x4044 not in starts(special, load_bias=0x4030)
record('absolute symbols retain LS address and undefined symbols are not entries')

# A separate data PT_LOAD contains three distinct absolute code pointers.
# Its vaddr moves; its file offset and contents do not.
data = bytearray(wrap(blob([0x35000000] * 12)))
elf = parse_elf(data)
phoff = struct.unpack_from('>I', data, 0x1C)[0]
payload = len(data)
data.extend(blob([0x4040, 0x4048, 0x4050]))
struct.pack_into('>H', data, 0x2C, 2)
# Put the additional header at EOF, then relocate the whole header table there.
headers = bytes(data[phoff:phoff + 32]) + struct.pack('>IIIIIIII', 1, payload, 0x100, 0x100, 12, 12, 6, 4)
struct.pack_into('>I', data, 0x1C, len(data))
data.extend(headers)
assert {0x4040, 0x4048, 0x4050} <= starts(bytes(data), load_bias=0x4030)
record('absolute pointers in independently located data segment')

outside = plain.copy(); outside[0] = 0x42000000 | (0x9000 << 7) | 2
assert 0x9000 not in starts(wrap(blob(outside)), load_bias=0x4030)
for kw in [{'load_bias': 1}, {'load_bias': True}, {'load_bias': '4'},
           {'load_bias': -4}, {'load_bias': 0x40000},
           {'load_bias': 4, 'raw': True}, {'load_bias': 4, 'base_override': 0}]:
    try:
        discover(relative_elf, **kw)
    except ValueError:
        pass
    else:
        raise AssertionError('invalid bias admitted: ' + str(kw))
record('bounds, alignment and ambiguous options rejected')

names = ['plain', 'disable', 'enable']
programs = []
for i, name in enumerate(names):
    words = plain.copy(); words[1] |= [0, 0x80000, 0x40000][i]
    programs.append(words)
    image = out / (name + '.elf'); image.write_bytes(wrap(blob(words)))
    command([sys.executable, VENDOR / 'tools/spu_lifter.py', '--auto-functions', image,
             '--base', '0x4030', '-o', out, '--source-name', name + '.c',
             '--header-name', name + '.h', '--symbol-prefix', name + '_'])
    assert 0x4040 in registered((out / (name + '.c')).read_text())

if args.historical_lifter:
    old = out / 'historical'; old.mkdir()
    command([sys.executable, args.historical_lifter, '--auto-functions', out / 'plain.elf',
             '--base', '0x4030', '-o', old])
    assert 0x4040 not in registered((old / 'spu_recomp.c').read_text())
    report['historical_lifter_sha256'] = hashlib.sha256(args.historical_lifter.read_bytes()).hexdigest()
    record('actual old-production RED: successful generation omits native continuation')

header = []
for name in names:
    for suffix in ['spu_func_00004030', 'spu_func_00004040']:
        header.append('void ' + name + '_' + suffix + '(spu_context*);')
    header.append('void ' + name + '_spu_recomp_register(void);')
header.append('static const uint32_t programs[3][6] = {' + ','.join('{' + ','.join(hex(w) for w in p) + '}' for p in programs) + '};')
for array, suffix, proto in [('entries', 'spu_func_00004030', 'spu_context*'),
                             ('targets', 'spu_func_00004040', 'spu_context*'),
                             ('registrations', 'spu_recomp_register', 'void')]:
    header.append('static void (*const ' + array + '[])(' + proto + ') = {' + ','.join(n + '_' + suffix for n in names) + '};')
(out / 'load_bias_programs.h').write_text('\n'.join(header) + '\n')
spu = VENDOR / 'runtime/spu'
runtime = ['spu_channels.c', 'spu_drain.c', 'spu_lockstep.c', 'spu_coherency.c',
           'spu_workload.c', 'spurs_policy.c', 'spurs_job.c', 'spu_tsp_weak.c',
           'spu_vm_pagemap.c', 'spurs_policy_blob_weak.c', 'spu_interp.c',
           'spu_float_simd.c', 'spu_task_lifecycle.c']
sources = [ROOT / 'scripts/fixtures/spu_load_bias.c', *[out / (n + '.c') for n in names],
           *[spu / n for n in runtime], VENDOR / 'runtime/platform/win32_compat.c',
           VENDOR / 'runtime/memory/guest_read_sync.c',
           VENDOR / 'runtime/diag/loadtime_trace.c', VENDOR / 'runtime/platform/thread_name.c']
includes = [out, VENDOR / 'include', spu, VENDOR / 'runtime/platform']
binary = out / ('test.exe' if os.name == 'nt' else 'test')
if os.name == 'nt':
    compiler = os.environ.get('MV_CLANG') or shutil.which('clang-cl')
    assert compiler, 'clang-cl and Visual Studio environment required'
    argv = [compiler, '/nologo', '/TC', '/std:c17', '/O1', '/UNDEBUG', '/MDd',
            *['/I' + str(p) for p in includes], *sources, '/Fo' + str(out) + os.sep,
            '/Fe' + str(binary), '/link', 'Synchronization.lib']
else:
    compiler = os.environ.get('CC') or shutil.which('cc'); assert compiler
    argv = [compiler, '-std=gnu17', '-D_GNU_SOURCE', '-O1', '-UNDEBUG', *['-I' + str(p) for p in includes],
            *sources, '-pthread', '-lm', '-o', binary]
command(argv)
env = {k: v for k, v in os.environ.items() if not k.startswith(('SPU_', 'SPURS_', 'YDKJ_'))}
result = command([binary], env=env, cwd=out)
assert 'PASS 3 actual generated native continuations' in result.stdout
record('actual generated continuation execution and independent architectural oracle')
report['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in [Path(__file__), VENDOR / 'tools/find_spu_functions.py',
                                     VENDOR / 'tools/spu_lifter.py', sources[0]]}
(out / 'result.json').write_text(json.dumps(report, indent=2))
print('Evidence: ' + str(out / 'result.json'))
