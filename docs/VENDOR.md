# Vendor provenance and upstream

## Exact-byte fragment snapshot reuse (issue 213)

The generic `rsx_fp_snapshot.h` decision helper originates on own-fork modular
`b6b8c348f13b07e32575c69e34c7923cc70d1c02` and combined
`b9a4c5499267e60b92eebce084dee6e8b8722a00`. Focused Windows/Linux controls passed
on both [modular CI](https://github.com/robbe1912/ps3recomp/actions/runs/39958447051)
and [combined CI](https://github.com/robbe1912/ps3recomp/actions/runs/39958450484).
No upstream PR or title-specific rule is involved.

The native DX12 recorder compares the complete admitted snapshot bytes first.
Identical bytes retain the bound snapshot without decoding its structure again;
changed inline constants refresh it, while structurally recycled or malformed
live code retains the originally bound bytes. The existing snapshot ring,
address resolution and recording/replay lifetimes remain unchanged. Invalid
host snapshot metadata reports `FP_SNAPSHOT_ERROR` and aborts visibly.

The actual production helper and original decision agree on authored programs,
every-byte mutations, inline constants, structural changes, malformed live code
and program extents. Separately compiled historical eager-hash, blind-reuse and
refresh-recycled mutants must fail their specific behavioral/work assertions.
Both consumer CI platforms run these controls using their actual FP parser.

Five alternating checked-O2/Ob2/DebugCRT helper pairs, one million calls each,
measured identical 4096-byte authored snapshots at median 1884.164 ns before
(range 1878.084-1890.281) versus 92.9998 ns after (92.1099-94.2805). Verified
checksums and real function calls remain inside timing; count instrumentation
is absent. Structural decoding is replaced by exact byte comparison. The
4096-byte constant-edit paths overlap in timing; the 32-byte edit path instead
costs about 0.8 ns more. Private commands/source hashes/CPU times/results reside
under the fork's `build/fp-snapshot-tests`; the first short-window trial is
preserved separately. These are isolated helper measurements, not draw/frame
cost or gameplay FPS.

The archived issue209 renderer has three recovered
`structural_hash -> vp_fp_snap_for -> indexed draw` observations among 57 saved
stacks. This selected point evidence motivates the change without establishing
exclusive cost.

Native integration was checked in owned run `20261023T131716.848930Z`,
PID 15456, using original assets and the existing screen-gated PAD_FILE PLAY
route, with one observed Sony-caption skip. Original menu frame 11 and race
frame 73 (bike/opponents/HUD) were visually observed; geometry/shadow defects
remain. EXE `37e3483ca368443cbc61e1abc6a7354eea9587605a6e959dfd6fc22c767488df`,
PDB `17a3c4d0f3d139e5551e2520ab851e2c3b8d03dc5fee85680189827615b525b4`.
The five-step checked-O2/DebugCRT build restored configuration and preserved
all previous binaries. The controller exited 0 after an explicit owned stop
at 315.750 seconds; native return 1 is guard termination, not a natural-success
exit. The protected private packet has 4,461 files / 2,581,036,045 bytes;
rotation kept the latest five runs.

The unsuspended CPU window has 43 samples over 44.3471711 seconds. Process
median: 5.3905 logical CPU equivalents; `spu_async`: 39.0625 CPU seconds,
`frame_clock`: 33.21875, five main policy workers: 20.90625-22.25 each.
Thirty GPU 3D samples have median 23.0141%, maximum 30.4600%, no collector
error. Common-thread counters omit transient lifetimes, and utilization is
not causal frame-cost attribution. Fully contained main waits: 3,740 visibility
waits / 11.4229636 seconds (two crossing waits excluded), 440 vehicle waits /
4.9211536 seconds. The 110 two-byte CPU-surface reads total 5.8773668 seconds,
including 4.3211376 queued and 1.4712387 prior-fence seconds. These intervals
include scheduling/cooperation/synchronization, not exclusive CPU/GPU cost.

Separate later diagnostics have 301 cycles, one recorded suspend failure,
maximum 12.727 ms pause, 396 register-bound resident observations and 59
unfinished-wait register correlations. Archived PE-unwind replay recovered
305 partial walks with exact loaded PDB/CodeView identity; missing memory,
stopped walks and current-only DLL qualification remain explicit. Full stderr
scan found no error/fatal/failed/unhandled/unexpected/assert/overflow findings;
assertions and DX12 validation remained enabled. Native world retained 21
visible original fallbacks. Source/identity-bound analyses and hashes remain
private under `temp/issue213-fp-snapshot-equality/analysis`.

This is one unmatched native correctness run, not a controlled game speedup,
displayed-FPS result or stable 30 FPS proof. No frame-time or FPS gain follows
from the isolated helper result. #26/#27/#137 and the larger typed native game
rewrite remain open.

## Bounded policy admission integration (issue 209)

The previous joined-round consumer fails an authored actual-runtime test:
a blocked policy prevents an independent runnable producer from being admitted.
The selective port uses own-fork modular `codex/issue-209-native-admission-contracts`
at `bddee4c078cb55022545655a9493363f9b238bcc`, integrated into `combined` at
`09c97cc29eba90bbb12321f18082f75ac4ae8a0a`.
[Focused fork CI](https://github.com/robbe1912/ps3recomp/actions/runs/39941863558)
passes the actual scheduler and negative controls on Windows, Linux and macOS.
Fork master remains separate from this curated integration.

Native-build include follow-up `cc0bf49780e39f15588526e6569d71c0c5ebc8d7`
(modular) / `754dd6cfb138b7aff0b9bbce5c191f43ff0e503e` (combined)
resolves the naming header relative to its production module. It requires no
additional native consumer include path. [Follow-up fork CI](https://github.com/robbe1912/ps3recomp/actions/runs/39945465094)
passes on Windows, Linux and macOS; [consumer CI](https://github.com/robbe1912/motorstorm-mv-recomp/actions/runs/39945545271)
passes the actual scheduler/counter controls on Linux and Windows.

One coordinator admits work fairly across one to six persistent owned workers
per instance, with stable physical lanes and bounded contention. Only an actual
policy return releases admission. Guest execution and the existing periodic
publication delay occur outside scheduler locks. Ready counts remain policy-owned
requested demand; admission changes contention without consuming that demand.
This agrees with the public RPCS3 SPURS scheduler's requested-lane model
(`cellSpursSpu.cpp`, inspected blob `4be245810ffd118d7478b36cd8fd849ebc9390b6`),
without importing its implementation.

Per-instance resident-context references protect full workload incarnations.
BUSY teardown leaves live state unchanged; quiescent removal and instance
finalization retire contexts after owned joins. Exclusivity is unconditional;
the historical diagnostic switches that disabled context claim/run locking
are removed. Counter resets precede admission, including rejected runs.

The consumer's LF-normalized 25,399-byte execution region remains identical: FP/SIMD,
MFC/IRQ, boundary and native-leaf handling, ABI, budget and diagnostics stay in
place. Eighty-eight other function bodies, including taskset creation and
unrelated SDK implementations, remain identical. This is a selective scheduler
and ownership port, not wholesale replacement of the toolkit or game workloads.

`python scripts/check_spurs_scheduler.py --mutants` executes the real consumer
scheduler/policy/coherency code with authored modules. It covers producer
progress, capacity/contention, fairness, priorities, independent instances,
LS/TLS ownership, BUSY immutability, actual stop classification and retirement.
Three separately compiled negative controls must fail their intended behavior:
serialized admission, host consumption of demand, and stale rejected-run state.
`python scripts/check_spurs_policy_counters.py --mutants` retains actual
concurrent exit/poll/DMA checks in both intercept modes and checks every sole
productive lane and all-idle case with the persistent workers. Its three
historical controls still require the specific behavioral failures.
Windows and Linux CI retain source-only command/hash/diagnostic logs for five days.

Checked-O2 Windows DX12 run `20261023T114208.076688Z` uses EXE
`0ffcfaaaa0c4ae7ae69d4df46feb54492ef1ae55d430469627626da2c0d3acb2` and PDB
`4e88d028fd683b48e17ecb05e7d7a436a0a11ba02d603c322dc3a615c1fcbd57`.
Saved native frames 11 and 81 show the original main menu and race through the
existing screen-gated normal PLAY route. No desktop input was used. The owned
controller stopped explicitly after 315.922 seconds; native return 1 is guard
termination, not a natural successful process exit. Five rotating runs remain;
the source/hash-bound evidence packet is protected separately.

Before suspending diagnostics, 43 samples cover 44.6459943 seconds. Process CPU
is a median 5.0 logical CPUs; GPU 3D is a median 10.3537% across 30 samples.
Five named workers on the main instance each use 18.16-20.17 CPU seconds;
`spu_async` uses 39.015625 and native renderer thread `frame_clock` 33.3125.
Main-thread fully contained vehicle waits total 4.4079405 seconds; visibility
waits total 12.8062919. Ninety-five synchronous two-byte surface requests total
3.110211 seconds, including 2.3046809 queued and 0.7436323 prior-fence seconds.
These are wall intervals including scheduling and overlapping work, not exclusive
CPU/GPU costs. CPU read-transfer growth is 262,144 bytes; cached/non-disk I/O
prevents a preloading claim. This is an optimized Debug configuration with the
debug CRT, assertions and DX12 validation retained, not a Release baseline.

Subsequent separate diagnostics cover 284 cycles in 45.0544 seconds, with no
suspension errors and maximum pause 27.330 ms. Exact new-PDB schemas replace the
obsolete flat resident table; sequential worker/resident/register/original-code
checks yield 443 executing-context associations and 92 selected-record
correlations within unfinished waits. Offline raw-record validation additionally
checks every busy worker's native entry against its resident entry. The next
observer includes that check directly. Stable rereads cannot exclude ABA.
The existing checks and an additional diagnostic scan find no fatal/assert,
failed/unhandled or DX12-error reports; original fallback paths remain visible.

This accepts the bounded scheduler integration. Rendering defects (#137),
controlled performance comparison (#26), stable 30 FPS (#27) and the larger typed
native rewrite remain incomplete. These unmatched scene windows and diagnostic
point IPs do not establish a speedup, displayed FPS or exclusive frame cost.

## Concurrent policy counter isolation (issue 202)

The curated joined-lane consumer still used shared `g_spurs_pm_exited`,
`g_spurs_pm_polls` and `g_wws_batch_gets` state. An authored two-thread reproduction
using its actual policy runner and kernel intercepts failed: a second lane's
kernel exit made the first lane's unexpected stop return success. This is a
behavioral race, not merely inaccurate telemetry.

The existing own-fork TLS correction is selectively ported with its shared
declaration header from modular `codex/issue-202-policy-counter-declarations`
at `8b17ab7`, integrated into `combined` at `7e6bf70`. The fork's actual Windows
scheduler fixture and compiled serialized-admission control pass, as does
[combined CI 39934434638](https://github.com/robbe1912/ps3recomp/actions/runs/39934434638).
The game retains its joined-round scheduling: each worker records whether it
polled; the coordinator combines those results after owned joins for the existing
idle/burst decisions. Reading coordinator TLS alone would lose productive work
from other lanes. Counters clear before admission so rejected runs cannot report
previous productivity. Thread creation/join/close failures remain visible fatal
failures; no work is synthesized.

`python scripts/check_spurs_policy_counters.py --mutants` compiles the actual
consumer runner, scheduler round, channels, interpreter, MFC, coherency and drain
paths with assertions enabled. It tests compiled and interpreted kernel-service
intercepts, actual command GETs, independent stop/exit/poll/DMA state, all one-to-six
lane rounds with each lane separately productive, idle rounds and rejected-run
reset. Compiled mutants restoring shared counters, dropping worker productivity
or delaying admission reset must fail their specific behavioral assertion in
both intercept modes; compilation failures, unrelated crashes and timeouts are
not accepted. Exact commands, source hashes and complete diagnostics remain in
ignored `build/self-tests/spurs-policy-counters`. The same fixture passes against
the private consumer with its separate SIMD scope implementation linked, retaining
the original boundary/MFC safeguards and its unrelated source edits.

The Linux fixture uses the declared GNU pthread naming API and exact diagnostic
integer signatures. Its included production units receive explicit prototypes;
no compiler errors are disabled. The diagnostic implementation's self-contained
`<stdint.h>` include is selectively retained from own-fork `d0ac0d4`.
The curated watch hook uses the fork's existing `ppu_memory.h` declaration;
a conflicting redundant declaration of its 64-bit argument is removed.
CI retains only source-fixture logs and command/hash JSON for five days,
including failed builds; executable or game inputs are not uploaded.

This removes a prerequisite race for selective scheduling work. It does not
change workload admission/order, interpreter policy or tuning, replace a game
operation, or demonstrate an FPS gain. Native correctness and frame-time evidence
remain required; [issue 202](https://github.com/robbe1912/motorstorm-mv-recomp/issues/202)
tracks this correction, [155](https://github.com/robbe1912/motorstorm-mv-recomp/issues/155)
tracks producer attribution and [27](https://github.com/robbe1912/motorstorm-mv-recomp/issues/27)
tracks stable 30 FPS.

## Native Windows scheduler validation (issue 206)

Issue [206](https://github.com/robbe1912/motorstorm-mv-recomp/issues/206)
validates the fork's existing bounded persistent-worker scheduler before a
selective game port. Own-fork modular branch
`codex/issue-206-windows-spurs-tests` at `87a8133` contains implementation
`ec73ca6` and the registered-workflow integration; `combined` integrates it at
`bd4c149`. Fork `master` and upstream `master` were verified identical at
`a6d76c8`. This does not synchronize the divergent combined runtime wholesale.

The authored regression compiles the actual scheduler, policy runner, channels
and coherency code on Windows with assertions enabled. Owned thread handles
are joined and closed, and waits use elapsed deadlines. Out-of-scope taskset
and job-chain linkage traps abort if called. The tests retain producer/consumer
progress, bounded contention, stable physical slots, fair admission, BUSY
immutability, teardown/reinitialization, independent-instance/local-store
ownership and concurrent stop/exit checks. A compiled coordinator mutant with
only one admission slot must fail the producer-progress assertion; an unrelated
crash, compile failure or successful platform skip cannot satisfy CI.

The local Windows fixture and negative control pass. Hosted provenance is
[modular run 39932786504](https://github.com/robbe1912/ps3recomp/actions/runs/39932786504)
and [combined run 39932752929](https://github.com/robbe1912/ps3recomp/actions/runs/39932752929).
All six Windows/Linux/macOS jobs passed the native-leaf and scheduler
regressions, including required actual-execution markers. Logs and exact compile commands are
retained as five-day source-only artifacts. No original game input is used.

The fork's full Windows, Linux, Linux/Vulkan and macOS workflows are manually
disabled while Windows DX12 performance is the priority; the broad Windows
suite also builds the parked Vulkan backend. Focused DX12/SPU workflows remain
enabled, including the small scheduler portability matrix. These are reversible
repository settings, not changes to upstream or fork `master`. There are no
scheduled workflows in the inspected combined configuration. This validation
does not port the scheduler into the game or establish native compatibility,
a frame-time gain or stable 30 FPS. A selective port must preserve the private
boundary observer, SIMD scopes, MFC ownership and lifecycle safeguards;
[issue 202](https://github.com/robbe1912/motorstorm-mv-recomp/issues/202)
separately owns counter isolation and aggregation.

Issue [196](https://github.com/robbe1912/motorstorm-mv-recomp/issues/196)
adds an explicit native-leaf registration seam, developed on own-fork modular
branch `codex/spu-native-leaf-dispatch` through `d996c59` and integrated into
fork `combined` at `2a37eda`. The atomic head passed Windows, Linux and macOS
focused checks; the combined tree is identical and passed the local suite.
Registrations are copied before interpretation and then frozen. Guards must
prove private ownership and unchanged code/data, decline without effects, and
provide an exact instruction count and real continuation. No game identity,
automatic compiled handoff or interpreter-disable switch is added.

The curated port is selective: it preserves existing interrupt delivery,
forced-policy interpretation, rejoin behavior, statistics, and the legacy
global ceiling that counts an attempted step before decoding. The new optional
local ceiling counts decoded instructions; native plans must fit both limits.
Unregistered, rejected, traced, watched, interrupted and partial-budget work
continues through the retained interpreter. Callback code has process lifetime;
preparation is read-only/thread-safe, execution stays on its owner thread, and
invalid plans or continuations fail visibly. See
[`spu_native_leaf.h`](../vendor/ps3recomp/runtime/spu/spu_native_leaf.h).

`python scripts/check_native_leaf_dispatch.py` compiles the actual interpreter
and interrupt runtime against authored programs. It checks complete context,
FP/TLS, real interrupt delivery, changed code, nesting, four workers, stops and
intersecting budget limits; six unsafe dispatch/environment mutants and a faulty TLS
callback are rejected. A separately compiled, hash-pinned pre-port interpreter
matches 56 full-state/telemetry records byte-for-byte after normalizing only
the LS allocation pointer. These cover four FP modes, seven legacy ceilings,
and normal/interrupt paths. This establishes runtime compatibility for those
cases, not a game performance improvement. Application registration and checked
normal-PLAY shadow/native validation are recorded in [Native game operations](NATIVE_GAME.md);
stable 30 FPS remains unachieved. The private selective integration preserves
its boundary observer and SIMD scopes instead of replacing that runtime.


Issue [201](https://github.com/robbe1912/motorstorm-mv-recomp/issues/201) removes native-leaf diagnostic-option scans from the hot path. Own-fork modular `codex/spu-leaf-startup-options` at `a42bb551` passed focused Windows/Linux/macOS checks and was integrated into `combined` at `3dc12531`; the combined focused matrix and local suite passed. Seven option presences are captured once under the registration lock before release-publishing the frozen registry. Empty strings and `"0"` still mean present. Later environment changes do not reconfigure startup diagnostics; dynamic context, interrupt, DMA and watch checks remain live. A direct pre-freeze call-trace dump retains its old behavior without freezing registration. The actual-interpreter test counts real environment reads, exercises racing first callers, accepted/rejected warm paths and unchanged startup tracing after environment changes, and rejects a restored hot lookup. The hash-pinned original-runtime comparison still passes. The application separately caches startup policy-interpretation presence. Selective private integration preserves its boundary observer and SIMD scopes; no game identity is added to the toolkit.

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
This is fork-only; no external PR was opened. Local checkouts push to remote `fork`; `origin` push stays deliberately disabled.

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

Absolute QPC boundaries and client/renderer IDs supplement optional profile records. The authored regression compiles production completion/request/service functions, verifies a submitted model pixel and waiter event, and rejects premature recording/missing completion; default-off clocks and prior accounting/packing controls remain. This models scheduling, not an actual GPU. Own-fork focused Linux/Windows jobs pass; actual muted DX12 normal-PLAY validation completed on checkedO2/Ob2 EXE61d63b581a423ca8acca09ddc950fb11aa50c9c6424d29738001594fbef491fc/PDB931cb331424d6d5d20967877a11f193bb111f4cdf701ab97d8cd58f49cd4c51f. Native hierarchy/PM1/debug validation retained. Run20261021T175402.989970Z reached observed menu/race/HUD and an explicit owned stop305.875s/native1.77requests from one client are fully QPC-contained in44.863s, with5.283s request wall/3.974s queue/1.245s prior GPU fence. This is an unmatched diagnostic case; it does not prove a causal FPS speedup, and a loading request still queued5.293s. No stable30 claim; see181 for protected evidence and limits.


## Prepared native vertex uploads (issue 215)

The legacy DX12 upload fetched all16attribute slots independently for every
expanded vertex. Own-fork modular
`0161bb4127003db5102330abe741c90b152d59b1`, merged into combined
`bc080bf0ae2345e5b25a0b315763b406eeff274e`, adds a per-batch constants/active-slot
plan and typed16-float4 output. Both focused
[modular](https://github.com/robbe1912/ps3recomp/actions/runs/39966706794) and
[combined](https://github.com/robbe1912/ps3recomp/actions/runs/39966711278)
Windows/Linux runs passed. Six native upload functions prepare only after
valid-state admission; topology, indices, buffer ownership and capacities
are untouched. The position diagnostic remains once per fetched vertex.

Sparse layouts (at most8enabled nonzero-stride arrays) bulk-copy current
constants and invoke the actual scalar fetch only for active slots. Dense
layouts retain the original vertex loop. Guest array data/address translation
remain live per vertex, including context-DMA, page mappings, divisors, unknown
format diagnostics and unsupported/default behavior. The complete4667-byte
LF-normalized scalar function is unchanged (SHA256
`4415c168ed9ba051dd6a31766062796a02453da063d3c87eea7d1dcbcd17d2ec`).
Call `rsx_vertex_fetch_prepare` again after declaration/current-register changes;
there is no cross-draw data cache or new title-specific path.

`python scripts/check_vertex_prepared.py --mutants` compares complete outputs,
resolver traces and actual function calls across918format/index combinations,
live-byte edits, missing VM, refreshed declarations, zero strides, wraparound
indices, NaN/default bits, MAIN/LOCAL and both frequency modes. Three separately
compiled controls reject historical all-slot work, lost constants and stale
live bytes. Call-count instrumentation is inserted only into the checked test
copy; benchmark builds use uninstrumented production source/resolvers.

Five alternating checked-O2/Ob2/DebugCRT authored draw pairs include preparation
and verified real checksums. At4active arrays/1024vertices, median51.184ns per
vertex (50.637-51.791) became28.090ns (27.353-28.313). Constant-only and8-array
cases also improved; dense1024-vertex ranges overlap. Dense single-vertex
preparation adds roughly17-20ns in these trials. This is a native input-expansion
micro result with authored mappings, not a full renderer/game speedup. Timed
windows use20million vertices/side; Windows self CPU/wall time, compiler/source
hashes and commands are retained privately under fork build/vertex-prepared-tests.
Earlier short/instrumented trials remain separately identified. Host12logical
CPUs had11.98% total load before and23.57% after the final series; no game ran.
Native integration used checked EXE
`9a6b1977906bae5acf99708dd5638645198f832a76dd2637d174890358002ac4`
and PDB `af938a8ef2a5c0dbc3675ad2f6196f766e3e7fd26317324f8ff7922045ffb0ef`.
The five-step build restored configuration/preserved all prior binaries;
source preimages match measured213, and the inverse patch reproduces every
unrelated private RHI byte. Existing capacity/cache user work remains intact.

Run `20261023T171441.594042Z`, owned PID3004, used the existing screen-gated
PAD_FILE route and one observed Sony-caption skip. Original menu11 and race119
were personally viewed: bike/rider/opponents/HUD progress, with geometry/shadow
issues remaining. Explicit owned guard stop400.219s/native1/controller0 is
not natural-success termination. The private protected packet contains5709files,
3,500,906,437bytes plus complete hashes; latest-five rotation kept5/removed1.
Full stderr error/assert/fatal/failed/unhandled/unexpected/overflow scan is empty;
assertions/DX12 validation remain enabled and16original world fallbacks visible.

Unsuspended43CPU samples span44.6114993s; process median4.924logical CPUs,
async38.9375CPU seconds, frame_clock30.59375 and five main workers18.94-21.11each.
GPU30valid3D samples median17.7989%, max23.4546%, with no collector error.
All37683completed native waits validate; contained main visibility3264waits/
9.5135458s and vehicle380/4.477326s.95contained two-byte surface requests take
7.5613673s (queue6.1034666/prior-fence1.3939703); one crossing request is excluded.
These wall intervals include scheduling/cooperation/synchronization, and process
transfer growth262144bytes includes cached/non-disk I/O.

A separately admitted own-PID PresentMon2.6.0 trace has83rows/one swapchain;
82adjacent intervals lie wholly inside the unsuspended CPU window: API present
median446.3919ms (373.3846-711.6708), display-change465.227ms, GPU busy101.1931ms
and GPU wait293.05985ms. Original114-row intro trace is separately labelled:
its first wrapper falsely matched parent-shell script text. The corrected
wrapper requires exact cpu_window.py argv and owned run; no game restart,
existing-session stop, UI or privilege request occurred. Console-stats and
process-query privilege warnings are retained, with exact PID/application
validated. ETW cadence is not semantic frame identity, exclusive cost or a
controlled before/after improvement; it plainly does not establish stable30.

After those windows,276separately suspending cycles retain no reported context
errors and a132.546ms maximum pause. Exact-PDB/original-code analysis validates
515register-bound associations and91unfinished-wait register correlations.
280native stack walks remain partial/current-DLL-qualified; no missing local
modules. Of276FIFO declaration observations,239identical epoch/byte rereads
have0-8active arrays (89zero;150nonzero),37changed, no read errors. Raw bytes,
SHA256, exact PDB field extents and active lists revalidate offline. These
sequential declarations establish plausible sparse eligibility, not draw-weighted
usage, ABA-proof snapshots, function costs or frame savings. #155/#26/#27/#137
and complete typed game-workload replacement remain open.

## Bounded native job trace foundation

Issue [219](https://github.com/robbe1912/motorstorm-mv-recomp/issues/219) uses
authored recorder storage from fork modular commits
[`c902c728`](https://github.com/robbe1912/ps3recomp/commit/c902c728c08c06d981672c17b5697308e0defdc9)
and [`c60c6297`](https://github.com/robbe1912/ps3recomp/commit/c60c6297c8c65013a4bb993e686ff076de76148c).
The single combined branch integrates them as
[`a970623a`](https://github.com/robbe1912/ps3recomp/commit/a970623aabc1919fd7a3d8a793a8dd424e4bbfe5)
and [`f846155a`](https://github.com/robbe1912/ps3recomp/commit/f846155a823de90dfee082db61bf63df69771ae5).
Fork master remains separate; no upstream push or outside-game PR was made.

The production header SHA256 is
`afd83a8ec59a1d636399445e35bb6a30121da11e18dd392f771680ff7253188d`;
the implementation is
`1bcb4d6743515fb9157db18c46499b4f986e958555bb956d965fe8ff3c2fb668`.
Both are byte-identical to the fork. Public test/runner paths are adapted to
the curated tree; fixture data and implementation are wholly authored, with
no original instruction stream, guest context or asset in public tests.

The opt-in owner API allocates a fixed record array at setup and requires
lock-free counters. Append does no allocation, clock/environment reads,
formatting or file I/O. Release/acquire publication hides unfinished payloads;
overflow drops visibly and never overwrites retained records. Live metadata
is not a final atomic snapshot; quiescent teardown and owner error reporting
are required. No game call site creates a trace in this checkpoint.

`python scripts/check_native_job_trace.py --mutants` compiles the actual C17
implementation and a C++17 API consumer, checks paused publication and 16,384
concurrent authored events, and rejects four compiled mutants by their specific
assertions. Final modular
[CI 40003722104](https://github.com/robbe1912/ps3recomp/actions/runs/40003722104)
and combined
[CI 40003867170](https://github.com/robbe1912/ps3recomp/actions/runs/40003867170)
passed on Windows, Linux and macOS. Earlier foundational runs also passed.
This proves recorder storage behavior, not game binding, capture overhead,
whole-job tracing, exclusive frame cost or a performance improvement.

The [original publication/marker checkpoint](research/NATIVE_JOB_TIMELINE.md)
records independently checked original bytes, partial Ghidra coverage and a
private production-interpreter arithmetic replay. Original inputs and generated
instructions remain private. At that initial checkpoint, actual commit/worker/job
hooks, generation-aware analysis and a native run remained required; stable30 and
the full typed native game migration remain open.

### Actual atomic observation hooks (#219)

Fork-first modular branch `codex/issue-219-atomic-observers` contains
[`60bb1ae1`](https://github.com/robbe1912/ps3recomp/commit/60bb1ae10c81ffe8e2e8085e18377f0381ac8a44),
layered on the prior combined branch. `combined` fast-forwarded to the same
commit; master remains separate. No upstream push or outside-game PR was made.
Follow-up [`7aa4e904`](https://github.com/robbe1912/ps3recomp/commit/7aa4e904049f87a900d3de0b297a8186ae119711)
is integrated on both branches. The new complete-source Linux check exposed
a missing forward declaration before the curated policy trampoline calls
`spu_halt`; this declares the existing function without changing halt behavior,
disabling diagnostics or relaxing the compiler gate.
Modular [atomic CI 40009267498](https://github.com/robbe1912/ps3recomp/actions/runs/40009267498)
and [native regressions 40009267311](https://github.com/robbe1912/ps3recomp/actions/runs/40009267311)
pass Windows/Linux/macOS. Combined
[atomic CI 40010599712](https://github.com/robbe1912/ps3recomp/actions/runs/40010599712)
and [native regressions 40010599761](https://github.com/robbe1912/ps3recomp/actions/runs/40010599761)
also pass all three platforms.

The authored observer header is byte-identical to the fork Git blob, SHA256
`df7081a1582f3a384b94b0ac3ef1c77d450ffc27b7be459ce3d8d8e13495c64b`.
Only selected function deltas, installer blocks and includes were curated into
the PPU/SPU modules; inverse edits recover their original bytes exactly.
Existing public alias normalization, diagnostics, two-word PPU watch reporting
and line-hook notification remain intact. CMake receives only the default-OFF
diagnostic option and its compile definition, preserving the curated tests guard.
Runner paths and authored fixture dependencies account for these existing
public differences, including the absence of the fork's independent taskset
notification. No original program stream or guest capture is included.

`python scripts/check_native_atomic_observer.py --mutants --syntax` exercises
actual extracted production atomic functions with authored VM/lock/coherence
dependencies, checks full SPU translation-unit syntax, and rejects five mutants
at specific assertions. Local LLVM-MinGW and Windows SDK checks pass. These
checks establish observation behavior within that fixture, not full runtime
coherence, bounded recorder integration, job identity, live timing, capture
overhead or an FPS improvement. Both public audit jobs run the checks and retain
their authored logs for five days. The
[timeline report](research/NATIVE_JOB_TIMELINE.md) states remaining #219 gates;
no observer is installed by the game, and the ordinary build has no probe code.
