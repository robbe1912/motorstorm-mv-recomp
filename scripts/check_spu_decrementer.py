#!/usr/bin/env python3
"""Check the production RdDec case against arbitrary-precision time arithmetic."""
import argparse
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    if os.name == 'nt':
        from project import build_environment
        os.environ.update(build_environment())
    runtime = root / 'runtime/spu/spu_channels.c'
    if not runtime.exists():
        runtime = root / 'vendor/ps3recomp/runtime/spu/spu_channels.c'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=runtime)
    args = parser.parse_args()
    source = args.source.read_text()
    marker = 'case SPU_RdDec: {'
    assert source.count(marker) == 1, 'Expected one production decrementer case'
    case = marker + source.split(marker)[1].split('\n    case ', 1)[0]
    rate = next(line for line in source.splitlines() if line.startswith('#define SPU_DECREMENTER_HZ'))
    driver = r'''
#include <stdint.h>
#include <stdio.h>
#include <inttypes.h>
typedef struct { uint32_t decrementer; uint64_t dec_base_ns; } timer;
static uint64_t now_ns;
static uint64_t spu_host_ns(void) { return now_ns; }
#define SPU_RdDec 8
RATE
static uint32_t read_timer(timer* ctx) {
    uint32_t v = 0;
    switch (SPU_RdDec) { CASE }
    return v;
}
int main(void) {
    timer ctx;
    while (scanf("%" SCNu32 " %" SCNu64 " %" SCNu64,
                 &ctx.decrementer, &ctx.dec_base_ns, &now_ns) == 3) {
        uint32_t value = read_timer(&ctx);
        printf("%" PRIu32 " %" PRIu64 "\n", value, ctx.dec_base_ns);
    }
    return ferror(stdin) ? 1 : 0;
}
'''.replace('RATE', rate).replace('CASE', case)
    u32, u64 = (1 << 32) - 1, (1 << 64) - 1
    first_overflow = u64 // 79_800_000
    elapsed = [0, 1, 12, 13, 999_999_999, 1_000_000_000,
               first_overflow - 1, first_overflow, first_overflow + 1,
               232_000_000_000, 354_000_000_000, 462_000_000_000,
               1_000_000_000_000, u64 - 1, u64]
    rng = random.Random(168)
    elapsed += [rng.getrandbits(64) for _ in range(512)]
    cases = [(reload, 1, (1 + ns) & u64)
             for ns in elapsed for reload in (0, 1, 0x80000000, u32)]
    cases += [(reload, 0, now) for reload in (0, 1, u32)
              for now in (1, 1_000_000_000, u64)]
    compiler = (os.environ.get('MV_CLANG') or os.environ.get('CC') or
                shutil.which('clang-cl' if os.name == 'nt' else 'cc'))
    if not compiler:
        raise RuntimeError('C compiler required for production-case regression')
    with tempfile.TemporaryDirectory() as temporary:
        out = Path(temporary)
        src = out / 'decrementer.c'
        src.write_text(driver)
        binary = out / ('test.exe' if os.name == 'nt' else 'test')
        if os.name == 'nt':
            command = [compiler, '/nologo', '/TC', '/O2', '/UNDEBUG',
                       '/D_CRT_SECURE_NO_WARNINGS', str(src), '/Fe:' + str(binary)]
        else:
            command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra',
                       '-Werror', str(src), '-o', str(binary)]
        subprocess.run(command, cwd=out, check=True, capture_output=True, text=True)
        inputs = ''.join(f'{reload} {base} {now}\n' for reload, base, now in cases)
        result = subprocess.run([str(binary)], input=inputs, capture_output=True,
                                text=True, check=True, timeout=15)
    rows = result.stdout.splitlines()
    assert len(rows) == len(cases), 'Missing production-case results'
    failures = []
    for (reload, base, now), row in zip(cases, rows):
        # Python integers do not overflow; only the final hardware counter wraps.
        active_base = base if base else now
        ns = (now - active_base) & u64
        expected = (reload - ns * 79_800_000 // 1_000_000_000) & u32
        actual, actual_base = map(int, row.split())
        if (actual, actual_base) != (expected, active_base):
            failures.append((ns, reload, actual, expected))
    print(f'RdDec production case: {len(cases) - len(failures)} pass, {len(failures)} fail')
    for failure in failures[:5]:
        print('elapsed_ns=%d reload=%d actual=%d expected=%d' % failure)
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
