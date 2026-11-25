"""Muted native run with unique output ownership and resource guards."""
import argparse, ctypes, datetime, hashlib, json, math, os, subprocess, threading, time
from pathlib import Path
import psutil
from project import ROOT, config
from native_window import visible_native_window
from runtime_profile import PROFILES, admit_execution_profile, supports_job_wait_profile
from native_resource_guard import commit_reserve, physical_reserve, limits, first_breach

class Memory(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(x,ctypes.c_ulonglong) for x in ('total_phys','available_phys','total_commit','available_commit','total_virtual','available_virtual','available_extended')]

def require_worktree_private_replay(profile_path, profile):
    """Reject replay inputs which would borrow another worktree's captures."""
    private_root=(ROOT/'temp').resolve()
    def require_private(path, label):
        try: Path(path).resolve().relative_to(private_root)
        except ValueError: raise SystemExit(f'{label} escapes this worktree temp directory; no process launched')
    require_private(profile_path, 'Menu replay profile')
    for step in profile['steps']: require_private(step['reference'], 'Menu replay reference')
    target=profile['target']; require_private(target['reference'], 'Menu replay target reference')
    for check in target.get('checks',[]): require_private(check['reference'], 'Menu replay target check reference')

# MotorStorm race surfaces whose CPU reads --surface-prefetch 1 serves from copies queued ahead.
SURFACE_PREFETCH='01A80500,00A80500,02A30480'

def job_dump_directory(value):
    """Directory of <image>:<entry>[:<max jobs>[:<every n-th job>]]:<directory>, the value of SPU_JOB_DUMP.
    None when the value is malformed."""
    fields=value.split(':')
    if len(fields)<3 or not fields[0].isdigit() or int(fields[0])==0: return None
    entry=fields[1][2:] if fields[1].lower().startswith('0x') else ''
    if not entry or any(c not in '0123456789abcdefABCDEF' for c in entry): return None
    i=2
    while i<len(fields)-1 and i<4 and fields[i].isdigit() and int(fields[i]): i+=1
    if i<len(fields)-1 and i<4 and fields[i].isdigit(): return None
    directory=':'.join(fields[i:])
    return directory or None

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--seconds',type=int,default=600)
    ap.add_argument('--executable',type=Path,help='Executable with its adjacent build_identity.json')
    ap.add_argument('--execution-profile',choices=PROFILES,default='baseline-interpreter',
                    help='Runtime policy; toolkit-default explicitly starts a fresh baseline')
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
    ap.add_argument('--original-intro',action='store_true',help='Use original language/video startup for reference diagnostics')
    ap.add_argument('--capture-jobs',action='store_true',help='Arm bounded job capture in an owned run-local directory; requires matching build')
    ap.add_argument('--job-capture-seconds',type=float,help='Open capture for 0.05..5 seconds after the independently observed replay target')
    ap.add_argument('--job-capture-execution-pc',type=lambda value:int(value,0),action='append',default=[],help='Retain execution events matching a raw source or target SPU PC; repeat up to 32 times')
    ap.add_argument('--native-pcm-cubic',choices=('0','shadow','1'),default='0',help='Explicit verified PCM DSP mode; requires matching native-enabled build')
    ap.add_argument('--native-particle-collisions',choices=('0','shadow','1'),default='0',help='Explicit particle-box collision mode; requires matching native-enabled build')
    ap.add_argument('--native-particle-thresholds',choices=('0','shadow','1'),default='0',help='Explicit verified particle threshold scan mode; requires matching native-enabled build')
    ap.add_argument('--native-visibility',choices=('0','shadow','1'),default='0',help='Explicit verified visibility mode; requires matching native-enabled build')
    ap.add_argument('--native-visibility-batch',choices=('0','1'),default='0',help='Enable the debug-US native visibility batch trial')
    ap.add_argument('--depth-observer',action='store_true',help='Enable the bounded raw depth observer; requires a matching observer build')
    ap.add_argument('--native-depth',choices=('0','1'),default='0',help='Experimental native depth query; requires --depth-observer and a matching native-query build')
    ap.add_argument('--d3d12-debug',choices=('default','0','1'),default='default',help='Explicit API validation selection; default preserves build policy and assertions stay enabled')
    ap.add_argument('--profile-textures',action='store_true',help='Existing aggregate DX12 texture phases and cache outcomes; adds timing overhead')
    ap.add_argument('--profile-job-waits',action='store_true',help='Record completed native marker waits with owner, caller, threshold and QPC timing; requires selected build support')
    ap.add_argument('--profile-ppu-waits',action='store_true',help='Record the wall time of guest waits ([PPU_WAIT_PROFILE] lines: cond, semaphore, mutex, event queue, event flag)')
    ap.add_argument('--profile-cpu-surfaces',action='store_true',help='Existing per-request CPU surface read queue, match, copy and fence diagnostics; adds timing and logging overhead')
    ap.add_argument('--surface-prefetch',choices=('0','1'),default='0',help='Copy the race feedback surfaces (deformation 01A80500, 1280x720 00A80500, exposure 02A30480) ahead of coherent CPU reads (default 0: copy on read)')
    ap.add_argument('--eager-surface-submit',choices=('0','1'),default='0',help='Submit the batch as soon as the game stops drawing into the race exposure target (02A30480), ahead of its coherent CPU read (default 0: submit at the read or frame end)')
    ap.add_argument('--eager-surface',type=lambda value:int(value,16),action='append',default=[],metavar='OFFSET',help='Add an RSX surface offset (hex) to the eager list; repeatable, needs --eager-surface-submit 1, 3 extra offsets at most')
    ap.add_argument('--cpu-surface-fast',choices=('0','1'),default='1',help='Serve current-generation CPU surface reads on the calling thread (default 1); 0 queues every read')
    ap.add_argument('--cpu-surface-snapshot-fast',choices=('0','1'),default='0',help='Serve a snapshot CPU read on the calling thread when no recorded draw targets its range and its surfaces are current (default 0: wait for the renderer FIFO boundary)')
    ap.add_argument('--spurs-kernel-notify',choices=('0','1'),default='0',help='Wake the SPURS coordinator when the game publishes job demand, instead of its periodic poll (default 0)')
    ap.add_argument('--spurs-wait-priority',choices=('0','1'),default='0',help='Give a free SPU lane first to the workload of the job list that a marker wait of the game needs (default 0)')
    ap.add_argument('--spurs-marker-wake',choices=('0','1'),default='0',help='End a marker wait of the game when a job list commits, in place of its 100 us timer step (default 0)')
    ap.add_argument('--spurs-lanes',choices=('0','1','2','3','4','5','6'),default='0',help='Lane count for each SPURS instance in place of the count of the game; 0 keeps the count of the game (default 0)')
    ap.add_argument('--rsx-switch',action='append',default=[],metavar='KEY=VALUE',help='Set one RSX_* switch of the runtime (repeatable); the launch record names each switch')
    ap.add_argument('--fastmem-spin-detector',choices=('0','1'),default='1',help='1: the fast memory spin detector runs (default); 0: PPU_FM_SPINDET=0 turns it off')
    ap.add_argument('--fastmem-gate',choices=('0','1'),default='1',help='1: the PPU fast memory paths run (default); 0: PPU_FM=0 sends each guest memory access of the lifted code through the out-of-line family')
    ap.add_argument('--fastmem-count',choices=('0','1'),default='0',help='1: PPU_FM_COUNT=1 turns on the call counter of the PPU fast memory accessors (a diagnostic: it costs speed); 0: default')
    ap.add_argument('--submit-draws',type=int,default=0,help='Submit the batch at the first draw boundary holding this many draws (0 = off, the default; otherwise 16 up to the build draw-record capacity)')
    ap.add_argument('--cpu-surface-prompt',choices=('default','0','1'),default='default',help='Prompt disjoint CPU surface reads; default preserves backend policy, 0 uses batch-end service')
    ap.add_argument('--cpu-surface-flush',choices=('default','0','1'),default='default',help='Submit recorded writes needed by queued CPU reads at the next draw boundary or idle pump')
    ap.add_argument('--prompt-flip',action='store_true',help='Deliver the drained frame completion at take and wake its guest waiter at the original refresh limit')
    ap.add_argument('--profile-flip',action='store_true',help='Record flip wait, vblank and guest delivery latency in groups of 64 waits')
    ap.add_argument('--drain-overlap',choices=('default','0','1'),default='default',help='Overlap recording with a submitted capacity batch; default preserves backend policy')
    ap.add_argument('--texture-retention',choices=('0','1'),default='0',help='Explicit reference or bounded persistent DX12 texture cache')
    ap.add_argument('--texture-cache-mib',type=int,default=512,help='Default+upload allocation target, 0..4096 MiB; live batch pins may exceed it')
    ap.add_argument('--texture-mips',choices=('0','1'),default='0',help='Upload the guest mip chain below level 0 for 2D/cube textures (default 0: level 0 only)')
    ap.add_argument('--profile-renderer',action='store_true',help='CPU renderer phases and per-batch GPU timestamps, without broad asset/Havok probes')
    ap.add_argument('--profile-renderer-draws',action='store_true',help='Add per-draw GPU timestamps to --profile-renderer; adds timing overhead')
    ap.add_argument('--replay-observe-seconds',type=int,default=5,help='Observe after the gated replay target (default 5; overall --seconds guard still applies)')
    ap.add_argument('--replay-screen-stride',type=int,default=120,
                    help='Renderer batches between screen observations during menu replay (default 120)')
    ap.add_argument('--min-free-commit-gib',type=commit_reserve,default=12,help='Host free-commit reserve, 1..12 GiB (default 12); records budget and preserves other guards')
    ap.add_argument('--jobmod-dispatch-log',action='store_true',help='Diagnostic: log the first 16 and every 64th native job transfer a lift serves ([pm-jobmod] DISPATCH resolver=lift); slows SPU threads')
    ap.add_argument('--native-owned-jobs',action='store_true',help='Opt in to fingerprint-owned native jobs while retaining policy interpretation')
    ap.add_argument('--native-owned-image', type=int, help='Restrict native-owned jobs to one resident SPU image ID')
    ap.add_argument('--jobmod-header-fnv',action='store_true',help='Also identify staged job images by their declared C0DEC0DE span, ignoring load padding')
    ap.add_argument('--pm-native-services',action='store_true',help='Run the job manager services native jobs call (registered in src/motorstorm/spu_pm_services.cpp) compiled while their LS text is pristine; requires --native-owned-jobs')
    ap.add_argument('--min-free-physical-gib',type=physical_reserve,default=4,help='Host free physical RAM reserve, 1..4 GiB (default 4); lower explicitly for concurrent host work')
    ap.add_argument('--havok-threads',type=int,default=0,help='Havok PPU worker threads for the physics step: 0 keeps the game count (2), 1..6; above 0 requires a matching --havok-threads build')
    ap.add_argument('--job-dump',metavar='IMAGE:ENTRY[:MAX[:EVERY]]:DIR',help='Diagnostic: SPU_JOB_DUMP of the runtime, a dump of jobs that enter ENTRY of image IMAGE (at most MAX jobs, 64 by default; EVERY n-th job) into DIR inside this worktree temp directory; slows SPU threads, do not time that run')
    args=ap.parse_args()
    if args.profile_renderer_draws and not args.profile_renderer:
        ap.error('--profile-renderer-draws requires --profile-renderer')
    if args.job_dump is not None:
        job_dump_dir=job_dump_directory(args.job_dump)
        if job_dump_dir is None: raise SystemExit('--job-dump takes <image>:<entry>[:<max jobs>[:<every n-th job>]]:<directory> with a decimal image above 0, a 0x entry and two optional numbers above 0: '+args.job_dump)
        try: Path(job_dump_dir).resolve().relative_to((ROOT/'temp').resolve())
        except ValueError: raise SystemExit('--job-dump directory escapes this worktree temp directory; no process launched')
    if args.job_capture_execution_pc and (not args.capture_jobs or
            len(args.job_capture_execution_pc) > 32 or
            any(pc < 0 or pc > 0x3fffc or pc % 4 for pc in args.job_capture_execution_pc)):
        raise SystemExit('Execution PC selection requires --capture-jobs and up to 32 aligned SPU PCs in 0..0x3fffc')
    if not 0<=args.texture_cache_mib<=4096: ap.error("Texture cache target must be 0..4096 MiB")
    if args.job_capture_seconds is not None and (
            not args.capture_jobs or not args.menu_replay or
            not math.isfinite(args.job_capture_seconds) or not .05 <= args.job_capture_seconds <= 5):
        raise SystemExit('--job-capture-seconds requires --capture-jobs, --menu-replay and a duration of 0.05..5 seconds')
    if args.submit_draws and args.submit_draws<16: raise SystemExit("Submit draw cap must be 0 (off) or at least 16")
    resource_policy=limits(args.min_free_commit_gib, args.min_free_physical_gib)
    if not 0<=args.capture_burst_frames<=120: raise SystemExit('Capture burst must be 0 (disabled) or 1..120 frames')
    if not 0<=args.capture_on_pad<=0xffff: raise SystemExit('Capture event mask must be 0 (disabled) or 1..0xffff')
    if args.capture_on_pad and not args.capture_burst_frames: raise SystemExit('Capture input event requires --capture-burst-frames')
    if args.capture_burst_frames and not (args.capture_menu or args.menu_replay): raise SystemExit('Capture burst requires --capture-menu or --menu-replay')
    if args.pm_native_services and not args.native_owned_jobs: raise SystemExit('Native policy services require --native-owned-jobs')
    if args.native_owned_image is not None:
        if not args.native_owned_jobs or not 1 <= args.native_owned_image <= 0x7fffffff:
            raise SystemExit('--native-owned-image requires --native-owned-jobs and an image ID in 1..2147483647')
        if args.pm_native_services or args.capture_jobs:
            raise SystemExit('--native-owned-image requires policy services and job capture to be off')
    if args.menu_replay:
        from menu_replay import load_profile
        replay_profile=load_profile(args.menu_replay)  # Reject blind routes before process creation.
        require_worktree_private_replay(args.menu_replay, replay_profile)
    if not 1<=args.seconds<=600: raise SystemExit('Bounded run must be 1..600 seconds')
    if not 1<=args.replay_observe_seconds<=600: raise SystemExit('Replay observation must be 1..600 seconds')
    if args.replay_observe_seconds!=5 and not args.menu_replay: raise SystemExit('Replay observation requires --menu-replay')
    if not 1<=args.replay_screen_stride<=120 or (args.replay_screen_stride!=120 and not args.menu_replay):
        raise SystemExit('Replay screen stride must be 1..120 and requires --menu-replay when changed')
    if not 0<=args.trace_task_lifecycle<=4096: raise SystemExit('Task lifecycle trace must be 0..4096 events')
    if args.trace_task_image is not None and (args.trace_task_image<0 or not args.trace_task_lifecycle): raise SystemExit('Task image filter requires an enabled trace and nonnegative image ID')
    if not 0<=args.havok_threads<=6: raise SystemExit('Havok thread count must be 0 (game count) or 1..6; no process launched')
    if any(p.info['name']=='ms1_recomp.exe' for p in psutil.process_iter(['name'])): raise SystemExit('A native instance already exists; close it first')
    c=config(); exe=(args.executable or ROOT/'build/native/ms1_recomp.exe').resolve()
    if args.menu_replay and hashlib.sha256(c['elf'].read_bytes()).hexdigest()!=replay_profile['elf_sha256']:
        raise SystemExit('Menu replay target differs from configured ELF; no process launched')
    if not exe.is_file(): raise SystemExit('Build first: python scripts/project.py build')
    elf_sha256=hashlib.sha256(c['elf'].read_bytes()).hexdigest()
    try: admitted=admit_execution_profile(args.execution_profile,exe,elf_sha256)
    except (OSError,ValueError) as error: raise SystemExit(str(error))
    if args.native_owned_image is not None:
        identity = admitted['build_identity']
        if identity['runtime_capabilities'].get('native_owned_image') is not True or identity.get('job_capture'):
            raise SystemExit('--native-owned-image requires a matching image-scope build with capture observers off')
    if args.native_owned_jobs and admitted['build_identity'].get('job_capture'):
        raise SystemExit('--native-owned-jobs has no effect in a job capture build: the SPU jobs stay interpreted (#345). Use a build without --capture-jobs')
    menu_boot = admitted['build_identity'].get('menu_boot') is True and not args.original_intro
    if args.menu_replay and replay_profile.get('startup', 'original') != ('menu' if menu_boot else 'original'):
        raise SystemExit('Replay startup differs from selected executable mode; select a menu-start profile or --original-intro')
    for selected,flag,description in ((args.native_pcm_cubic,'native_pcm_cubic','PCM DSP'),
                                     (args.native_particle_collisions,'native_particle_collisions','Particle-box collision batch'),
                                     (args.native_particle_thresholds,'native_particle_thresholds','Particle threshold scan'),
                                     (args.native_visibility,'native_visibility','Visibility'),
                                     (args.native_visibility_batch,'native_visibility_batch','Visibility batch')):
        if selected != '0':
            # The selected executable's own admitted build record, not build/native's.
            identity=admitted['build_identity']
            if not identity.get(flag) or identity.get('sha256') != admitted['exe_sha256']:
                raise SystemExit(f'{description} mode requires a matching --{flag.replace("_","-")} build; no process launched')
    if args.depth_observer:
        identity=admitted['build_identity']
        if not identity.get('depth_observer') or identity.get('sha256') != hashlib.sha256(exe.read_bytes()).hexdigest():
            raise SystemExit('Depth observer requires a matching --depth-observer build; no process launched')
    if args.native_depth != '0':
        if not args.depth_observer:
            raise SystemExit('Native depth requires --depth-observer and a matching native-query build; no process launched')
        identity=admitted['build_identity']
        if not identity.get('native_depth_query') or identity.get('sha256') != hashlib.sha256(exe.read_bytes()).hexdigest():
            raise SystemExit('Native depth requires a matching native-query build; no process launched')
    if args.havok_threads:
        identity=admitted['build_identity']
        if not identity.get('havok_threads') or identity.get('sha256') != admitted['exe_sha256']:
            raise SystemExit('Havok thread count above 0 requires a matching --havok-threads build; no process launched')
    if args.capture_jobs:
        identity = admitted['build_identity']
        if not identity.get('job_capture') or not identity.get('queue_call_observation'):
            raise SystemExit('Job capture requires a matching --capture-jobs build with queue bindings; no process launched')
        if args.job_capture_execution_pc and not identity.get('job_capture_execution_filter'):
            raise SystemExit('Execution PC filter requires a matching filter-enabled capture build; no process launched')
    if args.profile_job_waits and not supports_job_wait_profile(admitted['build_identity']):
        raise SystemExit('Job wait profiling requires a selected native-job-wait build with profiling capability; no process launched')
    # User-approved storage policy, before any native process or PAD replay.
    # Referenced/failed/evidence runs and the supplied profile are protected.
    from prune_runs import automatic
    automatic(ROOT, args.menu_replay)
    if psutil.disk_usage(str(ROOT)).free < 16*1024**3:
        raise SystemExit('Insufficient free disk space: need at least 16 GiB before native startup')
    out=ROOT/'temp/runs'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'); out.mkdir(parents=True)
    env=dict(os.environ)
    env['MS_NATIVE_PCM_CUBIC']=args.native_pcm_cubic
    env['MS_NATIVE_PARTICLE_THRESHOLDS']=args.native_particle_thresholds
    env['MS_NATIVE_PARTICLE_COLLISIONS']=args.native_particle_collisions
    env['MS_NATIVE_VISIBILITY']=args.native_visibility
    env['MS_NATIVE_VISIBILITY_BATCH']=args.native_visibility_batch
    env['MS_DEPTH_OBSERVER']='1' if args.depth_observer else '0'
    env['MS_NATIVE_DEPTH']=args.native_depth
    env['MS_HAVOK_THREADS']=str(args.havok_threads)
    env.pop('D3D12_DBG',None)
    env.pop('PERF',None)
    if args.d3d12_debug != 'default':env['D3D12_DBG']=args.d3d12_debug
    # Clear inherited diagnostics before applying the documented booting configuration.
    for key in list(env):
        if key.startswith(('SPU_','FLOW_','RSX_','GCM_','PAD_','FPS_','PM_','CAP_HAVOK','CAP_BIKE','LOADTIME_','AUDIO_','TEX_')) or key in ('FLIP_LAT','FP_PICK','SCREEN_AS_TEX','RD_WWSJOB_SHIM','VDEC_TRACE','FS_READ_ALL','SEMTID','SEM_WAITDBG','PS3_FSLOG','MS_JOB_CAPTURE_DIR','MS_JOB_CAPTURE_EXECUTION_PCS','MS_BOOT_MENU','MS_NATIVE_JOB_WAIT','MS_NATIVE_JOB_WAIT_PROFILE'):env.pop(key)
    env.update(PATH=str(c['ffmpeg']/'bin')+os.pathsep+env.get('PATH',''),PS3_VFS_ROOT=str(c['disc']),PS3_HDD0_ROOT=str(c['userdata']),PS3_SAVEDATA_ROOT=str(c['userdata']/'home/00000001/savedata'),AUDIO_MUTE='1',SCREEN_AS_TEX='0',PAD_FILE=str(out/'pad.txt'),FPS_STATS='1',FPS_STATS_CSV=str(out/'frames.csv'),RECOMP_TITLE='MotorStorm MV native')
    env.update(admitted['execution_environment'])
    env['MS_BOOT_MENU'] = '1' if menu_boot else '0'
    if args.profile_job_waits:
        env.update(MS_NATIVE_JOB_WAIT='1', MS_NATIVE_JOB_WAIT_PROFILE='1')
    if args.jobmod_dispatch_log:env['SPU_JOBMOD_DISPATCH_LOG']='1'
    if args.native_owned_jobs:env['SPU_NATIVE_OWNED_JOBS']='1'
    if args.native_owned_image is not None:
        env['SPU_NATIVE_OWNED_IMAGE'] = str(args.native_owned_image)
    if args.jobmod_header_fnv:env['SPU_JOBMOD_HEADER_FNV']='1'
    if args.job_dump is not None: env['SPU_JOB_DUMP']=args.job_dump
    if args.pm_native_services:env['SPU_PM_NATIVE_SVC']='1'
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
    if args.capture_jobs:
        (out/'job-capture').mkdir()
        env['MS_JOB_CAPTURE_DIR'] = str(out/'job-capture')
        if args.job_capture_execution_pc:
            env['MS_JOB_CAPTURE_EXECUTION_PCS'] = ','.join(f'0x{pc:x}' for pc in args.job_capture_execution_pc)
    if args.capture_textures:
        (out/'textures').mkdir(); env.update(TEX_RAWDBG='1',TEX_RAWDBG_DIR=str(out/'textures'))
    if args.trace_video:
        env.update(VDEC_TRACE='1',FS_READ_ALL='1',SEMTID='1',SEM_WAITDBG='1',PS3_FSLOG='1')
    if args.profile_renderer:
        env.update(PERF='1',RSX_PHASE_STATS='1',RSX_PHASE_CSV=str(out/'rsx_phases.csv'))
        if args.profile_renderer_draws:
            env['RSX_PHASE_GPU_DRAWS']='1'
    if args.profile_textures:
        env.update(PERF='1',RSX_TEXTURE_PROFILE='1')
    if args.profile_cpu_surfaces:
        env['RSX_CPU_SURFACE_PROFILE']='1'
    if args.cpu_surface_prompt != 'default':env['RSX_CPU_SURFACE_PROMPT']=args.cpu_surface_prompt
    if args.surface_prefetch=='1':env['RSX_CPU_SURFACE_PREFETCH']=SURFACE_PREFETCH
    eager=[0x02A30480]+args.eager_surface
    if args.eager_surface and args.eager_surface_submit!='1': raise SystemExit('--eager-surface requires --eager-surface-submit 1')
    if (any(not 0<off<=0xffffffff for off in args.eager_surface) or len(args.eager_surface)>3 or
            len(set(args.eager_surface))!=len(args.eager_surface) or 0x02A30480 in args.eager_surface):
        raise SystemExit('--eager-surface takes up to 3 distinct RSX offsets of 1-8 hex digits, other than 02A30480')
    if args.eager_surface_submit=='1':env['RSX_CPU_SURFACE_EAGER']=','.join('%08X'%off for off in eager)
    if args.cpu_surface_fast=='0':env['RSX_CPU_SURFACE_FAST']='0'
    if args.cpu_surface_snapshot_fast=='1':env['RSX_CPU_SURFACE_SNAPSHOT_FAST']='1'
    env.pop('SPURS_KERNEL_NOTIFY',None)
    if args.spurs_kernel_notify=='1':env['SPURS_KERNEL_NOTIFY']='1'
    env.pop('SPURS_WAIT_PRIORITY',None)
    if args.spurs_wait_priority=='1':env['SPURS_WAIT_PRIORITY']='1'
    env.pop('SPURS_MARKER_WAKE',None)
    if args.spurs_marker_wake=='1':env['SPURS_MARKER_WAKE']='1'
    env.pop('SPURS_LANES',None)
    if args.spurs_lanes!='0':env['SPURS_LANES']=args.spurs_lanes
    env.pop('PPU_WAIT_PROFILE',None)
    if args.profile_ppu_waits:env['PPU_WAIT_PROFILE']='1'
    env.pop('PPU_FM_SPINDET',None)
    if args.fastmem_spin_detector=='0':env['PPU_FM_SPINDET']='0'
    env.pop('PPU_FM',None)
    if args.fastmem_gate=='0':env['PPU_FM']='0'
    env.pop('PPU_FM_COUNT',None)
    if args.fastmem_count=='1':env['PPU_FM_COUNT']='1'
    if args.submit_draws:env['RSX_SUBMIT_DRAWS']=str(args.submit_draws)
    if args.cpu_surface_flush != 'default':env['RSX_CPU_SURFACE_FLUSH']=args.cpu_surface_flush
    if args.profile_flip:
        env['FLIP_LAT'] = '1'
    if args.prompt_flip:
        env.update(GCM_FLIP_PROMPT='1', GCM_FLIP_AT_TAKE='1')
    if args.drain_overlap != 'default':env['RSX_DRAIN_OVERLAP']=args.drain_overlap
    env.update(RSX_TEXTURE_RETENTION=args.texture_retention,RSX_TEXTURE_CACHE_MIB=str(args.texture_cache_mib),RSX_TEX_MIPS=args.texture_mips)
    (out/'pad.txt').write_text('0\n')
    if args.capture_menu or args.menu_replay:
        (out/'rsx').mkdir()
        stride=args.replay_screen_stride
        env.update(RSX_CAP=f'1:{12000//stride}:{stride}',RSX_CAP_DIR=str(out/'rsx'),RSX_CAP_SCREEN_ONLY='1')
        if (args.menu_replay and not args.capture_menu and
                admitted['build_identity'].get('replay_backbuffer_capture') is True):
            env['RSX_CAP_BACKBUFFER_ONLY']='1'
    if args.capture_burst_frames:
        env.update(RSX_CAP_ARM_FILE=str(out/'capture-burst.arm'),RSX_CAP_BURST=str(args.capture_burst_frames))
    if args.capture_on_pad:
        env['RSX_CAP_PAD_MASK']=hex(args.capture_on_pad)
    for switch in args.rsx_switch:
        key,sep,value=switch.partition('=')
        if not sep or not key.startswith('RSX_') or len(key)<5 or not key.isupper() or not value or key in env:
            raise SystemExit('--rsx-switch takes RSX_<NAME>=<value> pairs with a key the launcher does not set: '+switch)
        env[key]=value
    if (hashlib.sha256(exe.read_bytes()).hexdigest()!=admitted['exe_sha256'] or
            hashlib.sha256(c['elf'].read_bytes()).hexdigest()!=elf_sha256):
        raise SystemExit('Executable or ELF changed after profile admission; no process launched')
    log=(out/'native.log').open('wb');err=(out/'native.err').open('wb')
    # Request a GUI window while keeping the launcher console hidden.
    startup=subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow=5  # SW_SHOW
    p=subprocess.Popen([str(exe),str(c['elf'])],cwd=ROOT,env=env,stdout=log,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW,startupinfo=startup)
    proc=psutil.Process(p.pid); start=time.monotonic(); reason='guard tooling failure'; terminated=False
    record={'pid':p.pid,'create_time':proc.create_time(),'exe':str(exe),'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'elf_sha256':hashlib.sha256(c['elf'].read_bytes()).hexdigest(),'output':str(out),'muted':True,'capture_menu':bool(args.capture_menu or args.menu_replay),'menu_replay':str(args.menu_replay.resolve()) if args.menu_replay else None,'capture_textures':args.capture_textures,'trace_video':args.trace_video,'capture_havok':args.capture_havok or args.capture_havok_only,'capture_bike':args.capture_bike,'loadtime_trace':args.loadtime_trace,'capture_profile':'broad' if args.capture_havok else 'havok-only' if args.capture_havok_only else 'none','environment':{k:v for k,v in env.items() if k in ('PS3_VFS_ROOT','PS3_HDD0_ROOT','PS3_SAVEDATA_ROOT','AUDIO_MUTE','PAD_FILE','CAP_HAVOK_DIR','CAP_BIKE_DIR','CAP_BIKE_ARM_FILE','LOADTIME_TRACE','LOADTIME_TRACE_FILE','SPU_PM_INTERP','SPU_NATIVE_OWNED_JOBS','SPU_NATIVE_OWNED_IMAGE','SPU_JOBMOD_HEADER_FNV','SPU_JOBMOD_DISPATCH_LOG') or k.startswith(('SPU_PM_','TEX_','RSX_')) or k in ('VDEC_TRACE','FS_READ_ALL','SEMTID','SEM_WAITDBG','PS3_FSLOG') or k=='SPU_WP'}}
    if 'SPURS_KERNEL_NOTIFY' in env:record['environment']['SPURS_KERNEL_NOTIFY']=env['SPURS_KERNEL_NOTIFY']
    if 'SPURS_WAIT_PRIORITY' in env:record['environment']['SPURS_WAIT_PRIORITY']=env['SPURS_WAIT_PRIORITY']
    if 'SPURS_MARKER_WAKE' in env:record['environment']['SPURS_MARKER_WAKE']=env['SPURS_MARKER_WAKE']
    if 'SPURS_LANES' in env:record['environment']['SPURS_LANES']=env['SPURS_LANES']
    if 'PPU_WAIT_PROFILE' in env:record['environment']['PPU_WAIT_PROFILE']=env['PPU_WAIT_PROFILE']
    if 'PPU_WAIT_PROFILE_MIN_US' in env:record['environment']['PPU_WAIT_PROFILE_MIN_US']=env['PPU_WAIT_PROFILE_MIN_US']
    if 'PPU_FM_SPINDET' in env:record['environment']['PPU_FM_SPINDET']=env['PPU_FM_SPINDET']
    if 'PPU_FM' in env:record['environment']['PPU_FM']=env['PPU_FM']
    if 'PPU_FM_COUNT' in env:record['environment']['PPU_FM_COUNT']=env['PPU_FM_COUNT']
    record['ppu_fastmem3']=admitted['build_identity'].get('ppu_fastmem3')
    if 'SPU_JOB_DUMP' in env:record['environment']['SPU_JOB_DUMP']=env['SPU_JOB_DUMP']
    record['resource_limits']=resource_policy
    record['resource_breach']=None
    record['launcher_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    record['resource_guard_sha256']=hashlib.sha256(Path(__file__).with_name('native_resource_guard.py').read_bytes()).hexdigest()
    record['environment']['MS_BOOT_MENU'] = env['MS_BOOT_MENU']
    record['environment']['MS_HAVOK_THREADS'] = env['MS_HAVOK_THREADS']
    record['capture_jobs'] = args.capture_jobs
    record['job_capture_seconds'] = args.job_capture_seconds
    record['job_capture_execution_pcs'] = args.job_capture_execution_pc
    if args.capture_jobs:
        record['environment']['MS_JOB_CAPTURE_DIR'] = env['MS_JOB_CAPTURE_DIR']
        if args.job_capture_execution_pc:
            record['environment']['MS_JOB_CAPTURE_EXECUTION_PCS'] = env['MS_JOB_CAPTURE_EXECUTION_PCS']
    record['capture_burst_frames']=args.capture_burst_frames
    record['capture_on_pad']=args.capture_on_pad
    record.update(admitted)
    record['environment'].update(admitted['execution_environment'])
    record['profile_job_waits']=args.profile_job_waits
    record['profile_ppu_waits']=args.profile_ppu_waits
    record['profile_renderer']=args.profile_renderer
    record['profile_textures']=args.profile_textures
    record['d3d12_debug']=args.d3d12_debug
    record['replay_observe_seconds']=args.replay_observe_seconds
    record['environment'].update({k:v for k,v in env.items() if k in ('FLIP_LAT','GCM_FLIP_PROMPT','GCM_FLIP_AT_TAKE','PERF','D3D12_DBG','RSX_TEXTURE_RETENTION','RSX_TEXTURE_CACHE_MIB','RSX_TEX_MIPS','RSX_CPU_SURFACE_PROFILE','MS_DEPTH_OBSERVER') or k.startswith('MS_NATIVE_')})
    record['environment'].update({k:env[k] for k in ('SPU_TASK_LIFECYCLE_TRACE','SPU_TASK_LIFECYCLE_IMAGE') if k in env})
    (out/'launch.json').write_text(json.dumps(record,indent=2)); print('Owned native PID',p.pid,'output',out,flush=True)
    window_ready=False
    job_capture_armed = not args.capture_jobs
    replay_thread=None; replay_result=[]
    def replay_worker():
        from menu_replay import replay
        try:
            result = replay(out,args.menu_replay)
            if args.job_capture_seconds is not None:
                from job_capture_replay import capture_after_target
                from native_pad import owned
                timing = capture_after_target(out,args.job_capture_seconds,owned)
                (out/'job-capture/timing.json').write_text(json.dumps(timing,indent=2),encoding='utf-8')
            replay_result.append((True,result,time.monotonic()))
        except Exception as exc: replay_result.append((False,str(exc),time.monotonic()))
    try:
        while p.poll() is None:
            elapsed=time.monotonic()-start; m=Memory();m.length=ctypes.sizeof(m)
            if not job_capture_armed:
                with (out/'native.err').open('rb') as capture_log:
                    job_capture_armed = b'[job-capture] armed ' in capture_log.read(65536)
                if not job_capture_armed and elapsed >= 10:
                    reason = 'job capture did not arm within 10 seconds; inspect build and native.err'
                    break
            if not window_ready:
                window=visible_native_window(p.pid)
                if window and job_capture_armed:
                    window_ready=True
                    (out/'window.json').write_text(json.dumps(dict(window,elapsed=elapsed,create_time=record['create_time']),indent=2))
                    print('Visible owned native window verified; ready for screen-gated runtime input' if args.capture_menu or args.menu_replay else 'Visible owned native window verified; ready for manual navigation',flush=True)
                    if args.menu_replay:
                        replay_thread=threading.Thread(target=replay_worker,daemon=True)
                        replay_thread.start()
                elif not window and elapsed>=30:
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
        log.close()
        err.close()
        if args.capture_jobs:
            capture_log = (out/'native.err').read_text(encoding='utf-8',errors='replace')
            record['job_capture_armed'] = '[job-capture] armed ' in capture_log
            record['job_capture_snapshot_written'] = '[job-capture] snapshot written ' in capture_log
        (out/'final.json').write_text(json.dumps(record,indent=2));print('Closed:',reason,flush=True)
        from prune_latest_runs import automatic as trim_latest
        trim_latest(ROOT)

if __name__=='__main__':main()
