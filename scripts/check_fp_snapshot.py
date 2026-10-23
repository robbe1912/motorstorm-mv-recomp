#!/usr/bin/env python3
"""Actual native fragment-snapshot decisions and optional matched helper timings."""
import argparse,hashlib,json,os,platform,shutil,statistics,subprocess
from project import build_environment
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
env=build_environment() if os.name=='nt' else os.environ.copy()
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--compiler',default=env.get('MV_CLANG')or os.environ.get('CC')or shutil.which('clang-cl'if os.name=='nt'else'cc'))
p.add_argument('--mutants',action='store_true');p.add_argument('--benchmark',action='store_true')
p.add_argument('--runtime',type=Path,default=repo/'vendor/ps3recomp');p.add_argument('--output',type=Path,default=repo/'build/self-tests/fp-snapshot')
args=p.parse_args();root=args.runtime.resolve();assert args.compiler,'Set CC or --compiler'
out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
fixture=repo/'scripts/fixtures/fp_snapshot.c';header=root/'libs/video/rsx_fp_snapshot.h';decompiler=root/'libs/video/rsx_fp_decompiler.c'
manifest={str(x.relative_to(repo)) if x.is_relative_to(repo) else str(x):hashlib.sha256(x.read_bytes()).hexdigest()for x in [fixture,header,decompiler,root/'libs/video/rsx_fp_decompiler.h',root/'include/ps3emu/ps3types.h',Path(__file__)]}
(out/'source-hashes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
commands=[];run_records=[]
def build(name,override=None,counts=True):
    folder=out/name;folder.mkdir(exist_ok=True);exe=folder/('fixture.exe'if os.name=='nt'else'fixture')
    command=[args.compiler,str(fixture),str(decompiler)]
    includes=([override]if override else[])+[root/'libs/video',root/'include']
    if os.name=='nt':command+=['/nologo','/std:c17','/O2','/Ob2','/MDd','/Zi','/UNDEBUG','/Gy','/Gw',*['/I'+str(x)for x in includes],*(['/DFP_SNAPSHOT_VERIFY_COUNTS']if counts else[]),'/Fo'+str(folder)+os.sep,'/Fe'+str(exe),'/link','/OPT:REF']
    else:command+=['-std=c17','-D_POSIX_C_SOURCE=200809L','-O2','-UNDEBUG','-ffunction-sections','-fdata-sections',*['-I'+str(x)for x in includes],*(['-DFP_SNAPSHOT_VERIFY_COUNTS']if counts else[]),'-lm','-o',str(exe)]
    commands.append(command);(out/'commands.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
    result=subprocess.run(command,env=env,capture_output=True,text=True,errors='replace');(folder/'build.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode:raise AssertionError(f'{name} compiler failure: {result.stdout}{result.stderr}')
    return exe,folder
def run(exe,folder,arguments=None,expected=None):
    command=[str(exe),*(arguments or[])];result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=120)
    run_records.append(dict(command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
    (out/'run-commands.json').write_text(json.dumps(run_records,indent=2),encoding='utf-8')
    if not arguments:(folder/'run.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    if expected:assert result.returncode and expected in result.stderr,(result.returncode,result.stdout,result.stderr)
    else:assert result.returncode==0,(result.returncode,result.stdout,result.stderr)
    return result
exe,folder=build('actual');run(exe,folder);print('PASS actual FP snapshot decisions and unchanged-path hash count')
if args.mutants:
    source=header.read_text(encoding='utf-8')
    mutants=[('eager-hash','    if (memcmp(live, bound, size) == 0)\n        return RSX_FP_SNAPSHOT_KEEP;\n    return rsx_fp_structural_hash(live, capacity, 0) == hash\n        ? RSX_FP_SNAPSHOT_REFRESH : RSX_FP_SNAPSHOT_KEEP;','    return rsx_fp_structural_hash(live, capacity, 0) == hash && memcmp(live, bound, size) != 0 ? RSX_FP_SNAPSHOT_REFRESH : RSX_FP_SNAPSHOT_KEEP;', 'unchanged snapshot redundantly rehashed'),
             ('blind-reuse','    return rsx_fp_structural_hash(live, capacity, 0) == hash\n        ? RSX_FP_SNAPSHOT_REFRESH : RSX_FP_SNAPSHOT_KEEP;','    return RSX_FP_SNAPSHOT_KEEP;', 'inline constant refresh'),
             ('refresh-recycled','? RSX_FP_SNAPSHOT_REFRESH : RSX_FP_SNAPSHOT_KEEP;','? RSX_FP_SNAPSHOT_REFRESH : RSX_FP_SNAPSHOT_REFRESH;', 'recycled structural program stays bound')]
    for name,before,after,failure in mutants:
        assert source.count(before)==1
        folder=out/name;folder.mkdir(exist_ok=True);mutated=folder/header.name;mutated.write_text(source.replace(before,after),encoding='utf-8')
        (folder/'source-hash.json').write_text(json.dumps({header.name:hashlib.sha256(mutated.read_bytes()).hexdigest()}),encoding='utf-8')
        exe,folder=build(name,folder);run(exe,folder,expected='FAIL '+failure);print('PASS compiled '+name+' mutant rejects intended '+failure)
if args.benchmark:
    exe,folder=build('benchmark',counts=False);results=[]
    claim='Matched checked-O2/DebugCRT Windows (O2 POSIX) helper CPU timing on authored identical/constant-edited snapshots only; no full draw/game/FPS claim.'
    (folder/'claim.json').write_text(json.dumps(dict(claim=claim,logical_cpus=os.cpu_count(),platform=platform.platform(),counts_instrumentation=False,executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())),encoding='utf-8')
    for n in [1,32,128]:
        for edit in [0,1]:
            for pair in range(5):
                for side in ['original','candidate']:
                    r=json.loads(run(exe,folder,[side,str(n),'1000000',str(edit)]).stdout);r['pair']=pair;results.append(r)
            for side in ['original','candidate']:
                rows=[r for r in results if r['side']==side and r['edit']==edit and r['bytes']==n*32];times=[r['seconds']/r['iterations']*1e9 for r in rows]
                print(json.dumps(dict(side=side,bytes=n*32,edit=edit,runs=len(times),median_ns=statistics.median(times),min_ns=min(times),max_ns=max(times))))
    (folder/'results.json').write_text(json.dumps(dict(claim=claim,results=results),indent=2),encoding='utf-8')
