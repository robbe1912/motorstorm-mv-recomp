"""Check the read-only bike observer against synthetic host memory on Windows.

No game inputs, generated guest instructions or private keys are needed.
"""
import argparse
import datetime
from pathlib import Path
import subprocess
from project import ROOT, build_environment

FIXTURE = r'''#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <thread>
#include <vector>
#include <string>
struct ppu_context { uint64_t gpr[32]; uint64_t lr; };
unsigned char* vm_base;
static ULONGLONG fixture_tick;
static ULONGLONG fixture_clock() { return fixture_tick; }
#define GetTickCount64 fixture_clock
#include "@HEADER@"
static unsigned files(const std::string& dir,const char* stage) {
 WIN32_FIND_DATAA data; unsigned count=0;
 HANDLE h=FindFirstFileA((dir+"/*_"+stage+".txt").c_str(),&data);
 if(h==INVALID_HANDLE_VALUE)return 0;
 do {++count;} while(FindNextFileA(h,&data));FindClose(h);return count;
}
extern void other_tu_probe(ppu_context*);
int main(int argc,char** argv) {
 if(argc<3)return 10;
 ppu_context ctx={};
 if(!strcmp(argv[1],"disabled")) {
  _putenv_s("CAP_BIKE_DIR","");bike_probe_entry(&ctx,"vpfn");return 0;
 }
 std::string dir=argv[2],arm=dir+"/arm.txt";
 _putenv_s("CAP_BIKE_DIR",dir.c_str());_putenv_s("CAP_BIKE_ARM_FILE",arm.c_str());
 bike_probe_entry(&ctx,"vpfn");
 if(files(dir,"vpfn"))return 2;
 FILE* f=fopen(arm.c_str(),"wb");if(!f)return 11;fclose(f);
 vm_base=(unsigned char*)VirtualAlloc(nullptr,65536,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
 if(!vm_base)return 12;
 for(unsigned i=0;i<65536;++i)vm_base[i]=(unsigned char)i;
 memcpy(vm_base+256,"synthetic bike observer",24);
 ctx.gpr[4]=256;ctx.gpr[5]=512;
 unsigned char before[65536];memcpy(before,vm_base,sizeof before);ppu_context prior=ctx;
 fixture_tick=240001;
 for(int i=0;i<64;++i)bike_probe_entry(&ctx,"rsload");
 other_tu_probe(&ctx);
 bike_probe_entry(&ctx,"rsfind");bike_probe_entry(&ctx,"vpfn");
 if(files(dir,"rsload")!=64 || files(dir,"rsfind")!=1 || files(dir,"vpfn")!=1)return 3;
 std::vector<std::thread> threads;
 for(int i=0;i<8;++i)threads.emplace_back([&]{for(int j=0;j<40;++j)bike_probe_entry(&ctx,"vtload");});
 for(auto& t:threads)t.join();
 if(files(dir,"vtload")!=64)return 4;
 if(memcmp(&ctx,&prior,sizeof ctx) || memcmp(vm_base,before,sizeof before))return 5;
 puts("PASS: marker gating; independent stage quotas; concurrent cap; guest context/memory unchanged");return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--header', type=Path, default=ROOT/'src/diagnostics/bike_capture.h', help='Observer header; use a private old copy to demonstrate the original failure')
    args = parser.parse_args()
    header = args.header.resolve()
    if not header.is_file():
        parser.error('Observer header is missing')
    out = ROOT/'temp/validation'/('bike-observer-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
    out.mkdir(parents=True)
    source = out/'observer.cpp'
    source.write_text(FIXTURE.replace('@HEADER@', header.as_posix()), encoding='utf-8')
    helper = out/'other.cpp'
    helper.write_text('''#include <stdint.h>
#include <windows.h>
struct ppu_context { uint64_t gpr[32]; uint64_t lr; };
extern unsigned char* vm_base;
#include "''' + header.as_posix() + '''"
void other_tu_probe(ppu_context* ctx) { bike_probe_entry(ctx,"rsload"); }
''', encoding='utf-8')
    exe = out/'observer.exe'
    env = build_environment()
    log = out/'compile.log'
    with log.open('wb') as stream:
        result = subprocess.run([env['MV_CLANG'], '/std:c++17', str(source), str(helper), '/Fe'+str(exe)], cwd=out, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=30)
    print('Compiler diagnostics:', log, flush=True)
    if result.returncode:
        print(log.read_text(errors='replace'))
        raise SystemExit(result.returncode)
    capture = out/'capture'
    capture.mkdir()
    disabled = subprocess.run([str(exe), 'disabled', str(capture)], cwd=out, capture_output=True, timeout=15)
    if disabled.returncode or disabled.stdout or disabled.stderr:
        raise SystemExit('FAIL: disabled observer emitted output or failed')
    result = subprocess.run([str(exe), 'enabled', str(capture)], cwd=out, capture_output=True, timeout=15)
    (out/'observer.err').write_bytes(result.stderr)
    print(result.stdout.decode(errors='replace').strip())
    if result.returncode:
        print(result.stderr.decode(errors='replace'))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
