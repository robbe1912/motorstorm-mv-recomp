"""Compile the native query adapter against authored guest objects and callbacks."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
if os.name == "nt":
    from project import build_environment

    os.environ.update(build_environment())


def main():
    out = ROOT / "temp/checks" / f"deformation-query-{time.time_ns()}"
    out.mkdir(parents=True)
    (out / "ppu_recomp.h").write_text("""#pragma once
#include "ppu_context.h"
#include <cstdint>
std::uint8_t vm_read8(std::uint64_t);
std::uint32_t vm_read32(std::uint64_t);
std::uint64_t vm_read64(std::uint64_t);
void vm_write32(std::uint64_t, std::uint32_t);
void vm_write64(std::uint64_t, std::uint64_t);
extern "C" void ps3_indirect_call(ppu_context*);
""")
    compiler = (
        os.environ.get("MV_CLANG")
        if os.name == "nt"
        else shutil.which("clang++") or shutil.which("g++")
    )
    assert compiler, "C++ compiler unavailable"
    source = ROOT / "src/motorstorm/deformation_query.cpp"
    fixture = ROOT / "scripts/fixtures/deformation_query_fixture.cpp"
    exe = out / ("query.exe" if os.name == "nt" else "query")
    includes = [
        out,
        ROOT / "src/motorstorm",
        ROOT / "vendor/ps3recomp/include",
        ROOT / "vendor/ps3recomp/runtime/ppu",
    ]
    if os.name == "nt":
        command = [
            compiler,
            "/nologo",
            "/std:c++20",
            "/O2",
            "/EHsc",
            "/W4",
            "/WX",
            "/fp:strict",
            *[f"/I{p}" for p in includes],
            str(source),
            str(ROOT / "src/motorstorm/deformation_depth.cpp"),
            str(fixture),
            f"/Fe{exe}",
            f"/Fo{out}\\",
        ]
    else:
        command = [
            compiler,
            "-std=c++20",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-frounding-math",
            "-ffp-contract=off",
            *[f"-I{p}" for p in includes],
            str(source),
            str(ROOT / "src/motorstorm/deformation_depth.cpp"),
            str(fixture),
            "-o",
            str(exe),
        ]
    results = []

    def run(args, timeout, succeeds=True):
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        results.append(
            dict(
                command=args,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        )
        (out / "result.json").write_text(
            json.dumps(
                dict(
                    commands=results,
                    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                ),
                indent=2,
            )
        )
        if succeeds:
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            assert result.returncode != 0 and "query check failed:" in result.stderr, (
                result.stdout + result.stderr
            )

    run(command, 120)
    for fp_mode in range(16):
        for deferred in range(2):
            run([str(exe), str(fp_mode), str(deferred)], 30)
    original = source.read_text()
    mutants = {
        "missing retained completion": original.replace(
            "complete_retained_calls(context);", "(void)&complete_retained_calls;"
        ),
        "missing cache reset": original.replace(
            "vm_write32(std::uint64_t(manager) + 0x4c, 0);", "(void)manager;", 1
        ),
        "missing Unlock": original.replace(
            "call_virtual(context, object, 0x18, 0x0029cb6c);", ";", 1
        ),
        "wrong stride": original.replace(" >> 3;", " >> 2;", 1),
        "wrong result": original.replace(
            "result = motorstorm::game::sample_deformation_depth(patch, mode);",
            "result = motorstorm::game::sample_deformation_depth(patch, mode) + 1;",
            1,
        ),
        "missing TOC restore": original.replace(
            "context->gpr[2] = toc;", "context->gpr[2] = toc + 4;"
        ),
        "hidden snapshot failure": original.replace(
            "status == VM_READ_SNAPSHOT_UNAVAILABLE)",
            "status == VM_READ_SNAPSHOT_UNAVAILABLE || status == VM_READ_SNAPSHOT_FAILED)",
            1,
        ),
    }
    for index, (label, changed) in enumerate(mutants.items()):
        assert changed != original, label
        directory = out / f"mutant-{index}"
        directory.mkdir()
        candidate = directory / "candidate.cpp"
        candidate.write_text(changed)
        candidate_exe = directory / exe.name
        candidate_command = [
            str(candidate)
            if arg == str(source)
            else str(candidate_exe)
            if arg == str(exe)
            else arg.replace(str(out), str(directory))
            if arg.startswith(("/Fe", "/Fo"))
            else arg
            for arg in command
        ]
        run(candidate_command, 120)
        run([str(candidate_exe), "0", "1"], 30, succeeds=False)
    print(
        "PASS native query control, reference outputs, acquisition/fallback, cleanup and ABI; 16 FP modes, seven mutants rejected"
    )
    print(out / "result.json")


if __name__ == "__main__":
    main()
