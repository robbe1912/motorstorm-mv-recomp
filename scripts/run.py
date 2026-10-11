"""Muted native run with unique output ownership and resource guards."""
import argparse, ctypes, datetime, hashlib, json, os, subprocess, time
from pathlib import Path
import psutil
from project import ROOT, config

class Memory(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(x,ctypes.c_ulonglong) for x in ('total_phys','available_phys','total_commit','available_commit','total_virtual','available_virtual','available_extended')]

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--seconds',type=int,default=600)
    capture=ap.add_mutually_exclusive_group()
    capture.add_argument('--capture-havok',action='store_true',help='Existing Havok plus graphics/audio diagnostic profile')
    capture.add_argument('--capture-havok-only',action='store_true',help='Enable only the existing Havok observer, without graphics/audio probes')
    ap.add_argument('--capture-bike',action='store_true',help='Prepare bike observer; arm with the owned bike/arm.txt before observed input')
    args=ap.parse_args()
    if not 1<=args.seconds<=600: raise SystemExit('Bounded run must be 1..600 seconds')
    if any(p.info['name']=='ms1_recomp.exe' for p in psutil.process_iter(['name'])): raise SystemExit('A native instance already exists; close it first')
    c=config(); exe=ROOT/'build/native/ms1_recomp.exe'
    if not exe.is_file(): raise SystemExit('Build first: python scripts/project.py build')
    out=ROOT/'temp/runs'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'); out.mkdir(parents=True)
    env=dict(os.environ)
    # Clear inherited diagnostics before applying the documented booting configuration.
    for key in list(env):
        if key.startswith(('SPU_','FLOW_','RSX_','GCM_','PAD_','FPS_','PM_','CAP_HAVOK','CAP_BIKE','AUDIO_')) or key in ('FP_PICK','SCREEN_AS_TEX','RD_WWSJOB_SHIM'):env.pop(key)
    env.update(PATH=str(c['ffmpeg']/'bin')+os.pathsep+env.get('PATH',''),PS3_VFS_ROOT=str(c['disc']),PS3_HDD0_ROOT=str(c['userdata']),PS3_SAVEDATA_ROOT=str(c['userdata']/'home/00000001/savedata'),AUDIO_MUTE='1',SPU_PM_INTERP='1',SPU_PROBE_INTERP='0',SCREEN_AS_TEX='0',PAD_FILE=str(out/'pad.txt'),FPS_STATS='1',FPS_STATS_CSV=str(out/'frames.csv'),RECOMP_TITLE='MotorStorm MV native')
    for key in ('SPU_WP','SPU_PM_GATE_TRACE','SPU_PM_RETIRE_GUARD','SPU_PM_PC_RESUME','SPU_PM_FLOW_RESUME','SPU_PM_YIELD_RESUME'):env[key]='0'
    env['PS3_KEYS_FILE']=str(c.get('keys',ROOT/'game/private_keys')/'keys.json')
    if args.capture_havok or args.capture_havok_only:
        (out/'havok').mkdir(); env['CAP_HAVOK_DIR']=str(out/'havok')
    if args.capture_havok:
        (out/'rsx').mkdir()
        env.update(VDEC_TRACE='1',FP_PICK='036CC2C1',RSX_DBG_VP='04E6FD00',RSX_DBG_VTX='04E6FD00',RSX_DBG_CB='04E6FD00',AUDIO_RATE='1',RSX_PHASE_STATS='1',RSX_PHASE_CSV=str(out/'rsx_phases.csv'),SPU_INTERP_STATS='1',AUDIO_PEAK='1',AUDIO_WAV=str(out/'audio.f32'),PM_JOBPARAMS='1',PS3_FSLOG='1',RSX_CAP='110:3:20',RSX_CAP_DIR=str(out/'rsx'))
    if args.capture_bike:
        (out/'bike').mkdir()
        env.update(CAP_BIKE_DIR=str(out/'bike'),CAP_BIKE_ARM_FILE=str(out/'bike/arm.txt'),PS3_FSLOG='1')
    (out/'pad.txt').write_text('0\n')
    log=(out/'native.log').open('wb');err=(out/'native.err').open('wb')
    p=subprocess.Popen([str(exe),str(c['elf'])],cwd=ROOT,env=env,stdout=log,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    proc=psutil.Process(p.pid); start=time.monotonic(); reason='guard tooling failure'; terminated=False
    record={'pid':p.pid,'create_time':proc.create_time(),'exe':str(exe),'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'elf_sha256':hashlib.sha256(c['elf'].read_bytes()).hexdigest(),'output':str(out),'muted':True,'capture_havok':args.capture_havok or args.capture_havok_only,'capture_bike':args.capture_bike,'capture_profile':'broad' if args.capture_havok else 'havok-only' if args.capture_havok_only else 'none','environment':{k:v for k,v in env.items() if k in ('PS3_VFS_ROOT','PS3_HDD0_ROOT','PS3_SAVEDATA_ROOT','AUDIO_MUTE','PAD_FILE','CAP_HAVOK_DIR','CAP_BIKE_DIR','CAP_BIKE_ARM_FILE','SPU_PM_INTERP') or k.startswith('SPU_PM_') or k=='SPU_WP'}}
    (out/'launch.json').write_text(json.dumps(record,indent=2)); print('Owned native PID',p.pid,'output',out,flush=True)
    try:
        while p.poll() is None:
            elapsed=time.monotonic()-start; m=Memory();m.length=ctypes.sizeof(m)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):raise OSError('Memory guard unavailable')
            private=proc.memory_info().private
            with (out/'resources.jsonl').open('a') as f:f.write(json.dumps({'elapsed':elapsed,'private':private,'physical_available':m.available_phys,'commit_available':m.available_commit})+'\n')
            if (out/'stop.txt').exists():reason='explicit stop marker';break
            if elapsed>args.seconds:reason='bounded duration elapsed';break
            if private>14*1024**3 or m.available_phys<4*1024**3 or m.available_commit<12*1024**3:reason='resource limit reached';break
            time.sleep(2)
        else: reason='guest process exited; inspect logs for outcome'
    finally:
        if p.poll() is None:
            terminated=True;p.terminate()
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
        record.update(reason=reason,elapsed=time.monotonic()-start,returncode=p.returncode,terminated_by_guard=terminated)
        (out/'final.json').write_text(json.dumps(record,indent=2));log.close();err.close();print('Closed:',reason,flush=True)

if __name__=='__main__':main()
