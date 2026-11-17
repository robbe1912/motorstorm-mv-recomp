"""Check native startup policy using authored calls and retained callback controls."""

import json
import hashlib
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "build/self-tests/menu-boot"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ppu_recomp.h").write_text(
        "#pragma once\n#include <cstdint>\n"
        "struct ppu_context { std::uint64_t gpr[32]{}, lr{}; };\n"
        "",
        encoding="utf-8",
    )
    env = os.environ.copy()
    if os.name == "nt":
        from project import build_environment

        env.update(build_environment())
    compiler = env.get("MV_CLANG") or env.get("CXX") or "c++"
    msvc = Path(compiler).name.lower() in {"cl", "cl.exe", "clang-cl", "clang-cl.exe"}
    exe = out / ("fixture.exe" if os.name == "nt" else "fixture")
    sources = [
        ROOT / "src/motorstorm/menu_boot.cpp",
        ROOT / "scripts/fixtures/menu_boot_fixture.cpp",
    ]
    if msvc:
        command = [
            compiler,
            "/nologo",
            "/std:c++17",
            "/EHsc",
            "/W4",
            "/WX",
            "/D_CRT_SECURE_NO_WARNINGS",
            f"/I{out}",
            *map(str, sources),
            f"/Fe:{exe}",
            f"/Fo{out}{os.sep}",
        ]
    else:
        command = [
            compiler,
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(out),
            *map(str, sources),
            "-o",
            str(exe),
        ]
    build = subprocess.run(command, env=env, text=True, capture_output=True)
    (out / "build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
    assert build.returncode == 0, build.stderr
    results = []
    for mode in ("video", "language", "original"):
        for deferred in (False, True):
            child = dict(env, MS_BOOT_MENU="0" if mode == "original" else "1")
            args = [str(exe), mode] + (["deferred"] if deferred else [])
            run = subprocess.run(args, env=child, text=True, capture_output=True)
            results.append(
                dict(
                    mode=mode,
                    deferred=deferred,
                    returncode=run.returncode,
                    stdout=run.stdout,
                    stderr=run.stderr,
                )
            )
            assert run.returncode == 0, run.stderr
    unset = env.copy()
    unset.pop("MS_BOOT_MENU", None)
    assert (
        subprocess.run([str(exe), "video"], env=unset, capture_output=True).returncode
        == 0
    )
    invalid = dict(env, MS_BOOT_MENU="invalid")
    invalid_run = subprocess.run([str(exe), "video"], env=invalid, capture_output=True)
    assert (
        invalid_run.returncode != 0
        and b"MS_BOOT_MENU must be 0 or 1" in invalid_run.stderr
    )
    original = sources[0].read_text(encoding="utf-8")
    mutations = {
        "all-callers": (
            "opening_caller(context->lr)",
            "(opening_caller(context->lr) || true)",
        ),
        "wrong-caller": ("case 0x50da44:", "case 0x50da48:"),
        "no-close": ("func_0050C5A0(context);", "(void)context;"),
        "repeat-opening": (
            "!opening_skipped.exchange(true, std::memory_order_acq_rel)",
            "true",
        ),
        "ignored-original-mode": (
            'return !mode || std::strcmp(mode, "0") != 0;',
            "return true;",
        ),
        "language-accept-omitted": ("func_005340A8(context);", "context->gpr[3] = 4;"),
        "foreign-language-caller": ("context->lr == 0x56bec0", "true"),
        "wrong-language-event": (
            "static_cast<std::uint32_t>(context->gpr[4]) == 0x30",
            "true",
        ),
    }
    rejected = []
    for name, (before, after) in mutations.items():
        assert original.count(before) == 1, name
        mutant = out / f"{name}.cpp"
        mutant.write_text(original.replace(before, after), encoding="utf-8")
        mutant_command = [
            str(mutant) if item == str(sources[0]) else item for item in command
        ]
        built = subprocess.run(mutant_command, env=env, text=True, capture_output=True)
        (out / f"{name}-build.log").write_text(
            built.stdout + built.stderr, encoding="utf-8"
        )
        assert built.returncode == 0, name
        failures = []
        for mode in ("video", "language", "original"):
            child = dict(env, MS_BOOT_MENU="0" if mode == "original" else "1")
            run = subprocess.run(
                [str(exe), mode], env=child, text=True, capture_output=True
            )
            failures.append(run.returncode != 0)
            (out / f"{name}-{mode}.log").write_text(
                run.stdout + run.stderr, encoding="utf-8"
            )
        assert any(failures), name
        rejected.append(name)
    report = dict(
        commands=[command],
        cases=results,
        mutants=rejected,
        sources={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources
        },
        native_title_verified=False,
    )
    (out / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS native menu boot, original/deferred controls and eight mutants")


if __name__ == "__main__":
    main()
