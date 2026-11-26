"""Check the fast forms of the SPU float helpers: fa, fs, fm, fma, fms, fnms.

The vendor tree (vendor/ps3recomp) is checked in four builds: the fast forms
with SSSE3, without SSSE3, at /Od, and off (SPU_FLOAT_FAST=0). --fork <path>
adds the same four builds of a checkout of the fork. --vendor <path> checks
another copy of the vendor tree in place of vendor/ps3recomp.
Each build compares every call with the exact integer path of the tree and
with the scoped host form of the earlier path, and it checks that each call
takes the fast form when and only when the rules hold: a scope is active, the
host mode is the mode of a scope, no exponent field 255 in an input, no result
of 2^127 and above, FMA3 admitted for the fused family. The groups cover each
lane position, zeros of both signs, denormals as input and as result, exponent
field 255, one million random vectors per helper (fixed seed), inputs that need
one rounding, six host modes changed from outside the scope, a scope without
FMA3, and calls outside a scope. Rows from the exact-rational model
(robbe_float_oracle.py) go through stdin.
Each planted mutant changes one text of a private copy of the headers. A
mutant of the fused family changes the same text at each FMA3 function that
the header has. The check needs a value mismatch, a host mismatch or a wrong
path in a helper that the mutant names. Authored inputs only: no game input.
--mutant runs named mutants only, with no build of the forms.
"""
import argparse
import hashlib
import json
import os
import random
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import robbe_float_oracle as oracle

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'scripts/fixtures/spu_float_fast_driver.c'
HEADERS = ('spu_float_simd.h', 'spu_helpers.h', 'spu_context.h', 'spu_shuffle.h', 'spu_float.h')
HELPERS = ('fa', 'fs', 'fm', 'fma', 'fms', 'fnms')
BINARY, FUSED = HELPERS[:3], HELPERS[3:]
MIN_CASES = 6000000   # the matrices and one million random vectors per helper
MIN_FAST = 400000     # fast calls of each helper in the random group
MIN_SLOW = 100000     # calls of each helper on the earlier path in the random group
NO_FAST_GROUPS = ('mode-nearest-ftz-daz', 'mode-down-ftz-daz', 'mode-up-ftz-daz', 'mode-rtz-no-ftz',
                  'mode-rtz-ftz-no-daz', 'mode-nearest-no-ftz', 'outside-scope-spu-mode', 'outside-scope-nearest')
PROBE_ADD = '0x42800001u, 0xc2800001u, 0x80800000u, 0x00000000u'
# The operand list of the two FMA3 functions in spu_float_simd.h: the second line of each function.
OPERANDS = '\n' + ' ' * 25 + ': [a] "+x"(a) : [b] "x"(b), [c] "x"(c), [z] "x"('
# Form 1: (name, file, text before, text after, helpers that must show a mismatch, trees (None: both)).
# Form 2: (name, file, [(text before, text after, mark), ...], helpers, trees). mark '' : the text must be
# in the header one time. mark 'fnma': the same, in a header that has the function spu_sf_fast_fnma.
# A header without that function has only spu_sf_fast_fma, and fnms uses it: there the first edit
# covers fnms.
MUTANTS = [
    ('mul-is-add', 'spu_float_simd.h', 'SPU_SF_FAST_OP(spu_sf_fast_mul, "mulps")',
     'SPU_SF_FAST_OP(spu_sf_fast_mul, "addps")', ('fm',), None),
    ('sub-is-add', 'spu_float_simd.h', 'SPU_SF_FAST_OP(spu_sf_fast_sub, "subps")',
     'SPU_SF_FAST_OP(spu_sf_fast_sub, "addps")', ('fs',), None),
    # The binary forms use the SPU_SF_FAST_OP macro. The fused family uses spu_sf_fast_fma. A header
    # with the function spu_sf_fast_fnma (fork commit e0afc08e) has fnms call that function.
    ('binary-zero-fix-lost', 'spu_float_simd.h', r'instruction " %[b], %[a]\n\taddps %[z], %[a]"',
     r'instruction " %[b], %[a]"', BINARY, None),
    ('fused-zero-fix-lost', 'spu_float_simd.h',
     [(r'"vfmadd213ps %[c], %[b], %[a]\n\taddps %[z], %[a]"', r'"vfmadd213ps %[c], %[b], %[a]"'),
      (r'"vfnmadd213ps %[c], %[b], %[a]\n\taddps %[z], %[a]"', r'"vfnmadd213ps %[c], %[b], %[a]"', 'fnma')],
     FUSED, None),
    ('binary-zero-fix-negative', 'spu_float_simd.h', '[b] "x"(b), [z] "x"(_mm_setzero_ps())',
     '[b] "x"(b), [z] "x"(_mm_set1_ps(-0.0f))', BINARY, None),
    ('fused-zero-fix-negative', 'spu_float_simd.h',
     [(r'"vfmadd213ps %[c], %[b], %[a]\n\taddps %[z], %[a]"' + OPERANDS + '_mm_setzero_ps())',
       r'"vfmadd213ps %[c], %[b], %[a]\n\taddps %[z], %[a]"' + OPERANDS + '_mm_set1_ps(-0.0f))'),
      (r'"vfnmadd213ps %[c], %[b], %[a]\n\taddps %[z], %[a]"' + OPERANDS + '_mm_setzero_ps())',
       r'"vfnmadd213ps %[c], %[b], %[a]\n\taddps %[z], %[a]"' + OPERANDS + '_mm_set1_ps(-0.0f))', 'fnma')],
     FUSED, None),
    ('ftz-test-lost', 'spu_float_simd.h', PROBE_ADD,
     '0x42800001u, 0xc2800001u, 0x00000000u, 0x00000000u', HELPERS, None),
    ('daz-test-lost', 'spu_float_simd.h',
     'return _mm_movemask_epi8(_mm_cmpeq_epi32(product, _mm_setzero_si128())) == 0xffff;', 'return 1;', HELPERS, None),
    ('rounding-test-lost', 'spu_float_simd.h', PROBE_ADD,
     '0x42800000u, 0xc2800000u, 0x80800000u, 0x00000000u', HELPERS, None),
    # The scope test is the first condition of each fast form. The fused family has its own test (value 2).
    ('scope-test-lost', 'spu_float_simd.h', 'if (!g_spu_sf_simd_scope || !spu_sf_probe()) return 0;',
     'if (!spu_sf_probe()) return 0;', BINARY, None),
    ('fma-admission-lost', 'spu_float_simd.h', 'if (g_spu_sf_simd_scope != 2 || !spu_sf_probe()) return 0;',
     'if (!spu_sf_probe()) return 0;', FUSED, None),
    # The FMA3 instruction: replaced by two roundings, by another instruction, or with two operands exchanged.
    # The fork at e0afc08e and the game tree after the carry of e0afc08e have two FMA3 functions, and fnms
    # calls spu_sf_fast_fnma there. Each mutant changes both functions, so fnms changes in each form.
    ('fused-two-roundings', 'spu_float_simd.h',
     [(r'"vfmadd213ps %[c], %[b], %[a]\n\taddps %[z], %[a]"',
       r'"mulps %[b], %[a]\n\taddps %[c], %[a]\n\taddps %[z], %[a]"'),
      (r'"vfnmadd213ps %[c], %[b], %[a]\n\taddps %[z], %[a]"',
       r'"vmulps %[b], %[a], %[a]\n\tvsubps %[a], %[c], %[a]\n\taddps %[z], %[a]"', 'fnma')], FUSED, None),
    ('fused-is-add', 'spu_float_simd.h',
     [(r'"vfmadd213ps %[c], %[b], %[a]', r'"addps %[c], %[a]'),
      (r'"vfnmadd213ps %[c], %[b], %[a]', r'"addps %[c], %[a]', 'fnma')], FUSED, None),
    ('fma-operands-swapped', 'spu_float_simd.h',
     [(r'"vfmadd213ps %[c], %[b], %[a]', r'"vfmadd213ps %[b], %[c], %[a]'),
      (r'"vfnmadd213ps %[c], %[b], %[a]', r'"vfnmadd213ps %[b], %[c], %[a]', 'fnma')], FUSED, None),
    # The result test sends every call to the earlier path whose host result has exponent field 254 or
    # 255. An input with exponent field 255 gives such a host result (infinity or NaN), so the test
    # also covers these inputs: the fast form has no separate input test.
    ('result-range', 'spu_float_simd.h', '_mm_and_si128(result, _mm_set1_epi32(0x7fffffff)), _mm_set1_epi32(0x7effffff));',
     '_mm_and_si128(result, _mm_set1_epi32(0x7fffffff)), _mm_set1_epi32(0x7f7fffff));', HELPERS, None),
    ('binary-result-test-lost', 'spu_float_simd.h', 'if (_mm_movemask_epi8(spu_sf_fast_bad(av))) return 0;',
     'if (0) return 0;', BINARY, None),
    ('fused-result-test-lost', 'spu_float_simd.h', 'if (_mm_movemask_epi8(spu_sf_fast_bad(r))) return 0;',
     'if (0) return 0;', FUSED, None),
    ('fallback-lost-fa', 'spu_helpers.h', 'return spu__fa_slow(a, b);', 'return a;', ('fa',), None),
    ('fms-negation', 'spu_helpers.h', 'c._u32, 0, 0x80000000u)) return r; return spu__fms_slow(a, b, c);',
     'c._u32, 0x80000000u, 0)) return r; return spu__fms_slow(a, b, c);', ('fms',), None),
    ('fnms-negation-lost', 'spu_helpers.h', 'c._u32, 0x80000000u, 0)) return r; return spu__fnms_slow(a, b, c);',
     'c._u32, 0, 0)) return r; return spu__fnms_slow(a, b, c);', ('fnms',), None),
    ('fm-fast-is-add', 'spu_helpers.h', '#define SPU_FM_FAST(out, a, b) spu_sf_fast_binary(out, a, b, 2)',
     '#define SPU_FM_FAST(out, a, b) spu_sf_fast_binary(out, a, b, 0)', ('fm',), ('vendor',)),
    ('fm-fast-is-add', 'spu_helpers.h',
     'spu_sf_fast_binary(r._u32, a._u32, b._u32, 2)) return r; return spu__fm_slow(a, b);',
     'spu_sf_fast_binary(r._u32, a._u32, b._u32, 0)) return r; return spu__fm_slow(a, b);', ('fm',), ('fork',)),
]
# variant: SSSE3, optimization, fast forms off
VARIANTS = [('fast-ssse3', True, '/O2', False), ('fast-base', False, '/O2', False),
            ('fast-od', True, '/Od', False), ('off', True, '/O2', True)]


def model_rows():
    """Rows for stdin: op and three vectors. Returns the rows, the results of the
    exact-rational model, and the number of rows per op that must take the fast form."""
    rng = random.Random(0x5f1a57)
    rows, expected, fast = [], [], [0] * 6

    def add(op, lanes):
        rows.append((op, lanes))
        results = [oracle.reference(op, *lane) for lane in lanes]
        expected.extend(results)
        words = [w for lane in lanes for w in lane[:3 if op >= 3 else 2]]   # fa, fs and fm do not read the third operand
        fast[op] += all(((w >> 23) & 255) != 255 for w in words) and all((r & 0x7fffffff) < 0x7f000000 for r in results)

    def word(kind):
        r = rng.getrandbits(32)
        if kind == 0:
            return r
        exponent = (r >> 23) % 255 if kind == 1 else rng.randint(100, 150)
        return (r & 0x807fffff) | (exponent << 23)

    def as_float(word):
        return struct.unpack('<f', struct.pack('<I', word))[0]

    for op, group in oracle.cases():
        if op > 5:
            break
        add(op, group)
    for op in range(6):
        for n in range(2048):
            add(op, [tuple(word(n & 3) for _ in range(3)) for _ in range(4)])
        for _ in range(256):   # third operand near the negative product: the fused family needs one rounding
            lanes = []
            for _ in range(4):
                a, b = word(2), word(2)
                near = struct.unpack('<I', struct.pack('<f', -as_float(a) * as_float(b)))[0]
                lanes.append((a, b, near ^ (rng.getrandbits(1) << 31)))
            add(op, lanes)
    return rows, expected, fast


def parse(text):
    gates = re.search(r'^FF gates fast=(\d+) x86=(\d+)$', text, re.M)
    scope = re.search(r'^FF scope=(\d+)$', text, re.M)
    groups = {(g, op): dict(calls=int(c), fast=int(f), value=int(v), hit=int(h), host=int(s)) for g, op, c, f, v, h, s in
              re.findall(r'^group (\S+) op (\S+) calls=(\d+) fast=(\d+) value=(\d+) hit=(\d+) host=(\d+)$', text, re.M)}
    model = {op: (int(n), int(f)) for op, n, f in re.findall(r'^model (\S+) rows=(\d+) fast=(\d+)$', text, re.M)}
    result = re.search(r'^RESULT (PASS|FAIL) cases=(\d+) fast=(\d+)$', text, re.M)
    results = [int(w, 16) for line in re.findall(r'^(?:[0-9a-f]{8} ?){4}$', text, re.M) for w in line.split()]
    flags = re.search(r'^FF flags exact-add new=([0-9a-f]+)$', text, re.M)
    return dict(fast=int(gates.group(1)) if gates else None, scope=int(scope.group(1)) if scope else None, groups=groups,
                model=model, result=result.group(1) if result else None, cases=int(result.group(2)) if result else 0,
                results=results, flags=flags.group(1) if flags else None)


def wrong_path(groups, helpers):
    return {op: sum(groups[key][c] for key in groups for c in ('value', 'hit', 'host') if key[1] == op) for op in helpers}


def edits_of(entry):
    """The edits of one mutant: (text before, text after, mark). The mark 'fnma' holds the edits of the
    function spu_sf_fast_fnma. A header without that function has only spu_sf_fast_fma, and fnms
    uses it: there the other edits cover fnms."""
    if len(entry) == 5:
        name, header, pairs, helpers, trees = entry
        return name, header, [p if len(p) == 3 else (p[0], p[1], '') for p in pairs], helpers, trees
    return entry[0], entry[1], [(entry[2], entry[3], '')], entry[4], entry[5]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--fork', type=Path, help='Checkout of the fork to check next to the vendor tree')
    ap.add_argument('--vendor', type=Path, help='Another copy of the vendor tree, checked in place of vendor/ps3recomp')
    ap.add_argument('--compiler', help='clang-cl of the Visual Studio environment by default')
    ap.add_argument('--mutant', help='Comma separated names: only these mutants, with no build of the forms')
    args = ap.parse_args()
    if os.name == 'nt' and not (os.environ.get('INCLUDE') and os.environ.get('LIB')):
        from project import build_environment
        os.environ.update(build_environment())
    cc = args.compiler or os.environ.get('MV_CLANG') or os.environ.get('CC') or ('clang-cl' if os.name == 'nt' else 'clang')
    msvc = Path(cc).name.lower() in ('cl', 'cl.exe', 'clang-cl', 'clang-cl.exe')
    obj_suffix, exe_suffix = ('.obj', '.exe') if msvc else ('.o', '')
    out = ROOT / 'temp/checks' / ('spu-float-fast-' + str(time.time_ns()))
    out.mkdir(parents=True)
    records, failures, builds, mutants = [], [], [], []
    only = set(args.mutant.split(',')) if args.mutant else None
    if only and not only <= {entry[0] for entry in MUTANTS}:
        ap.error('unknown mutant names: %s' % ' '.join(sorted(only - {entry[0] for entry in MUTANTS})))
    rows, expected, fast_rows = model_rows()
    payload = ''.join('%u %s\n' % (op, ' '.join('%08x' % lanes[lane][operand] for operand in range(3) for lane in range(4)))
                      for op, lanes in rows)
    rows_per_op = [sum(1 for op, _ in rows if op == h) for h in range(6)]

    def run(cmd, expected, timeout=600, stdin=None):
        cmd = list(map(str, cmd))
        r = subprocess.run(cmd, cwd=out, capture_output=True, text=True, errors='replace', timeout=timeout, input=stdin)
        records.append(dict(command=cmd, returncode=r.returncode, stdout=r.stdout if stdin is None else 'model output retained separately',
                            stderr=r.stderr))
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
            cmd = [cc, '/nologo', '/c', '/std:c17', opt, '/UNDEBUG', '/D_CRT_SECURE_NO_WARNINGS', '/clang:-fno-strict-aliasing',
                   '/clang:-ffp-contract=off', *includes, *defines, *ssse3, source, '/Fo' + str(obj)]
        else:
            cmd = [cc, '-std=gnu17', '-O0' if opt == '/Od' else '-O2', '-fno-strict-aliasing', '-ffp-contract=off', '-UNDEBUG',
                   *includes, *defines, *ssse3, '-c', source, '-o', obj]
        r = run(cmd, 0)
        noise = [line for line in (r.stdout + r.stderr).splitlines() if 'error' in line or 'warning' in line]
        if noise:
            print(name + ': ' + '\n'.join(noise[:12]), flush=True)
        return obj if obj.exists() else None

    def link(name, objs):
        if any(obj is None for obj in objs):
            return None
        exe = out / (name + exe_suffix)
        run([cc] + (['/nologo'] if msvc else []) + objs + (['/Fe' + str(exe)] if msvc else ['-o', exe]), 0)
        return exe if exe.exists() else None

    def measure(name, exe, quick):
        """Runs one build with the model rows. Returns the parsed output."""
        if exe is None:
            failures.append('%s: no executable' % name)
            print(name + ': no executable', flush=True)
            return None
        r = run([exe] + (['quick'] if quick else []), None, stdin=None if quick else payload)
        text = r.stdout + r.stderr
        (out / (name + '.log')).write_text(text, encoding='utf8')
        return dict(code=r.returncode, text=text, **parse(text))

    for kind, root in [('vendor', (args.vendor or ROOT / 'vendor/ps3recomp').resolve())] + \
                      ([('fork', args.fork.resolve())] if args.fork else []):
        spu, inc = root / 'runtime/spu', root / 'include'
        float_obj = compile(kind + '-float', spu / 'spu_float_simd.c', [], False, '/O2', [spu, inc])
        for variant, ssse3, opt, off in ([] if only else VARIANTS):
            name = '%s-%s' % (kind, variant)
            defines = ['SPU_SIMD=1'] * (kind == 'vendor') + ['SPU_FLOAT_FAST=0'] * off + ['SPU_FLOAT_FAST_TREE_FORK'] * (kind == 'fork')
            drv_obj = compile(name + '-driver', FIXTURE, defines, ssse3, opt, [root, inc, spu])
            p = measure(name, link(name, [drv_obj, float_obj]), False)
            if p is None:
                continue
            g, local = p['groups'], []
            if p['code'] != 0 or p['result'] != 'PASS':
                local.append('%s: result %r, return code %d' % (name, p['result'], p['code']))
            if p['fast'] != (0 if off else 1) or p['scope'] != 2:
                local.append('%s: gates fast=%r scope=%r (the host must have FMA3)' % (name, p['fast'], p['scope']))
            for op in HELPERS:
                cell = g.get(('scope-held-random', op))
                if not cell or cell['calls'] < 1000000:
                    local.append('%s: %s has %r random calls' % (name, op, cell))
                elif off:
                    if cell['fast']:
                        local.append('%s: %s takes the fast form with the forms off' % (name, op))
                elif cell['fast'] < MIN_FAST or cell['calls'] - cell['fast'] < MIN_SLOW:
                    local.append('%s: %s fast %d, earlier path %d: both must be covered' % (name, op, cell['fast'], cell['calls'] - cell['fast']))
            for group in NO_FAST_GROUPS:
                if any(g.get((group, op), {}).get('fast', 0) for op in HELPERS):
                    local.append('%s: a fast call in group %s' % (name, group))
            if not off and (any(g.get(('scope-without-fma', op), {}).get('fast', 1) == 0 for op in BINARY)
                            or any(g.get(('scope-without-fma', op), {}).get('fast', 1) for op in FUSED)):
                local.append('%s: group scope-without-fma must be fast for %s and never fast for %s' % (name, BINARY, FUSED))
            if p['cases'] < MIN_CASES:
                local.append('%s: %d cases, expected %d' % (name, p['cases'], MIN_CASES))
            if p['results'] != expected:
                local.append('%s: %d of %d model results differ from the exact-rational model' % (
                    name, sum(x != y for x, y in zip(p['results'], expected)) + abs(len(p['results']) - len(expected)), len(expected)))
            for op in HELPERS:
                want = (rows_per_op[HELPERS.index(op)], 0 if off else fast_rows[HELPERS.index(op)])
                if p['model'].get(op) != want:
                    local.append('%s: model %s %r, expected %r' % (name, op, p['model'].get(op), want))
            failures.extend(local)
            builds.append(dict(tree=kind, root=str(root), variant=variant, ssse3=ssse3, optimization=opt, fast_forms=not off,
                               returncode=p['code'], result=p['result'], cases=p['cases'], scope=p['scope'],
                               flags_of_an_exact_fast_call=p['flags'], groups={'%s %s' % k: v for k, v in g.items()}, model=p['model']))
            print('%s: gates fast=%d scope=%d result=%s cases=%d flags=%s %s' % (
                name, p['fast'], p['scope'], p['result'], p['cases'], p['flags'],
                ' '.join('%s=%d/%d' % (op, g.get(('scope-held-random', op), {}).get('fast', -1),
                                       g.get(('scope-held-random', op), {}).get('calls', -1)) for op in HELPERS)), flush=True)
        # Mutants in the build with every form active. The float unit stays the same.
        for index, entry in enumerate(MUTANTS):
            mutant, header, edits, helpers, trees = edits_of(entry)
            if trees and kind not in trees:
                continue
            if only and mutant not in only:
                continue
            private = out / kind / ('%d-%s' % (index, mutant))
            (private / 'runtime/spu').mkdir(parents=True)
            for h in HEADERS:
                path = spu / h
                if not path.exists():
                    continue
                text = path.read_text(encoding='utf8')
                if h == header:
                    with_fnma = 'spu_sf_fast_fnma(__m128i a' in text
                    live = [e for e in edits if e[2] != 'fnma' or with_fnma]
                    for before, after, mark in live:
                        if text.count(before) != 1:
                            failures.append('%s: %s: %s holds the text %d times' % (kind, mutant, h, text.count(before)))
                    for before, after, mark in live:
                        text = text.replace(before, after)
                (private / 'runtime/spu' / h).write_text(text, encoding='utf8')
            name = '%s-mutant-%s' % (kind, mutant)
            defines = ['SPU_SIMD=1'] * (kind == 'vendor') + ['SPU_FLOAT_FAST_TREE_FORK'] * (kind == 'fork')
            drv_obj = compile(name + '-driver', FIXTURE, defines, True, '/O2', [private, root, inc, spu])
            p = measure(name, link(name, [drv_obj, float_obj]), True)
            bad = wrong_path(p['groups'], helpers) if p else {op: 0 for op in helpers}
            rejected = bool(p) and p['code'] == 1 and p['result'] == 'FAIL' and all(bad.values())
            mutants.append(dict(tree=kind, mutant=mutant, header=header, edits=edits, helpers=helpers,
                                mismatches=bad, returncode=p['code'] if p else None, result=p['result'] if p else None, rejected=rejected))
            if not rejected:
                failures.append('%s: mutant %s is not rejected: %s' % (kind, mutant, bad))
            print('%s mutant %-24s rejected=%s %s' % (kind, mutant, rejected, bad), flush=True)

    report = dict(builds=builds, mutants=mutants, compiler=cc, model_rows=rows_per_op, failures=failures, passed=not failures,
                  sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (FIXTURE, Path(__file__), ROOT / 'scripts/robbe_float_oracle.py')})
    (out / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    (out / 'commands.json').write_text(json.dumps(records, indent=2), encoding='utf8')
    for line in failures:
        print('FAIL ' + line)
    print('spu float fast: %s, %d builds, %d mutants, evidence %s' % (
        'PASS' if report['passed'] else 'FAIL', len(builds), len(mutants), out))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
