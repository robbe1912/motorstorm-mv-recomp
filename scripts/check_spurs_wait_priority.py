#!/usr/bin/env python3
"""Game-free checks for the SPURS wait priority (SPURS_WAIT_PRIORITY=1).

1. Audits the vendor copy, scripts/run.py and the job wait adapter: the pass
   of the coordinator tests the workload of the waited job list first, the
   launcher sets the switch only with --spurs-wait-priority 1 and records it,
   and the adapter registers the callback and names the waited job list for
   the time of a marker wait. Mutants must fail.
2. Compiles the production header with an authored harness: switch value,
   callback, workload of a job list, scan order and counters. Mutants of the
   header must fail.
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

SWITCH = "SPURS_WAIT_PRIORITY"
ARGUMENT = "ap.add_argument('--spurs-wait-priority',"
POP = "env.pop('SPURS_WAIT_PRIORITY',None)"
SET = "if args.spurs_wait_priority=='1':env['SPURS_WAIT_PRIORITY']='1'"
RECORD = "if 'SPURS_WAIT_PRIORITY' in env:record['environment']['SPURS_WAIT_PRIORITY']=env['SPURS_WAIT_PRIORITY']"

PREFIX = "[wait_priority] "
LINE = "[SPURS_WAIT_PRIORITY] "
OFF_VALUES = [None, "0", "true", "11", "1 ", " 1", "01", "on"]
ON_VALUE = "1"
LINES = [LINE + "waits=2 boosted_jobs=1", LINE + "waits=3 boosted_jobs=1", LINE + "waits=3 boosted_jobs=1"]

# Each text must occur in libs/spurs/cellSpurs.c exactly count times.
WIRING = [
    ('#include "spurs_wait_priority.h"', 1),
    # The wanted workload is a workload of the instance that runs the pass.
    ('    return s_workloads[wid].in_use && s_workloads[wid].spurs_ea == (u32)(uintptr_t)ctx\n'
     '        ? s_workloads[wid].data : 0;\n', 1),
    ('        const int wanted = spurs_wait_priority_workload(spurs_wait_priority_job_list(),\n'
     '                                                        spurs_wait_priority_data, (void *)(uintptr_t)ea);\n', 1),
    # One wait for each free lane that the pass gave while a PPU thread waited.
    ('            if (wanted >= 0) spurs_wait_priority_wait();\n', 1),
    ('            for (u32 checked = 0; checked < spurs_wait_priority_count(wanted); checked++) {\n'
     '                int at = spurs_wait_priority_at(wanted, &si->cursor, checked);\n'
     '                if (at < 0) continue;   /* the wanted workload had its position */\n'
     '                u32 wid = (u32)at;\n', 1),
    ('                if ((int)wid == wanted) spurs_wait_priority_job();\n'
     '                slot->busy = 1;\n', 1),
    # The line prints outside the registry lock, after each pass.
    ('        ReleaseSRWLockExclusive(&s_workload_registry_lock);\n'
     '        spurs_wait_priority_report(GetTickCount());\n', 1),
    ('checked < 16; checked++', 0),
    ('u32 wid = si->cursor;', 0),
]
SOURCE_MUTANTS = [
    # name, text in libs/spurs/cellSpurs.c, replacement
    ('scan-without-wanted-position', 'checked < spurs_wait_priority_count(wanted)', 'checked < 16'),
    ('cursor-order-only',
     '                int at = spurs_wait_priority_at(wanted, &si->cursor, checked);\n'
     '                if (at < 0) continue;   /* the wanted workload had its position */\n'
     '                u32 wid = (u32)at;\n',
     '                u32 wid = si->cursor; si->cursor = (wid + 1) & 15;\n'),
    ('empty-position-not-skipped',
     '                if (at < 0) continue;   /* the wanted workload had its position */\n', ''),
    ('wanted-from-any-instance',
     '    return s_workloads[wid].in_use && s_workloads[wid].spurs_ea == (u32)(uintptr_t)ctx\n'
     '        ? s_workloads[wid].data : 0;\n',
     '    return s_workloads[wid].data;\n'),
    ('wanted-of-no-thread', 'const int wanted = spurs_wait_priority_workload(spurs_wait_priority_job_list(),',
     'const int wanted = spurs_wait_priority_workload(0,'),
    ('waits-not-counted', '            if (wanted >= 0) spurs_wait_priority_wait();\n', ''),
    ('jobs-not-counted', '                if ((int)wid == wanted) spurs_wait_priority_job();\n', ''),
    ('report-missing', '        spurs_wait_priority_report(GetTickCount());\n', ''),
    ('report-under-registry-lock',
     '        ReleaseSRWLockExclusive(&s_workload_registry_lock);\n'
     '        spurs_wait_priority_report(GetTickCount());\n',
     '        spurs_wait_priority_report(GetTickCount());\n'
     '        ReleaseSRWLockExclusive(&s_workload_registry_lock);\n'),
    ('header-not-included', '#include "spurs_wait_priority.h"', '#include "spurs_wait_priority_off.h"'),
]
HEADER_MUTANTS = [
    # name, text in the header, replacement
    ('switch-any-value', "v = e && e[0] == '1' && !e[1];", 'v = e != NULL;'),
    ('switch-prefix', "v = e && e[0] == '1' && !e[1];", "v = e && e[0] == '1';"),
    ('switch-always-off', "v = e && e[0] == '1' && !e[1];", 'v = 0;'),
    ('callback-without-switch', '    if (!spurs_wait_priority_on()) return 0;\n', ''),
    ('callback-ignored', '    return fn ? fn(__atomic_load_n(&s_wait_priority_ctx, __ATOMIC_ACQUIRE)) : 0;\n',
     '    return fn ? 0 : 0;\n'),
    ('callback-without-context', 'fn(__atomic_load_n(&s_wait_priority_ctx, __ATOMIC_ACQUIRE))', 'fn(0)'),
    ('registration-not-stored',
     '    __atomic_store_n(&s_wait_priority_fn, fn, __ATOMIC_RELEASE);\n}\n',
     '    (void)fn; (void)ctx;\n}\n'),
    ('callback-without-context-dropped',
     '    __atomic_store_n(&s_wait_priority_fn, fn, __ATOMIC_RELEASE);\n}\n',
     '    if (ctx) __atomic_store_n(&s_wait_priority_fn, fn, __ATOMIC_RELEASE);\n}\n'),
    ('workload-last-match',
     '    if (!list) return -1;\n'
     '    for (unsigned wid = 0; wid < SPURS_WAIT_PRIORITY_WORKLOADS; wid++)\n'
     '        if (data(ctx, wid) == list) return (int)wid;\n'
     '    return -1;\n',
     '    int found = -1;\n'
     '    if (!list) return found;\n'
     '    for (unsigned wid = 0; wid < SPURS_WAIT_PRIORITY_WORKLOADS; wid++)\n'
     '        if (data(ctx, wid) == list) found = (int)wid;\n'
     '    return found;\n'),
    ('workload-misses-last', 'wid < SPURS_WAIT_PRIORITY_WORKLOADS; wid++)',
     'wid + 1 < SPURS_WAIT_PRIORITY_WORKLOADS; wid++)'),
    ('workload-without-list-guard', '    if (!list) return -1;\n', ''),
    ('scan-without-wanted-position', '    return SPURS_WAIT_PRIORITY_WORKLOADS + (wanted >= 0);\n',
     '    return SPURS_WAIT_PRIORITY_WORKLOADS;\n'),
    ('scan-one-position-too-many', '    return SPURS_WAIT_PRIORITY_WORKLOADS + (wanted >= 0);\n',
     '    return SPURS_WAIT_PRIORITY_WORKLOADS + 1;\n'),
    ('wanted-not-first', '    if (wanted >= 0 && !checked) return wanted;\n',
     '    if (wanted >= 0 && checked == 1) return wanted;\n'),
    ('hit-position-not-empty', '    return (int)wid == wanted ? -1 : (int)wid;\n',
     '    return (int)wid;\n'),
    ('cursor-not-advanced',
     '    unsigned wid = *cursor;\n'
     '    *cursor = (wid + 1) & (SPURS_WAIT_PRIORITY_WORKLOADS - 1u);\n',
     '    unsigned wid = *cursor;\n'),
    ('report-each-pass', 'now_ms - s_wait_priority_last_line < SPURS_WAIT_PRIORITY_LINE_MS', '0'),
    ('report-without-switch', 'if (!spurs_wait_priority_on() || now_ms', 'if (now_ms'),
    ('report-one-line-per-two-seconds', '#define SPURS_WAIT_PRIORITY_LINE_MS 1000',
     '#define SPURS_WAIT_PRIORITY_LINE_MS 2000'),
    ('waits-not-counted', '    s_wait_priority_waits++;\n', ''),
    ('jobs-not-counted', '    s_wait_priority_jobs++;\n', ''),
    ('report-counts-swapped',
     '(unsigned long long)s_wait_priority_waits, (unsigned long long)s_wait_priority_jobs);',
     '(unsigned long long)s_wait_priority_jobs, (unsigned long long)s_wait_priority_waits);'),
]
# Each text must occur in src/motorstorm/job_wait_adapter.cpp exactly one time.
ADAPTER_WIRING = [
    # The fixture build does not link the runtime: the symbol stays outside it.
    ('#ifndef MOTORSTORM_JOB_WAIT_FIXTURE\n'
     '// SPURS_WAIT_PRIORITY=1: the runtime asks for the job list that a PPU thread waits on.\n'
     'extern "C" void spurs_wait_priority_set(std::uint64_t (*job_list)(void*), void* context);\n'
     '#endif\n', 1),
    ('std::atomic<std::uint32_t> wait_priority_owner{0};\n', 1),
    ('    return wait_priority_owner.load(std::memory_order_acquire);\n', 1),
    ('    ~WaitPriority() { wait_priority_owner.store(0, std::memory_order_release); }\n', 1),
    # begin names the waited job list with the one read of the job list address.
    ('    wait_priority_owner.store(owner, std::memory_order_release);\n', 1),
    ('#ifndef MOTORSTORM_JOB_WAIT_FIXTURE\n'
     '            static const bool registered = [] { spurs_wait_priority_set(wait_priority_job_list, nullptr); return true; }();\n'
     '            (void)registered;\n'
     '#endif\n', 1),
    ('            const WaitPriority priority;   // the waited job list is cleared when the wait ends\n'
     '            const auto result = motorstorm::game::wait_for_job_marker(\n', 1),
]
ADAPTER_MUTANTS = [
    # name, text in the adapter, replacement
    ('registration-missing', 'spurs_wait_priority_set(wait_priority_job_list, nullptr); return true;', 'return true;'),
    ('callback-returns-none', 'return wait_priority_owner.load(std::memory_order_acquire);', 'return 0;'),
    ('boost-not-set', '    wait_priority_owner.store(owner, std::memory_order_release);\n', ''),
    ('boost-not-cleared', '    ~WaitPriority() { wait_priority_owner.store(0, std::memory_order_release); }\n',
     '    ~WaitPriority() {}\n'),
    ('boost-outside-wait', '            const WaitPriority priority;   // the waited job list is cleared when the wait ends\n', ''),
    ('boost-of-wait-object', 'wait_priority_owner.store(owner, std::memory_order_release);',
     'wait_priority_owner.store(static_cast<std::uint32_t>(ctx->gpr[3]), std::memory_order_release);'),
    ('registration-in-fixture-build',
     '#ifndef MOTORSTORM_JOB_WAIT_FIXTURE\n'
     '            static const bool registered',
     '#if 1\n'
     '            static const bool registered'),
]


def audit(source, launcher, adapter):
    """Raise AssertionError when the pass, the launcher or the adapter is not wired."""
    for text in (ARGUMENT, POP, SET, RECORD):
        assert launcher.count(text) == 1, "the launcher has one line: " + text
    assert launcher.index(POP) < launcher.index(SET) < launcher.index(RECORD), "the launcher clears, sets, records"
    for text, count in WIRING:
        assert source.count(text) == count, (count, source.count(text), text[:70])
    for text, count in ADAPTER_WIRING:
        assert adapter.count(text) == count, (count, adapter.count(text), text[:70])


def build(environment, work, header, harness):
    """Compile the harness with `header` in a tree that has the layout of the vendor copy."""
    (work / "tests").mkdir(parents=True, exist_ok=True)
    (work / "libs/spurs").mkdir(parents=True, exist_ok=True)
    (work / "libs/spurs/spurs_wait_priority.h").write_text(header)
    source = work / "tests" / harness.name
    source.write_text(harness.read_text())
    exe = work / "harness.exe"
    command = [environment["MV_CLANG"], "/nologo", "/O2", "/clang:-Wno-everything", str(source),
               "/Fo" + str(work) + os.sep, "/Fe" + str(exe)]
    result = subprocess.run(command, cwd=work, env=environment, capture_output=True, text=True,
                            errors="replace", timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    return exe


def run(exe, environment, value):
    """Return the harness result for one value of the switch, None for unset, and its records."""
    variables = {key: item for key, item in environment.items() if key != SWITCH}
    if value is not None:
        variables[SWITCH] = value
    result = subprocess.run([str(exe)], capture_output=True, text=True, env=variables, timeout=30,
                            errors="replace")
    records = {}
    for line in result.stdout.splitlines():
        if not line.startswith(PREFIX):
            continue
        fields = dict(re.findall(r"(\w+)=(-?\w+)", line[len(PREFIX):]))
        kind = line[len(PREFIX):].split()[0].split("=")[0]
        if kind == "scan":
            # One record for each wanted workload: key "scan<wanted>".
            records["scan" + fields["wanted"]] = fields
        else:
            records[kind] = fields
    lines = [line for line in result.stderr.splitlines() if line.startswith(LINE)]
    return result, records, lines


def verify(exe, environment):
    """Raise AssertionError when the harness at exe breaks one rule."""
    zero = ("none", "list", "zero", "replaced", "removed", "removed_without_context", "null_context")
    for value in OFF_VALUES:
        result, records, lines = run(exe, environment, value)
        assert result.returncode == 0 and not result.stderr, (value, result.stderr[-2000:])
        assert records["on"] == {"on": "0"}, (value, records["on"])
        # The callback is not called and gives no job list without the switch.
        assert all(records[key] == {key: "0"} for key in zero if key != "list"), (value, records)
        assert records["list"] == {"list": "0", "calls": "0"}, (value, records)
        assert not lines, (value, lines)
        verify_scan(records)
    result, records, lines = run(exe, environment, ON_VALUE)
    assert result.returncode == 0, (result.returncode, result.stderr[-2000:])
    assert records["on"] == {"on": "1"}, records
    assert records["none"] == {"none": "0"} and records["zero"] == {"zero": "0"}, records
    assert records["list"] == {"list": "4004c580", "calls": "1"}, records
    assert records["replaced"] == {"replaced": "40048500"}, records
    assert records["removed"] == {"removed": "0"}, records
    assert records["removed_without_context"] == {"removed_without_context": "0"}, records
    assert records["null_context"] == {"null_context": "40044480"}, records
    # The workload of a job list is the first workload of the instance with that data.
    assert records["found"] == {"found": "8"} and records["other_instance"] == {"other_instance": "-1"}, records
    assert records["first_of_two"] == {"first_of_two": "3"}, records
    assert records["last"] == {"last": "15"} and records["missing"] == {"missing": "-1"}, records
    assert records["no_list"] == {"no_list": "-1"}, records
    assert records["count"] == {"count": "16", "extra": "17"}, records
    verify_scan(records)
    # The counters print at most one line per second, and only with the switch.
    assert lines == LINES, lines
    assert [line for line in result.stderr.splitlines() if not line.startswith(LINE)] == [], result.stderr


def verify_scan(records):
    """The scan of one free lane: each workload once, the wanted one first."""
    for wanted in range(-1, 16):
        scan = records["scan" + str(wanted)]
        expected = {"wanted": str(wanted), "first": str(wanted if wanted >= 0 else 3), "count": "16",
                    "all": "1", "order": "1", "cursor": "3"}
        assert scan == expected, (scan, expected)


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
    parser.add_argument("--harness", type=Path, default=ROOT / "scripts/fixtures/spurs_wait_priority_harness.c")
    args = parser.parse_args()
    spurs = args.vendor / "libs/spurs"
    launcher = args.launcher.read_text()
    source = (spurs / "cellSpurs.c").read_text()
    header = (spurs / "spurs_wait_priority.h").read_text()
    adapter = args.adapter.read_text()
    audit(source, launcher, adapter)
    mutants = [launcher.replace(line, "", 1) for line in (ARGUMENT, POP, SET, RECORD)]
    mutants.append(launcher.replace("if args.spurs_wait_priority=='1':", "if True:", 1))
    for index, changed in enumerate(mutants):
        try:
            audit(source, changed, adapter)
        except AssertionError:
            pass
        else:
            raise AssertionError("launcher mutant %d accepted" % index)
    for name, before, after in SOURCE_MUTANTS:
        assert source.count(before) == 1, (name, before)
        try:
            audit(source.replace(before, after), launcher, adapter)
        except AssertionError:
            pass
        else:
            raise AssertionError("source mutant accepted: " + name)
    for name, before, after in ADAPTER_MUTANTS:
        assert adapter.count(before) == 1, (name, before)
        try:
            audit(source, launcher, adapter.replace(before, after))
        except AssertionError:
            pass
        else:
            raise AssertionError("adapter mutant accepted: " + name)
    environment = project.build_environment()
    with tempfile.TemporaryDirectory(prefix="spurs-wait-priority-") as directory:
        root = Path(directory)
        verify(build(environment, root / "actual", header, args.harness), environment)
        for name, anchor, replacement in HEADER_MUTANTS:
            assert header.count(anchor) == 1, (name, anchor)
            try:
                verify(build(environment, root / name, header.replace(anchor, replacement), args.harness), environment)
            except AssertionError:
                pass
            else:
                raise AssertionError("header mutant accepted: " + name)
    if os.name == "nt":
        syntax_only(environment, spurs / "cellSpurs.c")
    print("PASS actual wait priority: switch, callback, workload of a job list, scan order, counters, "
          "coordinator wiring, launcher, adapter, %d launcher, %d source, %d adapter and %d header mutants "
          "rejected, syntax-only cellSpurs"
          % (len(mutants), len(SOURCE_MUTANTS), len(ADAPTER_MUTANTS), len(HEADER_MUTANTS)))


if __name__ == "__main__":
    main()
