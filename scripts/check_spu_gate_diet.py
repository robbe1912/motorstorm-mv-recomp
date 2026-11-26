#!/usr/bin/env python3
"""Gate diet of the lifted SPU engine: the stop list holds with one policy test per drain iteration.

Builds scripts/fixtures/spu_gate_diet.c with the production runtime, runs the stop scenarios, and
builds one mutant of the production sources for each rule. A mutant is rejected when the build
succeeds and one scenario then fails. The scenarios:
  - lifted code runs and the result equals the interpreted reference (owned, irq, calls, tails);
  - a stop state keeps the lifted code out: an option (SPU_LS_WATCH, SPU_SMC_WATCH, SPU_LS_LOWREAD,
    SPU_PCHIST, SPU_NATIVE_OWNED_JOBS=0), a state set on the context, a DMA that overwrites the
    owner, a lifted function that arms a stop state and names a lifted target;
  - the job dump probe sees each address that the gate examines.
No mutant removes the range test of the pc alone: with the policy service off, the owner walk
holds the same bound (an owner ends at SPU_LS_SIZE), so such a mutant changes no result here.
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sdk=root/'vendor/ps3recomp'
sys.path.insert(0,str(sdk/'tools'))
if os.name=='nt':
    from project import build_environment
    os.environ.update(build_environment())
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path);ap.add_argument('--only',nargs='*',help='mutant names; `none` builds the production only');args=ap.parse_args()
out=(args.output or root/'temp/checks'/('spu-gate-diet-'+str(time.time_ns()))).resolve();out.mkdir(parents=True,exist_ok=False)

NAMES=['spu_channels.c','spu_drain.c','spu_lockstep.c','spu_coherency.c','spu_workload.c','spurs_policy.c','spurs_job.c','spu_tsp_weak.c','spu_vm_pagemap.c','spurs_policy_blob_weak.c','spu_interp.c','spu_float_simd.c','spu_task_lifecycle.c']
EXTRA=['runtime/platform/win32_compat.c','runtime/memory/guest_read_sync.c','runtime/diag/spu_execution_observer.c','runtime/diag/loadtime_trace.c','runtime/platform/thread_name.c','runtime/syscalls/spu_ea_alias.c']
fixture=root/'scripts/fixtures/spu_gate_diet.c'
GATE='runtime/spu/spu_native_owned.h';DRAIN='runtime/spu/spu_drain.c';READERS='runtime/spu/spu_channels.c'
# name: (file, text of the production line, text of the mutant)
MUTANTS={
 'watch-dropped':(GATE,'g_spu_ls_watch_n > 0 || g_spu_ls_probe','g_spu_ls_probe'),
 'smc-watch-dropped':(GATE,'g_spu_ls_probe > 0 || g_spu_smc_watch > 0 ||','g_spu_ls_probe > 0 ||'),
 'ls-probe-dropped':(GATE,'g_spu_ls_watch_n > 0 || g_spu_ls_probe > 0 ||','g_spu_ls_watch_n > 0 ||'),
 'interrupt-pending-dropped':(GATE,'(ctx->int_enable && (ctx->event_status & ctx->event_mask)) ||\n',''),
 'interrupt-state-dropped':(GATE,'|| ctx->irq_frame || ctx->irq_saved ||','||'),
 'owner-range-dropped':(GATE,'return ctx->resident_code[i].image_id > 0 &&\n               (!image || image == ctx->resident_code[i].image_id) &&\n               base < SPU_LS_SIZE &&\n               size <= SPU_LS_SIZE-base;','return 1;'),
 'image-scope-dropped':(GATE,'(!image || image == ctx->resident_code[i].image_id) &&\n ',''),
 'observed-dropped':(GATE,'spu_owned_observed()) return 0;','0) return 0;'),
 'policy-test-inverted':(DRAIN,'const int owned = spu_native_owned_policy(ctx);','const int owned = !spu_native_owned_policy(ctx);'),
 'drain-gate-skipped':(DRAIN,'if (owned && !spu_native_owned_run_ok(ctx,ctx->pc))\n                fn=spu_indirect_branch;','if (0 && owned && !spu_native_owned_run_ok(ctx,ctx->pc))\n                fn=spu_indirect_branch;'),
 'misaligned-pc-dropped':(GATE,'pc >= SPU_LS_SIZE || (pc & 3) ||','pc >= SPU_LS_SIZE ||'),
 'no-local-store-dropped':(GATE,'ctx->image_id < 0 || !ctx->ls ||','ctx->image_id < 0 ||'),
 'image-id-dropped':(GATE,'ctx->image_id < 0 || !ctx->ls ||','!ctx->ls ||'),
 'job-dump-probe-lost':(GATE,'if (g_spu_job_dump >= 0) spu_job_dump_probe(ctx, pc);\n',''),
 'mode-word-not-stored':(READERS,'g_spu_native_owned_mode=mode+1;','g_spu_native_owned_mode=0;'),
 'observed-word-not-stored':(READERS,'g_spu_native_owned_observed=observed+1;','g_spu_native_owned_observed=0;'),
 'image-word-not-stored':(READERS,'g_spu_native_owned_image=image+1;','g_spu_native_owned_image=0;'),
 'mode-word-read-wrong':(GATE,'return word ? word - 1 : spu_native_owned_enabled();','return word ? word : spu_native_owned_enabled();'),
 'observed-word-read-wrong':(GATE,'return word ? word - 1 : spu_native_owned_observed();','return word ? word : spu_native_owned_observed();'),
 'image-word-read-wrong':(GATE,'return word ? word - 1 : spu_native_owned_image();','return word ? word : spu_native_owned_image();'),
}
for name,(path,old,new) in MUTANTS.items():
    text=(sdk/path).read_bytes().decode().replace('\r\n','\n')
    assert text.count(old)==1,'mutant text of %s occurs %d times in %s'%(name,text.count(old),path)

def stage(name):
    """A copy of the runtime sources with the mutant applied. The production build uses the tree."""
    if name is None:return sdk
    base=out/('tree-'+name);shutil.copytree(sdk/'runtime',base/'runtime');shutil.copytree(sdk/'include',base/'include')
    path,old,new=MUTANTS[name];file=base/path
    text=file.read_bytes().decode().replace('\r\n','\n');assert text.count(old)==1
    file.write_bytes(text.replace(old,new).encode());return base

def build(source,label):
    target=out/label;target.mkdir();spu=source/'runtime/spu'
    from spu_lifter import SPULifter,LiftedFunction
    from spu_disasm import spu_decode
    code=SPULifter()._translate(spu_decode(0x35200100,0x4004),LiftedFunction(name='owned',start_addr=0x4000,end_addr=0x4014))
    tail=SPULifter()._translate(spu_decode(0x327E0080,0x5004),LiftedFunction(name='subjob',start_addr=0x5000,end_addr=0x5008))
    (target/'spu_native_owned_call.h').write_text('#define OWNED_POLICY_CALL '+code+'\n#define OWNED_SUBJOB_TAIL '+tail+'\n')
    compiler=os.environ.get('MV_CLANG') or shutil.which('clang-cl')
    assert compiler,'clang-cl plus the Visual Studio developer environment is required'
    sources=[fixture,fixture.parent/'ppu_fm_window_off.c',*[spu/n for n in NAMES+['spu_dispatch_mt.c']],*[source/n for n in EXTRA]]
    includes=[target,source/'include',spu,source/'runtime/platform',sdk/'runtime/spu']
    binary=target/'test.exe'
    command=[compiler,'/nologo','/TC','/std:c17','/O1','/UNDEBUG','/MDd','/DOWNED_MAIN_NAME=gate_base_main',*['/I'+str(p) for p in includes],*map(str,sources),'/Fo'+str(target)+os.sep,'/Fe'+str(binary),'/link','Synchronization.lib']
    result=subprocess.run(command,capture_output=True,text=True,timeout=300)
    (target/'build.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        lines=(result.stdout+result.stderr).splitlines();print(label,': compile failed');print('\n'.join(x for x in lines if 'error' in x.lower())[-8:],flush=True)
    assert result.returncode==0,'compile failed: '+str(target/'build.log')
    return binary

STOP='FAIL native calls=0 expected=1 native_in_irq=0'
# (mode, extra environment, expectation) ; 'pass': exit 0 with PASS; 'stop': lifted code stayed out
RUNS=[(m,{},'pass') for m in ('owned','irq','queued-irq','call-policy','nested-owned','nested-tail','dma-invalidate','owner-miss','unknown','overlap','invalid-range','admission','direct','stop-in-lifted','musttail')]
RUNS+=[(m,{'SPU_PM_INTERP':'1','SPU_NATIVE_OWNED_IMAGE':'25'},'pass') for m in ('scoped-nested','scoped-overlap','owned')]
RUNS+=[(m,{},'stop') for m in ('stop-watch','stop-smc','stop-lowread')]
RUNS+=[('owned',{'SPU_PCHIST':'1'},'stop'),('owned',{'SPU_NATIVE_OWNED_JOBS':'0'},'red'),('owned',{'SPU_JOB_DUMP':'25:16384:4:1:dumpdir'},'dump')]

def run(binary,variant,mode,extra,expect,report):
    env={k:v for k,v in os.environ.items() if not k.startswith(('SPU_','SPURS_','YDKJ_','LBP_','GH3_'))}
    env['SPU_NATIVE_OWNED_JOBS']='1';env['SPU_INTERP_UNLIFTED']='1';env.update(extra)
    dump=binary.parent/'dumpdir'
    if dump.exists():shutil.rmtree(dump)
    result=subprocess.run([str(binary),mode],cwd=binary.parent,env=env,capture_output=True,text=True,timeout=30)
    files=sorted(p.name for p in dump.iterdir()) if dump.exists() else []
    okay=(result.returncode==0 and 'PASS' in result.stdout) if expect=='pass' else \
         (result.returncode!=0) if expect=='red' else \
         (result.returncode!=0 and STOP in result.stderr) if expect=='stop' else \
         (result.returncode==0 and 'PASS native=1' in result.stdout and len(files)==1)
    report['runs'].append({'variant':variant,'mode':mode,'environment':extra,'expect':expect,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'dump_files':files,'okay':okay})
    return okay

report={'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
        'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'production_sha256':{p:hashlib.sha256((sdk/p).read_bytes()).hexdigest() for p in (GATE,DRAIN,READERS)},
        'mutants':{k:{'file':v[0],'text':v[1],'mutant':v[2]} for k,v in MUTANTS.items()},'variants':[]}


def variant(name):
    label=name or 'production';entry={'label':label,'runs':[]};report['variants'].append(entry)
    binary=build(stage(name),label)
    for mode,extra,expect in RUNS:
        run(binary,name,mode,extra,expect,entry)
        (out/'result.json').write_text(json.dumps(report,indent=2))
    failed=[[r['mode'],r['environment']] for r in entry['runs'] if not r['okay']]
    entry['failed_runs']=failed
    print(('MUTANT ' if name else 'PASS    ')+label+': %d runs, %d fail: %s'%(len(entry['runs']),len(failed),[f[0] for f in failed]),flush=True)
    return failed


survivors=[];variant(None)
names=[] if args.only==['none'] else (args.only or list(MUTANTS))
for name in names:
    if not variant(name):survivors.append(name)
report['survivors']=survivors;(out/'result.json').write_text(json.dumps(report,indent=2))
print('Mutants: %d, rejected: %d, survivors: %s'%(len(names),len(names)-len(survivors),survivors))
print('Evidence: '+str(out/'result.json'))
assert not survivors,'mutants accepted: '+', '.join(survivors)
