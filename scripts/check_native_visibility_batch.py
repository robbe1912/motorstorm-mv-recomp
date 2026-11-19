"""Check the US visibility classifier with authored local-store data."""
import os
from pathlib import Path
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "build/self-tests/native-visibility-batch"
    output.mkdir(parents=True, exist_ok=True)
    source = root / "src/motorstorm"
    spu = root / "vendor/ps3recomp/runtime/spu"
    sdk_include = root / "vendor/ps3recomp/include"
    windows = os.name == "nt"
    compiler = os.environ.get("MV_CLANG") or os.environ.get("CC") or shutil.which("clang-cl" if windows else "cc")
    if not compiler:
        raise RuntimeError("Set MV_CLANG or CC to the native C compiler")
    executable = output / ("fixture.exe" if windows else "fixture")
    sources = [str(source / "visibility_batch.c"), str(spu / "spu_float_simd.c"),
               str(root / "scripts/fixtures/native_visibility_batch.c")]
    if windows:
        options = ["/nologo", "/std:c17", "/O2", "/fp:strict",
                   *("/I" + str(path) for path in (source, spu, sdk_include)),
                   "/Fe:" + str(executable)]
    else:
        options = ["-std=gnu17", "-O2", "-ffp-contract=off", "-frounding-math",
                   *("-I" + str(path) for path in (source, spu, sdk_include)),
                   "-o", str(executable)]
    command = [compiler, *options, *sources]
    if not windows:
        command.append("-lm")
    with (output / "build.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True)
    subprocess.run([str(executable)], cwd=output, check=True)


if __name__ == "__main__":
    main()
