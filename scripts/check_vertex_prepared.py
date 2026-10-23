#!/usr/bin/env python3
"""Actual prepared/scalar vertex parity, work controls and matched draw costs."""
import argparse,hashlib,json,os,platform,shutil,statistics,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--runtime',type=Path,default=root/'vendor/ps3recomp')
p.add_argument('--compiler')
p.add_argument('--mutants',action='store_true');p.add_argument('--benchmark',action='store_true')
p.add_argument('--output',type=Path,default=root/'build/self-tests/vertex-prepared')
a=p.parse_args();runtime=a.runtime.resolve()
if os.name=='nt':
    from project import build_environment
    tool_env=build_environment()
else:tool_env=os.environ.copy()
a.compiler=a.compiler or tool_env.get('MV_CLANG')or tool_env.get('CC')or shutil.which('cc')
assert a.compiler,'Set CC or --compiler'
out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
fixture=root/'scripts/fixtures/vertex_prepared.c';source=runtime/'libs/video/rsx_vertex_fetch.c'
files=[fixture,source,source.with_suffix('.h'),runtime/'libs/video/rsx_commands.h',runtime/'include/ps3emu/ps3types.h',Path(__file__)]
(out/'source-hashes.json').write_text(json.dumps({str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in files},indent=2),encoding='utf-8')
commands=[];records=[]
def build(name,text=None,counts=True):
    folder=out/name;folder.mkdir(exist_ok=True)
    text=source.read_text(encoding='utf-8')if text is None else text
    if counts:
        anchor='void rsx_fetch_attrib(const rsx_state* st, int idx, u32 vi, float out[4])\n{'
        assert text.count(anchor)==1
        text=text.replace(anchor,anchor+'\n    extern u64 test_fetch_calls; ++test_fetch_calls;')
    src=folder/'rsx_vertex_fetch.c';src.write_text(text,encoding='utf-8')
    (folder/'compiled-source-hash.json').write_text(json.dumps({'sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'call_count_instrumentation':counts}),encoding='utf-8')
    exe=folder/('test.exe'if os.name=='nt'else'test')
    if os.name=='nt':
        cmd=[a.compiler,'/nologo','/TC','/std:c17','/O2','/Ob2','/MDd','/Zi','/UNDEBUG','/Gy','/Gw',str(fixture),str(src),'/I'+str(runtime/'libs/video'),'/I'+str(runtime/'include'),'/Fo'+str(folder)+'/', '/Fe:'+str(exe),'/link','/OPT:REF']
        if counts:cmd.insert(2,'/DVERTEX_VERIFY_COUNTS')
    else:
        cmd=[a.compiler,'-std=c17','-D_POSIX_C_SOURCE=200809L','-O2','-UNDEBUG',str(fixture),str(src),'-I'+str(runtime/'libs/video'),'-I'+str(runtime/'include'),'-o',str(exe)]
        if counts:cmd.insert(2,'-DVERTEX_VERIFY_COUNTS')
    commands.append(cmd);(out/'commands.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
    r=subprocess.run(cmd,capture_output=True,text=True,cwd=folder,env=tool_env);(folder/'build.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,r.stdout+r.stderr
    return exe,folder
def run(exe,folder,args=(),expected=None,nofreq=False,diagnostic=False):
    env=tool_env.copy();env.pop('VP_NOFREQ',None);env.pop('VTX_TYPEDBG',None)
    if nofreq:env['VP_NOFREQ']='1'
    if diagnostic:env['VTX_TYPEDBG']='1'
    cmd=[str(exe),*args];r=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=90)
    records.append(dict(command=cmd,nofreq=nofreq,diagnostic=diagnostic,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr));(out/'runs.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    (folder/('last-nofreq.log'if nofreq else'last-run.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
    if expected:assert r.returncode!=0 and 'FAIL '+expected in r.stderr,(r.returncode,r.stdout,r.stderr)
    else:
        assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
        if diagnostic:assert '[VTXTYPE] UNHANDLED type=0' in r.stderr and '[VTXTYPE] UNHANDLED type=8'in r.stderr,r.stderr
    return r
exe,folder=build('actual')
for mode in [False,True]:run(exe,folder,nofreq=mode,diagnostic=True)
print('PASS actual prepared/scalar live vertex/default/mapping parity and real call counts; both frequency modes')
if a.mutants:
    text=source.read_text(encoding='utf-8')
    loop='    for (u32 i = 0; i < batch->count; ++i) {\n        u32 slot = batch->active[i];\n        rsx_fetch_attrib(batch->state, (int)slot, vi, out[slot].v);\n    }'
    signature='void rsx_fetch_vertex_prepared(const rsx_vertex_fetch_batch* batch, u32 vi,\n                               rsx_vertex_value out[16])\n{'
    mutants=[('historical-all-slots',loop,'    for (u32 i = 0; i < 16; ++i)\n        rsx_fetch_attrib(batch->state, (int)i, vi, out[i].v);','constant-only slots fetched individually'),
        ('lost-defaults','memcpy(out, batch->constants, sizeof(batch->constants));','memset(out, 0, sizeof(batch->constants));','initial defaults and arrays'),
        ('cached-live-data',signature,signature+'\n    static rsx_vertex_value saved[16]; static int valid;\n    if(valid) { memcpy(out,saved,sizeof saved);return; }', 'live vertex edits lost')]
    for name,before,after,why in mutants:
        assert text.count(before)==1,(name,before)
        changed=text.replace(before,after)
        if name=='cached-live-data':
            anchor='        rsx_fetch_attrib(batch->state, (int)slot, vi, out[slot].v);\n    }'
            assert changed.count(anchor)==1;changed=changed.replace(anchor,anchor+'\n    memcpy(saved,out,sizeof saved);valid=1;')
        exe,folder=build(name,changed)
        for mode in [False,True]:run(exe,folder,expected=why,nofreq=mode)
        print('PASS compiled '+name+' rejects intended '+why)
if a.benchmark:
    exe,folder=build('benchmark',counts=False);results=[]
    claim=dict(scope='Authored complete 16-slot draw fetch including preparation, live scalar array decoding and verified checksums; checked-O2/DebugCRT on Windows; no game/FPS claim.',logical_cpus=os.cpu_count(),platform=platform.platform(),executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),call_count_instrumentation=False)
    (folder/'claim.json').write_text(json.dumps(claim,indent=2),encoding='utf-8')
    for active in [0,4,8,12,16]:
        for n in [1,1024]:
            draws=max(1,20000000//n)
            for pair in range(5):
                for side in ['original','candidate']:
                    row=json.loads(run(exe,folder,[side,str(active),str(n),str(draws)]).stdout);row['pair']=pair;results.append(row)
            for side in ['original','candidate']:
                rows=[x for x in results if x['side']==side and x['active']==active and x['vertices']==n]
                times=[x['seconds']/(x['draws']*n)*1e9 for x in rows]
                print(json.dumps(dict(side=side,active=active,vertices=n,runs=len(times),median_ns_per_vertex=statistics.median(times),min_ns=min(times),max_ns=max(times))),flush=True)
            (folder/'results.json').write_text(json.dumps(dict(claim=claim,results=results),indent=2),encoding='utf-8')
