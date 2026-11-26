#!/usr/bin/env python3
"""Counter of the SPU dispatches that send owned code to the interpreter.

Builds scripts/fixtures/spu_interp_count.c with the production runtime, runs
the environment cases, and builds one mutant of the production sources for each
rule. A mutant is rejected when the build succeeds and one case then fails.
The cases:
  - the counter vectors and the parity of the stop reasons with the gate;
  - a stop state, no code owner, a target without a lifted entry: one
    [spu-miss] line with the lane, the image id and the cause;
  - two lanes: lane=0 and lane=1;
  - the switch off, and the switch at 0: no [spu-miss] line.
One process per environment: the switch reads the environment once. Each
build uses a private copy of the runtime, so a mutant changes only that copy.
--sdk <dir> runs the check on another copy of the runtime (a staged carry)."""
import argparse, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path);ap.add_argument('--mutants',action='store_true');ap.add_argument('--sdk',type=Path,default=root/'vendor/ps3recomp')
ap.add_argument('--only',nargs='*',help='build these variants only (names)');args=ap.parse_args()
out=(args.output or root/'temp/checks'/('spu-interp-count-'+str(time.time_ns()))).resolve();out.mkdir(parents=True,exist_ok=False)
fixture=root/'scripts/fixtures/spu_interp_count.c'
stubs=root/'scripts/fixtures/spu_interp_count_stubs.h'  # link-only boundaries that abort when reached
sdk=args.sdk.resolve()
sys.path.insert(0,str(sdk/'tools'))
if os.name=='nt':
    from project import build_environment
    os.environ.update(build_environment())
NAMES=['spu_channels.c','spu_drain.c','spu_lockstep.c','spu_coherency.c','spu_workload.c','spurs_policy.c','spurs_job.c','spu_tsp_weak.c','spu_vm_pagemap.c','spurs_policy_blob_weak.c','spu_interp.c','spu_float_simd.c','spu_task_lifecycle.c']
EXTRA=['runtime/platform/win32_compat.c','runtime/memory/guest_read_sync.c','runtime/diag/spu_execution_observer.c','runtime/diag/loadtime_trace.c','runtime/platform/thread_name.c','runtime/syscalls/spu_ea_alias.c']
GATE='runtime/spu/spu_native_owned.h';SITE='runtime/spu/spu_channels.c'
ON={'SPU_NATIVE_OWNED_MISS_LOG':'1'}
# (name, file, before, after): one planted defect each.
MUTANTS=[
 ('gate-inverted',GATE,'    return __builtin_expect(g_spu_miss_log >= 0, 1) ? g_spu_miss_log : spu_miss_log_init();',
  '    return __builtin_expect(g_spu_miss_log >= 0, 1) ? !g_spu_miss_log : !spu_miss_log_init();'),
 ('counter-not-reset',GATE,'    memset(im->cause, 0, sizeof im->cause);','    (void)im;'),
 ('wrong-lane',GATE,'spu_miss_count(&g_spu_miss, spu_miss_lane(), ctx->image_id,','spu_miss_count(&g_spu_miss, 0, ctx->image_id,'),
 ('wrong-cause-class',GATE,'    return spu_lifted_lookup(ctx,ctx->pc) ? 0 : SPU_MISS_NO_ENTRY;','    return spu_lifted_lookup(ctx,ctx->pc) ? 0 : SPU_STOP_NO_OWNER;'),
 ('line-when-off',GATE,'    g_spu_miss_log = (e && *e && strcmp(e, "0")) ? 1 : 0;','    g_spu_miss_log = 1;'),
 ('stop-reason-drift',GATE,'    if (g_spu_smc_watch > 0) return SPU_STOP_SMC_WATCH;\n    if (spu_owned_observed())','    if (g_spu_smc_watch > 0) return SPU_STOP_NO_OWNER;\n    if (spu_owned_observed())'),
 ('period-lost',GATE,'    if (now_ms - s->last_ms < SPU_MISS_PERIOD_MS) return 0;','    if (0) return 0;'),
 ('image-key-lost',GATE,'    spu_miss_image* im = &s->image[spu_miss_slot(s, image)];','    spu_miss_image* im = &s->image[spu_miss_slot(s, 0)];'),
 ('count-call-lost',SITE,'        if (miss) { spu_miss_hit(ctx, miss); spu_native_owned_interpret(ctx); return; }',
  '        if (miss) { spu_native_owned_interpret(ctx); return; }'),
]
def stage(label,changes=()):
    """A copy of the runtime sources with the mutant applied."""
    src=out/label/'src'
    shutil.copytree(sdk,src,ignore=shutil.ignore_patterns('.git','__pycache__'))
    for rel,before,after in changes:
        path=src/rel;text=path.read_bytes().decode().replace('\r\n','\n')
        assert text.count(before)==1,f'{label}: {rel}: {text.count(before)} hits for {before[:40]!r}'
        path.write_bytes(text.replace(before,after).encode())
    return src
def build(src,label,changes):
    target=out/label;spu=src/'runtime/spu'
    compiler=os.environ.get('MV_CLANG') or shutil.which('clang-cl')
    assert compiler,'clang-cl plus the Visual Studio developer environment is required'
    identity=subprocess.run([compiler,'--version'],capture_output=True,text=True,timeout=10)
    assert identity.returncode==0,'compiler identification failed: '+identity.stderr
    shutil.copy2(stubs,target/stubs.name)
    sources=[fixture,*[spu/n for n in NAMES],*[src/n for n in EXTRA]]
    sources.append(spu/'spu_dispatch_mt.c')
    includes=[target,src/'include',spu,src/'runtime/platform',src/'runtime/syscalls']
    (target/'obj').mkdir(exist_ok=True)
    binary=target/'test.exe'
    if True:
        command=[compiler,'/nologo','/TC','/std:c17','/O1','/UNDEBUG','/MDd','/D_CRT_SECURE_NO_WARNINGS','/DSPU_INTERP_COUNT_STUBS=1',
                 *['/I'+str(p) for p in includes],*map(str,sources),'/Fo'+str(target/'obj')+os.sep,
                 '/Fe'+str(binary),'/link','Synchronization.lib']
    started=time.time()
    result=subprocess.run(command,capture_output=True,text=True,timeout=600)
    (target/'build.log').write_text(result.stdout+result.stderr)
    if result.returncode:print((result.stdout+result.stderr)[-4000:],flush=True)
    if result.returncode:print((result.stdout+result.stderr)[-4000:],flush=True)
    assert result.returncode==0,'compile failed: '+str(target/'build.log')
    return binary,{'label':label,'compiler':identity.stdout.splitlines()[0],'seconds':round(time.time()-started,1),
           'mutated_sha256':{rel:hashlib.sha256((src/rel).read_bytes()).hexdigest() for rel,_,_ in changes},
           'executable_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
L='[spu-miss] lane='
# mode, environment additions, (line, count) that must print
CASES=[('unit',{},[]),
       ('smc',ON,[(L+'0 img=77 gate stop smc watch=1',1)]),
       ('owner',ON,[(L+'0 img=77 gate stop no code owner=1',1)]),
       ('entry',ON,[(L+'0 img=77 no lifted entry 0x04000=1',1)]),
       ('lanes',ON,[(L+'0 img=77 gate stop smc watch=1',1),(L+'1 img=77 gate stop smc watch=1',1)]),
       ('smc',{},[]),('entry',{},[]),('smc',{'SPU_NATIVE_OWNED_MISS_LOG':'0'},[])]
report={'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
        'stubs_sha256':hashlib.sha256(stubs.read_bytes()).hexdigest(),'production_sha256':{rel:hashlib.sha256((sdk/rel).read_bytes()).hexdigest() for rel in (GATE,SITE)},
        'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'variants':[]}
def run(binary,mode,env_extra,expect):
    env={k:v for k,v in os.environ.items() if not k.startswith(('SPU_','SPURS_','YDKJ_','LBP_','GH3_'))}
    env['SPU_NATIVE_OWNED_JOBS']='1';env.update(env_extra)
    result=subprocess.run([str(binary),mode],cwd=binary.parent,env=env,capture_output=True,text=True,timeout=60)
    lines=result.stderr.splitlines()
    ok=result.returncode==0 and 'PASS' in result.stdout \
       and all(result.stderr.count(k)==n for k,n in expect) and not any(k.startswith('[spu-miss]') and k not in dict(expect) for k in lines)
    return ok,{'mode':mode,'env':env_extra,'returncode':result.returncode,'ok':ok,'stdout':result.stdout,'stderr':result.stderr}
variants=[('production',())]
if args.mutants:variants+=[(name,[(rel,before,after)]) for name,rel,before,after in MUTANTS]
if args.only:variants=[v for v in variants if v[0] in args.only]
for name,changes in variants:
    src=stage(name,changes)
    binary,entry=build(src,name,changes)
    report['variants'].append(entry)
    for mode,env_extra,expect in CASES:
        ok,result=run(binary,mode,env_extra,expect)
        entry.setdefault('runs',[]).append(result)
        if not changes:assert ok,(name,mode,env_extra,result['stdout'],result['stderr'])
        elif not ok:entry.setdefault('killed_by',[]).append(mode+str(env_extra))
        if changes:entry['killed']=bool(entry.get('killed_by'))
        print(('PASS ' if ok else 'FAIL ')+name+' '+mode+' '+str(env_extra),flush=True)
        (out/'result.json').write_text(json.dumps(report,indent=2))
    if changes:print(('KILLED ' if entry['killed'] else 'SURVIVED ')+name+' '+str(entry.get('killed_by')),flush=True)
mutants=[v for v in report['variants'] if v['mutated_sha256']]
assert all(v['killed'] for v in mutants),'a mutant survived'
print('PASS: %d environment cases; %d mutants rejected'%(len(CASES),len(mutants)))
print('Evidence: '+str(out/'result.json'))
