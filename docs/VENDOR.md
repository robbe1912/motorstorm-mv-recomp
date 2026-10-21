# Vendor provenance and upstream

Issue [170](https://github.com/robbe1912/motorstorm-mv-recomp/issues/170)
adds opt-in DX12 texture-slot phase attribution from own-fork modular commit
`f896596`, integrated into fork `combined` at `412278d`. Set both
`PERF=1` and `RSX_TEXTURE_PROFILE=1` to emit one aggregate record every
20 render batches. Default-off calls do not sample a profiling clock.
The counters distinguish current-frame hits, prior-frame validation, stale
entries, misses and failures; setup, lookup, checksum and remainder wall
times are disjoint. Remainder includes decode/upload and other call work,
not GPU execution time. Clock failures are reported explicitly. This changes
diagnostics only: cache identity, invalidation, upload and error behavior
remain as before. Authored fixtures compile the production lookup/checksum
bodies and profiling helpers on Windows/Linux. Checked diagnostic EXE
`ffe878f6...ebba0f` completed muted DX12 run `20261021T020352.573739Z`
through the existing gated PLAY route. Original menu frame 11 and live race
frame 77 were visually inspected; rendering defects remain. The owned stop
was explicit after 295.563 s. In the 44.566 s sampled gameplay window,
12 texture records had zero failures/clock errors: 99.073% current-frame
hits, 70.186 mean examined slots, and wall-phase shares 1.569% setup,
3.755% lookup, 1.308% checksum, 93.367% remainder. The remainder includes
conversion/upload and other work; these counters do not isolate allocation.
Thirty valid GPU 3D samples had 9.713% median/24.700% maximum activity;
process CPU had 5.412 median logical-CPU equivalents. Startup-log identities
and stable CPU counters identify busy SPU/SPURS and frame-clock workers;
the latter also drains/renders RSX work. This favors CPU-side investigation
over a GPU-load explanation, without proving the limiting dependency.
The private name-query consumer discarded positive-success HRESULT names;
startup logs, not that consumer, supply the reported labels. Raw samples,
identities and selected original captures are preserved outside run retention.
No controlled speedup or stable-30/displayed-FPS acceptance is claimed.

Source: [sp00nznet/ps3recomp](https://github.com/sp00nznet/ps3recomp), snapshot base `268336af3a9f736835181ec09a7d88f695795e06` plus preserved local dirty runtime/lifter fixes. This is not a claim that local changes were accepted upstream. The full old checkout/history and migration hashes remain private.

Retain vendor/LICENSE and per-component notices. Root MIT preserves Ned Heller/sp00nznet credit. Standalone ATRAC source in third_party/at3_standalone remains LGPL2.1 with COPYING.LGPLv2.1; stb_truetype has its own MIT/public-domain notice; shared FFmpeg is external and its license obligations apply. Algorithmic AES/SHA/CRC/JPEG/ATRAC tables are implementation data, not game textures or firmware images. Behavioral RPCS3 reference does not authorize copying GPL implementation.

The NID hash suffix, import IDs, syscall constants and diagnostic addresses are interoperability/research metadata. They are not the separately removed decryption keys or captured instruction fixtures. Automated signatures supplement manual provenance review; they do not certify rights to every future contribution.

The public snapshot excludes nested Git/history, firmware/resource binaries, captured programs, generated lifts, unreviewed instruction fixtures and bundled platform keys. Tests are disabled with an explicit error if requested; see [setup](BUILDING.md). Runtime diagnostic target identifiers are research metadata, not game payloads.

Historical upstream reference documents and the hardcoded private PRX helper remain in a private archive rather than duplicated as current project instructions. The original source licenses, CONTRIBUTING and CONTRIBUTORS remain public.

Public vendor tools are limited to 14 generation/extraction dependencies, enforced by `VENDOR_TOOLS` in the staged-source auditor. Other research/port helpers, baselines, diagnostic output and generic templates remain in the same private reference archive. They are not required by the documented build/generation workflow. Any reused helper must receive a separate provenance review before publication.

Clean upstream was refreshed to `a2c20108af45174dbb7d3e2f87f6acaaef09c6b4`
(v0.14.0, PR246) on 2026-10-14. The earlier `5244db9`/v0.13 survey is historical.
Reuse selectively, preserving curated fixes, component licenses and attribution.

[PR230](https://github.com/sp00nznet/ps3recomp/pull/230),
codex/d3d12-fp-source-capacity, commit `75a32692a6a4cb8f5a9217b78a0ab047c521d6c9`,
is now merged (merge `89f9a32`, 2026-10-13). Its authored 4096-byte/256-instruction
shader expands to 57382 HLSL bytes; original capacity regression 36 pass/3 fail
became 39/0, FXC ps_5_0/O3 passed, Release runtime built and CTest passed 5/5.
These are the original qualified checks, not native game acceptance. The local
analogous fix is in graphics evidence; no game payloads were published.

PR213 overlaps signal/event/context work; do not duplicate it. Private upstream
research artifacts remain in a private archive. Earlier candidate/status lists
are historical; inspect current source and PR state before a trial.

## Combined fork testing

The off-main policy workload-argument trial selectively ports own-fork atomic
`680f097`. Its observed descriptor-write difference and black-background native
regression are recorded in [SPURS evidence](research/SPURS.md#policy-workload-argument-trial-2026-10-14-issue-8).
This trial has not been promoted to the native main branch.

The owner authorized a continuous integration branch in our own fork while
retaining atomic implementation branches for later upstream proposals.
[`combined`](https://github.com/robbe1912/ps3recomp/tree/combined) merges the
existing fix chain through `8e40617`, fragment capacity/window changes, and
upstream v0.14.0 at `8b244cf`. Its
[commit map and validation boundaries](https://github.com/robbe1912/ps3recomp/blob/combined/docs/COMBINED.md)
are canonical for that fork; unfinished observer and force-updated pointer-audit
branches were excluded. No new upstream PR was opened.

Windows Release runtime build and seven CTest tests pass locally. All 24 fork
Python test commands exit successfully, with the POSIX interpreter fixture
explicitly skipped on Windows. Separate authored production-source checks pass
restart, vertex fetch, AA layout, source-2 absolute and WARP clipping. The new
source-2 regression (`27559e1`) fails with the old behavior and passes with the
fix. Its header comes from the same tree as its seven-argument API; a previous
cross-tree eight-argument test result was invalid.

Integration commits enable `combined` pushes in all four workflows, link the
read-coherence module in standalone fiber/codec and direct CI fixtures, and
remove the guest-field runner's assumption that `MV_CLANG` is always set.
Hosted CI caught those dependency/environment failures. All four workflows
(Windows, Linux, Linux Vulkan and macOS) now pass at fork head
`71617d687335c3c004f1fe37f27c419bddfb557b`. These are reusable build/test fixes.

This merge was not overlaid onto MotorStorm and no native game run used it.
The basic private overflow MFC/reservation-holder mechanisms described by
newer PR290 already exist in the curated source; that source comparison does
not establish the cause of the current PVS wait. Scheduler PR291 remains
untried. Original menu assets, the missing bike, normal PLAY and sustained
performance still require native proof under their existing issues.

## Boundary-history diagnostic trial

Generic opt-in interpreter boundary capture was developed and tested on own-fork
`codex/spu-boundary-history`, commits `e9954e3` and `c619594`. Its source, reader,
fixtures and configuration guide remain in that separate diagnostic branch,
not the combined correctness baseline. The temporary curated overlay was only
the shared header and two interpreter insertions; both were removed after the
native probe and the supported noninstrumented build passed. Captured GPR/LS
payloads stay private. [Native evidence and limits](research/SPURS.md#filtered-boundary-history-2026-10-14-issue-8)
record the bounded ordered witness, overwritten history, strict archived-image
admission and remaining PVS wait. No upstream PR or native acceptance is claimed.

## Fork-first workflow

Packed XY16F render-target sampling is authored on own-fork atomic branch
`codex/rsx-xy16-rtt-view`. The new `rsx_texture_alias.h` helper and its D3D
float-readback fixture are identical in the curated integration; the older
fork backend has a selective adapter for its four-unit draw record and cache.
Curated integration uses its current 16-unit records and complete negative
cache identity. Seven authored cases fail unpatched and pass on WARP/hardware;
Windows runtime and supported native builds pass. The first muted native view
improves hill ghosting but retains terrain stipple and no bike. See
[graphics evidence](research/GRAPHICS_AUDIO.md#packed-render-target-sampling-and-residual-stipple-2026-10-14-issue-94).
This is fork-only; no external PR was opened.

Productive interrupt-return regression: own-fork `codex/spu-iret-progress`,
commit `719ea0d`, is included in combined `20b1384`. The fork already lacks the
curated IRET idle heuristic. The curated overlay removes only that heuristic;
equal continuation PCs cannot establish idleness across productive execution.
The actual-interpreter authored fixture fails old curated code and passes both
corrected curated code and fork. It does not test complete IRQ restoration.
[Native evidence](research/SPURS.md#productive-iret-incorrectly-classified-as-idle-2026-10-14-issue-8)
does not establish bike/race acceptance. No external PR was opened.

Task lifecycle diagnostics are authored first on own fork branch
`codex/task-lifecycle-trace`, commit
[`dbe0b4b`](https://github.com/robbe1912/ps3recomp/commit/dbe0b4b).
Only the shared opt-in trace header and corresponding call sites are overlaid.
The fork baseline and curated snapshot have different cleanup implementations;
this overlay preserves each tree's existing behavior. This is a diagnostic
trial, not a task-retirement correction or native race proof. No external PR
was opened.

Guest taskset layout adopts Kurtisone's merged upstream
[PR240](https://github.com/sp00nznet/ps3recomp/pull/240), head
`50c4b361527d219ef3c969d303c8d985c87ad05a`, cherry-picked first to our fork
as [`3ed7f07`](https://github.com/robbe1912/ps3recomp/commit/3ed7f07).
The curated overlay deletes only three native-field stores in CreateTask,
DestroyTaskset and ShutdownTaskset. Their offsets 4/0/8 overlap the guest
RUNNING bitset. All other behavior remains at the curated revision.
Own-fork fixture [`34acdab`](https://github.com/robbe1912/ps3recomp/commit/34acdab)
is authored source, independent of game inputs. The public checker compiles
complete affected API definitions and the real guest-bitset builder; dispatch
and image sizing are stubbed. All three old stores fail the fixture in both
trees; the selected correction passes. This protects guest fields, without
implementing genuine exit retirement or proving native race entry. See
[native limits](research/HAVOK_REFERENCE.md#guest-taskset-layout-correction-2026-10-13).

Keep new ps3recomp work on branches in [our fork](https://github.com/robbe1912/ps3recomp). Upstream branches and open PRs may also be cherry-picked into that fork for local trials. Inspect each diff, preserve attribution, record the exact commit and validate the relevant generic regression and native behavior before adopting it in this project's vendor snapshot. A trial is not an accepted fix; keep unrelated changes separate so they can be selected or reverted independently.

For upstream submission, prepare a small reviewable cherry-pick of the validated fix and ask the user before opening the PR. Existing upstream PRs are context, not authorization to open or reopen one. PR233 remains closed. Keep proprietary inputs and captures private throughout this workflow.

Memory-capacity trial: selected13-line runtime change from our fork commit
`dcd6f48e881d2d44190f19ed4d63a3319b629a72`, branch
[codex/memory-pool-capacity](https://github.com/robbe1912/ps3recomp/tree/codex/memory-pool-capacity).
It enlarges virtual placement space without raising the213MiB physical budget
and resolves aliases by registration above the old arena end. The local
collision-guard dependency was already present; unrelated upstream ABI and
fallback changes were excluded. The synthetic fixture is authored source,
derived from that fork's test, and exercises the real VM/syscall component.
`python scripts/check_memory_capacity.py` records source/binary hashes and
red/green results without game inputs. Windows and Linux CI pass. The native
trial passes the same-resource allocation boundary with a real nonzero buffer;
race/menu acceptance remains unproved. See [executed evidence](research/HAVOK_REFERENCE.md#executed-guest-malloc-failure-2026-10-11).
Inherited bump reclamation, alias registration lifecycle/32-entry capacity
and commit-failure accounting limits remain; this trial does not claim to
correct those contracts. No external PR was opened.

No releases/binaries/dependencies are redistributed by the initial source commit. A separate distribution needs its own complete component/license audit.
## Indexed strip restart adoption

Our fork commit `7db6730` implements the two NV4097 restart-state methods and
incremental D3D12 indexed strip/fan assembly. Only those changes and its small
game-free assembler header are adopted here; the rest of the upstream backend
is not replaced. Disabled restart and an oversized sentinel for 16-bit indices
retain ordinary-index behavior, matching the existing generic dispatcher.
Strip winding and fan centers reset at cuts; assembly continues across draw
packets in the same BEGIN epoch.

`python scripts/check_rsx_restart.py` compiles the actual upload function with
synthetic index/vertex adapters. The old function fails: 15 references and three
sentinel fetches where the authored case requires six references and no sentinel
fetch. The candidate passes cuts, packet continuation, disabled/width rules,
fan assembly and winding. This does not test GPU pixels or all primitive modes.
Native evidence and the unchanged malformed-menu verdict are recorded in
[graphics research](research/GRAPHICS_AUDIO.md). No external PR was opened.

## Packed vertex fetch adoption

The legacy shared fetch now decodes format 6 as big-endian signed 11/11/10-bit
XYZ with W=1, matching the existing compact/live-draw decode paths. The change
is authored first on our fork commit `0b85442`, branch `codex/packed-vertex-fetch`; unrelated
vertex formats and callers are preserved. `python scripts/check_rsx_vertex.py`
compiles the production component with game-free memory/location adapters and
covers size-one packed input, signed fields, endian order, stride, MAIN/LOCAL,
frequency, disabled defaults and ordinary-float control. Native graphics
remain malformed after this correction. No external PR was opened.

## Fragment third-source absolute modifier

The curated fragment decompiler adopts own-fork commit `0d03c8b` from
`codex/fp-source2-absolute`: source 2 uses its own absolute-value flag at bit 18
of DWORD3. Passing zero to its decoder silently dropped that modifier.
`scripts/check_rsx_fp_source.py` compiles the real decompiler with authored MAD
instructions and checks absolute value, negation after absolute value, and an
unmodified operand. The preserved baseline fails; the candidate passes.
Both Windows and Linux CI run this contract. No external PR was opened.
The native menu remains malformed; this is a repaired instruction contract.

### Upstream recheck — October 12, 2026

Rechecked all 230 upstream PRs and 14 issues, including open and closed entries.
Upstream master remains `5244db92669b54831c6d3ebb7a96d58c4dbfa6df`
(October 7). No matching MotorStorm menu fix or native acceptance proof was found.
The relevant current proposals remain open:

| Reference | Applicable seam and present limitation |
| --- | --- |
| [PR 238](https://github.com/sp00nznet/ps3recomp/pull/238) | MAIN offsets use the IO table before a VRAM heuristic. Our resolver still has the old fallback. The selected ticket program and textures have verified LOCAL identity, so this does not explain their measured zero RGB; it remains a candidate for other assets. |
| [PR 215](https://github.com/sp00nznet/ps3recomp/pull/215) | FFmpeg H.264/MPEG-2 decoding proposal; relevant to genuine video, without MotorStorm playback proof. |
| [PR 240](https://github.com/sp00nznet/ps3recomp/pull/240) / [PR 242](https://github.com/sp00nznet/ps3recomp/pull/242) | Guest taskset corruption and committed-signal wake fixes. Reported Twisted Metal results justify separate semantic checks; they do not establish MotorStorm loading correctness or unpark retail mstream. |
| [PR 230](https://github.com/sp00nznet/ps3recomp/pull/230) | FP caller source capacity is already corrected locally. |
| [PR 221](https://github.com/sp00nznet/ps3recomp/pull/221) | Unnormalized texture coordinates in the register-file engine; current legacy D3D12 ticket samples already produce finite nonzero values. |
| [PR 213](https://github.com/sp00nznet/ps3recomp/pull/213) | Broad inFamous integration. FP edits include texture usage/WPOS handling; inspected VP edits add constant usage analysis. No repair of the measured zero ticket multiplier was identified. Its reported gameplay and frame rate are another title's claims. |
| [Issue 214](https://github.com/sp00nznet/ps3recomp/issues/214) | Killzone 3 proposals include packed FP operations, predication, gamma and LOD. Current predication already uses per-lane branches; the remaining proposals require focused evidence. The linked gist is a proposal, not a merged correction or MotorStorm result. |

Vulkan-specific image size, cube-map, stencil, HDR target and readback proposals
are not direct changes to the current legacy D3D12 path. No upstream changes
were merged or submitted during this recheck. Original captured shaders and
asset evidence remain private.


The exposure trace gives [open upstream PR #224](https://github.com/sp00nznet/ps3recomp/pull/224)
new relevance: it flushes host GPU surfaces before NV3089/NV309E guest-memory
transfers and uploads transfer writes. Its implementation is scoped to the
register-file engine and RGBA8, leaving legacy D3D12 unchanged. Native MotorStorm
now demonstrates an FP16 exposure surface whose GPU center is 1.0 while the PPU
reads zero from guest VRAM; see the graphics evidence. This is a related coherence
failure, but #224 is not an existing correction for the observed path. No full
upstream branch was adopted and no external PR was opened.


Typed CPU surface visibility is developed first on the own fork branch
`codex/cpu-surface-coherence`. New `guest_read_sync` API, D3D12 render-thread
service and pitched row conversion are authored here; they do not copy RPCS3 or
PR 224 code. Only corresponding reviewed seams are overlaid into the curated
backend, preserving earlier adopted fixes. The MotorStorm-only fastmem header
uses the same barrier and has a real old-header red/candidate green test.
Native GPU/PPU equality and restored content are recorded in graphics evidence;
correct placement and normal PLAY race acceptance are still absent. No external
PR was submitted. Private observers and original captures remain excluded.

Own fork checkpoint: [`77cab17`](https://github.com/robbe1912/ps3recomp/commit/77cab17),
`codex/cpu-surface-coherence`. Only authored API, backend integration, packing
and HLE fixture were committed; private trials remained untracked.

AA sample-memory extent is authored first on own fork branch
`codex/aa-surface-sample-layout`, checkpoint
[`12a158f`](https://github.com/robbe1912/ps3recomp/commit/12a158fc4bacf0c287ac204ff79fee7655276cae).
The curated overlay preserves its existing backend differences. The shared
helper and legacy D3D12 integration use the hardware AA grid and logical clip;
padding does not add visible columns. The actual target-sizing seam passes
the same authored fixture in both trees. Native placement gains and remaining
malformed geometry are qualified in [graphics evidence](research/GRAPHICS_AUDIO.md).
Issue 214's gist V5 concerns a separate register-file/Vulkan proposal; no gist
or RPCS3 implementation was copied. Private observers, generated guest code,
captures and helper trial files are excluded. No external PR was opened.

Explicit async task ownership (#78) was authored and tested first on own fork
`codex/task-dispatch-identity`, commits
[`f7104c0`](https://github.com/robbe1912/ps3recomp/commit/f7104c0a622388b19e49547265db2c62daf23026)
and fixture adapter `fda09a4`. Only the explicit dispatch API, task caller
arguments and captured-owner context reads are overlaid. The generic async
entry has no task owner. Curated argument handling, phantom registration,
diagnostics, host launch and task-return cleanup remain at their prior behavior;
the fork's different retirement policy is not imported. The authored fixture
compiles the complete dispatch functions against fingerprint/spawn adapters;
both old trees fail identity capture and generic ownership, and both corrected
trees pass. This does not prove genuine exit recycling, fresh task incarnations
or race entry. [Native evidence](research/HAVOK_REFERENCE.md#explicit-task-dispatch-identity-2026-10-13)
records separate observations. No external PR was opened.

## Explicit task exit and incarnation ownership

Issue #74 was developed first on our ps3recomp fork branch
`codex/task-exit-lifecycle`: `35239df`, fixture alias adapter `9bfe08d`,
and unlaunched-claim correction `8e40617`. The selective port adds a generic
lifecycle module, immutable generation/dispatch tokens, an actual task-EXIT
result bridge and generation-tagged LS storage. It removes the inherited
image22 first-EXIT exception. Ordinary entry return and generic STOP do not
retire guest tasks. Publication, signal-bit updates and retirement share the
lifecycle lock; guest changes use the existing VM write helpers. A failed or
unavailable initial dispatch releases its execution claim and leaves READY
for a subsequent legitimate attempt.

Curated argument fallback, phantom identity, runner options, counters and
unrelated diagnostics remain. The fixed host ownership/LS directory capacities
are replaced by stable allocated records. Fixtures exercise the actual module,
complete cleanup/API definitions and actual runner bridge with documented host
adapters; they execute no original guest instructions. No external PR was
opened. [Qualified native observations](research/HAVOK_REFERENCE.md#explicit-exit-incarnations-2026-10-13)
remain separate from race and graphics acceptance.

## Signed homogeneous vertex output

Issue 24's clipping correction was trialed first in the own task-lifecycle
fork checkout using an ignored copy of the curated vertex decompiler; the
tracked fork already preserves signed W. Compiling the real candidate and
replaying retained shader/upload/constants rejected behind-camera geometry
without changing the visible control. The selective native port removes only
the erroneous W-sign emission and replaces its unsupported sign-agnostic
comment; other curated viewport/depth behavior stays separate. The public
pixel-readback fixture is authored and contains no captured game payload.
[Native limitations](research/GRAPHICS_AUDIO.md#preserve-homogeneous-clip-w-issue-24)
include the remaining bike-loading emblem and stippled ground. No external PR
was opened.

### Event-triggered capture burst (issue 110)

The generic capture selector and atomic PAD_FILE event latch were authored
first on own-fork `codex/rsx-capture-burst` at `272bdd1`, based on
depth-contract `18061de`.
The curated copy preserves the same helper/event sources and authored fixture;
only the surrounding backend integration differs. No RPCS3 implementation or
game payload was copied. The fork CTest target and curated portable checker
exercise the actual helpers; native event-trigger evidence remains separate.
No external PR is authorized or opened by this work.


### B8 CPU readback checkpoint (issue 153)

The generic B8 readback fix comes from fork branch `codex/cpu-surface-b8-readback` through `558b56294233dd3f7c293f8a39519e3d33a4089f`, integrated in `combined` at `a90b39674e7e468dba50f8098a1e356758f519f1`. Guest B8 stores blue from the existing RGBA8 host storage. Guest row bounds and aligned host footprints are checked separately; other formats and explicit failures remain intact. The host-pitch helper is compared against D3D12 GetCopyableFootprints in a debug-layer WARP fixture. Modular and combined Linux, Windows, macOS and Vulkan CI passed.

The original-target checked Debug/O1 native build `f1d72246dc9cfc30134785274a8bb3fe7275425c6c51c590ede2860cd2bdedbb` reached normal PLAY and the race HUD under owned scripted navigation. Run `20261019T202344.869587Z` acknowledged one normal R2 probe from a freshly inspected HUD frame and recorded 119 successful B8 surface synchronizations, including the previously failing 2048-square terrain surface; no CPU-surface failure or deadline error was logged before guarded shutdown. This validates the native path for [issue 153](https://github.com/robbe1912/motorstorm-mv-recomp/issues/153). That build also contains retained runtime changes from its existing worktree; it is not a clean-main build of this port alone. Stable 30 FPS and full graphics correctness remain unverified.

## Indexed vertex decoding checkpoint (2026-10-20)

Imported per-callback strip/fan vertex reuse from fork modular commit `8ee85989d9c4d83bae2393f4b57946dbf96e35e7` and combined `e301bcd17ed80d62b523086d8c6835cf1f5d594c`; both passed all four platform workflows. Three cached vertices retain the complete emitted GPU stream, winding, restart/cursor state and count. Single-triangle callbacks keep the direct path. Main's existing capacity and error handling are unchanged. The authored fixture extracts the actual uploader and links the shared attribute decoder, checking formats/defaults/frequencies, splits, mutable data, exact bytes, bounded decoding and both fixed-buffer parity regions.

Five alternating checked-O1 fork helper pairs have matching output hashes: baseline median 2.495 seconds, candidate 0.986 seconds for 20000 draws of 512 indices; single-triangle medians are 0.248/0.249 seconds. These are helper measurements. Checked original-target native candidate `b7b897b156ed83fec9d64de24bc146039a778f2f75335046f7c3a16101512ea6` reached the original menu/PLAY and Grizzly HUD in run `20261020T142556.536251Z`; matched native samples hit cache lookup/copy. This binary includes retained runtime overlays and does not establish an isolated build of this port. Diagnostic API presents remained about 895 ms apart, with no controlled native speedup or 30 FPS claim. Material defects and source-parity work remain open; Vulkan and retail mstream remain parked.


## Long-lived decrementer arithmetic (issue 168)

The split-second RdDec arithmetic is a selective port of upstream `7e257f75`
(PR313), already present in own-fork combined baseline `326c28d`. The curated
copy had retained the older elapsed-nanoseconds multiplication, which overflows
after about 231 seconds. The authored production-case regression comes from
fork modular `codex/spu-decrementer-regression` at `f446ff9`; its curated copy
adds only the local Windows compiler-environment setup. Python arbitrary-precision
arithmetic independently checks 2117 reads, including overflow boundaries, long
elapsed intervals, final 32-bit wrap and lazy base initialization. The old native
case fails 2076 cases; the existing fork case and selective port pass all cases.

Five retained native reads at elapsed roughly 354 seconds fit the overflowed
arithmetic interval and fall outside the exact timer interval. Private raw contexts
and original instruction bytes remain excluded. Both compiled and interpreted
execution use this shared helper, so this finding does not establish the first
PM divergence in issue 9 or a native performance improvement. Native validation
of the corrected candidate beyond the old overflow boundary is recorded below.

Checked Debug/O2 native candidate `1c9704422fa27409da7ec224ded539ffffcc6b4717e891bb3073ed6015f54090`
in owned muted DX12 run `20261021T013053.174639Z` reached ordinary PLAY, the
original bike preview and live race HUD. Original menu frame 11 and race frame 68
were visually inspected; race rendering defects remain. Five complete context/LS
pairs at roughly 263 seconds all fit the independent exact-integer timer interval
bracketed by the pre/post QPC observations, beyond the former overflow boundary.
The five retained old native pairs fail that same oracle. Full LS is unchanged
across each new pair, only the destination GPR changes, and selected timer/event
fields remain unchanged. The controller closed through its explicit owned stop
marker. This checks the timer correction, without a 30 FPS or speedup claim.

## Exact SPU fingerprint cache (issue 172)

Own-fork modular commit `cc1fd7e` adds an opt-in, thread-owned cache for the
existing workload fingerprint; combined `9ddb580` also carries the portable
fixture corrections in `30bbbd4` and `3d42376`, overlapping-view checks in
`563e409`, and MinGW TLS isolation in `04b4a71`. Every hit compares the entire
buffer against an owned snapshot. Pointer reuse alone never establishes a hit.
Misses hash that snapshot with the unchanged legacy FNV basis and multiplier;
allocation failure visibly falls back to the original calculation. Buffers must
remain stable during the call, as before; this does not make concurrent writes
atomic. Eligible sizes are 4–256 KiB, with 32 entries and at most 4 MiB retained
per thread. Windows FLS and POSIX key destructors release the snapshots.

`SPU_FINGERPRINT_CACHE=1` enables the cache; the default makes no snapshot
allocations or byte comparisons. Optional `SPU_FINGERPRINT_STATS=1` emits bounded
cumulative per-thread counters. Authored production-path checks compare hashes
with an independent Python oracle, mutate interior and boundary bytes, exercise
eviction and visible allocation failures, and verify independent workers and
thread-exit cleanup. Historical uncached code fails the raw-call reduction check.
Five alternating helper trials over 20,000 stable 124,150-byte calls measured
median 2.1560 seconds uncached and 0.07182 seconds cached, with identical results.
This synthetic repeated-buffer test does not establish native FPS or a speedup
for the game.

Checked Debug/O2 candidate `ccdf1246c37fba3b2b5a0d458d0da15c2bf139ac23db90695dfc3404a9563a58`
completed muted DX12 ordinary PLAY, bike selection and a 60-second observed
gameplay window in run `20261021T030112.269572Z`, with PM interpretation enabled.
Original menu frame 11 and live race frame 104 were visually inspected; rendering
defects remain. Owned shutdown occurred after 353.484 seconds. An earlier attempt
stopped safely at an unmatched intro caption; a genuine observed caption variant
passed positive and negative checks before the successful replay, without changing
the ROI, threshold, input or once-only skip rule.

One observed cumulative cache state had 524,288 calls, 296,731 exact-byte hits,
6,300 misses and 221,257 size bypasses, with zero allocation failures. These sparse
cumulative samples are not exact gameplay-window totals. During 44.735 seconds of
CPU sampling, the busy `spu_async` worker still consumed 0.876 logical CPU, and
process CPU median was 5.195 logical CPUs. Thirty GPU 3D samples had median
16.778% activity. The last complete 30 seconds of API Present records had median
514.011 ms; the incomplete CSV tail is retained separately. These diagnostics
establish neither displayed/simulation FPS nor a controlled native speedup or
stable 30 FPS. Bounded identities, counters, CPU/GPU records and original observed
frames are preserved outside disposable runs. The later MinGW qualifier correction
leaves the MSVC branch used by this native candidate unchanged. Remaining limits
are tracked in [issue 172](https://github.com/robbe1912/motorstorm-mv-recomp/issues/172).

## Resident compiled lookup ownership (issue 174)

Own-fork modular `codex/spu-resident-lookup` commit `b7b125f`, merged into
`combined` as `ddf8f45`, makes `spu_lifted_lookup` honor the first containing
resident code span before the primary image. A missing resident entry returns
no function instead of falling through to overwritten primary code. The
curated port retains its existing relocation subtraction and primary-policy
base fallback outside resident spans; interpreter force/span/kernel guards
are unchanged. No external PR was opened.

The historical production lookup fails authored overlapping-image check 4.
The corrected fork passes 16 checks; the curated and native source variants
pass 18, including relocation, owner misses, boundaries, independent contexts,
ownership replacement and clearing, and unchanged null-context/wildcard
behavior. Function tokens abort if executed; these tests check selection,
not guest instruction execution. Existing wildcard diagnostics remain visible.

A separate lookup-only replay uses five preserved native contexts and original
registry address metadata: primary image 3, resident image 210 at LS `0x4000`,
size 75328, source EA `0x100e6f80`, relocation 0. At queried native entries
`0x16334` and `0x1635c`, the corrected lookup agrees with resident dispatch;
the old primary lookup misses. Captured post-read PC `0x16338` remains a miss
because it is not an original registered entry. Required PM interpretation
continues to block rejoin. These query results do not prove a first instruction
divergence, native gameplay, a speedup or stable 30 FPS. Private source-bound
results remain under own-fork `temp/issue9-dispatch-ownership`; follow-up is
tracked in [issue 174](https://github.com/robbe1912/motorstorm-mv-recomp/issues/174).

Checked O2/Ob2 DX12 candidate `77652f3c...85ac981` completed the existing
screen-gated normal PLAY route in muted run `20261021T111022.658573Z`.
Original main-menu frame 11 and live race frame 76 were visually inspected;
race rendering defects remain. The owned controller stopped explicitly at
303.281 s after its 60.5 s gameplay observation window. No fatal/assertion or
device-removal diagnostic was found. In the 44.548 s CPU sample, process use
had a 5.450 logical-CPU median and GPU 3D activity a 16.002% median/18.616%
maximum. The corresponding 42.109 s resource interval recorded 262144 bytes
of process read transfers, about 1.804 GB private memory and at least 17.835 GB
available physical RAM. Read transfers include cached/non-disk reads; these
counters do not measure I/O latency or VRAM budget. Eleven complete PERF
windows recorded 0--2 pipeline misses and rounded pipeline time of 0.00 s.
Their batch rates are not displayed/simulation FPS. This is one diagnostic
run with PM interpretation retained, not a controlled speedup or stable-30
result. Raw logs, identities, counters and selected original captures are
hash-preserved outside the five-run retention directory under private
`temp/issue174-resident-lookup/native-evidence`.

## Interpreter report ownership (issue 163)

Per-thread interpreter PC and instruction-count reporting comes from own-fork `codex/spu-interpreter-thread-stats` commit `0b03c7f`, integrated into `combined` as `326c28d`. The selective port updates the two definitions, public declarations and existing owning-thread consumers. Host budgets, guest instructions, errors and required PM interpretation remain intact. The payload-free real-interpreter test runs 401 authored IL/STOP programs across four workers, checking register values, program bytes, stop state and report isolation; source-audit CI runs the curated test on Windows and Linux. Native timing and the remaining performance limit are tracked in [issue 163](https://github.com/robbe1912/motorstorm-mv-recomp/issues/163); this change does not establish a speedup or stable 30 FPS. No external PR was opened.

## CPU surface request latency (issue 179)

Default-off `RSX_CPU_SURFACE_PROFILE=1` comes from own-fork
`codex/d3d12-cpu-surface-profile` production commit `3a7f7a3` and authored-fixture
clarification `c62fc8c`, merged into `combined` through `c81566f`. The selective
port retains curated device-error handling and adds request latency accounting;
it preserves synchronization, copies, GPU validation, errors and the 30-second
deadline. No external PR was opened.

`CPUSURFACE_PROFILE` fields are QPC ticks at the reported `frequency`.
`total = queue + service + return`; allocation, prior-fence, commands,
copy-fence, packing and other sum to service. Queue includes event creation
and scheduling before renderer service. Fence stages include host signal/wait
and status checks; they are not exclusive GPU execution. Packing includes Map,
CPU conversion and Unmap. Matched/hit/copy counters and full host/guest byte
counts distinguish unchanged generations from full-surface copies caused by
scalar reads. Direct requests have zero queue/return; shutdown completions
have zero service. Concurrent requests can overlap; totals are request wall
time, not exclusive frame or CPU costs.

`python scripts/check_cpu_surface_profile.py` compiles actual production
request/service code against an authored clock/queue model, checks emitted
phase sums and default-off clock behavior, and rejects clock-failure and
over-accounting controls. The copy stages in this fixture are modeled;
existing CPU-surface packing tests and identity-bound native observations
cover different requirements. Linux and Windows CI run both regressions.
Performance attribution and native evidence remain in
[issue 179](https://github.com/robbe1912/motorstorm-mv-recomp/issues/179),
with broader producer and sustained-30 acceptance in issues 155 and 27.

### CPU surface batch completion (#181)

Own-fork modular90bbae9 (fixture portability93a335a), combined621fcfa, adds CPU-surface service at the end of a submitted render batch, after captures, presentation and allocator/fence advancement. The message pump remains. Recording must be closed; existing generation/resource-state checks, command order, GPU fences, copies, deadlines and errors remain. This addresses queue delay measured under179, without skipping unchanged or changed reads.

Absolute QPC boundaries and client/renderer IDs supplement optional profile records. The authored regression compiles production completion/request/service functions, verifies a submitted model pixel and waiter event, and rejects premature recording/missing completion; default-off clocks and prior accounting/packing controls remain. This models scheduling, not an actual GPU. Own-fork focused Linux/Windows jobs pass; actual muted DX12 normal-PLAY validation is in progress on checkedO2/Ob2 EXE61d63b581a423ca8acca09ddc950fb11aa50c9c6424d29738001594fbef491fc/PDB931cb331424d6d5d20967877a11f193bb111f4cdf701ab97d8cd58f49cd4c51f. Native hierarchy/PM1/debug validation retained. No FPS or controlled speedup claim; see181 for outcomes and limits.
