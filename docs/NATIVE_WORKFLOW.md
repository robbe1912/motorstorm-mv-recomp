# Native development workflow and paused checkpoint

## State at user-requested stop (2026-10-14)

Feature iteration is paused by the user, not complete. Resume only on explicit
user instruction. DoD remains original main-menu assets displaying normally and
entering a race through ordinary PLAY, with native observation. No fake assets,
forced waits/completion, suppressed errors or title-specific exceptions. Later
verification includes driving, opponents, menus, saves, audio and sustained30FPS
(the user relaxed the original60FPS requirement). Retail mstream stays parked.

The current checkout `codex/pause-workflow-handoff` is runtime-equivalent to
`codex/asset-extraction-guide` atf15ed4be29cb0ef38adad03ff6a392e2f12e648b, plus
this documentation checkpoint. It is the prior boot/menu-capable baseline, **not
an accepted race build**. Do not resume by building the sampler candidate.

Restored `build/native/ms1_recomp.exe` SHA256:
`a3f153bccfca241407a4736739a52cf4fa8c966eb22633c656bd05ac01affb64`.
Supported build logs: `temp/builds/20261014T174845.547343Z`.
Muted owned boot check: `temp/runs/20261014T174927.034095Z`; internal
`rsx/frame_18/backbuffer.bmp` shows LANGUAGE/ENGLISH/FRANCAIS/ESPANOL. No PAD input
was sent. `boot-restoration-check.json`, launch/final records and frame hash retain
proof; owned explicit stop followed. This proves startup usability only, not
correct main-menu scenery, motion, racing, sound or performance. Exact EXE/PDB
backup and hashes: `temp/usable-native-20261014/identity.json`.

The own ps3recomp checkout is back on `combined` atbd4d50a991ef82bbfc574fbc2baa1972b981da6e.
Sampler changes are saved separately and **not** merged into combined.

## Read order and ownership

1. Repository `AGENTS.md`: enforce its instructions before any work.
2. [Build/inputs](BUILDING.md), [operations](OPERATIONS.md),
   [worktrees](WORKTREES.md), [vendor provenance](VENDOR.md),
   [repository boundary](REPOSITORY.md), [issue workflow](NEXT_STEPS.md).
3. Select one atomic [GitHub issue](https://github.com/robbe1912/motorstorm-mv-recomp/issues)
   and read it and its linked canonical evidence before edits.
4. Renderer: [graphics/audio](research/GRAPHICS_AUDIO.md). Runtime/PVS:
   [SPURS](research/SPURS.md), [Havok/reference](research/HAVOK_REFERENCE.md).
   Assets: [reusable extraction](assets/README.md) and
   [MotorStorm correlations](assets/MOTORSTORM.md). Retail:
   [parked lane](research/PARKED_MSTREAM.md), only if explicitly resumed.

Current local repositories are `E:/GitRepos/motorstorm-mv-recomp` and
`E:/GitRepos/ps3recomp-task-lifecycle-trace`. The older Pacific-Rift-named workspace
is historical private evidence, not the current source checkout. The active
native target is the named launch-US debug ELF, not Complete Edition03.10 data.
Original ELF `F:/MSR-extract/ms1_beta/EBOOT_MSMVdbgUS.ELF` SHA256:
`3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706`.
Disc input: `F:/MSR-extract/MotorStorm (USA) (En,Fr,Es) (FW1.80)/PS3_GAME`.
Do not publish inputs, original instruction/asset payloads, keys, saves or dumps.

## Repeatable work cycle

1. Revalidate branch, index, process ownership, source/config/ELF identities and
   live tool handles. Do not infer process death from a timeout or old lock file.
   Work solo, one bounded issue. Preserve work on atomic `codex/` branches.
2. Use the diagnosing-bugs discipline: actual-path red-capable feedback command,
   then3-5 falsifiable ranked hypotheses. Change one contract at a time; a still
   image does not establish motion-blur behavior. Distinguish extraction,
   residency, draw binding, shader execution and correct displayed output.
3. Generic runtime/lifter/renderer work goes to the own ps3recomp fork first.
   Its `origin` push is deliberately disabled; use remote `fork`. Ask before any
   PR outside the MotorStorm repo. Adapt selectively: older fork backend has
   four texture units while curated backend has16 and different cache APIs.
   Validate atomic fixes, combine only accepted candidates, then test together.
4. Add authored game-free regression fixtures using real production helpers and
   an independent expected result; old code must fail the relevant case. Record
   source/binary hashes and complete outputs under ignored `temp/checks`.
   GPU tests use explicit WARP/hardware without silent hardware fallback.
5. Serialize native builds/runs. Check ownership before stopping any process;
   never kill another task's run. Supported build, from repository root:

   ```powershell
   python scripts/project.py build --optimize --jobs 8
   ```

   The supported build kills the native image before relinking. Keep build,
   generated target trees, config, temp and userdata worktree-local. Link only
   selected original input directories read-only. Never recursively delete
   junctions/worktrees; use Git worktree removal.
6. Normal launch entry point:

   ```powershell
   python scripts/run.py --seconds 600
   ```

   Runs must be muted and uniquely owned by PID/create-time/exact EXE. Resource
   guards: available physical>=4GiB, available commit>=12GiB, private<=14GiB and
   duration<=600s. Confirm the owned visible window, not merely a live PID.
   Retain launch.json, final.json, logs, resources, frame stats, captures and pad
   receipts. Stop via the owned run's `stop.txt`; verify its launcher is terminal.
   Required SPU_PM_INTERP=1 and documented wedge diagnostics=0. Diagnostic captures
   perturb timing; do not use them for frame-time acceptance.
7. Only observed-screen-gated ordinary PAD_FILE navigation. ASCII MASK POLLS,
   1-8 polls/action; CROSS4000,START0008,UP0010,RIGHT0020,DOWN0040,LEFT0080.
   A fresh completed numeric BMP, owned identity and native press acknowledgment
   are required. Optional intro skip must follow actual intro observation, once;
   if PLAY is already visible do not send a skip. No blank gate, blind replay,
   scene jump or forced load completion. Any owned suspension must be bounded
   and resume in finally. No desktop/screen control without permission.
8. Inspect the original native repro after the narrow regression passes. Match
   scope: a successful build/test/title/present/nonblack capture is not normal
   graphics, racing or FPS proof. Retain exact EXE/PDB and verify identity before
   any matched-memory/unwind inference. Sequential reads are not atomic snapshots.
9. Update the canonical subject page and authoritative issue with exact proof,
   limitations and next falsifiable step. Before staging and again on actual index:

   ```powershell
   python scripts/check_repository.py
   python scripts/check_docs.py
   git diff --cached --check
   ```

   Inspect actual staged paths/provenance; never force-add private payloads.
   Commit atomically, push own branches, attach every created MotorStorm PR.
   Keep unaccepted candidates draft/unmerged. No issue closure without declared
   native proof. Never manufacture completion or lower the DoD.

## Saved branch/PR stack

| PR | Head / base | State and meaning |
|---|---|---|
| [92](https://github.com/robbe1912/motorstorm-mv-recomp/pull/92) | spurs-policy-u64 / main | Draft scalar-u64 trial; not a proven complete race fix |
| [93](https://github.com/robbe1912/motorstorm-mv-recomp/pull/93) | spu-iret-progress / spurs-policy-u64 | Productive IRET classifier removal, actual-interpreter red/green; native race unproven |
| [95](https://github.com/robbe1912/motorstorm-mv-recomp/pull/95) | renderer-motion-evidence / spu-iret-progress | XY16F RTT decode-before-filter/remap; solid hill improved, residual defects remain |
| [96](https://github.com/robbe1912/motorstorm-mv-recomp/pull/96) | asset-extraction-guide / renderer-motion-evidence | Reusable extraction/material/vertex-color knowledge; no universal exporter claim |
| [98](https://github.com/robbe1912/motorstorm-mv-recomp/pull/98) | rsx-guest-samplers / asset-extraction-guide | Draft bf416c6; native boot fails; do not merge/promote |

Branch names in the table have the `codex/` prefix. Own-fork sampler candidate:
052c17ceda40be8a62cd077466a091faabbdf62f, `codex/rsx-sampler-evidence`; no external PR.
Working baseline includes the older draft stack, not sampler98. Do not merge or
rebase the whole stack indiscriminately.

## Next work, only after resume

1. **Sampler97 / graphics94:** candidate actual-D3D12 descriptor/root-table tests
   pass seven authored cases on WARP/hardware; old fixed states fail five.
   Native rejects u0 address60030303/filter04074000/control080078000 before
   LANGUAGE. Strong witness174110: EXE9726985d..., active FP01F8C8C1/mask0001.
   Exact failed EXE/PDB: `temp/issue-render-motion/native-sampler-9726985d`.
   Min7/mag4/kernel2 mean Gaussian convolution, but coefficients/offsets/LOD/edge
   behavior lack an independent RSX oracle. Do not guess a kernel or silently
   map to linear. Capture exact shader/texture on the working baseline, build
   an authored impulse/checkerboard/filter oracle, then recheck boot and moving
   terrain. Final candidate capture-only run174655 was stopped by user; picked
   files retained, not newly interpreted. Candidate remains unaccepted.
2. **Residual graphics94:** establish a dense temporal repro and identify the
   first incorrect pass. Compare raw scene/MRT, resolve and final output; prior
   XY16F correction helped hill opacity, not stipple/blur/flat material. Upload
   currently uses one mip despite9-12 guest levels. Trace mip chains, actual hill
   draw, UVs, sampler policy, vertex-color format/normalization/order/interpolation
   and material binding. Detailed original diffuse/normal maps are resident.
   Menu terrain VP attribute3->COLOR0 is confirmed; R blends material/detail,
   B alters material response, alpha's eventual role remains unknown. Do not
   assume full hill coverage or that every race landscape uses the same shader.
3. **Bike24 / art23:** bind complete original mesh/color/index/LOD/material spans
   to actual draws. Real bike VB/IB residency is proven, visibility is not.
   Oversized coordinates belonged to environment3Dsky_vehicleselect, not proven
   bike corruption. Startup texture observer's32-item quota is not missing-data
   proof; use bounded late capture45 where needed.
4. **Normal PLAY13 / Havok71 / conditional PVS8:** obtain a current matched failure
   and identify the actual completion producer; do not reuse an old marker wait
   as current truth. Last productive-IRET run's main thread was WaitFlip, not
   C5C424 marker wait. Uncapped PVS queue can progress after confirmation, so PVS
   is not established as the missing-bike cause. Preserve scoped-exonerated CPU
   arithmetic/reservation spans and allocation release/reallocate evidence; do
   not clear maps or fake completion. IRET fixture does not prove full IRQ state.
5. **Remaining acceptance:** video20/21 and binding46, load timing11/12,
   controller44, driving14, opponents15, menus16, saves17, decoded/listened audio
   18/19 (listening authorization required), frame-time25/26 and sustained
   correctness/min30FPS27, clean-input setup29. Measure only after correctness;
   no diagnostic capture FPS claim. Conditional resource/Havok1/3/4/6/7 and PM9/10
   activate only when their exact prerequisites are observed. Generic SPU/codecs
   36/37/38 remain backlog, not permission to resume parked retail30.

## Private tooling and evidence traps

- `temp/issue-render-motion/run.py`: clean renderer capture derivative,
  RSX_CAP1:80:60; no PPU watch/bike observer. `control.py` follows ordinary
  to-class/class-to-model, observes12s, then stops; it does NOT confirm MOHAWK/race.
- `run_material.py` adds FP_PICK/attribute diagnostics; raw texture quota can
  exclude late uploads. `run_convolution.py` is capture-only at FP01F8C8C1.
- `temp/issue8-ppu/run_watch.py` unconditionally enables an uncapped PPU watch;
  not a clean renderer baseline. `control_iret.py` has a bounded intro-observation
  suspension handshake; do not invoke unattended or mistake it for automatic
  observation. Its marker parser requires exact matched C5C424 plus ppu_run.
- `temp/issue24-draw` retains older read-only observer tools, but the current
  production backend lacks their capture_draw_batch/RSX_DRAW_CAPTURE hook.
  Setting those env knobs alone does not capture geometry.
- RSX_CAP manifests precede full BMP completion; validate payload and numeric
  ordering. FP_PICK HLSL precedes later adaptations; picked binary is a later
  guest read, not automatically the SET-time snapshot. Color BMPs drop alpha;
  FP16/FP32 visualization uses abs/clamp, not raw signed/HDR values.
- Baseline130115/frame65: ghostlike output despite solid raw hill.
  Candidate131633/frame37: solid but flat hill, stipple/no bike. Run132520 retains
  terrain shader/material reads and detailed BC maps;133222 captures sampler
  registers. These remain private and prove only the stated scope.
