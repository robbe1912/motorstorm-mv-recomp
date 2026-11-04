#!/usr/bin/env python3
"""Run actual lifted call brackets against interpreter/drain return ownership."""
import argparse, hashlib, json, os, shutil, subprocess, time, sys, re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sdk=root/'vendor/ps3recomp';fixtures=root/'scripts/fixtures'
sys.path.insert(0,str(sdk/'tools'))
if os.name=='nt':
    from project import build_environment
    os.environ.update(build_environment())
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path);ap.add_argument('--historical-lifter',type=Path);args=ap.parse_args()
out=(args.output or root/'temp/checks'/('call-boundaries-'+str(time.time_ns()))).resolve();out.mkdir(parents=True,exist_ok=False)
names=['spu_channels.c','spu_drain.c','spu_lockstep.c','spu_coherency.c','spu_workload.c','spurs_policy.c','spurs_job.c','spu_tsp_weak.c','spu_vm_pagemap.c','spurs_policy_blob_weak.c','spu_interp.c','spu_float_simd.c','spu_task_lifecycle.c']
fixture=fixtures/'spu_call_boundaries.c'
report={'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'variants':[]}
def emission(module):
    from spu_disasm import spu_decode
    lifter=module.SPULifter()
    result=''
    for zero in (False,True):
        addr=0x3FFFC if zero else 0x200
        func=module.LiftedFunction(name='test',start_addr=addr,end_addr=addr+4)
        ops={'DIRECT':0x31080006,'RELATIVE':0x33080086 if zero else 0x3307C006,'INDIRECT':0x35200106,'ALIAS':0x35200306}
        for key,word in ops.items():result+='#define EMIT_'+key+('_ZERO' if zero else '')+' '+lifter._translate(spu_decode(word,addr),func)+'\n'
    return result
if args.historical_lifter:
    import importlib.util,sys
    spec=importlib.util.spec_from_file_location('historical_spu_lifter_270',args.historical_lifter)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    actual=emission(module)
    retained='\n'.join((fixtures/'spu_call_brackets_legacy.h').read_text().splitlines()[1:])+'\n'
    assert actual==retained,'historical production emitter differs from retained control'
    report['historical_lifter_sha256']=hashlib.sha256(args.historical_lifter.read_bytes()).hexdigest()
def build(source,label,historical=False,baseline=False):
    target=out/label;target.mkdir();spu=source/'runtime/spu'
    if historical:header=(fixtures/'spu_call_brackets_legacy.h').read_text()
    else:
        import spu_lifter
        header=emission(spu_lifter)
    if not historical:
        from update_spu_call_boundaries import update
        legacy=(fixtures/'spu_call_brackets_fork_legacy.h').read_text()
        rewritten,changed,existing=update(legacy)
        assert changed==8 and existing==0
        assert '\n'.join(rewritten.splitlines()[1:])+'\n'==header,'copy updater differs from actual emitter'
        assert update(header)==(header,0,8),'copy updater is not idempotent'
        try:update('spu_drain_call(ctx, variable_return);')
        except ValueError:pass
        else:raise AssertionError('unknown bracket silently accepted')
    (target/'spu_call_brackets.h').write_text(header)
    active_fixture=fixtures/'spu_interpreter_handoff.c' if baseline else fixture
    sources=[active_fixture,*[spu/n for n in names],source/'runtime/platform/win32_compat.c',source/'runtime/memory/guest_read_sync.c',source/'runtime/diag/loadtime_trace.c',source/'runtime/platform/thread_name.c']
    includes=[target,source/'include',spu,source/'runtime/platform']
    binary=target/('test.exe' if os.name=='nt' else 'test')
    if os.name=='nt':
        compiler=os.environ.get('MV_CLANG') or shutil.which('clang-cl')
        if not compiler:raise SystemExit('clang-cl plus the Visual Studio developer environment is required')
        command=[compiler,'/nologo','/TC','/std:c17','/O1','/UNDEBUG','/MDd',*['/I'+str(p) for p in includes],*map(str,sources),'/Fo'+str(target)+os.sep,'/Fe'+str(binary),'/link','Synchronization.lib']
    else:
        compiler=os.environ.get('CC') or shutil.which('cc');assert compiler,'C compiler required'
        command=[compiler,'-std=gnu17','-D_GNU_SOURCE','-O1','-UNDEBUG',*['-I'+str(p) for p in includes],*map(str,sources),'-pthread','-lm','-o',str(binary)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=120)
    (target/'build.log').write_text(result.stdout+result.stderr)
    entry={'label':label,'emission_sha256':hashlib.sha256(header.encode()).hexdigest(),'lifter_sha256':hashlib.sha256((source/'tools/spu_lifter.py').read_bytes()).hexdigest(),'command':command,'returncode':result.returncode,'sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'runs':[]}
    report['variants'].append(entry);(out/'result.json').write_text(json.dumps(report,indent=2))
    if result.returncode:
        print('Full compiler diagnostics: '+str(target/'build.log'),flush=True)
        print('\n'.join(s for s in (result.stdout+result.stderr).splitlines() if re.search(r'(?:error|unresolved|fatal)',s,re.I)),flush=True)
    assert result.returncode==0,'compile failed: '+str(target/'build.log')
    return binary,entry
def run(binary,entry,case,red=False,baseline=False):
    env={k:v for k,v in os.environ.items() if not k.startswith(('SPU_','SPURS_','YDKJ_','LBP_','GH3_'))}
    if not baseline:env['SPU_INTERP_UNLIFTED']='1'
    if baseline and case in ('stepcap','negative-stepcap'):env.update(YDKJ_SPU_TRACE='1',SPU_STEPCAP='2')
    result=subprocess.run([str(binary),str(case)],cwd=binary.parent,env=env,capture_output=True,text=True,timeout=10)
    entry['runs'].append({'case':case,'red':red,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    (out/'result.json').write_text(json.dumps(report,indent=2))
    if red:assert result.returncode!=0 and any(s in result.stderr for s in ['return boundary not published','interpreter passed native return boundary','outer return boundary not restored','return boundary queued compiled dispatch','compiled return entered while native caller owns it']),entry['runs'][-1]
    else:assert result.returncode==0 and ('PASS' if baseline else 'PASS exact call boundary') in result.stdout,entry['runs'][-1]
    print(('RED ' if red else 'PASS ')+entry['label']+' '+str(case),flush=True)
for historical in (False,True):
    binary,entry=build(sdk,'historical' if historical else 'production',historical)
    for case in range(17):run(binary,entry,case,historical)
binary,entry=build(sdk,'baseline',baseline=True)
for case in ['top','top-zero','nested-return','nested-return-unlifted','nested-calls','stop-zero','nested-stop','stop-code','halt','smc','pure-interpreter','stepcap','negative-stepcap']:run(binary,entry,case,baseline=True)
print('Evidence: '+str(out/'result.json'))
