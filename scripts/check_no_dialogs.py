#!/usr/bin/env python3
"""Keep the dialogs of a diagnostic build off the desktop.

1. Audits src/main.cpp and src/motorstorm/no_dialogs.h: main calls
   motorstorm::no_dialogs() before its first library call; the debug CRT
   writes each report to stderr; Windows Error Reporting gets no dialog.
   Mutants of both texts must fail.
2. Compiles scripts/fixtures/no_dialogs_fixture.cpp with the debug CRT (the
   runtime library of the game) and runs it through scripts/quiet_run.py on a
   private desktop:
   - without no_dialogs(): a message box, an assertion and an invalid CRT
     parameter each block the program. The window is on the private desktop and
     not on the desktop of the caller. The time limit ends the program (124).
   - with no_dialogs(): the assertion text and the heap corruption text are on
     stderr and the program runs to its end; the invalid parameter ends the
     program with an error code. No run blocks.
   Mutants of the header must fail.
No game input; no performance claim."""
import argparse
import ast
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import project  # noqa: E402

HEADER = ROOT / "src/motorstorm/no_dialogs.h"
MAIN = ROOT / "src/main.cpp"
QUIET_RUN = ROOT / "scripts/quiet_run.py"
FIXTURE = ROOT / "scripts/fixtures/no_dialogs_fixture.cpp"

CALL = "    motorstorm::no_dialogs();\n"
FIRST_LIBRARY_CALL = "    timeBeginPeriod(1);\n"
CRT_DIALOG = "Microsoft Visual C++ Runtime Library"
PROBE_TITLE = "MOTORSTORM_QUIET_RUN_PROBE_TITLE"
TIMEOUT = 4                 # seconds: a blocked fixture run ends after this time
EXIT_TIMEOUT = 124          # scripts/quiet_run.py
END = "fixture: %s end"
EXIT_END = 4                 # the exit code of the fixture at its end

# Each text must occur exactly count times.
MAIN_WIRING = [
    ('#include "motorstorm/no_dialogs.h"', 1),
    (CALL, 1),
]
HEADER_WIRING = [
    ('#if defined(_DEBUG)\n', 1),
    ('    _CrtSetReportMode(_CRT_WARN, _CRTDBG_MODE_FILE);\n', 1),
    ('    _CrtSetReportFile(_CRT_WARN, _CRTDBG_FILE_STDERR);\n', 1),
    ('    _CrtSetReportMode(_CRT_ERROR, _CRTDBG_MODE_FILE);\n', 1),
    ('    _CrtSetReportFile(_CRT_ERROR, _CRTDBG_FILE_STDERR);\n', 1),
    ('    _CrtSetReportMode(_CRT_ASSERT, _CRTDBG_MODE_FILE);\n', 1),
    ('    _CrtSetReportFile(_CRT_ASSERT, _CRTDBG_FILE_STDERR);\n', 1),
    ('    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);\n', 1),
]
# name, replacements [(text, replacement)], the fixture run that must fail
HEADER_MUTANTS = [
    ('assert-report-keeps-dialog', [('    _CrtSetReportMode(_CRT_ASSERT, _CRTDBG_MODE_FILE);\n', '')],
     'assert'),
    ('assert-report-not-on-stderr', [('    _CrtSetReportFile(_CRT_ASSERT, _CRTDBG_FILE_STDERR);\n', '')],
     'assert'),
    ('error-report-not-on-stderr', [('    _CrtSetReportMode(_CRT_ERROR, _CRTDBG_MODE_FILE);\n', '')], 'heap'),
]
# name, replacements [(text, replacement)]; the audit must reject each one
MAIN_MUTANTS = [
    ('not-called', [(CALL, '')]),
    ('called-after-first-library-call',
     [(CALL, ''),
      (FIRST_LIBRARY_CALL, FIRST_LIBRARY_CALL + CALL)]),
]


def audit(main_text, header_text):
    """Raise AssertionError when main or the header breaks one rule."""
    for text, count in MAIN_WIRING:
        assert main_text.count(text) == count, (count, main_text.count(text), text)
    assert main_text.index("int main(") < main_text.index(CALL) < main_text.index(FIRST_LIBRARY_CALL), \
        "no_dialogs() must run before the first library call of main"
    for text, count in HEADER_WIRING:
        assert header_text.count(text) == count, (count, header_text.count(text), text)


def build(environment, work, include_first, source=FIXTURE):
    """Compile the fixture with the debug CRT. Return the executable."""
    work.mkdir(parents=True, exist_ok=True)
    exe = work / "fixture.exe"
    command = [environment["MV_CLANG"], "/nologo", "/std:c++17", "/MDd", "/Od", "/EHsc",
               "/D_CRT_SECURE_NO_WARNINGS", "/I" + str(include_first), "/I" + str(ROOT / "src"),
               str(source), "user32.lib", "/Fo" + str(work) + os.sep, "/Fe" + str(exe)]
    result = subprocess.run(command, cwd=work, env=environment, capture_output=True, text=True,
                            errors="replace", timeout=300)
    (work / "build.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    return exe


def run(exe, mode, quiet):
    """Return (exit code, stdout, stderr, windows) of one fixture run on a private desktop.

    `windows` is None when the program ended by itself, else (titles on the private desktop,
    titles on the desktop of the caller), read while the program was blocked.
    """
    command = [sys.executable, str(QUIET_RUN), "--timeout", str(TIMEOUT), "--", str(exe), mode]
    if quiet:
        command.append("quiet")
    result = subprocess.run(command, capture_output=True, text=True, errors="replace",
                            timeout=TIMEOUT + 120)
    windows = None
    match = re.search(r"Windows on its desktop: (.*); on the desktop of the caller: (.*)", result.stderr)
    if match:
        windows = (ast.literal_eval(match.group(1)), ast.literal_eval(match.group(2)))
    return result.returncode, result.stdout, result.stderr, windows


def quiet_ok(mode, code, stdout, stderr, windows):
    """Return True when the fixture run with no_dialogs() obeys the rule of `mode`."""
    if code == EXIT_TIMEOUT or windows is not None:
        return False
    if mode == "assert":
        return END % mode in stdout and "Assertion failed: mode == nullptr" in stderr
    if mode == "param":
        return code != 0 and "stream.valid()" in stderr and END % mode not in stdout
    if mode == "heap":
        return code == EXIT_END and "HEAP CORRUPTION DETECTED" in stderr
    raise ValueError(mode)


def verify(exe):
    """Raise AssertionError when the fixture breaks one rule."""
    blocked = {"box": PROBE_TITLE, "assert": CRT_DIALOG, "param": CRT_DIALOG}
    for mode, title in blocked.items():
        # Without no_dialogs(): the report blocks the program; its window stays on the private desktop.
        code, stdout, stderr, windows = run(exe, mode, quiet=False)
        assert code == EXIT_TIMEOUT and windows is not None, (mode, code, windows, stderr[-1500:])
        assert any(title in item for item in windows[0]), (mode, windows)
        assert not any(CRT_DIALOG in item or PROBE_TITLE in item for item in windows[1]), (mode, windows)
        assert END % mode not in stdout, mode
    # With no_dialogs(): no run blocks; the rule of each mode is in quiet_ok.
    for mode in ("assert", "param", "heap"):
        code, stdout, stderr, windows = run(exe, mode, quiet=True)
        assert quiet_ok(mode, code, stdout, stderr, windows), \
            (mode, code, windows, stdout, stderr[-1500:])


def verify_mutants(environment, directory):
    """Compile one fixture per header mutant. Each named run must fail its rule."""
    for name, replacements, mode in HEADER_MUTANTS:
        text = HEADER.read_text().replace("\r\n", "\n")
        for old, new in replacements:
            assert text.count(old) == 1, (name, old)
            text = text.replace(old, new)
        work = directory / name
        (work / "src/motorstorm").mkdir(parents=True, exist_ok=True)
        (work / "src/motorstorm/no_dialogs.h").write_text(text)
        exe = build(environment, work, work / "src")
        code, stdout, stderr, windows = run(exe, mode, quiet=True)
        assert not quiet_ok(mode, code, stdout, stderr, windows), \
            "mutant accepted: %s (code %s, windows %r)" % (name, code, windows)
        print("rejected header mutant: %s (code %s)" % (name, code))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--header", type=Path, default=HEADER)
    parser.add_argument("--main", type=Path, default=MAIN)
    parser.add_argument("--no-mutants", action="store_true", help="run the audit and the fixture only")
    args = parser.parse_args()
    main_text = args.main.read_text().replace("\r\n", "\n")
    header_text = args.header.read_text().replace("\r\n", "\n")
    audit(main_text, header_text)
    if not args.no_mutants:
        for name, replacements in MAIN_MUTANTS:
            text = main_text
            for old, new in replacements:
                assert text.count(old) == 1, (name, old)
                text = text.replace(old, new)
            try:
                audit(text, header_text)
            except AssertionError:
                print("rejected main mutant: %s" % name)
            else:
                raise AssertionError("mutant accepted: %s" % name)
    environment = project.build_environment()
    with tempfile.TemporaryDirectory(prefix="no-dialogs-") as name:
        directory = Path(name)
        exe = build(environment, directory / "fixture", ROOT / "src")
        verify(exe)
        if not args.no_mutants:
            verify_mutants(environment, directory / "mutants")
    print("PASS no dialogs: the game writes its CRT reports to stderr and makes no error report box; "
          "a dialog of a test program stays on the private desktop of scripts/quiet_run.py; "
          "%d main and %d header mutants rejected" % (0 if args.no_mutants else len(MAIN_MUTANTS),
                                                     0 if args.no_mutants else len(HEADER_MUTANTS)))


if __name__ == "__main__":
    main()
