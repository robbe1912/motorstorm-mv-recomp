"""Check actual fragment decompilation using authored MAD instruction fixtures."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = r'''
#include <stdio.h>
#include <string.h>
#include "rsx_fp_decompiler.h"
static void word(unsigned char *b,unsigned v){unsigned s=(v<<16)|(v>>16);b[0]=s>>24;b[1]=s>>16;b[2]=s>>8;b[3]=s;}
static int check(unsigned flags,const char *expected){
 unsigned char code[32]={0};char text[65536];float constants[16]={0};u32 count=0;
 word(code,(4u<<24)|(15u<<9)|1u);word(code+4,(0xe4u<<9)|(7u<<18));word(code+8,0xe4u<<9);word(code+12,2u|(0xe4u<<9)|flags);
 for(unsigned i=0;i<4;i++)word(code+16+i*4,0xbe800000u);
 int n=rsx_fp_decompile_buffered_ex(code,sizeof code,0x40,0,text,sizeof text,&count,constants);
 if(n!=1||count!=1||!strstr(text,expected)){fprintf(stderr,"SRC2 modifier missing or wrong: expected %s; instructions=%d constants=%u\n",expected,n,count);return 1;}return 0;
}
int main(void){
 if(check(1u<<18,"abs((fp_constants[0]).xyzw)"))return 1;
 if(check((1u<<18)|(1u<<17),"-(abs((fp_constants[0]).xyzw))"))return 2;
 if(check(0,"+ ((fp_constants[0]).xyzw)"))return 3;
 puts("PASS actual MAD decompiler: SRC2 absolute, negation-after-absolute, plain operand");return 0;
}
'''

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, default=ROOT / 'vendor/ps3recomp/libs/video/rsx_fp_decompiler.c')
    args = ap.parse_args()
    source = args.source.resolve()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'temp/checks' / ('rsx-fp-source-' + stamp)
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
    inputs = [source, ROOT / 'vendor/ps3recomp/libs/video/rsx_fp_decompiler.h',
              ROOT / 'vendor/ps3recomp/libs/video/rsx_commands.h']
    result = dict(source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
                  build_returncode=build.returncode, game_inputs=False,
                  production_function='rsx_fp_decompile_buffered_ex', authored_instruction_fixture=True)
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
