"""Game-free checks for staged jobmod identity (SPU_JOBMOD_HEADER_FNV).

Compiles the production staging accumulator from spu_channels.c with an
authored fixture. Images are synthetic C0DEC0DE headers over pseudo-random
bytes; nothing is read from a game. Each case stages chunked transfers the
way a policy module does and records which registry keys are offered. Six
source mutants must each fail. No native execution or speed claim."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
SDK = ROOT / 'vendor/ps3recomp'
SOURCE = SDK / 'runtime/spu/spu_channels.c'
BEGIN = '/* ---- Staged jobmod identity ----'
END = '/* ---- end staged jobmod identity ---- */'

FIXTURE = r'''
#include "spu_context.h"
#include "spu_jobmod_identity.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
@IDENTITY@
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static uint64_t fnv(const uint8_t* p,uint32_t n){uint64_t h=1469598103934665603ULL;for(uint32_t i=0;i<n;i++)h=(h^p[i])*1099511628211ULL;return h;}
static void put(uint8_t* p,uint32_t v){p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;}
static uint8_t src[0x40000];
/* Authored image: header fields at +0x14 (image size), +0x20 (magic), +0x28
 * (link base), pseudo-random body, zero tail as load padding. */
static void image(uint32_t size,uint32_t base,uint32_t seed){
    memset(src,0,sizeof src);uint32_t s=seed;
    for(uint32_t i=0;i<size;i++){s=s*1103515245u+12345u;src[i]=(uint8_t)(s>>16);}
    put(src+0x14,size);put(src+0x20,0xC0DEC0DEu);put(src+0x28,base);
}
typedef struct{unsigned offered,last_index,with_two,legacy_hits;}result;
/* Stage [lsa, lsa+total) in chunk-byte transfers; an extra gap transfer (if
 * gap_at) skips 0x100 bytes once. Mirrors the caller: a registry hit ends the
 * burst (stage_hashed = 0). */
static result stage(spu_context* c,uint32_t lsa,uint32_t total,uint32_t chunk,int header,
                    uint64_t want,uint32_t gap_at,int after){
    result r={0,0,0,0};uint32_t off=0;unsigned idx=0;
    while(off<total){
        uint32_t n=total-off<chunk?total-off:chunk;
        if(gap_at&&off==gap_at){off+=0x100;continue;}
        uint64_t keys[2]={0,0};
        unsigned k=spu_stage_accumulate(c,c->ls+lsa+off,lsa+off,0x10000000u+off,n,header,keys);
        CHECK(k<=2);
        if(k==2)r.with_two++;
        for(unsigned i=0;i<k;i++)if(keys[i]==want){r.offered++;r.last_index=idx;if(i==0)r.legacy_hits++;c->stage_hashed=0;break;}
        off+=n;idx++;
    }
    for(int extra=0;extra<after;extra++){ /* contiguous follow-on data */
        uint64_t keys[2]={0,0};
        unsigned k=spu_stage_accumulate(c,c->ls+lsa+off,lsa+off,0x20000000u,0x400,header,keys);
        for(unsigned i=0;i<k;i++)if(keys[i]==want)r.offered++;
        off+=0x400;
    }
    return r;
}
static spu_context* fresh(void){
    spu_context* c=calloc(1,sizeof *c);CHECK(c);c->ls=calloc(1,0x40000);CHECK(c->ls);return c;
}
/* The production hook runs after a transfer lands, so LS is filled first. */
static result run(uint32_t lsa,uint32_t size,uint32_t staged,uint32_t chunk,int header,uint32_t gap,int after){
    spu_context* c=fresh();
    uint64_t want=fnv(src,size-0x20);
    memcpy(c->ls+lsa,src,staged);
    result r=stage(c,lsa,staged,chunk,header,want,gap,after);
    free(c->ls);free(c);return r;
}
int main(int argc,char** argv){
    if(argc>1&&!strcmp(argv[1],"env")){printf("%d\n",spu_jobmod_header_fnv_enabled());return 0;}
    unsigned passed=0;
    /* 1. Exact load (image - 0x20): legacy key matches at the final transfer
     *    in both modes; the header key is never offered as a duplicate. */
    for(int h=0;h<2;h++){image(0x12660,0x4000,7);result r=run(0x4000,0x12660,0x12640,0x4000,h,0,0);
        CHECK(r.offered==1&&r.legacy_hits==1&&r.last_index==4&&r.with_two==0);passed++;}
    /* 2. Padded load (image 0x179B0 staged as 0x17A00): legacy never matches;
     *    header mode offers the identity exactly once, at the final transfer. */
    image(0x179B0,0x4000,11);
    { result r=run(0x4000,0x179B0,0x17A00,0x4000,0,0,0);CHECK(r.offered==0);passed++; }
    { result r=run(0x4000,0x179B0,0x17A00,0x4000,1,0,0);
      CHECK(r.offered==1&&r.legacy_hits==0&&r.last_index==5&&r.with_two==1);passed++; }
    /* 3. Same padded load in uneven 0x1000/0x2340 chunks. */
    { result r=run(0x4000,0x179B0,0x17A00,0x2340,1,0,0);CHECK(r.offered==1&&r.with_two==1);passed++; }
    /* 4. Header link base differs from the staging address: no header key. */
    image(0x179B0,0x8000,11);
    { result r=run(0x4000,0x179B0,0x17A00,0x4000,1,0,0);CHECK(r.offered==0&&r.with_two==0);passed++; }
    /* 5. No magic: no header key. */
    image(0x179B0,0x4000,11);src[0x20]^=1;
    { result r=run(0x4000,0x179B0,0x17A00,0x4000,1,0,0);CHECK(r.offered==0&&r.with_two==0);passed++; }
    /* 6. Non-contiguous burst (a 0x100 gap): the burst restarts; no identity. */
    image(0x179B0,0x4000,11);
    { result r=run(0x4000,0x179B0,0x17A00,0x4000,1,0x8000,0);CHECK(r.offered==0);passed++; }
    /* 7. Unregistered-at-completion burst continued by contiguous data: the
     *    header key is offered once, never again on follow-on transfers. */
    { spu_context* c=fresh();memcpy(c->ls+0x4000,src,0x17A00);
      result r=stage(c,0x4000,0x17A00,0x4000,1,0x1234,0,0);CHECK(r.with_two==1);
      uint64_t keys[2];unsigned twos=0;
      for(int i=0;i<4;i++){unsigned k=spu_stage_accumulate(c,c->ls+0x1BA00+i*0x400,0x1BA00+i*0x400,0,0x400,1,keys);twos+=k==2;}
      CHECK(twos==0);free(c->ls);free(c);passed++; }
    /* 8. Image too small for the 0x800 threshold: no header key. */
    image(0x800,0x4000,3);
    { result r=run(0x4000,0x800,0x900,0x900,1,0,0);CHECK(r.offered==0&&r.with_two==0);passed++; }
    /* 9. Two back-to-back padded loads on one context both resolve. */
    { spu_context* c=fresh();image(0x179B0,0x4000,11);uint64_t want=fnv(src,0x17990);
      memcpy(c->ls+0x4000,src,0x17A00);
      result a=stage(c,0x4000,0x17A00,0x4000,1,want,0,0);
      result b=stage(c,0x4000,0x17A00,0x4000,1,want,0,0);
      CHECK(a.offered==1&&b.offered==1);free(c->ls);free(c);passed++; }
    printf("PASS %u staged jobmod identity cases\n",passed);
    return 0;
}
'''

MUTANTS = {
    'span-includes-trailer': ('return image - 0x20u;', 'return image;'),
    'ignores-link-base': (' || stage_be32(ls + 0x28) != lsa', ''),
    'hashes-padding': ('uint32_t take = ctx->stage_hdr_span - ctx->stage_hdr_len;', 'uint32_t take = size;'),
    'ignores-switch': ('header_identity ? stage_header_span(ls, lsa, size) : 0', 'stage_header_span(ls, lsa, size)'),
}


def compile_and_run(out, label, identity, fixture=FIXTURE, header=None):
    target = out / label
    target.mkdir()
    c = target / 'check.c'
    c.write_text(fixture.replace('@IDENTITY@', identity), encoding='utf-8')
    if header is not None:
        (target / 'spu_jobmod_identity.h').write_text(header, encoding='utf-8')
    exe = target / ('check.exe' if os.name == 'nt' else 'check')
    includes = [SDK / 'include', SDK / 'runtime/spu', SDK / 'runtime/platform']
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        cmd = [env['MV_CLANG'], '/nologo', '/D_CRT_SECURE_NO_WARNINGS', *('/I' + str(p) for p in includes),
               str(c), '/Fe' + str(exe), '/Fo' + str(target) + os.sep]
    else:
        cmd = [env.get('CC') or shutil.which('cc'), '-std=gnu11', '-pthread', '-UNDEBUG', '-Wall', '-Wno-unused-function',
               *('-I' + str(p) for p in includes), '-o', str(exe), str(c)]
    build = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    (target / 'build.log').write_text(build.stdout + build.stderr)
    if build.returncode:
        return dict(label=label, build=build.returncode, log=(build.stdout + build.stderr)[-2000:])
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    modes = {}
    for value in (None, '0', '1', '2'):
        e = {k: v for k, v in os.environ.items() if k != 'SPU_JOBMOD_HEADER_FNV'}
        if value is not None:
            e['SPU_JOBMOD_HEADER_FNV'] = value
        m = subprocess.run([str(exe), 'env'], capture_output=True, text=True, timeout=30, env=e)
        modes[str(value)] = dict(returncode=m.returncode, stdout=m.stdout.strip())
    return dict(label=label, build=0, returncode=run.returncode, output=(run.stdout + run.stderr).strip(), modes=modes)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    text = SOURCE.read_text()
    identity = text[text.index(BEGIN):text.index(END) + len(END)]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('spu-jobmod-identity-' + stamp)
    out.mkdir(parents=True)
    report = dict(game_inputs=False, source=str(SOURCE), source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  identity_sha256=hashlib.sha256(identity.encode()).hexdigest(), mutants={})
    header = (SDK / 'runtime/spu/spu_jobmod_identity.h').read_text(encoding='utf-8')
    ok = True
    production = compile_and_run(out, 'production', identity)
    report['production'] = production
    print(production.get('output') or production.get('log'))
    modes = production.get('modes', {})
    ok &= production.get('build') == 0 and production.get('returncode') == 0
    ok &= modes.get('None', {}).get('stdout') == '0' and modes.get('0', {}).get('stdout') == '0'
    ok &= modes.get('1', {}).get('stdout') == '1' and modes.get('2', {}).get('returncode') != 0
    for name, (old, new) in MUTANTS.items():
        assert identity.count(old) + header.count(old) == 1, name
        mutant = compile_and_run(out, 'mutant-' + name, identity.replace(old, new),
                                 header=header.replace(old, new))
        killed = mutant.get('build') == 0 and mutant.get('returncode') not in (None, 0)
        report['mutants'][name] = dict(killed=killed, output=mutant.get('output') or mutant.get('log'))
        print(f'mutant {name}: {"killed" if killed else "SURVIVED"}')
        ok &= killed
    workers = (ROOT / 'scripts/fixtures/spu_jobmod_identity_threads.c.in').read_text(encoding='utf-8')
    workers = workers.replace('../spu_jobmod_identity.h', 'spu_jobmod_identity.h')
    concurrent = compile_and_run(out, 'concurrent-workers', identity, fixture=workers)
    report['concurrent_workers'] = concurrent
    print(concurrent.get('output') or concurrent.get('log'))
    ok &= concurrent.get('build') == 0 and concurrent.get('returncode') == 0
    for name, declaration in [('shared-selector', 'int'), ('shared-log-counter', 'unsigned')]:
        old = 'static SPU_JOBMOD_THREAD_LOCAL ' + declaration
        assert header.count(old) == 1, name
        mutant = compile_and_run(out, 'mutant-' + name, identity, fixture=workers,
                                 header=header.replace(old, 'static ' + declaration))
        killed = mutant.get('build') == 0 and mutant.get('returncode') not in (None, 0)
        report['mutants'][name] = dict(killed=killed, output=mutant.get('output') or mutant.get('log'))
        print(f'mutant {name}: {"killed" if killed else "SURVIVED"}')
        ok &= killed
    (out / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PASS' if ok else 'FAIL', out)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
