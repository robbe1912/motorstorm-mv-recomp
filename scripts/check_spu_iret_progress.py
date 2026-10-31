#!/usr/bin/env python3
"""Repeated productive IRET continuations must not synthesize a halt."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
if os.name=='nt':
    from project import build_environment
    os.environ.update(build_environment())
p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,default=root/'vendor/ps3recomp/runtime/spu');a=p.parse_args();src=a.runtime.resolve();out=root/'temp/checks'/f'iret-progress-{time.time_ns()}';out.mkdir(parents=True)
fixture=root/'scripts/fixtures/spu_iret_progress.c';binary=out/('test.exe' if os.name=='nt' else 'test')
env={k:v for k,v in os.environ.items() if not k.startswith(('SPU_','SPURS_','LBP_','YDKJ_','DIAG_'))};env['SPU_PM_INTERP']='1'
inputs=[fixture,src/'spu_interp.c',src/'spu_context.h',src/'spu_helpers.h',src/'spu_float_simd.c',src/'spu_float_simd.h',src/'spu_float.h'];(out/'inputs.json').write_text(json.dumps({str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs},indent=2))
if os.name=='nt':cmd=[os.environ.get('MV_CLANG','clang-cl'),'/nologo','/TC','/O1','/UNDEBUG','/I'+str(src),'/I'+str(src.parent.parent/'include'),str(fixture),str(src/'spu_interp.c'),str(src/'spu_float_simd.c'),'/Fe'+str(binary),'/Fo'+str(out)+'/' ]
else:cmd=[os.environ.get('CC','cc'),'-std=gnu17','-O1','-UNDEBUG','-I'+str(src),'-I'+str(src.parent.parent/'include'),str(fixture),str(src/'spu_interp.c'),str(src/'spu_float_simd.c'),'-lm','-o',str(binary)]
build=subprocess.run(cmd,capture_output=True,text=True);(out/'build.log').write_text(build.stdout+build.stderr)
if build.returncode:print('\n'.join(x for x in (build.stdout+build.stderr).splitlines() if 'error' in x));raise SystemExit(build.returncode)
run=subprocess.run([str(binary)],capture_output=True,text=True,env=env,timeout=10);(out/'run.log').write_text(run.stdout+run.stderr);(out/'result.json').write_text(json.dumps(dict(returncode=run.returncode,exe_sha256=hashlib.sha256(binary.read_bytes()).hexdigest()),indent=2));print(run.stdout+run.stderr);print(out);raise SystemExit(run.returncode)
