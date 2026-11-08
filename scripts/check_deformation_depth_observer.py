#!/usr/bin/env python3
"""Compile the real PPU depth observer and prove it preserves fallback output."""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile

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
            "typedef struct ppu_context { uint64_t gpr[32]; double fpr[32]; } ppu_context;\n",
            encoding="utf-8",
        )
        executable = out / ("observer.exe" if os.name == "nt" else "observer")
        command = [
            cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror", str(SOURCE), str(FIXTURE),
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
    print("PASS actual depth observer fallback, nested Lock capture, and bounded output")


if __name__ == "__main__":
    main()
