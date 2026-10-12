"""Game-free contract for the actual RSX guest vertex-fetch component."""

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
FIXTURE = r'''#include "rsx_vertex_fetch.h"
#include <stdio.h>
#include <math.h>
#include <string.h>
static unsigned char memory[256];uint8_t*vm_base=memory;static int location=-1;
u32 cellGcmResolveLocated(int local,u32 offset){location=local;return offset;}
static void put(u32 offset,u32 word){memory[offset]=word>>24;memory[offset+1]=word>>16;memory[offset+2]=word>>8;memory[offset+3]=word;}
static u32 pack(int x,int y,int z){return ((u32)x&2047u)|(((u32)y&2047u)<<11)|(((u32)z&1023u)<<22);}
static int near(float a,float b){return isfinite(a)&&fabsf(a-b)<0.000001f;}
int main(void){rsx_state s={0};float o[4];for(int i=0;i<4;i++)s.vertex_data4f[2][i]=(float)(i+5);s.vertex_attribs[2].enabled=1;s.vertex_attribs[2].type=6;s.vertex_attribs[2].size=1;s.vertex_attribs[2].stride=26;s.vertex_attribs[2].offset=4;
put(56,pack(1023,-512,-256));rsx_fetch_attrib(&s,2,2,o);printf("CMP fetched %.9g,%.9g,%.9g,%.9g\n",o[0],o[1],o[2],o[3]);if(!near(o[0],1)||!near(o[1],-512.0f/1023)||!near(o[2],-256.0f/511)||o[3]!=1||location!=1)return 1;
s.vertex_attribs[2].offset=0x80000004;rsx_fetch_attrib(&s,2,2,o);if(location!=0||!near(o[0],1)||o[3]!=1)return 2;
s.vertex_attribs[2].frequency=2;rsx_fetch_attrib(&s,2,4,o);if(!near(o[1],-512.0f/1023))return 3;
s.frequency_divider_op=1u<<2;put(30,pack(-1,0,511));rsx_fetch_attrib(&s,2,3,o);if(!near(o[0],-1.0f/1023)||o[1]!=0||!near(o[2],1))return 4;
s.vertex_attribs[2].frequency=0;s.frequency_divider_op=0;put(56,pack(-1024,1023,-512));rsx_fetch_attrib(&s,2,2,o);if(!near(o[0],-1024.0f/1023)||!near(o[1],1)||!near(o[2],-512.0f/511))return 5;
s.vertex_attribs[2].enabled=0;rsx_fetch_attrib(&s,2,2,o);for(int i=0;i<4;i++)if(o[i]!=(float)(i+5))return 6;
s.vertex_attribs[2].enabled=1;s.vertex_attribs[2].type=2;s.vertex_attribs[2].size=1;put(56,0x3f800000);rsx_fetch_attrib(&s,2,2,o);if(o[0]!=1||o[1]!=6||o[2]!=7||o[3]!=8)return 7;
puts("PASS actual vertex fetch: packed XYZ/W, BE, signed fields, size-one, stride, MAIN/LOCAL, frequency, defaults, float control");return 0;}
'''

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, default=ROOT / 'vendor/ps3recomp/libs/video/rsx_vertex_fetch.c')
    args = ap.parse_args()
    source = args.source.resolve()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('rsx-vertex-' + stamp)
    out.mkdir(parents=True)
    c, exe = out / 'check.c', out / ('check.exe' if os.name == 'nt' else 'check')
    c.write_text(FIXTURE)
    env = os.environ.copy()
    if os.name == 'nt':
        from project import build_environment
        env = build_environment()
        cmd = [env['MV_CLANG'], '/nologo', '/I' + str(ROOT / 'vendor/ps3recomp/include'), '/I' + str(ROOT / 'vendor/ps3recomp/libs/video'), str(c), str(source), '/Fe' + str(exe), '/Fo' + str(out) + os.sep]
    else:
        cmd = [env.get('CC', 'cc'), '-std=c11', '-I' + str(ROOT / 'vendor/ps3recomp/include'), '-I' + str(ROOT / 'vendor/ps3recomp/libs/video'), '-o', str(exe), str(c), str(source), '-lm']
    with (out / 'build.log').open('wb') as log:
        build = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    inputs = [source, ROOT / 'vendor/ps3recomp/libs/video/rsx_vertex_fetch.h',
              ROOT / 'vendor/ps3recomp/libs/video/rsx_commands.h']
    result = dict(source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
                  build_returncode=build.returncode, game_inputs=False,
                  production_function='rsx_fetch_attrib', synthetic_adapters=True)
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
