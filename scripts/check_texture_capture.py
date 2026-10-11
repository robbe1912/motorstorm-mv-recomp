"""Check bounded run-local texture snapshots using authored host memory."""
import datetime
import json
import os
from pathlib import Path
import subprocess
from project import ROOT, build_environment

FIXTURE = r'''#include <windows.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "@HEADER@"
static uint8_t* memory;
static DWORD WINAPI worker(void* unused) {
 (void)unused;
 for(int i=0;i<20;i++)rsx_capture_texture(memory,1,0,8,8,0x86,1,0,64,16);
 return 0;
}
int main(int argc,char** argv) {
 if(argc<2)return 10;
 memory=VirtualAlloc(NULL,65536,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
 if(!memory)return 11;
 for(int i=0;i<65536;i++)memory[i]=(uint8_t)(i*17+3);
 uint8_t before[65536];memcpy(before,memory,65536);
 _putenv_s("TEX_RAWDBG_DIR",argv[1]);_putenv_s("TEX_RAWDBG","0");
 rsx_capture_texture(memory,1,0,8,8,0x86,1,0,64,16);
 if(tex_capture_attempts)return 12;
 _putenv_s("TEX_RAWDBG","1");
 rsx_capture_texture(memory,1,0,8,8,0x86,1,0,64,16);
 rsx_capture_texture(memory,1,0,8,8,0x86,1,0,64,16);
 if(tex_capture_count!=1)return 13;
 memory[0]^=1;
 rsx_capture_texture(memory,1,0,8,8,0x86,1,0,64,16);
 if(tex_capture_count!=2)return 14;
 HANDLE t[8];for(int i=0;i<8;i++)t[i]=CreateThread(NULL,0,worker,NULL,0,NULL);
 WaitForMultipleObjects(8,t,TRUE,INFINITE);for(int i=0;i<8;i++)CloseHandle(t[i]);
 if(tex_capture_count!=2)return 15;
 char existing[1024];snprintf(existing,sizeof existing,"%s/raw_%lu_2_00000000.bin",argv[1],GetCurrentProcessId());
 FILE* old=fopen(existing,"wb");if(!old)return 18;fwrite("sentinel",1,8,old);fclose(old);
 rsx_capture_texture(memory,99,0,8,8,0x86,1,0,64,16);
 memory[0]^=1;
 DWORD protection;VirtualProtect(memory+32768,4096,PAGE_NOACCESS,&protection);
 rsx_capture_texture(memory,1,32768,8,8,0x86,1,0,64,16);
 rsx_capture_texture(memory,1,0xFFFFFFFFu,8,8,0x86,1,0,64,16);
 VirtualProtect(memory+32768,4096,protection,&protection);
 for(unsigned i=0;i<100;i++)rsx_capture_texture(memory,10+i,0,8,8,0x86,1,0,64,16);
 if(tex_capture_attempts!=32 || tex_capture_count!=29)return 16;
 if(memcmp(before,memory,65536))return 17;
 return 0;
}
'''


def main():
    out=ROOT/'temp/validation'/('textures-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
    out.mkdir(parents=True);captures=out/'captures';captures.mkdir()
    source=out/'fixture.c';source.write_text(FIXTURE.replace('@HEADER@',(ROOT/'vendor/ps3recomp/libs/video/rsx_texture_capture.h').as_posix()))
    env=build_environment();exe=out/'fixture.exe';log=out/'compile.log'
    with log.open('wb') as stream:
        result=subprocess.run([env['MV_CLANG'],'/std:c17','/MDd',source,'/Fe'+str(exe)],cwd=out,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=30)
    print('Compiler diagnostics:',log,flush=True)
    if result.returncode:raise SystemExit(log.read_text(errors='replace'))
    result=subprocess.run([exe,str(captures)],cwd=out,capture_output=True,timeout=20)
    (out/'fixture.err').write_bytes(result.stderr)
    assert result.returncode==0, result.returncode
    meta=sorted(captures.glob('*.json'));raw=sorted(captures.glob('*.bin'))
    assert len(meta)==29 and len(raw)==30 and not list(out.glob('raw_*'))
    assert next(p for p in raw if '_2_00000000' in p.name).read_bytes()==b'sentinel'
    hashes=set()
    for p in meta:
        record=json.loads(p.read_text());data=p.with_suffix('.bin').read_bytes()
        assert len(data)==record['bytes']==64 and record['source']==0 and record['pitch']==16
        h=14695981039346656037
        for b in data:h=((h^b)*1099511628211)&0xffffffffffffffff
        assert record['fingerprint_fnv1a64']==f'{h:016X}'
        hashes.add(h)
    assert len(hashes)==2 and b'snapshot failed' in result.stderr and b'invalid/over-budget span' in result.stderr and b'capture budget reached' in result.stderr and b'create failed' in result.stderr
    print('PASS: disabled observer, EA-zero/change identity, concurrent dedupe, bounds/protection, explicit cap, run-local metadata and unchanged memory')


if __name__=='__main__':main()
