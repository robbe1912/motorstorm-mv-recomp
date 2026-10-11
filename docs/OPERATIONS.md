# Running and capturing

After [setup/build](BUILDING.md), use:

```powershell
python scripts/run.py --seconds 600
python scripts/run.py --seconds 600 --capture-havok
python scripts/run.py --seconds 600 --capture-havok-only
```

Each invocation creates a unique temp/runs/UTC_TIMESTAMP with launch.json, stdout/stderr logs, resources.jsonl, frames.csv, pad.txt and final.json after closure. Launch identity includes EXE/ELF hashes, PID/create_time and capture profile. It uses configured isolated userdata and mutes host audio. `--capture-havok` activates existing hooks if present plus graphics/audio probes and sparse RSX capture. `--capture-havok-only` enables the existing Havok observer without those additional probes. The flags are mutually exclusive; empty output does not prove those boundaries executed.

Owned child limits: 600s, available physical ≥4GiB, available commit ≥12GiB, private ≤14GiB. Write stop.txt in its run directory for closure. final.json distinguishes guards from natural exits; always inspect fatal logs even on exit 0. Match PID/create_time before attaching/stopping; preserve ordinary user RPCS3.

Inherited probes are cleared; development SPU_PM_INTERP=1 remains. Six known pre-menu wedge probes are zeroed: SPU_WP, SPU_PM_GATE_TRACE, SPU_PM_RETIRE_GUARD, SPU_PM_PC_RESUME, SPU_PM_FLOW_RESUME, SPU_PM_YIELD_RESUME. Probe-off boots both clean/instrumented menus; individual guilty knob is not isolated. FLOW_FSDBG=1 correlated with early resourcesystem 938 fatal and is omitted. Hooks alone were exonerated for this pre-menu wedge, not permanent stability.

## Input and proof

Write one ASCII line MASK POLLS to the current pad.txt:

```powershell
Set-Content -LiteralPath 'temp/runs/YOUR_RUN/pad.txt' -Value '0x4000 8' -Encoding ascii
```

File clears on consumption; stdout acknowledges [cellPad] PAD_FILE press. Observe the screen before the next press. Default 40 polls can auto-repeat. Hex masks: CROSS 0x4000, START 0x0008, UP 0x0010, RIGHT 0x0020, DOWN 0x0040, LEFT 0x0080. Avoid timed scripts for acceptance. The historical “7-press” list CROSS×4, DOWN, CROSS contains six presses; actual screens/acknowledgments override that label and old 225s timings. Old retail guidance used a ≥15s cadence.

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
Synthetic observer checks cover disabled output, capture gating and quotas;
normal-menu geometry/material capture and the bike render remain unverified.
