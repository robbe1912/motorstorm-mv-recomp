#!/usr/bin/env python3
"""Game-free checks for the PPU wait profile (PPU_WAIT_PROFILE=1).

1. Audits the vendor copy and scripts/run.py: the five blocking syscall
   entries bracket their wait with the profile, and the launcher sets the
   switch only with --profile-ppu-waits and records it. Mutants must fail.
2. Compiles the production header with an authored fixture: off by default;
   record fields; a measured wait; a nested begin replaces the first. Mutants
   of the header must fail.
3. Compiles the four syscall files with a syntax-only clang-cl pass.
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

SWITCH = "PPU_WAIT_PROFILE"
ARGUMENT = "ap.add_argument('--profile-ppu-waits',action='store_true',"
POP = "env.pop('PPU_WAIT_PROFILE',None)"
SET = "if args.profile_ppu_waits:env['PPU_WAIT_PROFILE']='1'"
RECORD = "if 'PPU_WAIT_PROFILE' in env:record['environment']['PPU_WAIT_PROFILE']=env['PPU_WAIT_PROFILE']"
FLAG = "record['profile_ppu_waits']=args.profile_ppu_waits"
HOOKS = {
    "sys_cond.c": ("sys_cond_wait", "cond_wait"),
    "sys_semaphore.c": (None, "semaphore_wait"),
    "sys_mutex.c": ("sys_mutex_lock", "mutex_lock"),
    "sys_event.c": ("sys_event_queue_receive", "event_queue_receive"),
}
EVENT_FLAG = ("sys_event_flag_wait", "event_flag_wait")

FIXTURE = r'''
#include <stdio.h>
#include <string.h>
#include "ppu_wait_profile.h"

typedef struct {
    unsigned long long thread_id;
    unsigned long long gpr[32];
    unsigned lr;
} ppu_context;

#define LV2_ARG_U32(ctx, i) ((unsigned)((ctx)->gpr[3 + (i)]))

#ifdef _WIN32
#include <windows.h>
static void wait_milliseconds(unsigned ms) { Sleep(ms); }
#else
#include <time.h>
static void wait_milliseconds(unsigned ms)
{
    struct timespec t;
    t.tv_sec = (time_t)(ms / 1000);
    t.tv_nsec = (long)((ms % 1000) * 1000000L);
    nanosleep(&t, NULL);
}
#endif

int main(int argc, char** argv)
{
    ppu_context ctx;
    const char* mode = argc > 1 ? argv[1] : "on";
    int brackets = 0;
    memset(&ctx, 0, sizeof ctx);
    ctx.thread_id = 7;
    ctx.lr = 0x00ABCDEFu;
    ctx.gpr[3] = 3;

    /* An end without a begin writes nothing. */
    ppu_wait_profile_end();

    if (!strcmp(mode, "sleep")) {
        /* A real wait of 40 ms inside one bracket. */
        PPU_WAIT_PROFILE_BEGIN(&ctx, "cond_wait", LV2_ARG_U32(&ctx, 0));
        wait_milliseconds(40);
        ppu_wait_profile_end();
        brackets = 1;
    } else if (!strcmp(mode, "nested")) {
        /* A second begin on the same thread replaces the first. */
        ctx.gpr[3] = 5;
        PPU_WAIT_PROFILE_BEGIN(&ctx, "semaphore_wait", LV2_ARG_U32(&ctx, 0));
        ctx.gpr[3] = 9;
        PPU_WAIT_PROFILE_BEGIN(&ctx, "mutex_lock", LV2_ARG_U32(&ctx, 0));
        ppu_wait_profile_end();
        /* The bracket is closed: a second end writes nothing. */
        ppu_wait_profile_end();
        brackets = 1;
    } else {
        /* "on" and "off": one bracket that returns at once. */
        PPU_WAIT_PROFILE_BEGIN(&ctx, "cond_wait", LV2_ARG_U32(&ctx, 0));
        ppu_wait_profile_end();
        brackets = 1;
    }
    /* After a closed bracket, an end writes nothing. */
    ppu_wait_profile_end();
    printf("brackets=%d\n", brackets);
    return 0;
}
'''

# One mutant per rule of the header: name, text to replace, replacement.
HEADER_MUTANTS = [
    ("gate", "if (!ppu_wait_profile_on()) {", "if (0) {"),
    ("start-as-finish", "t_ppu_wait_profile.lr, t_ppu_wait_profile.start, finished,",
     "t_ppu_wait_profile.lr, t_ppu_wait_profile.start, t_ppu_wait_profile.start,"),
    ("open-bracket-kept", "    t_ppu_wait_profile.active = 0;\n    finished = ppu_wait_profile_now();",
     "    finished = ppu_wait_profile_now();"),
    ("end-ignores-bracket", "    if (!t_ppu_wait_profile.active)\n        return;", "    if (0)\n        return;"),
    ("begin-never-opens", "    t_ppu_wait_profile.active = 1;", "    t_ppu_wait_profile.active = 0;"),
    ("any-value", "value[0] == '1' && value[1] == 0", "value[0] != 0"),
    ("call-site-lost", "    t_ppu_wait_profile.lr = lr;", "    t_ppu_wait_profile.lr = 0;"),
    ("nested-begin-ignored", "    if (!ppu_wait_profile_on()) {",
     "    if (!ppu_wait_profile_on() || t_ppu_wait_profile.active) {"),
]


def wrapper_pattern(wrapped, kind):
    """The public entry: begin with the object id, the wait, the end."""
    begin = re.escape('PPU_WAIT_PROFILE_BEGIN(ctx, "%s", LV2_ARG_U32(ctx, 0));' % kind)
    if wrapped is None:
        return (r'int64_t sys_semaphore_wait\(ppu_context\* ctx\)\s*\{\s*' + begin
                + r'\s*int64_t r = sys_semaphore_wait_impl\(ctx\);\s*ppu_wait_profile_end\(\);')
    return (r'int64_t %s\(ppu_context\* ctx\)\s*\{\s*' % wrapped + begin
            + r'\s*int64_t result = %s_impl\(ctx\);\s*ppu_wait_profile_end\(\);\s*return result;\s*\}' % wrapped)


def audit(sources, launcher):
    """`sources` maps the four syscall file names to their text."""
    for text in (ARGUMENT, POP, SET, RECORD, FLAG):
        assert launcher.count(text) == 1, "the launcher has one line: " + text
    assert launcher.index(POP) < launcher.index(SET) < launcher.index(RECORD), "the launcher clears, sets, records"
    hooks = dict(HOOKS)
    hooks["sys_event.c"] = [HOOKS["sys_event.c"], EVENT_FLAG]
    for name, entries in hooks.items():
        source = sources[name]
        assert source.count('#include "ppu_wait_profile.h"') == 1, name + ": one include"
        if not isinstance(entries, list):
            entries = [entries]
        for wrapped, kind in entries:
            begin = 'PPU_WAIT_PROFILE_BEGIN(ctx, "%s", LV2_ARG_U32(ctx, 0));' % kind
            assert source.count(begin) == 1, name + ": one begin with the object id: " + kind
            assert len(re.findall(wrapper_pattern(wrapped, kind), source)) == 1, \
                name + ": the entry brackets its wait: " + kind


def build(environment, work, header):
    work.mkdir(parents=True, exist_ok=True)
    (work / "ppu_wait_profile.h").write_text(header)
    source = work / "harness.c"
    source.write_text(FIXTURE)
    exe = work / "harness.exe"
    command = [environment["MV_CLANG"], "/nologo", "/O2", "/clang:-Wno-everything", "/I" + str(work),
               str(source), "/Fo" + str(work) + os.sep, "/Fe" + str(exe)]
    result = subprocess.run(command, cwd=work, env=environment, capture_output=True, text=True,
                            errors="replace", timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    return exe


def run(exe, mode, switch, environment):
    env = dict(environment)
    env.pop(SWITCH, None)
    if switch is not None:
        env[SWITCH] = switch
    result = subprocess.run([str(exe), mode], capture_output=True, text=True, env=env, timeout=30)
    lines = result.stderr.splitlines()
    records = [dict(re.findall(r"(\w+)=(\w+)", line)) for line in lines
               if line.startswith("[PPU_WAIT_PROFILE]")]
    other = [line for line in lines if not line.startswith("[PPU_WAIT_PROFILE]")]
    return result, records, other


def seconds(record):
    return (int(record["finished"]) - int(record["started"])) / int(record["frequency"])


def verify(exe, environment):
    for name, switch in (("off", None), ("zero", "0"), ("word", "yes")):
        result, records, other = run(exe, "on", switch, environment)
        assert result.returncode == 0 and result.stdout.strip() == "brackets=1", (name, result.stdout, result.stderr)
        assert not records and not other, (name + ": the default run writes no line", records, other)
    result, records, other = run(exe, "on", "1", environment)
    assert result.returncode == 0 and not other and len(records) == 1, (result.stdout, result.stderr, records)
    record = records[0]
    assert (record["tid"], record["kind"], record["id"], record["lr"]) == ("7", "cond_wait", "3", "00ABCDEF"), record
    assert int(record["frequency"]) > 0 and 0 <= seconds(record) < 1.0, record
    result, records, other = run(exe, "sleep", "1", environment)
    assert result.returncode == 0 and not other and len(records) == 1, (result.stdout, result.stderr, records)
    assert records[0]["kind"] == "cond_wait" and 0.030 <= seconds(records[0]) < 2.0, records[0]
    result, records, other = run(exe, "nested", "1", environment)
    assert result.returncode == 0 and not other and len(records) == 1, (result.stdout, result.stderr, records)
    assert (records[0]["kind"], records[0]["id"]) == ("mutex_lock", "9"), records[0]


def syntax_only(environment, path):
    command = [environment["MV_CLANG"], "/nologo", "/Zs", "/clang:-std=c17"]
    command += ["/I" + str(ROOT / "vendor/ps3recomp" / part)
                for part in ("include", "libs/video", "runtime", "third_party")]
    command.append(str(path.resolve()))
    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True,
                            errors="replace", timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", type=Path, default=ROOT / "vendor/ps3recomp/runtime/syscalls")
    parser.add_argument("--launcher", type=Path, default=ROOT / "scripts/run.py")
    args = parser.parse_args()
    launcher = args.launcher.read_text()
    sources = {name: (args.vendor / name).read_text() for name in HOOKS}
    header = (args.vendor / "ppu_wait_profile.h").read_text()
    audit(sources, launcher)
    mutants = [launcher.replace(line, "", 1) for line in (ARGUMENT, POP, SET, RECORD, FLAG)]
    mutants.append(launcher.replace("if args.profile_ppu_waits:", "if True:", 1))
    for name in sources:
        source = sources[name]
        changed = source.replace('#include "ppu_wait_profile.h"\n', "", 1)
        mutants.append((dict(sources, **{name: changed}), launcher))
    hooks = [(name, entry) for name, entry in HOOKS.items()]
    hooks.append(("sys_event.c", EVENT_FLAG))
    for name, (wrapped, kind) in hooks:
        source = sources[name]
        begin = 'PPU_WAIT_PROFILE_BEGIN(ctx, "%s", LV2_ARG_U32(ctx, 0));' % kind
        pattern = wrapper_pattern(wrapped, kind)
        match = re.search(pattern, source)
        assert match, (name, kind)
        without_end = source[:match.start()] + match.group(0).replace("ppu_wait_profile_end();", "", 1) \
            + source[match.end():]
        other_kind = "event_flag_wait" if kind != "event_flag_wait" else "cond_wait"
        wrong_id = source[:match.start()] + match.group(0).replace("LV2_ARG_U32(ctx, 0)", "0", 1) + source[match.end():]
        for changed in (without_end, source.replace(begin, begin.replace(kind, other_kind), 1), wrong_id):
            mutants.append((dict(sources, **{name: changed}), launcher))
    for index, mutant in enumerate(mutants):
        try:
            audit(mutant[0], mutant[1])
        except AssertionError:
            pass
        else:
            raise AssertionError("mutant %d accepted" % index)
    environment = project.build_environment()
    with tempfile.TemporaryDirectory(prefix="ppu-wait-profile-") as directory:
        root = Path(directory)
        verify(build(environment, root / "actual", header), environment)
        count = 0
        for name, anchor, replacement in HEADER_MUTANTS:
            assert header.count(anchor) == 1, (name, anchor)
            try:
                verify(build(environment, root / name, header.replace(anchor, replacement)), environment)
            except AssertionError:
                count += 1
            else:
                raise AssertionError("header mutant accepted: " + name)
    if os.name == "nt":
        for name in sources:
            syntax_only(environment, args.vendor / name)
    print("PASS actual wait profile: default off, switch values, record fields, measured wait, nested begin, "
          "five entries, launcher, %d audit mutants, %d header mutants, syntax-only syscalls"
          % (len(mutants), count))


if __name__ == "__main__":
    main()
