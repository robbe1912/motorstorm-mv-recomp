#!/usr/bin/env python3
"""Actual curated SPU helpers: extended values and the zero-normalization defect."""
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
if os.name=='nt':
    from project import build_environment
    os.environ.update(build_environment())
p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,default=root/'vendor/ps3recomp/runtime/spu');a=p.parse_args();runtime=a.runtime.resolve()
out=root/'temp/checks'/f'spu-float-{time.time_ns()}';out.mkdir(parents=True)
source=root/'scripts/fixtures/spu_float.c';exe=out/('test.exe' if os.name=='nt' else 'test')
inputs=[source,runtime/'spu_helpers.h',runtime/'spu_context.h']
if (runtime/'spu_float.h').exists():inputs.append(runtime/'spu_float.h')
(out/'inputs.json').write_text(json.dumps({str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs},indent=2))
if os.name=='nt':cmd=[os.environ.get('MV_CLANG','clang-cl'),'/nologo','/TC','/O2','/fp:strict','/I'+str(runtime),str(source),'/Fe'+str(exe),'/Fo'+str(out)+'/']
else:cmd=[os.environ.get('CC','cc'),'-std=c11','-O2','-ffp-contract=off','-I',str(runtime),str(source),'-lm','-o',str(exe)]
build=subprocess.run(cmd,capture_output=True,text=True);(out/'build.log').write_text(build.stdout+build.stderr)
if build.returncode:print(build.stdout+build.stderr);raise SystemExit(build.returncode)
run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10);(out/'run.log').write_text(run.stdout+run.stderr)
(out/'result.json').write_text(json.dumps(dict(returncode=run.returncode,exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest()),indent=2))
print(run.stdout+run.stderr);print(out);raise SystemExit(run.returncode)
