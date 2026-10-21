"""Compile/run the production opt-in phase accounting, including no-clock mode."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
if not VIDEO.exists():
    VIDEO = ROOT / 'libs/video'
SOURCE = r'''
#include "rsx_texture_profile.h"
#include <assert.h>
#include <math.h>
#include <stdlib.h>
/* Actual production lookup/checksum bodies with authored cache/memory inputs. */
#define VP_TEX_SLOTS 4
typedef uint32_t u32;
typedef uint8_t u8;
typedef struct {void*res;u32 key,w,h,fmt,off,csum;int cube,used;} VPTexSlot;
static struct {unsigned vp_tex_capacity;VPTexSlot vp_tex[4];} s_d3d;
static u8 source_bytes[256];
static u8* vm_base=source_bytes;
@CHECKSUM@
@PROFILE_CHECKSUM@
static int production_lookup(u32 off,u32 w,u32 h,u32 fmt,int cube,rsx_texture_profile_call*profile){
    u32 key_off=off,bpp=4,blkrow=0,blkrows=0;int dxt=0;
@LOOKUP@
    return slot>=0?slot:-100;
}
typedef struct {double t; unsigned reads;} test_clock;
static double clock_read(void* p){test_clock*c=p;c->reads++;return c->t;}
int main(void){
    rsx_texture_profile measured={0};rsx_texture_profile_call probe;test_clock fake={0};
    s_d3d.vp_tex_capacity=4;
    s_d3d.vp_tex[1]=(VPTexSlot){(void*)1,64,2,2,0x85,64,0,0,1};
    rsx_texture_profile_begin(&probe,&measured,clock_read,&fake);
    int slot=production_lookup(64,2,2,0x85,0,&probe);
    rsx_texture_profile_finish(&probe,slot);
    assert(slot==1&&measured.outcomes[RSX_TEX_FRAME_HIT]==1&&measured.examined==2&&!measured.checksum_calls);
    s_d3d.vp_tex[1].used=0;
    s_d3d.vp_tex[1].csum=tex_csum(source_bytes+64,16);
    rsx_texture_profile_begin(&probe,&measured,clock_read,&fake);
    slot=production_lookup(64,2,2,0x85,0,&probe);
    rsx_texture_profile_finish(&probe,slot);
    assert(slot==1&&measured.outcomes[RSX_TEX_VALIDATED_HIT]==1&&measured.checksum_calls==1);
    assert(measured.sampled_words==4&&s_d3d.vp_tex[1].used==1);
    source_bytes[64]^=1;s_d3d.vp_tex[1].used=0;
    rsx_texture_profile_begin(&probe,&measured,clock_read,&fake);
    slot=production_lookup(64,2,2,0x85,0,&probe);
    rsx_texture_profile_finish(&probe,slot);
    assert(slot==1&&measured.outcomes[RSX_TEX_STALE]==1&&measured.checksum_calls==2);
    rsx_texture_profile_begin(&probe,&measured,clock_read,&fake);
    slot=production_lookup(128,2,2,0x85,0,&probe);
    rsx_texture_profile_finish(&probe,slot);
    assert(slot==-100&&measured.outcomes[RSX_TEX_MISS]==1&&measured.examined==10&&measured.failures==1);
    rsx_texture_profile s={0};rsx_texture_profile_call c;test_clock t={0};
    rsx_texture_profile_begin(&c,&s,NULL,&t);
    rsx_texture_profile_lookup_begin(&c);
    rsx_texture_profile_lookup_end(&c,99,RSX_TEX_FRAME_HIT);
    rsx_texture_profile_checksum_begin(&c,8192);
    rsx_texture_profile_checksum_end(&c);
    rsx_texture_profile_finish(&c,1);
    assert(!t.reads&&!s.calls&&!s.examined&&!s.sampled_words);

    rsx_texture_profile_begin(&c,&s,clock_read,&t);
    t.t=1;rsx_texture_profile_lookup_begin(&c);
    t.t=3;rsx_texture_profile_lookup_end(&c,7,RSX_TEX_VALIDATED_HIT);
    t.t=4;rsx_texture_profile_checksum_begin(&c,8192);
    t.t=5;rsx_texture_profile_checksum_end(&c);
    /* A later fallthrough must not charge lookup a second time. */
    rsx_texture_profile_lookup_end(&c,99,RSX_TEX_MISS);
    c.outcome=RSX_TEX_STALE;
    t.t=8;rsx_texture_profile_finish(&c,4);
    assert(s.calls==1&&s.outcomes[RSX_TEX_STALE]==1&&!s.failures);
    assert(s.setup==1&&s.lookup==2&&s.checksum==1&&s.remainder==4&&s.total==8);
    assert(s.examined==7&&s.checksum_calls==1&&s.sampled_words==1024&&!s.clock_errors);
    assert(s.total==s.setup+s.lookup+s.checksum+s.remainder);

    for(int outcome=0;outcome<RSX_TEX_OUTCOMES;outcome++){
        rsx_texture_profile_begin(&c,&s,clock_read,&t);
        c.outcome=outcome;t.t+=1;rsx_texture_profile_finish(&c,-1);
    }
    assert(s.failures==RSX_TEX_OUTCOMES&&s.calls==1+RSX_TEX_OUTCOMES);
    assert(s.outcomes[RSX_TEX_FRAME_HIT]==1&&s.outcomes[RSX_TEX_STALE]==2);
    memset(&s,0,sizeof(s));
    assert(!s.calls&&!s.total&&!s.checksum_calls);
    rsx_texture_profile_begin(&c,&s,clock_read,&t);
    t.t-=1;rsx_texture_profile_finish(&c,-1);
    assert(s.clock_errors==1&&s.failures==1&&s.total==-1);
    return 0;
}
'''

if __name__ == '__main__':
    if os.name == 'nt' and (ROOT / 'scripts/project.py').exists():
        from project import build_environment
        os.environ.update(build_environment())
    compiler = os.environ.get('MV_CLANG') or os.environ.get('CC') or shutil.which('clang-cl' if os.name == 'nt' else 'cc')
    if not compiler:
        raise SystemExit('C compiler required')
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        source = directory / 'profile.c'
        backend = (VIDEO / 'rsx_d3d12_backend.c').read_text()
        def function(signature):
            start = backend.index(signature)
            return backend[start:backend.index('\n}', start) + 2]
        body = function('static int vp_upload_tex_slot_impl(')
        start = body.index('    #define TEX_CSUM')
        stop = body.index('    rsx_texture_profile_lookup_end(profile, VP_TEX_SLOTS, RSX_TEX_MISS);')
        stop += len('    rsx_texture_profile_lookup_end(profile, VP_TEX_SLOTS, RSX_TEX_MISS);')
        fixture = SOURCE.replace('@LOOKUP@', body[start:stop])
        fixture = fixture.replace('@CHECKSUM@', function('static u32 tex_csum('))
        fixture = fixture.replace('@PROFILE_CHECKSUM@', function('static u32 texture_profile_csum('))
        source.write_text(fixture)
        binary = directory / ('profile.exe' if os.name == 'nt' else 'profile')
        include = str(VIDEO)
        if 'clang-cl' in Path(compiler).name.lower() or Path(compiler).name.lower() == 'cl.exe':
            command = [compiler, '/nologo', '/TC', '/O2', '/UNDEBUG', '/I', include, str(source), '/Fe:' + str(binary)]
        else:
            command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-I', include, str(source), '-o', str(binary)]
        subprocess.run(command, cwd=directory, check=True)
        environment = os.environ.copy()
        environment.pop('TEX_NOCACHE', None)
        subprocess.run([str(binary)], cwd=directory, env=environment, check=True)
    print('PASS: actual cache lookup/checksum, disjoint phase accounting, disabled clock and visible failure')
