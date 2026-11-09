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
        built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert built.returncode == 0, built.stderr
        result = subprocess.run([str(executable)], cwd=ROOT, capture_output=True, text=True, timeout=30)
        transcript = result.stdout + result.stderr
        assert result.returncode == 0, transcript
        assert "install rejected: original entries unavailable" in transcript
        assert "installed raw GetDepth/PixelBuffer::Lock observer" in transcript
        assert transcript.count("[depth-observe] seq=") == 64
        assert "depth-gpr=111,222,333,444" in transcript
        assert "lock-seen=1 lock=aaaa,bbbb,cccc,status=fedcba98" in transcript
        assert transcript.count("capture cap=64 reached") == 1
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
    print("PASS depth observer: verified direct/table binding, exact fallback, nested Lock, cap, rejected unbound-entry mutant")


if __name__ == "__main__":
    main()
