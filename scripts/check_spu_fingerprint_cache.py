"""Execute the production fingerprint wrapper and exact snapshot cache."""
import argparse,os,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'vendor/ps3recomp/runtime/spu'
def function(text,name):
    import re
    match=re.search(r'(?:static )?uint64_t '+name+r'\([^;]+?\)\s*\{',text)
    assert match,name
    depth=1;end=match.end()
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[match.start():end]
def oracle(data):
    value=1469598103934665603  # Preserve the runtime's existing offset basis.
    for byte in data:value=((value^byte)*1099511628211)&((1<<64)-1)
    return value
SOURCE=r'''
#include <stdint.h>
#include <stdlib.h>
#include <assert.h>
#include <string.h>
#include <stddef.h>
#ifdef _MSC_VER
#define TEST_TLS __declspec(thread)
#else
#define TEST_TLS _Thread_local
#endif
static TEST_TLS unsigned allocations,frees,fail_alloc,raw_calls;
typedef struct{unsigned calls,allocs,freed;} worker_result;
static TEST_TLS worker_result* active_result;
/* Keep observer ownership with the allocation: C TLS may already have been
 * torn down when pthread key destructors run (notably on macOS). */
typedef union { max_align_t alignment; worker_result* owner; } allocation_header;
static void* allocate(size_t n){
    if(fail_alloc)return NULL;
    allocation_header*h=malloc(sizeof(*h)+n);
    if(!h)return NULL;
    h->owner=active_result;allocations++;return h+1;
}
static void release(void*p){
    if(!p)return;
    allocation_header*h=(allocation_header*)p-1;
    frees++;if(h->owner)h->owner->freed++;free(h);
}
#define SPU_FP_ALLOC allocate
#define SPU_FP_FREE release
#include "spu_fingerprint_cache.h"
@RAW@
@WRAPPER@
static void fill(unsigned char*p,size_t n){for(size_t i=0;i<n;i++)p[i]=(unsigned char)(i*37+19);}
#ifdef _WIN32
static DWORD WINAPI worker(void*arg){
#else
static void* worker(void*arg){
#endif
    worker_result*r=(worker_result*)arg;unsigned char bytes[4096];fill(bytes,sizeof(bytes));
    active_result=r;
    for(unsigned i=0;i<100;i++)assert(spu_workload_fingerprint(bytes,sizeof(bytes))==@SMALL@ULL);
    r->calls=raw_calls;
    /* Exercise the OS thread-exit destructor, not just manual cleanup.
     * Store final allocation counters through a small destructor observer. */
    r->allocs=allocations;r->freed=frees;
    return 0;
}
int main(int argc,char**argv){assert(argc==2);int enabled=!strcmp(argv[1],"on");
    unsigned char*p=malloc(SPU_FP_MAX_BUFFER+1);assert(p);fill(p,SPU_FP_MAX_BUFFER+1);
    for(unsigned i=0;i<100;i++)assert(spu_workload_fingerprint(p,4096)==@SMALL@ULL);
    assert(raw_calls==(enabled?1u:100u));
    if(!enabled){assert(!allocations);free(p);puts("PASS default disabled: no snapshot allocation");return 0;}
    spu_fp_cache*c=spu_fp_thread_get();assert(c&&c->hits==99&&c->misses==1);
    spu_fp_thread_release();assert(allocations==frees);
    fail_alloc=1;assert(spu_workload_fingerprint(p,4096)==@SMALL@ULL);fail_alloc=0;
    assert(allocations==frees);
    spu_fp_cache core={0};
    assert(spu_fp_compute(&core,p,SPU_FP_MAX_BUFFER,spu_workload_fingerprint_raw)==@LARGE@ULL);
    assert(spu_fp_compute(&core,p,SPU_FP_MAX_BUFFER,spu_workload_fingerprint_raw)==@LARGE@ULL);
    const size_t positions[]={0,15,16,63,64,131072,262143};
    const uint64_t changed[]={@MUTATIONS@};
    for(unsigned i=0;i<sizeof(positions)/sizeof(positions[0]);i++){
        p[positions[i]]^=0xa5;
        assert(spu_fp_compute(&core,p,SPU_FP_MAX_BUFFER,spu_workload_fingerprint_raw)==changed[i]);
        assert(spu_fp_compute(&core,p,SPU_FP_MAX_BUFFER,spu_workload_fingerprint_raw)==changed[i]);
        p[positions[i]]^=0xa5;
        assert(spu_fp_compute(&core,p,SPU_FP_MAX_BUFFER,spu_workload_fingerprint_raw)==@LARGE@ULL);
    }
    /* Overlapping views and identical addresses with different lengths must
     * each validate their own full byte range after a shared-byte mutation. */
    const uint64_t alias_hashes[]={@ALIASES@};
    for(unsigned changed=0;changed<2;changed++){
        if(changed)p[4095]^=0xa5;
        for(unsigned repeat=0;repeat<2;repeat++){
            assert(spu_fp_compute(&core,p,4096,spu_workload_fingerprint_raw)==alias_hashes[changed*3]);
            assert(spu_fp_compute(&core,p,8192,spu_workload_fingerprint_raw)==alias_hashes[changed*3+1]);
            assert(spu_fp_compute(&core,p+16,4096,spu_workload_fingerprint_raw)==alias_hashes[changed*3+2]);
        }
    }
    p[4095]^=0xa5;
    assert(spu_fp_compute(&core,NULL,0,spu_workload_fingerprint_raw)==1469598103934665603ULL);
    assert(spu_fp_compute(&core,p,SPU_FP_MAX_BUFFER+1,spu_workload_fingerprint_raw)==@OVERSIZED@ULL);
    spu_fp_clear(&core);assert(!core.retained_bytes);
    fail_alloc=1;assert(spu_fp_compute(&core,p,4096,spu_workload_fingerprint_raw)==@SMALL@ULL);
    assert(core.allocation_failures==1&&!core.retained_bytes);fail_alloc=0;
    unsigned char*many=malloc(40u*SPU_FP_MAX_BUFFER);assert(many);
    for(unsigned i=0;i<40;i++){
        unsigned char*q=many+i*SPU_FP_MAX_BUFFER;fill(q,SPU_FP_MAX_BUFFER);
        assert(spu_fp_compute(&core,q,SPU_FP_MAX_BUFFER,spu_workload_fingerprint_raw)==@LARGE@ULL);
        assert(core.retained_bytes<=SPU_FP_MAX_BYTES);
    }
    assert(core.evictions>0);
    assert(spu_fp_compute(&core,many,SPU_FP_MAX_BUFFER,spu_workload_fingerprint_raw)==@LARGE@ULL);
    spu_fp_clear(&core);free(many);free(p);assert(allocations==frees);
    worker_result results[4]={{0}};
#ifdef _WIN32
    HANDLE threads[4];for(unsigned i=0;i<4;i++){threads[i]=CreateThread(NULL,0,worker,results+i,0,NULL);assert(threads[i]);}
    for(unsigned i=0;i<4;i++){assert(WaitForSingleObject(threads[i],INFINITE)==WAIT_OBJECT_0);CloseHandle(threads[i]);}
#else
    pthread_t threads[4];for(unsigned i=0;i<4;i++)assert(!pthread_create(threads+i,NULL,worker,results+i));
    for(unsigned i=0;i<4;i++)assert(!pthread_join(threads[i],NULL));
#endif
    for(unsigned i=0;i<4;i++){assert(results[i].calls==1);assert(results[i].allocs==results[i].freed);}
    puts("PASS exact fingerprints, all-byte changes, bounds, failure, eviction and independent worker caches");return 0;
}
'''
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--production-source',type=Path,default=RUNTIME/'spu_workload.c');args=parser.parse_args()
    text=args.production_source.read_text()
    wrapper=function(text,'spu_workload_fingerprint')
    if 'spu_workload_fingerprint_raw' in text:
        raw=function(text,'spu_workload_fingerprint_raw')
        raw=raw.replace('{','{ raw_calls++;',1)
    else:
        raw=wrapper.replace('spu_workload_fingerprint(','spu_workload_fingerprint_raw(',1).replace('{','{ raw_calls++;',1)
        wrapper=wrapper.replace('{','{ raw_calls++;',1)
    data=bytearray((i*37+19)&255 for i in range(262145))
    mutated=[]
    for position in (0,15,16,63,64,131072,262143):
        data[position]^=0xa5;mutated.append(str(oracle(data[:262144]))+'ULL');data[position]^=0xa5
    aliases=[]
    for changed in (False,True):
        if changed:data[4095]^=0xa5
        aliases.extend(str(oracle(view))+'ULL' for view in (data[:4096],data[:8192],data[16:4112]))
    data[4095]^=0xa5
    source=SOURCE.replace('@RAW@',raw).replace('@WRAPPER@',wrapper).replace('@SMALL@',str(oracle(data[:4096]))).replace('@LARGE@',str(oracle(data[:262144]))).replace('@OVERSIZED@',str(oracle(data))).replace('@MUTATIONS@',','.join(mutated)).replace('@ALIASES@',','.join(aliases))
    compiler=os.environ.get('MV_CLANG') or os.environ.get('CC') or shutil.which('clang-cl' if os.name=='nt' else 'cc')
    assert compiler,'C compiler required'
    with tempfile.TemporaryDirectory() as temporary:
        directory=Path(temporary);(directory/'test.c').write_text(source)
        exe=directory/('test.exe' if os.name=='nt' else 'test')
        if os.name=='nt':command=[compiler,'/nologo','/TC','/O2','/UNDEBUG','/D_CRT_SECURE_NO_WARNINGS','/I'+str(RUNTIME),'test.c','/Fe:'+str(exe)]
        else:command=[compiler,'-std=c11','-O2','-UNDEBUG','-Wall','-Wextra','-Werror','-pthread','-I'+str(RUNTIME),'test.c','-o',str(exe)]
        subprocess.run(command,cwd=directory,check=True)
        for mode in ('off','on'):
            env=dict(os.environ,SPU_FINGERPRINT_CACHE='1' if mode=='on' else '0',SPU_FINGERPRINT_STATS='0')
            subprocess.run([str(exe),mode],env=env,check=True,timeout=60)
if __name__=='__main__':
    if os.name=='nt':
        from project import build_environment
        os.environ.update(build_environment())
    main()
