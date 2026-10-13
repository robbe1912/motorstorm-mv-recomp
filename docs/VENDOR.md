# Vendor provenance and upstream

Source: [sp00nznet/ps3recomp](https://github.com/sp00nznet/ps3recomp), snapshot base `268336af3a9f736835181ec09a7d88f695795e06` plus preserved local dirty runtime/lifter fixes. This is not a claim that local changes were accepted upstream. The full old checkout/history and migration hashes remain private.

Retain vendor/LICENSE and per-component notices. Root MIT preserves Ned Heller/sp00nznet credit. Standalone ATRAC source in third_party/at3_standalone remains LGPL2.1 with COPYING.LGPLv2.1; stb_truetype has its own MIT/public-domain notice; shared FFmpeg is external and its license obligations apply. Algorithmic AES/SHA/CRC/JPEG/ATRAC tables are implementation data, not game textures or firmware images. Behavioral RPCS3 reference does not authorize copying GPL implementation.

The NID hash suffix, import IDs, syscall constants and diagnostic addresses are interoperability/research metadata. They are not the separately removed decryption keys or captured instruction fixtures. Automated signatures supplement manual provenance review; they do not certify rights to every future contribution.

The public snapshot excludes nested Git/history, firmware/resource binaries, captured programs, generated lifts, unreviewed instruction fixtures and bundled platform keys. Tests are disabled with an explicit error if requested; see [setup](BUILDING.md). Runtime diagnostic target identifiers are research metadata, not game payloads.

Historical upstream reference documents and the hardcoded private PRX helper remain in a private archive rather than duplicated as current project instructions. The original source licenses, CONTRIBUTING and CONTRIBUTORS remain public.

Public vendor tools are limited to 14 generation/extraction dependencies, enforced by `VENDOR_TOOLS` in the staged-source auditor. Other research/port helpers, baselines, diagnostic output and generic templates remain in the same private reference archive. They are not required by the documented build/generation workflow. Any reused helper must receive a separate provenance review before publication.

Clean upstream observed `5244db92669b54831c6d3ebb7a96d58c4dbfa6df` (v0.13) versus local v0.11 base. Reuse selectively, preserve fixes and attribution. The snapshot of 18 open PRs / 7 issues is time-specific: recheck before contributing.

Existing [draft PR 230](https://github.com/sp00nznet/ps3recomp/pull/230), codex/d3d12-fp-source-capacity, commit `75a32692a6a4cb8f5a9217b78a0ab047c521d6c9`: a generic synthetic 4096-byte/256-instruction shader expands to 57382 HLSL bytes; caller capacity red 36 pass/3 fail → green 39/0, FXC ps_5_0/O3 pass, Release runtime build 0, CTest 5/5, diff-check 0. Last saved status OPEN/draft with empty check rollup: not CI success or merge approval. No game payloads in the PR. The local analogous fix is in graphics evidence.

PR 213 overlaps signal/event/context work; do not duplicate it. Issue 214 KZ3 findings, PR 215 real video candidate and PR 226 null-read diagnostics are triage candidates, not adopted fixes. Private upstream research artifacts remain in a private archive.

## Fork-first workflow

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
