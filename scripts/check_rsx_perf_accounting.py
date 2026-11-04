#!/usr/bin/env python3
"""Exercise actual renderer accounting/submission helpers with an authored clock."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(source, name):
    match = re.search(r"\bstatic\s+void\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", source)
    assert match, "missing actual helper: " + name
    start = match.start()
    depth, state, i = 1, "code", match.end()
    while i < len(source):
        c, pair = source[i], source[i:i + 2]
        if state == "line":
            if c == "\n":
                state = "code"
        elif state == "block":
            if pair == "*/":
                state = "code"
                i += 1
        elif state in ('"', "'"):
            if c == "\\":
                i += 1
            elif c == state:
                state = "code"
        elif pair in ("//", "/*"):
            state = "line" if pair == "//" else "block"
            i += 1
        elif c in ('"', "'"):
            state = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if not depth:
                return source[start:i + 1]
        i += 1
    raise AssertionError("unterminated function " + name)


def contract(source):
    body = function(source, "render_frame")
    assert body.count("perf_batch_finish(_rf0);") == 1, "one full-batch accounting boundary required"
    assert body.index("perf_batch_finish(_rf0);") > body.index("cpu_surface_frame_complete();"), \
        "full-batch accounting must follow completion"
    assert body.index("cpu_surface_frame_complete();") > body.index("submit_recorded_commands();")
    assert "s_perf_rf +=" not in body and "[PERF]" not in body, "premature inline accounting"
    finish = function(source, "perf_batch_finish")
    assert "batches/s" in finish and "outside_render" in finish
    assert "guest %" not in finish and " fps " not in finish, "unproved game/FPS attribution"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "vendor/ps3recomp/libs/video/rsx_d3d12_backend.c")
    parser.add_argument("--historical-source", type=Path)
    args = parser.parse_args()
    source = args.source.read_text()
    contract(source)
    moved = source.replace("    if (perf_on()) perf_batch_finish(_rf0);\n", "", 1)
    moved = moved.replace("    submit_recorded_commands();",
                          "    if (perf_on()) perf_batch_finish(_rf0);\n    submit_recorded_commands();", 1)
    for candidate in [moved] + ([args.historical_source.read_text()] if args.historical_source else []):
        try:
            contract(candidate)
        except AssertionError:
            pass
        else:
            raise AssertionError("historical early accounting accepted")
    submit = function(source, "submit_recorded_commands")
    finish = function(source, "perf_batch_finish")
    globals_ = source[source.index("static double s_perf_tex"):source.index("static double perf_now")]
    template = (Path(__file__).parent / "fixtures/rsx_perf_accounting.c.in").read_text()
    code = template.replace("@GLOBALS@", globals_)
    code = code.replace("@SUBMIT@", submit).replace("@FINISH@", finish)
    environment = os.environ.copy()
    if os.name == "nt":
        from project import build_environment
        environment = build_environment()
    compiler = os.environ.get("CC") or environment.get("MV_CLANG") or shutil.which("clang") or shutil.which("gcc")
    assert compiler, "C compiler required"
    with tempfile.TemporaryDirectory(prefix="rsx-perf-accounting-") as temporary:
        path = Path(temporary)
        c = path / "fixture.c"
        exe = path / ("fixture.exe" if os.name == "nt" else "fixture")
        c.write_text(code)
        if Path(compiler).stem.lower() in ("cl", "clang-cl"):
            command = [compiler, "/nologo", "/W4", "/WX", "/std:c11", str(c), "/Fe" + str(exe)]
        else:
            command = [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(c), "-o", str(exe)]
        if os.name == "nt":
            video = ROOT / "vendor/ps3recomp"
            syntax_command = [environment["MV_CLANG"], "/nologo", "/std:c11", "/Zs"]
            syntax_command += ["/I" + str(video / part) for part in ("include", "runtime", "libs", "libs/video")]
            syntax_command += [str(args.source.resolve())]
            syntax = subprocess.run(syntax_command, cwd=path, env=environment,
                                    capture_output=True, text=True, timeout=120)
            assert syntax.returncode == 0, syntax.stdout + syntax.stderr
        subprocess.run(command, cwd=path, env=environment, check=True, timeout=120)
        for mode in [[], ["--disabled"], ["--fail-close"]]:
            result = subprocess.run([str(exe), *mode], capture_output=True, text=True, timeout=15)
            assert result.returncode == (77 if mode and mode[0].startswith("--fail-") else 0), result
            if not mode:
                assert "accounting checks=51 failures=0" in result.stdout, result
                assert "render_frame 2.00s" in result.stderr, result
                assert "outside_render 0.95s" in result.stderr, result
                assert "command_close 0.060s | command_execute 0.140s" in result.stderr, result
            if mode == ["--fail-close"]:
                assert "Command list close failed" in result.stderr, result
        # The first curated port accidentally retained an unavailable fork API.
        # Never invent stubs for that missing production subsystem.
        hook = '    if(!rsx_submission_commit())gpu_submission_fail("commit");\n'
        missing_owner = code.replace("    HRESULT hr =", hook + "    HRESULT hr =", 1)
        assert missing_owner != code
        c.write_text(missing_owner)
        broken = subprocess.run(command, cwd=path, env=environment,
                                capture_output=True, text=True, timeout=120)
        assert broken.returncode != 0, "unavailable submission owner accepted"
        assert "rsx_submission_commit" in broken.stderr and "gpu_submission_fail" in broken.stderr, broken
        c.write_text(code.replace("s_perf_rf += now - started;", "s_perf_rf += 0.010;", 1))
        subprocess.run(command, cwd=path, env=environment, check=True, timeout=120)
        control = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
        assert control.returncode == 1 and "FAIL whole renderer tail included" in control.stderr, control
    print("PASS actual full-batch accounting, Close/Execute, disabled mode, errors and historical controls")


if __name__ == "__main__":
    main()
