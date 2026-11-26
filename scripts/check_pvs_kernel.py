"""Checks the native kernel of the PVS job (SPU image 210, jobmod_056ac0eea1a6_e12270) against the
lifted code, pair for pair.

The kernel (src/motorstorm/pvs_kernel.c, made by temp/pvskernel/p5_gen.py) holds the portable
lifted functions of the job main. A pair is the state of the context when the lifted drain
dispatches the entry (0x4030) and the state when the job main returns. The pairs come from the
replay of the dumped jobs (temp/jobdump/pvs-race) on the lifted code.

For each pair the check puts the entry state into the context and calls the bound entry (the
wrapper that scripts/native_game_binding.py makes) with mode native. The context after the call
must equal the exit state of the pair: the whole spu_context outside the pointer ls and the
counter steps, the whole local store, the DMA records and the exit kind.

The check then runs five mutants of the kernel. Each mutant must change the result of every pair
of a sample of 24 jobs: a wrong resume address, a dropped store, a second run of a step, a
skipped epilogue and a missing write of the interrupt state.

The work is in temp/pvskernel/k5_build.py (engines under temp/pvskernel/build). The check needs
local inputs: config/local.json (key elf), the generated lifted unit, the runtime objects of
temp/pvs/p2_build and the dumped jobs. Windows with clang-cl only.

Usage: python scripts/check_pvs_kernel.py [--jobs N] [--chunk N] [--parallel N] [--build]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'temp/pvskernel'))
import k5_build  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--jobs', type=int, default=100000, help='number of complete jobs (default: all)')
    parser.add_argument('--chunk', type=int, default=25, help='jobs per engine process')
    parser.add_argument('--parallel', type=int, default=3)
    parser.add_argument('--build', action='store_true', help='compile the engines before the check')
    args = parser.parse_args(argv)
    k5_build.generate()
    engines = ROOT / 'temp/pvskernel/build'
    if args.build or not all((engines / name / (name + '.exe')).exists() for name in ('check', *[('check-' + m) for m in k5_build.MUTANTS])):
        args.engines, args.force = 'check,mutants', ''
        k5_build.build(args)
    ok = k5_build.pairs(args)
    print('PVS_KERNEL_CHECK', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
