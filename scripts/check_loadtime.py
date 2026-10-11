"""Check load tracing/report regressions with authored fixtures, no game inputs."""
import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from project import ROOT, build_environment

FIXTURE = r'''#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include "ps3emu/loadtime_trace.h"
static HANDLE gate;
static volatile LONG bad_clock;
static DWORD WINAPI worker(void* unused) {
 (void)unused; WaitForSingleObject(gate,INFINITE);
 for(int i=0;i<40;i++) {
  if(loadtime_on() && loadtime_us()>60000000) InterlockedIncrement(&bad_clock);
  loadtime_event_path("fixture","dur_us=1","asset with spaces/quote\"=test.rpk");
 }
 return 0;
}
int main(int argc,char** argv) {
 (void)argv;
 if(argc>1) { _putenv_s("LOADTIME_TRACE","0");loadtime_event("disabled","");return loadtime_on()!=0; }
 HANDLE threads[8];gate=CreateEventA(NULL,TRUE,FALSE,NULL);
 for(int i=0;i<8;i++) { threads[i]=CreateThread(NULL,0,worker,NULL,0,NULL);if(!threads[i])return 2; }
 SetEvent(gate);WaitForMultipleObjects(8,threads,TRUE,INFINITE);
 for(int i=0;i<8;i++)CloseHandle(threads[i]);CloseHandle(gate);
 return bad_clock ? 3 : 0;
}
'''


def report_checks(out):
    spec=importlib.util.spec_from_file_location('report',ROOT/'scripts/analysis/loadtime_report.py')
    report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)
    def event(t,k,d='',**extra):
        return dict(t_us=t,us=t,kind=k,detail=d,_detail=report.parse_detail(d),tid=1,**extra)
    events=[event(0,'trace_start'),event(1,'fs_open','fd=3',path='first.rpk'),
            event(10,'fs_read','fd=3 got=100 dur_us=1'),event(11,'fs_close','fd=3'),
            event(12,'fs_open','fd=3',path='second with spaces/"=.rpk'),
            event(13,'fs_read','fd=3 got=50 dur_us=1'),event(14,'boot','stage=elf_loaded'),
            event(15,'boot','stage=services_ready'),event(16,'boot','stage=entry_dispatch'),
            event(20,'wait_event_begin','start_us=20 timeout=1000000'),
            event(30,'first_present'),event(50,'wait_event_end','start_us=20 end_us=50 dur_us=30 timeout=1000000 result=0')]
    names=[x[0] for x in report.boundaries(out,events)[1]]
    assert all(x in names for x in ('elf','services','entry','first-present'))
    assert report.wait_union(events,0,25)==5
    assert report.wait_union([event(5,'wait_event','timeout=1000000')],0,100)==0
    totals=report.stage_totals(events,10,51)
    assert totals[2]==150 and set(totals[3])=={(100,'first.rpk'),(50,'second with spaces/"=.rpk')}
    (out/'frames.csv').write_text('frame,t_ms,dt_ms,flips_since_prev_present\n0,123456,1,1\n')
    assert report.boundaries(out,[event(0,'trace_start')])[1]==[('trace-start',0,'observer anchor; VM allocation may precede it')]
    (out/'loadtime.jsonl').write_text(json.dumps({'t_us':0,'kind':'trace_start','detail':''})+'\n{malformed\n')
    try: report.load_events(out)
    except ValueError as exc: assert ':2:' in str(exc)
    else: raise AssertionError('Malformed trace silently accepted')
    (out/'loadtime.jsonl').write_text(json.dumps({'t_us':0,'kind':'trace_start','detail':''})+'\n')
    subprocess.run([os.sys.executable,ROOT/'scripts/analysis/loadtime_report.py',out],check=True,stdout=subprocess.DEVNULL)


def main():
    out=ROOT/'temp/validation'/('loadtime-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
    out.mkdir(parents=True)
    report_checks(out)
    source=out/'fixture.c';source.write_text(FIXTURE)
    env=build_environment();exe=out/'fixture.exe';log=out/'compile.log'
    with log.open('wb') as stream:
        result=subprocess.run([env['MV_CLANG'],'/std:c17','/MDd','/DLT_MAX_EVENTS=32',
            '/I'+str(ROOT/'vendor/ps3recomp/include'),source,ROOT/'vendor/ps3recomp/runtime/diag/loadtime_trace.c','/Fe'+str(exe)],
            cwd=out,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=30)
    print('Compiler diagnostics:',log,flush=True)
    if result.returncode: raise SystemExit(log.read_text(errors='replace'))
    env['LOADTIME_TRACE']='1';env['LOADTIME_TRACE_FILE']=str(out/'threaded.jsonl')
    disabled=subprocess.run([exe,'disabled'],cwd=out,env=env,capture_output=True,timeout=15)
    assert disabled.returncode==0 and not disabled.stdout and not disabled.stderr and not (out/'threaded.jsonl').exists()
    result=subprocess.run([exe],cwd=out,env=env,capture_output=True,timeout=15)
    (out/'fixture.err').write_bytes(result.stderr)
    assert result.returncode==0
    records=[json.loads(x) for x in (out/'threaded.jsonl').read_text().splitlines()]
    assert len(records)==34 and records[0]['kind']=='trace_start' and records[-1]['kind']=='trace_truncated'
    assert sum(r['kind']=='fixture' for r in records)==32
    assert all(r.get('path')=='asset with spaces/quote"=test.rpk' for r in records[1:-1])
    assert [r['t_us'] for r in records]==sorted(r['t_us'] for r in records)
    assert b'event budget reached' in result.stderr
    print('PASS: concurrent initialization/cap, path escaping, measured waits, fd lifetimes, boot/first-present clock and strict/zero-span reports')


if __name__=='__main__': main()
