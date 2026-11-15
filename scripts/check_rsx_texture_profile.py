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
#include "rsx_texture_fingerprint.h"
#include <assert.h>
#include <math.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
/* Actual production lookup/checksum bodies with authored cache/memory inputs. */
#define VP_TEX_SLOTS 4
typedef uint32_t u32;typedef uint64_t u64;
typedef uint8_t u8;
typedef struct {void*res;u32 key,w,h,fmt,off,mips,depth,levels;u64 csum,last_use;int cube,used;} VPTexSlot;
static struct {unsigned vp_tex_capacity;VPTexSlot vp_tex[4];u64 vp_tex_use_serial;} s_d3d;
static u8 source_bytes[256];
static u8* vm_base=source_bytes;
@CHECKSUM@
@PROFILE_CHECKSUM@
@RETENTION@
@SOURCE_CHECKSUM@
@HINT@
static int production_lookup_levels(u32 off,u32 w,u32 h,u32 fmt,int cube,u32 depth,u32 levels,rsx_texture_profile_call*profile){
    u32 key_off=off,mips=levels>1u?2u:1u,src_bytes=w*h*4*depth;
@LOOKUP@
    return slot>=0?slot:-100;
}
static int production_lookup_depth(u32 off,u32 w,u32 h,u32 fmt,int cube,u32 depth,rsx_texture_profile_call*profile){
    return production_lookup_levels(off,w,h,fmt,cube,depth,1u,profile);
}
static int production_lookup(u32 off,u32 w,u32 h,u32 fmt,int cube,rsx_texture_profile_call*profile){
    return production_lookup_depth(off,w,h,fmt,cube,1,profile);
}
typedef struct {double t; unsigned reads;} test_clock;
static double clock_read(void* p){test_clock*c=p;c->reads++;return c->t;}
int main(void){
    const int hints=vp_tex_hint_on();
    rsx_texture_profile measured={0};rsx_texture_profile_call probe;test_clock fake={0};
    s_d3d.vp_tex_capacity=4;
    s_d3d.vp_tex[1]=(VPTexSlot){.res=(void*)1,.key=64,.w=2,.h=2,.fmt=0x85,.off=64,.mips=1,.used=1};
    rsx_texture_profile_begin(&probe,&measured,clock_read,&fake);
    int slot=production_lookup(64,2,2,0x85,0,&probe);
    rsx_texture_profile_finish(&probe,slot);
    assert(slot==1&&measured.outcomes[RSX_TEX_FRAME_HIT]==1&&measured.examined==2&&!measured.checksum_calls);
    s_d3d.vp_tex[1].used=0;
    s_d3d.vp_tex[1].csum=texture_source_csum(NULL,source_bytes+64,16,2,2,0x85,0,1,1,1);
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
    /* Linear scans examine 2+2+2+4 slots; with hints the two repeat hits
     * examine only the hinted slot. */
    assert(slot==-100&&measured.outcomes[RSX_TEX_MISS]==1&&measured.examined==(hints?8u:10u)&&measured.failures==1);
    if(hints){
        /* A hint naming a slot that no longer holds the key falls back to the
         * scan: the key moved from slot 1 to slot 2 (slot reuse). */
        s_d3d.vp_tex[2]=s_d3d.vp_tex[1];s_d3d.vp_tex[1].key=200;s_d3d.vp_tex[2].used=1;
        rsx_texture_profile_begin(&probe,&measured,clock_read,&fake);
        slot=production_lookup(64,2,2,0x85,0,&probe);
        rsx_texture_profile_finish(&probe,slot);
        assert(slot==2);
        assert(s_vp_tex_hint[vp_tex_hint_hash(64,2,2,0x85,0)]==3);
        /* A colliding/garbage hint (out of range, or another key's slot). */
        s_vp_tex_hint[vp_tex_hint_hash(64,2,2,0x85,0)]=99;
        slot=production_lookup(64,2,2,0x85,0,NULL);assert(slot==2);
        s_vp_tex_hint[vp_tex_hint_hash(64,2,2,0x85,0)]=2;   /* slot 1: key 200 */
        slot=production_lookup(64,2,2,0x85,0,NULL);assert(slot==2);
        /* Same offset, different size/format/cube must never take the hint. */
        s_vp_tex_hint[vp_tex_hint_hash(64,4,2,0x85,0)]=3;
        slot=production_lookup(64,4,2,0x85,0,NULL);assert(slot==-100);
        s_vp_tex_hint[vp_tex_hint_hash(64,2,2,0x85,1)]=3;
        slot=production_lookup(64,2,2,0x85,1,NULL);assert(slot==-100);
        /* ...nor a different volume depth. The hint hash has no depth, so a
         * 3D lookup finds the 2D slot's hint; trusting it would skip the scan
         * and miss the depth-4 slot that does exist (a duplicate upload). */
        s_d3d.vp_tex[3]=s_d3d.vp_tex[2];s_d3d.vp_tex[3].depth=4;
        s_vp_tex_hint[vp_tex_hint_hash(64,2,2,0x85,0)]=3;
        slot=production_lookup_depth(64,2,2,0x85,0,4,NULL);assert(slot==3);
        s_d3d.vp_tex[3]=(VPTexSlot){0};
        s_d3d.vp_tex[1].key=64;s_d3d.vp_tex[2]=(VPTexSlot){0};
        memset(s_vp_tex_hint,0,sizeof(s_vp_tex_hint));
        puts("hint cases pass");
    }
    /* Two resources share the declared key but expose different uploaded
     * levels. A stale single-level hint must fall back to the chained slot.
     * Keep declared mips equal to isolate the uploaded-level discriminator. */
    memset(s_d3d.vp_tex,0,sizeof(s_d3d.vp_tex));
    s_d3d.vp_tex_capacity=2;
    s_d3d.vp_tex[0]=(VPTexSlot){.res=(void*)1,.key=64,.w=2,.h=2,.fmt=0x85,.mips=2,.used=1};
    s_d3d.vp_tex[1]=s_d3d.vp_tex[0];s_d3d.vp_tex[1].levels=2;
    s_vp_tex_hint[vp_tex_hint_hash(64,2,2,0x85,0)]=1;
    slot=production_lookup_levels(64,2,2,0x85,0,1,2,NULL);assert(slot==1);
    /* A correct chained hint must agree with a verification scan that skips
     * the earlier single-level slot. Zero stored levels normalize to one. */
    s_vp_tex_hint[vp_tex_hint_hash(64,2,2,0x85,0)]=2;
    slot=production_lookup_levels(64,2,2,0x85,0,1,2,NULL);assert(slot==1);
    s_d3d.vp_tex[0].mips=1;
    slot=production_lookup_levels(64,2,2,0x85,0,1,1,NULL);assert(slot==0);
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
        end = '    rsx_texture_profile_lookup_end(profile, s_d3d.vp_tex_capacity, RSX_TEX_MISS);'
        stop = body.index(end) + len(end)
        fixture = SOURCE.replace('@LOOKUP@', body[start:stop])
        fixture = fixture.replace('@CHECKSUM@', function('static u32 tex_csum('))
        fixture = fixture.replace('@PROFILE_CHECKSUM@', function('static u32 texture_profile_csum('))
        fixture=fixture.replace('@RETENTION@',function('static int texture_retention_on(void)\n{')).replace('@SOURCE_CHECKSUM@',function('static u64 texture_source_csum('))
        hint_start = backend.index('#define VP_TEX_HINTS')
        hint_end = backend.index('\n}\n', backend.index('static int vp_tex_hint_on(void)')) + 3
        fixture = fixture.replace('@HINT@', backend[hint_start:hint_end])
        source.write_text(fixture)
        binary = directory / ('profile.exe' if os.name == 'nt' else 'profile')
        include = str(VIDEO)
        if 'clang-cl' in Path(compiler).name.lower() or Path(compiler).name.lower() == 'cl.exe':
            command = [compiler, '/nologo', '/TC', '/O2', '/UNDEBUG', '/I', include, str(source), str(VIDEO/'rsx_texture_layout.c'), '/I', str(VIDEO.parents[1]/'include'), '/Fe:' + str(binary)]
        else:
            command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-I', include, str(source),str(VIDEO/'rsx_texture_layout.c'),'-I',str(VIDEO.parents[1]/'include'), '-o', str(binary)]
        subprocess.run(command, cwd=directory, check=True)
        environment = os.environ.copy()
        environment.pop('TEX_NOCACHE', None)
        environment.pop('RSX_TEX_HINT', None)
        environment.pop('RSX_TEX_HINT_VERIFY', None)
        for mode in ('0','1'):
            hinted = subprocess.run([str(binary)], cwd=directory, env=dict(environment, RSX_TEX_HINT_VERIFY='1', RSX_TEXTURE_RETENTION=mode), capture_output=True, text=True)
            assert hinted.returncode == 0 and 'hint cases pass' in hinted.stdout and 'MISMATCH' not in hinted.stderr, hinted.stdout + hinted.stderr
            subprocess.run([str(binary)], cwd=directory, env=dict(environment, RSX_TEX_HINT='0', RSX_TEXTURE_RETENTION=mode), check=True)
        # Each key comparison must reject a different uploaded level count.
        verified = ('            if (c->res && c->key == key_off && c->w == w && c->h == h && c->fmt == fmt\n'
                    '                && c->cube == cube && (c->depth ? c->depth : 1u) == depth\n'
                    '                && (!retention || c->mips == mips)\n'
                    '                && (c->levels ? c->levels : 1u) == levels) hinted = (int)(hs - 1u);')
        no_depth = verified.replace(' && (c->depth ? c->depth : 1u) == depth', '')
        no_levels = verified.replace('\n                && (c->levels ? c->levels : 1u) == levels', '')
        scan_levels = '\n            && (c->levels ? c->levels : 1u) == levels'
        verify_levels = '\n                  && (c->levels ? c->levels : 1u) == levels'
        mutants = {
            'unverified-hint': (verified, '            (void)c; hinted = (int)(hs - 1u);', '1'),
            'hint-ignores-depth': (verified, no_depth, '1'),
            'hint-ignores-levels': (verified, no_levels, '1'),
            'scan-ignores-levels': (scan_levels, '', '0'),
            'verification-ignores-levels': (verify_levels, '', '1'),
        }
        for name, (before, after, hint_mode) in mutants.items():
            assert fixture.count(before) == 1, name
            mutant = directory / f'mutant-{name}.c'
            mutant.write_text(fixture.replace(before, after))
            mbinary = directory / (f'mutant-{name}.exe' if os.name == 'nt' else f'mutant-{name}')
            mcommand = [str(mutant) if x == str(source) else x for x in command]
            mcommand = [('/Fe:' + str(mbinary)) if x.startswith('/Fe:') else (str(mbinary) if x == str(binary) else x) for x in mcommand]
            subprocess.run(mcommand, cwd=directory, check=True)
            bad = subprocess.run([str(mbinary)], cwd=directory,
                                 env=dict(environment, RSX_TEX_HINT=hint_mode,
                                          RSX_TEX_HINT_VERIFY='1', RSX_TEXTURE_RETENTION='1'),
                                 capture_output=True, text=True)
            assert bad.returncode != 0 or 'MISMATCH' in bad.stderr, f'{name} mutant passed'
            print(f'mutant {name} rejected')
    print('PASS: actual cache lookup/checksum with verified hints (and RSX_TEX_HINT=0) under reference and retention, disjoint phase accounting, disabled clock and visible failure')
