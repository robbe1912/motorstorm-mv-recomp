"""Check the x86 SIMD forms of the hot SPU helpers against their scalar bodies.

The vendor tree (vendor/ps3recomp) is checked in four builds: SPU_SIMD=1 with
SSSE3 (every form), SPU_SIMD=1 without SSSE3 (the SSE2 forms only), SPU_SIMD=0
(the scalar bodies on both sides), and the first build at /Od. --fork <path>
adds three builds of a checkout of fork branch codex/spu-simd-helpers. The
reference unit holds the scalar bodies, the driver unit the forms under test.
Each planted mutant changes one line of a private copy of the headers: the
check needs a value mismatch in the helpers that the mutant names.
Authored inputs only: no game input."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'scripts/fixtures/spu_simd_driver.c'
HEADERS = ('spu_helpers.h', 'spu_shuffle.h', 'spu_context.h')
CONVERTED = ('rotqby', 'rotqbyi', 'cwd', 'cwx', 'fm', 'shufb', 'ls_read128', 'ls_write128')
MIN_CASES = 1000000
# name, header, text before, text after, helpers that must show a mismatch
MUTANTS = [
    ('rotate-direction', 'spu_helpers.h',
     '#define SPU__X86_ROT_SRC(sh, j) (((((j) ^ 3) + (sh)) & 15) ^ 3)',
     '#define SPU__X86_ROT_SRC(sh, j) (((((j) ^ 3) - (sh)) & 15) ^ 3)', ('rotqby', 'rotqbyi')),
    ('rotate-count-off-by-one', 'spu_helpers.h',
     'spu__x86_rot_mask((int)b._u32[0])', 'spu__x86_rot_mask((int)b._u32[0] + 1)', ('rotqby',)),
    ('rotate-table-mask', 'spu_helpers.h',
     'return _mm_load_si128((const __m128i*)mask + (sh & 15));',
     'return _mm_load_si128((const __m128i*)mask + (sh & 7));', ('rotqby', 'rotqbyi')),
    ('cwd-inserted-word', 'spu_helpers.h',
     '{0x10111213u, 0x00010203u, 0x18191A1Bu, 0x1C1D1E1Fu}',
     '{0x10111213u, 0x00020304u, 0x18191A1Bu, 0x1C1D1E1Fu}', ('cwd', 'cwx')),
    ('cwd-row-index', 'spu_helpers.h',
     '_mm_load_si128((const __m128i*)table + ((pos >> 2) & 3))',
     '_mm_load_si128((const __m128i*)table + ((pos >> 1) & 3))', ('cwd', 'cwx')),
    ('cwx-operand', 'spu_helpers.h',
     'spu__x86_cwd_table(a._u32[0] + b._u32[0])', 'spu__x86_cwd_table(a._u32[0] - b._u32[0])', ('cwx',)),
    ('fm-normalize-bit', 'spu_helpers.h',
     'const __m128i t = _mm_srli_epi32(q, 24);', 'const __m128i t = _mm_srli_epi32(q, 23);', ('fm',)),
    ('fm-underflow-boundary', 'spu_helpers.h',
     '_mm_cmplt_epi32(biased, _mm_set1_epi32(1))', '_mm_cmplt_epi32(biased, zero)', ('fm',)),
    ('fm-overflow-boundary', 'spu_helpers.h',
     '_mm_cmpgt_epi32(biased, _mm_set1_epi32(255))', '_mm_cmpgt_epi32(biased, _mm_set1_epi32(256))', ('fm',)),
    ('fm-zero-operand', 'spu_helpers.h',
     '_mm_cmpeq_epi32(eb, zero)', '_mm_cmpeq_epi32(eb, kexp)', ('fm',)),
    ('fm-sign', 'spu_helpers.h',
     '_mm_xor_si128(av, bv)', '_mm_or_si128(av, bv)', ('fm',)),
    ('shufb-source-bit', 'spu_shuffle.h',
     '_mm_and_si128(cv, _mm_set1_epi8(16)), _mm_set1_epi8(16)',
     '_mm_and_si128(cv, _mm_set1_epi8(32)), _mm_set1_epi8(32)', ('shufb',)),
    ('shufb-special-value', 'spu_shuffle.h',
     '_mm_and_si128(e0, _mm_set1_epi8((char)0x80))', '_mm_and_si128(e0, _mm_set1_epi8((char)0xFF))', ('shufb',)),
    ('ls-load-swap-lost', 'spu_context.h',
     '_mm_storeu_si128((__m128i*)v._u8, _mm_shuffle_epi8(_mm_loadu_si128((const __m128i*)p), spu__ls_swap()));',
     '_mm_storeu_si128((__m128i*)v._u8, _mm_loadu_si128((const __m128i*)p));', ('ls_read128',)),
    ('ls-store-swap-lost', 'spu_context.h',
     '_mm_storeu_si128((__m128i*)p, _mm_shuffle_epi8(v, spu__ls_swap()));',
     '_mm_storeu_si128((__m128i*)p, v);', ('ls_write128',)),
    ('ls-swap-mask-byte', 'spu_context.h',
     '3, 2, 1, 0, 7, 6, 5, 4, 11, 10, 9, 8, 15, 14, 13, 12};',
     '3, 2, 1, 0, 7, 6, 5, 4, 11, 10, 9, 8, 15, 14, 13, 13};', ('ls_read128', 'ls_write128')),
]
# tree kind: defines of the reference unit (the scalar bodies)
REF_DEFINES = {
    'vendor': ('SPU_SIMD=0', 'SPU_SHUFB_FORCE_SCALAR'),
    'fork': ('SPU_SCALAR_HELPERS', 'SPU_SCALAR_INT', 'SPU_SHUFB_FORCE_SCALAR', 'SPU_SIMD_TREE_FORK'),
}
# variant: defines, unit built with SSSE3, optimization, expected gates (int, ssse3, ls, shufb)
VARIANTS = {
    'vendor': [('simd-ssse3', ('SPU_SIMD=1',), True, '/O2', (1, 1, 1, 1)),
               ('simd-base', ('SPU_SIMD=1',), False, '/O2', (1, 0, 0, 0)),
               ('simd-od', ('SPU_SIMD=1',), True, '/Od', (1, 1, 1, 1)),
               ('scalar', ('SPU_SIMD=0',), False, '/O2', (0, 0, 0, 0))],
    'fork': [('unit-ssse3', (), True, '/O2', (1, 1, 1, 1)),
             ('unit-base', (), False, '/O2', (1, 0, 0, 0)),
             ('scalar-macros', ('SPU_SCALAR_HELPERS', 'SPU_SCALAR_INT', 'SPU_SHUFB_FORCE_SCALAR'), True, '/O2', (0, 0, 0, 0))],
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--fork', type=Path, help='Checkout of the fork to check next to the vendor tree')
    ap.add_argument('--compiler', help='clang-cl of the Visual Studio environment by default')
    args = ap.parse_args()
    if os.name == 'nt' and not (os.environ.get('INCLUDE') and os.environ.get('LIB')):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from project import build_environment
        os.environ.update(build_environment())
    cc = args.compiler or os.environ.get('MV_CLANG') or os.environ.get('CC') or ('clang-cl' if os.name == 'nt' else 'clang')
    msvc = Path(cc).name.lower() in ('cl', 'cl.exe', 'clang-cl', 'clang-cl.exe')
    obj_suffix = '.obj' if msvc else '.o'
    exe_suffix = '.exe' if os.name == 'nt' else ''
    out = ROOT / 'temp/checks' / ('spu-simd-' + str(time.time_ns()))
    out.mkdir(parents=True)
    records, failures, report = [], [], dict(variants=[], mutants=[])

    def run(cmd, expected=0, timeout=120):
        cmd = list(map(str, cmd))
        r = subprocess.run(cmd, cwd=out, capture_output=True, text=True, errors='replace', timeout=timeout)
        records.append(dict(command=cmd, returncode=r.returncode, stdout=r.stdout, stderr=r.stderr))
        if expected is not None and r.returncode != expected:
            failures.append('%s returned %d, expected %d\n%s%s' % (
                ' '.join(cmd[:2]), r.returncode, expected, r.stdout[-2000:], r.stderr[-4000:]))
        return r

    def compile(name, source, defines, ssse3, opt, includes):
        obj = out / (name + obj_suffix)
        defines = [('/D' if msvc else '-D') + d for d in defines]
        includes = [('/I' if msvc else '-I') + str(p) for p in includes]
        ssse3 = [('/clang:-mssse3' if msvc else '-mssse3')] if ssse3 else []
        if msvc:
            cmd = [cc, '/nologo', '/c', '/std:c17', opt, '/UNDEBUG', '/D_CRT_SECURE_NO_WARNINGS', *includes, *defines, *ssse3, source, '/Fo' + str(obj)]
        else:
            cmd = [cc, '-std=c17', '-O0' if opt == '/Od' else '-O2', '-fno-strict-aliasing', '-ffp-contract=off', '-UNDEBUG',
                   *includes, *defines, *ssse3, '-c', source, '-o', obj]
        r = run(cmd)
        noise = [line for line in (r.stdout + r.stderr).splitlines() if line.strip()]
        if noise:
            print(name + ': ' + '\n'.join(noise[:12]))
        return obj

    def link(name, objs):
        exe = out / (name + exe_suffix)
        run([cc] + (['/nologo'] if msvc else []) + objs + (['/Fe' + str(exe)] if msvc else ['-o', exe]))
        return exe

    def parse(text):
        gates = re.search(r'^gates int=(\d) ssse3=(\d) ls=(\d) shufb=(\d)$', text, re.M)
        ops = {name: dict(cases=int(c), ref=int(r), model=int(m)) for name, c, r, m in
               re.findall(r'^op (\S+)\s+cases=(\d+) ref=(\d+) model=(\d+)$', text, re.M)}
        result = re.search(r'^RESULT (PASS|FAIL) cases=(\d+)$', text, re.M)
        return gates and tuple(map(int, gates.groups())), ops, result and result.group(1)

    def execute(name, exe):
        r = run([exe], expected=None, timeout=600)
        (out / (name + '.log')).write_text(r.stdout + r.stderr, encoding='utf8')
        return r.returncode, r.stdout + r.stderr

    for kind in ['vendor'] + (['fork'] if args.fork else []):
        root = args.fork.resolve() if kind == 'fork' else ROOT / 'vendor/ps3recomp'
        spu, inc = root / 'runtime/spu', root / 'include'
        float_obj = compile(kind + '-float', spu / 'spu_float_simd.c', (), False, '/O2', [spu, inc])
        for variant, defines, ssse3, opt, gates in VARIANTS[kind]:
            name = kind + '-' + variant
            ref_obj = compile(name + '-ref', FIXTURE, ['SPU_SIMD_REF', *REF_DEFINES[kind]], False, '/O2', [spu, inc])
            drv_obj = compile(name + '-driver', FIXTURE, defines, ssse3, opt, [spu, inc])
            exe = link(name, [ref_obj, drv_obj, float_obj])
            code, text = execute(name, exe)
            got_gates, ops, result = parse(text)
            report['variants'].append(dict(tree=kind, root=str(root), variant=variant, defines=defines, ssse3=ssse3,
                                           optimization=opt, returncode=code, gates=got_gates, ops=ops, result=result))
            if code != 0 or result != 'PASS':
                failures.append('%s: result %r, return code %d' % (name, result, code))
            if got_gates != gates:
                failures.append('%s: gates %s, expected %s' % (name, got_gates, gates))
            for op in CONVERTED:
                if op not in ops or ops[op]['cases'] < MIN_CASES or ops[op]['ref'] or ops[op]['model']:
                    failures.append('%s: %s %r' % (name, op, ops.get(op)))
            print(name + ': gates=%s result=%s %s' % (got_gates, result, ' '.join(
                '%s=%d' % (op, ops[op]['cases']) for op in CONVERTED if op in ops)), flush=True)
        # Mutants on the build with every form active. The reference unit stays the same.
        base = VARIANTS[kind][0]
        ref_obj = out / (kind + '-' + base[0] + '-ref' + obj_suffix)
        for mutant, header, before, after, helpers in MUTANTS:
            private = out / kind / mutant
            private.mkdir(parents=True)
            for h in HEADERS:
                text = (spu / h).read_text(encoding='utf8')
                if h == header:
                    if text.count(before) != 1:
                        failures.append('%s: %s: %s holds the text %d times' % (kind, mutant, h, text.count(before)))
                    text = text.replace(before, after)
                (private / h).write_text(text, encoding='utf8')
            name = kind + '-' + mutant
            drv_obj = compile(name + '-driver', FIXTURE, base[1], base[2], base[3], [private, spu, inc])
            exe = link(name, [ref_obj, drv_obj, float_obj])
            code, text = execute(name, exe)
            _, ops, result = parse(text)
            bad = {op: ops[op]['ref'] for op in helpers if op in ops}
            rejected = code == 1 and result == 'FAIL' and all(bad.values()) if bad else False
            report['mutants'].append(dict(tree=kind, mutant=mutant, header=header, before=before, after=after,
                                          helpers=helpers, mismatches=bad, returncode=code, result=result, rejected=rejected))
            if not rejected:
                failures.append('%s: mutant %s is not rejected: %s, return code %d' % (kind, mutant, bad, code))
            print('%s mutant %-24s rejected=%s %s' % (kind, mutant, rejected, bad), flush=True)

    report['sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (FIXTURE, Path(__file__))}
    report['compiler'] = cc
    report['failures'] = failures
    report['passed'] = not failures
    (out / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    (out / 'commands.json').write_text(json.dumps(records, indent=2), encoding='utf8')
    for line in failures:
        print('FAIL ' + line)
    print('spu simd: %s, %d builds, %d mutants, evidence %s' % (
        'PASS' if report['passed'] else 'FAIL', len(report['variants']), len(report['mutants']), out))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
