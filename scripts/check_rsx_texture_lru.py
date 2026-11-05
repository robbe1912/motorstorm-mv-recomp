"""Texture slot replacement (#155): compile the production vp_tex_victim with
authored pools and check the miss policy -- empty slot first, cold same-shape
slot next, then the coldest slot, growth while a recently bound texture would
otherwise be evicted, and a bounded pool. A frame whose working set spans
several record batches must stop evicting itself; mutants of the policy fail."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / 'vendor/ps3recomp/libs/video'
if not VIDEO.exists():
    VIDEO = ROOT / 'libs/video'

SOURCE = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32; typedef uint64_t u64;
typedef struct {void*res;void*up;u32 off,w,h,fmt,dxgi,csum;int cube;u32 key;int used;u64 last_frame;} VPTexSlot;
@VICTIM@
static VPTexSlot P[64];
static void slot(int i,int res,u32 w,u32 h,u32 fmt,int cube,int used,u64 last){
    P[i]=(VPTexSlot){0};P[i].res=res?(void*)(uintptr_t)(i+1):NULL;P[i].w=w;P[i].h=h;P[i].fmt=fmt;
    P[i].cube=cube;P[i].used=used;P[i].last_frame=last;
}
/* Frame model: `textures` distinct same-shape textures bound in order across
 * `batches` record batches per frame; `used` is cleared at each batch, as
 * render_frame does. Returns misses over `frames` frames after warm-up. */
static unsigned long long simulate(unsigned capacity,unsigned max_slots,unsigned textures,unsigned batches,unsigned frames,int policy_first_unused){
    static VPTexSlot pool[4096];static u32 key_at[4096];
    memset(pool,0,sizeof pool);memset(key_at,0,sizeof key_at);
    vp_tex_cache_stats st={0};unsigned long long misses=0;unsigned cap=capacity;
    for(unsigned f=0;f<frames;f++){
        for(unsigned b=0;b<batches;b++){
            for(unsigned i=0;i<cap;i++)pool[i].used=0;
            for(unsigned t=b*textures/batches;t<(b+1)*textures/batches;t++){
                u32 key=t+1;int hit=-1;
                for(unsigned i=0;i<cap;i++)if(pool[i].res&&key_at[i]==key){hit=(int)i;break;}
                if(hit<0){
                    if(f>=2)misses++;
                    int v=-1;
                    if(policy_first_unused){for(unsigned i=0;i<cap;i++)if(!pool[i].used){v=(int)i;break;}}
                    else v=vp_tex_victim(pool,cap,f,256,256,0x86,0,max_slots,&st);
                    if(v<0){v=(int)cap;cap=cap*2>4096?4096:cap*2;}
                    pool[v].res=(void*)1;pool[v].w=256;pool[v].h=256;pool[v].fmt=0x86;key_at[v]=key;hit=v;
                }
                pool[hit].used=1;pool[hit].last_frame=f+1;
            }
        }
    }
    return misses;
}
int main(void){
    (void)vp_tex_lru_on;(void)vp_tex_slots_max;(void)s_vp_tex_stats;
    vp_tex_cache_stats st={0};
    /* 1. Empty slot wins over any cold occupied slot. */
    slot(0,1,64,64,0x86,0,0,1);slot(1,0,0,0,0,0,0,0);slot(2,1,64,64,0x86,0,0,1);
    assert(vp_tex_victim(P,3,10,64,64,0x86,0,1024,&st)==1&&st.empty==1);
    /* 2. Cold same-shape slot beats an older cold slot of another shape. */
    slot(0,1,128,128,0x86,0,0,1);slot(1,1,64,64,0x86,0,0,5);slot(2,1,64,64,0x86,0,1,1);
    assert(vp_tex_victim(P,3,10,64,64,0x86,0,1024,&st)==1&&st.cold_same==1);
    /* Same size, other format or cube-ness is not the same shape. */
    slot(1,1,64,64,0x88,0,0,5);
    assert(vp_tex_victim(P,3,10,64,64,0x86,0,1024,&st)==0&&st.cold_other==1);
    slot(1,1,64,64,0x86,1,0,5);
    assert(vp_tex_victim(P,3,10,64,64,0x86,0,1024,&st)==0&&st.cold_other==2);
    /* 3. Slots bound this frame (last=frame+1) or the previous one (last=frame)
     *    are recent: grow instead while under the bound. */
    slot(0,1,64,64,0x86,0,0,10);slot(1,1,64,64,0x86,0,0,11);slot(2,1,64,64,0x86,0,1,2);
    assert(vp_tex_victim(P,3,10,64,64,0x86,0,1024,&st)==-1&&st.grow==1);
    /* last=9 was bound two frames ago: cold. */
    slot(0,1,64,64,0x86,0,0,9);
    assert(vp_tex_victim(P,3,10,64,64,0x86,0,1024,&st)==0);
    /* 4. At the bound, evict the least recently bound unused slot. */
    slot(0,1,64,64,0x86,0,0,11);slot(1,1,32,32,0x86,0,0,10);
    assert(vp_tex_victim(P,3,10,64,64,0x86,0,3,&st)==1&&st.evict_recent==1);
    /* 5. Never a slot in use by this batch; all in use -> grow even at the bound. */
    slot(0,1,64,64,0x86,0,1,1);slot(1,1,64,64,0x86,0,1,1);slot(2,1,64,64,0x86,0,1,1);
    assert(vp_tex_victim(P,3,10,64,64,0x86,0,3,&st)==-1);
    for(int i=0;i<3;i++)P[i].used=(i!=2);
    assert(vp_tex_victim(P,3,10,64,64,0x86,0,3,&st)==2);
    /* 6. A frame of 300 textures over 3 batches, pool starting at 192: the
     *    first-unused policy misses on most binds every frame; the new policy
     *    grows once and then never misses. */
    unsigned long long old_misses=simulate(192,1024,300,3,12,1);
    unsigned long long new_misses=simulate(192,1024,300,3,12,0);
    printf("simulated misses over 10 frames: first-unused %llu, lru %llu\n",old_misses,new_misses);
    assert(old_misses>=1000&&new_misses==0);
    /* 7. Bounded: a working set larger than the bound still misses, but only
     *    the textures that do not fit (no unbounded growth). */
    unsigned long long bounded=simulate(64,128,300,3,12,0);
    printf("working set 300 over a 128-slot bound: %llu misses over 10 frames\n",bounded);
    assert(bounded>0);
    puts("lru cases pass");
    return 0;
}
'''

def build(directory, text, name, compiler, strict=True):
    source = directory / (name + '.c')
    source.write_text(text)
    binary = directory / (name + ('.exe' if os.name == 'nt' else ''))
    if 'clang-cl' in Path(compiler).name.lower() or Path(compiler).name.lower() == 'cl.exe':
        command = [compiler, '/nologo', '/TC', '/O2', '/UNDEBUG', str(source), '/Fe:' + str(binary)]
    else:
        command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', *(['-Werror'] if strict else []), str(source), '-o', str(binary)]
    subprocess.run(command, cwd=directory, check=True)
    return binary

if __name__ == '__main__':
    if os.name == 'nt' and 'MV_CLANG' not in os.environ and (ROOT / 'scripts/project.py').exists():
        from project import build_environment
        os.environ.update(build_environment())
    compiler = os.environ.get('MV_CLANG') or os.environ.get('CC') or shutil.which('clang-cl' if os.name == 'nt' else 'cc')
    if not compiler:
        raise SystemExit('C compiler required')
    backend = (VIDEO / 'rsx_d3d12_backend.c').read_text()
    start = backend.index('typedef struct {\n    unsigned long long misses, empty,')
    end = backend.index('static void vp_tex_cache_log(void)')
    victim = backend[start:end]
    # The production hook: the victim replaces the first-unused slot on a miss.
    hook = ('    if (slot < 0 && vp_tex_lru_on())\n'
            '        freeslot = vp_tex_victim(s_d3d.vp_tex, s_d3d.vp_tex_capacity, s_d3d.frame_count,\n')
    assert backend.count(hook) == 1, 'miss path no longer calls vp_tex_victim'
    assert 's_d3d.vp_tex[result].last_frame = s_d3d.frame_count + 1u;' in backend, 'binds no longer stamp last_frame'
    fixture = SOURCE.replace('@VICTIM@', victim)
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        binary = build(directory, fixture, 'lru', compiler)
        env = {k: v for k, v in os.environ.items() if k not in ('RSX_TEX_LRU', 'RSX_TEX_SLOTS_MAX')}
        r = subprocess.run([str(binary)], cwd=directory, env=env, capture_output=True, text=True)
        assert r.returncode == 0 and 'lru cases pass' in r.stdout, r.stdout + r.stderr
        print(r.stdout.strip())
        mutants = {
            'no-grow': ('    if (capacity < max_slots || lru < 0) { st->grow++; return -1; }',
                        '    if (lru < 0) { st->grow++; return -1; }'),
            'unbounded': ('    if (capacity < max_slots || lru < 0)', '    if (1)'),
            'newest-victim': ('if (lru < 0 || c->last_frame < pool[lru].last_frame) lru = (int)i;',
                              'if (lru < 0 || c->last_frame > pool[lru].last_frame) lru = (int)i;'),
            'no-shape-preference': ('    if (same >= 0 && VP_TEX_COLD(same)) { st->cold_same++; return same; }\n', ''),
            'used-evictable': ('        if (c->used) continue;\n', ''),
            'recent-is-cold': ('    #define VP_TEX_COLD(i) (pool[i].last_frame + 1u < frame + 1u)',
                               '    #define VP_TEX_COLD(i) (pool[i].last_frame < frame + 1u)'),
        }
        for name, (before, after) in mutants.items():
            assert fixture.count(before) == 1, name
            mb = build(directory, fixture.replace(before, after), 'mutant_' + re.sub(r'\W', '_', name), compiler, strict=False)
            bad = subprocess.run([str(mb)], cwd=directory, env=env, capture_output=True, text=True)
            assert bad.returncode != 0, f'mutant {name} passed'
            print(f'mutant {name} rejected')
    print('PASS: texture slot replacement keeps a multi-batch working set, prefers cold same-shape slots, grows within its bound, and mutants fail')
