#!/usr/bin/env python3
"""Game-free checks for the SPURS notify coordinator wait (SPURS_KERNEL_NOTIFY=1).

1. Audits the vendor copy and scripts/run.py: the coordinator keeps its
   fallback deadline in QueryPerformanceCounter, waits on a waitable timer,
   and a kick makes that timer expire at once; the launcher sets the switch
   only with --spurs-kernel-notify 1 and records it. Mutants must fail.
2. Compiles the production wait header with an authored fixture: clock units,
   period, no system-tick step, a 2 ms deadline wait, a wake from another
   thread, a re-arm. Mutants of the header must fail.
3. Compiles libs/spurs/cellSpurs.c with a syntax-only clang-cl pass.
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

SWITCH = "SPURS_KERNEL_NOTIFY"
ARGUMENT = "ap.add_argument('--spurs-kernel-notify',"
POP = "env.pop('SPURS_KERNEL_NOTIFY',None)"
SET = "if args.spurs_kernel_notify=='1':env['SPURS_KERNEL_NOTIFY']='1'"
RECORD = "if 'SPURS_KERNEL_NOTIFY' in env:record['environment']['SPURS_KERNEL_NOTIFY']=env['SPURS_KERNEL_NOTIFY']"

PREFIX = "[SPURS_NOTIFY_WAIT] "
TICK = 78000            # half of a 15.6 ms system tick, in 100 ns
CONVERSIONS = [
    ((1, 1), 10000000),
    ((10000000, 10000000), 10000000),
    ((3000000000, 3000000000), 10000000),
    ((12345678901234567, 1000000000), 123456789012345),
    ((3579500, 3579500), 10000000),
    ((0, 0), 0),
    (((1 << 62) + 12345, 1 << 40), 41943040000000),
]

# Each text must occur in libs/spurs/cellSpurs.c exactly count times.
WIRING = [
    ('#include "spurs_notify_wait.h"', 1),
    ('HANDLE poll_timer;', 1),
    ('const int notify = spurs_kernel_notify() && si->poll_timer != NULL;', 1),
    ('uint64_t next_poll = notify ? spurs_kernel_now() + SPURS_KERNEL_POLL_100NS : 0;', 1),
    ('            uint64_t now = spurs_kernel_now();', 1),
    ('                spurs_poll_arm(si->poll_timer, next_poll);\n'
     '                ReleaseSRWLockExclusive(&si->lock);\n'
     '                WaitForSingleObject(si->poll_timer, INFINITE);\n'
     '                AcquireSRWLockExclusive(&si->lock);\n'
     '                now = spurs_kernel_now();\n', 1),
    ('            timed = now >= next_poll;\n'
     '            if (timed) next_poll = now + SPURS_KERNEL_POLL_100NS;\n', 1),
    ('si->poll_timer = spurs_kernel_notify() ? spurs_poll_timer_create() : NULL;', 1),
    ('spurs_poll_wake(si->poll_timer);', 3),
    ('spurs_poll_timer_close(si);', 2),
    ('    timer = si->poll_timer; si->poll_timer = NULL;\n'
     '    ReleaseSRWLockExclusive(&si->lock);\n'
     '    if (timer) CloseHandle(timer);\n', 1),
    ('CloseHandle(si->poll_timer)', 0),
    ('GetTickCount64', 0),
    ('CONDITION_VARIABLE kick;', 0),
    ('SleepConditionVariableSRW(&si->kick', 0),
]

# One mutant per rule of the coordinator wait: name, text, replacement.
SOURCE_MUTANTS = [
    ("tick-clock-at-start", "spurs_kernel_now() + SPURS_KERNEL_POLL_100NS",
     "GetTickCount64() + SPURS_KERNEL_POLL_MS"),
    ("tick-clock-after-wait", "                now = spurs_kernel_now();",
     "                now = GetTickCount64() * 10000u;"),
    ("clock-not-read-after-wait", "                now = spurs_kernel_now();\n", ""),
    ("period-in-ticks", "next_poll = now + SPURS_KERNEL_POLL_100NS;", "next_poll = now + SPURS_KERNEL_POLL_MS;"),
    ("wait-holds-lock",
     '                ReleaseSRWLockExclusive(&si->lock);\n'
     '                WaitForSingleObject(si->poll_timer, INFINITE);\n'
     '                AcquireSRWLockExclusive(&si->lock);\n',
     '                WaitForSingleObject(si->poll_timer, INFINITE);\n'),
    ("kick-without-wake", "    si->kicks++;\n    spurs_poll_wake(si->poll_timer);", "    si->kicks++;"),
    ("stop-without-wake",
     "si->stopping = 1; WakeAllConditionVariable(&si->wake); spurs_poll_wake(si->poll_timer);\n"
     "    ReleaseSRWLockExclusive(&si->lock);\n    if (si->coordinator)",
     "si->stopping = 1; WakeAllConditionVariable(&si->wake);\n"
     "    ReleaseSRWLockExclusive(&si->lock);\n    if (si->coordinator)"),
    ("timer-not-created", "si->poll_timer = spurs_kernel_notify() ? spurs_poll_timer_create() : NULL;",
     "si->poll_timer = NULL;"),
    ("timer-handle-not-cleared", "    timer = si->poll_timer; si->poll_timer = NULL;\n",
     "    timer = si->poll_timer;\n"),
    ("wait-without-timer", "spurs_kernel_notify() && si->poll_timer != NULL", "spurs_kernel_notify()"),
]

# One mutant per rule of the header: name, text to replace, replacement.
HEADER_MUTANTS = [
    ("tick-clock",
     "    QueryPerformanceCounter(&counter);\n"
     "    QueryPerformanceFrequency(&frequency);\n"
     "    return spurs_kernel_100ns((uint64_t)counter.QuadPart, (uint64_t)frequency.QuadPart);\n",
     "    return GetTickCount64() * 10000u;\n"),
    ("rate-in-milliseconds",
     "counter / frequency * 10000000u + counter % frequency * 10000000u / frequency",
     "counter / frequency * 1000u + counter % frequency * 1000u / frequency"),
    ("counter-times-rate",
     "counter / frequency * 10000000u + counter % frequency * 10000000u / frequency",
     "counter * 10000000u / frequency"),
    ("no-rate-guard", "    if (!frequency)\n        return 0;\n", ""),
    ("period-in-milliseconds", "((uint64_t)SPURS_KERNEL_POLL_MS * 10000u)",
     "((uint64_t)SPURS_KERNEL_POLL_MS * 1000u)"),
    ("arm-absolute-time", "due.QuadPart = deadline > now ? -(LONGLONG)(deadline - now) : -1;",
     "due.QuadPart = deadline > now ? (LONGLONG)(deadline - now) : -1;"),
    ("wake-arms-one-second", "    due.QuadPart = -1;\n    SetWaitableTimer",
     "    due.QuadPart = -10000000;\n    SetWaitableTimer"),
]

# The fixture includes the header and the platform shim of the vendor copy.
FIXTURE = r'''
#include <stdio.h>
#include "runtime/platform/win32_compat.h"
#define SPURS_KERNEL_POLL_MS 1
#include "libs/spurs/spurs_notify_wait.h"

/* Time in 100 ns, read and converted here, not through the header under test. */
static uint64_t own_now(void)
{
    LARGE_INTEGER counter, frequency;
    QueryPerformanceCounter(&counter);
    QueryPerformanceFrequency(&frequency);
    return (uint64_t)((long double)counter.QuadPart * 10000000.0L / (long double)frequency.QuadPart);
}

/* Milliseconds of CPU time; a busy loop, so the system tick plays no part. */
static void busy_milliseconds(double milliseconds)
{
    uint64_t start = own_now();
    while (own_now() - start < (uint64_t)(milliseconds * 10000.0)) { }
}

static void convert(uint64_t counter, uint64_t frequency)
{
    printf("[SPURS_NOTIFY_WAIT] convert counter=%llu frequency=%llu units=%llu\n",
           (unsigned long long)counter, (unsigned long long)frequency,
           (unsigned long long)spurs_kernel_100ns(counter, frequency));
}

/* One wait on the timer; prints the elapsed time and the wait result. */
static void waited(const char* kind, int index, HANDLE timer)
{
    uint64_t start = own_now();
    DWORD result = WaitForSingleObject(timer, 5000);
    uint64_t elapsed = own_now() - start;
    printf("[SPURS_NOTIFY_WAIT] %s index=%d elapsed=%llu wait=%lu\n",
           kind, index, (unsigned long long)elapsed, (unsigned long)result);
}

static HANDLE wake_timer;
static DWORD WINAPI wake_later(void* unused)
{
    (void)unused;
    Sleep(30);
    spurs_poll_wake(wake_timer);
    return 0;
}

int main(void)
{
    /* One second at each common rate, a sub-second remainder, no rate, and a
     * counter whose product with 10000000 exceeds 64 bits. */
    convert(1, 1);
    convert(10000000, 10000000);
    convert(3000000000ull, 3000000000ull);
    convert(12345678901234567ull, 1000000000ull);
    convert(3579500, 3579500);
    convert(0, 0);
    convert((1ull << 62) + 12345, 1ull << 40);
    printf("[SPURS_NOTIFY_WAIT] period ms=%d units=%llu\n", SPURS_KERNEL_POLL_MS,
           (unsigned long long)SPURS_KERNEL_POLL_100NS);

    /* The clock has no system-tick step: two reads around a 2 ms busy wait
     * differ by about 2 ms, also when the wait lies inside one tick. */
    for (int i = 0; i < 8; i++) {
        uint64_t before = spurs_kernel_now();
        busy_milliseconds(2.0);
        uint64_t after = spurs_kernel_now();
        printf("[SPURS_NOTIFY_WAIT] busy index=%d elapsed=%llu after_before=%d\n", i,
               (unsigned long long)(after - before), before <= after);
    }

    HANDLE timer = spurs_poll_timer_create();
    printf("[SPURS_NOTIFY_WAIT] timer created=%d\n", timer != NULL);
    if (!timer) return 1;

    /* The deadline ends the wait: 2 ms, not a system tick. The check reads
     * the shortest sample, so load on the host does not fail it. */
    for (int i = 0; i < 6; i++) {
        spurs_poll_arm(timer, spurs_kernel_now() + 20000);
        waited("deadline", i, timer);
    }

    /* A wake from another thread ends a long wait: 30 ms into a 3 s wait. */
    spurs_poll_arm(timer, spurs_kernel_now() + 30000000);
    wake_timer = timer;
    HANDLE thread = CreateThread(NULL, 0, wake_later, NULL, 0, NULL);
    waited("wake", 0, timer);
    printf("[SPURS_NOTIFY_WAIT] thread created=%d\n", thread != NULL);
    WaitForSingleObject(thread, INFINITE);
    CloseHandle(thread);

    /* A wait that ended does not end the next one: a new arm replaces the
     * pending signal. */
    for (int i = 0; i < 3; i++) {
        spurs_poll_wake(timer);
        waited("signaled", i, timer);
        spurs_poll_arm(timer, spurs_kernel_now() + 20000);
        waited("rearmed", i, timer);
    }
    CloseHandle(timer);
    return 0;
}
'''


def audit(source, launcher):
    """Raise AssertionError when the wait is not wired or the launcher leaks the switch."""
    for text in (ARGUMENT, POP, SET, RECORD):
        assert launcher.count(text) == 1, "the launcher has one line: " + text
    assert launcher.index(POP) < launcher.index(SET) < launcher.index(RECORD), "the launcher clears, sets, records"
    for text, count in WIRING:
        assert source.count(text) == count, (count, source.count(text), text[:70])


def build(environment, work, header, shim):
    """Compile the fixture with `header` in a tree that has the layout of the vendor copy."""
    (work / "libs/spurs").mkdir(parents=True, exist_ok=True)
    (work / "runtime/platform").mkdir(parents=True, exist_ok=True)
    (work / "libs/spurs/spurs_notify_wait.h").write_text(header)
    (work / "runtime/platform/win32_compat.h").write_text(shim)
    source = work / "harness.c"
    source.write_text(FIXTURE)
    exe = work / "harness.exe"
    command = [environment["MV_CLANG"], "/nologo", "/O2", "/clang:-Wno-everything", str(source),
               "/Fo" + str(work) + os.sep, "/Fe" + str(exe)]
    result = subprocess.run(command, cwd=work, env=environment, capture_output=True, text=True,
                            errors="replace", timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    return exe


def run(exe, environment):
    """Return the fixture result and its records as (kind, fields) pairs."""
    result = subprocess.run([str(exe)], capture_output=True, text=True, env=environment, timeout=30)
    records = []
    for line in result.stdout.splitlines():
        if line.startswith(PREFIX):
            kind, _, fields = line[len(PREFIX):].partition(" ")
            records.append((kind, dict(re.findall(r"(\w+)=(\w+)", fields))))
    return result, records


def of_kind(records, kind):
    return [fields for name, fields in records if name == kind]


def verify(exe, environment):
    """Raise AssertionError when the fixture at exe breaks one rule."""
    result, records = run(exe, environment)
    assert result.returncode == 0 and not result.stderr, (result.returncode, result.stderr[-2000:])
    converted = of_kind(records, "convert")
    assert len(converted) == len(CONVERSIONS), records
    for fields, ((counter, frequency), units) in zip(converted, CONVERSIONS):
        assert (int(fields["counter"]), int(fields["frequency"]), int(fields["units"])) == \
            (counter, frequency, units), fields
    period, = of_kind(records, "period")
    assert int(period["units"]) == int(period["ms"]) * 10000, period

    # The clock has no system-tick step.
    busy = of_kind(records, "busy")
    assert len(busy) == 8, records
    assert all(fields["after_before"] == "1" for fields in busy), busy
    elapsed = sorted(int(fields["elapsed"]) for fields in busy)
    assert elapsed[0] >= 15000, elapsed
    assert sum(value < TICK for value in elapsed) >= 4, elapsed

    # The timer ends a wait at its deadline, below the tick.
    timer, = of_kind(records, "timer")
    assert timer["created"] == "1", timer
    deadline = of_kind(records, "deadline")
    assert len(deadline) == 6 and all(fields["wait"] == "0" for fields in deadline), deadline
    elapsed = sorted(int(fields["elapsed"]) for fields in deadline)
    assert 20000 <= elapsed[0] < TICK, elapsed

    # A wake from another thread ends a long wait.
    wake, = of_kind(records, "wake")
    assert wake["wait"] == "0" and 15000 <= int(wake["elapsed"]) < 2500000, wake
    thread, = of_kind(records, "thread")
    assert thread["created"] == "1", thread

    # A new arm replaces a pending signal.
    signaled = of_kind(records, "signaled")
    rearmed = of_kind(records, "rearmed")
    assert len(signaled) == len(rearmed) == 3, records
    assert all(fields["wait"] == "0" for fields in signaled + rearmed), records
    # The shortest sample shows the rule; load on the host lengthens the others.
    assert min(int(fields["elapsed"]) for fields in signaled) < TICK, signaled
    assert 20000 <= min(int(fields["elapsed"]) for fields in rearmed) < TICK, rearmed


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
    args = parser.parse_args()
    spurs = args.vendor / "libs/spurs"
    launcher = args.launcher.read_text()
    source = (spurs / "cellSpurs.c").read_text()
    header = (spurs / "spurs_notify_wait.h").read_text()
    shim = (args.vendor / "runtime/platform/win32_compat.h").read_text()
    audit(source, launcher)
    mutants = [launcher.replace(line, "", 1) for line in (ARGUMENT, POP, SET, RECORD)]
    mutants.append(launcher.replace("if args.spurs_kernel_notify=='1':", "if True:", 1))
    for index, changed in enumerate(mutants):
        try:
            audit(source, changed)
        except AssertionError:
            pass
        else:
            raise AssertionError("launcher mutant %d accepted" % index)
    count = 0
    for name, before, after in SOURCE_MUTANTS:
        assert source.count(before) == 1, (name, before)
        try:
            audit(source.replace(before, after), launcher)
        except AssertionError:
            count += 1
        else:
            raise AssertionError("source mutant accepted: " + name)
    environment = project.build_environment()
    with tempfile.TemporaryDirectory(prefix="spurs-notify-wait-") as directory:
        root = Path(directory)
        verify(build(environment, root / "actual", header, shim), environment)
        header_count = 0
        for name, anchor, replacement in HEADER_MUTANTS:
            assert header.count(anchor) == 1, (name, anchor)
            try:
                verify(build(environment, root / name, header.replace(anchor, replacement), shim), environment)
            except AssertionError:
                header_count += 1
            else:
                raise AssertionError("header mutant accepted: " + name)
    if os.name == "nt":
        syntax_only(environment, spurs / "cellSpurs.c")
    print("PASS actual notify wait: clock units, period, no tick step, 2 ms deadline, wake, re-arm, "
          "coordinator wiring, launcher, %d audit mutants, %d header mutants, syntax-only cellSpurs"
          % (len(mutants) + count, header_count))


if __name__ == "__main__":
    main()
