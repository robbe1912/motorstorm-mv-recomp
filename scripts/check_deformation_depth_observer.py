#!/usr/bin/env python3
"""Compile the real PPU depth observer and prove it preserves fallback output."""
from __future__ import annotations

import os
from dataclasses import replace
import hashlib
import pathlib
import shutil
import subprocess
import tempfile
from native_game_binding import DEPTH_OBSERVER, digest, prepare

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "motorstorm" / "deformation_depth_observer.cpp"
FIXTURE = ROOT / "scripts" / "fixtures" / "deformation_depth_observer.cpp"


def main() -> None:
    cxx = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
    assert cxx, "need clang++ or g++"
    with tempfile.TemporaryDirectory(prefix="depth-observer-") as raw:
        out = pathlib.Path(raw)
        (out / "ppu_recomp.h").write_text(
            "#pragma once\n#include <stdint.h>\n"
            "typedef struct ppu_context { uint64_t gpr[32]; double fpr[32]; } ppu_context;\n"
            "void func_0029C684(ppu_context*);\n",
            encoding="utf-8",
        )
        header = out / "ppu_recomp.h"
        generated = out / "input"
        (generated / "ppu").mkdir(parents=True)
        (generated / "ppu/ppu_recomp.h").write_bytes(header.read_bytes())
        with header.open("a") as output:
            output.write("uint32_t vm_read32(uint64_t);\nuint8_t fixture_original_read8(uint64_t);\n"
                         "uint64_t fixture_byte_address(unsigned);\nunsigned fixture_byte_count();\n"
                         "#define vm_read8 fixture_original_read8\n")
        (generated / "ppu/ppu_recomp.h").write_bytes(header.read_bytes())
        body = (b"void func_0029C684(ppu_context* ctx) { fixture_depth_body(ctx); "
                b"ctx->gpr[9] = 0; if (ctx->gpr[8]) { for (unsigned i=0;i<fixture_byte_count();++i) "
                b"ctx->gpr[9] += vm_read8(fixture_byte_address(i)); } }")
        (generated / "ppu/depth.cpp").write_bytes(
            b'#include "ppu_recomp.h"\nvoid fixture_depth_body(ppu_context*);\n' + body +
            b"\nauto fixture_outside_reader = &vm_read8;\n")
        elf = out / "authored-input"
        elf.write_bytes(b"Authored depth observer input identity")
        contract = replace(DEPTH_OBSERVER, elf_sha256=digest(elf),
                           body_sha256=hashlib.sha256(body).hexdigest())
        # Exercise an upgrade from the exact older, registry/direct-only copy.
        prepare(generated, out / "bound", elf, out / "binding.json", replace(contract, byte_observer=''))
        binding = prepare(generated, out / "bound", elf, out / "binding.json", contract)
        bound = pathlib.Path(binding["copied_tu"])
        executable = out / ("observer.exe" if os.name == "nt" else "observer")
        command = [
            cxx, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", str(SOURCE), str(FIXTURE), str(bound),
            f"-I{out}", f"-I{ROOT / 'src'}", f"-I{ROOT / 'vendor' / 'ps3recomp' / 'include'}",
            "-o", str(executable),
        ]
        if os.name == "nt":
            # Match the native target's CRT policy for standard getenv.
            command.append("-D_CRT_SECURE_NO_WARNINGS")
        built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert built.returncode == 0, built.stderr
        result = subprocess.run([str(executable)], cwd=ROOT, capture_output=True, text=True, timeout=30)
        transcript = result.stdout + result.stderr
        assert result.returncode == 0, transcript
        assert "install rejected: original entries unavailable" in transcript
        assert "installed raw GetDepth/PixelBuffer::Lock observer" in transcript
        samples = [line for line in transcript.splitlines() if line.startswith("[depth-observe] seq=")]
        assert len(samples) == 128, f"Expected 64 samples per Lock class, got {len(samples)}"
        assert sum("lock-seen=0 " in line for line in samples) == 64
        assert sum("lock-seen=1 " in line for line in samples) == 64
        assert "depth-gpr=111,222,333,444" in transcript
        assert "lock-seen=1 lock=aaaa,bbbb,cccc,status=fedcba98" in transcript
        assert transcript.count("capture cap=64 reached lock-seen=0") == 1
        assert transcript.count("capture cap=64 reached lock-seen=1") == 1
        assert "PASS actual depth observer fallback and nested Lock capture" in transcript
        assert "metadata reads=1344" in transcript, "Metadata reads must stop after 64 attempts"
        assert "snapshot calls=64" in transcript, "Every complete bounded query must probe admission"
        views = [line for line in transcript.splitlines() if line.startswith("[depth-view]")]
        reads = [line for line in transcript.splitlines() if line.startswith("[depth-bytes]")]
        assert len(views) == len(reads) == 64, "Expected bounded authentic query metadata and original read results"
        assert all("format=25 dims=256,128 output=7000 xy=3e800000,3f400000" in line for line in views)
        assert all("count=5 b0=7000:14 b1=7001:15 b2=7002:16 b3=7003:17 b4=7004:18" in line for line in reads)
        resources = [line for line in transcript.splitlines() if line.startswith("[depth-resource]")]
        assert len(resources) == 64
        assert all("ea=5000 words=1,0,7000,8000,7000,2000,6000 parent=2,0,7000,8000,7000,2000,0" in line for line in resources)
        snapshots = [line for line in transcript.splitlines() if line.startswith("[depth-snapshot]")]
        assert len(snapshots) == 64
        assert all("status=1 valid=1 bytes=a0,a1,a2,a3" in line for line in snapshots)
        for status in (0, -1, -2):
            result = subprocess.run([str(executable), str(status)], capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, result.stdout + result.stderr
            snapshots = [line for line in result.stderr.splitlines() if line.startswith("[depth-snapshot]")]
            assert len(snapshots) == 64 and all(
                f"status={status} valid=0 bytes=0,0,0,0" in line for line in snapshots)
            assert "snapshot calls=64" in result.stdout
        for mode in ("wide", "short"):
            result = subprocess.run([str(executable), "1", mode], capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, result.stdout + result.stderr
            assert "snapshot calls=0" in result.stdout
            snapshots = [line for line in result.stderr.splitlines() if line.startswith("[depth-snapshot]")]
            if mode == "wide":
                assert len(snapshots) == 64 and all("status=-1 valid=0" in line for line in snapshots)
            else:
                assert not snapshots, "Incomplete original queries cannot authorize a snapshot"
        # Reproduce the missed-direct-call pattern with an otherwise valid
        # binding. Original outputs still agree, but observation must fail.
        text = bound.read_text()
        forward = "{ motorstorm_observe_deformation_depth(ctx); }"
        assert text.count(forward) == 1
        bound.write_text(text.replace(forward, "{ game_original_deformation_depth(ctx); }"))
        built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert built.returncode == 0, built.stderr
        result = subprocess.run([str(executable)], cwd=ROOT, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "[depth-observe] seq=" not in result.stderr, "Unbound callers must fail the observation oracle"
        # A global cap preserves results but starves Lock-bearing evidence.
        bound.write_text(text)
        source = SOURCE.read_text()
        assert source.count("if (class_sequence <= 64)") == 1
        mutant = out / "observer-global-budget.cpp"
        mutant.write_text(source.replace("if (class_sequence <= 64)", "if (sequence <= 64)"))
        mutant_command = command.copy()
        mutant_command[mutant_command.index(str(SOURCE))] = str(mutant)
        mutant_command.append(f"-I{SOURCE.parent}")
        built = subprocess.run(mutant_command, cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert built.returncode == 0, built.stderr
        result = subprocess.run([str(executable)], cwd=ROOT, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "lock-seen=1 lock=" not in result.stderr, "Global-cap mutant must lose later Lock samples"
        for before, after, oracle in (
            ("sample->byte_values[index] = value;", "sample->byte_values[index] = value ^ 1;",
             "b0=7000:14 b1=7001:15 b2=7002:16 b3=7003:17 b4=7004:18"),
            ("sample->x_bits = vm_read32(out_slot + 4u);", "sample->x_bits = vm_read32(out_slot + 8u);",
             "xy=3e800000,3f400000"),
            ("if (attempt >= 64) return;", "if (attempt >= 65) return;", "metadata reads=1344"),
        ):
            assert source.count(before) == 1
            mutant.write_text(source.replace(before, after))
            built = subprocess.run(mutant_command, cwd=ROOT, capture_output=True, text=True, timeout=120)
            assert built.returncode == 0, built.stderr
            result = subprocess.run([str(executable)], cwd=ROOT, capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, result.stdout + result.stderr
            assert oracle not in result.stdout + result.stderr, "Corrupted capture must fail its independent oracle"
        # Truncating guest addresses would turn an invalid probe into a different valid read.
        before = "if (address > UINT32_MAX)"
        assert source.count(before) == 1
        mutant.write_text(source.replace(before, "if (address == UINT64_MAX)"))
        built = subprocess.run(mutant_command, cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert built.returncode == 0, built.stderr
        result = subprocess.run([str(executable), "1", "wide"], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "snapshot calls=64" in result.stdout and "status=-1 valid=0" not in result.stderr
    print("PASS depth observer: exact fallback/reads, bounded snapshot admission and statuses, six rejected mutants")


if __name__ == "__main__":
    main()
