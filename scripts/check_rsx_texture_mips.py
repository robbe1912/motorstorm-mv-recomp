"""Game-free checks for RSX texture mip chains (RSX_TEX_MIPS).

Builds the production rsx_texture_layout.c, the production fingerprint header
and the backend's extracted level selection with an authored fixture. Level
data is synthetic and placed with an independent reference walk (Morton order,
packed levels, 4x4 blocks); nothing is read from a game. Source mutants must
fail. No GPU pixel, rendering or FPS claim; tools on Windows cover D3D12."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
BACKEND = VIDEO / 'rsx_d3d12_backend.c'
FINGERPRINT = VIDEO / 'rsx_texture_fingerprint.h'
LEVEL_BEGIN = '    /* RSX_TEX_MIPS: the levels below level 0'
LEVEL_END = '    const u32 key_off = off;'

FIXTURE = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rsx_texture_layout.h"
#include "fingerprint.h"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
typedef uint64_t u64;
@MIPS_ON@
/* The backend's level selection, extracted verbatim. */
static int select_levels(u32 off,u32 w,u32 h,u32 fmt,u32 mips,u32 depth,int vol,
                         u32* levels_out,u32* bytes_out,rsx_tex_level* lv_out){
    rsx_tex_layout tl;rsx_texture_layout(fmt,w,h,&tl);
    const int dxt=tl.compressed;u32 bpp=tl.compressed?1u:tl.bytes_per_texel;
    u32 blkrow=dxt?tl.row_bytes:0,blkrows=dxt?tl.rows:0;(void)off;
@LEVELS@
    *levels_out=levels;*bytes_out=src_bytes;memcpy(lv_out,mip_lv,sizeof mip_lv);
    return 0;
}
/* Independent references. */
static unsigned morton(unsigned x,unsigned y,unsigned lw,unsigned lh){
    unsigned o=0,b=0;for(unsigned i=0;i<16;i++){if(i<lw)o|=((x>>i)&1u)<<b++;if(i<lh)o|=((y>>i)&1u)<<b++;}return o;}
static unsigned lg(unsigned v){unsigned l=0;while((1u<<l)<v)l++;return l;}
static unsigned half(unsigned v){return v>1?v>>1:1;}
static unsigned level_bytes(unsigned fmt,unsigned w,unsigned h){
    unsigned b=fmt&0x9Fu;
    if(b==0x86)return ((w+3)/4)*((h+3)/4)*8;
    if(b==0x87||b==0x88)return ((w+3)/4)*((h+3)/4)*16;
    return w*h*(b==0x85?4u:b==0x8B?2u:1u);
}
static unsigned ref_levels(unsigned w,unsigned h,unsigned mips){
    if(!mips)mips=1;
    unsigned n=0;
    for(;;){n++;if(n==mips||n==14||(w==1&&h==1))return n;w=half(w);h=half(h);}
}
static void chain(unsigned fmt,unsigned w,unsigned h,unsigned mips){
    rsx_tex_level lv[RSX_MAX_TEXTURE_LEVELS];
    unsigned n=rsx_texture_mip_chain(fmt,w,h,mips,0,lv),off=0,lw=w,lh=h;
    CHECK(n==ref_levels(w,h,mips));
    for(unsigned i=0;i<n;i++){
        CHECK(lv[i].w==lw&&lv[i].h==lh&&lv[i].offset==off);
        CHECK(lv[i].tl.face_bytes==level_bytes(fmt,lw,lh));
        off+=level_bytes(fmt,lw,lh);lw=half(lw);lh=half(lh);
    }
}
static unsigned char texel(unsigned level,unsigned x,unsigned y,unsigned c){return (unsigned char)(level*61u+x*7u+y*13u+c*29u+1u);}
/* Every level of an A8R8G8B8 texture, swizzled or linear, round-trips through
 * the production decoder at the production level offsets. */
static void decode_levels(unsigned fmt,unsigned w,unsigned h,unsigned mips){
    rsx_tex_level lv[RSX_MAX_TEXTURE_LEVELS];
    unsigned n=rsx_texture_mip_chain(fmt,w,h,mips,0,lv);
    unsigned total=lv[n-1].offset+lv[n-1].tl.face_bytes;
    unsigned char*src=calloc(total,1),*dst=calloc(w*h*4,1);CHECK(src&&dst);
    int swz=!(fmt&0x20u);
    for(unsigned i=0;i<n;i++){
        unsigned lw=lv[i].w,lh=lv[i].h;CHECK(lv[i].tl.swizzled==swz);
        for(unsigned y=0;y<lh;y++)for(unsigned x=0;x<lw;x++){
            unsigned o=lv[i].offset+(swz?morton(x,y,lg(lw),lg(lh)):y*lw+x)*4u;
            for(unsigned c=0;c<4;c++)src[o+c]=texel(i,x,y,c);
        }
    }
    for(unsigned i=0;i<n;i++){
        memset(dst,0,w*h*4);
        rsx_texture_decode(dst,lv[i].w*4,src+lv[i].offset,lv[i].w,lv[i].h,&lv[i].tl,0);
        for(unsigned y=0;y<lv[i].h;y++)for(unsigned x=0;x<lv[i].w;x++){
            const unsigned char*d=dst+(y*lv[i].w+x)*4;
            /* ARGB source -> RGBA host, the decoder's documented order. */
            CHECK(d[0]==texel(i,x,y,1)&&d[1]==texel(i,x,y,2)&&d[2]==texel(i,x,y,3)&&d[3]==texel(i,x,y,0));
        }
    }
    free(src);free(dst);
}
/* Compressed levels are block rows copied as stored, down to the 1x1 level's
 * single block. */
static void decode_blocks(unsigned fmt,unsigned w,unsigned h){
    rsx_tex_level lv[RSX_MAX_TEXTURE_LEVELS];
    unsigned n=rsx_texture_mip_chain(fmt,w,h,99,0,lv);
    unsigned total=lv[n-1].offset+lv[n-1].tl.face_bytes;
    unsigned char*src=malloc(total),*dst=malloc(total*4+4096);CHECK(src&&dst);
    for(unsigned i=0;i<total;i++)src[i]=(unsigned char)(i*37u+5u);
    for(unsigned i=0;i<n;i++){
        unsigned pitch=256;memset(dst,0,total*4+4096);
        rsx_texture_decode(dst,pitch,src+lv[i].offset,lv[i].w,lv[i].h,&lv[i].tl,0);
        for(unsigned r=0;r<lv[i].tl.rows;r++)
            CHECK(!memcmp(dst+r*pitch,src+lv[i].offset+r*lv[i].tl.row_bytes,lv[i].tl.row_bytes));
    }
    free(src);free(dst);
}
static void identity(void){
    /* 32x32 A8R8G8B8 cube with 2 levels: chain 4096+1024, stride 5120. */
    rsx_texture_source_view v;
    unsigned char*mem=calloc(6*5120+64,1);CHECK(mem);
    CHECK(rsx_texture_source_view_init(32,32,0x85,1,2,6*5120,&v));
    CHECK(v.face_stride==5120&&v.face_bytes==4096&&v.faces==6);
    rsx_texture_source_view e=v;
    CHECK(rsx_texture_source_view_extend(&e,5120,6*5120));
    CHECK(e.face_bytes==5120&&e.hashed_bytes==6*5120&&e.span_bytes==6*5120);
    uint64_t a=rsx_texture_source_fingerprint(mem,&e),top=rsx_texture_source_fingerprint(mem,&v);
    mem[5*5120+4096+3]^=1;   /* face 5, level 1 */
    CHECK(rsx_texture_source_fingerprint(mem,&e)!=a);
    CHECK(rsx_texture_source_fingerprint(mem,&v)==top);   /* level 0 alone misses it */
    rsx_texture_source_view bad=v;
    CHECK(!rsx_texture_source_view_extend(&bad,5121,6*5120+64));   /* chain past the stride */
    bad=v;CHECK(!rsx_texture_source_view_extend(&bad,4095,6*5120));  /* shorter than level 0 */
    bad=v;CHECK(!rsx_texture_source_view_extend(&bad,5120,6*5120-1));/* past the source */
    /* 2D: a 64x64 A8R8G8B8 with 3 levels hashes 16384+4096+1024 bytes. */
    CHECK(rsx_texture_source_view_init(64,64,0x85,0,3,21504,&v));
    CHECK(rsx_texture_source_view_extend(&v,21504,21504)&&v.face_bytes==21504&&v.span_bytes==21504);
    free(mem);
}
static void selection(void){
    rsx_tex_level lv[RSX_MAX_TEXTURE_LEVELS];u32 levels,bytes;
    int on=texture_mips_on();
    select_levels(0x1000,64,64,0x85,7,1,0,&levels,&bytes,lv);
    CHECK(levels==(on?7u:1u));
    CHECK(bytes==(on?(64u*64+32*32+16*16+8*8+4*4+2*2+1)*4u:64u*64*4));
    select_levels(0x1000,512,512,0x88,11,1,0,&levels,&bytes,lv);   /* DXT5, 11 levels */
    CHECK(levels==(on?10u:1u));   /* 512 -> 1 is ten levels; the guest's 11 is clamped */
    CHECK(on?bytes==lv[9].offset+lv[9].tl.face_bytes:bytes==128u*128*16);
    select_levels(0x1000,64,64,0x85,1,1,0,&levels,&bytes,lv);CHECK(levels==1&&bytes==64u*64*4);
    select_levels(0x1000,16,16,0xA5,4,8,1,&levels,&bytes,lv);CHECK(levels==1&&bytes==16u*16*4*8);  /* volume */
}
int main(int argc,char**argv){
    if(argc>1&&!strcmp(argv[1],"env")){printf("%d\n",texture_mips_on());return 0;}
    chain(0x85,64,32,7);chain(0x85,256,256,9);chain(0xA5,100,60,4);chain(0x86,16,16,5);
    chain(0x88,64,16,7);chain(0x87,512,512,11);chain(0x85,8,8,20);chain(0x85,8,8,0);chain(0x8B,4,64,99);
    decode_levels(0x85,64,32,7);decode_levels(0x85,16,16,5);decode_levels(0xA5,24,10,3);
    decode_blocks(0x86,16,16);decode_blocks(0x88,64,32);
    identity();selection();
    printf("PASS mip chain offsets, per-level swizzled/linear/block decode, chain identity and level selection (RSX_TEX_MIPS=%d)\n",texture_mips_on());
    return 0;
}
'''

MUTANTS = {
    'identity-level0-only': ('levels', '    const u32 src_bytes = levels > 1u\n        ? mip_lv[levels - 1u].offset + mip_lv[levels - 1u].tl.face_bytes\n        :',
                             '    const u32 src_bytes ='),
    'switch-ignored': ('levels', '(!vol && mips > 1u && texture_mips_on())', '(!vol && mips > 1u)'),
    'volume-chained': ('levels', '(!vol && mips > 1u && texture_mips_on())', '(mips > 1u && texture_mips_on())'),
    'cube-chain-overlaps': ('fingerprint', ' ||\n            (view->faces > 1 && chain_bytes > view->face_stride)', ''),
    'extend-no-bound': ('fingerprint', '    if (span > available || span > SIZE_MAX) return 0;\n    view->face_bytes = chain_bytes;',
                        '    view->face_bytes = chain_bytes;'),
}


def extract(backend):
    a = backend.index(LEVEL_BEGIN)
    b = backend.index(LEVEL_END, a)
    s = backend.index('static int texture_mips_on(void)\n{')
    e = backend.index('\n}\n', s) + 3
    return backend[a:b], backend[s:e]


def build_and_run(out, label, levels, mips_on, fingerprint):
    target = out / label
    target.mkdir()
    (target / 'fingerprint.h').write_text(fingerprint)
    c = target / 'check.c'
    c.write_text(FIXTURE.replace('@LEVELS@', levels).replace('@MIPS_ON@', mips_on))
    exe = target / ('check.exe' if os.name == 'nt' else 'check')
    include = [target, VIDEO, ROOT / 'vendor/ps3recomp/include']
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        cmd = [env['MV_CLANG'], '/nologo', '/D_CRT_SECURE_NO_WARNINGS', *('/I' + str(p) for p in include),
               str(c), str(VIDEO / 'rsx_texture_layout.c'), '/Fe' + str(exe), '/Fo' + str(target) + os.sep]
    else:
        cmd = [env.get('CC') or shutil.which('cc'), '-std=gnu11', '-UNDEBUG', '-Wall', '-Werror', '-Wno-unused-function',
               *('-I' + str(p) for p in include), '-o', str(exe), str(c), str(VIDEO / 'rsx_texture_layout.c')]
    build = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    (target / 'build.log').write_text(build.stdout + build.stderr)
    record = dict(label=label, build=build.returncode)
    if build.returncode:
        record['log'] = (build.stdout + build.stderr)[-2000:]
        return record
    base = {k: v for k, v in os.environ.items() if k != 'RSX_TEX_MIPS'}
    runs = {}
    for value in ('0', '1'):
        p = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60, env=dict(base, RSX_TEX_MIPS=value))
        runs[value] = dict(returncode=p.returncode, output=(p.stdout + p.stderr).strip())
    modes = {}
    for value in (None, '2'):
        e = dict(base)
        if value is not None:
            e['RSX_TEX_MIPS'] = value
        p = subprocess.run([str(exe), 'env'], capture_output=True, text=True, timeout=30, env=e)
        modes[str(value)] = dict(returncode=p.returncode, stdout=p.stdout.strip())
    record.update(runs=runs, modes=modes)
    return record


def passed(record):
    return (record['build'] == 0 and all(r['returncode'] == 0 for r in record['runs'].values())
            and record['modes']['None']['stdout'] == '0' and record['modes']['2']['returncode'] != 0)


def main():
    backend = BACKEND.read_text()
    fingerprint = FINGERPRINT.read_text()
    levels, mips_on = extract(backend)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('rsx-texture-mips-' + stamp)
    out.mkdir(parents=True)
    report = dict(game_inputs=False, sources={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                              for p in (BACKEND, FINGERPRINT, VIDEO / 'rsx_texture_layout.c')},
                  mutants={})
    production = build_and_run(out, 'production', levels, mips_on, fingerprint)
    report['production'] = production
    for r in production.get('runs', {}).values():
        print(r['output'])
    if 'log' in production:
        print(production['log'])
    ok = passed(production) if 'runs' in production else False
    for name, (where, old, new) in MUTANTS.items():
        source = levels if where == 'levels' else fingerprint
        assert source.count(old) == 1, name
        mutated = source.replace(old, new)
        rec = build_and_run(out, 'mutant-' + name, mutated if where == 'levels' else levels, mips_on,
                            mutated if where == 'fingerprint' else fingerprint)
        # A mutant that does not build proves nothing about the assertions.
        killed = rec['build'] == 0 and not passed(rec)
        report['mutants'][name] = dict(killed=killed, record=rec)
        print(f'mutant {name}: {"killed" if killed else "BUILD FAILED" if rec["build"] else "SURVIVED"}')
        ok &= killed
    (out / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PASS' if ok else 'FAIL', out)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
