"""Muted native run with unique output ownership and resource guards."""
import argparse, ctypes, datetime, hashlib, json, os, subprocess, threading, time
from pathlib import Path
import psutil
from project import ROOT, config
from native_window import visible_native_window
from native_resource_guard import commit_reserve, physical_reserve, limits, first_breach

class Memory(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(x,ctypes.c_ulonglong) for x in ('total_phys','available_phys','total_commit','available_commit','total_virtual','available_virtual','available_extended')]

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--seconds',type=int,default=600)
    capture=ap.add_mutually_exclusive_group()
    capture.add_argument('--capture-havok',action='store_true',help='Existing Havok plus graphics/audio diagnostic profile')
    capture.add_argument('--capture-havok-only',action='store_true',help='Enable only the existing Havok observer, without graphics/audio probes')
    ap.add_argument('--capture-bike',action='store_true',help='Prepare bike observer; arm with the owned bike/arm.txt before observed input')
    ap.add_argument('--loadtime-trace',action='store_true',help='Record bounded load-stage events in the owned run')
    ap.add_argument('--capture-textures',action='store_true',help='Bounded run-local compressed source snapshots; adds observer overhead')
    ap.add_argument('--trace-video',action='store_true',help='Video/FS/semaphore observations; adds observer overhead')
    ap.add_argument('--trace-task-lifecycle',type=int,default=0,help='Opt-in task exit/return trace, 1..4096 events per runtime component')
    ap.add_argument('--trace-task-image',type=int,help='Restrict the lifecycle trace to a registered image ID')
    ap.add_argument('--capture-menu',action='store_true',help='Internal menu frames for screen-gated PAD_FILE reproduction; no desktop capture')
    ap.add_argument('--capture-burst-frames',type=int,default=0,help='Opt-in once-only consecutive presented-frame burst, 1..120; arm via run-local capture-burst.arm')
    ap.add_argument('--capture-on-pad',type=lambda value:int(value,0),default=0,help='Arm capture burst in native code when PAD_FILE consumes a matching button mask')
    ap.add_argument('--menu-replay',type=Path,help='Private observed-screen profile; normal PAD_FILE input, not a scene jump')
    ap.add_argument('--profile-renderer',action='store_true',help='CPU renderer phases and GPU timestamps, without broad asset/Havok probes; adds timing overhead')
    ap.add_argument('--replay-observe-seconds',type=int,default=5,help='Observe after the gated replay target (default 5; overall --seconds guard still applies)')
    ap.add_argument('--min-free-commit-gib',type=commit_reserve,default=12,help='Host free-commit reserve, 4..12 GiB (default 12); records budget and preserves other guards')
    ap.add_argument('--native-owned-jobs',action='store_true',help='Opt in to fingerprint-owned native jobs while retaining policy interpretation')
    ap.add_argument('--min-free-physical-gib',type=physical_reserve,default=4,help='Host free physical RAM reserve, 1..4 GiB (default 4); lower explicitly for concurrent host work')
    args=ap.parse_args()
    resource_policy=limits(args.min_free_commit_gib, args.min_free_physical_gib)
    if not 0<=args.capture_burst_frames<=120: raise SystemExit('Capture burst must be 0 (disabled) or 1..120 frames')
    if not 0<=args.capture_on_pad<=0xffff: raise SystemExit('Capture event mask must be 0 (disabled) or 1..0xffff')
    if args.capture_on_pad and not args.capture_burst_frames: raise SystemExit('Capture input event requires --capture-burst-frames')
    if args.capture_burst_frames and not (args.capture_menu or args.menu_replay): raise SystemExit('Capture burst requires --capture-menu or --menu-replay')
    if args.menu_replay:
        from menu_replay import load_profile
        replay_profile=load_profile(args.menu_replay)  # Reject blind routes before process creation.
    if not 1<=args.seconds<=600: raise SystemExit('Bounded run must be 1..600 seconds')
    if not 1<=args.replay_observe_seconds<=600: raise SystemExit('Replay observation must be 1..600 seconds')
    if args.replay_observe_seconds!=5 and not args.menu_replay: raise SystemExit('Replay observation requires --menu-replay')
    if not 0<=args.trace_task_lifecycle<=4096: raise SystemExit('Task lifecycle trace must be 0..4096 events')
    if args.trace_task_image is not None and (args.trace_task_image<0 or not args.trace_task_lifecycle): raise SystemExit('Task image filter requires an enabled trace and nonnegative image ID')
    if any(p.info['name']=='ms1_recomp.exe' for p in psutil.process_iter(['name'])): raise SystemExit('A native instance already exists; close it first')
    c=config(); exe=ROOT/'build/native/ms1_recomp.exe'
    if args.menu_replay and hashlib.sha256(c['elf'].read_bytes()).hexdigest()!=replay_profile['elf_sha256']:
        raise SystemExit('Menu replay target differs from configured ELF; no process launched')
    if not exe.is_file(): raise SystemExit('Build first: python scripts/project.py build')
    # User-approved storage policy, before any native process or PAD replay.
    # Referenced/failed/evidence runs and the supplied profile are protected.
    from prune_runs import automatic
    automatic(ROOT, args.menu_replay)
    if psutil.disk_usage(str(ROOT)).free < 16*1024**3:
        raise SystemExit('Insufficient free disk space: need at least 16 GiB before native startup')
    out=ROOT/'temp/runs'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'); out.mkdir(parents=True)
    env=dict(os.environ)
    # Clear inherited diagnostics before applying the documented booting configuration.
    for key in list(env):
        if key.startswith(('SPU_','FLOW_','RSX_','GCM_','PAD_','FPS_','PM_','CAP_HAVOK','CAP_BIKE','LOADTIME_','AUDIO_','TEX_')) or key in ('FP_PICK','SCREEN_AS_TEX','RD_WWSJOB_SHIM','VDEC_TRACE','FS_READ_ALL','SEMTID','SEM_WAITDBG','PS3_FSLOG'):env.pop(key)
    env.update(PATH=str(c['ffmpeg']/'bin')+os.pathsep+env.get('PATH',''),PS3_VFS_ROOT=str(c['disc']),PS3_HDD0_ROOT=str(c['userdata']),PS3_SAVEDATA_ROOT=str(c['userdata']/'home/00000001/savedata'),AUDIO_MUTE='1',SPU_PM_INTERP='1',SPU_PROBE_INTERP='0',SCREEN_AS_TEX='0',PAD_FILE=str(out/'pad.txt'),FPS_STATS='1',FPS_STATS_CSV=str(out/'frames.csv'),RECOMP_TITLE='MotorStorm MV native')
    if args.native_owned_jobs:env['SPU_NATIVE_OWNED_JOBS']='1'
    for key in ('SPU_WP','SPU_PM_GATE_TRACE','SPU_PM_RETIRE_GUARD','SPU_PM_PC_RESUME','SPU_PM_FLOW_RESUME','SPU_PM_YIELD_RESUME'):env[key]='0'
    env['PS3_KEYS_FILE']=str(c.get('keys',ROOT/'game/private_keys')/'keys.json')
    if args.trace_task_lifecycle:
        env['SPU_TASK_LIFECYCLE_TRACE']=str(args.trace_task_lifecycle)
        if args.trace_task_image is not None:env['SPU_TASK_LIFECYCLE_IMAGE']=str(args.trace_task_image)
    if args.capture_havok or args.capture_havok_only:
        (out/'havok').mkdir(); env['CAP_HAVOK_DIR']=str(out/'havok')
    if args.capture_havok:
        (out/'rsx').mkdir()
        env.update(VDEC_TRACE='1',FP_PICK='036CC2C1',RSX_DBG_VP='04E6FD00',RSX_DBG_VTX='04E6FD00',RSX_DBG_CB='04E6FD00',AUDIO_RATE='1',RSX_PHASE_STATS='1',RSX_PHASE_CSV=str(out/'rsx_phases.csv'),SPU_INTERP_STATS='1',AUDIO_PEAK='1',AUDIO_WAV=str(out/'audio.f32'),PM_JOBPARAMS='1',PS3_FSLOG='1',RSX_CAP='110:3:20',RSX_CAP_DIR=str(out/'rsx'))
    if args.capture_bike:
        (out/'bike').mkdir()
        env.update(CAP_BIKE_DIR=str(out/'bike'),CAP_BIKE_ARM_FILE=str(out/'bike/arm.txt'),PS3_FSLOG='1')
    if args.loadtime_trace:
        env.update(LOADTIME_TRACE='1',LOADTIME_TRACE_FILE=str(out/'loadtime.jsonl'))
    if args.capture_textures:
        (out/'textures').mkdir(); env.update(TEX_RAWDBG='1',TEX_RAWDBG_DIR=str(out/'textures'))
    if args.trace_video:
        env.update(VDEC_TRACE='1',FS_READ_ALL='1',SEMTID='1',SEM_WAITDBG='1',PS3_FSLOG='1')
    if args.profile_renderer:
        env.update(PERF='1',RSX_PHASE_STATS='1',RSX_PHASE_CSV=str(out/'rsx_phases.csv'))
    (out/'pad.txt').write_text('0\n')
    if args.capture_menu or args.menu_replay:
        (out/'rsx').mkdir()
        env.update(RSX_CAP='1:100:120',RSX_CAP_DIR=str(out/'rsx'),RSX_CAP_SCREEN_ONLY='1')
    if args.capture_burst_frames:
        env.update(RSX_CAP_ARM_FILE=str(out/'capture-burst.arm'),RSX_CAP_BURST=str(args.capture_burst_frames))
    if args.capture_on_pad:
        env['RSX_CAP_PAD_MASK']=hex(args.capture_on_pad)
    log=(out/'native.log').open('wb');err=(out/'native.err').open('wb')
    # Request a GUI window while keeping the launcher console hidden.
    startup=subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow=5  # SW_SHOW
    p=subprocess.Popen([str(exe),str(c['elf'])],cwd=ROOT,env=env,stdout=log,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW,startupinfo=startup)
    proc=psutil.Process(p.pid); start=time.monotonic(); reason='guard tooling failure'; terminated=False
    record={'pid':p.pid,'create_time':proc.create_time(),'exe':str(exe),'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'elf_sha256':hashlib.sha256(c['elf'].read_bytes()).hexdigest(),'output':str(out),'muted':True,'capture_menu':bool(args.capture_menu or args.menu_replay),'menu_replay':str(args.menu_replay.resolve()) if args.menu_replay else None,'capture_textures':args.capture_textures,'trace_video':args.trace_video,'capture_havok':args.capture_havok or args.capture_havok_only,'capture_bike':args.capture_bike,'loadtime_trace':args.loadtime_trace,'capture_profile':'broad' if args.capture_havok else 'havok-only' if args.capture_havok_only else 'none','environment':{k:v for k,v in env.items() if k in ('PS3_VFS_ROOT','PS3_HDD0_ROOT','PS3_SAVEDATA_ROOT','AUDIO_MUTE','PAD_FILE','CAP_HAVOK_DIR','CAP_BIKE_DIR','CAP_BIKE_ARM_FILE','LOADTIME_TRACE','LOADTIME_TRACE_FILE','SPU_PM_INTERP','SPU_NATIVE_OWNED_JOBS') or k.startswith(('SPU_PM_','TEX_','RSX_')) or k in ('VDEC_TRACE','FS_READ_ALL','SEMTID','SEM_WAITDBG','PS3_FSLOG') or k=='SPU_WP'}}
    record['resource_limits']=resource_policy
    record['resource_breach']=None
    record['launcher_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    record['resource_guard_sha256']=hashlib.sha256(Path(__file__).with_name('native_resource_guard.py').read_bytes()).hexdigest()
    record['capture_burst_frames']=args.capture_burst_frames
    record['capture_on_pad']=args.capture_on_pad
    record['profile_renderer']=args.profile_renderer
    record['replay_observe_seconds']=args.replay_observe_seconds
    record['environment'].update({k:v for k,v in env.items() if k=='PERF' or k.startswith('MS_NATIVE_')})
    record['environment'].update({k:env[k] for k in ('SPU_TASK_LIFECYCLE_TRACE','SPU_TASK_LIFECYCLE_IMAGE') if k in env})
    (out/'launch.json').write_text(json.dumps(record,indent=2)); print('Owned native PID',p.pid,'output',out,flush=True)
    window_ready=False
    replay_thread=None; replay_result=[]
    def replay_worker():
        from menu_replay import replay
        try: replay_result.append((True,replay(out,args.menu_replay),time.monotonic()))
        except Exception as exc: replay_result.append((False,str(exc),time.monotonic()))
    try:
        while p.poll() is None:
            elapsed=time.monotonic()-start; m=Memory();m.length=ctypes.sizeof(m)
            if not window_ready:
                window=visible_native_window(p.pid)
                if window:
                    window_ready=True
                    (out/'window.json').write_text(json.dumps(dict(window,elapsed=elapsed,create_time=record['create_time']),indent=2))
                    print('Visible owned native window verified; ready for screen-gated runtime input' if args.capture_menu or args.menu_replay else 'Visible owned native window verified; ready for manual navigation',flush=True)
                    if args.menu_replay:
                        replay_thread=threading.Thread(target=replay_worker,daemon=True)
                        replay_thread.start()
                elif elapsed>=30:
                    reason='no visible owned game window within 30 seconds';break
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):raise OSError('Memory guard unavailable')
            private=proc.memory_info().private
            cpu=threads=read_b=-1
            try:
                cpu=round(proc.cpu_percent(None),1);threads=proc.num_threads();read_b=proc.io_counters().read_bytes
            except (psutil.Error,AttributeError,NotImplementedError):pass
            disk_available=psutil.disk_usage(str(ROOT)).free
            with (out/'resources.jsonl').open('a') as f:f.write(json.dumps({'elapsed':elapsed,'private':private,'cpu_percent':cpu,'threads':threads,'io_read_bytes':read_b,'physical_available':m.available_phys,'commit_available':m.available_commit,'disk_available':disk_available})+'\n')
            if (out/'stop.txt').exists():reason='explicit stop marker';break
            if replay_result:
                ok,value,finished=replay_result[0]
                if not ok:reason='menu replay failed: '+str(value);break
                if time.monotonic()-finished>=args.replay_observe_seconds:reason='menu replay target observed; graphics verdict separate';break
            if elapsed>args.seconds:reason='bounded duration elapsed';break
            breach=first_breach(dict(private=private,physical_available=m.available_phys,commit_available=m.available_commit,disk_available=disk_available),resource_policy)
            if breach:
                record['resource_breach']=breach
                prefix='disk space limit reached' if breach['metric']=='disk_available' else 'resource limit reached'
                reason=f"{prefix}: {breach['metric']}={breach['actual_bytes']} bytes; {breach['kind']}={breach['limit_bytes']} bytes"
                break
            time.sleep(2)
        else: reason='guest process exited; inspect logs for outcome'
    finally:
        if p.poll() is None:
            terminated=True;p.terminate()
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
        if replay_thread:replay_thread.join(timeout=2)
        record.update(reason=reason,elapsed=time.monotonic()-start,returncode=p.returncode,terminated_by_guard=terminated,window_ready=window_ready)
        (out/'final.json').write_text(json.dumps(record,indent=2));log.close();err.close();print('Closed:',reason,flush=True)
        from prune_latest_runs import automatic as trim_latest
        trim_latest(ROOT)

if __name__=='__main__':main()
