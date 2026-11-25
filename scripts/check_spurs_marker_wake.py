#!/usr/bin/env python3
"""Game-free checks for the marker wake (SPURS_MARKER_WAKE=1).

1. Audits the vendor copy, scripts/run.py and the job wait adapter: the runtime
   calls the host line commit hook after each committing PUTLLC and PUTLLUC,
   outside the line lock; the launcher sets the switch only with
   --spurs-marker-wake 1 and records it; the adapter installs the hook with the
   switch. Mutants must fail.
2. Compiles the production adapter in its Windows build with an authored fixture
   and a stand-in lift header: a commit on the waited job list line ends the
   wait at once, a commit during a poll does not make the next wait rest on the
   fallback time, the fallback time ends a wait without a commit, and nothing
   is installed without the switch. Mutants of the adapter must fail.
3. Compiles runtime/spu/spu_channels.c with a syntax-only clang-cl pass.
No game input; no performance claim."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import project  # noqa: E402

SWITCH = "SPURS_MARKER_WAKE"
ARGUMENT = "ap.add_argument('--spurs-marker-wake',"
POP = "env.pop('SPURS_MARKER_WAKE',None)"
SET = "if args.spurs_marker_wake=='1':env['SPURS_MARKER_WAKE']='1'"
RECORD = "if 'SPURS_MARKER_WAKE' in env:record['environment']['SPURS_MARKER_WAKE']=env['SPURS_MARKER_WAKE']"

PREFIX = "[job_marker_wake] "
OFF_VALUES = [None, "0"]
BAD_VALUES = ["true", "11", "1 ", "on"]   # not 0 or 1: a visible error
ON_VALUE = "1"
# The fixture compiles with a fallback time of 200 ms: a lost wake is a wait of 200 ms.
FALLBACK = 200
PROMPT = 150            # ms: a wait that a wake ends
LATE = 150              # ms: the fallback time started

# Each text must occur in runtime/spu/spu_channels.c exactly count times.
WIRING = [
    ('#include "ps3emu/spu_host_line_commit.h"\n', 1),
    ('void (*g_spu_host_line_commit_hook)(uint32_t line) = 0;\n', 1),
    ('        if (ctx->atomic_stat == 0 && g_spu_host_line_commit_hook) g_spu_host_line_commit_hook(ea & ~127u);\n', 1),
    ('        if (g_spu_line_commit_hook) g_spu_line_commit_hook(ea & ~127u);\n'
     '        if (g_spu_host_line_commit_hook) g_spu_host_line_commit_hook(ea & ~127u);\n', 1),
    ('g_spu_host_line_commit_hook(ea & ~127u);', 2),
]
SOURCE_MUTANTS = [
    # name, text in runtime/spu/spu_channels.c, replacement
    ('hook-not-defined', 'void (*g_spu_host_line_commit_hook)(uint32_t line) = 0;\n', ''),
    ('hook-header-not-included', '#include "ps3emu/spu_host_line_commit.h"\n', ''),
    ('hook-not-called-after-putllc',
     '        if (ctx->atomic_stat == 0 && g_spu_host_line_commit_hook) g_spu_host_line_commit_hook(ea & ~127u);\n', ''),
    ('hook-not-called-after-putlluc',
     '        if (g_spu_line_commit_hook) g_spu_line_commit_hook(ea & ~127u);\n'
     '        if (g_spu_host_line_commit_hook) g_spu_host_line_commit_hook(ea & ~127u);\n',
     '        if (g_spu_line_commit_hook) g_spu_line_commit_hook(ea & ~127u);\n'),
    ('hook-called-on-failed-putllc',
     'if (ctx->atomic_stat == 0 && g_spu_host_line_commit_hook) g_spu_host_line_commit_hook',
     'if (g_spu_host_line_commit_hook) g_spu_host_line_commit_hook(ea & ~127u); if (0) 0'),
]
ADAPTER_WIRING = [
    ('#ifndef MOTORSTORM_JOB_WAIT_FIXTURE\n'
     '#include "ps3emu/spu_host_line_commit.h"   // SPURS_MARKER_WAKE=1: each commit of a guest line\n'
     '#endif\n', 1),
    # An auto-reset event: each wake ends one wait.
    ('HANDLE const marker_wake_event = CreateEventW(nullptr, FALSE, FALSE, nullptr);\n', 1),
    # Only a commit on a line of the waited job list wakes the wait.
    ('    if (!first || number < first || number > marker_wake_last.load(std::memory_order_relaxed)) return;\n', 1),
    # The wait flags itself, then tests the count again: a commit in between is not lost.
    ('    marker_wake_waiting.store(true, std::memory_order_release);\n', 1),
    ('    if (marker_wake_generation.load(std::memory_order_acquire) != seen) {\n', 1),
    ('    const DWORD wait = WaitForMultipleObjects(2, handles, FALSE, INFINITE);\n', 1),
    # No WaitOnAddress or WakeByAddressAll: they need a library that the game does not link.
    ('WaitOnAddress', 0),
    ('WakeByAddress', 0),
]
ADAPTER_AUDIT_MUTANTS = [
    # name, text in the adapter, replacement; the audit must reject each one
    ('wake-on-any-line',
     '    if (!first || number < first || number > marker_wake_last.load(std::memory_order_relaxed)) return;\n',
     '    if (!first) return;\n'),
    ('event-is-manual-reset', 'HANDLE const marker_wake_event = CreateEventW(nullptr, FALSE, FALSE, nullptr);\n',
     'HANDLE const marker_wake_event = CreateEventW(nullptr, TRUE, FALSE, nullptr);\n'),
]
ADAPTER_MUTANTS = [
    # name, text in the adapter, replacement; the fixture must reject each one
    ('hook-not-installed',
     '    MarkerWakeRegistration() { if (marker_wake_on()) g_spu_host_line_commit_hook = &marker_wake_commit; }\n',
     '    MarkerWakeRegistration() {}\n'),
    ('hook-installed-without-switch',
     'if (marker_wake_on()) g_spu_host_line_commit_hook = &marker_wake_commit;',
     'g_spu_host_line_commit_hook = &marker_wake_commit;'),
    ('switch-any-value', '        return mode && !std::strcmp(mode, "1");\n', '        return mode != nullptr;\n'),
    ('switch-always-off', '        return mode && !std::strcmp(mode, "1");\n', '        return false;\n'),
    ('wake-not-signaled', '    if (marker_wake_waiting.load(std::memory_order_acquire)) SetEvent(marker_wake_event);\n', ''),
    ('wait-does-not-flag', '    marker_wake_waiting.store(true, std::memory_order_release);\n', ''),
    ('commit-not-counted', '    marker_wake_generation.fetch_add(1, std::memory_order_release);\n', ''),
    ('commit-during-poll-waits', '    if (now != seen) { seen = now; return; }\n', '    seen = now;\n'),
    ('waited-lines-not-set',
     '    if (marker_wake_on()) {\n        marker_wake_last.store((owner + 31) >> 7, std::memory_order_release);\n',
     '    if (false) {\n        marker_wake_last.store((owner + 31) >> 7, std::memory_order_release);\n'),
    ('wait-ignores-switch', '    if (marker_wake_on()) { marker_wake_wait(timer.handle); return; }\n',
     '    { marker_wake_wait(timer.handle); return; }\n'),
    ('fallback-missing',
     '    const DWORD wait = WaitForMultipleObjects(2, handles, FALSE, INFINITE);\n',
     '    const DWORD wait = WaitForSingleObject(marker_wake_event, INFINITE);\n'),
    ('fallback-too-long', '    due.QuadPart = -10000LL * MOTORSTORM_JOB_WAIT_WAKE_FALLBACK_MS;',
     '    due.QuadPart = -10000LL * 10 * MOTORSTORM_JOB_WAIT_WAKE_FALLBACK_MS;'),
]


def audit(channels, launcher, adapter):
    """Raise AssertionError when the hook, the launcher or the adapter is not wired."""
    for text in (ARGUMENT, POP, SET, RECORD):
        assert launcher.count(text) == 1, "the launcher has one line: " + text
    assert launcher.index(POP) < launcher.index(SET) < launcher.index(RECORD), "the launcher clears, sets, records"
    for text, count in WIRING:
        assert channels.count(text) == count, (count, channels.count(text), text[:70])
    # Each call of the hook comes after the release of the line lock of its command.
    for call in ("if (ctx->atomic_stat == 0 && g_spu_host_line_commit_hook) g_spu_host_line_commit_hook",
                 "if (g_spu_host_line_commit_hook) g_spu_host_line_commit_hook"):
        end = channels.index(call)
        assert channels.rfind("spu_lockline_lock();", 0, end) < channels.rfind("spu_lockline_unlock();", 0, end), call
    for text, count in ADAPTER_WIRING:
        assert adapter.count(text) == count, (count, adapter.count(text), text[:70])


def build(environment, work, adapter, fixture, vendor_include=True):
    """Compile `adapter` (its Windows build) with the fixture. Return the executable."""
    work.mkdir(parents=True, exist_ok=True)
    source = work / "job_wait_adapter.cpp"
    source.write_text(adapter)
    # The adapter registers the wait priority callback of the runtime: the fixture has no runtime.
    stub = work / "runtime_stub.cpp"
    stub.write_text('extern "C" void spurs_wait_priority_set(unsigned long long (*job_list)(void*), void* context)\n'
                    '{ (void)job_list; (void)context; }\n')
    # The lift header is generated and is not in the repository. The stand-in declares the three
    # names that the adapter uses in its production Windows build.
    lift = work / "lift"
    lift.mkdir(parents=True, exist_ok=True)
    (lift / "ppu_recomp.h").write_text('#pragma once\n#include <cstdint>\n'
                                       'struct ppu_context { std::uint64_t gpr[32], ctr, lr; std::uint32_t cr; };\n'
                                       'std::uint32_t vm_read32(std::uint64_t);\n'
                                       'std::uint16_t vm_read16(std::uint64_t);\n')
    exe = work / "fixture.exe"
    command = [environment["MV_CLANG"], "/nologo", "/std:c++17", "/O2", "/UNDEBUG", "/EHsc",
               "/DMOTORSTORM_JOB_WAIT_WAKE_FALLBACK_MS=%d" % FALLBACK,
               "/I" + str(lift), "/I" + str(ROOT / "src/motorstorm"),
               *(["/I" + str(ROOT / "vendor/ps3recomp/include")] if vendor_include else []),
               str(source), str(ROOT / "src/motorstorm/job_wait.cpp"), str(stub), str(fixture),
               "/Fo" + str(work) + os.sep, "/Fe" + str(exe)]
    result = subprocess.run(command, cwd=work, env=environment, capture_output=True, text=True,
                            errors="replace", timeout=300)
    (work / "build.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    return exe


def run(exe, environment, value):
    """Return the fixture records for one value of the switch, None for unset."""
    variables = {key: item for key, item in environment.items()
                 if key != SWITCH and not key.startswith("MS_NATIVE_JOB_WAIT")}
    if value is not None:
        variables[SWITCH] = value
    try:
        result = subprocess.run([str(exe)], capture_output=True, text=True, env=variables, timeout=20,
                                errors="replace")
    except subprocess.TimeoutExpired:
        raise AssertionError("the marker wait does not end with SPURS_MARKER_WAKE=%r" % value)
    assert result.returncode == 0, (value, result.returncode, result.stderr[-2000:])
    # A value that is not 0 or 1 makes each of the three calls a visible error and a fallback.
    errors = result.stderr.count("ORIGINAL fallback: SPURS_MARKER_WAKE must be 0 or 1")
    assert errors == (3 if value in BAD_VALUES else 0), (value, result.stderr[-2000:])
    records = {fields["scenario"]: int(fields["elapsed"])
               for fields in (dict(re.findall(r"(\w+)=(-?\w+)", line[len(PREFIX):]))
                              for line in result.stdout.splitlines() if line.startswith(PREFIX))
               if "scenario" in fields}
    for line in result.stdout.splitlines():
        if line.startswith(PREFIX) and "installed=" in line:
            records["installed"] = int(line.split("installed=")[1])
        elif line.startswith(PREFIX):
            assert line.endswith("complete=1") or value in BAD_VALUES, (value, line)
    return records


def verify(exe, environment):
    """Raise AssertionError when the fixture at exe breaks one rule."""
    for value in OFF_VALUES:
        records = run(exe, environment, value)
        # Nothing is installed without the switch; the timer step of the wait stays.
        assert records["installed"] == 0, (value, records)
        assert all(records[name] < PROMPT for name in ("wake", "fallback", "stale")), (value, records)
        assert records["wake"] >= 15, (value, records)
    # A value that is not 0 or 1 is a visible error: nothing is installed and no wait runs.
    for value in BAD_VALUES:
        records = run(exe, environment, value)
        assert records["installed"] == 0, (value, records)
        assert all(records[name] < 15 for name in ("wake", "fallback", "stale")), (value, records)
    records = run(exe, environment, ON_VALUE)
    assert records["installed"] == 1, records
    # A commit on the waited job list line ends the wait at once.
    assert 15 <= records["wake"] < PROMPT, records
    # A commit during a poll does not make the next wait rest on the fallback time.
    assert records["stale"] < PROMPT, records
    # Without a commit report, the fallback time ends the wait: it never hangs.
    assert LATE <= records["fallback"] < 3 * FALLBACK, records


def syntax_only(environment, path):
    command = [environment["MV_CLANG"], "/nologo", "/Zs", "/std:c11", "/experimental:c11atomics",
               "/clang:-std=c17", "/D_CRT_SECURE_NO_WARNINGS", "-Wno-everything"]
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
    parser.add_argument("--adapter", type=Path, default=ROOT / "src/motorstorm/job_wait_adapter.cpp")
    parser.add_argument("--fixture", type=Path, default=ROOT / "scripts/fixtures/job_marker_wake.cpp")
    args = parser.parse_args()
    channels = (args.vendor / "runtime/spu/spu_channels.c").read_text()
    launcher = args.launcher.read_text()
    adapter = args.adapter.read_text()
    fixture = args.fixture.resolve()
    audit(channels, launcher, adapter)
    mutants = [launcher.replace(line, "", 1) for line in (ARGUMENT, POP, SET, RECORD)]
    mutants.append(launcher.replace("if args.spurs_marker_wake=='1':", "if True:", 1))
    for index, changed in enumerate(mutants):
        try:
            audit(channels, changed, adapter)
        except AssertionError:
            pass
        else:
            raise AssertionError("launcher mutant %d accepted" % index)
    for name, before, after in SOURCE_MUTANTS:
        assert channels.count(before) == 1, (name, before)
        try:
            audit(channels.replace(before, after), launcher, adapter)
        except AssertionError:
            pass
        else:
            raise AssertionError("source mutant accepted: " + name)
    for name, before, after in ADAPTER_AUDIT_MUTANTS:
        assert adapter.count(before) == 1, (name, before)
        try:
            audit(channels, launcher, adapter.replace(before, after))
        except AssertionError:
            pass
        else:
            raise AssertionError("adapter audit mutant accepted: " + name)
    environment = project.build_environment()
    with tempfile.TemporaryDirectory(prefix="spurs-marker-wake-") as directory:
        root = Path(directory)
        verify(build(environment, root / "actual", adapter, fixture), environment)
        for name, before, after in ADAPTER_MUTANTS:
            assert adapter.count(before) == 1, (name, before)
            try:
                verify(build(environment, root / name, adapter.replace(before, after), fixture), environment)
            except AssertionError:
                pass
            else:
                raise AssertionError("adapter mutant accepted: " + name)
        # The adapter needs the hook header: without the include path of the
        # vendor copy, the build fails.
        try:
            build(environment, root / "no-header", adapter, fixture, vendor_include=False)
        except AssertionError:
            pass
        else:
            raise AssertionError("adapter builds without the hook header")
    if os.name == "nt":
        syntax_only(environment, args.vendor / "runtime/spu/spu_channels.c")
    print("PASS actual marker wake: wake at once, no stale wait, bounded fallback, nothing without the switch, "
          "line commit hook, launcher, adapter, %d launcher, %d source, %d adapter audit and %d adapter mutants "
          "rejected, syntax-only spu_channels"
          % (len(mutants), len(SOURCE_MUTANTS), len(ADAPTER_AUDIT_MUTANTS), len(ADAPTER_MUTANTS)))


if __name__ == "__main__":
    main()
