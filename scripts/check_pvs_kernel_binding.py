"""Checks the build-time binding of the native kernel of the PVS job through the real lifted entry
of SPU image 210 (jobmod_056ac0eea1a6_e12270).

scripts/native_game_binding.py renames the lifted function jobmod_056ac0eea1a6_e12270_spu_func_00004030
to game_original_pvs_4030. The lifted name becomes a wrapper of motorstorm_pvs_entry_00004030.
This check applies the same script, with the contract of the visibility batch and the contract of
the kernel entry, to the generated unit on a private tree. It compiles the unit with the SPU
runtime, the adapter, the kernel and the visibility batch (the engines of temp/pvskernel/k5_build.py).

It replays the complete dumped jobs (temp/jobdump/pvs-race) from the entry of the job to its
return address. The replay engine compares every job with its dump: exit points, DMA records,
PUT bytes, guest memory and the local store. It runs two modes:
  mode native: the kernel runs. Native runs must be more than 0. Every job must equal its dump.
  mode shadow: the kernel and the lifted code run on two copies of the context up to the return
               address of the drain. A difference stops the program. Shadow comparisons must be
               more than 0. Every job must equal its dump.

The check needs local inputs: config/local.json (key elf), the generated lifted unit, the runtime
objects of temp/pvs/p2_build and the dumped jobs. Windows with clang-cl only.

Usage: python scripts/check_pvs_kernel_binding.py [--jobs N] [--chunk N] [--parallel N] [--build]
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
    parser.add_argument('--build', action='store_true', help='compile the engine before the check')
    args = parser.parse_args(argv)
    k5_build.generate()
    engine = ROOT / 'temp/pvskernel/build/check/check.exe'
    if args.build or not engine.exists():
        args.engines, args.force = 'check', ''
        k5_build.build(args)
    ok = k5_build.binding(args)
    print('PVS_KERNEL_BINDING_CHECK', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
