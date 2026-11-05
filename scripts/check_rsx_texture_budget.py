"""Actual cache budget helpers + checked retirement, using authored CPU objects.
Does not validate real D3D12 allocations, fence progress, pixels or performance.
"""
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/"vendor/ps3recomp"
if os.name=="nt":
    from project import build_environment
    os.environ.update(build_environment())
def function(text,name,returns="void"):
    start=text.index('static '+returns+' '+name+'(');end=text.index('{',start)+1;depth=1
    while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
def main():
    out=ROOT/'temp/checks'/f'texture-budget-{time.time_ns()}';out.mkdir(parents=True)
    backend=(VENDOR/'libs/video/rsx_d3d12_backend.c').read_text()
    # Both actual call sites unpin only after the checked descriptor/PSO gate.
    assert backend.count('    texture_retention_begin_batch();')==2
    assert backend.count('    gpu_pso_retire();\n    texture_retention_begin_batch();')==2
    gate=function(backend,'gpu_pso_retire')
    header=VENDOR/'libs/video/rsx_d3d12_texture_residency.h';text=header.read_text()
    source=r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <crtdbg.h>
#endif
typedef uint64_t u64;typedef uint32_t u32;typedef int HRESULT;
#define S_OK 0
static u64 completed=1;static int removed;
typedef struct Device Device;typedef struct Fence Fence;
typedef struct{HRESULT(*GetDeviceRemovedReason)(Device*);}DeviceOps;
typedef struct{u64(*GetCompletedValue)(Fence*);}FenceOps;
struct Device{DeviceOps*lpVtbl;};struct Fence{FenceOps*lpVtbl;};
static HRESULT removed_reason(Device*d){(void)d;return removed;}
static u64 completion(Fence*f){(void)f;return completed;}
static DeviceOps device_ops={removed_reason};static FenceOps fence_ops={completion};
static Device device={&device_ops};static Fence fence={&fence_ops};
static int retired,allow_retire=1,resource_releases,pso_releases,retire_calls,wait_ok=1;
typedef struct Resource Resource;
typedef struct {unsigned(*Release)(Resource*);} ResourceOps;
struct Resource {ResourceOps*lpVtbl;};
static unsigned release(Resource*r){(void)r;if(!retired){fprintf(stderr,"UNRETIRED RELEASE\n");abort();}++resource_releases;return 0;}
static ResourceOps resource_ops={release};static Resource resources[6];
typedef struct{Resource*res,*up;u64 allocation_bytes,last_use;int used;}VPTexSlot;
static struct{Device*device;Fence*fence;unsigned frame_index;u64 fence_values[1];VPTexSlot vp_tex[3];unsigned vp_tex_capacity;u64 vp_tex_use_serial,vp_tex_bytes,vp_tex_peak_over_budget,vp_tex_evictions,vp_tex_resource_failures;}s_d3d;
static int texture_retention_on(void){return 1;}
#include "rsx_gpu_references.h"
static rsx_gpu_references refs;
static void retain(void*c,void*p){(void)c;(void)p;}
static void release_pso(void*c,void*p){(void)c;(void)p;++pso_releases;fprintf(stderr,"PSO RELEASE\n");}
static int wait_for_gpu(void){++retire_calls;return wait_ok;}
"""+function(backend,'vp_upload_retire','int')+r"""
static int retire(void*c){int ok=vp_upload_retire(c);if(ok)retired=1;return ok;}
static const rsx_gpu_reference_ops ops={NULL,retain,release_pso,retire};
#define s_gpu_pso_refs refs
#define s_gpu_pso_ops ops
"""+gate+r"""
#include "BUDGET_HEADER"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"budget contract failed line %d: %s\n",__LINE__,#x);return 3;}}while(0)
static void setup(void){
    memset(&s_d3d,0,sizeof s_d3d);memset(&refs,0,sizeof refs);
    resource_releases=pso_releases=retire_calls=retired=0;allow_retire=1;
    completed=1;removed=0;s_d3d.device=&device;s_d3d.fence=&fence;s_d3d.fence_values[0]=1;
    s_d3d.vp_tex_capacity=3;s_d3d.vp_tex_use_serial=20;s_d3d.vp_tex_bytes=3*1024*1024;
    for(int i=0;i<6;++i)resources[i].lpVtbl=&resource_ops;
    for(int i=0;i<3;++i)s_d3d.vp_tex[i]=(VPTexSlot){&resources[2*i],&resources[2*i+1],1024*1024,3u-i,1};
    rsx_gpu_reference_hold(&refs,&resources[0],&ops);
}
int main(int argc,char**argv){
#ifdef _WIN32
    _set_error_mode(_OUT_TO_STDERR);_set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
#endif
    if(argc>1&&!strcmp(argv[1],"budget")){printf("BUDGET=%llu\n",(unsigned long long)texture_retention_budget());return 0;}
    setup();
    if(argc>1&&!strcmp(argv[1],"blocked")){
        completed=0;gpu_pso_retire();texture_retention_begin_batch();return 4;
    }
    CHECK(texture_retention_budget()==1024*1024);
    wait_ok=0;CHECK(!rsx_gpu_reference_retire(&refs,&ops)&&refs.count==1&&!pso_releases);wait_ok=1;
    removed=-1;CHECK(!rsx_gpu_reference_retire(&refs,&ops)&&refs.count==1&&!pso_releases);
    removed=0;completed=UINT64_MAX;CHECK(!rsx_gpu_reference_retire(&refs,&ops)&&refs.count==1&&!pso_releases);
    completed=0;CHECK(!rsx_gpu_reference_retire(&refs,&ops)&&refs.count==1&&!pso_releases);
    setup();
    gpu_pso_retire();CHECK(retire_calls==1&&pso_releases==1&&resource_releases==0);
    texture_retention_trim();CHECK(resource_releases==0&&s_d3d.vp_tex_bytes==3*1024*1024);
    CHECK(texture_pinned_bytes()==3*1024*1024&&s_d3d.vp_tex_peak_over_budget==2*1024*1024);
    s_d3d.vp_tex[1].used=0;texture_retention_trim();CHECK(resource_releases==2);
    CHECK(!s_d3d.vp_tex[1].res&&!s_d3d.vp_tex[1].up&&s_d3d.vp_tex_evictions==1);
    CHECK(s_d3d.vp_tex_bytes==2*1024*1024&&texture_pinned_bytes()==2*1024*1024);
    setup();gpu_pso_retire();texture_retention_begin_batch();
    CHECK(retire_calls==1&&resource_releases==4&&s_d3d.vp_tex_bytes==1024*1024);
    CHECK(s_d3d.vp_tex[0].res&&!s_d3d.vp_tex[1].res&&!s_d3d.vp_tex[2].res);
    CHECK(!texture_pinned_bytes());texture_slot_release(&s_d3d.vp_tex[0]);
    CHECK(!s_d3d.vp_tex_bytes&&resource_releases==6);
    puts("PASS bytes/LRU/pins/overage/checked retirement/release accounting");return 0;
}
"""
    result={'qualification':__doc__,'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [header,VENDOR/'libs/video/rsx_gpu_references.h',VENDOR/'libs/video/rsx_d3d12_backend.c']},'commands':[]}
    compiler=os.environ.get('MV_CLANG') or shutil.which('clang-cl' if os.name=='nt' else 'clang') or shutil.which('cc');assert compiler
    env=dict(os.environ)
    for k in list(env):
        if k.startswith(('TEX_','RSX_')):env.pop(k)
    def run(cmd,tag,configuration=None):
        e=dict(env)
        if configuration is not None:e['RSX_TEXTURE_CACHE_MIB']=configuration
        p=subprocess.run(list(map(str,cmd)),cwd=ROOT,env=e,capture_output=True,text=True,timeout=45)
        result['commands'].append(dict(tag=tag,command=list(map(str,cmd)),budget=configuration,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));(out/'result.json').write_text(json.dumps(result,indent=2));return p
    def build(content,tag):
        h=out/(tag+'.h');h.write_text(content);c=out/(tag+'.c');c.write_text(source.replace('BUDGET_HEADER',h.as_posix()))
        exe=out/(tag+('.exe' if os.name=='nt' else ''))
        if os.name=='nt':cmd=[compiler,'/nologo','/TC','/std:c17','/O2','/UNDEBUG','/MDd','/I'+str(VENDOR/'libs/video'),str(c),'/Fo'+str(out/(tag+'.obj')),'/Fe'+str(exe)]
        else:cmd=[compiler,'-std=c17','-O2','-UNDEBUG','-I'+str(VENDOR/'libs/video'),str(c),'-o',str(exe)]
        assert run(cmd,tag+'-compile').returncode==0,f'Compilation failed: {out}/result.json'
        return exe
    exe=build(text,'production');assert run([exe],'production','1').returncode==0,f'{out}/result.json'
    blocked=run([exe,'blocked'],'blocked','1')
    assert blocked.returncode!=0 and 'GPU retirement failed' in blocked.stderr and 'RELEASE' not in blocked.stderr
    for value,expected in [(None,512),('0',0),('1',1),('4096',4096)]:
        p=run([exe,'budget'],'budget-valid',value);assert p.returncode==0 and p.stdout.strip()==f'BUDGET={expected*1024*1024}'
    for value in ['', '-1','+1','1.5','nan','inf','4097','999999999999999999999999999999999999']:
        p=run([exe,'budget'],'budget-invalid',value);assert p.returncode!=0 and 'invalid RSX_TEXTURE_CACHE_MIB' in p.stderr
    mutants={'drop-accounting':text.replace('s_d3d.vp_tex_bytes -= t->allocation_bytes;','/* byte accounting omitted */'),
        'ignore-pins':text.replace('if (!t->used && t->allocation_bytes)','if (t->allocation_bytes)'),
        'leak-upload':text.replace('if (t->up) t->up->lpVtbl->Release(t->up);','/* upload leaked */'),
        'wrong-lru':text.replace('victim < 0 || age > oldest_age','victim < 0')}
    for name,content in mutants.items():
        assert content!=text;mutant=build(content,name)
        assert run([mutant],name,'1').returncode!=0,'Budget mutant survived: '+name
    result['passed']=True;(out/'result.json').write_text(json.dumps(result,indent=2));print('PASS: actual budget/retirement helpers; finite bounds; four mutants rejected');print(out/'result.json')
if __name__=='__main__':main()
