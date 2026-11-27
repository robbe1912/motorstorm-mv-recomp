#!/usr/bin/env python3
"""Game-free checks for the async SPU task thread pool (PS3RECOMP_SPU_TASK_POOL=1).

1. Audits the vendor copy and scripts/run.py: spu_workload.c hands an async
   SPU task to the pool only with the switch, on both platforms; on Windows a
   pool thread does per task what spu_async_thread does per thread (the stack
   guarantee, then dropping its stack from the lock-line reserver set); the
   launcher sets the switch only with --spu-task-pool 1, clears an inherited
   value and records it. Mutants must fail.
2. Compiles scripts/fixtures/spu_task_pool.c against the vendored
   runtime/spu/spu_task_pool.h for this platform and runs it: reuse, no
   queueing behind a running task, a stress of 40,000 tasks from four
   submitters, and idle retirement. Header mutants must fail.
3. On Windows, compiles runtime/spu/spu_workload.c with a syntax-only
   clang-cl pass.
No game input; no performance claim."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

ARGUMENT = "ap.add_argument('--spu-task-pool',"
POP = "env.pop('PS3RECOMP_SPU_TASK_POOL',None)"
SET = "if args.spu_task_pool=='1':env['PS3RECOMP_SPU_TASK_POOL']='1'"
RECORD = ("if 'PS3RECOMP_SPU_TASK_POOL' in env:"
          "record['environment']['PS3RECOMP_SPU_TASK_POOL']=env['PS3RECOMP_SPU_TASK_POOL']")

# Each text must occur in runtime/spu/spu_workload.c exactly count times.
WIRING = [
    ('#include "spu_task_pool.h"              /* PS3RECOMP_SPU_TASK_POOL */\n', 1),
    ('    spu_task_pool_item  pool_item;   /* PS3RECOMP_SPU_TASK_POOL hand-off */\n', 1),
    ('static spu_task_pool s_spu_task_pool = SPU_TASK_POOL_INIT(2000u, (size_t)256u << 20);\n', 2),
    ('        const char* e = getenv("PS3RECOMP_SPU_TASK_POOL");\n'
     '        v = e && e[0] == \'1\' && !e[1];\n', 2),
    ('    if (spu_task_pool_enabled()) {\n', 2),
    # Windows: per task, the stack leaves the reserver set as at thread exit.
    ('    if (!t_guarantee) { ULONG g = 256 * 1024; SetThreadStackGuarantee(&g); t_guarantee = 1; }\n'
     '    spu_async_run((spu_async_job*)p);\n'
     '    { ULONG_PTR lo, hi; GetCurrentThreadStackLimits(&lo, &hi);\n'
     '      extern void spu_coh_forget_range(uintptr_t, uintptr_t);\n'
     '      spu_coh_forget_range((uintptr_t)lo, (uintptr_t)hi); }\n', 1),
    ('        if (!spu_task_pool_submit_ex(&s_spu_task_pool, &j->pool_item, spu_async_pool_run, j, &nt)) {\n', 1),
    ('        if (nt) { ps3_thread_setname((uintptr_t)nt, "spu_async"); CloseHandle(nt); }\n', 1),
    ('        if (!spu_task_pool_submit(&s_spu_task_pool, &j->pool_item, spu_async_pool_run, j)) {\n', 1),
]
WIRING_MUTANTS = [
    ('pool-without-switch', '    if (spu_task_pool_enabled()) {\n', '    if (1) {\n'),
    ('stack-kept-in-reserver-set',
     '    spu_async_run((spu_async_job*)p);\n'
     '    { ULONG_PTR lo, hi; GetCurrentThreadStackLimits(&lo, &hi);\n'
     '      extern void spu_coh_forget_range(uintptr_t, uintptr_t);\n'
     '      spu_coh_forget_range((uintptr_t)lo, (uintptr_t)hi); }\n}\n#else',
     '    spu_async_run((spu_async_job*)p);\n}\n#else'),
    ('switch-accepts-any-value', "        v = e && e[0] == '1' && !e[1];\n", "        v = e != NULL;\n"),
]
# Header mutants: each must fail the fixture on the platform that compiles it.
HEADER_MUTANTS = [
    # The unsafe policy: queue whenever a pool thread exists, busy or not.
    ('queue-behind-busy-threads', 'if (pool->idle > pool->queued) {', 'if (pool->threads > pool->queued) {'),
    # Queue with no idle thread left to take the task.
    ('queue-without-idle-thread', 'if (pool->idle > pool->queued) {', 'if (pool->idle >= pool->queued) {'),
    # Never retire an idle thread.
    ('no-retirement', '      0, 0, 0, 0, 0, 0, (idle_ms), (stack_size) }', '      0, 0, 0, 0, 0, 0, 1000000u, (stack_size) }'),
]


def audit(workload, launcher):
    for text, count in WIRING:
        assert workload.count(text) == count, (count, workload.count(text), text)
    for text in (ARGUMENT, POP, SET, RECORD):
        assert launcher.count(text) == 1, text


def compiler():
    return (os.environ.get("MV_CLANG") or os.environ.get("CC")
            or ("clang-cl" if os.name == "nt" else shutil.which("clang") or "cc"))


def run_fixture(folder, header, fixture):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "spu_task_pool.h").write_text(header, encoding="utf-8", newline="\n")
    exe = folder / ("check.exe" if os.name == "nt" else "check")
    cc = compiler()
    if Path(cc).name.lower() in {"cl", "cl.exe", "clang-cl", "clang-cl.exe"}:
        cmd = [cc, "/nologo", "/O2", "/W3", "/std:c11", "/experimental:c11atomics", "/I" + str(folder),
               str(fixture), "/Fo" + str(folder) + os.sep, "/Fe" + str(exe)]
    else:
        cmd = [cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
               "-I" + str(folder), str(fixture), "-o", str(exe), "-pthread"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    try:
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    return r.returncode, r.stdout + r.stderr


def syntax_only(path):
    command = [os.environ.get("MV_CLANG", "clang-cl"), "/nologo", "/Zs", "/std:c11",
               "/experimental:c11atomics", "/clang:-std=c17", "/D_CRT_SECURE_NO_WARNINGS", "-Wno-everything"]
    command += ["/I" + str(path.parents[2] / part)
                for part in ("include", "libs/video", "runtime/ppu", "runtime/spu", "runtime/memory",
                             "runtime/syscalls", "runtime/platform")]
    command.append(str(path.resolve()))
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", type=Path, default=ROOT / "vendor/ps3recomp")
    parser.add_argument("--launcher", type=Path, default=ROOT / "scripts/run.py")
    parser.add_argument("--fixture", type=Path, default=ROOT / "scripts/fixtures/spu_task_pool.c")
    args = parser.parse_args()
    workload = (args.vendor / "runtime/spu/spu_workload.c").read_text(encoding="utf-8").replace("\r\n", "\n")
    header = (args.vendor / "runtime/spu/spu_task_pool.h").read_text(encoding="utf-8").replace("\r\n", "\n")
    launcher = args.launcher.read_text(encoding="utf-8")
    audit(workload, launcher)
    mutants = [launcher.replace(line, "", 1) for line in (ARGUMENT, POP, SET, RECORD)]
    mutants.append(launcher.replace("if args.spu_task_pool=='1':", "if True:", 1))
    for index, changed in enumerate(mutants):
        try:
            audit(workload, changed)
        except AssertionError:
            pass
        else:
            raise AssertionError("launcher mutant %d accepted" % index)
    for name, before, after in WIRING_MUTANTS:
        assert workload.count(before) >= 1, (name, before)
        try:
            audit(workload.replace(before, after), launcher)
        except AssertionError:
            pass
        else:
            raise AssertionError("wiring mutant accepted: " + name)
    with tempfile.TemporaryDirectory(prefix="spu-task-pool-") as directory:
        root = Path(directory)
        code, output = run_fixture(root / "actual", header, args.fixture.resolve())
        print(output, end="")
        assert code == 0, "fixture failed on the vendored header"
        for name, before, after in HEADER_MUTANTS:
            assert header.count(before) == 2, (name, header.count(before))   # POSIX and Windows halves
            code, output = run_fixture(root / name, header.replace(before, after), args.fixture.resolve())
            assert code != 0, "header mutant accepted: " + name
    if os.name == "nt":
        syntax_only(args.vendor / "runtime/spu/spu_workload.c")
    print("PASS actual async SPU task pool: reuse, no task queued behind another, stress, retirement, "
          "wiring and launcher; %d launcher, %d wiring and %d header mutants rejected%s"
          % (len(mutants), len(WIRING_MUTANTS), len(HEADER_MUTANTS),
             ", syntax-only spu_workload" if os.name == "nt" else ""))


if __name__ == "__main__":
    main()
