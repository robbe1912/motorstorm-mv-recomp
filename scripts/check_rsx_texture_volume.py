"""Game-free checks for the RSX 3D volume path: actual layout decode and FP declarations.

Builds the production rsx_texture_layout.c and rsx_fp_decompiler.c with an
authored fixture. Volume data is a synthetic Z-dependent pattern placed with an
independent reference Morton walk; nothing is read from a game. No GPU pixel or
rendering-fix claim."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
FIXTURE = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rsx_texture_layout.h"
#include "rsx_fp_decompiler.h"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);return 1;}}while(0)
/* Independent reference: one bit of each axis per level, x then y then z,
 * while that axis still has bits. */
static unsigned ref3(unsigned x,unsigned y,unsigned z,unsigned lw,unsigned lh,unsigned ld){
    unsigned o=0,b=0;
    for(unsigned i=0;i<12;i++){
        if(i<lw)o|=((x>>i)&1u)<<b++;
        if(i<lh)o|=((y>>i)&1u)<<b++;
        if(i<ld)o|=((z>>i)&1u)<<b++;
    }
    return o;
}
static unsigned char value(unsigned x,unsigned y,unsigned z){return (unsigned char)(x*7u+y*29u+z*101u+3u);}
static int volume(unsigned w,unsigned h,unsigned d){
    unsigned lw=rsx_log2_ceil(w),lh=rsx_log2_ceil(h),ld=rsx_log2_ceil(d),n=w*h*d;
    unsigned char *src=calloc(n,1),*dst=calloc(n,1),*seen=calloc(n,1);
    CHECK(src&&dst&&seen);
    for(unsigned z=0;z<d;z++)for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++){
        unsigned o=rsx_swizzle_offset_3d(x,y,z,lw,lh,ld);
        CHECK(o==ref3(x,y,z,lw,lh,ld));CHECK(o<n);CHECK(!seen[o]);seen[o]=1;
        if(d==1)CHECK(o==rsx_swizzle_offset(x,y,lw,lh));
        src[o]=value(x,y,z);
    }
    rsx_tex_layout tl;rsx_texture_layout(0x81,w,h,&tl);  /* B8, swizzled */
    CHECK(tl.swizzled&&tl.bytes_per_texel==1&&tl.dst_bytes_per_texel==1);
    CHECK(rsx_texture_decode_volume(dst,w,w*h,src,w,h,d,&tl,0)==0);
    for(unsigned z=0;z<d;z++)for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)
        CHECK(dst[z*w*h+y*w+x]==value(x,y,z));
    if(d>1){
        /* Negative control: the 2D path (what the renderer used before) does
         * not recover slice 0 of a Morton volume. */
        memset(dst,0,n);rsx_texture_decode(dst,w,src,w,h,&tl,0);
        int same=1;for(unsigned y=0;y<h&&same;y++)for(unsigned x=0;x<w;x++)if(dst[y*w+x]!=value(x,y,0)){same=0;break;}
        CHECK(!same);
    }
    /* Linear (LN) volume: slices of h rows, each row_bytes apart. */
    rsx_tex_layout ln;rsx_texture_layout(0xA1,w,h,&ln);CHECK(!ln.swizzled);
    for(unsigned z=0;z<d;z++)for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)src[z*w*h+y*w+x]=value(x,y,z);
    memset(dst,0,n);CHECK(rsx_texture_decode_volume(dst,w,w*h,src,w,h,d,&ln,0)==0);
    CHECK(!memcmp(dst,src,n));
    free(src);free(dst);free(seen);return 0;
}
static void word(unsigned char *b,unsigned v){unsigned s=(v<<16)|(v>>16);b[0]=s>>24;b[1]=s>>16;b[2]=s>>8;b[3]=s;}
static int fp(unsigned op,unsigned mask,char *text,unsigned size){
    unsigned char code[16]={0};static rsx_fp_constant_block constants;u32 count=0;
    /* op unit1 -> r0.xyzw, END; SRC0 = f[TEX0] (input 4), identity swizzle. */
    word(code,(op<<24)|(1u<<17)|(4u<<13)|(15u<<9)|1u);
    word(code+4,1u|(0xe4u<<9)|(7u<<18));word(code+8,0xe4u<<9);word(code+12,0xe4u<<9);
    return rsx_fp_decompile_buffered_ex(code,sizeof code,0x40,mask,text,size,&count,&constants);
}
int main(void){
    if(volume(16,16,16)||volume(16,16,8)||volume(8,4,2)||volume(4,8,16)||volume(16,16,1))return 1;
    { rsx_tex_layout tl;unsigned char b[64]={0};rsx_texture_layout(0x81,4,4,&tl);
      CHECK(rsx_texture_decode_volume(b,4,16,b,4,4,3,&tl,0)==-1); }  /* NPOT Morton depth */
    static char t[65536];
    CHECK(fp(0x17,1u<<17,t,sizeof t)==1);
    CHECK(strstr(t,"Texture3D   rsx_tex1 : register(t1);"));
    CHECK(strstr(t,"Texture2D   rsx_tex0 : register(t0);"));
    CHECK(strstr(t,"rsx_tex1.Sample(rsx_samp[1], (")&&strstr(t,").xyz)"));
    CHECK(fp(0x18,1u<<17,t,sizeof t)==1);
    CHECK(strstr(t,"rsx_tex1.Sample(rsx_samp[1], (")&&strstr(t,").xyz / ("));
    CHECK(fp(0x17,0,t,sizeof t)==1);          /* legacy all-2D output */
    CHECK(strstr(t,"Texture2D    rsx_tex[16] : register(t0);")&&!strstr(t,"Texture3D"));
    CHECK(strstr(t,"rsx_tex[1].Sample(rsx_samp[1], (")&&strstr(t,").xy)"));
    CHECK(fp(0x17,2u,t,sizeof t)==1&&strstr(t,"TextureCube rsx_tex1")&&!strstr(t,"Texture3D"));
    CHECK(fp(0x17,2u|(1u<<17),t,sizeof t)<0);  /* a unit is never both cube and 3D */
    puts("PASS actual 3D Morton/linear volume decode (Z-dependent, 2D-path negative control, NPOT reject) and Texture3D/.xyz FP declarations");
    return 0;
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('rsx-texture-volume-' + stamp)
    out.mkdir(parents=True)
    c, exe = out / 'check.c', out / ('check.exe' if os.name == 'nt' else 'check')
    c.write_text(FIXTURE)
    sources = [VIDEO / 'rsx_texture_layout.c', VIDEO / 'rsx_fp_decompiler.c']
    env = os.environ.copy()
    include = [ROOT / 'vendor/ps3recomp/include', VIDEO]
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        cmd = [env['MV_CLANG'], '/nologo', '/D_CRT_SECURE_NO_WARNINGS', *('/I' + str(p) for p in include),
               str(c), *map(str, sources), '/Fe' + str(exe), '/Fo' + str(out) + os.sep]
    else:
        cmd = [env.get('CC', 'cc'), '-std=c11', '-UNDEBUG', *('-I' + str(p) for p in include),
               '-o', str(exe), str(c), *map(str, sources), '-lm']
    with (out / 'build.log').open('wb') as log:
        build = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    result = dict(game_inputs=False, build_returncode=build.returncode,
                  source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    run = None
    if build.returncode:
        print((out / 'build.log').read_text(encoding='utf-8', errors='replace'))
    else:
        run = subprocess.run([str(exe)], capture_output=True, timeout=60)
        (out / 'run.log').write_bytes(run.stdout + run.stderr)
        print((run.stdout + run.stderr).decode(errors='replace').strip())
        result['run_returncode'] = run.returncode
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 1 if build.returncode or run.returncode else 0


if __name__ == '__main__':
    raise SystemExit(main())
