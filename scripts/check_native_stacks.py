#!/usr/bin/env python3
"""Validate actual optimized native unwinding and missing-memory rejection."""
from pathlib import Path
import argparse,json,struct,subprocess,sys
from native_stack_replay import ROOT, Replay, compile_reader, sha, codeview_identity
from analyze_native_stacks import checked_blob

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mutants',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'build/self-tests/native-stacks')
    args=parser.parse_args();out=args.output.resolve();library=compile_reader(out,chain=True)
    subprocess.run([str(out/'native_stack_chain.exe'),str(out)],check=True,timeout=15)
    base,size,rsp,count,ip=map(int,(out/'meta.txt').read_text().split())
    context=(out/'context.bin').read_bytes();stack=(out/'stack.bin').read_bytes()
    assert len(context)==1232 and len(stack)==count and struct.unpack_from('<Q',context,0xf8)[0]==ip
    replay=Replay(library,[dict(base=base,size=size,path=out/'native_stack_chain.exe')],out)
    try:
        positive=replay.walk(context,rsp,stack)
        names=[f['symbol']for f in positive['frames']]
        expected=['profile_leaf','profile_middle','profile_top','main']
        assert names[:4]==expected,(names,positive)
        identity=replay.module_identity(base)
        assert identity['symbol_type']==3 and sha(identity['pdb'])==sha(out/'native_stack_chain.pdb')
        assert {key:identity[key]for key in ['guid','age']}==codeview_identity(out/'native_stack_chain.exe')
        assert all(f['symbol_type']==3 for f in positive['frames'][:4]),'Expected exact PDB-backed names'
        truncated=replay.walk(context,rsp,stack[:8]);assert truncated['missing_reads']>0 and len(truncated['frames'])<4,truncated
        invalid=bytearray(context);struct.pack_into('<Q',invalid,0xf8,0)
        try:replay.walk(bytes(invalid),rsp,stack)
        except ValueError:pass
        else:raise AssertionError('Unmapped context accepted')
        try:replay.walk(context,rsp+8,stack)
        except ValueError:pass
        else:raise AssertionError('Mismatched stack base accepted')
    finally:replay.close()
    wrong=Replay(library,[dict(base=base+0x100000000,size=size,path=out/'native_stack_chain.exe')],out)
    try:
        try:wrong.walk(context,rsp,stack)
        except ValueError:pass
        else:raise AssertionError('Wrong module base accepted')
    finally:wrong.close()
    for metadata in [dict(path='context.bin',bytes=len(context),sha256='0'*64),
                     dict(path='../outside.blob',bytes=0,sha256='0'*64)]:
        try:checked_blob(out,metadata)
        except ValueError:pass
        else:raise AssertionError('Corrupt/escaping archived blob accepted')
    for bad_exe,bad_pdb in [('0'*64,sha(out/'native_stack_chain.pdb')),(sha(out/'native_stack_chain.exe'),'0'*64)]:
        command=[sys.executable,str(ROOT/'scripts/analyze_native_stacks.py'),'--packet',str(out),
                 '--exe',str(out/'native_stack_chain.exe'),'--exe-sha',bad_exe,'--pdb-sha',bad_pdb,
                 '--output',str(out.parent/'rejected-native-stack-input')]
        rejected=subprocess.run(command,capture_output=True,text=True,timeout=15)
        assert rejected.returncode and 'EXE/PDB admission mismatch' in rejected.stderr,rejected.stderr
    if args.mutants:
        mutant=out/'missing-runtime-functions';mutant.mkdir(exist_ok=True)
        source=(ROOT/'scripts/fixtures/native_stack_reader.c').read_text(encoding='utf-8')
        assert source.count('else return f;')==1
        path=mutant/'reader.c';path.write_text(source.replace('else return f;','else return NULL;'),encoding='utf-8')
        broken_library=compile_reader(mutant,reader_source=path)
        broken=Replay(broken_library,[dict(base=base,size=size,path=out/'native_stack_chain.exe')],out)
        try:
            result=broken.walk(context,rsp,stack)
            assert [f['symbol']for f in result['frames']][:4]!=expected,'Missing-metadata mutant retained authored callers'
            (mutant/'rejected.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        finally:broken.close()
        print('PASS compiled missing-unwind-metadata mutant loses intended authored callers')
    (out/'results.json').write_text(json.dumps(dict(positive=positive,truncated=truncated),indent=2),encoding='utf-8')
    print('PASS actual optimized leaf/middle/top/main unwind; truncated memory and invalid context/base controls')
if __name__=='__main__':main()
