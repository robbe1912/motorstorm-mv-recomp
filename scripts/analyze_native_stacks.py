#!/usr/bin/env python3
"""Attribute saved native stacks; never opens a target process or launches a game."""
import argparse
from collections import Counter,defaultdict
import hashlib,json,struct
from pathlib import Path
from native_stack_replay import ROOT,Replay,compile_reader,sha,codeview_identity

REGISTERS=['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi','r8','r9','r10','r11','r12','r13','r14','r15']

def checked_blob(packet,metadata):
    path=(packet/metadata['path']).resolve()
    if not path.is_relative_to(packet.resolve()) or path.is_symlink():
        raise ValueError('Blob escapes admitted packet')
    data=path.read_bytes()
    if len(data)!=metadata['bytes'] or hashlib.sha256(data).hexdigest()!=metadata['sha256']:
        raise ValueError('Archived blob identity mismatch')
    return data

def checked_image(path):
    path=Path(path).resolve()
    if not path.is_absolute() or str(path).startswith('\\\\') or not path.is_file():
        raise ValueError('A local existing PE is required')
    data=path.read_bytes()
    if len(data)<64:raise ValueError('Truncated PE header')
    offset=struct.unpack_from('<I',data,0x3c)[0]
    if offset+24+60>len(data):raise ValueError('Truncated PE optional header')
    if data[:2]!=b'MZ' or data[offset:offset+4]!=b'PE\0\0' or struct.unpack_from('<H',data,offset+4)[0]!=0x8664:
        raise ValueError('Not an x64 PE')
    return struct.unpack_from('<I',data,offset+24+56)[0],hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--exe-sha',required=True)
    parser.add_argument('--pdb-sha',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();packet=args.packet.resolve();out=args.output.resolve()
    if out==packet or out.is_relative_to(packet):raise ValueError('Outputs must stay outside archived packet')
    out.mkdir(parents=True,exist_ok=True)
    exe=args.exe.resolve();image_size,exe_hash=checked_image(exe)
    if exe_hash!=args.exe_sha or sha(exe.with_suffix('.pdb'))!=args.pdb_sha:
        raise ValueError('EXE/PDB admission mismatch')
    with (packet/'timeline.jsonl').open(encoding='utf-8') as stream:
        header=json.loads(next(stream))
        if header['kind']!='identity' or header['owner']['exe_sha256']!=args.exe_sha or header['layout']['pdb_sha256']!=args.pdb_sha:
            raise ValueError('Capture identity admission mismatch')
        modules=[];unavailable=[]
        for record in header['modules']:
            try:
                size,digest=checked_image(record['path'])
                if size!=record['size']:raise ValueError('PE image extent changed')
                modules.append(dict(record,sha256=digest,identity_scope='capture-bound EXE' if Path(record['path']).resolve()==exe else 'current local DLL; historical bytes not independently captured'))
            except (ValueError,OSError,struct.error) as error:
                unavailable.append(dict(record,error=str(error)))
        chosen=[m for m in modules if Path(m['path']).resolve()==exe]
        if len(chosen)!=1 or chosen[0]['size']!=image_size:raise ValueError('Exact captured EXE not mapped')
        ordered=sorted(modules,key=lambda m:m['base'])
        if any(a['base']+a['size']>b['base'] for a,b in zip(ordered,ordered[1:])):raise ValueError('Overlapping module ranges')
        library=compile_reader(out/'reader')
        replay=Replay(library,modules,exe.parent)
        counts=Counter();reasons=defaultdict(Counter);inclusive=defaultdict(Counter);walks=[]
        try:
            for line in stream:
                row=json.loads(line)
                for thread in row.get('threads',[]):
                    blobs=thread.get('native_stack_files',[])
                    if not blobs:continue
                    if thread['previous_suspend_count']!=0:raise ValueError('Thread was already suspended')
                    by_kind={Path(b['path']).suffixes[-2]:b for b in blobs}
                    context=checked_blob(packet,by_kind['.win64-context']);stack=checked_blob(packet,by_kind['.stack'])
                    if len(context)!=1232:raise ValueError('Wrong Win64 CONTEXT extent')
                    registers=dict(zip(REGISTERS,struct.unpack_from('<16Q',context,0x78)))
                    if registers!=thread['regs'] or struct.unpack_from('<Q',context,0xf8)[0]!=thread['ip']:
                        raise ValueError('Archived CONTEXT disagrees with recorded registers')
                    rsp=registers['rsp'];bounds=thread['stack_bounds']
                    if not bounds['limit']<=rsp<bounds['base'] or len(stack)>bounds['base']-rsp:
                        raise ValueError('Captured stack outside admitted thread bounds')
                    try:result=replay.walk(context,rsp,stack)
                    except ValueError as error:result=dict(frames=[],reason=str(error),missing_reads=0)
                    verified_path=True
                    for frame in result['frames']:
                        owner=next((m for m in modules if m['base']<=frame['ip']<m['base']+m['size']),None)
                        frame['module']=Path(owner['path']).name if owner else None
                        frame['rva']=frame['ip']-owner['base'] if owner else None
                        if not owner or owner['identity_scope']!='capture-bound EXE':verified_path=False
                        frame['unwind_path_capture_verified']=verified_path
                    tid=thread['tid'];counts[tid]+=1;reasons[tid][result['reason']]+=1
                    for name in set(f['symbol'] for f in result['frames'] if f['module']==exe.name and f['symbol']):inclusive[tid][name]+=1
                    walks.append(dict(cycle=row['cycle'],tid=tid,context_sha256=by_kind['.win64-context']['sha256'],stack_sha256=by_kind['.stack']['sha256'],**result))
            loaded=replay.module_identity(chosen[0]['base'])
            if loaded['symbol_type']!=3 or sha(loaded['pdb'])!=args.pdb_sha or {key:loaded[key]for key in ['guid','age']}!=codeview_identity(exe):
                raise ValueError('Actually loaded PDB hash/GUID/age mismatch')
        finally:replay.close()
    report=dict(identity=dict(exe=str(exe),exe_sha256=args.exe_sha,pdb_sha256=args.pdb_sha,owner=header['owner']),
                loaded_pdb=loaded,modules=modules,unavailable_modules=unavailable,saved_walks_by_thread=dict(counts),
                reasons_by_thread={tid:dict(value)for tid,value in reasons.items()},
                inclusive_exe_callers={tid:value.most_common() for tid,value in inclusive.items()},walks=walks,
                qualification='Physical stack replay of selected every-fifth-cycle later suspending observations. Not CPU-event weights, exclusive CPU fractions, missing inline/tail callers, causal frame costs or FPS. EXE/PDB and blobs are capture-bound. Current DLL sizes/hashes cannot prove historical DLL identity; paths traversing them are marked unverified. All incomplete/missing-memory walks remain explicit.')
    (out/'native-stack-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(walks=dict(counts),reasons=report['reasons_by_thread'],unavailable_modules=len(unavailable))))
if __name__=='__main__':main()
