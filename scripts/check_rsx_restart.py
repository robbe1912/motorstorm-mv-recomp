"""Game-free contract for the actual D3D12 indexed strip/fan upload helper.

Compile the production function with synthetic index/vertex adapters, not a
second implementation. Native command decoding and GPU pixels require the
separate runtime loop; this contract checks assembly and sentinel fetches.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
PREFIX = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;typedef uint64_t u64;typedef uint8_t u8;
typedef struct {float v[4];} VPSlot;
typedef struct {struct {int enabled;} vertex_attribs[16];u32 index_array_dma,begin_epoch,restart_index_enable,restart_index;} rsx_state;
#define MAX_VERTICES 4096
#define VP_VERT_STRIDE 256
static VPSlot buffer[4096*16];
static struct {void*vp_vb_mapped;u32 vp_vb_offset,vp_parity;} s_d3d={buffer,0,0};
uint8_t*vm_base=(uint8_t*)1;static const u32*indices;static unsigned markers_fetched;
static u32 read_guest_index(const rsx_state*s,u32 k){(void)s;return indices[k];}
static void read_vp_vertex(const rsx_state*s,u32 i,VPSlot*out){out[0].v[0]=(float)i;if(s->restart_index_enable&&((s->index_array_dma>>4)!=1||s->restart_index<=65535)&&i==s->restart_index)markers_fetched++;}
'''
CHECK = r'''
int main(void){rsx_state s={0};s.vertex_attribs[0].enabled=1;s.index_array_dma=16;s.begin_epoch=1;s.restart_index_enable=1;s.restart_index=65535;
u32 input[]={0,1,2,65535,3,4,5};indices=input;u32 n=upload_strip_vp_indexed(&s,0,7,0);printf("enabled strip emitted=%u marker_fetches=%u\n",n,markers_fetched);if(n!=6||markers_fetched)return 1;
s.begin_epoch++;s_d3d.vp_vb_offset=0;u32 split=upload_strip_vp_indexed(&s,0,2,0);split+=upload_strip_vp_indexed(&s,2,2,0);split+=upload_strip_vp_indexed(&s,4,3,0);if(split!=6||markers_fetched)return 2;
s.begin_epoch++;s_d3d.vp_vb_offset=0;s.restart_index_enable=0;if(upload_strip_vp_indexed(&s,0,7,0)!=15)return 3;
s.begin_epoch++;s_d3d.vp_vb_offset=0;s.restart_index_enable=1;s.restart_index=0xffffffff;if(upload_strip_vp_indexed(&s,0,7,0)!=15)return 4;
s.begin_epoch++;s_d3d.vp_vb_offset=0;s.index_array_dma=0;u32 wide[]={0,1,2,0xffffffff,3,4,5};indices=wide;if(upload_strip_vp_indexed(&s,0,7,0)!=6||markers_fetched)return 5;
s.begin_epoch++;s_d3d.vp_vb_offset=0;s.index_array_dma=16;s.restart_index=65535;indices=input;if(upload_strip_vp_indexed(&s,0,7,1)!=6)return 6;
s.begin_epoch++;s_d3d.vp_vb_offset=0;u32 plain[]={0,1,2,3};indices=plain;if(upload_strip_vp_indexed(&s,0,4,0)!=6)return 7;if(buffer[3*16].v[0]!=2||buffer[4*16].v[0]!=1)return 8;
puts("PASS real indexed upload: restart, split batches, disabled/width rules, fan, winding");return 0;}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, default=ROOT / 'vendor/ps3recomp/libs/video/rsx_d3d12_backend.c')
    args = ap.parse_args()
    source = args.source.resolve()
    text = source.read_text(encoding="utf-8")
    a = text.index('static u32 upload_strip_vp_indexed(')
    b = text.index('\nstatic void d3d12_draw_arrays(', a)
    body = text[a:b]
    header = source.with_name('rsx_index_strip.h')
    include = '#include "' + header.as_posix() + '"\n' if 'rsx_index_strip_push' in body else ''
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('rsx-restart-' + stamp)
    out.mkdir(parents=True)
    c, exe = out / 'check.c', out / ('check.exe' if os.name == 'nt' else 'check')
    prefix = PREFIX
    vertex_source = source.with_name('rsx_vertex_fetch.c')
    prepared = 'rsx_vertex_fetch_prepare' in body
    if prepared:
        vertex_header = source.with_name('rsx_vertex_fetch.h')
        prefix = prefix.replace('#include <string.h>', '#include <string.h>\n#include <stdlib.h>\n#include "' + vertex_header.as_posix() + '"')
        prefix = prefix.replace('typedef struct {float v[4];} VPSlot;', 'typedef rsx_vertex_value VPSlot;')
        prefix = prefix.replace('typedef struct {struct {int enabled;} vertex_attribs[16];u32 index_array_dma,begin_epoch,restart_index_enable,restart_index;} rsx_state;', '')
        prefix = prefix.replace('const rsx_state*s,u32 i,VPSlot*out', 'const rsx_state*s,const rsx_vertex_fetch_batch*b,u32 i,VPSlot*out')
        prefix = prefix.replace('out[0].v[0]=(float)i;', 'if(b->state!=s)abort();out[0].v[0]=(float)i;')
        prefix += '\nu32 cellGcmResolveOffset(u32 o){(void)o;abort();}\nu32 cellGcmResolveLocated(int l,u32 o){(void)l;(void)o;abort();}\n'
    c.write_text(prefix + include + body + CHECK, encoding='utf-8')
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        cmd = [env['MV_CLANG'], '/nologo', str(c), '/Fe' + str(exe), '/Fo' + str(out) + os.sep]
    else:
        cmd = [env.get('CC', 'cc'), '-std=c11', '-o', str(exe), str(c)]
    if prepared:
        cmd += [str(vertex_source), ('/I' if os.name == 'nt' else '-I') + str(vertex_source.parents[2] / 'include')]
    with (out / 'build.log').open('wb') as log:
        build = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    inputs = [source] + ([header] if include else []) + ([vertex_source, vertex_header, source.with_name('rsx_commands.h')] if prepared else [])
    result = dict(source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
                  build_returncode=build.returncode, game_inputs=False,
                  production_function='upload_strip_vp_indexed', synthetic_adapters=True)
    if build.returncode == 0:
        with (out / 'run.log').open('wb') as log:
            run = subprocess.run([str(exe)], stdout=log, stderr=subprocess.STDOUT, timeout=30)
        result['run_returncode'] = run.returncode
        result['exe_sha256'] = hashlib.sha256(exe.read_bytes()).hexdigest()
        print((out / 'run.log').read_text())
    (out / 'result.json').write_text(json.dumps(result, indent=2))
    print('Evidence:', out)
    return build.returncode or result.get('run_returncode', 1)


if __name__ == '__main__':
    sys.exit(main())
