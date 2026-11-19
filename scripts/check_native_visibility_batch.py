"""Check US visibility classification and initialization with authored data."""
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
    fixture = root / "scripts/fixtures/native_visibility_initialize.cpp"
    initializer = output / ("initialize.exe" if windows else "initialize")
    cxx = compiler if windows else os.environ.get("CXX") or shutil.which("c++")
    if not cxx:
        raise RuntimeError("Set CXX to the native C++ compiler")
    if windows:
        init_options = ["/nologo", "/std:c++17", "/O2", "/UNDEBUG",
                        *("/I" + str(path) for path in (source, spu, sdk_include)),
                        "/Fe:" + str(initializer)]
    else:
        init_options = ["-x", "c++", "-std=c++17", "-O2", "-UNDEBUG",
                        *("-I" + str(path) for path in (source, spu, sdk_include)),
                        "-o", str(initializer)]
    with (output / "initialize-build.log").open("w", encoding="utf-8") as log:
        subprocess.run([cxx, *init_options, str(fixture)], cwd=output,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    subprocess.run([str(initializer)], cwd=output, check=True)


if __name__ == "__main__":
    main()
