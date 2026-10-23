#!/usr/bin/env python3
"""Execute real concurrent policy runners and joined-lane productivity checks."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
import hashlib
from project import ROOT, build_environment

def build_and_run(runtime, out, expected_failure=None):
    spu=runtime/'runtime/spu'
    out.mkdir(parents=True,exist_ok=True)
    fixture=ROOT/'scripts/fixtures/spurs_policy_counters.c'
    units=['spu_drain','spu_lockstep','spu_coherency','spu_workload',
           'spurs_policy','spurs_job','spu_tsp_weak','spu_vm_pagemap',
           'spurs_policy_blob_weak','spu_interp','spu_task_lifecycle']
    # Selected consumers can carry the independently compiled SIMD scope unit.
    if (spu/'spu_float_simd.c').is_file():units.append('spu_float_simd')
    env={k:v for k,v in build_environment().items() if not k.startswith(('SPU_','SPURS_','YDKJ_','LBP_','GH3_'))}
    exe=out/('fixture.exe' if os.name=='nt' else 'fixture')
    inputs=[fixture,ROOT/'scripts/fixtures/spurs_policy_counter_intercepts.c',*[spu/(u+'.c') for u in units],
            *[runtime/'runtime'/p for p in ['platform/win32_compat.c','memory/guest_read_sync.c',
              'syscalls/spu_ea_alias.c','platform/thread_name.c','diag/loadtime_trace.c']]]
    includes=[runtime/'include',spu,runtime/'runtime/platform',runtime/'libs/spurs']
    tracked=inputs+[runtime/'libs/spurs/cellSpurs.c',spu/'spu_context.h',
                    spu/'spu_dma.h',spu/'spu_workload.h',spu/'spu_policy_counters.h']
    (out/'source-hashes.json').write_text(json.dumps({str(path):hashlib.sha256(path.read_bytes()).hexdigest()
                                                   for path in tracked},indent=2))
    if os.name=='nt':
        cmd=[env.get('MV_CLANG','clang-cl'),'/nologo','/std:c17','/O2','/UNDEBUG','/Gy','/Gw','/D_CRT_SECURE_NO_WARNINGS',
             *['/I'+str(p) for p in includes],*map(str,inputs),'/Fo'+str(out)+os.sep,'/Fe'+str(exe),'/link','/OPT:REF']
    else:
        cmd=[env.get('CC','cc'),'-std=gnu17','-O2','-UNDEBUG','-ffunction-sections','-fdata-sections',
             '-Wl,-dead_strip' if sys.platform=='darwin' else '-Wl,--gc-sections',
             *['-I'+str(p) for p in includes],*map(str,inputs),'-pthread','-lm','-o',str(exe)]
    (out/'command.json').write_text(json.dumps(cmd,indent=2))
    built=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=120)
    (out/'build.log').write_text(built.stdout+built.stderr)
    if built.returncode:
        print('\n'.join(line for line in (built.stdout+built.stderr).splitlines() if 'error' in line.lower()))
        print('Full diagnostics:',out/'build.log');return built.returncode
    for mode in ['compiled','interpreted']:
        run_command=[str(exe),*(['--interpreted'] if mode=='interpreted' else [])]
        ran=subprocess.run(run_command,cwd=out,env=env,capture_output=True,text=True,timeout=20)
        (out/f'{mode}-run.log').write_text(ran.stdout+ran.stderr)
        (out/f'{mode}-run-command.json').write_text(json.dumps(run_command))
        if expected_failure:
            if not ran.returncode or ('FAIL '+expected_failure) not in ran.stderr:
                raise RuntimeError(f'Negative control missed intended {mode} assertion: {out}')
            print(f'PASS {out.name} compiled and rejected by {mode} {expected_failure}')
            continue
        if ran.returncode:
            print(ran.stdout+ran.stderr);return ran.returncode
        for marker in ['PASS actual concurrent policy exit/poll/DMA isolation',
                       'PASS actual joined scheduler worker productivity and idle rounds',
                       f'PASS actual {mode} kernel intercepts']:
            if marker not in ran.stdout:raise RuntimeError(f'Missing execution marker: {marker}')
            print(marker)
    return 0

RESET='''    /* Clear before admission: a rejected/busy run must not inherit productivity. */
    g_spurs_pm_polls = 0;
    g_spurs_pm_exited = 0;
    g_wws_batch_gets = 0;
'''

def replace_once(path, before, after):
    source=path.read_text()
    if source.count(before)!=1:raise RuntimeError(f'Negative-control anchor changed: {path}')
    path.write_text(source.replace(before,after))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,default=ROOT/'vendor/ps3recomp')
    parser.add_argument('--output',type=Path,default=ROOT/'build/self-tests/spurs-policy-counters')
    parser.add_argument('--mutants',action='store_true')
    args=parser.parse_args()
    runtime,out=args.runtime.resolve(),args.output.resolve()
    result=build_and_run(runtime,out)
    if result or not args.mutants:return result
    for name,failure in [
        ('global-counters','per-run stop versus kernel-exit classification'),
        ('dropped-worker-polls','joined worker productivity aggregation'),
        ('stale-rejected-run','rejected run inherited stale productivity')]:
        mutant_out=out/name
        mutant=mutant_out/'runtime-copy'
        def source_only(directory,names):
            return [name for name in names if (Path(directory)/name).is_file()
                    and Path(name).suffix not in {'.c','.h','.inc','.inl','.def'}]
        for directory in ['include','runtime','libs/spurs']:
            shutil.copytree(runtime/directory,mutant/directory,dirs_exist_ok=True,ignore=source_only)
        if name=='global-counters':
            for relative in ['runtime/spu/spurs_policy.c','runtime/spu/spu_policy_counters.h']:
                path=mutant/relative
                source=path.read_text();before='SPU_THREAD_LOCAL volatile unsigned g_'
                if source.count(before)!=3:raise RuntimeError('Counter declaration anchors changed')
                path.write_text(source.replace(before,'volatile unsigned g_'))
        elif name=='dropped-worker-polls':
            replace_once(mutant/'libs/spurs/cellSpurs.c',
                         'productive |= workers[sn - 1].polled;','productive |= 0;')
        else:
            path=mutant/'runtime/spu/spurs_policy.c'
            replace_once(path,RESET,'')
            anchor='    if (wid >= SPURS_PM_MAX_WKL || spu_num >= 6) return -1;'
            replace_once(path,anchor,RESET+anchor)
        result=build_and_run(mutant,mutant_out,failure)
        if result:return result
    return 0

if __name__=='__main__':raise SystemExit(main())
