"""Game-free pixel-readback contract for the production vertex decompiler (Windows)."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
GENERATOR = r'''
#include "rsx_vp_decompiler.h"
#include <stdio.h>
#include <string.h>
static void word(unsigned char *b, unsigned v) {
    b[0]=v; b[1]=v>>8; b[2]=v>>16; b[3]=v>>24;
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    unsigned char code[16]={0}; char text[65536];
    /* Authored NV40 MOV o[0].xyzw, v[0].xyzw, END. No game bytes. */
    unsigned source=2u|(3u<<8)|(2u<<10)|(1u<<12);
    word(code, (63u<<15)|(1u<<30));
    word(code+4, (1u<<22)|((source>>9)&255u));
    word(code+8, (source&511u)<<23);
    word(code+12, 1u|(63u<<7)|(15u<<13));
    if (rsx_vp_decompile(code,sizeof(code),text,sizeof(text)) != 1) return 3;
    FILE *f=fopen(argv[1],"wb"); if (!f) return 4;
    size_t size=strlen(text), written=fwrite(text,1,size,f);
    int closed=fclose(f); return written!=size || closed!=0;
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path,
                    default=ROOT / 'vendor/ps3recomp/libs/video/rsx_vp_decompiler.c')
    ap.add_argument('--device', choices=('warp', 'hardware'), default='warp',
                    help='Explicit test device; WARP supports CI, hardware has no fallback')
    args = ap.parse_args()
    if os.name != 'nt':
        raise SystemExit('This D3D pixel-readback regression requires Windows')
    from project import build_environment
    env = build_environment()
    source = args.source.resolve()
    fixture = ROOT / 'scripts/fixtures/rsx_clip_gpu.cpp'
    out = ROOT / 'temp/checks' / ('rsx-clip-' + datetime.datetime.now(
        datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
    out.mkdir(parents=True)
    generator = out / 'generate.c'
    generator.write_text(GENERATOR, encoding='utf-8')
    generate_exe, gpu_exe = out / 'generate.exe', out / 'gpu.exe'
    include = ROOT / 'vendor/ps3recomp'
    common = [env['MV_CLANG'], '/nologo', '/D_CRT_SECURE_NO_WARNINGS']
    commands = [common + ['/I' + str(include / 'include'),
                         '/I' + str(include / 'libs/video'),
                         str(generator), str(source), '/Fe' + str(generate_exe)],
                common + ['/std:c++17', '/EHsc', str(fixture), '/Fe' + str(gpu_exe),
                          '/link', 'd3d11.lib', 'd3dcompiler.lib']]
    result = dict(game_inputs=False, authored_instruction_fixture=True,
                  production_function='rsx_vp_decompile', device=args.device,
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
                  cases=[])
    with (out / 'build.log').open('wb') as log:
        for command in commands:
            completed = subprocess.run(command, cwd=out, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, timeout=120)
            if completed.returncode:
                print((out / 'build.log').read_text(errors='replace'))
                return completed.returncode
    shader = out / 'authored.hlsl'
    subprocess.run([str(generate_exe), str(shader)], check=True, timeout=30)
    constants = [0.0] * 2048 + [1.0, 1.0, 0.5, 1.0, 0.0, 0.0, 0.5, 0.0]
    cb = out / 'constants.bin'
    cb.write_bytes(struct.pack('<2056f', *constants))
    for name, w, expected in [('behind', -1.0, '0'), ('visible', 1.0, '1')]:
        vertices = []
        for x, y in [(-0.5, -0.5), (0.5, -0.5), (0.0, 0.5)]:
            vertices.extend([x, y, 0.0, w] + [0.0] * 60)
        vb = out / (name + '.bin')
        vb.write_bytes(struct.pack('<192f', *vertices))
        completed = subprocess.run([str(gpu_exe), str(shader), str(vb), str(cb),
                                    expected, args.device], capture_output=True,
                                   timeout=30)
        output = completed.stdout + completed.stderr
        (out / (name + '.log')).write_bytes(output)
        print(output.decode(errors='replace').strip())
        result['cases'].append(dict(name=name, returncode=completed.returncode))
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('Evidence:', out)
    return int(any(case['returncode'] for case in result['cases']))


if __name__ == '__main__':
    sys.exit(main())
