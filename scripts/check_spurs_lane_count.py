#!/usr/bin/env python3
"""Game-free checks for the SPURS lane count override (SPURS_LANES=N).

1. Audits the vendor copy and scripts/run.py: the override sits after the
   validity check of the value of the game and before the instance gets its
   count; the launcher sets the switch only with --spurs-lanes and records it.
   Mutants must fail.
2. Compiles the production header with an authored fixture: each kind of
   SPURS_LANES value gives the documented lane count. Mutants of the header
   must fail.
3. Compiles libs/spurs/cellSpurs.c with a syntax-only clang-cl pass.
No game input; no performance claim."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import project  # noqa: E402

ARGUMENT = ("ap.add_argument('--spurs-lanes',choices=('0','1','2','3','4','5','6'),default='0',")
POP = "env.pop('SPURS_LANES',None)"
SET = "if args.spurs_lanes!='0':env['SPURS_LANES']=args.spurs_lanes"
RECORD = "if 'SPURS_LANES' in env:record['environment']['SPURS_LANES']=env['SPURS_LANES']"

# Each text must occur in libs/spurs/cellSpurs.c exactly once, in this order.
WIRING = [
    '#include "spurs_lane_count.h"',
    '    if (!nspus || nspus > 6) return CELL_SPURS_CORE_ERROR_INVAL;',
    '    const uint32_t requested_lanes = nspus;',
    '    nspus = spurs_lane_count(nspus, getenv("SPURS_LANES"));',
    '    si->nspus = (nspus > 0 && nspus <= CELL_SPURS_MAX_SPU) ? nspus : 1;',
    'nSpus=%u requested=%u',
    'si->prefix, spurs_ea, si->nspus, requested_lanes);',
]
SOURCE_MUTANTS = [
    # (name, old, new)
    ("include-lost", '#include "spurs_lane_count.h"   /* SPURS_LANES: optional lane count override */\n', ""),
    ("override-lost", 'nspus = spurs_lane_count(nspus, getenv("SPURS_LANES"));\n', ""),
    ("override-before-validity-check",
     '    if (!nspus || nspus > 6) return CELL_SPURS_CORE_ERROR_INVAL;\n',
     '    nspus = spurs_lane_count(nspus, getenv("SPURS_LANES"));\n'
     '    if (!nspus || nspus > 6) return CELL_SPURS_CORE_ERROR_INVAL;\n'),
    ("count-written-first",
     '    nspus = spurs_lane_count(nspus, getenv("SPURS_LANES"));\n'
     '    si->nspus = (nspus > 0 && nspus <= CELL_SPURS_MAX_SPU) ? nspus : 1;\n',
     '    si->nspus = (nspus > 0 && nspus <= CELL_SPURS_MAX_SPU) ? nspus : 1;\n'
     '    nspus = spurs_lane_count(nspus, getenv("SPURS_LANES"));\n'),
    ("log-without-requested-count", "nSpus=%u requested=%u", "nSpus=%u"),
    ("log-prints-count-twice", "si->prefix, spurs_ea, si->nspus, requested_lanes);",
     "si->prefix, spurs_ea, si->nspus, si->nspus);"),
]
HEADER_MUTANTS = [
    ("accept-zero", "return n >= 1u && n <= SPURS_LANES_MAX ? n : requested;",
     "return n <= SPURS_LANES_MAX ? n : requested;"),
    ("accept-seven", "#define SPURS_LANES_MAX 6u", "#define SPURS_LANES_MAX 7u"),
    ("ignore-setting", "if (!setting || !*setting) return requested;", "return requested;"),
    ("no-guard-in-loop", "if (*p < '0' || *p > '9' || n > SPURS_LANES_MAX) return requested;",
     "if (*p < '0' || *p > '9') return requested;"),
    ("digit-off-by-one", "n = n * 10u + (uint32_t)(*p - '0');",
     "n = n * 10u + (uint32_t)(*p - '0' + 1);"),
    ("no-final-clamp", "return n >= 1u && n <= SPURS_LANES_MAX ? n : requested;", "return n ? n : requested;"),
]
LAUNCHER_MUTANTS = [
    ("argument-lost", ARGUMENT, "ap.add_argument('--spurs-lanes-unused',"),
    ("pop-lost", POP, ""),
    ("set-always", SET, "if True:env['SPURS_LANES']=args.spurs_lanes"),
    ("set-other-option", SET, "if args.spurs_kernel_notify=='1':env['SPURS_LANES']=args.spurs_lanes"),
    ("record-lost", RECORD, ""),
]
# (setting, requested) -> effective lane count. None = no setting.
CASES = [
    ((None, 5), 5), (("", 5), 5), (("6", 5), 6), (("4", 5), 4), (("1", 5), 1), (("06", 5), 6),
    (("6", 2), 6), (("0", 5), 5), (("7", 5), 5), (("12", 5), 5), (("x", 5), 5), (("5x", 5), 5),
    (("-1", 5), 5), (("+6", 5), 5), (("6 ", 5), 5), (("4294967297", 5), 5),
    (("99999999999999999999", 5), 5),
]

FIXTURE = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "spurs_lane_count.h"

int main(int argc, char **argv)
{
    if (argc != 3) return 2;
    const char *setting = strcmp(argv[1], "-") == 0 ? NULL : argv[1];
    printf("%u\n", spurs_lane_count((uint32_t)strtoul(argv[2], NULL, 10), setting));
    return 0;
}
'''


def audit(source, launcher):
    positions = []
    for needle in WIRING:
        assert source.count(needle) == 1, needle
        positions.append(source.index(needle))
    assert positions == sorted(positions), "wiring order"
    assert source.count('getenv("SPURS_LANES")') == 1
    for text, times in ((ARGUMENT, 1), (POP, 1), (SET, 1), (RECORD, 1)):
        assert launcher.count(text) == times, text
    assert "choices=('0','1','2','3','4','5','6')" in launcher


def rejects(callable_, *args):
    try:
        callable_(*args)
    except AssertionError:
        return True
    return False


def compiler_command(environment, include_dir, fixture, exe):
    compiler = environment["MV_CLANG"]
    if Path(compiler).name.lower() in ("cl", "cl.exe", "clang-cl", "clang-cl.exe"):
        return [compiler, "/nologo", "/O2", "/clang:-Wno-everything", "/I" + str(include_dir),
                str(fixture), "/Fe" + str(exe)]
    return [compiler, "-std=c11", "-O2", "-Wno-everything", "-I" + str(include_dir), str(fixture),
            "-o", str(exe)]


def build(environment, header_text, work, tag):
    include_dir = work / (tag + "-include")
    include_dir.mkdir()
    (include_dir / "spurs_lane_count.h").write_text(header_text)
    fixture = work / (tag + "-fixture.c")
    fixture.write_text(FIXTURE)
    exe = include_dir / ("lanes.exe" if sys.platform == "win32" else "lanes")
    result = subprocess.run(compiler_command(environment, include_dir, fixture, exe), cwd=ROOT,
                            capture_output=True, text=True, errors="replace", timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    return exe


def verify(exe):
    for (setting, requested), expected in CASES:
        result = subprocess.run([str(exe), "-" if setting is None else setting, str(requested)],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        got = int(result.stdout.strip())
        assert got == expected, f"{setting!r} {requested}: {got}, expected {expected}"


def syntax_only(environment, path):
    command = [environment["MV_CLANG"], "/nologo", "/Zs", "/std:c11", "/experimental:c11atomics",
               "/clang:-std=c17", "/D_CRT_SECURE_NO_WARNINGS", "/clang:-Wno-everything"]
    command += ["/I" + str(path.parents[2] / part)
                for part in ("include", "libs/video", "runtime/ppu", "runtime/spu", "runtime/memory",
                             "runtime/syscalls", "runtime/platform")]
    command.append(str(path.resolve()))
    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True,
                            errors="replace", timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", type=Path, default=ROOT / "vendor/ps3recomp")
    parser.add_argument("--launcher", type=Path, default=ROOT / "scripts/run.py")
    args = parser.parse_args()
    spurs = args.vendor / "libs/spurs"
    source = (spurs / "cellSpurs.c").read_text()
    header = (spurs / "spurs_lane_count.h").read_bytes().decode("utf-8")
    launcher = args.launcher.read_text()
    environment = project.build_environment()

    audit(source, launcher)
    for name, old, new in SOURCE_MUTANTS:
        assert source.count(old) == 1, name
        assert rejects(audit, source.replace(old, new), launcher), name
    for name, old, new in LAUNCHER_MUTANTS:
        assert launcher.count(old) == 1, name
        assert rejects(audit, source, launcher.replace(old, new)), name

    with tempfile.TemporaryDirectory(prefix="spurs-lane-count-") as directory:
        work = Path(directory)
        verify(build(environment, header, work, "production"))
        for name, old, new in HEADER_MUTANTS:
            assert header.count(old) == 1, name
            mutant = build(environment, header.replace(old, new), work, "mutant-" + name)
            assert rejects(verify, mutant), name

    syntax_only(environment, spurs / "cellSpurs.c")
    print(f"PASS: {len(CASES)} lane count cases, {len(SOURCE_MUTANTS)} source mutants, "
          f"{len(LAUNCHER_MUTANTS)} launcher mutants, {len(HEADER_MUTANTS)} header mutants, "
          "syntax-only cellSpurs.c")


if __name__ == "__main__":
    main()
