#!/usr/bin/env python3
"""Build the actual interpreter and authored leaf tests; reject unsafe mutants."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
spu = root / 'vendor/ps3recomp/runtime/spu'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--compiler', default=os.environ.get('MV_CLANG') or os.environ.get('CC') or shutil.which('clang-cl' if os.name=='nt' else 'cc'))
args = parser.parse_args()
assert args.compiler, 'Set CC or --compiler'
out = root / 'build/self-tests/native-leaf-dispatch'
out.mkdir(parents=True, exist_ok=True)
env = {k:v for k,v in os.environ.items() if not k.startswith(('SPU_','SPURS_','YDKJ_','LBP_','GH3_'))}

def build(name, source, baseline=False):
    directory=out/name
    directory.mkdir(exist_ok=True)
    exe=directory/('fixture.exe' if os.name=='nt' else 'fixture')
    command=[args.compiler, str(source), str(root/'scripts/fixtures/native_leaf_dispatch.c'), str(spu/'spu_drain.c')]
    if os.name=='nt':
        command+=['/nologo','/std:c17','/Gy','/Gw','/O2','/UNDEBUG','/D_CRT_SECURE_NO_WARNINGS',
                  '/I'+str(root/'vendor/ps3recomp/include'),'/I'+str(spu),'/Fo'+str(directory)+os.sep,'/Fe'+str(exe),'/link','/OPT:REF']
    else:
        dead_strip='-Wl,-dead_strip' if sys.platform=='darwin' else '-Wl,--gc-sections'
        command+=['-std=gnu17','-ffunction-sections','-fdata-sections',dead_strip,'-O2','-UNDEBUG','-I'+str(root/'vendor/ps3recomp/include'),'-I'+str(spu),'-lpthread','-lm','-o',str(exe)]
    if baseline:
        command.insert(1,'/DBASELINE_ONLY' if os.name=='nt' else '-DBASELINE_ONLY')
    (directory/'command.json').write_text(json.dumps(command,indent=2),encoding='utf-8')
    r=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True)
    (directory/'build.log').write_text(r.stdout+r.stderr)
    assert r.returncode==0, r.stdout+r.stderr
    return exe

def run(exe, mode='normal', extra=None):
    r=subprocess.run([str(exe),mode],cwd=exe.parent,env=dict(env,**(extra or {})),capture_output=True,text=True,timeout=20)
    (exe.parent/(mode+'.log')).write_text(r.stdout+r.stderr)
    return r

exe=build('production',spu/'spu_interp.c')
for mode in ['normal','empty']:
    r=run(exe,mode);assert r.returncode==0,r.stdout+r.stderr
for mode,message in [('bad','continuation/status'),('plan','invalid plan'),('ambiguous','ambiguous guards')]:
    r=run(exe,mode)
    assert r.returncode==86 and '[spu-native-leaf] invalid execution: '+message in r.stderr,r.stdout+r.stderr
r=run(exe,'tls')
assert r.returncode==1 and 'FAIL caller TLS queue' in r.stderr,r.stdout+r.stderr
for variable in ['SPU_LS_LOWREAD','SPU_SMC_WATCH','SPU_PCHIST','SPU_TRACE_CALLS',
                 'SPU_BOUNDARY_DIR','YDKJ_SPU_TRACE','YDKJ_CRI_GATE1TRACE','SPU_STEPCAP']:
    r=run(exe,'instrumented',{variable:'100'})
    assert r.returncode==0,r.stdout+r.stderr

source=(spu/'spu_interp.c').read_text(encoding='utf-8')

# Recover the exact pre-port public implementation, not a second model of its
# behavior. The pinned digest prevents the reconstruction from hiding drift.
reference=source
def undo(before,after):
    global reference
    assert reference.count(before)==1,before
    reference=reference.replace(before,after)
undo('#include "spu_native_leaf.h"\n#include <stdatomic.h>\n','')
begin=reference.index('enum { NATIVE_LEAVES')
end=reference.index('/* ---- decode:')
reference=reference[:begin]+reference[end:]
undo('static uint32_t interp_run_until_impl(spu_context* ctx, uint32_t start_lsa, uint32_t stop_lsa, uint64_t local_budget) {\n    native_freeze();',
     'static uint32_t interp_run_until_impl(spu_context* ctx, uint32_t start_lsa, uint32_t stop_lsa) {')
undo('        if (local_budget && steps>=local_budget) { g_spu_interp_steps=steps; return ctx->pc; }\n','')
begin=reference.index('        /* Explicit native leaves preserve')
end=reference.index('        int _rej =',begin)
reference=reference[:begin]+reference[end:]
undo('uint32_t spu_interp_run_until(spu_context* ctx, uint32_t start_lsa, uint32_t stop_lsa)\n{\n    return spu_interp_run_until_budget(ctx,start_lsa,stop_lsa,0);\n}\n\nuint32_t spu_interp_run_until_budget(spu_context* ctx, uint32_t start_lsa, uint32_t stop_lsa, uint64_t local_budget)\n{',
     'uint32_t spu_interp_run_until(spu_context* ctx, uint32_t start_lsa, uint32_t stop_lsa)\n{')
assert reference.count('interp_run_until_impl(ctx, start_lsa, stop_lsa, local_budget)')==3
reference=reference.replace('interp_run_until_impl(ctx, start_lsa, stop_lsa, local_budget)','interp_run_until_impl(ctx, start_lsa, stop_lsa)')
assert hashlib.sha256(reference.encode('utf-8')).hexdigest()=='45115b8e51070e7be2a393edc51a2531325a2229674216fa59c54ab476ec91b2','Pre-port source identity changed; review the actual baseline'
path=out/'pre-port.c';path.write_text(reference,encoding='utf-8')
baseline=build('pre-port',path,baseline=True)
records=[]
for binary in [baseline,exe]:
    r=subprocess.run([str(binary),'legacy-record'],env=env,capture_output=True,timeout=20)
    (binary.parent/'legacy-record.err').write_bytes(r.stderr)
    assert r.returncode==0,r.stderr
    records.append(r.stdout)
if records[0]!=records[1]:
    for name,data in zip(['pre-port','production'],records): (out/(name+'-legacy-record.bin')).write_bytes(data)
    raise AssertionError('Legacy empty-registry full-state/IRQ/FP/budget records differ from hash-pinned original')
assert len(records[0])>56*0x40000
(out/'legacy-record.json').write_text(json.dumps({'cases':56,'bytes':len(records[0]),'sha256':hashlib.sha256(records[0]).hexdigest(),'normalization':'Only LS allocation pointer set NULL; old API, four FP modes, seven global ceilings, normal and real IRQ vector cases'},indent=2),encoding='utf-8')

for name,before,after in [
    ('missing-seam','if (native_count && ctx->pc<0x40000','if (0 && ctx->pc<0x40000'),
    ('stop-bypass','(stop && stop>=leaf->begin && stop<leaf->end)','0'),
    ('zero-stop-sentinel','(stop && stop>=leaf->begin && stop<leaf->end)','(stop>=leaf->begin && stop<leaf->end)'),
    ('budget-bypass','if (plan.instructions>remaining) continue;','/* omitted budget admission */'),
    ('legacy-budget-bypass','if (legacy<remaining) remaining=legacy;','/* omitted legacy ceiling */'),
]:
    assert source.count(before)==1,name
    path=out/(name+'.c');path.write_text(source.replace(before,after),encoding='utf-8')
    r=run(build(name,path))
    assert r.returncode==1 and 'FAIL real host execution count' in r.stderr,r.stdout+r.stderr
print('PASS actual interpreter native-leaf state/stop/budget/IRQ/TLS/FP/thread tests and hash-pinned pre-port equivalence; five unsafe dispatch mutants and faulty TLS callback rejected')
