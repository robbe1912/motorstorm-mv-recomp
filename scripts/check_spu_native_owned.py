#!/usr/bin/env python3
"""Exercise real owned-job/policy transitions and a disabled-mode red control."""
import argparse, hashlib, json, os, shutil, subprocess, time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sdk=root/'vendor/ps3recomp'
import sys
sys.path.insert(0,str(sdk/'tools'))
if os.name=='nt':
    from project import build_environment
    os.environ.update(build_environment())
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path);ap.add_argument('--historical-source-root',type=Path);args=ap.parse_args()
out=(args.output or root/'temp/checks'/('native-owned-'+str(time.time_ns()))).resolve();out.mkdir(parents=True,exist_ok=False)
# Execute real launcher sanitization/selection/record expressions without a game.
import ast,copy
from types import SimpleNamespace
launch_path=root/'scripts/run.py';tree=ast.parse(launch_path.read_text())
sanitize=[n for n in ast.walk(tree) if isinstance(n,ast.For) and ast.unparse(n.target)=='key' and ast.unparse(n.iter)=='list(env)']
select=[n for n in ast.walk(tree) if isinstance(n,ast.If) and ast.unparse(n.test)=='args.native_owned_jobs']
assert len(sanitize)==len(select)==1,'explicit launcher mode required'
record=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='record' for t in n.targets))
environment=next(v for k,v in zip(record.keys,record.values) if k.value=='environment')
def launcher_case(selection,enabled):
    scope={'env':{'SPU_NATIVE_OWNED_JOBS':'1'},'args':SimpleNamespace(native_owned_jobs=enabled)}
    exec(compile(ast.Module(body=sanitize+selection,type_ignores=[]),'actual owned selection','exec'),scope)
    recorded=eval(compile(ast.Expression(environment),'actual launch receipt','eval'),scope)
    expected='1' if enabled else None
    assert scope['env'].get('SPU_NATIVE_OWNED_JOBS')==expected,'owned jobs not selected'
    assert recorded.get('SPU_NATIVE_OWNED_JOBS')==expected,'owned jobs not recorded'
    return recorded
launcher_receipt={'sha256':hashlib.sha256(launch_path.read_bytes()).hexdigest(),'default':launcher_case(select,False),'enabled':launcher_case(select,True)}
try:launcher_case([],True)
except AssertionError as error:assert str(error)=='owned jobs not selected'
else:raise AssertionError('historical cleared flag accepted')
names=['spu_channels.c','spu_drain.c','spu_lockstep.c','spu_coherency.c','spu_workload.c','spurs_policy.c','spurs_job.c','spu_tsp_weak.c','spu_vm_pagemap.c','spurs_policy_blob_weak.c','spu_interp.c','spu_float_simd.c','spu_task_lifecycle.c']
fixture=root/'scripts/fixtures/spu_native_owned.c'
report={'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
    'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'lifter_sha256':hashlib.sha256((sdk/'tools/spu_lifter.py').read_bytes()).hexdigest(),
    'link_fixture_sha256':hashlib.sha256((fixture.parent/'spu_interpreter_handoff.c').read_bytes()).hexdigest(),
    'variants':[],'launcher':launcher_receipt}
def build(source,label,historical=False,observed=False):
    target=out/label;target.mkdir();spu=source/'runtime/spu'
    from spu_lifter import SPULifter,LiftedFunction
    from spu_disasm import spu_decode
    code=SPULifter()._translate(spu_decode(0x35200100,0x4004),LiftedFunction(name='owned',start_addr=0x4000,end_addr=0x4014))
    tail=SPULifter()._translate(spu_decode(0x327E0080,0x5004),LiftedFunction(name='subjob',start_addr=0x5000,end_addr=0x5008))
    (target/'spu_native_owned_call.h').write_text('#define OWNED_POLICY_CALL '+code+'\n#define OWNED_SUBJOB_TAIL '+tail+'\n')
    compiler=(os.environ.get('MV_CLANG') or shutil.which('clang-cl')) if os.name=='nt' else (os.environ.get('CC') or shutil.which('cc'))
    assert compiler,'supported C compiler required'
    identity=subprocess.run([compiler,'--version'],capture_output=True,text=True,timeout=10)
    assert identity.returncode==0,'compiler identification failed: '+identity.stderr
    clang='clang' in identity.stdout.lower()
    sources=[fixture,*[spu/n for n in names],source/'runtime/platform/win32_compat.c',source/'runtime/memory/guest_read_sync.c',source/'runtime/diag/spu_execution_observer.c',source/'runtime/diag/loadtime_trace.c',source/'runtime/platform/thread_name.c',source/'runtime/syscalls/spu_ea_alias.c']
    if clang:sources.append(spu/'spu_dispatch_mt.c')
    includes=[target,source/'include',spu,source/'runtime/platform',sdk/'runtime/spu']
    binary=target/('test.exe' if os.name=='nt' else 'test')
    if os.name=='nt':
        compiler=os.environ.get('MV_CLANG') or shutil.which('clang-cl')
        if not compiler:raise SystemExit('clang-cl plus the Visual Studio developer environment is required')
        command=[compiler,'/nologo','/TC','/std:c17','/O1','/UNDEBUG','/MDd',*['/I'+str(p) for p in includes],*map(str,sources),'/Fo'+str(target)+os.sep,'/Fe'+str(binary),'/link','Synchronization.lib']
        if historical:command.insert(1,'/DOWNED_HISTORICAL')
        if observed:command[1:1]=['/DPS3_EXECUTION_OBSERVATION=1','/DPS3_ATOMIC_OBSERVATION=1']
    else:
        compiler=os.environ.get('CC') or shutil.which('cc');assert compiler,'C compiler required'
        command=[compiler,'-std=gnu17','-D_GNU_SOURCE','-O1','-UNDEBUG',*['-I'+str(p) for p in includes],*map(str,sources),'-pthread','-lm','-o',str(binary)]
        if historical:command.insert(1,'-DOWNED_HISTORICAL')
        if observed:command[1:1]=['-DPS3_EXECUTION_OBSERVATION=1','-DPS3_ATOMIC_OBSERVATION=1']
    result=subprocess.run(command,capture_output=True,text=True,timeout=120)
    (target/'build.log').write_text(result.stdout+result.stderr)
    entry={'label':label,'compiler_identity':{'command':[compiler,'--version'],'stdout':identity.stdout,'stderr':identity.stderr},'headers':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in spu.glob('*.h')},'emitted_sha256':hashlib.sha256((target/'spu_native_owned_call.h').read_bytes()).hexdigest(),'command':command,'returncode':result.returncode,'sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'runs':[]}
    report['variants'].append(entry);(out/'result.json').write_text(json.dumps(report,indent=2))
    if result.returncode:
        lines=(result.stdout+result.stderr).splitlines()
        print('\n'.join([x for x in lines if 'error' in x.lower()][-12:]),flush=True)
    assert result.returncode==0,'compile failed: '+str(target/'build.log')
    capability=subprocess.run([str(binary),'capabilities'],capture_output=True,text=True,timeout=10)
    assert capability.returncode==0 and capability.stdout.strip() in ('musttail=0','musttail=1'),capability
    entry['musttail_compiled']=capability.stdout.strip()=='musttail=1'
    assert entry['musttail_compiled']==clang,'compiler identity and actual compiled capability disagree'
    entry['executable_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
    entry['capability']={'returncode':capability.returncode,'stdout':capability.stdout,'stderr':capability.stderr}
    (out/'result.json').write_text(json.dumps(report,indent=2))
    return binary,entry
def run(binary,entry,mode,flag='1',observed=False,red=False,pm=False):
    env={k:v for k,v in os.environ.items() if not k.startswith(('SPU_','SPURS_','YDKJ_','LBP_','GH3_'))}
    env['SPU_NATIVE_OWNED_JOBS']=flag;env['SPU_INTERP_UNLIFTED']='1'
    if observed:env['SPU_PCHIST']='1'
    if pm:env['SPU_PM_INTERP']='1'
    result=subprocess.run([str(binary),mode],cwd=binary.parent,env=env,capture_output=True,text=True,timeout=10)
    entry['runs'].append({'mode':mode,'flag':flag,'observed':observed,'red':red,'required_pm_interp':pm,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    (out/'result.json').write_text(json.dumps(report,indent=2))
    if red:assert result.returncode!=0 and ('FORBIDDEN compiled policy' in result.stderr or 'invalid SPU_NATIVE_OWNED_JOBS' in result.stderr or 'FAIL native calls=0 expected=1 native_in_irq=0' in result.stderr),entry['runs'][-1]
    else:assert result.returncode==0 and 'PASS' in result.stdout,entry['runs'][-1]
    print(('RED ' if red else 'PASS ')+entry['label']+' '+mode,flush=True)
binary,entry=build(sdk,'production')
for mode in ['owned','call-policy','live-explicit-stop','native-call-no-frame','native-call-wrong-return','nested-owned','nested-tail','irq','queued-irq','dma-invalidate','unknown','owner-miss','overlap','invalid-range','budget','global-budget','native-call-global-budget','stop-boundary','admission']:run(binary,entry,mode)
if entry['musttail_compiled']:run(binary,entry,'musttail')
run(binary,entry,'observed',observed=True);run(binary,entry,'owned',flag='0',red=True);run(binary,entry,'owned',flag='invalid',red=True)
for mode in ['owned','call-policy','live-explicit-stop','native-call-no-frame','native-call-wrong-return','nested-owned','nested-tail','irq','unknown','owner-miss','overlap','invalid-range','budget','global-budget','native-call-global-budget','stop-boundary']:run(binary,entry,mode,pm=True)
run(binary,entry,'owned',flag='0',pm=True,red=True)
binary,entry=build(sdk,'compiled-observers',observed=True)
run(binary,entry,'observed')
if args.historical_source_root:
    binary,entry=build(args.historical_source_root.resolve(),'historical',True)
    run(binary,entry,'owned',red=True);run(binary,entry,'call-policy',red=True)
print('Evidence: '+str(out/'result.json'))
