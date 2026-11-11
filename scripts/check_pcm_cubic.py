"""Authored rational oracle and FP/transaction controls for native PCM DSP."""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import itertools
import json
import os
import random
import shutil
import struct
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'temp/checks' / ('pcm-cubic-' + str(time.time_ns()))
OUT.mkdir(parents=True)
report = {'qualification': 'Authored typed DSP controls, not original-job or native-game acceptance.', 'commands': [], 'runs': []}


def bits(f): return struct.unpack('<I', struct.pack('<f', f))[0]
def value(b):
    exponent = (b >> 23) & 255
    if not exponent: return F(0)
    assert exponent < 255
    return (-1 if b >> 31 else 1) * F((b & 0x7fffff) | 0x800000) * F(2) ** (exponent - 150)


def rounded(x):
    if not x: return 0
    sign = 0x80000000 if x < 0 else 0
    x = abs(x)
    exponent = x.numerator.bit_length() - x.denominator.bit_length()
    if x < F(2) ** exponent: exponent -= 1
    if exponent < -126: return 0
    assert exponent <= 127, 'oracle corpus exceeds admitted range'
    significand = int(x / (F(2) ** (exponent - 23)))
    return sign | ((exponent + 127) << 23) | (significand - 0x800000)


def add(a, b): return rounded(value(a) + value(b))
def sub(a, b): return rounded(value(a) - value(b))
def mul(a, b): return rounded(value(a) * value(b))
def fma(a, b, c): return rounded(value(a) * value(b) + value(c))


def oracle(pcm, state, count):
    positions, step = state[:16], state[16:]
    result = []
    half = bits(.5)
    for block in range(count // 16):
        for p in positions:
            i = int(value(p)); t = sub(p, rounded(F(i)))
            a, b, c, d = [rounded(F(pcm[i + k], 32768)) for k in range(4)]
            tangent = mul(sub(c, a), half)
            difference = sub(b, c)
            first = add(tangent, difference)
            cubic = fma(sub(d, b), half, add(difference, first))
            quadratic = add(first, cubic)
            nested = rounded(value(t) * value(cubic) - value(quadratic))
            result.append(fma(t, fma(t, nested, tangent), b))
        last = positions[12:]
        positions = []
        for group in range(4):
            last = [add(p, s) for p, s in zip(last, step)]
            positions.extend(last)
    return positions + step, result


def command(args, env):
    p = subprocess.run(list(map(str, args)), env=env, capture_output=True, text=True, timeout=90)
    report['commands'].append({'argv': list(map(str, args)), 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
    (OUT/'result.json').write_text(json.dumps(report, indent=2))
    assert p.returncode == 0, f'Command failed; see {OUT / "result.json"}'


def build(core, label):
    folder = OUT / label; folder.mkdir()
    sources = [ROOT/'scripts/fixtures/pcm_cubic.cpp', ROOT/'src/motorstorm/native_cpu.cpp', core]
    objects = []
    for n, source in enumerate(sources):
        obj = folder / (str(n) + ('.obj' if os.name == 'nt' else '.o')); objects.append(obj)
        if os.name == 'nt':
            cmd = [CC, '/nologo', '/std:c++20', '/EHsc', '/O2', '/MDd', '/UNDEBUG', '/I'+str(ROOT/'src/motorstorm'), '/clang:-ffp-contract=off', '/clang:-fno-strict-aliasing', '/c', source, '/Fo'+str(obj)]
            if n == 2: cmd += ['/clang:-mavx2', '/clang:-mfma']
        else:
            cmd = [CC, '-std=c++20', '-O2', '-UNDEBUG', '-frounding-math', '-ffp-contract=off', '-fno-strict-aliasing', '-I'+str(ROOT/'src/motorstorm'), '-c', source, '-o', obj]
            if n == 2: cmd += ['-mavx2', '-mfma']
        command(cmd, ENV)
    exe = folder / ('test.exe' if os.name == 'nt' else 'test')
    command([CC, *objects, '/MDd', '/Fe'+str(exe)] if os.name == 'nt' else [CC, *objects, '-o', exe], ENV)
    return exe


ENV = dict(os.environ)
if os.name == 'nt':
    from project import build_environment
    ENV = build_environment(); CC = ENV['MV_CLANG']
else: CC = shutil.which('c++')
assert CC
core = ROOT/'src/motorstorm/pcm_cubic.cpp'
report['sources'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [core, core.with_suffix('.h'), ROOT/'scripts/fixtures/pcm_cubic.cpp']}
native = build(core, 'native')
mutant = OUT/'mutant.cpp'
text = core.read_text(); old = 'canonical(_mm_fmadd_ps(a, b, c))'
assert text.count(old) == 1
mutant.write_text(text.replace(old, 'canonical(_mm_add_ps(_mm_mul_ps(a, b), c))'))
wrong = build(mutant, 'unfused')
rng = random.Random(288)
pcm = [rng.randrange(-32768, 32768) for _ in range(4096)]
cases = []
for seed in range(10):
    state = [bits(rng.uniform(2, 256)) for _ in range(16)] + [bits(s) for s in (.25, .5, 1., 2.)]
    cases.append(('random'+str(seed), state, 256, 0, pcm))
cases += [('zeros', [0]*20, 64, 0, [0]*4096), ('negative-zero', [0x80000000]*20, 16, 0, pcm),
          ('subnormal', [1]*20, 16, 0, pcm), ('empty', [0]*20, 0, 0, pcm)]
valid = [bits(4)]*16 + [bits(1)]*4
for name, state, count, flags, source in [
    ('nan', [0x7fc00001]+valid[1:], 16, 1, pcm),
    ('infinity-step', valid[:16]+[0x7f800000]*4, 16, 1, pcm),
    ('negative-position', [bits(-1)]+valid[1:], 16, 1, pcm),
    ('late-failure', valid[:16]+[bits(2048)]*4, 32, 1, pcm),
    ('output-alias-state', valid, 16, 3, pcm),
    ('output-alias-pcm', valid, 16, 5, pcm),
    ('short-source', [0]*20, 16, 1, pcm[:3]),
    ('partial-group', valid, 17, 1, pcm)]: cases.append((name, state, count, flags, source))

mutant_differences = 0
for n, (name, state, count, flags, source) in enumerate(cases):
    path = OUT/(name+'.bin')
    path.write_bytes(struct.pack('<III20I', len(source), count, flags, *state) + struct.pack('<'+'h'*len(source), *source))
    expected_state, expected_output = (state, [0xcdcdcdcd]*count) if flags else oracle(source, state, count)
    expected = struct.pack('<'+'I'*(21+count), bool(flags), *expected_state, *expected_output)
    for rounding, flush in itertools.product((0, 0x2000, 0x4000, 0x6000), (0, 0x40, 0x8000, 0x8040)):
        out = OUT/'output.bin'; csr = rounding | flush | 0x3f
        command([native, path, out, hex(csr)], ENV)
        assert out.read_bytes() == expected, f'{name} disagrees with rational oracle at MXCSR {csr:X}'
        report['runs'].append({'case': name, 'mxcsr': csr, 'matched': True})
    if not flags and count:
        out = OUT/'mutant-output.bin'; command([wrong, path, out, '0'], ENV)
        mutant_differences += out.read_bytes() != expected
assert mutant_differences, 'Unfused arithmetic mutant escaped'
report['mutant_differences'] = mutant_differences
(OUT/'result.json').write_text(json.dumps(report, indent=2))
print(f'PASS {len(cases)} authored cases x16 caller FP modes; unfused mutant rejected in {mutant_differences} cases; no game/performance claim')
