"""Production full-face identity; independent spans and actual sparse-path RED."""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/"vendor/ps3recomp"
if os.name=="nt":
    from project import build_environment
    os.environ.update(build_environment())

def main():
    out=ROOT/'temp/checks'/f'texture-fingerprint-{time.time_ns()}';out.mkdir(parents=True)
    header=VENDOR/'libs/video/rsx_texture_fingerprint.h';backend=VENDOR/'libs/video/rsx_d3d12_backend.c'
    source=backend.read_text();a=source.index('static u32 tex_csum(');sparse=source[a:source.index('\n}',a)+2]
    prefix='#include <stdint.h>\n#include <string.h>\ntypedef uint32_t u32;typedef uint8_t u8;\n'
    fixture=r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rsx_texture_fingerprint.h"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"fingerprint contract line %d: %s\n",__LINE__,#x);return 3;}}while(0)
static unsigned char bytes[65536],packed[6*2048];
int main(void){
    CHECK(XXH3_64bits("",0)==UINT64_C(0x2d06800538d394c2));
    for(unsigned i=0;i<sizeof bytes;i++)bytes[i]=(unsigned char)((i*17+(i>>5)*83)%251);
    rsx_texture_source_view v;
    CHECK(rsx_texture_source_view_init(128,128,0xa5,0,1,sizeof bytes,&v));
    CHECK(v.face_bytes==65536&&v.hashed_bytes==65536&&v.span_bytes==65536);
    uint64_t h=rsx_texture_source_fingerprint(bytes,&v);u32 old=tex_csum(bytes,65536);
    bytes[7]^=128;CHECK(tex_csum(bytes,65536)==old); /* actual old production misses this byte */
    CHECK(rsx_texture_source_fingerprint(bytes,&v)!=h);bytes[7]^=128;
    for(unsigned i=0;i<65536;i+=97){bytes[i]^=1;CHECK(rsx_texture_source_fingerprint(bytes,&v)!=h);bytes[i]^=1;}
    bytes[65535]^=1;CHECK(rsx_texture_source_fingerprint(bytes,&v)!=h);bytes[65535]^=1;
    CHECK(rsx_texture_source_view_init(32,16,0xa5,1,3,sizeof bytes,&v));
    CHECK(v.face_bytes==2048&&v.face_stride==2688&&v.span_bytes==15488&&v.hashed_bytes==12288);
    for(unsigned f=0;f<6;f++)memcpy(packed+f*2048,bytes+f*2688,2048);
    h=rsx_texture_source_fingerprint(bytes,&v);CHECK(h==XXH3_64bits(packed,sizeof packed));
    for(unsigned f=0;f<6;f++)for(unsigned i=0;i<2048;i+=127){
        unsigned at=f*2688+i;bytes[at]^=64;CHECK(rsx_texture_source_fingerprint(bytes,&v)!=h);bytes[at]^=64;
    }
    bytes[2048]^=32;CHECK(rsx_texture_source_fingerprint(bytes,&v)==h);bytes[2048]^=32;
    CHECK(!rsx_texture_source_view_init(32,16,0xa5,1,3,15487,&v));
    CHECK(rsx_texture_source_view_init(16,16,0xa8,1,2,sizeof bytes,&v));
    CHECK(v.face_bytes==256&&v.face_stride==384&&v.span_bytes==2176); /* BC3: 16-byte blocks */
    CHECK(rsx_texture_source_view_init(5,7,0xa6,0,1,sizeof bytes,&v));CHECK(v.face_bytes==32); /* BC1 */
    CHECK(rsx_texture_source_view_init(5,7,0xa8,0,1,sizeof bytes,&v));CHECK(v.face_bytes==64); /* BC3 */
    CHECK(rsx_texture_source_view_init(16,16,0xa4,0,1,sizeof bytes,&v));CHECK(v.face_bytes==512); /* packed 16-bit SOURCE */
    CHECK(rsx_texture_source_view_init(32,16,0x85,0,1,sizeof bytes,&v));CHECK(v.face_bytes==2048); /* swizzled footprint */
    CHECK(rsx_texture_source_view_init(16,16,0xa5,1,0,sizeof bytes,&v));CHECK(v.face_stride==1024);
    CHECK(!rsx_texture_source_view_init(0,16,0xa5,0,1,sizeof bytes,&v));
    CHECK(!rsx_texture_source_view_init(4097,16,0xa5,0,1,sizeof bytes,&v));
    CHECK(!rsx_texture_source_view_init(16,16,0xa5,2,1,sizeof bytes,&v));
    CHECK(!rsx_texture_source_view_init(16,16,0xa5,1,33,sizeof bytes,&v));
    CHECK(!rsx_texture_source_view_init(4096,4096,0xa5,1,32,1024,&v));
    puts("PASS full 2D/six-face content, mip gaps/stride, BC1/BC3/packed/swizzled spans and actual sparse-path RED");return 0;
}
"""
    compiler=os.environ.get('MV_CLANG') or shutil.which('clang-cl' if os.name=='nt' else 'clang') or shutil.which('cc')
    assert compiler,'Prepare compiler environment and set MV_CLANG'
    result={'qualification':'Authored CPU source bytes and exact production layout/fingerprint; actual sparse reference demonstrates missed content. No GPU descriptor/game/FPS proof.','source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [header,backend,VENDOR/'libs/video/rsx_texture_layout.c']},'commands':[]}
    def command(cmd,tag):
        p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=60)
        result['commands'].append(dict(tag=tag,command=cmd,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));(out/'result.json').write_text(json.dumps(result,indent=2));return p
    def run(text,tag):
        work=out/tag;work.mkdir();(work/'rsx_texture_fingerprint.h').write_text(text)
        c=work/'test.c';c.write_text(prefix+sparse+'\n'+fixture);exe=work/('test.exe' if os.name=='nt' else 'test')
        if os.name=='nt':cmd=[compiler,'/nologo','/TC','/std:c17','/O2','/UNDEBUG','/MDd','/I'+str(work),'/I'+str(VENDOR/'libs/video'),'/I'+str(VENDOR/'include'),str(c),str(VENDOR/'libs/video/rsx_texture_layout.c'),'/Fo'+str(work)+'/', '/Fe'+str(exe)]
        else:cmd=[compiler,'-std=c17','-O2','-UNDEBUG','-I'+str(work),'-I'+str(VENDOR/'libs/video'),'-I'+str(VENDOR/'include'),str(c),str(VENDOR/'libs/video/rsx_texture_layout.c'),'-lm','-o',str(exe)]
        assert command(cmd,tag+'-compile').returncode==0,f'Compilation failed: {out}/result.json'
        return command([str(exe)],tag)
    text=header.read_text();assert run(text,'production').returncode==0,f'Production failed: {out}/result.json'
    mutants={'prefix-only':text.replace('XXH3_64bits(source,(size_t)view->face_bytes)','XXH3_64bits(source,4)'),
      'first-face-only':text.replace('face<view->faces','face<1'),
      'ignore-mip-stride':text.replace('stride = (chain + 127u) & ~UINT64_C(127);','stride = face;')}
    for tag,mutant in mutants.items():
        assert mutant!=text;assert run(mutant,tag).returncode==3,f'Mutant survived: {tag}'
    result['passed']=True;(out/'result.json').write_text(json.dumps(result,indent=2));print('PASS production fingerprint; actual sparse-path RED; three mutants rejected');print(out/'result.json')
if __name__=='__main__':main()
