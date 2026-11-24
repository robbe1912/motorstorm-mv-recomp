# Running and capturing

After [setup/build](BUILDING.md), use:

```powershell
python scripts/run.py --seconds 600
python scripts/run.py --seconds 600 --capture-havok
python scripts/run.py --seconds 600 --capture-havok-only
```

Each invocation creates a unique temp/runs/UTC_TIMESTAMP with launch.json, stdout/stderr logs, resources.jsonl, frames.csv, pad.txt and final.json after closure. Launch identity includes EXE/ELF hashes, PID/create_time and capture profile. It uses configured isolated userdata and mutes host audio. `--capture-havok` activates existing hooks if present plus graphics/audio probes and sparse RSX capture. `--capture-havok-only` enables the existing Havok observer without those additional probes. The flags are mutually exclusive; empty output does not prove those boundaries executed.

`--trace-task-lifecycle N` enables a separate task exit/return diagnostic budget,
1..4096 events per runtime component. `--trace-task-image ID` optionally restricts
it to a registered image without spending the budget on other images. The
launcher records both knobs in `launch.json`. Exit/yield requests and ordinary
entry-return cleanup are distinct events. The trace reports sequential exit
context and enabled-bit reads; it changes no task bits and does not prove an
atomic snapshot or race acceptance. It is disabled by default.

Owned child limits: 600s, available physical ≥4GiB, available commit ≥12GiB by default, private ≤14GiB. `--min-free-commit-gib 6` explicitly selects a 6GiB host commit reserve; accepted reserves are finite and 1..12GiB. `--min-free-physical-gib 1` allows concurrent host work with a 1GiB free physical RAM floor; accepted reserves are finite and 1..4GiB. These reserves are host headroom, not game memory requirements. They stay fixed during the run so the guard does not silently reduce its own stop threshold. Lower physical or commit headroom may cause paging and perturb timings; retain the recorded policy when comparing runs. Other guards remain active. `launch.json` and `final.json` record all byte limits and launcher/guard source hashes; a resource stop records its exact metric, value and bound. The [guard policy](../scripts/native_resource_guard.py) and [historical admission checks](../scripts/check_native_resource_guard.py) keep defaults and every other limit enforced. Write stop.txt in its run directory for closure. final.json distinguishes guards from natural exits; always inspect fatal logs even on exit 0. Match PID/create_time before attaching/stopping; preserve ordinary user RPCS3.

Menu/replay captures select `RSX_CAP_SCREEN_ONLY=1` and record it in launch
identity. A periodic sample due during an offscreen capacity drain stays due
until a nonempty presenting batch; it spends neither the scheduled nor burst
budget on the drain. Raw diagnostic capture remains the backend default
(unset or `RSX_CAP_SCREEN_ONLY=0`). This changes capture selection only, not
rendering, submission order or guest presentation. A presenting manifest still
requires successful-Present/error checks and semantic image inspection.

With a supported DX12 executable, automatic replay writes the backbuffer and
a short manifest for periodic screen checks. Explicit `--capture-menu` and
armed bursts retain the full capture. `--replay-screen-stride 40` samples
more often than the default stride of 120. PAD_FILE actions still require
the same observed screen and acknowledgment.
For a normal step whose caption appears before it accepts input, a private
profile can set `stable_frames` to require up to four distinct matching
captures before one press. Intro skip remains a one-time optional action.

Use `--d3d12-debug default|0|1` to select optional DX12 API validation.
Inherited `D3D12_DBG` is cleared: `default` retains the compiled policy, `0`
disables validation, and `1` requests it. Assertions and ordinary device,
queue and resource error handling remain active. The requested setting and
actual environment are recorded; confirm the backend's startup result because
a requested debug interface can be unavailable. Compare the same executable
with matched options before attributing a frame-time difference to validation.

`--profile-textures` enables existing aggregate texture setup/lookup/checksum/
remainder timing and cache outcomes (`PERF=1`, `RSX_TEXTURE_PROFILE=1`). It
records this environment without enabling broad asset captures or GPU queries.
These counters add overhead; retain the same profiling setting on both sides
of a comparison. Texture-call remainder includes several kinds of work and
must not be reported as allocation time alone.

Set `RSX_VERTEX_PROFILE=1` in the launcher environment to print one
`[VTXPROFILE]` line per frame. It reports vertex fetch bytes and time, indexed
uploader calls, cache hits and misses, direct output bytes, and cache copy
bytes and time. Fetch bytes count converted output, not guest input. Copy bytes
and time count the copies of all cached vertices, hits and misses. Each
`misses` value is one converted vertex. The option adds clock reads
and one log line per frame. Leave it off for timing runs that do not need
these counters. The default path does not read the profile clock.

For a renderer timing trial, add `--profile-renderer` to the normal launcher.
It enables CPU phase counters and two GPU timestamp queries per renderer batch, retaining
`rsx_phases.csv`, `[PERF]`/`[RSXPHASE]` logs and the exact timing environment in
launch/final records. It does not enable the broad Havok/asset capture profile.
The backend logs the active timestamp mode. Match GPU results to their
reported `gpu_frame` and include nonpresenting batches when summing GPU time
between Presents. Add `--profile-renderer-draws` for per-draw timing. This
adds query overhead and populates the small and other draw durations.

For CPU boundary timing without GPU queries, set `PERF=1` in
the launcher environment and leave `--profile-renderer` off. The report counts
render batches, including nonpresenting drains, and measures the whole render
function. `outside_render` is unclassified time between batches. The
`command_close` and `command_execute` fields isolate CPU wall time in the API
calls; they include driver work/waits and are not GPU execution durations.

With a private replay, `--replay-observe-seconds 120` retains two minutes after
the observed target instead of the default five seconds, subject to the same
overall `--seconds` and resource guards. Target observation remains a navigation
receipt; inspect images, errors and actual work before reporting a race result.
The launch identity also records inherited `MS_NATIVE_*` modes and `PERF`.

Process creation is reported separately from window readiness. The launcher
checks the owned D3D12 window is visible, unminimized and intersects the desktop,
writes `window.json`, then reports readiness for manual navigation. A hidden
window is a launch failure after 30 seconds even if rendering continues.
`scripts/native_window.py` performs read-only checks; it sends no input or focus
commands. `scripts/check_native_window.py` rejects the real hidden-window trial.

The correction addresses the prior mistake of reporting visibility from a PID.
Trial `20261011T151137.499215Z` had an owned hidden window; the regression rejects
that state. After explicit showing in the D3D12 backend, muted no-input trial
`20261011T153310.991243Z` recorded a visible owned window at 0.157 s and ended
at its 12 s duration guard. This verifies launch readiness only. The inherited
hide mechanism was not traced, and this run does not verify menu or race rendering.

Inherited probes are cleared; development SPU_PM_INTERP=1 remains. Six known pre-menu wedge probes are zeroed: SPU_WP, SPU_PM_GATE_TRACE, SPU_PM_RETIRE_GUARD, SPU_PM_PC_RESUME, SPU_PM_FLOW_RESUME, SPU_PM_YIELD_RESUME. Probe-off boots both clean/instrumented menus; individual guilty knob is not isolated. FLOW_FSDBG=1 correlated with early resourcesystem 938 fatal and is omitted. Hooks alone were exonerated for this pre-menu wedge, not permanent stability.

## Runtime profile admission (issue 149)

The default `--execution-profile baseline-interpreter` retains that curated
environment. Admission requires the selected EXE's adjacent `build_identity.json`,
matching EXE and configured ELF hashes, selected runtime source and recorded
capabilities. Older builds without capabilities must be rebuilt. Capabilities
are never inferred from a later source checkout. An unsupported baseline fails
before run retention, output creation, PAD replay or process creation.

For a deliberate trial of a runtime without the curated policy interpreter:

```powershell
python scripts/run.py --executable 'build/separate/ms1_recomp.exe' --execution-profile toolkit-default --seconds 60
```

`toolkit-default` omits the curated interpreter and resume/probe switches; inherited
SPU/FLOW diagnostics are still cleared. It requires explicit selection even if
the baseline is unsupported. `launch.json` and `final.json` retain the selected
profile, exact profile environment, matching build record and EXE/ELF identities.
The recorded build source includes its capability-source hash and, for a toolkit
Git checkout, revision and dirty status. These records identify the selected
build; they do not prove all possible source capabilities or execution parity.

This selection starts a fresh runtime baseline. It is not an API-only comparison
with an earlier curated D3D12 build. Renderer comparisons need matching runtime,
CPU/SPU/input profiles, build conditions and observations on both renderers.
Vulkan host integration remains under #146; this tooling change launches no
Vulkan trial and establishes no original assets, race entry or 30 FPS result.

`python scripts/check_runtime_profile.py` uses authored inert identities and
intercepts native compilation/process creation while executing the real build
and launcher entry points. It requires Python 3.10+ and `psutil` from
`requirements.txt`. Add `--historical-runtime PATH` to verify actual
`runtime/spu/spu_channels.c` from own-fork commit
`39a36296511c445707adabcd312f0b740cfbd694` (Git blob
`506da3f99dbfa7576dda3d0d53d9d859643e54fb`): the unsupported default must
reject before launch and explicit toolkit-default must record the selection.
`--fetch-historical` fetches only that file at the pinned commit (CI uses it on
Linux and Windows). Without that source, only this optional historical check is
skipped, and the skip is reported. No game
inputs or original instructions are used by either check.

Use `--prompt-flip` to let the guest waiter consume the completion of its
own drained frame when the renderer takes it for presentation. This enables
both GCM completion switches and preserves the refresh limit. Use
`--profile-flip` to log latency in groups of 64 waits. The launcher records
each explicit selection. Both options default to off.

CPU surface dependency diagnostics use `scripts/run.py --profile-cpu-surfaces`.
This explicitly enables and records the existing `RSX_CPU_SURFACE_PROFILE=1`
backend diagnostics after inherited RSX settings are cleared. Each completed
request reports absolute QPC timestamps, client/renderer IDs, exact-range
matches, clean hits, copies, bytes, and disjoint queue/service/copy/fence phases.
Use matches and copies to distinguish stale page dispatches from required GPU
synchronization before changing ownership or waits. Per-request timing and log
I/O perturb execution; keep these captures separate from performance comparisons.
The option changes no readback, completion, error or deadline behavior.
It also records up to 64 snapshot admission observations from the renderer
owner, including current primitive/draw state, requested ranges and candidate
surface extents/generations. Sequence IDs join these records to returned
statuses. A cap is explicit. These observations perturb diagnostic timing.

## Input and proof

Write one ASCII line MASK POLLS to the current pad.txt:

```powershell
Set-Content -LiteralPath 'temp/runs/YOUR_RUN/pad.txt' -Value '0x4000 8' -Encoding ascii
```

File clears on consumption; stdout acknowledges [cellPad] PAD_FILE press. Default 40 polls can auto-repeat. Hex masks: CROSS 0x4000, START 0x0008, UP 0x0010, RIGHT 0x0020, DOWN 0x0040, LEFT 0x0080. The historical “7-press” list CROSS×4, DOWN, CROSS contains six presses; screens and acknowledgments override old timing recipes.

For a known menu checkpoint, use `python scripts/run.py --menu-replay PRIVATE_PROFILE.json`. The supported launcher captures game-internal backbuffers and drives normal input without desktop capture, focus or input. Schema 1 profiles contain the selected ELF SHA256, observed reference BMPs/ROIs/labels, single-button steps with 1..8 polls, and a target with optional additional checks. Profiles and reference images remain private. Text comparisons use white-glyph overlap; exact RGB comparison requires an unchanged observed ROI. A heading alone can match a help overlay: include a distinguishing target check.

PAD_FILE replacement retries a sharing violation at most six times, rechecking
ownership immediately before each attempt. A revoked run or persistent sharing
error preserves the existing command and removes the pending file. The actual-send
regression in `scripts/check_menu_replay.py` covers transient/permanent sharing,
revocation during the delay, and a real Windows handle without delete sharing.
This does not explain the separate historical replay-ownership failure.

Replay binds required and optional sends to the frame whose complete gate set
passed. A newer completed presenting frame before selection or PAD_FILE replacement
requires fresh gate validation. The regression changes a secondary condition while
preserving the caption and checks that neither route writes a command.

### Native menu boot

Supported debug-US builds enable the identity-checked startup policy by default.
The policy accepts the configured selected language through its original handler,
closes the first opening-video request at verified caller addresses, and lets the
original finished-video transition perform menu initialization, profile saving,
background-video start and music setup. Background and later movie requests retain
the original path. This changes startup workflow under the owner direction in #323.

`--original-intro` selects reference startup. Build `--no-menu-boot` omits the binding.
Other target identities retain original startup. Launch metadata records the selected
`MS_BOOT_MENU` value and the selected executable's `menu_boot` capability.

Menu-start replay profiles declare `"startup": "menu"` and begin at PLAY.
Original-start profiles declare `"startup": "original"` or omit the field.
The launcher checks profile mode against selected build/runtime mode before launch.
Continue the subsequent menus through the existing observed-screen gates.
Authored tests cover caller identity, one-time selection, callback completion,
original mode, background forwarding and eight compiled negative controls.
Owned muted run `20261117T040309.228124Z` verified this policy at source
`6c42e97eac5b8dc4c0b418ba35b8307410614f3b`, EXE
`20dd52eaee7c66cdf0540f34d43b379f3ac51b9d419a222c1657b068fb0342bd`.
It reached the inspected PLAY menu with zero required/optional replay inputs and
no PAD_FILE press receipts. Both native startup markers and the `gui_d.m2v`
background open were present. The owned target guard closed at 34.406 seconds.
This verifies startup behavior. Race graphics, interpreter removal and minimum
30 FPS remain open. Private receipt is
`temp/menu-boot-evidence/20261117T040309.228124Z/analysis.json`.

Reference runs selected with `--original-intro` use continuation profiles with
screen-gated intro skips in `optional_actions`.
Each uses the same observed reference/ROI/label/button/polls as a required step,
plus `after_step` (the number of required steps already acknowledged). An action
sends once when observed; an absent intro does not block the route. The target
is checked first. Use `mode: "contrast"` for colored or fading intro captions:
normalized grayscale correlation retains the 0.95 match threshold and rejects
flat references/observations. For visibly verified fades, `reference_variants`
lists additional private BMP paths using the same ROI/mode. They belong to the
same action: any matching variant selects the reference used for the acknowledged
send, then consumes that action once. Keep the 0.95 threshold; do not duplicate
skip actions for alternate images. Avoid blank-screen skip gates. The regression
for issue104 rejects ignoring an observed variant and reusing an action on a
second variant. Native runs `20261014T233820.319968Z` and
`20261014T233859.335448Z` each acknowledge one CROSS8 on the Sony caption and
reach visually inspected PLAY frame11; both close at about 38.5 seconds. They
use EXE `d9b1af564150eb048ede3cfaa39ae809035433917ddc0c5adb8618cb1e96c33b`.
These are intro/menu receipts, without a graphics or race verdict. The regression
checks faded captions, wrong screens, absent/repeated intros and target priority.

Native trial `20261013T134536.081481Z` (EXE
`5ba10a87abd5667cc498317282b5236d51a4dcadad9cc117be7a592fb945c111`)
acknowledged English, then CROSS on the observed intro caption at 13:46:06 UTC.
The next retained backbuffer shows PLAY over the original menu background;
the owned muted run closed at 42.406 s after target observation. This proves
intro skipping and the menu checkpoint, not ticket/3D correctness or race entry.
The optional-skip regression fails against main `b921cad` because it omits
the expected skip input; retained red/green logs and frames remain private.

Screen/input selection requires a complete internal BMP and exactly one
`presenting=1` manifest field. Offscreen (`presenting=0`), missing, partial or
ambiguous presentation status cannot authorize input. Offscreen captures remain
available for renderer analysis. Issue125's production-selector regression rejects
frame25 of run `20261015T163536.232616Z` and selects presented frame24; neither
selection nor a nonblack image proves a playable race. Authored selector cases
run with `python scripts/check_menu_replay.py`.

Replay validates the target identity before launching, checks PID/create-time/executable/PAD_FILE ownership before writes, waits for fresh internal frames and input receipts, refuses unknown screens, and stops on timeout/error. An observed target is not a graphics or gameplay verdict. Do not request repeated manual navigation for an established checkpoint or jump directly into a guest scene. `scripts/native_pad.py --help` describes the one-step gated interface; `python scripts/check_menu_replay.py` tests the rejected blind recipe, wrong screens, ownership and observed-state progression without game bytes.

Completed backbuffers are selected by numeric frame sequence, including the
`frame_99` to `frame_100` boundary. Lexicographic ordering previously selected
an old `frame_99` while `frame_277` was fresh; the freshness guard refused input.
The producer writes the manifest before exporting its backbuffer, so selection
also requires a complete BMP header and its declared pixel payload. Partial
writes remain unavailable; unsupported completed headers still raise errors.
The authored regressions cover numeric ordering, missing manifests, empty or
short headers and a truncated pixel payload. Both former selectors fail their
respective new checks; all ten menu-replay checks pass after correction.

Muted named-US run `20261013T192701.416457Z`, EXE SHA256
`e1e041a43880f7cfe71a58ee0dfb4ccc866ca524cf8ce8a7276fee52fa711e34`,
acknowledged ordinary ticket, Anything and class inputs from completed frames
125, 127 and 129, then observed the selected MOHAWK heading in frame 130.
The latest completed frame was 159 when the owned run stopped explicitly at
130.828 seconds. The private ticket-art reference was updated from an observed
capture of this clipping candidate; no freshness/ownership threshold changed.
This verifies replay beyond the ordering boundary, not bike or race correctness.

### Havok worker threads

The game starts two PPU threads for the Havok step. Each thread name is
`ppu:Havok PPU Thread`. `HavokSystem::NUM_PPU_THREADS` (`0x10066030`) holds the
count. `hkMultithreadingUtil::initMultithreading` (`0xA01220`) starts the threads
and clamps the count to 6. An opt-in switch raises the count.

Build with `python scripts/project.py build --havok-threads`. This binds the
lifted function `func_00A01220` to `src/motorstorm/havok_threads.cpp`. Then start
with `--havok-threads N`, where `N` is 1 to 6. `--havok-threads 0` is the default
and keeps the game count. The launcher sets `MS_HAVOK_THREADS=N` and records it
in `launch.json`. A count above 0 needs a build with the identity flag
`havok_threads`. Without that build, the launcher stops and starts no process.

The hook writes one line to `native.err` at boot, before the first race frame:
`[HAVOK_THREADS] game=<n> set=<n> workers=<n>`. `game` is the count of the game.
`set` is the request. `workers` is the count that the guest started. Each worker
takes 1,500,016 bytes from the Havok heap of 17,039,360 bytes. Two workers take
17.6 % of the heap. Four workers take 35.2 %.

Measured result (exe `8856e66571f07c3e`, diagnostic arms): keep the game count
of two workers.

- Three workers (`--havok-threads 3`, run `20261124T050935`): the race loads.
  The game stops presenting frames after about 170 s. At 340 s the three Havok
  threads and five `spu_async` threads each use 99 % of one core, and the main
  thread is idle. The cause is not known.
  A second run with three workers (exe `62fadf7802bd24e4`, run `20261124T103056`)
  did not stop in 352 s. The three Havok threads used 30 to 35 ms of CPU per
  frame each, against 22 to 25 ms for two workers. The frame did not get
  faster: 134 ms in a diagnostic run, against 108 ms with two workers (run
  `20261124T095418`). Three workers give no gain, and the stop is not regular.
- Four workers (`--havok-threads 4`, run `20261124T050653`): the game stops at
  race load after 70 s with `MsHavokAllocator out of memory trying to
  allocate 8320 bytes`, then `sys_process_exit(code=0)`.

The hook does not change the step order, the substeps, or the stack size of a
thread (256 KiB). `python scripts/check_havok_threads.py` checks the launcher
lines, the registration, the hook and the lifted body.

## Capture discipline

The Havok observer check allows 120 seconds for its compiler/linker and 15
seconds for the synthetic observer executable. It prints compiler duration and
exit status; compiler errors, timeouts and observer assertion failures remain
fatal. The separate compile budget addresses repeated 30-second deadlines on
cold hosted Windows builds (issue108); it changes no native runtime limits.

The private baseline contains ten PPU sources, 24 SPU images and five capture hooks; it is instrumented. Original EXE/PDB are retained under build/preserved/, and rebuilt identities are in build/native/build_identity.json. Build success is not gameplay proof.

Record same-resource raw ID/length/hash, root/variants and lookup args at the same operation. Current observer: four 16MiB raw slots, fatal dump budget 128MiB and buffer 16MiB. Successful animations previously exhausted the 128-event quota; reserve fatal budget and cover both constructors. A fatal_gate label can describe a successful animation-present gate, not a fatal. Heavy diagnostics change timing.

Before native symbolization check EXE/PDB CodeView GUID+age. Actual PC, unwound frames and raw stack candidates are distinct; stale CIA0 is not current PC. RPCS3 GDB attach pauses execution: validate guest bytes, set breakpoint, explicitly resume vCont;c, distinguish trap from frozen post-fault capture. Compare effective full configs/version logs/disc/HDD inputs and explicit target mapping.

RSX_CAP=start:count:interval plus RSX_CAP_DIR retains manifests/backbuffer/targets locally. Shader identity must use bound snapshots, not later recycled addresses. Check print budgets before inferring dead threads. Brightness, title FPS, presents/s or an autosave read are not acceptance.

## Bind registers to their capture

A metadata unwind restores a context pointer, not the old contents at that
pointer. Offline analysis can take long enough for live guest GPRs to belong
to a later operation. Prefer bytes retained in the same matched minidump,
using the verified context layout and an unambiguous memory extent. If absent,
report the missing evidence; a later live read is not a substitute. Preserve
EXE/PDB/dump identities and each read's source/time. Guest objects, queues and
LS read afterward remain sequential observations, not a whole-process atomic
snapshot. The [retained PVS mismatch](research/SPURS.md#queue-contracts-and-uncapped-ppu-watch-2026-10-14-issue-8)
demonstrates why this matters and records the private helper correction.

## Closure discipline

Historical tools of the parked retail lane stay archived with that lane in [parked mstream](research/PARKED_MSTREAM.md); they may hardcode old paths, so inspect and rebase them into a fresh ignored experiment directory before use. Current run.py is the supported launcher. Match guest vm_base/ELF before memory dumping.

Close with actual observations, hashes/identities, limitations and cleanup. Stop only owned processes, preserve artifacts, remove deliberate temporary hooks with matching installer/source assertions, kill native before needed relink and record new identity. Five capture hooks remain unless a deliberate clean-build unit removes/verifies them. [Source coverage](SOURCE_COVERAGE.md) records overwritten-log caveats. Do not infer process death from a timeout or an old lock file.


Bike observer groundwork (#24): `python scripts/run.py --capture-bike` creates
an owned `bike/` output directory and records `CAP_BIKE_ARM_FILE` in launch.json.
After observing the selection screen, create that run's `bike/arm.txt` before the
next acknowledged input. This replaces a fixed boot-time cutoff. The selected
private generated tree must already contain validated entry probes; this profile
does not install them. Per-stage quotas are independent and exhaustion is logged.
`rsfind` captures the eight-byte ResourceIdentifier through r5; r4 is the output
handle, whose entry contents cannot establish a result. Older captures labeled
the r4 buffer as `identifier` and do not provide request-identifier snapshots.
Synthetic observer checks cover the distinct r4/r5 arguments, disabled output,
capture gating and quotas;
normal-menu geometry/material capture and the bike render remain unverified.

`--capture-textures` snapshots compressed uploads into owned `textures/`, with
binding/source addresses, format, dimensions, mips, face, pitch, QPC and full
noncryptographic content fingerprint. It observes upload cache misses, not every
draw; unchanged binding/content snapshots are deduplicated. Caps: 32 attempts,
16 MiB per snapshot, 128 MiB total. Errors and exhaustion are explicit; existing
files are never overwritten. `--trace-video` records the selected decoder/FS/
semaphore knobs in launch identity. Both profiles perturb timing; absent capped
log lines do not prove absent guest operations. All payloads remain private.

## Combined review validation (2026-10-11)

The primary checkout `codex/pr-integration-live` combined reviewed PRs #34,
#40, #42 and #43 with main. All four authored observer regressions and the
source/docs audits passed. The supported native build succeeded; EXE SHA256
`0dd887cccb9182e0c44a7dfaf4a44eb22e094f3e803b1e3541fa7dee8098575a`,
named-US ELF SHA256
`3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706`.
The original selected tree's 61 generated source hashes remained unchanged;
nine bike entry probes were installed only in an ignored copied tree.

Private run `20261011T021620.648042Z` enabled Havok-only, bike, compressed
textures, video trace and load-time trace together. It was visible, muted and
manually navigated by the user, with no PAD_FILE presses. Screenshots show
main-menu text over black, malformed race selection, then SELECT A BIKE
without bike artwork/model. The user reported selecting a bike to start;
the screen remained at selection. This establishes an attempted start, not
consumed-input timing or race entry. The user closed the window; the owned
launcher finalized at 217.125 s via its explicit stop marker (exit 1, guard
termination). It did not produce a playable race or Havok fatal capture.

The diagnostics operated within their declared limits. Their specific
findings belong to [graphics/video](research/GRAPHICS_AUDIO.md),
[load tracing](research/RUNTIME.md) and [PVS](research/SPURS.md). All raw
assets, logs, snapshots, build records and screenshots remain ignored.
The merged source tree was compared with the tested integration tree and
matched exactly before these documentation updates. This is one diagnostic
run, not a performance comparison, clean regeneration proof or acceptance
of assets, sound, saves, driving, opponents or minimum 60 FPS.

## Bounded capture at an input event (issue 110)

Use `--capture-menu --capture-burst-frames 64 --capture-on-pad 0x10` to capture
the first matching UP command consumed by native PAD_FILE code. The input
still requires the ordinary inspected-screen gate and receipt. A shared atomic
notification arms a once-only renderer burst; no guest addresses, menu names
or forced transitions are encoded in the runtime. The budget is 1..120
presented batches with recorded operations, with unique indices shared with
sparse navigation captures. Each manifest records reason and presenting flag.
The burst cannot restart in the same process. Invalid budgets/masks fail
before launch. Default capture behavior is unchanged.

Without `--capture-on-pad`, an owned controller may create the run-local
`capture-burst.arm` marker after checking ownership and the observed scene.
For continued observation after reaching a menu, use a capture-only bounded
launcher and a separate normal `menu_replay.replay` controller. Do not retain
a stale target gate to avoid the normal replay launcher's target shutdown.
Native event/manifest evidence is required in addition to selector tests.

`python scripts/check_rsx_capture_schedule.py` compiles the actual selector
and event latch with an authored game-free fixture, then checks launch
preflight. It runs on Ubuntu and Windows. Capture readback perturbs timing;
these runs do not prove normal frame rates or correct vehicle rendering.


## Offline native stack attribution

Issue [211](https://github.com/robbe1912/motorstorm-mv-recomp/issues/211)
reuses the Win64 contexts and bounded native stacks already saved by the owned
observer. Run `python scripts/check_native_stacks.py --mutants` on Windows x64
first: the authored optimized executable must recover leaf/middle/top/main,
while the separately compiled missing-unwind-metadata control loses those
callers. Missing stack bytes, wrong bases, context disagreement and bad
EXE/PDB/blob identities remain visible failures.

`scripts/analyze_native_stacks.py --help` documents the private packet,
EXE/hash/PDB-hash and output arguments. Output must be outside the protected
packet. The reader uses Windows StackWalk64 with the PE runtime-function table,
read-only non-executable image mappings and only the saved stack memory; it
never opens a target process, launches the game or uses desktop input. Symbols
use the admitted local PDB and local DLLs; symbol-server auto-detection and the
environment symbol path are disabled. Missing memory/metadata and unresolved
symbols are retained. A plausible return-address scan is not an unwind.

The protected issue209 packet produced 285 saved walks across the renderer,
async worker and three policy workers (57 each), with explicit partial-walk
reasons. Native worker callers include the interpreter, guarded native
visibility routines and SIMD helpers. Renderer callers include vertex fetch,
fragment-program hashing and texture upload. Async callers include the real
taskset signal wait and lifted job dispatch. This resolves some callers hidden
by earlier CRT/OS instruction-pointer observations, using no new native run.

These are selected later suspending point observations, not CPU-event samples,
exclusive CPU percentages, complete inline/tail-call histories or causal frame
time. Exact EXE/PDB/blob identities and the actually loaded PDB hash/CodeView GUID+age are verified; DLL bytes were not archived
at capture time, so current local DLL extents/hashes are reported separately
and walks through them lose historical-identity qualification. Every incomplete
walk remains explicit. #155 full critical-path cost, #27 stable30 and #137
rendering remain open; the next native rewrite still requires original/native
parity and matched gameplay timing. All memory, binaries, symbols and captures
remain private; CI uploads authored-test logs/JSON only.

For the default-off fingerprint-owned job experiment, pass `--native-owned-jobs` to [run.py](../scripts/run.py). The launcher clears inherited SPU flags, explicitly selects and records `SPU_NATIVE_OWNED_JOBS=1`, and retains required policy interpretation. Environment inheritance alone does not select this mode.

Use `--native-owned-jobs --native-owned-image 210` to isolate compiled
admission to the verified debug-US PVS image. The selected executable must
record the image selector capability. Use a build without job capture, and
keep native policy services off for this comparison. The launcher records
`SPU_NATIVE_OWNED_IMAGE`. The runtime checks the first containing resident
span and retains the original ownership, interrupt and observation guards.
This selects compiled jobs for measurement. A typed batch has a separate
input, output and completion contract.

Pass `--jobmod-dispatch-log` to select and record `SPU_JOBMOD_DISPATCH_LOG=1` (default off; diagnostic). `spu_indirect_branch` then logs the first 16 and every 64th transfer per worker into a claimed job span that a lift serves, as `[pm-jobmod] DISPATCH ... resolver=lift`. Transfers the resolver misses (`resolver=MISS->interp`) always log. With lift hits logged, a MotorStorm race writes about 875,000 of these lines, and the SPU threads wait on stderr and the C runtime's stream lock. Any value other than unset, `0` or `1` aborts. [check_spu_native_owned.py](../scripts/check_spu_native_owned.py) covers the switch.

Pass `--jobmod-header-fnv` as well to select and record `SPU_JOBMOD_HEADER_FNV=1` (default off). The staging matcher then also identifies a job image by the span its C0DEC0DE header declares (image minus the 0x20 trailer), once per burst. Without it, a job the policy module loads with tail padding never matches its registered identity and runs interpreted; the MP3 job objects (ids 217/218) are loaded this way. A header match logs `[pm-jobmod] header identity`. [check_spu_jobmod_identity.py](../scripts/check_spu_jobmod_identity.py) covers the matcher with authored images.

Pass `--pm-native-services` with `--native-owned-jobs` to select and record `SPU_PM_NATIVE_SVC=1` (default off). Native jobs call job manager services with `bisl` into the policy module's text, and under policy interpretation those services otherwise run in the interpreter. [spu_pm_services.cpp](../src/motorstorm/spu_pm_services.cpp) registers MotorStorm's job manager entries and the LS code ranges they reach. A call from compiled job code runs the lifted service while those ranges in LS equal the pristine text, copied from guest memory and checked against its fingerprint; the ranges stay admitted to the owned gate until the call's bracket ends, and every other owned-gate condition still applies. A LS mismatch logs `[pm-svc] LS ... differs` and that call stays interpreted. `SPU_PM_SVC_VERIFY=1` (diagnostic, set by hand) instead runs each call interpreted while recording its channel operations and their LS effects, replays the lifted service on a private context and LS fed those results, and logs `[pm-svc] VERIFY MISMATCH` if the operations, registers, pc or LS differ. [check_spu_pm_services.py](../scripts/check_spu_pm_services.py) covers admission, scope and the verifier with authored guest code.

### Persistent DX12 texture cache

`--texture-retention 0|1` explicitly selects the reference or bounded persistent
cache (default `0`); `--texture-cache-mib 0..4096` sets its allocation target
(default `512`). The launcher clears inherited selections and records both.
The target counts owned default texture and upload allocation footprints, not
all driver memory or physical VRAM residency. Indispensable live batch pins may
exceed it; `[TEXRESIDENCY]` reports this overage with `--profile-textures`.
A zero target retains required batch resources until genuine GPU retirement.

`--texture-mips 0|1` (`RSX_TEX_MIPS`, default `0`) uploads the mip levels
SET_TEXTURE_FORMAT declares below level 0 for 2D and cube textures, clamped to
the halvings the dimensions allow; volumes keep one level. Each (face, level)
is decoded at its own size and layout and copied to its own subresource, and
the identity covers every uploaded level. `[RSXTEXMIP]` names the first chained
uploads and their class. Linear (LN) chains assume lower levels packed at their
own width; that rule has no hardware cross-check yet. Game-free coverage:
[check_rsx_texture_mips.py](../scripts/check_rsx_texture_mips.py); D3D12
readback and per-level sampling: `check_rsx_texture_gpu.py` phase `mips-only`.

`--surface-prefetch 0|1` (default `0`) sets `RSX_CPU_SURFACE_PREFETCH` to
MotorStorm's three race feedback surfaces: the 2048x2048 deformation surface
(`01A80500`), a 1280x720 surface the game probes at varying points
(`00A80500`) and the 64x64 HDR exposure target (`02A30480`). Reads stay
coherent: each still returns the surface as of every write submitted before
it. After a submitted batch that wrote a listed surface the CPU has read since
its last copy, the renderer queues a copy behind that batch; a read that needs
exactly that generation packs it, waiting only for that copy's fence, instead
of fencing all submitted work and copying anew. Any other read takes the
ordinary copy. The launcher clears an inherited list and records the
selection. `RSX_CPU_SURFACE_PREFETCH_LOG=1` prints used, waited, missed and
copy counts. Game-free coverage:
[check_cpu_surface_prefetch.py](../scripts/check_cpu_surface_prefetch.py).

`--eager-surface-submit 0|1` (default `0`) sets `RSX_CPU_SURFACE_EAGER` to
MotorStorm's 64x64 HDR exposure target (`02A30480`). The main thread reads it
once per race frame, 10-20 ms after the renderer records the draws that write
it. Without the switch the batch holding those draws is submitted only when the
read arrives (or at the frame end), so the read waits for the renderer to
replay it and the GPU to run it. With it, the renderer submits the batch at the
first draw boundary after those draws whose draw no longer targets a listed
surface, or at its idle pump, through the same nonpresenting capacity path as
the early submission for pending reads. Reads stay coherent: each still needs
the surface's current generation; only the submission point moves. With
`--surface-prefetch 1` the copy queued behind that batch usually holds the
generation the read needs. The launcher clears an inherited list and records
the selection. `RSX_CPU_SURFACE_PROFILE=1` also prints `[CPUSURFACE_EAGER]`
submit counts. Game-free coverage:
[check_cpu_surface_eager.py](../scripts/check_cpu_surface_eager.py).

`--eager-surface OFFSET` (hex, repeatable, at most 3) adds RSX surface
offsets to the eager list of `--eager-surface-submit 1`. The default list
holds only the 64x64 HDR exposure target (`02A30480`). The launcher clears an
inherited list and records the selection.

`--cpu-surface-fast 0|1` (default `1`) selects the coherent read fast path.
A client read of a surface with no recorded write since its last copy is
served on the calling thread from that copy. `0` queues every read for the
renderer; use it only for a matched comparison on the same executable. A
read that needs a copy still waits. Measured in a race: no gain (#326).

`--cpu-surface-snapshot-fast 0|1` (default `0`) serves a snapshot request on
its calling thread when no recorded draw targets a range and each range lies
in one current surface that holds it fully, or in no surface. The client
repeats the check after the read. Other requests take the FIFO boundary
path. Measured in a race: it serves 95 percent of the requests and does not
cut the frame time (#326). Game-free coverage:
[check_cpu_surface_snapshot_fast.py](../scripts/check_cpu_surface_snapshot_fast.py).

`--profile-cpu-surfaces` prints one `[CPUSURFACE_PROFILE]` line per request:
address, bytes, match and copy counts, and the times in QPC ticks (queue,
service, copy fence, packing). With `--cpu-surface-snapshot-fast 1` it also
prints the `[CPUSURFACE_SNAPSHOT_FAST]` served and queued counters. It adds
timing and logging overhead: use it to find the slow requests, then run the
timing arm without it.

`--profile-renderer-draws` needs `--profile-renderer`. It adds a GPU timestamp
pair to each draw and writes `rsx_draws.csv` next to `rsx_phases.csv` (at most
2,000,000 rows). The `rt0` to `rt3` columns are RSX surface offsets: a row
with `rt0` equal to a listed offset selects the draws into that surface. The
readback of a row is ready at the start of the next batch, and the timestamps
add overhead. Game-free coverage:
[check_rsx_draw_profile.py](../scripts/check_rsx_draw_profile.py).

Four more columns tell whether a draw has the GPU state of the previous
draw of the batch. `cmd` is a bit sum. Bit 1: the mid-batch snapshot sits
before the draw. Bit 2: a clear record sits before the draw. Bit 4: the
draw uses another sampler table. Bit 8: the draw uses another stencil
reference. Bit 16: the draw is the first use of a depth surface.
`vc_sig` and `fc_sig` are FNV-1a signatures of the vertex constant slot
(b0) and of the fragment constants (b1) of the draw. `fc_sig` is 0 when
the backend has no b1 buffer. `state_eq` is 1 when the row has no flag,
`cmd` is 0 and both signatures are equal to those of the previous row of
the file. The first row of a batch has `state_eq` 0. `barriers` is not
part of `state_eq`. Two draws with `state_eq` 1 differ only in the vertex
data that they read. The record reads the b0 slot (8224 bytes) and the b1
constants of each draw for the signatures.

`--spurs-kernel-notify 0|1` (default `0`) selects `SPURS_KERNEL_NOTIFY=1`.
The SPURS coordinator thread looks for new job demand once per period. With
the switch off, each period is a `Sleep(1)` call. With the switch on, the
coordinator waits on a high-resolution waitable timer until the fallback
deadline. The HLE calls that publish job demand or return a lane make the
timer expire at once. The fallback deadline counts in
`QueryPerformanceCounter` units. It ends after 1 ms and does not step with
the system tick (15.6 ms on this machine). Before this change the deadline
used `GetTickCount64`, which steps with the tick. Stores of the guest code
into the ready counts are not seen at once; the timed pass finds them. The
default clears an inherited value, and the launch record names the selection.
The switch changes no job order. Measured in a race with lifted jobs before
the timer change: no change (5.92 against 5.83 presents per second, median
frame 165.6 against 165.8 ms; run `20261123T234752.038668Z` against
`20261123T231436.539891Z`). The timer change has no measured run. Its
expected saving is small: the game calls `timeBeginPeriod(1)` at start, so
the tick in the game process can already be near 1 ms [INFERENCE]. The
marker waits do not come from the coordinator wake-up
([#327](https://github.com/robbe1912/motorstorm-mv-recomp/issues/327)).
Game-free coverage: [check_spurs_notify_wait.py](../scripts/check_spurs_notify_wait.py).

`--spurs-lanes N` (default `0`) sets `SPURS_LANES=N` with `N` from 1 to 6. It
replaces the lane count that the game requests for each SPURS instance (5 in
a race). Each lane is one host worker thread. The instance and
`cellSpursGetInfo` report the effective count. The log line of the
initialization shows both counts: `nSpus=6 requested=5`. Without the option
the launcher clears an inherited value, because it does not clear the
`SPURS_` prefix. The launch record names the key. More lanes shorten a marker
wait only when jobs are ready and no lane is free. In a race, the first
marker wait of the vehicle jobs has no free lane for 8.1 ms per frame while
particle jobs hold the lanes
([#327](https://github.com/robbe1912/motorstorm-mv-recomp/issues/327)).
Measured result: no clear gain. Clean runs with the CPU deformation buffer on,
by wall time: median dt 97.9, 100.1 and 91.6 ms in the windows 200, 300 and 390 s
with six lanes (`20261124T094720`), against 98.6, 98.9 and 96.1 ms with five
lanes (`20261124T065827`). Over the same race frames 1100 to 1400 (exe
`8856e66571f07c3e`): median 99.3 ms against 100.5 ms, p95 108.2 ms against
108.7 ms. Six lanes with the wait priority and the marker wake (exe
`62fadf7802bd24e4`, run `20261124T111736`): median 97.9 and 96.5 ms in the
ranges 1100 to 1400 and 1500 to 1800, against 103.6 to 108.5 ms in two control
runs, but p95 141.8 and 162.9 ms against 115.8 to 121.0 ms. Game-free coverage:
[check_spurs_lane_count.py](../scripts/check_spurs_lane_count.py).

`--spurs-wait-priority 0|1` (default `0`) selects `SPURS_WAIT_PRIORITY=1`.
The SPURS coordinator gives each free lane to the first workload that passes
its admission checks, from a round-robin cursor. With the switch on, the job
wait adapter tells the runtime the job list address of each marker wait of
the game. The coordinator tests the workload of that job list at the first
position of the scan of each free lane. The admission checks do not change,
so the other workloads run later. With the switch on, the coordinator prints
`[SPURS_WAIT_PRIORITY] waits=N boosted_jobs=M` at most one line per second.
Without the option the launcher clears an inherited value, because it does
not clear the `SPURS_` prefix. The launch record names the key. In a race,
the vehicle marker wait takes 28.6 ms per frame. The marker 15 wait holds
245 particle records against 13.6 vehicle records
([#327](https://github.com/robbe1912/motorstorm-mv-recomp/issues/327)).
Measured result (exe `62fadf7802bd24e4`, clean runs with the CPU deformation
buffer on, same race frames): no gain in the median, and long frames. Frames
1100 to 1400: median 104.4 ms against 103.6 and 106.0 ms in two control runs
(`20261124T100551`, `20261124T111041`); p95 163.4 ms against 115.8 and
118.9 ms. Frames 1500 to 1800: median 106.5 ms against 107.4 and 108.5 ms;
p95 169.8 ms against 119.4 and 121.0 ms. Frames above 150 ms in the two
ranges: 17 and 31, against 2 and 5 in the control run `20261124T111041`.
One run counts 114,616 waits and 96,657 boosted jobs (run `20261124T101255`).
Game-free coverage:
[check_spurs_wait_priority.py](../scripts/check_spurs_wait_priority.py).

`--spurs-marker-wake 0|1` (default `0`) selects `SPURS_MARKER_WAKE=1`.
A marker wait of the game reads the counters of its job list 64 times, then
sleeps 100 us in a high-resolution timer. On the build machine Windows wakes
the timer after 0.52 ms at least, so each cooperation is late by about
0.4 ms. With the switch on, the runtime calls a host hook after each commit
of a guest line. The job wait adapter keeps the lines of the waited job list
and signals an event when one of these lines commits. The wait blocks on the
event and on the timer, so a lost wake-up cannot hang. A value that is not
`0` or `1` makes the adapter fall back to the guest wait and print an error
line. Without the option the launcher clears an inherited value, because it
does not clear the `SPURS_` prefix. The launch record names the key. In a
race, one cooperation takes 0.52 to 0.59 ms for a due of 100 us, and a
vehicle wait has 12 cooperations
([#327](https://github.com/robbe1912/motorstorm-mv-recomp/issues/327)).
Measured result (exe `62fadf7802bd24e4`, clean run with the switch on, the
wait priority on and the CPU deformation buffer on, run `20261124T102359`,
same race frames): no gain. Frames 1100 to 1400: median 106.1 ms, p95
131.6 ms. Frames 1500 to 1800: median 105.3 ms, p95 169.9 ms; 30 of 300
frames take more than 150 ms. The marker wake has no run without the wait
priority. Game-free coverage:
[check_spurs_marker_wake.py](../scripts/check_spurs_marker_wake.py).

`--rsx-switch KEY=VALUE` (repeatable) sets one `RSX_*` switch of the runtime
that has no launcher option. Use it for a diagnostic arm. The key must start
with `RSX_` and must not be a key that the launcher sets. Without the option
the launcher clears every inherited `RSX_*` key. The launch record names each
switch. Example: `--profile-renderer --rsx-switch RSX_DEFORM_CAPTURE=1
--rsx-switch RSX_DEFORM_TARGETS=00A80500`.

The CPU deformation buffer
([#346](https://github.com/robbe1912/motorstorm-mv-recomp/issues/346)) has
three run modes. Each needs `--rsx-switch RSX_DEFORM_TARGETS=00A80500`.
Capture writes the paint draws to `rsx_deform_draws.txt`: add
`--profile-renderer` and `RSX_DEFORM_CAPTURE=1`. On removes the GPU reads of
the game: add `RSX_DEFORM_BUFFER=1`. The `cpu=` count of
`[native-depth-query]` grows with each read from the buffer. Shadow is the
proof of the mode on: add `RSX_DEFORM_BUFFER=1` and `RSX_DEFORM_SHADOW=1`.
The game still reads the GPU bytes. A `[DEFORM_SHADOW]` line compares the
painted columns with the GPU bytes once a frame. A `[DEFORM_WHEEL]` line
holds the four bytes of one depth read from the CPU copy and from the GPU.
The shadow lines stop after `RSX_DEFORM_LOG` frames (300).
A `[DEFORM_SHADOW] start` line marks the frame in that the private copies
start as the GPU bytes. That frame does not compare.
Each shadow line and wheel line ends with `t_ms`: the performance clock
of `rsx_phases.csv` in milliseconds. A run time is the value minus `t_ms`
of the first row of that file. The wheel lines start with the first
compare that found painted texels. The first painted texel of a run came
22 s after the first paint draw: use `--seconds 300` for a shadow run.
`RSX_DEFORM_DUMP=<frames>` writes the first frames with a difference to a
file: `rsx_deform_dump.bin` next to `rsx_phases.csv` (`--profile-renderer`),
else the file of `RSX_DEFORM_DUMP_FILE`. Without the switches the runtime
takes the GPU path.

`--fastmem-spin-detector 0|1` controls the spin detector of the PPU fast
memory reads. The default `1` keeps the detector on. The value `0` sets
`PPU_FM_SPINDET=0` and the launch record names the key. Without the option
the launcher clears an inherited `PPU_FM_SPINDET`. Use `0` only for a profile
of the lifted code. A guest loop that spins on one address then gets no
yield and no hot-spin report.

`--profile-ppu-waits` sets `PPU_WAIT_PROFILE=1`. Each call of a guest wait
(condition, semaphore, mutex, event queue, event flag) that lasts at least
1 ms writes one `[PPU_WAIT_PROFILE]` line to the game log: thread, kind,
object id, caller address, start, end and frequency in QPC ticks. Set
`PPU_WAIT_PROFILE_MIN_US=<microseconds>` in the environment to change the
shortest wait; `0` writes a line for each call. The profile adds two clock
reads per wait. Do not time a frame interval with it. Game-free coverage:
[check_ppu_wait_profile.py](../scripts/check_ppu_wait_profile.py).

Use identical cache targets, validation and profiling settings for comparisons.
Retention validates every uploaded face with full XXH3; the reference retains
its sparse source checksum. Complete hashing has a measurable cost. Verify the
actual selected mode, allocations, evictions and bytes in `[TEXRESIDENCY]`, plus
the exact executable identity; a requested option is not execution evidence.
The new cache remains experimental pending native race observation and matched
measurements. Use the existing normal menu route and resource/ownership guards.

The restored native visibility operation uses explicit `--native-visibility 0|shadow|1` during runs. The default `0` overrides inherited `MS_NATIVE_VISIBILITY`; nonzero choices require a matching `--native-visibility` build and recorded executable identity. Shadow/native preserve the original operation fallback and real completion. Treat shadow results and operation timings separately from gameplay frame-rate acceptance.

Build with `--native-particle-collisions` and select
`--native-particle-collisions 0|shadow|1`. The default `0` overrides inherited
`MS_NATIVE_PARTICLE_COLLISIONS`; nonzero modes require matching capability
and executable identity. Shadow compares the complete local-store result
against the original collision loop and retains original execution. Native
uses the standalone typed particle-box operation and preserves the original
transform preparation, DMA, epilogue, queue publication and marker commit.
Unsupported images, inputs, ownership or observation/budget boundaries retain
interpretation. Count actual completed batches and contacts; shadow and stage
timings do not establish frame-time acceptance. See [the operation contract](NATIVE_GAME.md#particle-box-collision-batch-337).

Build with `--native-particle-thresholds` and select
`--native-particle-thresholds 0|shadow|1` during runs. The default `0`
overrides inherited `MS_NATIVE_PARTICLE_THRESHOLDS`; shadow and native require
the matching capability and executable hash in the adjacent build identity.
Shadow checks the complete context against original instruction execution;
native uses the guarded typed scan. Unsupported inputs retain interpretation,
and original particle publication and completion remain in place. Inspect
`[native-particle-threshold]` mode, completed, compared and fallback counters
to verify actual coverage. Shadow checks add substantial diagnostic work;
use native/reference modes for subsequent timing and keep the settings matched.

Build with `--native-visibility-batch` and run with
`--native-visibility-batch 1` to try the debug-US batch classifier.
Use `--native-visibility-batch 0` for a reference run with the same executable.
The batch runs after input DMA for a recognized image and caller. It leaves
the original epilogue and completion in place. A batch that may reach a
16 KiB output PUT uses the original interpreter path.
The same opt-in also clears the recognized job's workspace natively before
its original constructors and input DMA. Set `MS_NATIVE_VISIBILITY_INITIALIZE=0`
before launching to retain just that initialization loop for a comparison.
The launcher records this inherited selector in the run identity.
The opt-in also prepares recognized aligned occluder objects natively after
input DMA. It preserves the original next-object DMA, sorting and completion.
Unsupported geometry retains the interpreter. Set
`MS_NATIVE_VISIBILITY_OCCLUDERS=0` to retain this stage for a same-executable
comparison; the inherited selector is recorded with the other native options.

A profile may use a `kind: luminance_occupancy` secondary check for an animated
preview, with explicit `luma_below`, `min_fraction` and `max_fraction` bounds.
Every observed reference must qualify. The check cannot replace a primary
button/target screen; independent text matching and owned completed-frame
checks remain required. Validate real loaded/unloaded/distant/wrong-screen
cases, preserve reference provenance, and inspect graphics separately: a
readiness predicate is not graphics acceptance.


## Native marker-wait timing

`--profile-job-waits` records each completed native marker wait with its guest
caller, queue object, physical owner, threshold, actual final minimum, thread,
polls/cooperations and QPC start/finish/frequency. It selects native wait mode
and records `MS_NATIVE_JOB_WAIT=1` and `MS_NATIVE_JOB_WAIT_PROFILE=1` in the owned
launch packet. The launcher clears inherited values for both selectors.

Admission uses the selected executable's adjacent identity. New builds record
`native_job_wait_profile` alongside `native_job_wait`. Preserved earlier builds
are admitted when their native wait is enabled and their recorded adapter hash
matches the reviewed profiling implementation. Explicitly disabled capabilities
and unknown older implementations require a matching rebuild.

The actual adapter checks clock failures and reports original/reference fallback
separately. Formatting happens after the measured wait completes. Preserve that
logging overhead in the measurement conditions. Joining these QPC spans to job
capture requires equal clock frequency and qualified queue/job lifetimes.
A completed wrapper span supplies the actual wait interval and threshold;
selected-job ownership and an exclusive frame-critical producer remain separate
proof obligations under issue 219.

## Dialogs of a diagnostic build

The game is a debug build and links the debug CRT. Without a setting, each
assertion, each invalid CRT parameter and each heap check of that runtime opens
a modal dialog and stops its thread until a person clicks it. An owned run has
nobody at the window.

- `src/main.cpp` calls `motorstorm::no_dialogs()`
  (`src/motorstorm/no_dialogs.h`) first. The game writes each report to
  stderr, and the run directory keeps it in `native.err`. Windows Error
  Reporting shows no box for the game.
- Start each test program through `python scripts/quiet_run.py --timeout
  <seconds> -- <command>`. The command runs on a private desktop, so its
  dialogs are invisible. A command that blocks on a dialog ends at the time
  limit with exit code 124. The output then names the windows of the command.
  `quiet_run.py` passes stdout, stderr and the exit code of the command through
  unchanged.
- A test program that links the debug CRT includes `motorstorm/no_dialogs.h`
  and calls `motorstorm::no_dialogs()` first in `main`.

Check: `python scripts/quiet_run.py --timeout 900 -- python
scripts/check_no_dialogs.py`. It compiles a fixture with the debug CRT and
rejects 2 mutants of `main` and 3 mutants of the header.

## Compare arms over the same race frames

A window by wall time compares runs of different speed at different race
positions: a faster run is further in the race at the same second. The race
start is the first frame after which 50 frames each take more than 40 ms in
`frames.csv`. Compare the same frames after that frame. Skip the first 1000
race frames: two control runs of one executable differ by 33 ms in the median
there (143.5 and 110.6 ms, runs `20261124T100551` and `20261124T111041`).
Frames 1100 to 1400 and frames 1500 to 1800 gave medians within 12 ms for five
runs with the same options class.

State the median and the p95 of each range. The goal needs a p95 within
20 percent of the median, so count the frames above 150 ms too.

## Bounded job timeline capture

Issue #219 uses the opt-in capture build and an independently observed replay
profile. Configure with `python scripts/project.py build --optimize
--optimize-renderer --depth-observer --capture-jobs`. The selected executable must
record capture and queue-wrapper capabilities. Lifted SPU inputs and all three
toolkit observation options are required. A subsequent ordinary build explicitly
turns those capture options off.

Never time a capture build. Its capture filter stays on the SPU path for the
whole run and keeps every SPU job in the interpreter
([#345](https://github.com/robbe1912/motorstorm-mv-recomp/issues/345)). The
launcher refuses `--native-owned-jobs` on a capture build. For timing, build
without `--capture-jobs` and pass `--native-owned-jobs --jobmod-header-fnv`.
Report the frame-interval spread with every FPS number: the median and the
95th percentile of `dt` in `frames.csv`. An average hides uneven motion.

Run with `--capture-jobs --job-capture-seconds 0.1 --menu-replay <private-profile>`
and the selected native-depth, diagnostic and resource settings. The inherited
`MS_JOB_CAPTURE_DIR` and `MS_JOB_CAPTURE_EXECUTION_PCS` are cleared. The launcher
creates its own `job-capture` directory, waits for `[job-capture] armed`, then
performs the screen-gated menu-start route. Reference `--original-intro` runs use
an original-start profile and its observed intro action. After the target,
exclusive `open` and `snapshot` signals produce `timing.json` and `snapshot.bin`. Explicit stop,
resource, replay, acknowledgment and timeout failures retain their actual outcome.

Capture builds record `job_capture_queue_history=true`. The controller reports
`queue_history=1` and retains initialization/reset calls from startup in the same
bounded buffer. Publication, atomic, execution and scheduler events wait for
`open`. Downstream queue filters still apply. Earlier capture builds retain their
recorded scope. Use valid `open_before_qpc`/`open_after_qpc` bounds in
`timing.json` to distinguish startup lifecycle history from measured-window work.
The earliest record can precede the requested interval. Retain and check buffer
loss counters across both phases.

Retain launch/final metadata, original logs, selected build identity, timing,
snapshot and offline summary together. The snapshot uses native ABI/schema 8,
raw context/entry-LR values, a partial reservation horizon and explicit coverage
counts. Check clock validity, exclusions, pending records, loss, call-ID exhaustion
and inline-path gaps before interpreting a queue generation. Measure observer
overhead before a coordinated title capture. Wrapper return and marker progress
require separate evidence to establish genuine job completion.


Add `--job-capture-execution-pc <PC>` for each selected raw source or target PC
to retain execution observations touching those values. Up to 32 aligned SPU
PCs in `0..0x3fffc` are accepted. Omitting selection keeps full execution
capture. Selection requires the admitted build identity's
`job_capture_execution_filter` capability. The launcher records the canonical
PC list and `MS_JOB_CAPTURE_EXECUTION_PCS`; the controller freezes it before
installing producers and reports the count in its armed acknowledgment.

Selection affects execution events while atomic, scheduler and queue-call
capture retain their existing gates. Rejected execution events contribute to
the saturating exclusion counters. Unknown raw zero PCs may match selected zero;
retain event validity flags when interpreting that match. Keep launch metadata
with the snapshot because selected PCs describe intentional coverage exclusions.
All existing loss, partial-window, ownership and completion qualifications apply.


Policy-state capture copies the running/store slots, physical lane, module data,
three raw policy records, preferred r0/r3/r4/r5 values and dispatcher bytes at each
admitted policy execution event. Capture builds record `job_capture_policy_state`
and startup reports `policy_state=1`. Select raw PC `0x3094` to observe the original
job-call boundary alongside the output/cleanup/marker PCs. The supplemental
`policy` record retains its execution event and clock bounds around sequential
copies. Only private `ls_store` backing is copied. Null/external backing and
invalid clock bounds have explicit flags. Check original dispatcher identity and
record/lane semantics offline before joining job ownership. Concurrent DMA and
unobserved inline control paths still require lifetime/coverage qualification.

Schema 7 adds module identity at an interpreted dispatcher call from `0x3094`.
The inspector validates private backing, aligned module base, the existing SDK
header span and the exact declared entry before reading the bounded image.
It records the 48-byte header, up to 64 entry bytes and the SDK registry's existing
64-bit fingerprint over the declared image minus its 32-byte trailer. Module
status distinguishes unavailable base, invalid header and wrong entry. Capture
builds record `job_capture_module_identity`. The copy clock bounds include the
fingerprint calculation, so this diagnostic cost accompanies each observation.

Larger policy records increase bounded recorder memory. Retain the matching
decoder with each capture. Existing schema-5 and schema-6 evidence uses preserved
decoders and decoded artifacts. Current module-fingerprint title validation and
its overhead measurement remain pending.

## SPU job dump

`SPU_JOB_DUMP=<image>:<entry>[:<max jobs>[:<every n-th job>]]:<directory>`
writes the input files of the oracle for a native port of one SPU job. Set
it for one run. The dump is off by default.

- `image` is the id of the job module image. `entry` is the local store
  address of the job entry, decimal or `0x` hex. `210:0x16270` is the PVS job.
- `max jobs` stops the dump after this number of jobs. The default is 64.
  `every n-th job` dumps one entry of a context in `n`. The default is 1.
  `directory` is the output directory. The dump makes it when it does not
  exist. The rest of the value is the directory, so a drive letter works.
- A job starts at the entry address inside the image span. It ends at the
  next entry of the same context, when the policy module selects the next
  workload, or at the exit of the process. The exit flush writes the open
  jobs. A run that another process kills can lose the open job of a lane,
  at most 6 files.
- One file holds the local store at entry, the exit points, the local store
  of the last exit, and the bytes of each DMA transfer. A file is about
  520 KB without DMA bytes. Lock-line atomics and mailbox writes have no
  record.
- The dump costs memory and disk time per job. Do not time a run with the
  dump.
- An invalid value ends the process with exit code 2. The log holds the
  message `SPU_JOB_DUMP must be`.

Example for the PVS job: `SPU_JOB_DUMP=210:0x16270:64:1:E:/captures/pvs`.
`python scripts/spu_job_dump.py <directory>` prints one line per job. Add
`--dma` for the DMA records. The check is
[check_spu_job_dump.py](../scripts/check_spu_job_dump.py).
