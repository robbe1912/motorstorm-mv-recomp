#!/usr/bin/env python3
"""Compile the actual policy-entry r4 stores against the SPURS scalar-u64 ABI."""
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 source=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'vendor/ps3recomp/runtime/spu/spurs_policy.c'
 text=source.read_text();start=text.index('int spu_run_policy_module(');end=text.find('\nint ',start+1);body=text[start:end if end>=0 else len(text)]
 stores=re.findall(r'ctx->gpr\[4\]\._u32\[[0-3]\]\s*=\s*[^;]+;',body)[:4]
 assert len(stores)==4 and all(f'_u32[{i}]' in stores[i] for i in range(4)), 'Policy entry r4 stores changed; update extraction admission'
 out=ROOT/'temp/checks'/('policy-u64-'+str(time.time_ns()));out.mkdir(parents=True)
 code='''#include <stdint.h>
#include <stdio.h>
typedef struct {uint32_t _u32[4];} reg;
typedef struct {reg gpr[128];} context;
static void production_entry(context*ctx,uint64_t wkl_data){STORES}
int main(void){const uint64_t cases[]={0,0x12345600ull,0x8765432100000000ull,0x123456789abcdef0ull,UINT64_MAX};int failures=0;
for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++){context c={0};production_entry(&c,cases[i]);uint32_t high=(uint32_t)(cases[i]>>32),low=(uint32_t)cases[i];
if(c.gpr[4]._u32[0]!=high||c.gpr[4]._u32[1]!=low){fprintf(stderr,"case %u: preferred pair %08X:%08X expected %08X:%08X\\n",i,c.gpr[4]._u32[0],c.gpr[4]._u32[1],high,low);failures++;}}
printf("policy-u64 failures=%d\\n",failures);return failures?1:0;}
'''.replace('STORES','\n'.join(stores))
 c=out/'fixture.c';c.write_text(code);exe=out/('fixture.exe' if os.name=='nt' else 'fixture')
 from project import build_environment
 env=build_environment() if os.name=='nt' else os.environ.copy()
 cmd=([env.get('MV_CLANG','clang-cl'),'/nologo','/TC','/O1',str(c),'/Fo'+str(out/'fixture.obj'),'/Fe'+str(exe)] if os.name=='nt' else [os.environ.get('CC','cc'),'-std=c11','-O2',str(c),'-o',str(exe)])
 build=subprocess.run(cmd,capture_output=True,text=True,env=env);(out/'build.log').write_text(build.stdout+build.stderr);assert build.returncode==0,build.stdout+build.stderr
 run=subprocess.run([str(exe)],capture_output=True,text=True);(out/'run.log').write_text(run.stdout+run.stderr)
 (out/'result.json').write_text(json.dumps({'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'extracted_actual_stores':stores,'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'returncode':run.returncode,'scope':'Actual policy-entry register stores; authored scalar-u64 ABI cases; no game inputs'},indent=2));print(run.stdout+run.stderr,end='');print(out);return run.returncode
if __name__=='__main__':raise SystemExit(main())
