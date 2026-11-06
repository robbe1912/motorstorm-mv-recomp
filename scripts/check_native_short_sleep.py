#!/usr/bin/env python3
"""Actual Windows wait implementation/caller with deterministic API outcomes.
CPU fixture uses authored Win32 behavior; optional real Windows timers/FLS prove
deadline and thread-exit resource behavior. Neither is game/FPS equivalence.
"""
from pathlib import Path
import subprocess,sys,os,time,json,hashlib,argparse,shutil
ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/"vendor/ps3recomp"
if os.name=="nt":
 from project import build_environment
 os.environ.update(build_environment())
if os.name!='nt':
 import resource
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def benchmark_usec(value):
 n=int(value)
 if not 1<=n<1000:raise argparse.ArgumentTypeError('benchmark request must be 1..999 microseconds')
 return n

ap=argparse.ArgumentParser();ap.add_argument('--real',action='store_true');ap.add_argument('--historical-timer');ap.add_argument('--benchmark',action='store_true');ap.add_argument('--benchmark-usec',type=benchmark_usec,default=500);args=ap.parse_args()
if args.benchmark and os.name=='nt':
 import csv
 processes=subprocess.run(['tasklist','/FI','IMAGENAME eq ms1_recomp.exe','/FO','CSV','/NH'],text=True,capture_output=True,check=True)
 assert not any(row and row[0].lower()=='ms1_recomp.exe' for row in csv.reader(processes.stdout.splitlines())),'Refusing operation benchmark while native game is live'
p=ROOT/'temp/checks'/f'native-short-sleep-{time.time_ns()}';p.mkdir(parents=True)
report={'qualification':__doc__,'commands':[],'hashes':{}}
def digest(x):return hashlib.sha256(x.read_bytes()).hexdigest()
def save():(p/'result.json').write_text(json.dumps(report,indent=2))
def run(cmd,env=None,check=True):
 r=subprocess.run(list(map(str,cmd)),cwd=p,env=env,text=True,capture_output=True,timeout=30);report['commands'].append({'argv':list(map(str,cmd)),'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr});save()
 if check and r.returncode:raise AssertionError(f'command failed; inspect {p}/result.json')
 return r
base=VENDOR/'runtime/platform';src=base/'native_short_sleep.c';fixture=ROOT/'scripts/fixtures/native_short_sleep.c';header=ROOT/'scripts/fixtures/short_sleep_fake_windows.h';timer=VENDOR/'runtime/syscalls/sys_timer.c'
for x in [src,fixture,header,timer,base/'native_short_sleep.h']:report['hashes'][str(x.relative_to(ROOT))]=digest(x)
text=timer.read_text();start=text.index('    if (usec > 0 && usec < 1000 && ps3_native_short_sleep(usec))');end=text.index('\n#else',start);branch=text[start:end]
assert 'else if (usec >= 1000)' in branch and 'else if (usec > 0)' in branch
cpu=p/'cpu';cpu.mkdir();shutil.copy2(header,cpu/'windows.h');shutil.copy2(header,cpu/header.name)
env=os.environ.copy();win=os.name=='nt';cc=env.get('MV_CLANG','clang-cl') if win else env.get('CC','cc')
def build(source,name,real=False):
 out=p/(name+('.exe' if win else ''));f=p/(name+'.c');f.write_text(source)
 inc=[base]+([] if real else [cpu])
 if win:cmd=[cc,'/nologo','/TC','/std:c17','/O2','/MDd','/UNDEBUG','/clang:-ffp-contract=off','/clang:-fno-strict-aliasing',*[f'/I{x}' for x in inc],str(f),f'/Fe{out}',f'/Fo{p/(name+".obj")}']
 else:cmd=[cc,'-std=c17','-O2','-UNDEBUG','-ffp-contract=off','-fno-strict-aliasing',*[f'-I{x}' for x in inc],str(f),'-lm','-o',out]
 run(cmd);return out
def cpu_source(body,caller=branch):return fixture.read_text().replace('#include "../native_short_sleep.c"',body).replace('/* ACTUAL_WINDOWS_BRANCH */',caller)
def fresh(value):
 e={k:v for k,v in env.items() if not k.startswith(('SPU_','SPURS_','PS3_NATIVE_SHORT_SLEEP'))}
 if value is not None:e['PS3_NATIVE_SHORT_SLEEP']=value
 return e
exe=build(cpu_source(src.read_text()),'state-machine')
for m in [0,1,2,3,4,5,6,7,8,9,10,11,13]:run([exe,m],fresh('1'))
for value in [None,'0']:run([exe,20],fresh(value))
for m,reason in [(14,'frequency'),(15,'frequency'),(16,'counter'),(17,'overflow'),(18,'backwards'),(21,'conversion overflow')]:
 r=run([exe,m],fresh('1'),False);assert r.returncode and reason in r.stderr
for value in ['', '2','true',' 1','1x']:
 r=run([exe,1],fresh(value),False);assert r.returncode and 'must be 0 or 1' in r.stderr
mutants={
 'early-completion':src.read_text().replace('/* Older/early notifications must re-block; never spin to the deadline. */','return 1;'),
 'lost-fp':src.read_text().replace('if (fesetenv(&environment)) short_fatal("restoring caller floating-point state");','(void)environment;').replace('_mm_setcsr(csr);','(void)csr;'),
 'lost-close':src.read_text().replace('if (timer && !CloseHandle((HANDLE)timer)) short_fatal("timer close at thread exit");','(void)timer;'),
 'omitted-caller':src.read_text(),
 'refreshed-deadline':src.read_text().replace('for (;;) {','for (;;) { deadline=short_now()+ticks;'),
 'rounded-down-deadline':src.read_text().replace('+(part%1000000!=0)','')}
for name,body in mutants.items():
 caller=branch.replace('ps3_native_short_sleep(usec)','0') if name=='omitted-caller' else branch
 bad=build(cpu_source(body,caller),name);mode=13 if name=='rounded-down-deadline' else 2 if name in ('early-completion','refreshed-deadline') else 1
 r=run([bad,mode],fresh('1'),False);assert r.returncode and ('Assertion' in r.stderr or 'assertion' in r.stderr),name
if args.historical_timer:
 old=Path(args.historical_timer).read_text();a=old.index('    if (usec >= 1000) {',old.index('int64_t sys_timer_usleep'));b=old.index('\n#else',a);historical=build(cpu_source(src.read_text(),old[a:b]),'actual-old-caller');r=run([historical,1],fresh('1'),False);assert r.returncode and ('assertion' in r.stderr.lower());report['historical_timer_sha256']=digest(Path(args.historical_timer))
if args.real:
 assert win,'--real requires actual Windows timers'
 real=ROOT/'scripts/fixtures/native_short_sleep_real.c';report['hashes'][str(real.relative_to(ROOT))]=digest(real)
 rsource=real.read_text().replace('#include "../native_short_sleep.c"',src.read_text());realexe=build(rsource,'real-windows',True);r=run([realexe],fresh('1'));assert '4 owned/FLS-exit-closed' in r.stdout;print(r.stdout.strip())
if args.benchmark:
 assert win,'Benchmark requires real Windows timers'
 import statistics
 bench=ROOT/'scripts/fixtures/benchmark_native_short_sleep.c';report['hashes'][str(bench.relative_to(ROOT))]=digest(bench)
 bexe=build(bench.read_text().replace('#include "../native_short_sleep.c"',src.read_text()).replace('/* ACTUAL_WINDOWS_BRANCH */',branch),'benchmark',True)
 report['benchmark']={'requested_us':args.benchmark_usec,'qualification':'Five alternating windows/mode, same executable and actual curated wait branch, pinned owned thread, 1000 requests/window at the recorded requested_us with 32 warmups; scheduled CPU may quantize to zero; thread cycles retained without converting them to CPU seconds. Unrelated host work uncontrolled; no whole-game/audio/FPS inference. Timer latency distribution retained along with CPU cost.','windows':[]}
 for mode in [0,1]*5:
  r=run([bexe,1000,args.benchmark_usec],fresh(str(mode)));row=json.loads(r.stdout);assert row['operations']==1000 and row['minimum_us']>=args.benchmark_usec and row['requested_us']==args.benchmark_usec;row['mode']=mode;report['benchmark']['windows'].append(row);save()
 for mode in [0,1]:
  rows=[r for r in report['benchmark']['windows'] if r['mode']==mode];summary={key:{'median':statistics.median(r[key] for r in rows),'range':[min(r[key] for r in rows),max(r[key] for r in rows)]} for key in ['wall_ms','cpu_ms','thread_cycles','median_us','maximum_us']};report['benchmark'][str(mode)]=summary;print('Mode',mode,summary)
report['result']='PASS';save();print('PASS production short wait/caller: reference/default/fallbacks, deadline/early wake/overflow/FP, cleanup and six rejected mutants;',p/'result.json')
