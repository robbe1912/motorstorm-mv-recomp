#!/usr/bin/env python3
"""Run real bounded SPURS scheduling with manufactured policy modules only."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess

from project import ROOT, build_environment
root = ROOT/'vendor/ps3recomp'
fixture = ROOT/'scripts/fixtures/spurs_scheduler.c'
build_env = build_environment()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mutants', action='store_true', help='Reject serialized-admission regression')
parser.add_argument('--runtime',type=Path,default=root,help='Selected consumer runtime')
parser.add_argument('--output',type=Path,default=ROOT/'build/self-tests/spurs-scheduler')
parser.add_argument('--compiler', default=os.environ.get('CC') or
                    (build_env.get('MV_CLANG','clang-cl') if os.name=='nt' else build_env.get('CC','cc')))
args = parser.parse_args()
assert args.compiler, 'Set CC or --compiler to a C17 compiler'
root = args.runtime.resolve()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
units = ['spu_drain','spu_lockstep','spu_coherency','spu_workload',
         'spurs_policy','spurs_job','spu_tsp_weak','spu_vm_pagemap',
         'spurs_policy_blob_weak','spu_interp','spu_task_lifecycle']
if (root/'runtime/spu/spu_float_simd.c').is_file():units.append('spu_float_simd')
exe = out / ('fixture.exe' if os.name == 'nt' else 'fixture')
command = [args.compiler, str(fixture), str(ROOT/'scripts/fixtures/spurs_policy_counter_intercepts.c'),
           *[str(root/'runtime/spu'/f'{unit}.c') for unit in units],
           str(root/'runtime/platform/win32_compat.c'),
           str(root/'runtime/memory/guest_read_sync.c'),
           str(root/'runtime/platform/thread_name.c'),
           str(root/'runtime/syscalls/spu_ea_alias.c'),
           str(root/'runtime/diag/loadtime_trace.c')]
includes = [root/'include', root/'runtime/spu', root/'runtime/platform',root/'libs/spurs']
if os.name == 'nt':
    command += ['/nologo','/std:c17','/O2','/UNDEBUG','/Gy','/Gw',
                *['/I'+str(path) for path in includes], '/Fo'+str(out)+os.sep,
                '/Fe'+str(exe), '/link','/OPT:REF']
else:
    command += ['-std=gnu17','-D_GNU_SOURCE','-O2','-UNDEBUG','-ffunction-sections','-fdata-sections',
                '-Wl,-dead_strip' if platform.system()=='Darwin' else '-Wl,--gc-sections',
                *['-I'+str(path) for path in includes], '-pthread','-lm','-o',str(exe)]
env = {key:value for key,value in build_env.items()
       if not key.startswith(('SPU_','SPURS_','YDKJ_','LBP_','GH3_'))}
tracked=[Path(arg) for arg in command if str(arg).endswith('.c')]
tracked += [root/'runtime/spu/spu_channels.c',root/'libs/spurs/cellSpurs.c',root/'runtime/spu/spu_context.h',root/'runtime/spu/spu_workload.h',root/'runtime/spu/spu_policy_counters.h']
(out/'source-hashes.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked},indent=2))
# Compile changed production modules independently: a fixture's preceding
# includes must not conceal a missing module-level declaration.
standalone=[args.compiler]
if os.name=='nt':
    standalone += ['/nologo','/std:c17','/UNDEBUG','/Zs',*['/I'+str(path) for path in includes]]
else:
    standalone += ['-std=gnu17','-D_GNU_SOURCE','-UNDEBUG','-fsyntax-only',*['-I'+str(path) for path in includes]]
standalone += [str(root/'libs/spurs/cellSpurs.c'),str(root/'runtime/spu/spurs_policy.c')]
(out/'standalone-command.json').write_text(json.dumps(standalone,indent=2))
checked=subprocess.run(standalone,env=env,cwd=out,capture_output=True,text=True,timeout=120)
(out/'standalone-build.log').write_text(checked.stdout+checked.stderr)
if checked.returncode:
    print('\n'.join(line for line in (checked.stdout+checked.stderr).splitlines() if 'error' in line.lower()))
    raise SystemExit('Production module compilation failed: '+str(out/'standalone-build.log'))
print('PASS changed production modules compile independently of fixture includes')
(out/'command.json').write_text(json.dumps(command, indent=2))
built = subprocess.run(command, env=env, cwd=out, capture_output=True, text=True)
(out/'build.log').write_text(built.stdout+built.stderr)
if built.returncode:
    print('\n'.join(line for line in (built.stdout+built.stderr).splitlines() if 'error' in line.lower()))
    raise SystemExit('Actual scheduler fixture did not build; full diagnostics: '+str(out/'build.log'))
ran = subprocess.run([str(exe)], env=env, cwd=out, capture_output=True, text=True, timeout=30)
(out/'run.log').write_text(ran.stdout+ran.stderr)
print(ran.stdout, end='')
print(ran.stderr, end='')
assert ran.returncode == 0, 'Actual scheduler fixture failed; retain run.log'
assert 'SPURS same workload/lane across instances retains separate LS and TLS exit classification PASS' in ran.stdout
print('PASS actual scheduler on '+platform.system()+'; no title inputs or skipped execution')

if args.mutants:
    for name,failure in [
        ('serialized-admission','runnable producer could not run'),
        ('consumed-ready-demand','scheduler consumed policy-owned requested lanes'),
        ('stale-rejected-policy','rejected policy retained preceding worker productivity')]:
        mutant=out/name
        (mutant/'tests').mkdir(parents=True,exist_ok=True)
        (mutant/'libs/spurs').mkdir(parents=True,exist_ok=True)
        (mutant/'runtime/spu').mkdir(parents=True,exist_ok=True)
        shutil.copy2(fixture,mutant/'tests/test_spurs_scheduler.c')
        source=(root/'libs/spurs/cellSpurs.c').read_text()
        policy=(root/'runtime/spu/spurs_policy.c').read_text()
        if name=='serialized-admission':
            start=source.index('static DWORD WINAPI spurs_kernel_thread(LPVOID p)\n{')
            before='for (u32 sn = 0; sn < si->nspus; sn++)'
            assert before in source[start:]
            source=source[:start]+source[start:].replace(before,'for (u32 sn = 0; sn < 1; sn++)',1)
        elif name=='consumed-ready-demand':
            before='                /* Requested lanes are policy-owned demand'
            assert source.count(before)==1
            source=source.replace(before,'                if (ready) vm_base[ea + SPURS_WKL_READY1 + wid] = (u8)(ready - 1);\n'+before)
        else:
            before='    g_spurs_pm_polls = 0;\n    g_spurs_pm_exited = 0;\n    g_wws_batch_gets = 0;\n'
            assert policy.count(before)==1
            policy=policy.replace(before,'')
            admission='    if (wid >= SPURS_PM_MAX_WKL || spu_num >= 6) return -1;'
            assert policy.count(admission)==1
            policy=policy.replace(admission,before+admission)
        (mutant/'libs/spurs/cellSpurs.c').write_text(source)
        (mutant/'runtime/spu/spurs_policy.c').write_text(policy)
        mutant_exe=mutant/('fixture.exe' if os.name=='nt' else 'fixture')
        replacements={str(fixture):str(mutant/'tests/test_spurs_scheduler.c'),
                      str(root/'runtime/spu/spurs_policy.c'):str(mutant/'runtime/spu/spurs_policy.c'),
                      '/Fe'+str(exe):'/Fe'+str(mutant_exe),str(exe):str(mutant_exe),
                      '/Fo'+str(out)+os.sep:'/Fo'+str(mutant)+os.sep,
                      ('/I' if os.name=='nt' else '-I')+str(root/'libs/spurs'):('/I' if os.name=='nt' else '-I')+str(mutant/'libs/spurs')}
        mutant_command=[replacements.get(arg,arg) for arg in command]
        extra=[('/I' if os.name=='nt' else '-I')+str(root/path) for path in ('tests','libs/spurs')]
        position=mutant_command.index('/link') if os.name=='nt' else len(mutant_command)
        mutant_command[position:position]=extra
        (mutant/'command.json').write_text(json.dumps(mutant_command,indent=2))
        built=subprocess.run(mutant_command,env=env,cwd=mutant,capture_output=True,text=True)
        (mutant/'build.log').write_text(built.stdout+built.stderr)
        assert built.returncode==0, 'Mutant must compile: '+str(mutant/'build.log')
        ran=subprocess.run([str(mutant_exe)],env=env,cwd=mutant,capture_output=True,text=True,timeout=15)
        (mutant/'run.log').write_text(ran.stdout+ran.stderr)
        assert ran.returncode!=0 and failure in ran.stderr, 'Mutant escaped or failed for another reason: '+name
        if name=='serialized-admission':
            print('PASS serialized-admission mutant compiled and failed the real producer-progress assertion')
        else:
            print('PASS '+name+' mutant compiled and failed its intended behavioral assertion')
