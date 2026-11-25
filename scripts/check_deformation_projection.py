"""Check finite projection bits, NaN classification, and caller FP-state controls."""

from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import time

from check_ppu_vmx_fused import finite, flush, reference, rounded

ROOT = Path(__file__).resolve().parents[1]


def nan(bits):
    return (bits & 0x7fffffff) > 0x7f800000


def add(a, b):
    if nan(a) or nan(b):
        return 0x7fc00000
    if (a & 0x7fffffff) == 0x7f800000:
        return 0x7fc00000 if b == (a ^ 0x80000000) else a
    if (b & 0x7fffffff) == 0x7f800000:
        return b
    return rounded(finite(a) + finite(b), a == b == 0x80000000)


def oracle(point, rows, nj):
    result = []
    for row in rows:
        x = reference(0, row[0], 0, point[0], nj)
        z = reference(0, row[2], 0, point[2], nj)
        xy = reference(0, row[1], x, point[1], nj)
        zw = reference(0, row[3], z, point[3], nj)
        value = flush(add(flush(xy, nj), flush(zw, nj)), nj)
        if (value & 0x7fffffff) >= 0x7f800000:
            result.append(0x7fc00000)
            continue
        number = finite(value)
        fraction = rounded(number - int(number), value == 0x80000000)
        if finite(fraction) < 0:
            fraction = rounded(finite(fraction) + Fraction(1))
        result.append(fraction)
    return result


def main():
    if os.name == "nt":
        from project import build_environment
        os.environ.update(build_environment())
    out = ROOT / "temp/checks" / f"deformation-projection-{time.time_ns()}"
    out.mkdir(parents=True)
    source = ROOT / "src/motorstorm/deformation_depth.cpp"
    fixture = ROOT / "scripts/fixtures/deformation_projection_fixture.cpp"
    cases = []
    edge = [0, 0x80000000, 1, 0x80000001, 0x007fffff, 0x00800000,
            0x3f000000, 0xbf000000, 0x3f800000, 0xbf800000,
            0x3f800001, 0x3f7ffffe, 0x4b000001, 0x7f800000, 0x7fc00001]
    for nj in (0, 1):
        cases.append(([0x3f800000, 0x3f7ffffe, 0, 0x3f800000],
                      [[0xbf800000, 0x3f800001, 0, 0],
                       [0, 0, 0, 0x3e800000]], nj))
        for value in edge:
            cases.append(([0x3f800000] * 4,
                          [[value, 0, 0, 0], [0, value, 0, 0]], nj))
        randomizer = random.Random(302)
        for _ in range(256):
            words = []
            for _ in range(12):
                value = randomizer.randint(-64, 64) * 2.0 ** randomizer.randint(-140, 50)
                words.append(struct.unpack("<I", struct.pack("<f", value))[0])
            cases.append((words[:4], [words[4:8], words[8:]], nj))
    data = b"".join(struct.pack("<13I", *point, *rows[0], *rows[1], nj)
                    for point, rows, nj in cases)
    expected = [tuple(oracle(*case)) for case in cases]
    input_path = out / "input.bin"
    input_path.write_bytes(data)
    compiler = (
        os.environ.get("MV_CLANG") if os.name == "nt"
        else shutil.which("clang++") or shutil.which("g++")
    )
    assert compiler
    executable = out / ("projection.exe" if os.name == "nt" else "projection")
    include = ROOT / "src/motorstorm"
    if os.name == "nt":
        command = [compiler, "/nologo", "/std:c++20", "/O2", "/EHsc", "/W4", "/WX", "/D_CRT_SECURE_NO_WARNINGS",
                   "/fp:strict", f"/I{include}", str(source), str(fixture),
                   f"/Fe{executable}", f"/Fo{out}\\"]
    else:
        command = [compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                   "-frounding-math", "-ffp-contract=off", f"-I{include}",
                   str(source), str(fixture), "-o", str(executable)]
    results = []
    report = dict(
        commands=results,
        cases=len(cases),
        fp_modes=16,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
        input_sha256=hashlib.sha256(data).hexdigest(),
        comparison="bit-exact finite outputs and NaN classification",
    )

    def run(args):
        process = subprocess.run(args, capture_output=True, text=True, timeout=120)
        results.append(dict(command=args, returncode=process.returncode,
                            stdout=process.stdout, stderr=process.stderr))
        (out / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        assert process.returncode == 0, process.stdout + process.stderr

    def matches(path):
        actual = list(struct.iter_unpack("<2I", path.read_bytes()))
        return len(actual) == len(expected) and all(
            a == e or (nan(a) and nan(e))
            for row, target in zip(actual, expected)
            for a, e in zip(row, target))

    run(command)
    for mode in range(16):
        output = out / f"output-{mode}.bin"
        run([str(executable), str(input_path), str(output), str(mode)])
        assert matches(output), f"Projection arithmetic differs in FP mode {mode}"
    original = source.read_text(encoding="utf-8")
    mutants = {
        "unfused multiply/add": original.replace(
            "const auto value = std::fma(a, b, c);",
            "const auto value = static_cast<float>(static_cast<float>(a * b) + c);", 1),
        "wrong point lane": original.replace("row[1], point[1], x", "row[1], point[2], x", 1),
        "missing negative wrap": original.replace("single(fraction + 1.0f)", "single(fraction)", 1),
        "ignored NJ": original.replace("non_java && (bits", "false && non_java && (bits", 1),
        "caller FP leakage": original.replace("    const ScopedDepthFp fp;\n    std::array<float, 2>", "    std::array<float, 2>", 1),
    }
    for index, (label, changed) in enumerate(mutants.items()):
        assert changed != original, label
        directory = out / f"mutant-{index}"
        directory.mkdir()
        candidate = directory / "candidate.cpp"
        candidate.write_text(changed, encoding="utf-8")
        binary = directory / executable.name
        mutated = [str(candidate) if arg == str(source) else
                   f"/Fo{directory}\\" if arg.startswith("/Fo") else
                   arg.replace(str(executable), str(binary))
                   for arg in command]
        run(mutated)
        output = directory / "output.bin"
        process = subprocess.run([str(binary), str(input_path), str(output), "0"],
                                 capture_output=True, text=True, timeout=120)
        assert (process.returncode == 5 or
                (process.returncode == 0 and not matches(output))), label
        results.append(dict(mutant=label, returncode=process.returncode,
                            stdout=process.stdout, stderr=process.stderr))
    report["rejected_mutants"] = list(mutants)
    (out / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"PASS {len(cases)} projections, 16 FP modes, 5 rejected mutants; {out}")


if __name__ == "__main__":
    main()
