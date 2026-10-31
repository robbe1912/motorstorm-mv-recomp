#!/usr/bin/env python3
"""Exercise actual interpreter, return macros and scoped dispatch with authored dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

root=Path(__file__).resolve().parents[1]
toolkit=root/'vendor/ps3recomp'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--compiler',default=os.environ.get('CC') or ('clang-cl' if os.name=='nt' else 'cc'))
p.add_argument('--mutants',action='store_true')
p.add_argument('--syntax',action='store_true')
p.add_argument('--output',default='build/self-tests/spu-execution-observers')
a=p.parse_args();out=root/a.output;out.mkdir(parents=True,exist_ok=True)
compiler=shutil.which(a.compiler) or a.compiler
msvc=Path(compiler).name.lower() in ('cl','cl.exe','clang-cl','clang-cl.exe')
spu=toolkit/'runtime/spu';diag=toolkit/'runtime/diag/spu_execution_observer.c'
sources={x:(toolkit/x).read_text() for x in ['runtime/spu/spu_context.h','runtime/spu/spu_interp.c',
    'runtime/spu/spu_drain.c','runtime/spu/spu_channels.c','runtime/diag/spu_execution_observer.c',
    'runtime/spu/spu_float_simd.c','runtime/spu/spu_float_simd.h','runtime/spu/spu_float.h','runtime/spu/spu_helpers.h']}
def function(text,signature):
    start=text.index(signature);opening=text.index('{',start)
    clean=re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                 lambda m:' '*len(m[0]),text)
    depth=1;i=opening+1
    while depth:depth+=(clean[i]=='{')-(clean[i]=='}');i+=1
    return text[start:i]
def execute(cmd,d,label):
    (d/(label+'-command.json')).write_text(json.dumps(cmd,indent=2))
    r=subprocess.run(cmd,cwd=d,env=env,capture_output=True,text=True,timeout=90)
    (d/(label+'.log')).write_text(r.stdout+r.stderr)
    return r
env=os.environ.copy()
for key in list(env):
    if key.startswith(('SPU_','SPURS_','YDKJ_','LBP_','GH3_')):env.pop(key)
if a.syntax:
    for enabled in (0,1):
        for path in ['runtime/spu/spu_interp.c','runtime/spu/spu_drain.c',
                     'runtime/diag/spu_execution_observer.c','runtime/spu/spu_channels.c']:
            flags=(['/nologo','/std:c17','/Zs','/D_CRT_SECURE_NO_WARNINGS',
                '/DPS3_EXECUTION_OBSERVATION='+str(enabled),'/I'+str(toolkit/'include'),'/I'+str(spu)]
                if msvc else ['-std=gnu17','-fsyntax-only','-DPS3_EXECUTION_OBSERVATION='+str(enabled),
                             '-I'+str(toolkit/'include'),'-I'+str(spu)])
            r=execute([compiler,*flags,str(toolkit/path)],out,
                      Path(path).stem+'-syntax-'+str(enabled))
            assert r.returncode==0,r.stdout+r.stderr
    consumer=out/'consumer.cpp'
    consumer.write_text('#include "spu_context.h"\nvoid return_consumer(spu_context* c) { SPU_RET(c); }\n')
    for enabled in (0,1):
        flags=(['/nologo','/std:c++17','/Zs','/DPS3_EXECUTION_OBSERVATION='+str(enabled),
                '/I'+str(toolkit/'include'),'/I'+str(spu)] if msvc else
               ['-std=gnu++17','-fsyntax-only','-DPS3_EXECUTION_OBSERVATION='+str(enabled),
                '-I'+str(toolkit/'include'),'-I'+str(spu)])
        r=execute([compiler,*flags,str(consumer)],out,'cpp-syntax-'+str(enabled))
        assert r.returncode==0,r.stdout+r.stderr
def build_run(name,enabled,changes=None):
    d=out/name;d.mkdir(exist_ok=True);contents=dict(sources)
    for path,before,after in changes or []:
        assert contents[path].count(before)==1,(path,before)
        contents[path]=contents[path].replace(before,after)
    # Copy only authored runtime support into ignored output so header mutants
    # exercise real macros without changing source or private generated inputs.
    local=d/'runtime/spu';shutil.copytree(spu,local,dirs_exist_ok=True)
    shutil.copytree(toolkit/'include',d/'include',dirs_exist_ok=True)
    shutil.copytree(toolkit/'runtime/platform',d/'runtime/platform',dirs_exist_ok=True)
    for path in ['runtime/spu/spu_context.h','runtime/spu/spu_interp.c']:
        (local/Path(path).name).write_text(contents[path])
    (d/'observer.c').write_text(contents['runtime/diag/spu_execution_observer.c'].replace(
        '#include "../spu/spu_context.h"','#include "spu_context.h"'))
    drain=function(contents['runtime/spu/spu_drain.c'],'static void spu_drain_call_scoped_body(')
    # The curated drain has additional diagnostics and policy routing. Exercise
    # its exact selection/IRQ/call slice in an authored loop, not a fork model.
    begin=drain.index('            spu_task_launch_check(ctx, (void*)fn);')
    end=drain.index('            fn(ctx);',begin)+len('            fn(ctx);')
    pop=next(line for line in drain.splitlines() if line.startswith('#define SPU_DRAIN_POP_IRQ()'))
    base=next(line for line in drain.splitlines() if 'PS3_SPU_DISPATCH_BASE(fn);' in line)
    body=('static int pm_interp_forced(const spu_context* c) { (void)c; return 0; }\n'
        'static void spu_drain_call_scoped_body(spu_context* ctx, uint32_t return_pc) {\n'
        'spu_irq_frame f={0}; int s_diag=0; (void)return_pc;\n'+pop+'\n'
        'while (g_spu_trampoline_fn) {\n'
        'void (*fn)(spu_context*)=g_spu_trampoline_fn; g_spu_trampoline_fn=0;\n'
        +base+'\n'+drain[begin:end]+'\n}\nSPU_DRAIN_POP_IRQ();\n#undef SPU_DRAIN_POP_IRQ\n}\n')
    fixture=(root/'scripts/fixtures/spu_execution_observer.c').read_text()
    assert fixture.count('/* ACTUAL_SCOPED_BODY */')==1
    indirect=function(contents['runtime/spu/spu_channels.c'],'void spu_indirect_branch(')
    tail=function(indirect[indirect.rindex('    if (fn) {'):],'if (fn)')
    assert '__attribute__((musttail)) return fn(ctx);' in tail
    assert fixture.count('/* ACTUAL_RESOLVED_TAIL */')==1
    fixture=fixture.replace('/* ACTUAL_RESOLVED_TAIL */',tail)
    (d/'fixture.c').write_text(fixture.replace('/* ACTUAL_SCOPED_BODY */',body))
    exe=d/('fixture.exe'if os.name=='nt'else'fixture')
    inputs=[str(local/'spu_interp.c'),str(toolkit/'runtime/spu/spu_float_simd.c'),
            str(d/'observer.c'),str(d/'fixture.c')]
    if msvc:
        flags=['/nologo','/std:c17','/O2','/UNDEBUG','/D_CRT_SECURE_NO_WARNINGS',
            '/DPS3_EXECUTION_OBSERVATION='+str(enabled),'/I'+str(toolkit/'include'),'/I'+str(local),
            '/Fo'+str(d)+os.sep,'/Fe'+str(exe)]
    else:
        flags=['-std=gnu17','-O2','-UNDEBUG','-DPS3_EXECUTION_OBSERVATION='+str(enabled),
            '-I'+str(toolkit/'include'),'-I'+str(local),'-lm','-o',str(exe)]
    r=execute([compiler,*inputs,*flags],d,'build')
    assert r.returncode==0,r.stdout+r.stderr
    r=execute([str(exe)],d,'run')
    return r
for enabled in (0,1):
    r=build_run('production-'+str(enabled),enabled)
    assert r.returncode==0,r.stdout+r.stderr
    assert 'outputs and native admission retained' in r.stdout
controls=[]
if a.mutants:
    cases=[('missing-interpreted','runtime/spu/spu_interp.c',
        'PS3_SPU_EXECUTION(PS3_SPU_INTERPRETED_CONTROL, ctx, pc, next,',
        'PS3_SPU_EXECUTION(PS3_SPU_NATIVE_BEGIN, ctx, pc, next,',
        'events[1].kind==PS3_SPU_INTERPRETED_CONTROL'),
       ('force-interpretation','runtime/spu/spu_interp.c',
        'if (native_busy || !native_ready(ctx)) return 0;',
        'if (PS3_EXECUTION_OBSERVATION || native_busy || !native_ready(ctx)) return 0;',
        'native_calls==1'),
       ('missing-scoped-dispatch','runtime/spu/spu_drain.c',
        '            PS3_SPU_DISPATCH(ctx, fn);','            /* omitted observation */',
        'count==(unsigned)(interrupt?1:2)'),
       ('missing-return','runtime/spu/spu_context.h',
        'PS3_SPU_COMPILED_RETURN, (ctx), 0, (ctx)->pc, 0,',
        'PS3_SPU_NATIVE_END, (ctx), 0, (ctx)->pc, 0,',
        'events[1].kind==PS3_SPU_COMPILED_RETURN'),
       ('wrong-interrupt-function','runtime/spu/spu_drain.c',
        'PS3_SPU_DISPATCH(ctx, vf);','PS3_SPU_DISPATCH(ctx, fn);',
        'events[0].function==(uintptr_t)(interrupt?irq:plain)'),
       ('missing-resolved-call','runtime/spu/spu_channels.c',
        'PS3_SPU_RESOLVED(ctx, fn);','/* omitted resolved call */',
        'count==2 && events[0].function==(uintptr_t)plain'),
       ('repeat-register-expression','runtime/spu/spu_context.h',
        '(ctx)->pc, _ps3_return_register,','(ctx)->pc, (n),',
        'return_register==7'),
       ('hidden-clock','runtime/diag/spu_execution_observer.c',
        '(!event.tick ? PS3_SPU_CLOCK_INVALID : 0)','0',
        'events[0].flags&PS3_SPU_CLOCK_INVALID')]
    for name,path,before,after,message in cases:
        r=build_run(name,1,[(path,before,after)])
        assert r.returncode!=0 and message in r.stdout+r.stderr,(name,r.returncode,r.stdout,r.stderr)
        controls.append({'name':name,'returncode':r.returncode,'assertion':message})
def public_source(x):
    if x=='tests/spu_execution_observer.c': return root/'scripts/fixtures/spu_execution_observer.c'
    if x=='tools/test_spu_execution_observer.py': return Path(__file__)
    return toolkit/x
manifest={'compiler':compiler,'production_modes':[0,1],'controls':controls,
    'sources':{x:hashlib.sha256(public_source(x).read_bytes()).hexdigest() for x in [*sources,
        'runtime/spu/spu_native_leaf.h','runtime/spu/spu_helpers.h',
        'runtime/spu/spu_interp_tables.inc','include/ps3emu/spu_execution_observer.h','tests/spu_execution_observer.c',
        'tools/test_spu_execution_observer.py']},
    'scope':'Actual interpreter/native admission, real return/dispatch macros and exact dispatch/IRQ/call slice in authored loop; authored channel/VM/IRQ dependencies. Not full interrupt/coherence/game timeline or overhead proof.'}
(out/'result.json').write_text(json.dumps(manifest,indent=2))
print('PASS actual execution modes 0/1, native admission and specific coverage controls')
