"""Actual dispatch controls. Authored CPU provider, not a GPU coherency test."""

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

if os.name == "nt":
    from project import build_environment

    os.environ.update(build_environment())

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "vendor/ps3recomp"
out = ROOT / "temp/checks" / f"guest-snapshot-{time.time_ns()}"
out.mkdir(parents=True)
source = RUNTIME / "runtime/memory/guest_read_sync.c"
fixture = ROOT / "scripts/fixtures/guest_read_snapshot.cpp"
compiler = os.environ.get("MV_CLANG") or shutil.which(
    "clang-cl" if os.name == "nt" else "c++"
)
assert compiler, "Prepare the compiler environment first"
report = dict(
    qualification=__doc__,
    commands=[],
    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
    header_sha256=hashlib.sha256(
        (RUNTIME / "include/ps3emu/guest_read_sync.h").read_bytes()
    ).hexdigest(),
)


def run(command, success=True):
    p = subprocess.run(
        list(map(str, command)), cwd=out, text=True, capture_output=True, timeout=90
    )
    report["commands"].append(
        dict(
            command=list(map(str, command)),
            returncode=p.returncode,
            stdout=p.stdout,
            stderr=p.stderr,
        )
    )
    (out / "result.json").write_text(json.dumps(report, indent=2))
    assert (p.returncode == 0) if success else (p.returncode != 0)


def test(name, text, success):
    c = out / f"{name}.c"
    c.write_text(text)
    obj = out / (name + (".obj" if os.name == "nt" else ".o"))
    exe = out / (name + (".exe" if os.name == "nt" else ""))
    if os.name == "nt":
        run(
            [
                compiler,
                "/nologo",
                "/TC",
                "/std:c17",
                "/O2",
                "/MDd",
                "/UNDEBUG",
                f"/I{RUNTIME}/include",
                "/c",
                c,
                f"/Fo{obj}",
            ]
        )
        run(
            [
                compiler,
                "/nologo",
                "/std:c++20",
                "/EHsc",
                "/O2",
                "/MDd",
                "/UNDEBUG",
                f"/I{RUNTIME}/include",
                fixture,
                obj,
                f"/Fe{exe}",
            ]
        )
    else:
        cc = os.environ.get("CC") or shutil.which("cc")
        run(
            [
                cc,
                "-std=c17",
                "-O2",
                "-UNDEBUG",
                "-I",
                RUNTIME / "include",
                "-c",
                c,
                "-o",
                obj,
            ]
        )
        run(
            [
                compiler,
                "-std=c++20",
                "-O2",
                "-UNDEBUG",
                "-pthread",
                "-I",
                RUNTIME / "include",
                fixture,
                obj,
                "-o",
                exe,
            ]
        )
    run([exe], success)


text = source.read_text()
test("production", text, True)
mutants = {
    "source-overflow": text.replace(
        "(uint64_t)r->address+r->bytes>UINT64_C(0x100000000) ||", ""
    ),
    "failed-commit": text.replace(
        "if(result==VM_READ_SNAPSHOT_OK)memcpy(destination,staging,output_bytes);",
        "if(result!=VM_READ_SNAPSHOT_OK)memcpy(destination,staging,output_bytes);",
    ),
    "omitted-commit": text.replace(
        "if(result==VM_READ_SNAPSHOT_OK)memcpy(destination,staging,output_bytes);",
        "if(result==VM_READ_SNAPSHOT_OK)(void)staging;",
    ),
}
for name, mutant in mutants.items():
    assert mutant != text
    test(name, mutant, False)
print("PASS actual dispatch and three source mutants:", out)
