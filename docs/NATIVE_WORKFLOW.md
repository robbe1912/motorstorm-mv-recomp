# Native workflow checkpoint (2026-10-14)

Historical record of the user-requested feature pause and the usable build it
preserved. The operating procedure lives in [operations](OPERATIONS.md) and
[setup](BUILDING.md); pending work belongs to [GitHub issues](https://github.com/robbe1912/motorstorm-mv-recomp/issues)
through [issue tracking](NEXT_STEPS.md). This page keeps no backlog and no
second copy of the work cycle.

## Paused state and usable build

Feature iteration paused at the user's request on 2026-10-14; it was not
complete. DoD remains original main-menu assets displaying normally and
entering a race through ordinary PLAY, with native observation. No fake
assets, forced waits or completion, suppressed errors or title-specific
exceptions. Later verification includes driving, opponents, menus, saves,
audio and sustained 30 FPS (the user relaxed the original 60 FPS
requirement). Retail mstream stays parked.

The paused checkout `codex/pause-workflow-handoff` was runtime-equivalent to
`codex/asset-extraction-guide` at `f15ed4be29cb0ef38adad03ff6a392e2f12e648b`.
Restored `build/native/ms1_recomp.exe` SHA256
`a3f153bccfca241407a4736739a52cf4fa8c966eb22633c656bd05ac01affb64`, with
supported build logs `temp/builds/20261014T174845.547343Z` and the exact
EXE/PDB backup `temp/usable-native-20261014/identity.json`. The muted owned
boot check `temp/runs/20261014T174927.034095Z` recorded the
LANGUAGE/ENGLISH/FRANCAIS/ESPANOL backbuffer without PAD input; that proves
startup usability only, not menus, motion, racing or performance. The own
ps3recomp checkout was on `combined` at
`bd4d50a991ef82bbfc574fbc2baa1972b981da6e`, with sampler changes saved
separately and unmerged.

## Resume disposition

Work resumed on 2026-10-15; issue 104 closed the single observed intro skip.
The saved draft stack (PRs 92/93/95/96) and the 2026-10-14 evening
depth/clear checkpoint (the PR101 branch work) were subsequently
incorporated through PR124; their depth and workload acceptance gaps remain
open. Draft PR98 (native boot failed with the candidate samplers) stays
rejected, and the fork sampler candidate `codex/rsx-sampler-evidence`
(`052c17ceda40be8a62cd077466a091faabbdf62f`) remains unaccepted. Do not
merge, promote or resume either from this record; capture fresh evidence
under an open issue first. Sampler and graphics evidence lives in
[graphics/audio](research/GRAPHICS_AUDIO.md) on issue 94.

Since the resume, direction moved from renderer candidates to native
workload replacement: [native game operations](NATIVE_GAME.md) documents the
verified hierarchy and job-wait operations now bound into normal builds.
Issue tracking selects the next bounded unit.

## Private tooling and evidence traps

- `temp/issue-render-motion/run.py`: clean renderer capture derivative,
  RSX_CAP1:80:60; no PPU watch/bike observer. `control.py` follows ordinary
  to-class/class-to-model, observes 12s, then stops; it does NOT confirm
  MOHAWK/race. `run_material.py` adds FP_PICK/attribute diagnostics; a raw
  texture quota can exclude late uploads. `run_convolution.py` is
  capture-only at FP01F8C8C1.
- `temp/issue8-ppu/run_watch.py` unconditionally enables an uncapped PPU
  watch; not a clean renderer baseline. `control_iret.py` has a bounded
  intro-observation suspension handshake; do not invoke it unattended or
  mistake it for automatic observation. Its marker parser requires exact
  matched C5C424 plus ppu_run.
- `temp/issue24-draw` retains older read-only observer tools, but the
  current production backend lacks their capture_draw_batch/RSX_DRAW_CAPTURE
  hook; setting those env knobs alone does not capture geometry.
- RSX_CAP manifests precede full BMP completion; validate payload and
  numeric ordering. FP_PICK HLSL precedes later adaptations; the picked
  binary is a later guest read, not automatically the SET-time snapshot.
  Color BMPs drop alpha; FP16/FP32 visualization uses abs/clamp, not raw
  signed/HDR values.
- Baseline130115/frame65: ghostlike output despite a solid raw hill.
  Candidate131633/frame37: solid but flat hill, stipple/no bike. Run132520
  retains terrain shader/material reads and detailed BC maps; 133222
  captures sampler registers. These remain private and prove only the stated
  scope.
