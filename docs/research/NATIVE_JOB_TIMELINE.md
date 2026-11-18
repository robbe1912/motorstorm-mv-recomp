# Native visibility job timeline

Issue [219](https://github.com/robbe1912/motorstorm-mv-recomp/issues/219) remains
open. The goal is stable 30 FPS through normal PLAY on Windows DX12 and complete
typed native x86 game operations. This checkpoint supplies a bounded recorder
and original publication/marker bindings. It does not install game hooks,
capture a job timeline, attribute frame cost or establish a speedup.

## Why a policy return is insufficient

The [scheduling comparison](NATIVE_SCHEDULING.md) distinguishes the persistent
host pool from native game tasks. One policy invocation can process several
jobs. The selected job can also finish executing before its output transfers
and marker publication finish. A single pair of policy-entry/return timestamps
cannot resolve those intervals.

Read-only original analysis now separates these stages:

| Stage | Verified original identity | Observation still required |
| --- | --- | --- |
| Descriptor publication | PVS handler `0x87D858` calls through `0x87B814` to `MultiThreadSafeJobList::AddJob` at `0xC5C6A0`. | The successful 64-bit conditional store of the actual job header into an empty queue descriptor, not just function return. |
| Queue hint publication | The same AddJob path atomically maximizes the high halfword at queue `+0x10`, preserving its low halfword. | A separate successful 32-bit conditional store; descriptor and hint publication are distinct. |
| Requested lanes | The handler calls `SetReadyCount` through `0x87B854` to `0xC5BE20`, then the import trampoline at `0xD2A4E0`. | The real request and its owner/lifetime; inline guest publishers must remain visible too. |
| Host admission and execution | Current fork scheduler assigns a real policy to a persistent lane worker. | True eligibility, admission and worker start, separately from each selected job. |
| Selected running job | Policy running slot is LS `0x12E0`; its record is `0x1430 + 32 * slot`; physical lane is `0x1340`. | Running-record identity and generation at actual job entry. The newer claim index at `0x1410` is not this job. |
| Output/completion processing | Original transition `0x30B0..0x317C` moves the prior running slot into the store slot at `0x12F0` and calls the cleanup path at `0x3180`. | Execution end, pending output work and genuine release must be separate events. |
| Marker publication | Original code prepares the queue header, performs conditional MFC publication at `0x3330`, reads status and retries a failed store. | Only successful real commits establish marker publication; attempted writes and retries must not become completions. |
| Queue reuse | `JobListPrivate::ResetList` at `0xC5BF38` resets queue state and six lane counters. | A new queue lifetime/generation, including overlapping or uncovered resets. Marker values alone are reusable. |

The marker payload is the minimum marker among three remaining records that
match the selected queue, or `0xFFFF` when none remain. It updates that physical
lane's halfword at queue `+0x14 + 2 * lane`, preserving peer fields. This is a
queue progress counter, not a unique per-job completion message.

## Original evidence and coverage

The selected named-US ELF SHA256 is
`3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706`.
The connected REA provider is unconfigured and does not admit this PowerPC/SPU
target. The existing manual, read-only Ghidra bridge was instead used on a copy
of the saved project, following [the established workflow](TRANSLATION.md).
All nine original project files retain their hashes; the owned bridge shut
down and its process exited. No project/provider configuration was changed.

Independent ELF mapping and original-byte comparisons qualify every export:

| Original entry | Symbol extent | Ghidra exact coverage | Independent original decode |
| --- | ---: | ---: | ---: |
| PVS input preparation `0x87D348` | 984 bytes | 984 | 984 |
| PVS handler publication `0x87D858` | 372 | 372 | 372 |
| PVS wait `0x87D278` | 136 | 136 | 136 |
| AddJob `0xC5C6A0` | 136 | 36 | 136 |
| SetReadyCount `0xC5BE20` | 48 | 48 | 48 |
| Hint-max helper `0xC5BED4` | 68 | 68 | 68 |
| ResetList `0xC5BF38` | 156 | 156 | 156 |
| List initialization `0xC5D1C0` | 356 | 356 | 356 |
| ReadyCount import `0xD2A4E0` | 32 | 0 | 32 |

Ghidra's truncated AddJob flow and missing focused import export are retained
as coverage gaps. Complete independent linear decoding establishes the bytes
and atomic operations; it is not executed-path or ownership proof. Four actual
PPU thunks were also independently decoded to verify their destinations.

The raw policy source is guest EA `0x10135E00`, original file offset 16,539,136,
loaded at LS `0xA00`. The previously verified 168-byte dispatcher at LS `0x3008`
has SHA256 `796135f039c33420e25a13bca233d56e67e1f4a519f6206698747e09d66ee7ce`.
Across all 28 retained, SHA-verified worker contexts, all 2,064 words in
`0x1540..0x3580` match the original. The further raw candidate window has 138
unmatched words in `0x3580..0x37A8`; that staged region is excluded from original
code claims. The nearest preceding embedded SPU ELF was tested and rejected as
the policy owner. No missing match was repaired or treated as success.

An ignored private harness executes the original marker **arithmetic fragments**
with the production `spu_step` implementation. An independent scalar oracle
checks 4,096 authored record sets, all six lanes, three store slots, absent and
different queues, zero/sentinel markers and unchanged peer bytes. Deliberately
wrong header-offset and minimum-selection instructions both fail the specific
output assertion. Channel callbacks abort and none execute: this establishes
payload arithmetic, not GETLLAR/PUTLLC behavior, retries, whole-function
equivalence or live completion. An initial harness LS-pointer initialization
error was corrected before acceptance; failing logs remain in the packet.

The original files, generated instructions, saved contexts, read-only project
copy, verifier sources, build commands, hashes, logs and replay results stay in
ignored private packets under `temp/research/rea/job-lifecycle-20261023T195631`
and `temp/issue219-job-timeline`. Historical contexts correlate executing jobs
with unfinished waits; they do not measure current invocation mix or durations.
No new game run was needed for this checkpoint.

## Bounded recorder foundation

The authored [C/C++ API](../../vendor/ps3recomp/include/ps3emu/native_job_trace.h)
and [implementation](../../vendor/ps3recomp/runtime/diag/native_job_trace.c)
reserve immutable records with lock-free atomics, publish payloads with
release/acquire ordering and expose unfinished slots. Capacity is fixed at
creation, overflow never overwrites earlier events, and attempted/dropped
counts remain inspectable. Appending allocates nothing and performs no clock,
environment, formatting or file calls. A zero timestamp is explicitly invalid.

The owner supplies the clock domain, run ID, instance lifetime, dispatch and
queue generation. Storage does not invent those identities or dependencies.
Its live metadata is not an atomic final snapshot. Destruction requires all
producers and readers to be quiescent; setup failure must remain visible.
No recorder is created by the game at this checkpoint, so no new hot path,
environment option or scheduling behavior is enabled.

Run `python scripts/check_native_job_trace.py --mutants` to compile the actual
production implementation independently, compile a C++17 consumer, and test
16,384 concurrent authored events. A deterministic paused-writer seam checks
that a reserved slot is unreadable before payload publication. Four compiled
mutants must fail their own specific assertions: premature publication,
hidden loss, overwritten retained records and hidden invalid clock. These are
storage/concurrency checks, not an overhead or performance benchmark.

Fork-first commits and focused cross-platform CI are recorded in
[vendor provenance](../VENDOR.md). The production C/header are byte-identical
to the fork; only test/runner paths are adapted for this repository.

## Actual atomic-store observation hooks

The follow-up adds generic PPU32/PPU64 CAS and SPU conditional/unconditional
line-store observations. `PS3RECOMP_ATOMIC_OBSERVATION` defaults OFF; ordinary
builds preprocess out probe branches, buffers and clocks. An enabled build
still requires an owner to install immutable observers while producers are
quiescent. Installation failure must be reported. No game owner is installed
in this checkpoint.

PPU payloads use the actual CAS operands and returned observed value, in guest
byte order. Early reservation rejection remains distinct from a valid-memory
attempt and successful commit. SPU before/after payloads are copied under the
existing coherency lock; delivery follows unlock. A subsequent writer can
change shared memory without changing the retained observation. GETLLAR and
ordinary DMA are excluded from these store hooks. Existing notifications,
watch diagnostics, error reporting and reservation outcomes are preserved.

The owner supplies a monotonic clock and optional pre-copy filter. Clock and
delivery callbacks run outside reservation/coherency locks. Timestamp endpoints
bound the operation; they are **not exact commit instants or a total commit
order**. Raw saved PC/LR and context addresses do not establish instruction or
job lifetime identity. Filters must expose uncovered/excluded paths. These
constraints still apply when callbacks append to the bounded recorder.

`python scripts/check_native_atomic_observer.py --mutants --syntax` extracts
the actual production CAS/store functions and compiles them with authored
VM/reservation/diagnostic dependencies, in both build modes. It also syntax
checks the complete production SPU translation unit in both modes. Tests cover
success/failure, lost reservations, both scalar widths, all three SPU store
commands, invalid ranges/context/clock, rejected filters, lock release,
preserved peer notifications and a deliberate later writer. Five compiled
mutants must fail their specific assertions: false scalar completion, late
payload reread, hidden clock failure, false SPU completion and delivery under
lock. LLVM-MinGW functional checks and Windows SDK checks pass locally; this
is not full reservation-coherence, live timeline or capture-overhead proof.
Separately, the complete public PPU translation unit passes Windows SDK syntax
checks in both modes with the actual selected generated header read-only.
This is not a full target link or native run.

The public fixture explicitly retains curated-only watch/alias dependencies
and the existing line-hook notification path; it does not import the fork's
independent taskset notification. Selective runtime patches invert exactly to
the original public modules. Fork provenance and cross-platform checks are in
[VENDOR](../VENDOR.md).

## Execution observation checkpoint

The fork-first `PS3RECOMP_EXECUTION_OBSERVATION` option defaults OFF. Its public
runtime definition also reaches generated units compiled in the linked CMake
target; separately compiled units must use the same setting. The ordinary
build discards probe arguments, branches and clock calls. No game owner installs
an observer or captures a timeline yet.

Enabled observations cover actual interpreted control transfers and conditional
fallthrough, interpreter invocation, accepted native operation begin/end,
compiled return macros, selected dispatch after interrupt routing, and final
resolved indirect calls. The final resolver retains its required Clang
`musttail` call. Native admission and existing instrumentation guards remain
unchanged. A native END follows a valid continuation; faults/unwind do not
receive a fabricated completion event.

These boundaries have different meanings. Interpreter invocation can admit a
native operation before interpreting anything. A dispatch event precedes the
selected call, rather than proving its first instruction executed. Interpreted
control events identify the executed source instruction and resulting PC;
compiled returns lack precise source attribution. Raw pointers, image IDs,
saved PCs and accepted native logical PCs are not job/lifetime identities.
Uninstrumented units, direct calls and missing events remain coverage gaps.

Install/clear requires synchronized producer quiescence and immutable callback
lifetime. Callbacks must be concurrent-safe and must not mutate guest state,
reenter execution, allocate, format, perform I/O or take application locks.
Filtering runs before clocks and event construction; exclusions require explicit
coverage accounting. The owner supplies one clock domain and accounts for
invalid clocks, ordering, dropped data and capture windows.

`python scripts/check_spu_execution_observer.py --mutants --syntax` compiles the
actual public interpreter, observer core and return/dispatch macros with authored
streams and dependencies in both build modes. The curated drain differs from
the fork: its exact interrupt-selection/call slice runs inside an authored loop,
and the actual final resolver slice retains `musttail`. This is not full IRQ or
coherence equivalence. Unexpected channel/VM recovery services abort.
The public runtime uses its existing inline float helpers; the fixture does not
import the fork's separate floating-point implementation.

Eight compiled mutants must fail specific assertions: missing interpreted
control, forced interpretation, missing dispatch, missing return, wrong
interrupt-selected function, missing resolved call, repeated return-register
expression and hidden invalid clock. LLVM-MinGW functional and Windows SDK
functional/full-production syntax checks pass, including a C++ header consumer.
The existing hash-pinned pre-port equivalence, native-leaf state/FP/TLS/IRQ tests
and their negative controls also pass. Only observer additions are undone in
that reference reconstruction; its original digest is unchanged. The ownership
fixture passes 18 checks with its existing cross-image wildcard diagnostic
visible. These checks measure neither capture overhead nor game frame times.

## SPURS admission and worker observations

The default-OFF `PS3RECOMP_SPURS_SCHEDULER_OBSERVATION` option can expose real
instance reservation/result/closure, workload registration/removal, policy
admission and worker invocation/return. It assigns nonwrapping process-local
instance, workload-generation and dispatch identities. Exhaustion yields zero
and an explicit invalid-identity flag. A capture owner must supply a run identity
and one shared monotonic clock. Thread-local access identifies the current host
worker assignment; it does not establish that an arbitrary SPU context or job
belongs to it. A direct policy call outside the pool has no such assignment.

Admission metadata is copied under the existing scheduler locks and delivered
after their release. Its time interval starts before the admission pass acquires
the instance lock and ends after release. Multiple admissions share a pass; a
worker can begin or return before that pass is delivered. Ready/signal values
are sequential demand observations, not proof of job eligibility. Policy return
is not individual job completion. Failed or BUSY lifecycle API attempts are not
reported as completed transitions; successful instance closure retires its
remaining workloads. Filtering, clock failures, unknown bindings and missing
events must remain visible. Callbacks must not reenter or mutate the runtime,
allocate, format, perform I/O or take application locks.

The authored fixture executes the real scheduler and policies in both build modes.
It verifies physical lane and lifetime identity against the actual policy context,
reuse and exhaustion, direct-call absence, filtering, actual error returns and
same-thread lock witnesses. Nine compiled observer mutants and the three existing
scheduler regressions must fail their particular assertions. The test dependencies
are authored scaffolding, not proof of full game synchronization or capture cost.

## Remaining integration gates

1. Connect the atomic, execution and admission observations above to a capture
   owner and bounded recorder. Preserve native-leaf admission
   and all original failures. Event
   capture must not run guest work, allocate, format or take application locks.
   Qualify precise source attribution in interpreted and lifted paths: a lifted
   block's saved PC alone does not identify every channel instruction inside it.
2. Bind this game's original code, queue lifetime, selected running record and
   actual output release. Distinguish attempt/commit, policy/job and store/end.
   Uncovered inline publishers, reused identities, missing edges, clock
   failures, overflow and partial windows must remain explicit.
3. Exercise those actual hook paths and the game analyzer with authored
   wrong-owner, generation-reuse, missing-publication/completion, reversed-time
   and overflow controls. Storage tests alone do not cover these obligations.
4. Measure tracing overhead separately before one coordinated original-asset,
   muted, screen-gated normal-PLAY run. Retain unsuspended CPU/present timing
   before optional intrusive diagnostics; observe the original menu and race.
5. Choose publication-aware admission only if eligible work waits, or a complete
   typed PVS batch if execution/marshalling dominates. The existing native PPU
   scene transaction is a different operation. Never sum overlapping waits as
   exclusive costs or treat unknown edges as a complete dependency graph.

Stable30 and graphics acceptance (#27/#137), the critical producer's frame-time
cost (#155), and this timeline (#219) remain open. Vulkan and retail mstream
remain parked. Neither the recorder nor this static binding makes the game
faster by itself.

### Complete observation payload storage

The fixed job-trace record cannot hold an entire atomic observation. The new
bounded sized store accepts an owner-selected fixed payload size and preserves
each payload in one release-published slot, without fragments, allocation or
I/O on append. It exposes pending slots and saturating loss counters, never
reuses a slot, and requires producer and consumer quiescence before destruction.
The owner must define the schema, clocks, run and lifetime identities, and
interpret losses. The game-side controller below connects this store to the
startup and replay paths. The actual store fixture tests full authored atomic
snapshots, concurrent writers, pending publication, loss, counter saturation,
and odd-sized records; four compiled controls must fail specific assertions.

The game-side `job_capture` owner now connects the four installation points to
the sized store with one supplied clock and run ID. Each record includes a
thread ID and, when available, the current host-worker assignment. The latter
is not proof that an arbitrary observed context belongs to that worker. Failed
installation rolls back earlier installations; startup and shutdown require all
producers to be quiescent and no other observer owner. Optional owner-provided
atomic, execution, scheduler and queue-call filters execute before event capture. The owner
reports which filters were configured and saturating per-source exclusion counts;
excluded events are missing coverage, not proof of absent work. Filters must be
concurrent-safe and obey the observer callback restrictions. Null accepts all.
Finite capacity and loss must be accounted for in any capture.

The owner also provides a caller-thread private stream snapshot: a header,
indexed completed records and a footer containing the before/after counts,
pending slots, filters and losses. The reader checks the format, record indices
and total extent before delivering records. Truncated files and consumer errors
are rejected. The format uses the native ABI, has no payload checksum, and
`fflush` is not a durability guarantee. The caller owns the stream and must
close and independently preserve it. Capture-enabled startup and the owned replay
trigger now provide those integration points. The view remains non-atomic and cannot
establish missing job dependencies or a causal order.

An explicit visit API scans the initial reservation horizon and records pending
slots, consumer failures and metadata before and after the scan. Unexpected
append failures use a saturating counter; full-store losses use the store's drop
count. It is a live,
partial view; callbacks can arrive out of order, writers can complete after a
slot was scanned, and the layout contains native ABI fields rather than a
portable file format. The actual owner fixture checks concurrent complete
payloads, installation rollback, identity flags, loss and partial visits, with
five specific negative controls. A second fixture links the actual execution and
scheduler observer implementations; the atomic installers there are authored
test dependencies. A current capture-enabled game build, qualified game identities, overhead
measurements and a title trace remain required.


### Queue-call binding checkpoint

The provisional game adapter captures reset, initialization and AddJob call
arguments around the unchanged original functions. Selected original-US body
identities are pinned for base reset `0xC5BF38`, derived reset `0xC5D4C0`,
initialization `0xC5D1C0` and AddJob `0xC5C6A0`. The four functions share a generated translation unit. Binding preparation composes
verified recipes for that unit, keeps legacy observer recipes mutually exclusive,
and replaces the unit once in CMake. Unknown copied edits fail before writes.

The authored adapter checks disabled behavior, entry-captured arguments and
headers and raw entry LR, exception exits, eight simultaneous callers, unique call
IDs and ID exhaustion. Ten compiled mutants must fail, including bypassing the
derived reset observer and invoking its wrong original. The binding checker exercises
multiple functions and alternate recipes in one unit, compiled direct/table
callers, preserved originals and the actual CMake source-selection block.

These events identify host wrapper calls. Queue generations, inline publishers,
genuine completion and current live evidence remain integration work for
issue #219. The process owner must install and remove observers with producers
quiescent, and account for zero exhausted IDs and missing return events.


### Startup and replay capture wiring

`--capture-jobs` builds the three toolkit observation sources, the process owner
and all four verified queue wrappers. The build records those capabilities and
requires lifted SPU workloads. The launcher checks the selected executable's
record, clears inherited capture-directory state, creates a private run-local
directory and waits for the owner to arm before normal menu replay proceeds.
Setup failures and missing acknowledgments end the owned run visibly.

The owner starts before guest producers and uses QPC and host thread IDs.
Startup reset/init calls are retained in the bounded buffer. Publication,
atomic, execution and scheduler work wait for the exclusive `open` trigger.
Schema 5 retains raw
queue entry LR for later callsite qualification. The `snapshot` trigger writes a
create-new native-ABI file with record indices and before/after coverage counts.
The process-lifetime owner remains installed through producer lifetime.

`--job-capture-seconds` requests a finite 0.05..5-second window after an
independently observed replay target. Acknowledgments require complete lines.
Clock-valid opening bounds must be positive and ordered; their raw QPC values and
host request/acknowledgment times are retained in `job-capture/timing.json`.
Those bounds describe the host transition. Snapshot visitation remains partial,
and filters, pending slots, drops and append failures remain interpretation inputs.

Authored tests exercise actual owner/observer storage, concurrent calls,
installation rollback, exclusions, trigger failures, snapshots, reader truncation
and the actual PPU64 compare/exchange path. Launcher tests check selected-build
admission, inherited-directory sanitization, local output and recorded options.
CMake tests execute every observer-option combination and missing-SPU controls.
Offline summary and candidate analyzers preserve raw identities and incomplete
edges. Capture-enabled title overhead and a qualified publication-to-completion
span remain required before selecting an admission change or a complete native
PVS operation.

### Recorder-only overhead checkpoint

A private authored producer fixture exercises the actual owner/window, SDK
execution and scheduler notifications, atomic observation helpers and queue
wrappers. Atomic installation and memory producers are authored dependencies.
Each group offers six events and checks the original counter outputs. Checked
general O1 builds retain assertions. Closed, cold open, saturated and owner-absent
states check exclusions, delivered counts and intentional full-buffer drops.

Five alternating baseline/sharded executable pairs contain 600 checked trials.
The closed-state measurements contain 25 samples per variant and worker count.
For eight workers and 9,600 groups, observed elapsed median/range changed from
1.848 ms / 1.353..2.2934 ms to 0.3867 ms / 0.3563..0.6799 ms. For one worker
and 10,000 groups, it changed from 0.4911 ms / 0.3876..0.7786 ms to
0.6404 ms / 0.5175..0.8862 ms. The host had 12 logical processors and sampled
17% CPU use before the initial pass. Per-trial shard collisions were unrecorded.
The receipt and exact input/binary hashes are local at
`temp/capture-overhead/paired-result.json` and adjacent before/after reports.
These timings measure the authored recorder load. End-to-end game impact and
the production critical path remain unmeasured by this fixture.

Each exclusion source now has 64 cache-line-aligned atomic shards selected by
stable thread ID. Unknown IDs and collisions retain saturating atomic updates.
Metadata sums shards with saturating addition as a partial sequential view.
Eight simultaneous clients check all four totals with distinct and colliding
IDs. Four compiled controls reject one hot counter, omitted shards, wrapped
totals and wrapped increments. Existing owner, rollback, loss, partial-visit and
snapshot controls continue to run on both platforms.


### First owned title capture

Source `352db8c01521d47499864545ea5f576b6ba49fae` built capture-enabled checked
Debug with general O1 and renderer-specific O2. Executable SHA-256 was
`30d55111eaccaaf99692ca1902b3807d083e5fad806720b9f2598060e5b0daae`.
Run `20261116T170918.944029Z` reached the normal PLAY target through seven
acknowledged required inputs and one observed SONY skip. API validation was
disabled and required PM interpretation retained. The owned guard closed after
303.625 seconds with capture armed and snapshot written.

The 0.05-second capture request produced 65,536 complete stored records with
zero pending slots and zero unexpected append failures. Stored records comprised
65,524 execution, nine scheduler and three atomic observations. Their earliest
and latest observed ticks span 14.2641 ms. Snapshot metadata reported 425,393
drops before visitation and 486,834 afterward, with 490,929 and 552,370 attempted
records respectively. All stored record clock-validity checks passed. The
execution budget was dominated by interpreted controls from raw image 3 and
compiled dispatch/return observations from raw image 1.

Zero queue-call records were stored. Loss prevents inferring absent queue calls
or a complete PVS span. Queue generations and the critical producer remain
unqualified. This saturation motivated the execution PC selection below, with
selected PCs and exclusions retained for interpretation. End-to-end capture
cost, graphics acceptance, interpreter removal and minimum 30 FPS remain open.

Private snapshot, validated JSONL, summary, queue-call analysis, replay timing,
selected build identity and hashes are pinned under
`temp/runs/20261116T170918.944029Z/job-capture/`. The coverage receipt is
`temp/job-timeline-evidence/20261116T170918.944029Z/analysis.json`.


### Execution PC selection

The capture controller can freeze up to 32 explicitly selected raw source/target
PC values before installing producers. Its immutable filter performs bounded
comparisons without allocation, formatting, guest reads or runtime reentry.
The window rejects closed-startup execution events before invoking that filter.
Atomic, scheduler and queue streams retain their existing admission. Execution
rejections remain visible in the sharded exclusion totals. The snapshot schema
is unchanged; retain the launch PC list, armed count and selected build identity.

The launcher sanitizes inherited selection, rejects unsupported selected builds
and invalid/alignment/length/capture combinations before launch, and records
both numeric PCs and the canonical child environment. The build identity marks
filter support explicitly. Authored controls cover source/target/default paths,
maximum length, strict numeric parsing and unchanged state after invalid input.
Seven compiled filter mutants must fail. Actual Windows controller tests reject
invalid configuration, preserve a frozen filter after environment changes, and
expose rejected execution counts. Existing owner, queue, snapshot, binding,
launcher and SIMD controls continue to run. The filtered title checkpoint below
records current source volume. Title-overhead qualification remains pending.

The filter-inclusive authored fixture links the actual selector/window,
recorder, queue wrappers and SDK notification/storage code with checked general
O1, assertions and the Debug CRT. Five interleaved repetitions cover one worker
with 10,000 groups and eight workers with 9,600 total groups. Each group offers
one execution, one atomic, two scheduler and two queue-call events. Selection
covers the unfiltered path, a match in the last of 32 entries, and a 32-entry
rejection. The open rejection case stores five events per group. All 180 trials
validate counts, exclusions, deliberate saturated-buffer drops and unchanged
authored outputs. QPC covers worker release through joins, with separate worker
thread-cycle samples.

The pre-pass host CPU sample was 46.6% across 12 logical processors. The
eight-worker open wall medians/ranges were 3.5479 ms / 2.2678..4.1899 ms
unfiltered, 2.5091 ms / 2.2589..2.7074 ms for the last-entry match, and
1.9252 ms / 1.8326..1.9415 ms for rejection. Per-trial host load and shard
collisions were unrecorded. These data retain their differing coverage and
scheduling conditions; production timing and exclusive producer attribution
remain open. Private provenance, commands, input/binary hashes and all trials
are at `temp/capture-filter-overhead/result.json`, with grouped ranges in
`summary.json`.

The approved main-renderer integration retains snapshot FIFO ownership in the
early-flush scan. A regression first rejected submission driven by a request
behind a snapshot. The existing own-fork barrier fixes that case. Fourteen
prompt mutants, concurrent requests, capture/queue/binding/launcher controls
and serialized/overlapped WARP snapshot controls pass. The GPU fixture extracts
the actual drain selector and rejects an ignored-selection mutant.


### Filtered native-menu title checkpoint

The owned muted run `20261117T045348.949063Z` used launcher source
`5d8bf2a8228aa4536627375e9a1083d931d29cb5` and the preserved capture executable
`20dd52eaee7c66cdf0540f34d43b379f3ac51b9d419a222c1657b068fb0342bd`
from verified menu source `6c42e97eac5b8dc4c0b418ba35b8307410614f3b`.
All 34 recorded handwritten source hashes matched. Native startup reached PLAY
without opening-sequence inputs, followed by six acknowledged normal race-menu
inputs. The target/capture guard closed after 279.719 seconds. The inspected
race frame shows 00:03.00, LAP 0/2, POS 9/15 and AI vehicles ahead. Graphics
acceptance remains open.

Selected execution PCs were `0x30B0`, `0x317C`, `0x3180` and `0x3330`.
The validated snapshot contains 1,838 records over 0.5599999 seconds of stored
ticks, comprising 952 atomic, 250 execution, 402 scheduler and 234 queue-call
records. Dropped records, pending slots, unexpected append failures and recorded
clock/identity errors were zero. Startup and downstream exclusions remain
combined in the counters, and execution paths outside the selected PCs remain
outside this trace's coverage.

All 117 AddJob calls have consistent enter/returned pairs. The existing strict
analyzer finds 117 same-thread/context committed descriptor-store candidates.
An exploratory join also matches their ordered 32-bit hint updates, preserving
the low halfword and agreeing with the descriptor slot. Thirty-four calls have
entry LR `0x87D9A4`. Independent original-ELF decoding verifies the publisher's
call at `0x87D9A0` through thunk `0x87B814`, whose tail branch reaches
`0xC5C6A0`. Their candidate header is `0x40044480`, with descriptor slots 15..49.

The open window contains no ResetList or initialization calls. Queue-generation
history and selected running-job identity therefore remain unqualified. An
exploratory six-lane threshold scan produced zero ordered crossings for these
34 candidates under its unqualified header/threshold assumptions. The observed
marker-byte changes require lifetime and selected-job mapping before completion
or critical-path interpretation. Title overhead, producer attribution, minimum
30 FPS and interpreter removal remain open.

Private validated summary/events, candidate joins, original callsite receipt,
launch/build identities, screenshot and artifact hashes are pinned under
`temp/job-timeline-evidence/20261117T045348.949063Z/analysis.json` and the
associated run's `job-capture/` directory. Required post-native inventory was
attempted through the delegated worker, then completed read-only by the primary
agent after the worker hit its usage limit. Four worktrees, source changes,
shared inputs and protected evidence were retained.

## Main marker-wait span admission

The owned launcher exposes `--profile-job-waits` for issue 219. It admits the
selected executable's recorded profiling capability or exact reviewed legacy
adapter hash, clears inherited wait/profile selectors, and records native mode
and profiling in the launch packet. The existing adapter records completed wait
caller/object/owner/threshold/minimum and QPC bounds after genuine progress.
Actual launcher controls cover default sanitization, current/legacy admission,
unsupported/disabled selection and build capability recording. These spans can
be joined to the recorder clock once current ownership and queue generation are
qualified. The owned native-menu run `20261117T115751.061159Z` used launcher source
`50ba90c3f88601f875c3978eb79c54184be5a842` and the verified preserved
`20dd52eaee7c66cdf0540f34d43b379f3ac51b9d419a222c1657b068fb0342bd`
executable. Six normal race-menu inputs reached the target; the guard closed
after 366.828 seconds. The inspected race image shows 00:19.28, LAP 0/2 and
POS 10/15. The snapshot stores 16,395 records over 5.0584137 seconds, with zero
recorder drops, pending slots or unexpected append failures.

On main publication thread 26016, the clipped union of completed marker waits
at PVS caller `0x87D2D4` is 2.2890822 seconds, or 45.25% of this envelope.
The largest full completed PVS wait is 319.4676 ms. Vehicle caller `0x8AC670`
accounts for 0.5870457 seconds, or 11.61%, with a largest full wait of
33.6699 ms. The combined same-thread marker-wait union is 2.8761408 seconds.
Read-only Ghidra and 70 independently checked original instructions identify
`PVSPPUThread::Wait` at `0x87D278` and `SpuVehicleHandler::Wait` at `0x8AC610`.
Both actual thunk chains reach `0xC5C424` and preserve original completion.

The log contains 27,416 complete timing records and zero clock-error or
reference/fallback records. Parsing starts after the native marker because an
unrelated PM prefix can contain its own status field. Completed-only logging
leaves unfinished entry coverage open. Queue generation, selected job and
exclusive producer execution remain to be qualified. This single instrumented
window identifies the largest measured main marker-wait site; it leaves title
overhead, speedup and minimum 30 FPS unproven. PVS remains the first producer
under issues 155/219/282, with the vehicle batch tracked in issue 327.

Private launch/build/clock/decode/original verification and artifact hashes are
pinned at `temp/job-timeline-evidence/20261117T115751.061159Z/analysis.json`.

### Derived queue reset coverage

Original-code review after the profiled capture found that the selected ELF has
no direct branches to base `JobListPrivate::ResetList` at `0xC5BF38`. The derived
`MultiThreadSafeJobList::ResetList` at `0xC5D4C0` has five direct branch references,
including the TOC thunk at `0x675DF0`. Its 156 original bytes are identical to the
base reset, and all 39 instructions decode. Both clear descriptors, restore the
six lane halfwords to `0xFFFF`, and clear the taken/queued halfwords with the
original barriers.

The earlier capture CLI selected only the base reset, initialization and AddJob.
An actual selected-input preparation reproduces that omission. Queue observation
now also binds the independently verified derived body and forwards it to its
own preserved original. Its normalized generated-body SHA-256 is
`8018cd6ea22c22adf260a4eae47a1ed2056a9fabb3cac57fe21e16e93a8f0ce1`.
Authored direct and address-taken calls, disabled mode, concurrent calls, and two
derived-reset mutants verify the added path. Windows capture/adapter/binding
controls and the Linux adapter suite pass.

Private identities and preparation receipts are under
`temp/pvs-derived-reset-binding/`. Earlier live traces have incomplete reset
coverage. A rebuilt executable and startup lifecycle coverage remain required to
qualify queue generations and connect a selected PVS job to real completion.

### Startup queue history

The controller now opts into reset/init history before opening the measured
window. The generic window keeps its default closed behavior for other callers.
Both modes apply the original downstream queue filter. All records use the same
bounded owner and QPC clock. History can consume capacity, and its losses remain
visible through the existing counters. Wire fields and schema 5 stay compatible.

The actual integration fixture first reproduced missing startup reset/init
records. It now checks retained pairs before the opening bounds, rejected
publication/atomic/execution/scheduler traffic while closed, normal post-open
publication, and downstream exclusions in both phases. Three compiled controls
remove history, admit startup publications, or bypass the queue filter. A fourth
Windows control disables controller opt-in and must fail its pre-open record
check. Build identities record `job_capture_queue_history`, and the armed line
reports `queue_history=1`.

Consumers must retain launch/armed/timing data and scope measurements with the
opening QPC bounds. The complete record tick envelope includes startup history.
Queue generations, selected-job ownership and real completion still require
validated joins and coverage from a current executable.

### Owned startup-history run

Owned muted run `20261117T171503.565578Z` used source
`f29a05c13036d435b43416b7a4b9bae508628ac8` and executable
`8a94feb73cf5d35d3777f629068e358e0908a1e330287a3bfa771a644e3b9ee3`.
Native-menu startup and six observed race-menu inputs reached the target. The
owned target/capture guard closed after 276.203 seconds without a resource breach.
The inspected image shows timer 00:27.94, LAP 0/2 and POS 10/15.

The validated snapshot delivered 41,085 records with zero pending records,
buffer drops or unexpected append failures. Reservation counts changed from
41,085 to 41,195 during visitation, preserving its partial-live-view limit.
It contains five paired initializations, 15,095 paired resets and 645 paired
AddJob calls, with no partial or inconsistent call pairs. There are 30,114
lifecycle records before the opening bounds. Measured work uses the confirmed
opening QPC through the last recorded event, spanning 5.0736756 seconds.

Startup initialization maps the PVS queue object `0x40044410` directly to
physical header `0x40044480`. Its 3,432 observed resets retain caller
`0x67396c`. Six observed publication epochs each contain 50 descriptor/store-hint
candidates, including 34 PVS publications at caller `0x87d9a4` and 16 publications
from other callers. Each candidate agrees with the initialized header and lies
inside its observed lifecycle interval. These are observed wrapped-path epochs.
Coverage of every possible inline reset and selected-job ownership remains open.

Within the measured interval, main PVS caller `0x87d2d4` accumulated
2,355.2572 ms of clipped completed-wait union, 46.42 percent of the interval.
Its largest full completed wait was 453.4057 ms. Vehicle caller `0x8ac670`
accumulated 500.2052 ms, with a largest full wait of 46.7854 ms. Completed-only
profiling leaves unfinished-entry coverage open. Selected-job entry/exit,
exclusive producer cost, matched performance, minimum 30 FPS and interpreter
removal remain unqualified.

Private evidence is
`temp/job-timeline-evidence/20261117T171503.565578Z/analysis.json`, with original
logs/snapshot hashes, build identity, launch claim, initialization/reset/publication
candidates, scoped wait analysis and inspected-image hash.


## Selected policy observation

The original policy dispatcher writes its running slot at `0x303c` and calls the
job through `bisl r0,r5` at `0x3094`, with continuation `0x3098`. Its verified
168-byte dispatcher extent is LS `0x3008..0x30b0`. Supplemental schema-6 policy
records preserve that extent, the three raw records at `0x1430`, running/store
state, physical lane/module fields and preferred scalar register values.
Inspection runs synchronously in the execution callback and changes no guest
state. Private backing and copy clock bounds are explicit. These are sequential
observations requiring code, slot, generation and DMA/lifetime checks offline.

Authored tests reject wrong running/record/lane addresses, wrong preferred
register lane, admitted external backing, hidden clock failure and LS mutation.
Actual owner integration retains the ordinary execution record, checks optional
supplemental admission, and the Windows controller/decoder exercises the real
native snapshot and raw byte fields. A controller opt-in omission must fail.
Current module-body ownership, output DMA/final completion, exclusive producer
cost and title-overhead qualification remain open. The corrected title capture
below supplies dispatcher-call and publication candidates.


The first schema-6 title run, source `3350c26`, stored SDK lane 3 in the four
register fields. The runtime's preferred scalar is supplied by
`spu_preferred_u32()` from lane 0. Register fields from that run are invalid for
job interpretation. Its independently matching dispatcher bytes and raw LS
copies remain retained with this qualification. The corrected inspector uses the
SDK accessor. The authored fixture sets the preferred value through the runtime
constructor and places distinct poison values in lane 3, rejecting the previous
reader while also checking input preservation.


### Corrected selected-policy title capture

Owned muted run `20261117T184107.769729Z` used source `4cf2d9b` and executable
`87e527e040f925425804cf4f99cf8bc8979704ebcc936b0175046920508c32ad`.
Native-menu startup and six normal race-menu inputs reached the target. The
owned target/capture guard closed after 327.860 seconds. Schema 6 delivered
34,865 records, including 953 supplemental policy observations, with zero buffer
drops, pending records, unexpected append failures or recorded clock errors.
Reservation counts advanced to 35,475 during visitation, retaining the partial
live-view limitation.

All 953 dispatcher copies match the independently verified original 168-byte
extent. All 236 observed calls at `0x3094` have preferred r0 equal to `0x3098`
and masked preferred r5 equal to the reported target. The running-slot record
and initialized physical queue match 235 committed descriptor/publication
candidates inside their observed reset intervals. One call precedes the captured
publication boundary. There are 234 matching call/return-continuation candidates,
with explicit boundary gaps and zero observed reset crossings.

The 68 PVS publisher candidates at `0x87d9a4` select target LS `0x16270` and
return to `0x3098`. Their largest dispatcher wall interval is 317.2717 ms.
Thirty constraint-publisher candidates select `0x6100`; 120 vehicle-publisher
candidates select `0x20d40`. Concurrent interval totals overlap and include
scheduling and instrumentation. Module-body identity, complete inline-reset
coverage, output DMA, final marker completion and exclusive CPU cost require
further qualification before selecting a native replacement.

The confirmed after-open interval spans 1.0700984 seconds. Completed main PVS
wait union is 566.5768 ms and vehicle wait union is 145.0547 ms. These are one
instrumented diagnostic's completed waits. Matched performance, minimum 30 FPS
and interpreter removal remain open.

Private evidence is
`temp/job-timeline-evidence/20261117T184107.769729Z/analysis.json`, with original
logs/snapshot hashes, selected binary identity, publication/return candidates,
scoped waits and the first run's explicit register-field defect retained in its
separate evidence packet.

### Marker commit candidates and module identity

Further offline analysis of corrected run `20261117T184107.769729Z` connects all
234 call/return candidates to distinct cleanup observations and successful
128-byte conditional MFC commits at original PC `0x3330`. This includes all 68
PVS publisher candidates. Each link requires the same context, host assignment,
thread, initialized physical header, selected record and observed reset epoch.
The store changes only the publishing lane's halfword. Its value equals the
minimum remaining matching record index in the post-cleanup observation.
Authored alterations of context, host assignment, header, commit PC, failed-store
status and lane minimum reject the corresponding link. Commit and cleanup
indices are unique across the 234 candidates.

For the 68 PVS candidates, return-to-commit intervals range from 0.0257 to
0.0923 ms, with median 0.0435 ms. Selected-call wall intervals range from 7.2879
to 317.2717 ms. Publication-to-selection intervals range from 1.1095 to
321.4296 ms. These diagnostic intervals include scheduling and capture cost.
The observed commits narrow the remaining investigation to the selected
workload and its admission/execution. Output payload equivalence, complete
inline-reset coverage and exclusive CPU attribution remain open.

Private `completion-analysis.json` and `policy-completion-candidates.json` are
pinned beside the prior run analysis. Original cleanup bytes at LS
`0x30B0..0x33A8` were independently read from the selected ELF. Its publication
instruction is `0x3330`; ordinary claim commits at `0x2388` are excluded from
these links.

Schema 7 adds a bounded module fingerprint at the actual interpreted dispatcher
call. It reuses the SDK's pure header-span validation and existing fingerprint
basis, records the header and entry bytes, and retains clock bounds around the
whole read. The original PVS image's declared staging span is 75,328 bytes and
its expected registry fingerprint is `1D912920D52B9FE0`. The inspector checks
base alignment/range, magic/link base, span and entry correspondence before
reading that span. Sixteen compiled inspector controls cover the previous
slot/register/backing/clock invariants plus omitted module capture, wrong base,
entry bytes, fingerprint basis, truncation, trailer inclusion, invalid header, alignment and bounded short entries.
Windows controller/decoder tests exercise an authored valid module through the
actual capture path. The prior schema-6 decoder was preserved before rebuilding.
The rebuilt trace `20261118T095232.018909Z` used source `fe29d76` and executable
SHA256 `6122247025f1f9d1cc53950dcc1ae0026354b4b918c3c64101ee67586efefd16`.
It reached normal PLAY with six acknowledged inputs and recorded 32,139 events,
699 policy observations and zero buffer drops. The 174 selected calls joined
to published descriptors. All 68 PVS publications selected LS `0x16270` and
matched the original header and entry bytes. Twelve matched the registered
75,328-byte staged fingerprint. The other 56 had fingerprint
`F68BA71E8915A693`. Both fingerprints occurred across the same five SPU
contexts. Qualifying that variant requires locating the changed ranges and
establishing whether they contain instructions or mutable state.

Completed PVS waits covered 519.3137 ms in the 1.090671-second capture
interval. The policy copy and hash had median clock bounds of 79.35 µs and
73.35 µs for the two PVS groups, respectively. The 180 authored recorder
trials separately exercised a 75,328-byte hash and validated the recorded
fingerprints. Neither observation is a speedup comparison. The private
`job-timeline-evidence/20261118T095232.018909Z/analysis.json` retains capture,
build, cohort and measurement identities.

The selected original PVS body contains four stores to the 16-byte slot at
LS `0x16580`, inside the declared fingerprint span. On the selected ELF,
replacing the original slot's three zero words with `0x3F800000` reproduces
`F68BA71E8915A693` while retaining every other input byte. Schema 8 copies
that slot for the matching base, span and entry layout so the next live
capture can test this explanation against the actual bytes. Retain the schema-7
decoder for previous captures.

### Live mutable slot and compiled admission

Schema-8 run `20261118T103818.287257Z` reached normal PLAY and retained 40,186
records with zero observed recorder drops. All 132 selected PVS calls had
matching module headers and entry bytes. The original slot value occurred in
20 calls and produced `1D912920D52B9FE0`. The slot containing four ones occurred
in 112 calls and produced `F68BA71E8915A693`. Substituting each observed slot
into the original declared span reconstructed every live fingerprint.
These observations support mutable data as the explanation for both
fingerprints. The hash alone cannot establish equivalence of other bytes.

The same trace joins 462 selected call continuations to distinct successful
marker commits, including 127 PVS candidates. Six of 128 complete in-window
PVS waits join unique threshold crossings. The longest three all close on
descriptor 15, with waits of 191.0895, 190.2563 and 184.492 ms. Their observed
dispatcher intervals are 269.8232, 269.8825 and 257.6868 ms. The corresponding
waits finish 0.6211, 0.1436 and 0.0806 ms after the matching commits. These wall
intervals include scheduling and instrumentation. Each crossing also joins
one observed SPURS admission, worker entry and worker return by dispatch,
workload generation, worker thread, lane and physical queue. For the
three longest waits, publication to selection takes 0.7146–2.1531 ms and
the upper admission-to-worker bound is at most 0.0336 ms. Two later crossings
are selected more than 270 ms into an already-running assignment. These
intervals distinguish work inside a policy assignment from host assignment
startup. They leave job eligibility and exclusive CPU time unqualified.

The checked non-observer build from source `bd5a96fe` reached normal PLAY in
run `20261118T104237.760350Z` with `--native-owned-jobs`, policy interpretation
and marker-wait profiling enabled. Its sampled log records 436 lifted
dispatches to PVS image 210 at LS `0x16270`. The final 19.88-second persisted
window averaged 3.22 successful Presents per second. The repeated DMA guard
also reported 187 halts in policy image 3 at LS `0x2328`. Original disassembly
identifies that instruction as the command write for a 128-byte queue GET.
The same binary and replay with native-owned jobs disabled reached normal
PLAY in run `20261118T104905.516650Z`. Its final 19.80-second persisted
window averaged 1.82 successful Presents per second. The longest completed
PVS wait in the corresponding log bracket was 285.1942 ms with native-owned
jobs disabled and 56.2619 ms with them enabled. The repeat guard tripped 191
times in the reference run. These are two sequential diagnostic runs with
mutable race state and whole-worker admission enabled in the native arm.
Isolating the PVS effect requires controlling the other workloads and
validating outputs. The guard's critical-path cost and a matched speedup
remain unresolved.


### Current checked race diagnostics

The checked build from source `8c5c754` combines main's coherent prefetch,
eager submission and native policy service support with the PVS trace branch.
The following owned native-menu runs used executable
`bb8b6060746325b1b3dcf5a924b73ca57d9e8e92ecb7c183701eb20db2a94489`,
disabled capture observers and enabled native-owned jobs and marker-wait
profiling. Each reached the race HUD after six acknowledged inputs.

| Run | Additional setting | Final persisted Presents/s | Completed PVS wait | Completed vehicle wait |
| --- | --- | ---: | ---: | ---: |
| 20261118T221626.189910Z | Default | 2.92 | 3.084 s | 1.613 s |
| 20261118T222102.601745Z | Native policy services | 3.17 | 3.075 s | 1.872 s |

The wait totals use completed main-thread rows between persisted Present
markers, excluding the first possibly crossing row per caller. The brackets
are about 20 seconds. The service run verified its registered policy text
hash. The observed pair leaves a vehicle wait reduction unconfirmed.
The policy-image queue GET at LS `0x2328` triggered the repeat guard 214
and 179 times respectively. The guard's frame-time contribution remains
unmeasured.

Separate run `20261118T222516.846497Z` enabled CPU-surface profiling with
prefetch and eager submission at their default disabled settings. Within the
18.449-second main-thread QPC bracket, all 49 recorded main-thread surface
requests were two-byte reads at guest address `0xC2A34580`. They occupied
0.504 s including 0.286 s queued and 0.217 s servicing. The marker-wait
interval union was 3.815 s in the same bracket. The combined union was
4.319 s. This run supplies request timing on the integrated build.
The typed native deformation query was disabled, so its current handoff
cost remains open under #326. Each timed run has instrumentation overhead
and varying race state.

Private evidence is in the run-stamped folders under
`temp/job-timeline-evidence/`. The reports retain binary identities, matched
slot cohorts, committed marker joins, route receipts and artifact hashes.
