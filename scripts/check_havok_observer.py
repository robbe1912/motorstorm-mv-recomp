"""Check the read-only Havok observer against synthetic host memory on Windows.

No game inputs, generated guest instructions or private keys are needed.
"""
import argparse
import datetime
from pathlib import Path
import subprocess
from project import ROOT, build_environment

FIXTURE = r'''#include <stdint.h>
#include <windows.h>
#include <stdio.h>
#include <string.h>
struct ppu_context { uint64_t gpr[32]; uint64_t lr; };
unsigned char* vm_base;
#include "@HEADER@"
extern "C" int loadtime_on(void) { return 0; }
extern "C" void loadtime_event(const char*,const char*) {}
int main() {
 vm_base=(unsigned char*)VirtualAlloc(nullptr,65536,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
 if(!vm_base)return 10;
 DWORD oldprot;VirtualProtect(vm_base+32768,4096,PAGE_NOACCESS,&oldprot);
 ppu_context ctx={};ctx.gpr[20]=0x1000;ctx.gpr[30]=0x2000;ctx.gpr[31]=0;
 vm_base[0x1023]=16;memcpy(vm_base,"EA-zero-observer",16);_putenv("CAP_HAVOK_DIR=unused");
 havok_record_raw_oct10(&ctx);
 if(havok_raw_length!=16 || memcmp(havok_raw_bytes,vm_base,16)){fputs("FAIL: readable EA-zero raw bytes were not cached\n",stderr);return 2;}
 unsigned char b[16];
 if(havok_probe_read(0xffffffff,b,2) || havok_probe_read(32768,b,1))return 3;
 puts("PASS: EA-zero raw capture; overflowing/unreadable spans rejected");return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--header', type=Path, default=ROOT/'src/diagnostics/havok_capture.h', help='Observer header; use a private old copy to demonstrate the original failure')
    args = parser.parse_args()
    header = args.header.resolve()
    if not header.is_file():
        parser.error('Observer header is missing')
    out = ROOT/'temp/validation'/('observer-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
    out.mkdir(parents=True)
    source = out/'observer.cpp'
    source.write_text(FIXTURE.replace('@HEADER@', header.as_posix()), encoding='utf-8')
    exe = out/'observer.exe'
    env = build_environment()
    log = out/'compile.log'
    with log.open('wb') as stream:
        result = subprocess.run([env['MV_CLANG'], '/std:c++17', '/I'+str(ROOT/'vendor/ps3recomp/include'), str(source), '/Fe'+str(exe)], cwd=out, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=30)
    print('Compiler diagnostics:', log, flush=True)
    if result.returncode:
        print(log.read_text(errors='replace'))
        raise SystemExit(result.returncode)
    result = subprocess.run([str(exe)], cwd=out, timeout=15)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
