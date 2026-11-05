"""Exercise extracted production texture lookup; no GPU/lifetime or FPS claim."""
import argparse, hashlib, json, os, shutil, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/"vendor/ps3recomp"
if os.name=="nt":
    from project import build_environment
    os.environ.update(build_environment())

def fixture(source):
    a=source.index('int slot = -1, freeslot = -1;')
    b=source.index('/* TEX_OFF_BIAS',a)
    helper=''
    if 'static int texture_retention_on(void)' in source:
        start=source.index('static int texture_retention_on(void)\n{')
        end=source.index('{',start);depth=1;end+=1
        while depth:
            depth+=(source[end]=='{')-(source[end]=='}');end+=1
        helper=source[start:end]
    return r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rsx_texture_profile.h"
typedef uint32_t u32; typedef uint64_t u64; typedef uint8_t u8;
typedef struct {void*res;u32 off,key,w,h,fmt,mips;u64 csum;int cube,used;u64 last_use;} VPTexSlot;
static struct {VPTexSlot vp_tex[3];unsigned vp_tex_capacity;u64 vp_tex_use_serial;} s_d3d;
static u8 bytes[1024],*vm_base=bytes;
#define TEX_CSUM(base,size) ((u32)*(base))
"""+helper+r"""
static int pick(u32 key_off,int cube,u32 mips) {
    u32 w=8,h=8,fmt=0x85,bpp=4,blkrow=0,blkrows=0;int dxt=0;
    rsx_texture_profile_call*profile=NULL;
"""+source[a:b]+r"""
    return slot>=0?slot:freeslot;
}
static void reset(void) {
    memset(&s_d3d,0,sizeof s_d3d);memset(bytes,23,sizeof bytes);
    s_d3d.vp_tex_capacity=3;s_d3d.vp_tex_use_serial=20;
    for(int i=0;i<2;i++) s_d3d.vp_tex[i]=(VPTexSlot){
        .res=(void*)(uintptr_t)1,.off=256u+256u*i,.key=256u+256u*i,
        .w=8,.h=8,.fmt=0x85,.csum=23,.mips=1,.last_use=19u-i};
}
static void fill(void) {
    reset();s_d3d.vp_tex[2]=s_d3d.vp_tex[1];s_d3d.vp_tex[2].off=768;
    s_d3d.vp_tex[2].key=768;s_d3d.vp_tex[0].last_use=3;
    s_d3d.vp_tex[1].last_use=2;s_d3d.vp_tex[2].last_use=1;
}
#define CHECK(x) do{if(!(x)){fprintf(stderr,"lookup contract failed line %d: %s\n",__LINE__,#x);return 3;}}while(0)
int main(int argc,char**argv) {
    int native=argc>1&&!strcmp(argv[1],"native");
    reset();CHECK(pick(768,0,1)==(native?2:0));
    reset();CHECK(pick(256,0,1)==0);CHECK(s_d3d.vp_tex[0].used==1);
    CHECK(pick(512,0,1)==1);CHECK(pick(768,0,1)==2);
    reset();s_d3d.vp_tex[0].used=s_d3d.vp_tex[1].used=s_d3d.vp_tex[2].used=1;
    CHECK(pick(900,0,1)==-1); /* caller must grow/retire, never overwrite a pin */
    reset();bytes[256]=24;CHECK(pick(256,0,1)==0);CHECK(s_d3d.vp_tex[0].used==0);
    if(!native){puts("PASS reference metadata controls");return 0;}
    fill();CHECK(pick(900,0,1)==2);
    fill();s_d3d.vp_tex[2].used=1;CHECK(pick(900,0,1)==1);
    fill();CHECK(pick(768,0,1)==2);s_d3d.vp_tex[2].used=0;
    CHECK(pick(900,0,1)==1); /* a real hit must refresh recency */
    fill();s_d3d.vp_tex_use_serial=UINT64_MAX;
    s_d3d.vp_tex[0].last_use=UINT64_MAX-2;s_d3d.vp_tex[1].last_use=UINT64_MAX-1;
    s_d3d.vp_tex[2].last_use=UINT64_MAX;CHECK(pick(900,0,1)==0);
    reset();s_d3d.vp_tex[0].cube=1;s_d3d.vp_tex[0].used=1;
    CHECK(pick(256,1,2)==2); /* changed cube stride gets distinct storage */
    puts("PASS native empty/LRU/recency/wrap/pin/metadata/source controls");return 0;
}
"""

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--historical-backend',type=Path);args=ap.parse_args()
    backend=VENDOR/'libs/video/rsx_d3d12_backend.c';source=backend.read_text()
    output=ROOT/'temp/checks'/f'texture-retention-{time.time_ns()}';output.mkdir(parents=True)
    result={'qualification':'Actual extracted production lookup with authored metadata and checksum inputs; no COM objects, fences, GPU pixels, residency budget or performance proof.','source_sha256':hashlib.sha256(backend.read_bytes()).hexdigest(),'commands':[]}
    compiler=os.environ.get('MV_CLANG') or shutil.which('clang-cl' if os.name=='nt' else 'clang') or shutil.which('cc')
    assert compiler,'Set MV_CLANG and prepare the compiler environment'
    env=dict(os.environ)
    for k in list(env):
        if k.startswith(('TEX_','RSX_')):env.pop(k)
    def command(cmd,tag,environment=env):
        p=subprocess.run(cmd,cwd=ROOT,env=environment,capture_output=True,text=True,timeout=45)
        result['commands'].append(dict(tag=tag,command=list(map(str,cmd)),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
        (output/'result.json').write_text(json.dumps(result,indent=2));return p
    def build(text,tag):
        c=output/(tag+'.c');c.write_text(fixture(text));exe=output/(tag+('.exe' if os.name=='nt' else ''))
        if os.name=='nt':cmd=[compiler,'/nologo','/TC','/std:c17','/O2','/UNDEBUG','/MDd','/I'+str(VENDOR/'libs/video'),str(c),'/Fo'+str(output/(tag+'.obj')),'/Fe'+str(exe)]
        else:cmd=[compiler,'-std=c17','-O2','-UNDEBUG','-I'+str(VENDOR/'libs/video'),str(c),'-o',str(exe)]
        assert command(cmd,tag+'-compile').returncode==0,f'Compilation failed: {output}/result.json'
        return exe
    exe=build(source,'production')
    for flag,label in [('0','reference'),('1','native')]:
        assert command([str(exe),label],label,dict(env,RSX_TEXTURE_RETENTION=flag)).returncode==0,f'{label}: {output}/result.json'
    mutants={
      'first-unused':source.replace('if (retention) freeslot = empty >= 0 ? empty : oldest;','/* historical first-unused selection */'),
      'pinned-eviction':source.replace('if (retention && !c->used)', 'if (retention)'),
      'no-hit-recency':source.replace('if (retention) c->last_use = serial;', ''),
      'cube-stride-ignored':source.replace(' && (!retention || c->mips == mips)', ''),
    }
    for name,text in mutants.items():
        assert text!=source;mutant=build(text,name)
        assert command([str(mutant),'native'],name,dict(env,RSX_TEXTURE_RETENTION='1')).returncode==3,f'Mutant survived: {name}'
    if args.historical_backend:
        historical=build(args.historical_backend.read_text(),'historical')
        assert command([str(historical),'native'],'historical-red',dict(env,RSX_TEXTURE_RETENTION='1')).returncode==3,'Historical lookup unexpectedly satisfies new contract'
        result['historical_sha256']=hashlib.sha256(args.historical_backend.read_bytes()).hexdigest()
    result['passed']=True;(output/'result.json').write_text(json.dumps(result,indent=2))
    print('PASS: production reference/native metadata trace; four mutants rejected; historical RED' if args.historical_backend else 'PASS: production reference/native metadata trace; four mutants rejected')
    print(output/'result.json')
if __name__=='__main__':main()
