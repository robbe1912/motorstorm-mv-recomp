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

Owned child limits: 600s, available physical ≥4GiB, available commit ≥12GiB, private ≤14GiB. Write stop.txt in its run directory for closure. final.json distinguishes guards from natural exits; always inspect fatal logs even on exit 0. Match PID/create_time before attaching/stopping; preserve ordinary user RPCS3.

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

## Input and proof

Write one ASCII line MASK POLLS to the current pad.txt:

```powershell
Set-Content -LiteralPath 'temp/runs/YOUR_RUN/pad.txt' -Value '0x4000 8' -Encoding ascii
```

File clears on consumption; stdout acknowledges [cellPad] PAD_FILE press. Default 40 polls can auto-repeat. Hex masks: CROSS 0x4000, START 0x0008, UP 0x0010, RIGHT 0x0020, DOWN 0x0040, LEFT 0x0080. The historical “7-press” list CROSS×4, DOWN, CROSS contains six presses; screens and acknowledgments override old timing recipes.

For a known menu checkpoint, use `python scripts/run.py --menu-replay PRIVATE_PROFILE.json`. The supported launcher captures game-internal backbuffers and drives normal input without desktop capture, focus or input. Schema 1 profiles contain the selected ELF SHA256, observed reference BMPs/ROIs/labels, single-button steps with 1..8 polls, and a target with optional additional checks. Profiles and reference images remain private. Text comparisons use white-glyph overlap; exact RGB comparison requires an unchanged observed ROI. A heading alone can match a help overlay: include a distinguishing target check.

Continuation profiles must include screen-gated intro skips in `optional_actions`.
Each uses the same observed reference/ROI/label/button/polls as a required step,
plus `after_step` (the number of required steps already acknowledged). An action
sends once when observed; an absent intro does not block the route. The target
is checked first. Use `mode: "contrast"` for colored or fading intro captions:
normalized grayscale correlation retains the 0.95 match threshold and rejects
flat references/observations. Avoid blank-screen skip gates. The regression
checks faded captions, wrong screens, absent/repeated intros and target priority.

Native trial `20261013T134536.081481Z` (EXE
`5ba10a87abd5667cc498317282b5236d51a4dcadad9cc117be7a592fb945c111`)
acknowledged English, then CROSS on the observed intro caption at 13:46:06 UTC.
The next retained backbuffer shows PLAY over the original menu background;
the owned muted run closed at 42.406 s after target observation. This proves
intro skipping and the menu checkpoint, not ticket/3D correctness or race entry.
The optional-skip regression fails against main `b921cad` because it omits
the expected skip input; retained red/green logs and frames remain private.

Replay validates the target identity before launching, checks PID/create-time/executable/PAD_FILE ownership before writes, waits for fresh internal frames and input receipts, refuses unknown screens, and stops on timeout/error. An observed target is not a graphics or gameplay verdict. Do not request repeated manual navigation for an established checkpoint or jump directly into a guest scene. `scripts/native_pad.py --help` describes the one-step gated interface; `python scripts/check_menu_replay.py` tests the rejected blind recipe, wrong screens, ownership and observed-state progression without game bytes.

## Capture discipline

The private baseline contains ten PPU sources, 24 SPU images and five capture hooks; it is instrumented. Original EXE/PDB are retained under build/preserved/, and rebuilt identities are in build/native/build_identity.json. Build success is not gameplay proof.

Record same-resource raw ID/length/hash, root/variants and lookup args at the same operation. Current observer: four 16MiB raw slots, fatal dump budget 128MiB and buffer 16MiB. Successful animations previously exhausted the 128-event quota; reserve fatal budget and cover both constructors. A fatal_gate label can describe a successful animation-present gate, not a fatal. Heavy diagnostics change timing.

Before native symbolization check EXE/PDB CodeView GUID+age. Actual PC, unwound frames and raw stack candidates are distinct; stale CIA0 is not current PC. RPCS3 GDB attach pauses execution: validate guest bytes, set breakpoint, explicitly resume vCont;c, distinguish trap from frozen post-fault capture. Compare effective full configs/version logs/disc/HDD inputs and explicit target mapping.

RSX_CAP=start:count:interval plus RSX_CAP_DIR retains manifests/backbuffer/targets locally. Shader identity must use bound snapshots, not later recycled addresses. Check print budgets before inferring dead threads. Brightness, title FPS, presents/s or an autosave read are not acceptance.

## Closure discipline

Historical tools of the parked retail lane stay archived with that lane in [parked mstream](research/PARKED_MSTREAM.md); they may hardcode old paths, so inspect and rebase them into a fresh ignored experiment directory before use. Current run.py is the supported launcher. Match guest vm_base/ELF before memory dumping.

Close with actual observations, hashes/identities, limitations and cleanup. Stop only owned processes, preserve artifacts, remove deliberate temporary hooks with matching installer/source assertions, kill native before needed relink and record new identity. Five capture hooks remain unless a deliberate clean-build unit removes/verifies them. [Source coverage](SOURCE_COVERAGE.md) records overwritten-log caveats.


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
