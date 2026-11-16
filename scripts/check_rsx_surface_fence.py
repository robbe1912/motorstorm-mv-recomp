#!/usr/bin/env python3
"""Actual CPU-surface wait and explicit mock outcomes; optional real headless GPU."""
import argparse,csv,hashlib,json,os,re,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/'vendor/ps3recomp'
if os.name=='nt':
 from project import build_environment
 os.environ.update(build_environment())
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--gpu',action='store_true');ap.add_argument('--historical-surface',type=Path);args=ap.parse_args()
out=ROOT/'temp/checks'/('surface-fence-'+str(time.time_ns()));out.mkdir(parents=True)
source=VENDOR/'libs/video/rsx_cpu_surface.inc';text=source.read_text()
def function(text):return re.search(r'static void cpu_surface_fence_wait\(void\) \{.*?^\}',text,re.S|re.M).group()
body=function(text);record={'qualification':__doc__,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'commands':[]}
def run(command):
 p=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=60);record['commands'].append(dict(command=list(map(str,command)),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));(out/'result.json').write_text(json.dumps(record,indent=2));return p
def build(body,tag,gpu=False):
 template=ROOT/'scripts/fixtures'/('rsx_surface_fence_gpu.c' if gpu else 'rsx_surface_fence_cpu.c');record.setdefault('fixture_sha256',{})[str(template.relative_to(ROOT))]=hashlib.sha256(template.read_bytes()).hexdigest();c=out/(tag+'.c');c.write_text(template.read_text().replace('// WAIT_FUNCTION',body));exe=out/(tag+('.exe' if os.name=='nt' else ''));compiler=os.environ.get('MV_CLANG') or shutil.which('clang-cl' if os.name=='nt' else 'cc');assert compiler
 cmd=[compiler,'/nologo','/TC','/std:c17','/O2','/MDd','/UNDEBUG',c,'/Fo'+str(out/(tag+'.obj')),'/Fe'+str(exe)] if os.name=='nt' else [compiler,'-std=c17','-O2','-UNDEBUG',c,'-o',exe]
 if gpu:cmd+=['/link','d3d12.lib','dxgi.lib','dxguid.lib']
 assert run(cmd).returncode==0,out/'result.json';record.setdefault('binary_sha256',{})[tag]=hashlib.sha256(exe.read_bytes()).hexdigest();return exe
def controls(exe,tag):
 for mode in range(9):
  p=run([exe,str(mode)]);assert p.returncode==(0 if mode<2 else 9),(tag,mode,out/'result.json')
  errors={2:'GPU fence removed sentinel',3:'GetDeviceRemovedReason',4:'Signal',5:'SetEventOnCompletion',6:'GPU fence wait',7:'GPU fence deadline',8:'GPU fence counter overflow'}
  if mode in errors:assert errors[mode] in p.stderr,(tag,mode,out/'result.json')
controls(build(body,'production'),'production')
for tag,mutant in {'single-wake':body.replace('for(;;)','for(int once=0;once<1;once++)'),'ignore-removed-sentinel':body.replace('if(completed==UINT64_MAX)cpu_surface_fail("GPU fence removed sentinel",E_FAIL);',''),'refresh-deadline':body.replace('for(;;) {','for(;;) { deadline=GetTickCount64()+30000;')}.items():
 assert mutant!=body
 exe=build(mutant,tag)
 try:controls(exe,tag)
 except AssertionError:pass
 else:raise AssertionError('Mutant accepted: '+tag)
if args.gpu:
 assert os.name=='nt'
 tasks=subprocess.check_output(['tasklist','/FI','IMAGENAME eq ms1_recomp.exe','/FO','CSV','/NH'],text=True);assert not any(row and row[0].lower()=='ms1_recomp.exe' for row in csv.reader(tasks.splitlines()))
 exe=build(body,'hardware',True);p=run([exe]);assert p.returncode==0,out/'result.json';print(p.stdout.strip())
 if args.historical_surface:
  old=function(args.historical_surface.read_text());assert old!=body;record['historical_sha256']=hashlib.sha256(args.historical_surface.read_bytes()).hexdigest();exe=build(old,'historical-hardware',True);p=run([exe]);assert p.returncode==7 and 'target_complete' in p.stderr,out/'result.json';print('PASS actual historical CPU-surface stale-event RED')
record['passed']=True;(out/'result.json').write_text(json.dumps(record,indent=2));print('PASS CPU-surface fence outcomes and three mutants;',out)
