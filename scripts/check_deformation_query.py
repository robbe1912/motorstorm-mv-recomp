"""Compile the native query adapter against authored guest objects and callbacks."""

import hashlib
import json
import os
import re
import struct
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
if os.name == "nt":
    from project import build_environment

    os.environ.update(build_environment())



def captured_samples(stderr, cap=False):
    lines = re.findall(r"\[native-depth-input\] ([^\r\n]+)", stderr)
    records = [dict(field.split("=", 1) for field in line.split()) for line in lines]
    records.sort(key=lambda record: int(record["seq"]))
    assert records, "native input records missing"
    assert len(records) <= 64, "native input record cap exceeded"
    assert [int(record["seq"]) for record in records] == list(range(1, len(records) + 1))
    expected = {
        "manager": "00001000", "selector": "0030000f", "pixel": "00003000",
        "nj": "0", "point": "40000000/bf000000/40800000/3f800000",
        "row0": "3e000000/3f000000/3d800000/3a800000",
        "row1": "3e000000/3f000000/3e000000/3e7e0000",
        "xy": "3e808000/3f3f8000", "dims": "256/128", "bpp": "1",
        "base": "00007000", "offsets": "2040/2041/2140/2141",
        "fractions": "3e800000/3e800000", "mode": "1",
        "samples": "15/16/18/17", "snapshot": "1",
        "value": struct.pack(">d", struct.unpack(">f", bytes.fromhex("3dafafb0"))[0]).hex(),
    }
    for key, value in expected.items():
        assert records[0][key] == value, (key, records[0][key], value)
    if cap:
        assert len(records) == 64, "native input records stopped before their cap"
    else:
        assert len(records) == 10, "successful query record coverage"
        assert [record["mode"] for record in records[:8]] == ["1"] * 4 + ["0"] * 4
        assert [record["nj"] for record in records[8:]] == ["0", "1"]
        assert records[8]["point"] == records[9]["point"] == "00000001/00000000/00000000/3f800000"
        assert records[8]["xy"] != records[9]["xy"], "captured NJ projection differs"
        assert records[8]["value"] != records[9]["value"], "captured NJ result differs"
        assert [record["snapshot"] for record in records[:4]] == ["1", "1", "0", "0"], "snapshot/fallback records differ"
    return records


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
            "/D_CRT_SECURE_NO_WARNINGS",
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
            *[f"-I{p}" for p in includes[:2]],
            "-isystem", str(includes[2]),
            "-isystem", str(includes[3]),
            str(source),
            str(ROOT / "src/motorstorm/deformation_depth.cpp"),
            str(fixture),
            "-o",
            str(exe),
        ]
    results = []

    def run(args, timeout, succeeds=True, capture=True):
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "MS_DEPTH_OBSERVER": "1" if capture else "0"},
        )
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

        return result

    run(command, 120)
    for fp_mode in range(16):
        for deferred in range(2):
            result = run([str(exe), str(fp_mode), str(deferred)], 30)
            captured_samples(result.stderr)
    captured_samples(run([str(exe), "0", "0", "capture-cap"], 30).stderr, cap=True)
    quiet = run([str(exe), "0", "0"], 30, capture=False)
    assert "[native-depth-input]" not in quiet.stderr, "capture disabled control"
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
        "retained projection": original.replace("func_006CCF6C", "func_0029BE08"),
        "wrong homogeneous coordinate": original.replace(
            "projection.point[3] = read_float(vm_read32(toc - 0x2c90) & ~std::uint32_t(15));",
            "projection.point[3] = 0.0f;", 1,
        ),
        "unaligned matrix": original.replace(
            "matrix & ~std::uint32_t(15)", "matrix", 1,
        ),
        "wrong matrix row": original.replace("row * 16 + word * 4", "row * 8 + word * 4", 1),
        "ignored guest NJ": original.replace(
            "(context->vscr & (1u << 16)) != 0", "false", 1,
        ),
    }
    capture_mutants = {
        "captured point differs": original.replace("bits(projection.point[0])", "bits(0.0f)", 1),
        "capture cap exceeded": original.replace("sample_number <= 64", "sample_number <= 128", 1),
        "capture ignores selector": original.replace(
            "capture_inputs && sample_number <= 64",
            "(capture_inputs || sample_number != 0) && sample_number <= 64", 1,
        ),
        "capture hides fallback": original.replace("static_cast<unsigned>(snapshot),", "1u,", 1),
    }
    mutants.update(capture_mutants)
    rejected = []
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
        if label not in capture_mutants:
            run([str(candidate_exe), "0", "1"], 30, succeeds=False)
        else:
            args = [str(candidate_exe), "0", "1"]
            if label == "capture cap exceeded":
                args.append("capture-cap")
            result = run(args, 30, capture=label != "capture ignores selector")
            try:
                if label == "capture ignores selector":
                    assert "[native-depth-input]" not in result.stderr
                else:
                    captured_samples(result.stderr, cap=label == "capture cap exceeded")
            except AssertionError:
                pass
            else:
                raise AssertionError(f"Surviving capture mutant: {label}")
        rejected.append(label)
    report_path = out / "result.json"
    report = json.loads(report_path.read_text())
    report.update(
        rejected_mutants=rejected,
        fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
        fp_modes=16,
        capture_limit=64,
        capture_disabled_checked=True,
    )
    report_path.write_text(json.dumps(report, indent=2))
    print(
        "PASS typed projection, query control, acquisition/fallback, cleanup and ABI; 16 FP modes, twelve semantic and four capture mutants rejected"
    )
    print(out / "result.json")


if __name__ == "__main__":
    main()
