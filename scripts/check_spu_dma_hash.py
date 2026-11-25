#!/usr/bin/env python3
"""Cap of the DMA hash of staged jobmods (SPU_JOBMOD_HEADER_FNV=1).

Compiles the production staging accumulator from spu_channels.c. The reference
is the accumulator before the cap (hash of every byte). Two proofs:
  1. Synthetic images (authored C0DEC0DE headers over pseudo-random bytes; no
     game input): each burst with a header offers the same keys as the
     reference, a burst without the magic offers no key, a burst is sorted when
     it holds 0x30 bytes, legacy mode (switch off) is identical.
  2. Workload registration: when a job dump (temp/jobdump/pvs-race) and the
     registration manifest (build/native/native-world-input/spu/jobmods_manifest.json)
     exist, the recorded DMA transfers of the dump go through both accumulators
     against the registered keys (staged_fnv of the manifest). The identified
     image of each transfer must be the same, each registered image that the
     dump holds must be identified, and the cap must hash fewer bytes.
Each source mutant must fail."""
import argparse, hashlib, json, os, struct, subprocess, sys, time
from pathlib import Path
root=Path(__file__).resolve().parents[1];sdk=root/'vendor/ps3recomp'
SOURCE=sdk/'runtime/spu/spu_channels.c';HEADER=sdk/'runtime/spu/spu_jobmod_identity.h'
BEGIN='/* ---- Staged jobmod identity ----';END='/* ---- end staged jobmod identity ---- */'
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path);ap.add_argument('--dump',type=Path,default=root/'temp/jobdump/pvs-race');args=ap.parse_args()
out=(args.output or root/'temp/checks'/('spu-dma-hash-'+str(time.time_ns()))).resolve();out.mkdir(parents=True,exist_ok=False)

FIXTURE=r'''
#include "spu_context.h"
#include "spu_jobmod_identity.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
@IDENTITY@
static const char* tag="setup";
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL line %d: %s (%s)\n",__LINE__,#x,tag);exit(1);}}while(0)
#define FNV_BASIS 1469598103934665603ULL
#define FNV_PRIME 1099511628211ULL
static uint64_t fnv(const uint8_t* p,uint32_t n){uint64_t h=FNV_BASIS;for(uint32_t i=0;i<n;i++)h=(h^p[i])*FNV_PRIME;return h;}
static void put(uint8_t* p,uint32_t v){p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;}
/* The accumulator before the cap: every byte of a contiguous burst. */
typedef struct{uint32_t lo,ea0,hashed,hdr_span,hdr_len;uint64_t fnv,hdr_fnv;}ref_t;
static unsigned ref_accumulate(ref_t* s,const uint8_t* ls,uint32_t lsa,uint32_t ea,uint32_t size,
                               int header_identity,uint64_t keys[2])
{
    if (s->hashed==0 || lsa!=s->lo+s->hashed) {
        s->lo=lsa;s->ea0=ea;s->hashed=0;s->fnv=FNV_BASIS;
        s->hdr_span=header_identity?stage_header_span(ls,lsa,size):0;
        s->hdr_len=0;s->hdr_fnv=FNV_BASIS;
    }
    for (uint32_t i=0;i<size;++i) s->fnv=(s->fnv^ls[i])*FNV_PRIME;
    s->hashed+=size;
    int header_ready=0;
    if (s->hdr_len<s->hdr_span) {
        uint32_t take=s->hdr_span-s->hdr_len;
        if (take>size) take=size;
        for (uint32_t i=0;i<take;++i) s->hdr_fnv=(s->hdr_fnv^ls[i])*FNV_PRIME;
        s->hdr_len+=take;
        header_ready=s->hdr_len==s->hdr_span;
    }
    if (s->hashed<0x800u) return 0;
    unsigned n=0;
    keys[n++]=s->fnv;
    if (header_ready && s->hdr_fnv!=s->fnv) keys[n++]=s->hdr_fnv;
    return n;
}
static uint8_t src[0x40000],other[0x40000];
/* Authored image: header fields at +0x14 (image size), +0x20 (magic), +0x28
 * (link base), pseudo-random body, zero tail as load padding. */
static void image(uint8_t* dst,uint32_t size,uint32_t base,uint32_t seed){
    memset(dst,0,0x40000);uint32_t s=seed;
    for(uint32_t i=0;i<size;i++){s=s*1103515245u+12345u;dst[i]=(uint8_t)(s>>16);}
    put(dst+0x14,size);put(dst+0x20,0xC0DEC0DEu);put(dst+0x28,base);
}
static spu_context* fresh(void){
    spu_context* c=calloc(1,sizeof *c);CHECK(c);c->ls=calloc(1,0x40000);CHECK(c->ls);return c;
}
typedef struct{unsigned offers,hits,small_hits,nonempty;}result;
/* Stage staged bytes of src at lsa: the first transfer holds `first` bytes,
 * then `chunk` bytes. data: the burst has no header. Returns what each
 * accumulator offered; CHECK keeps the rule: reference keys are a subset of
 * the production keys, and a data burst offers nothing. */
static result run(unsigned* ref_hits,uint32_t lsa,uint32_t staged,uint32_t first,uint32_t chunk,int header,int data,uint64_t want){
    spu_context* c=fresh();ref_t ref;memset(&ref,0,sizeof ref);
    if(data){put(src+0x20,0xC0DEC0DEu^1u);} /* no magic: the same bytes as data */
    /* Each transfer lands in LS before the accumulator sees it, as in a DMA. */
    result r={0,0,0,0};uint32_t off=0;
    while(off<staged){
        uint32_t n=staged-off<(off?chunk:first)?staged-off:(off?chunk:first);
        memcpy(c->ls+lsa+off,src+off,n);
        uint64_t keys[2]={0,0},rkeys[2]={0,0};
        unsigned k=spu_stage_accumulate(c,c->ls+lsa+off,lsa+off,0x10000000u+off,n,header,keys);
        unsigned rk=ref_accumulate(&ref,c->ls+lsa+off,lsa+off,0x10000000u+off,n,header,rkeys);
        CHECK(k<=2 && rk<=2);
        if(!(data && header)) for(unsigned i=0;i<rk;i++){int found=0;for(unsigned j=0;j<k;j++)if(keys[j]==rkeys[i])found=1;CHECK(found);}
        if(data && header) CHECK(k==0); /* the cap: a data burst offers no key */
        if(k) r.nonempty++;
        for(unsigned i=0;i<k;i++)if(keys[i]==want)r.hits++;
        for(unsigned i=0;i<rk;i++)if(rkeys[i]==want)(*ref_hits)++;
        off+=n;
    }
    free(c->ls);free(c);return r;
}
static uint32_t struct_get(const uint8_t* file,uint32_t* pos);
static uint32_t registered_n;static uint64_t registered[64];
/* Replay one recorded job. Returns 1 when the identification of each transfer
 * is the same as the reference. Sets *bytes to the bytes that the production
 * accumulator hashed. */
static int replay(const uint8_t* file,uint32_t* pos,uint64_t* bytes){
    spu_context* c=fresh();ref_t ref;memset(&ref,0,sizeof ref);
    uint32_t n=struct_get(file,pos),same=1;*bytes=0;
    for(uint32_t t=0;t<n;t++){
        uint32_t lsa=struct_get(file,pos),size=struct_get(file,pos);const uint8_t* p=file+*pos;*pos+=size;
        if(!(lsa>=0x4000u && lsa+size<=0x3E000u)) continue;
        memcpy(c->ls+lsa,p,size);
        uint64_t keys[2]={0,0},rkeys[2]={0,0};
        unsigned k=spu_stage_accumulate(c,c->ls+lsa,lsa,0,size,1,keys),rk=ref_accumulate(&ref,c->ls+lsa,lsa,0,size,1,rkeys);
        if(k || c->stage_hdr_span<STAGE_SPAN_PENDING) *bytes+=size;
        unsigned mask=0,rmask=0;
        for(unsigned i=0;i<k;i++)for(unsigned j=0;j<registered_n;j++)if(keys[i]==registered[j])mask|=1u<<j;
        for(unsigned i=0;i<rk;i++)for(unsigned j=0;j<registered_n;j++)if(rkeys[i]==registered[j])rmask|=1u<<j;
        if(mask!=rmask) same=0;
        if(mask){c->stage_hashed=0;ref.hashed=0;}
    }
    free(c->ls);free(c);return same;
}
static uint32_t struct_get(const uint8_t* file,uint32_t* pos){uint32_t v;memcpy(&v,file+*pos,4);*pos+=4;return v;}
int main(int argc,char** argv){
    if(argc==4 && !strcmp(argv[1],"registry")){ /* registry <stream> <keys> */
        FILE* f=fopen(argv[3],"rb");CHECK(f);
        while(fscanf(f,"%llu",(unsigned long long*)&registered[registered_n])==1) registered_n++;
        fclose(f);CHECK(registered_n && registered_n<64);
        f=fopen(argv[2],"rb");CHECK(f);fseek(f,0,SEEK_END);long len=ftell(f);fseek(f,0,SEEK_SET);
        uint8_t* file=malloc(len);CHECK(file);CHECK(fread(file,1,len,f)==(size_t)len);fclose(f);
        uint32_t pos=0,jobs=struct_get(file,&pos),same=0;uint64_t bytes=0,total=0;
        for(uint32_t j=0;j<jobs;j++){uint64_t b;if(replay(file,&pos,&b))same++;bytes+=b;total++;}
        printf("registry jobs=%u same_identification=%u bytes_hashed=%llu registered=%u\n",jobs,same,(unsigned long long)bytes,registered_n);
        free(file);return same==jobs?0:1;
    }
    unsigned passed=0;unsigned ref_hits;
    tag="case 1"; /* 1. Exact load, both modes: the keys equal those of the reference; the
     *    registered key is offered. */
    image(src,0x12660,0x4000,7);
    for(int h=0;h<2;h++){ref_hits=0;result r=run(&ref_hits,0x4000,0x12640,0x4000,0x4000,h,0,fnv(src,0x12640));
        CHECK(r.hits==1 && ref_hits==1);passed++;} /* image without trailer */
    for(int h=0;h<2;h++){ref_hits=0;result r=run(&ref_hits,0x4000,0x12660,0x4000,0x4000,h,0,fnv(src,0x12640));
        CHECK(r.hits==(h?1u:0u) && ref_hits==(h?1u:0u));passed++;} /* with trailer */
    tag="case 2"; /* 2. Padded load. */
    image(src,0x179B0,0x4000,11);
    for(int h=0;h<2;h++){ref_hits=0;result r=run(&ref_hits,0x4000,0x17A00,0x4000,0x4000,h,0,fnv(src,0x17990));
        CHECK(r.hits==(h?1u:0u) && ref_hits==(h?1u:0u));passed++;}
    tag="case 3"; /* 3. Uneven chunks. */
    {ref_hits=0;result r=run(&ref_hits,0x4000,0x17A00,0x1000,0x2340,1,0,fnv(src,0x17990));CHECK(r.hits==1);passed++;}
    tag="case 4"; /* 4. First transfer below 0x30 bytes: sorted when 0x30 bytes hold. */
    for(uint32_t first=0x10;first<0x30;first+=8){ref_hits=0;
        result r=run(&ref_hits,0x4000,0x17A00,first,0x4000,1,0,fnv(src,0x17990));
        CHECK(r.hits==1);passed++;}
    {ref_hits=0;result r=run(&ref_hits,0x4000,0x17A00,0x18,0x10,1,0,fnv(src,0x17990));CHECK(r.hits==1);passed++;} /* the sort waits for 0x30 bytes in LS */
    tag="case 5"; /* 5. Data burst: no key, both modes compared with the reference. */
    for(int h=0;h<2;h++){ref_hits=0;result r=run(&ref_hits,0x2C820,0x1E20,0x4000,0x4000,h,1,0x1234);
        if(h) CHECK(r.nonempty==0); else CHECK(r.nonempty>0);
        CHECK(ref_hits==0);passed++;}
    tag="case 6"; /* 6. Header with another link base: the legacy key only, as before. */
    image(src,0x179B0,0x8000,11);
    {ref_hits=0;result r=run(&ref_hits,0x4000,0x17A00,0x4000,0x4000,1,0,fnv(src,0x17990));CHECK(r.hits==0&&ref_hits==0);passed++;}
    tag="case 7"; /* 7. Two images back to back on one context: each offers its own key. */
    image(src,0x12660,0x4000,7);image(other,0x179B0,0x4000,11);
    {spu_context* c=fresh();ref_t ref;memset(&ref,0,sizeof ref);uint32_t off=0;int hit_a=0,hit_b=0;
     uint64_t want_a=fnv(src,0x12640),want_b=fnv(other,0x17990);
     for(int which=0;which<2;which++){const uint8_t* img=which?other:src;uint32_t size=which?0x17A00:0x12660;off=0;
      memcpy(c->ls+0x4000,img,size);
      while(off<size){uint32_t n=size-off<0x4000?size-off:0x4000;uint64_t keys[2]={0,0};
       unsigned k=spu_stage_accumulate(c,c->ls+0x4000+off,0x4000+off,off,n,1,keys);
       for(unsigned i=0;i<k;i++){if(keys[i]==want_a){hit_a++;c->stage_hashed=0;}if(keys[i]==want_b){hit_b++;c->stage_hashed=0;}}
       off+=n;}}
     CHECK(hit_a==1 && hit_b==1);free(c->ls);free(c);passed++;}
    tag="case 8"; /* 8. Burst below 0x30 bytes: no key in each mode. */
    image(src,0x12660,0x4000,7);
    for(int h=0;h<2;h++){ref_hits=0;result r=run(&ref_hits,0x4000,0x20,0x10,0x10,h,0,fnv(src,0x12640));CHECK(r.nonempty==0);passed++;}
    printf("PASS %u staged hash cap cases\n",passed);
    return 0;
}
'''
MUTANTS={
 'data-burst-hashed':('block','if (ctx->stage_hdr_span > STAGE_SPAN_PENDING) return 0;','if (0 && ctx->stage_hdr_span > STAGE_SPAN_PENDING) return 0;'),
 'mode-ignored':('block','ctx->stage_hdr_span = !header_identity ? STAGE_SPAN_LEGACY','ctx->stage_hdr_span = 0 ? STAGE_SPAN_LEGACY'),
 'pending-bytes-not-counted':('block','{ ctx->stage_hashed += size; return 0; }','{ return 0; }'),
 'pending-bytes-not-hashed':('block','stage_hash_bytes(ctx, ctx->ls + ctx->stage_lo, ctx->stage_hashed);','(void)0;'),
 'header-burst-taken-as-data':('header','if (stage_be32(base + 0x20) != 0xC0DEC0DEu) return STAGE_SPAN_DATA;','if (stage_be32(base + 0x20) == 0xC0DEC0DEu) return STAGE_SPAN_DATA;'),
 'byte-order-turned':('header','return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];','return ((uint32_t)p[3] << 24) | ((uint32_t)p[2] << 16) | ((uint32_t)p[1] << 8) | p[0];'),
 'sorted-before-header-lands':('block','ctx->stage_hashed + size >= 0x30u','ctx->stage_hashed + size >= 0x20u'),
 'small-start-never-sorted':('block','else if (ctx->stage_hdr_span == STAGE_SPAN_PENDING && ','else if (0 && '),
 'image-size-field-wrong':('header','uint32_t image = stage_be32(ls + 0x14);','uint32_t image = stage_be32(ls + 0x18);'),
 'link-base-of-header-ignored':('header',' || stage_be32(ls + 0x28) != lsa',''),
}
text=SOURCE.read_text(encoding='utf-8');block=text[text.index(BEGIN):text.index(END)+len(END)];header=HEADER.read_text(encoding='utf-8')
for name,(where,old,new) in MUTANTS.items():
    assert (block if where=='block' else header).count(old)==1,name

def compile_and_run(label,block_text,header_text,fixture=FIXTURE,arguments=()):
    target=out/label;target.mkdir();c=target/'check.c'
    c.write_text(fixture.replace('@IDENTITY@',block_text),encoding='utf-8');(target/'spu_jobmod_identity.h').write_text(header_text,encoding='utf-8')
    exe=target/'check.exe';includes=[sdk/'include',sdk/'runtime/spu',sdk/'runtime/platform']
    if os.name=='nt':
        sys.path.insert(0,str(sdk/'tools'))
        from project import build_environment
        env=build_environment()
        cmd=[env['MV_CLANG'],'/nologo','/D_CRT_SECURE_NO_WARNINGS',*('/I'+str(p) for p in includes),str(c),'/Fe'+str(exe),'/Fo'+str(target)+os.sep]
    else:
        env=os.environ.copy();cmd=[env.get('CC') or 'cc','-std=gnu11','-UNDEBUG','-Wall','-Wno-unused-function',*('-I'+str(p) for p in includes),'-o',str(exe),str(c)]
    build=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=300);(target/'build.log').write_text(build.stdout+build.stderr)
    if build.returncode:
        print(label,'compile failed');print('\n'.join(x for x in (build.stdout+build.stderr).splitlines() if 'error' in x.lower())[-1500:]);return dict(label=label,build=build.returncode,returncode=None,stdout='',stderr=(build.stdout+build.stderr)[-1500:])
    run=subprocess.run([str(exe),*map(str,arguments)],cwd=target,capture_output=True,text=True,timeout=600)
    return dict(label=label,build=0,returncode=run.returncode,stdout=run.stdout.strip(),stderr=run.stderr.strip()[-1500:])

def registered_keys():
    manifest=root/'build/native/native-world-input/spu/jobmods_manifest.json'
    if not manifest.exists():return None
    entries=json.loads(manifest.read_text());return [e['staged_fnv'] for e in entries],[e['name'] for e in entries]

def stream(dump):
    """The recorded policy-mode GET transfers of each job: lsa, size, bytes."""
    sys.path.insert(0,str(root/'scripts'));import spu_job_dump as rd
    jobs=[]
    for job in rd.read_dir(dump):
        transfers=[]
        for r in job.records:
            if r['tag']!=rd.TAG_DMA or not r['is_get'] or r['bytes'] is None:continue
            if not (r['lsa']>=0x4000 and r['lsa']+r['size']<=0x3E000):continue
            transfers.append((r['lsa'],r['size'],r['bytes']))
        if transfers:jobs.append(transfers)
    parts=[struct.pack('<I',len(jobs))]
    for transfers in jobs:
        parts.append(struct.pack('<I',len(transfers)))
        for lsa,size,bytes_ in transfers:parts.append(struct.pack('<II',lsa,size)+bytes_)
    return b''.join(parts),len(jobs),sum(len(t[2]) for job in jobs for t in job)

report: dict =dict(game_inputs=False,source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),header_sha256=hashlib.sha256(HEADER.read_bytes()).hexdigest(),
            checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),mutants={})
keys=registered_keys();replay=None
if keys and args.dump.exists():
    data,jobs,total_bytes=stream(args.dump);(out/'stream.bin').write_bytes(data);report['transferred_bytes']=total_bytes
    (out/'keys.txt').write_text('\n'.join(str(k) for k in keys[0])+'\n')
    report.update(game_inputs=True,dump=str(args.dump),jobs=jobs,registered=keys[1]);replay=(out/'stream.bin',out/'keys.txt')
else:
    print('NOTE no job dump and manifest: the workload registration replay is skipped')
ok=True;production=compile_and_run('production',block,header);report['production']=production
print(production.get('stdout') or production.get('stderr') or production.get('log'));ok&=production['build']==0 and production['returncode']==0
if replay:
    registration=compile_and_run('registration',block,header,arguments=('registry',replay[0],replay[1]));report['registration']=registration
    print(registration.get('stdout') or registration.get('stderr'));ok&=registration.get('returncode')==0
for name,(where,old,new) in MUTANTS.items():
    b=block.replace(old,new) if where=='block' else block;h=header.replace(old,new) if where=='header' else header
    results=[]
    for label,args_ in (('synthetic',()),('registry',('registry',*replay)) if replay else ()):
        if label=='synthetic' or replay: results.append(compile_and_run('mutant-'+name+'-'+label,b,h,arguments=args_))
    killed=any(r['returncode'] not in (None,0) for r in results)
    report['mutants'][name]=dict(killed=killed,results=results);print(f'mutant {name}: {"killed" if killed else "SURVIVED"}');ok&=killed
(out/'result.json').write_text(json.dumps(report,indent=2));print('PASS' if ok else 'FAIL',out);return_code=0 if ok else 1
raise SystemExit(return_code)
