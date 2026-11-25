"""Check the opt-in Havok PPU worker count switch (--havok-threads).

Parts:
1. Launcher lines. Each line must occur once and in order. Mutants change one line.
2. Registration lines of the binding script, the CMake module, the build wrapper
   and the hook. Mutants change one line.
3. The hook with an inline fixture. The fixture stands in for the lifted guest
   function. Mutants change the hook source.
4. The identity of the hooked lifted body, and a syntax-only pass of the hook
   with the real generated header. Both need a lifted tree.
No game runs.

Run: python scripts/check_havok_threads.py [--generated <lifted tree>/ppu]
Without --generated, the script uses each lifted tree below build/generated.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import native_game_binding as binding  # noqa: E402

LAUNCHER = ROOT / "scripts/run.py"
HOOK = ROOT / "src/motorstorm/havok_threads.cpp"
CMAKE = ROOT / "src/motorstorm/native_world.cmake"
BUILD = ROOT / "scripts/project.py"
SCRIPT = ROOT / "scripts/native_game_binding.py"
VENDOR = ROOT / "vendor/ps3recomp/include"

SYMBOL = "func_00A01220"
ORIGINAL = "game_original_init_multithreading"
NATIVE = "motorstorm_havok_threads"
BODY_SHA256 = "9a263a15562ae116cbd6d9c252383733477e82c9811a7f8b7f27bc74622e443e"
VARIABLE = "MS_HAVOK_THREADS"
MESSAGE = "MS_HAVOK_THREADS must be 0 or 1..6"

# 1. Launcher lines.
ARGUMENT = "    ap.add_argument('--havok-threads',type=int,default=0,"
RANGE = ("    if not 0<=args.havok_threads<=6: raise SystemExit('Havok thread count must be 0 "
         "(game count) or 1..6; no process launched')")
GUARD = ("    if args.havok_threads:\n"
         "        identity=admitted['build_identity']\n"
         "        if not identity.get('havok_threads') or identity.get('sha256') != admitted['exe_sha256']:\n"
         "            raise SystemExit('Havok thread count above 0 requires a matching "
         "--havok-threads build; no process launched')")
SET = "    env['MS_HAVOK_THREADS']=str(args.havok_threads)"
RECORD = "    record['environment']['MS_HAVOK_THREADS'] = env['MS_HAVOK_THREADS']"
LAUNCHER_LINES = (("argument", ARGUMENT), ("range", RANGE), ("build guard", GUARD),
                  ("set", SET), ("record", RECORD))
LAUNCHER_MUTANTS = {
    "no-argument": (ARGUMENT, "    # removed\n"),
    "argument-default-four": ("'--havok-threads',type=int,default=0,",
                              "'--havok-threads',type=int,default=4,"),
    "no-range": (RANGE, ""),
    "range-to-sixty": ("if not 0<=args.havok_threads<=6:", "if not 0<=args.havok_threads<=60:"),
    "no-build-guard": (GUARD, "    pass"),
    "guard-off": (GUARD, GUARD.replace("    if args.havok_threads:", "    if False:")),
    "guard-other-flag": (GUARD, GUARD.replace("identity.get('havok_threads')",
                                              "identity.get('native_visibility')")),
    "guard-any-executable": (GUARD, GUARD.replace(
        " or identity.get('sha256') != admitted['exe_sha256']", "")),
    "no-set": (SET, ""),
    "set-inherited": (SET, "    env['MS_HAVOK_THREADS']=os.environ.get('MS_HAVOK_THREADS','0')"),
    "no-record": (RECORD, ""),
    "record-constant": (RECORD, "    record['environment']['MS_HAVOK_THREADS'] = '0'"),
}


def audit_launcher(text):
    """Each launcher line occurs once. The order is argument, range, guard, set, record."""
    places = []
    for name, line in LAUNCHER_LINES:
        assert text.count(line) == 1, f"launcher: {name} occurs {text.count(line)} times"
        places.append(text.index(line))
    assert places == sorted(places), "launcher: wrong order"


# 2. Registration lines.
CMAKE_OPTION = 'option(PORT_HAVOK_THREADS "Bind the opt-in Havok PPU worker count switch" OFF)'
CMAKE_SKIP = " AND NOT PORT_HAVOK_THREADS"
CMAKE_BINDING_OPTION = "        list(APPEND binding_options --havok-threads)"
CMAKE_SOURCE = ('        list(APPEND baseline_sources '
                '"${MOTORSTORM_NATIVE_SOURCE_DIR}/havok_threads.cpp")')
BUILD_OPTION = "b.add_argument('--havok-threads',action='store_true'"
BUILD_REQUEST = ("havok_threads = args.havok_threads and "
                 "hashlib.sha256(c['elf'].read_bytes()).hexdigest() == PRODUCTION.elf_sha256")
BUILD_DEFINE = "f'-DPORT_HAVOK_THREADS={\"ON\" if havok_threads else \"OFF\"}',"
BUILD_FLAG = "identity['havok_threads']=havok_threads"
BUILD_RECORD = "if menu_boot or havok_threads or args.native_world_transforms"
CONTRACT = ("HAVOK_THREADS = Contract(PRODUCTION.elf_sha256,\n"
            f"    '{BODY_SHA256}',\n"
            f"    '{SYMBOL}', '{ORIGINAL}', '{NATIVE}')")
KNOWN = "MENU_LANGUAGE, HAVOK_THREADS)"
SCRIPT_OPTION = "parser.add_argument('--havok-threads', action='store_true')"
SCRIPT_SELECT = "        selected.append(HAVOK_THREADS)"
HOOK_ORIGINAL = f"void {ORIGINAL}(ppu_context*);"
HOOK_ENTRY = f"void {NATIVE}(ppu_context* context) {{"


def audit_registration(cmake, build, script, hook):
    """Each registration line occurs once. Both early returns of the CMake module know the option."""
    for name, text, line in (
        ("cmake option", cmake, CMAKE_OPTION),
        ("cmake binding option", cmake, CMAKE_BINDING_OPTION),
        ("cmake source", cmake, CMAKE_SOURCE),
        ("build option", build, BUILD_OPTION),
        ("build request", build, BUILD_REQUEST),
        ("build define", build, BUILD_DEFINE),
        ("build flag", build, BUILD_FLAG),
        ("build record", build, BUILD_RECORD),
        ("binding contract", script, CONTRACT),
        ("binding known list", script, KNOWN),
        ("binding option", script, SCRIPT_OPTION),
        ("binding select", script, SCRIPT_SELECT),
        ("hook original", hook, HOOK_ORIGINAL),
        ("hook entry", hook, HOOK_ENTRY),
    ):
        assert text.count(line) == 1, f"{name} occurs {text.count(line)} times"
    assert cmake.count(CMAKE_SKIP) == 2, f"cmake early returns: {cmake.count(CMAKE_SKIP)}"
    contract = binding.HAVOK_THREADS
    assert (contract.elf_sha256, contract.body_sha256, contract.symbol, contract.original,
            contract.native) == (binding.PRODUCTION.elf_sha256, BODY_SHA256, SYMBOL, ORIGINAL, NATIVE)


def changed(text, replacements):
    """Apply each (before, after) pair. Each text must occur once."""
    for before, after in replacements:
        assert text.count(before) == 1, f"{before!r} occurs {text.count(before)} times"
        text = text.replace(before, after)
    return text


def rejects(texts, audit, mutants):
    """Each mutant must fail the audit. The function returns the names of the rejected mutants."""
    names = []
    for name, key, *replacements in mutants:
        mutant = dict(texts)
        mutant[key] = changed(texts[key], replacements)
        assert mutant[key] != texts[key], name
        try:
            audit(mutant)
        except AssertionError:
            names.append(name)
        else:
            raise AssertionError(f"mutant survived: {name}")
    return names


REGISTRATION_MUTANTS = (
    ("cmake option default on", "cmake", (CMAKE_OPTION, CMAKE_OPTION.replace(" OFF)", " ON)"))),
    ("cmake bind step skips the option", "cmake",
     ("NOT PORT_NATIVE_VISIBILITY AND NOT PORT_NATIVE_PCM_CUBIC AND NOT PORT_DEFORMATION_DEPTH_OBSERVER"
      " AND NOT PORT_QUEUE_CALL_OBSERVATION AND NOT PORT_NATIVE_MENU_BOOT AND NOT PORT_HAVOK_THREADS)",
      "NOT PORT_NATIVE_VISIBILITY AND NOT PORT_NATIVE_PCM_CUBIC AND NOT PORT_DEFORMATION_DEPTH_OBSERVER"
      " AND NOT PORT_QUEUE_CALL_OBSERVATION AND NOT PORT_NATIVE_MENU_BOOT)")),
    ("cmake configure step skips the option", "cmake",
     ("NOT PORT_NATIVE_PARTICLE_THRESHOLDS AND NOT PORT_NATIVE_PCM_CUBIC AND NOT PORT_DEFORMATION_DEPTH_OBSERVER"
      " AND NOT PORT_QUEUE_CALL_OBSERVATION AND NOT PORT_NATIVE_MENU_BOOT AND NOT PORT_HAVOK_THREADS)",
      "NOT PORT_NATIVE_PARTICLE_THRESHOLDS AND NOT PORT_NATIVE_PCM_CUBIC AND NOT PORT_DEFORMATION_DEPTH_OBSERVER"
      " AND NOT PORT_QUEUE_CALL_OBSERVATION AND NOT PORT_NATIVE_MENU_BOOT)")),
    ("cmake without binding option", "cmake", (CMAKE_BINDING_OPTION, "")),
    ("cmake without source", "cmake", (CMAKE_SOURCE, "")),
    ("build without option", "build", (BUILD_OPTION, "b.add_argument('--havok-workers',action='store_true'")),
    ("build binds any ELF", "build", (BUILD_REQUEST, "havok_threads = args.havok_threads")),
    ("build without define", "build", (BUILD_DEFINE, "")),
    ("build without identity flag", "build", (BUILD_FLAG, "")),
    ("build without binding record", "build", (BUILD_RECORD, "if menu_boot or args.native_world_transforms")),
    ("binding of another function", "script", (CONTRACT, CONTRACT.replace(SYMBOL, "func_00A012E8"))),
    ("binding of another body", "script", (CONTRACT, CONTRACT.replace(BODY_SHA256, "0" * 64))),
    ("binding with another original", "script", (CONTRACT, CONTRACT.replace(ORIGINAL, "game_original_workers"))),
    ("binding with another entry", "script", (CONTRACT, CONTRACT.replace(NATIVE, "motorstorm_havok_workers"))),
    ("binding not known", "script", (KNOWN, "MENU_LANGUAGE)")),
    ("binding without option", "script", (SCRIPT_OPTION, "")),
    ("binding never selected", "script", (SCRIPT_SELECT, "")),
    ("hook without original", "hook", (HOOK_ORIGINAL, "")),
    ("hook with another entry", "hook", (HOOK_ENTRY, "void motorstorm_havok_workers(ppu_context* context) {")),
)

# 3. The hook with the fixture.
HEADER = ("#pragma once\n#include <cstdint>\n"
          "struct ppu_context { std::uint64_t gpr[32]{}, lr{}; };\n"
          "std::uint32_t vm_read32(std::uint64_t address);\n")
FIXTURE = r'''#include "ppu_recomp.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <string>

void motorstorm_havok_threads(ppu_context*);

namespace {
std::uint32_t util[0x218 / 4];  // hkMultithreadingUtil object
int calls;
std::uint64_t seen[3];          // r3, r4 and r5 at the call
}

// Stand-in for the lifted hkMultithreadingUtil::initMultithreading 0xA01220.
// The guest clamps the count to 6 (0xA0124C) and stores m_numThreads.
// r3, r4 and r5 are volatile. The stand-in clears them, as a real callee can.
void game_original_init_multithreading(ppu_context* context) {
    ++calls;
    seen[0] = context->gpr[3];
    seen[1] = context->gpr[4];
    seen[2] = context->gpr[5];
    std::uint64_t count = seen[2];
    if (count > 6) count = 6;
    util[0x214 / 4] = static_cast<std::uint32_t>(count);
    context->gpr[3] = context->gpr[4] = context->gpr[5] = 0;
}

std::uint32_t vm_read32(std::uint64_t address) {
    const std::uint64_t base = reinterpret_cast<std::uint64_t>(util);
    if (address != base + 0x214) {
        std::fprintf(stderr, "FIXTURE bad read %llx\n", static_cast<unsigned long long>(address));
        std::abort();
    }
    return util[0x214 / 4];
}

int main(int argc, char** argv) {
    const std::string mode = argc > 1 ? argv[1] : "";
    ppu_context context{};
    context.gpr[3] = reinterpret_cast<std::uint64_t>(util);
    context.gpr[4] = 0x1000;                          // hkWorld*
    context.gpr[5] = mode == "clamp" ? 9 : 2;         // game count
    try {
        motorstorm_havok_threads(&context);
    } catch (const std::exception& error) {
        std::printf("calls=%d message=%s\n", calls, error.what());
        return 0;
    }
    std::printf("calls=%d r3=%d r4=%d r5=%llu\n", calls,
                seen[0] == reinterpret_cast<std::uint64_t>(util), seen[1] == 0x1000,
                static_cast<unsigned long long>(seen[2]));
    return 0;
}
'''
RECORD_LINE = "[HAVOK_THREADS] game=%u set=%u workers=%u\n"
CALLED = "calls=1 r3=1 r4=1 r5=%d\n"
LINE = "[HAVOK_THREADS] game=%d set=%d workers=%d\n"
REJECTED = f"calls=0 message={MESSAGE}\n"
CASES = {
    # name: (fixture argument, MS_HAVOK_THREADS or None, stdout, stderr)
    "game": ("", None, CALLED % 2, LINE % (2, 0, 2)),
    "game with text 0": ("", "0", CALLED % 2, LINE % (2, 0, 2)),
    "one": ("", "1", CALLED % 1, LINE % (2, 1, 1)),
    "four": ("", "4", CALLED % 4, LINE % (2, 4, 4)),
    "six": ("", "6", CALLED % 6, LINE % (2, 6, 6)),
    "request clamped by the guest": ("clamp", "6", CALLED % 6, LINE % (9, 6, 6)),
    "game count clamped by the guest": ("clamp", None, CALLED % 9, LINE % (9, 0, 6)),
}
for value in ("7", "-1", "abc", "", "4x", "0x4", "1.0"):
    CASES[f"reject {value or 'empty'}"] = ("", value, REJECTED, "")

HOOK_MUTANTS = {
    "count not applied": [("    if (set != 0) context->gpr[5] = set;", "    (void)set;")],
    "zero overrides the game": [("    if (set != 0) context->gpr[5] = set;",
                                "    context->gpr[5] = set;")],
    "read after the call": [("vm_read32(util + num_threads_offset)",
                             "vm_read32(context->gpr[3] + num_threads_offset)"),
                            ("    const std::uint64_t util = context->gpr[3];",
                             "    const std::uint64_t util = context->gpr[3]; (void)util;")],
    "offset low": [("num_threads_offset = 0x214", "num_threads_offset = 0x210")],
    "limit sixty": [("count > static_cast<long>(worker_limit)",
                     "count > static_cast<long>(worker_limit + 54)")],
    "limit five": [("count > static_cast<long>(worker_limit)",
                    "count > static_cast<long>(worker_limit - 1)")],
    "zero text rejected": [('if (!text || std::strcmp(text, "0") == 0) return 0u;',
                            "if (!text) return 0u;")],
    "trailing text accepted": [("if (*end != '\\0' || count < 1", "if (count < 1")],
    "negative accepted": [("|| count < 1 ||", "||")],
    "original not called": [("    game_original_init_multithreading(context);", "    (void)context;")],
    "game reads the request": [("static_cast<std::uint32_t>(context->gpr[5]);", "requested();")],
    "line repeats the game count": [('"[HAVOK_THREADS] game=%u set=%u workers=%u\\n", game, set, workers',
                                     '"[HAVOK_THREADS] game=%u set=%u workers=%u\\n", game, game, workers')],
    "line on stdout": [('std::fprintf(stderr, "[HAVOK_THREADS]',
                        'std::fprintf(stdout, "[HAVOK_THREADS]')],
    "other variable": [(f'std::getenv("{VARIABLE}")', 'std::getenv("MS_HAVOK_THREAD")')],
    "other message": [(f'"{MESSAGE}"', f'"{VARIABLE} must be 0..6"')],
    "workers not read": [("vm_read32(util + num_threads_offset)",
                          "vm_read32(util + num_threads_offset * 0)")],
}


def toolchain():
    environment = os.environ.copy()
    if os.name == "nt":
        import project
        environment.update(project.build_environment())
    environment.pop(VARIABLE, None)
    compiler = environment.get("MV_CLANG") or environment.get("CXX") or "c++"
    name = Path(compiler).name.lower()
    return environment, compiler, name in {"cl", "cl.exe", "clang-cl", "clang-cl.exe"}


def compile_command(compiler, msvc, work, exe, include, sources, syntax_only):
    if msvc:
        command = [compiler, "/nologo", "/std:c++17", "/EHsc", "/W4", "/WX", "/D_CRT_SECURE_NO_WARNINGS"]
        command += ["/Zs"] if syntax_only else [f"/Fo{work}{os.sep}", f"/Fe:{exe}"]
    else:
        command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror"]
        command += ["-fsyntax-only"] if syntax_only else ["-o", str(exe)]
    for directory in include:
        command += [f"/I{directory}"] if msvc else ["-I", str(directory)]
    return [*command, *map(str, sources)]


def failing_cases(exe, environment):
    """Return the names of the cases that fail."""
    failed = []
    for name, (argument, value, out, err) in CASES.items():
        child = dict(environment)
        child.pop(VARIABLE, None)
        if value is not None:
            child[VARIABLE] = value
        arguments = [str(exe)] + ([argument] if argument else [])
        run = subprocess.run(arguments, env=child, capture_output=True, text=True, timeout=30)
        if (run.returncode, run.stdout, run.stderr) != (0, out, err):
            failed.append(name)
    return failed


# 4. Lifted trees.
def lifted_trees(argument):
    if argument:
        return [argument.resolve()]
    return sorted(path.parent for path in (ROOT / "build/generated").glob("*/ppu/ppu_recomp.h"))


def audit_body(tree):
    """One unit of the tree defines the function. Its body has the reference identity.
    The binding renames it and appends the entry."""
    units = []
    pattern = re.compile(rb"\bvoid\s+" + SYMBOL.encode() + rb"\s*\(\s*ppu_context\s*\*\s*ctx\s*\)\s*\{")
    for path in sorted(tree.glob("*.c*")):
        source = path.read_bytes()
        if not pattern.search(source):
            continue
        transformed = binding.transform(source, binding.HAVOK_THREADS)
        assert transformed.count(f"void {ORIGINAL}(ppu_context* ctx) {{".encode()) == 1, path
        assert transformed.count(
            f"void {SYMBOL}(ppu_context* ctx) {{ {NATIVE}(ctx); }}".encode()) == 1, path
        units.append(path.name)
    assert len(units) == 1, f"{tree}: {len(units)} units define {SYMBOL}"
    return units[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated", type=Path,
                        help="lifted tree, the directory that holds ppu_recomp.h")
    argument = parser.parse_args().generated
    out = ROOT / "build/self-tests/havok-threads"
    out.mkdir(parents=True, exist_ok=True)

    launcher = LAUNCHER.read_text(encoding="utf-8")
    audit_launcher(launcher)
    launcher_mutants = rejects({"launcher": launcher}, lambda t: audit_launcher(t["launcher"]),
                               [(name, "launcher", pair) for name, pair in LAUNCHER_MUTANTS.items()])

    texts = {"cmake": CMAKE.read_text(encoding="utf-8"), "build": BUILD.read_text(encoding="utf-8"),
             "script": SCRIPT.read_text(encoding="utf-8"), "hook": HOOK.read_text(encoding="utf-8")}
    audit_registration(texts["cmake"], texts["build"], texts["script"], texts["hook"])
    registration_mutants = rejects(
        texts, lambda t: audit_registration(t["cmake"], t["build"], t["script"], t["hook"]),
        REGISTRATION_MUTANTS)

    environment, compiler, msvc = toolchain()
    (out / "ppu_recomp.h").write_text(HEADER, encoding="utf-8")
    fixture = out / "fixture.cpp"
    fixture.write_text(FIXTURE, encoding="utf-8")
    exe = out / ("fixture.exe" if os.name == "nt" else "fixture")
    command = compile_command(compiler, msvc, out, exe, [out], [HOOK, fixture], False)
    build = subprocess.run(command, env=environment, capture_output=True, text=True)
    (out / "build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
    assert build.returncode == 0, build.stdout + build.stderr
    assert failing_cases(exe, environment) == [], "hook fails a case"

    hook_mutants = []
    for name, replacements in HOOK_MUTANTS.items():
        mutant = out / "mutant.cpp"
        mutant.write_text(changed(texts["hook"], replacements), encoding="utf-8")
        built = subprocess.run(compile_command(compiler, msvc, out, exe, [out], [mutant, fixture], False),
                               env=environment, capture_output=True, text=True)
        assert built.returncode == 0, f"{name}: {built.stdout + built.stderr}"
        assert failing_cases(exe, environment), f"mutant survived: {name}"
        hook_mutants.append(name)

    trees = lifted_trees(argument)
    units = [audit_body(tree) for tree in trees]
    for tree in trees:
        checked = subprocess.run(
            compile_command(compiler, msvc, out, exe, [tree, VENDOR], [HOOK], True),
            env=environment, capture_output=True, text=True)
        assert checked.returncode == 0, f"{tree}: {checked.stdout + checked.stderr}"

    (out / "result.json").write_text(json.dumps(dict(
        commands=[command], cases=CASES, launcher_mutants=launcher_mutants,
        registration_mutants=registration_mutants, hook_mutants=hook_mutants,
        lifted_units=[str(tree / unit) for tree, unit in zip(trees, units)]), indent=2),
        encoding="utf-8")
    lifted = (f"lifted body and real-header syntax pass in {len(trees)} tree(s)"
              if trees else "no lifted tree: body identity and real-header syntax pass not run")
    print(f"PASS Havok worker count switch: {len(CASES)} cases, {len(LAUNCHER_MUTANTS)} launcher "
          f"mutants, {len(REGISTRATION_MUTANTS)} registration mutants, {len(HOOK_MUTANTS)} hook "
          f"mutants; {lifted}")


if __name__ == "__main__":
    main()
