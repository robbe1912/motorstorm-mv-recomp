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
        body = b"void func_0029C684(ppu_context* ctx) { fixture_depth_body(ctx); }"
        (generated / "ppu/depth.cpp").write_bytes(
            b'#include "ppu_recomp.h"\nvoid fixture_depth_body(ppu_context*);\n' + body + b"\n")
        elf = out / "authored-input"
        elf.write_bytes(b"Authored depth observer input identity")
        contract = replace(DEPTH_OBSERVER, elf_sha256=digest(elf),
                           body_sha256=hashlib.sha256(body).hexdigest())
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
    print("PASS depth observer: direct/table binding, exact fallback, independent Lock budgets, two rejected mutants")


if __name__ == "__main__":
    main()
