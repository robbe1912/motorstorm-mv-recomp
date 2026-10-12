"""One entry point for local setup, regeneration and native builds."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'vendor/ps3recomp/tools'

def config():
    p = ROOT / 'config/local.json'
    if not p.exists(): raise SystemExit('Run: python scripts/project.py setup --elf YOUR_ELF --disc YOUR_PS3_GAME --ffmpeg YOUR_FFMPEG')
    result=json.loads(p.read_text())
    return {k: (ROOT / v).resolve() for k,v in result.items()}

def run(args, **kwargs):
    subprocess.run([str(x) for x in args], cwd=ROOT, check=True, **kwargs)

def logged_run(args, log_path, **kwargs):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print('Diagnostics:', log_path, flush=True)
    with log_path.open('wb') as output:
        result = subprocess.run([str(x) for x in args], cwd=ROOT,
                                stdout=output, stderr=subprocess.STDOUT, **kwargs)
    if result.returncode:
        # Preserve the entire log; show a bounded tail for immediate diagnosis.
        with log_path.open('rb') as source:
            source.seek(max(0, log_path.stat().st_size - 8000))
            print(source.read().decode('utf-8', errors='replace'))
        raise SystemExit(f'Build failed ({result.returncode}); full log: {log_path}')

def build_environment():
    env=dict(os.environ)
    if os.name != 'nt': return env
    vswhere=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
    install=subprocess.check_output([str(vswhere),'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip()
    if not install: raise SystemExit('Visual Studio C++ build tools are required')
    vcvars=Path(install)/'VC/Auxiliary/Build/vcvars64.bat'
    task=ROOT/'temp/vcvars.cmd'; task.parent.mkdir(exist_ok=True)
    task.write_text(f'@echo off\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\nset\n')
    output=subprocess.check_output(['cmd','/d','/c',str(task)],text=True)
    for line in output.splitlines():
        if '=' in line and not line.startswith('='):
            key,value=line.split('=',1); env[key]=value
    clang=Path(install)/'VC/Tools/Llvm/x64/bin/clang-cl.exe'
    if not clang.is_file(): raise SystemExit('Install Visual Studio LLVM/clang-cl tools')
    env['MV_CLANG']=str(clang)
    return env

def main():
    ap=argparse.ArgumentParser(description=__doc__); sub=ap.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('setup'); s.add_argument('--elf',required=True); s.add_argument('--disc',required=True); s.add_argument('--ffmpeg',required=True)
    s.add_argument('--keys-dir', default='game/private_keys', help='Private headers and optional keys.json')
    b=sub.add_parser('build'); b.add_argument('--jobs',type=int,default=8); b.add_argument('--configure-only',action='store_true')
    b.add_argument('--optimize',action='store_true',help='Enable native O1 optimization with symbols and assertions retained')
    g=sub.add_parser('generate'); g.add_argument('--stage',choices=['ppu','spu'],required=True); g.add_argument('--jobs',type=int,default=8)
    sub.add_parser('check')
    args=ap.parse_args()
    if args.cmd=='setup':
        c={'elf':str(Path(args.elf).resolve()),'disc':str(Path(args.disc).resolve()),'ffmpeg':str(Path(args.ffmpeg).resolve()),'keys':str(Path(args.keys_dir).resolve()),'userdata':'game/userdata','generated':'build/generated/named'}
        for key in ('elf','disc','ffmpeg'):
            if not Path(c[key]).exists(): raise SystemExit(f'Missing {key}: {c[key]}')
        with Path(c['elf']).open('rb') as source:
            if source.read(4) != b'\x7fELF':
                raise SystemExit('Supply a decrypted ELF, not a SELF/container')
        if not (Path(c['disc'])/'USRDIR').is_dir():
            raise SystemExit('--disc must be the matching PS3_GAME directory containing USRDIR')
        for directory in ('include','lib','bin'):
            if not (Path(c['ffmpeg'])/directory).is_dir():
                raise SystemExit(f'FFmpeg development distribution missing {directory}/')
        (ROOT/'config/local.json').write_text(json.dumps(c,indent=2)+'\n'); print('Local configuration saved (Git-ignored)'); return
    if args.cmd=='check': run([sys.executable,ROOT/'scripts/check_repository.py']); return
    c=config()
    if args.cmd=='generate':
        if args.stage=='ppu':
            out=c['generated']/'ppu'
            if out.exists() and any(out.iterdir()): raise SystemExit('Existing lift preserved. Move it to temp/ before regeneration.')
            meta=ROOT/'build/metadata'; meta.mkdir(parents=True,exist_ok=True)
            run([sys.executable,TOOLS/'ppu_loader.py',c['elf'],'--output',meta])
            functions=meta/'named.functions.json'
            run([sys.executable,ROOT/'scripts/analysis/debug_elf_functions.py',c['elf'],'--out',functions])
            run([sys.executable,TOOLS/'ppu_lifter.py',c['elf'],'--functions',functions,'--hle-stubs',meta/(c['elf'].stem+'.imports.json'),'--cpp-nonlocal-jumps','--output',out,'--jobs',args.jobs])
        else:
            images=ROOT/'build/extracted/spu'; out=c['generated']/'spu'
            if out.exists() and any(out.iterdir()): raise SystemExit('Existing SPU tree preserved. Move it to temp/ before regeneration.')
            run([sys.executable,TOOLS/'extract_spu_images.py',c['elf'],'--output',images])
            run([sys.executable,TOOLS/'build_spu_workloads.py','--images',images,'--lifted',out,'--out',out/'spu_workloads.c','--title','MotorStorm MV','--constructor'])
        print('Generated output is private and ignored. See docs/BUILDING.md for additional module requirements.'); return
    if args.cmd=='build':
        if not 1<=args.jobs<=8: raise SystemExit('Use 1..8 jobs to bound compiler memory')
        if os.name=='nt':
            # Required discipline before relinking. No matching process is harmless.
            subprocess.run(['taskkill','/F','/IM','ms1_recomp.exe'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        env=build_environment(); binary=ROOT/'build/native'
        command=['cmake','-S',ROOT,'-B',binary,'-G','Ninja','-DCMAKE_BUILD_TYPE=Debug','-DPORT_CPP_NONLOCAL_JUMPS=ON',f'-DRECOMP_DIR={c["generated"]/"ppu"}',f'-DSPU_DIR={c["generated"]/"spu"}',f'-DPS3RECOMP_FFMPEG_ROOT={c["ffmpeg"]}',f'-DPORT_PRIVATE_KEYS_DIR={c.get("keys",ROOT/"game/private_keys")}']
        if 'MV_CLANG' in env: command.extend([f'-DCMAKE_C_COMPILER={env["MV_CLANG"]}',f'-DCMAKE_CXX_COMPILER={env["MV_CLANG"]}'])
        command.append(f'-DPORT_OPTIMIZE_NATIVE={"ON" if args.optimize else "OFF"}')
        logs=ROOT/'temp/builds'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        logged_run(command,logs/'configure.log',env=env)
        if args.configure_only: return
        logged_run(['cmake','--build',binary,'--parallel',args.jobs],logs/'build.log',env=env)
        exe=binary/('ms1_recomp.exe' if os.name=='nt' else 'ms1_recomp')
        identity={'path':str(exe),'sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'bytes':exe.stat().st_size,'elf_sha256':hashlib.sha256(c['elf'].read_bytes()).hexdigest(),'ppu_tree':str(c['generated']/'ppu'),'spu_tree':str(c['generated']/'spu'),'logs':str(logs)}
        identity.update(build_type='Debug',optimized_checked=args.optimize)
        (binary/'build_identity.json').write_text(json.dumps(identity,indent=2)); print('Build identity:',identity['sha256'])

if __name__=='__main__': main()
