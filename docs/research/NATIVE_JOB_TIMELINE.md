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

### Scoped compiled PVS admission

The checked build from `c6a1553` reached the race HUD through six
acknowledged inputs in run `20261118T225659.963901Z` with
`--native-owned-jobs --native-owned-image 210`. It recorded 226 sampled
lift dispatches at image 210 entry `0x16270`. The shared gate restricts
policy-mode admission. Dispatch logging also covers calls outside that gate.
The final persisted cadence was 38 Present intervals in 19.94 seconds
with dispatch logging and marker-wait profiling enabled.

In that log bracket, the largest completed wait on the main thread was
`SpuVertexBufferThread::Wait` at return PC `0x727258`. Its 79 rows totaled
8.304 seconds on queue object `0x40044440` and physical header
`0x40048500`. Vehicle waits totaled 3.087 seconds and PVS waits 1.371
seconds. Separately, the schema-8 trace joined eight publications from
`SpuJobHandler<SpuVertexBufferParams>::Process` at return PC `0x7276CC`
on that header to selected entry `0xB850` and distinct real marker
commits. The module inventory identifies image 212. Issue #331 tracks
joining the producer to timed waits and recovering the typed vertex-buffer
contract. Matched timing and full native execution remain open.

The follow-up pair used the same checked binary and six acknowledged menu
inputs with dispatch logging disabled in both arms. The reference and
image-212 arms each recorded less than 0.02 ms of completed vertex-buffer
waits over their final roughly 20-second brackets. Completed PVS waits
totaled 9.542 and 9.219 seconds respectively. Issue #331 retains the earlier
vertex stall as a separate observation whose trigger remains unverified.

### US PPU reference for visibility output

For [issue #282](https://github.com/robbe1912/motorstorm-mv-recomp/issues/282#issuecomment-6780136092),
the selected debug-US ELF `3e68c72f…` contains a named PPU reference for the
visibility work. A private verifier decoded 2,065 instructions across five
routines, checked eleven control-flow edges and resolved three output
pointer stores through the original function descriptor's TOC.

At `SceneObjectList::ComputeVisibleSet` (`0x6BE7E8`), the original flag selects
the SPU submission through `PVSPPUThread::Process` or the synchronous
`sceneresources::ComputePVS` path at `0x8661C4`. The latter initializes
visibility state and enters the window loop. Separate original calls handle
frustum rejection and occluder containment. The output block pointer is
loaded from `PVSInput+0x1F8`. The initializer installs its first three
entries as the opaque, blended and Z-pass output pointers in shared PPU
state. Replay of the PPU reference needs isolated copies of that state and
the pointed-to inputs and outputs.

The verified routing gives us a second implementation for comparing ordered
visibility outputs. The private report is `temp/pvs-ppu-reference.json`.

### Native US visibility batch

The checked Windows build can opt into the native classifier after the selected
debug-US job's input DMA. The host classifier updates radii and writes ordered
lists, depth values and counters. The original epilogue and caller still publish
the results and complete the job. The live adapter retains the original path
when a batch could issue a 16 KiB output transfer.

The private differential replay matched 109 captured batches using scalar and
checked SIMD arithmetic. It followed the original epilogue and five caller
return paths through the first subsequent DMA command. A forced flush matched
the descriptor and payload for all 86 captured batches with primary output.
That check modeled the transfer, with live flushing batches still retained.

Two muted normal-PLAY runs used executable `3d0eb7f9…`, identical renderer
settings and six screen-gated actions. Their final 15-second Present windows
had median intervals of 371 ms with the classifier enabled and 624 ms with it
disabled. The native run logged at least 32,768 batch completions. Each arm ran
once and race state varied. Neither met the 33.3 ms frame budget.

A subsequent run with the settled ticket screen reached the race HUD in
239 seconds through six normal actions. Its final 15-second median was 386 ms
with the classifier on. In its final complete 12-second renderer trace, draw
preparation consumed 5.95 s. Vehicle and visibility marker waits overlapped
1.25 s and 0.78 s of the gaps between renderer batches. The race-start camera
sequence occupied much of the time after confirming the race. The startup
profile retains direct menu boot and observes normal PLAY. Follow-up issues
track [DX12 shader-resource setup](https://github.com/robbe1912/motorstorm-mv-recomp/issues/332)
and [vehicle completion](https://github.com/robbe1912/motorstorm-mv-recomp/issues/327).

### Texture residency and the remaining race waits

Two muted MOHAWK runs used executable `dc7efbb8…`, native visibility,
the settled ticket replay at stride 32, and the same renderer, texture and
marker-wait profiling. Each reached the HUD after six screen-gated actions.
The second run enabled the existing 512 MiB persistent texture cache.

| Observation | Reference cache | Persistent cache |
| --- | ---: | ---: |
| Time from launch to observed race HUD | 239.06 s | 160.33 s |
| Median Present interval in the final 15 seconds | 385.9 ms | 328.1 ms |
| 95th-percentile Present interval in that window | 551.1 ms | 409.6 ms |
| Texture misses in the last 80 reported renderer batches | 3,562 | 1 |
| Texture-call wall time in those batches | 4.350 s | 0.261 s |
| Nested SRV setup in those batches | 4.710 s | 0.590 s |

The last 80-batch windows include offscreen batches and end separately from
the Present windows. They recorded about 1.05 million texture calls per arm.
The persistent run peaked at 234.3 MiB of owned texture and upload allocations
with no resource failure or eviction. The runs are a single instrumented pair
with varying race state. Both remain above the 33.3 ms frame budget.

With residency enabled, the last complete 12-second renderer trace spent
2.00 s in the renderer and 10.00 s between renderer batches. Completed
main-thread marker waits overlapped 5.71 s of those gaps. Visibility accounted
for 3.07 s, vehicle completion for 1.90 s, and vertex-buffer completion for
0.74 s. The rest of the gap still needs attribution. Use the persistent cache
for the next observed US performance run, with the reference mode available
for matched checks. See [texture residency](https://github.com/robbe1912/motorstorm-mv-recomp/issues/291)
and [SRV setup](https://github.com/robbe1912/motorstorm-mv-recomp/issues/332).

### Native US visibility workspace initialization

The next bounded #282 replacement clears the selected visibility job's own
68,016-byte workspace before its original constructors and parameter DMA.
The original loop executes 17,006 instructions per admitted dispatch. The
adapter uses the existing full module fingerprint, verifies the preceding
branch and register bounds, and preserves the remaining register, channel,
interrupt and completion state. Its counted plan retains exact guest step
accounting and the original continuation.

Private differential replay matched all register and local-store bytes across
109 captured states. It preserved the captured relocation register, whose
unused lanes differ from its effective-address lane. Mutated module bytes,
address bounds, address-lane relocation and unsafe execution state declined
admission. The public authored fixture checks the clear bounds and full
context preservation without distributing original game bytes.

This removes one interpreted setup loop. It does not replace the remaining
input processing, occluder setup, classification fallbacks or job completion,
and it does not establish a repeatable gameplay speedup.

An observed debug-US run with executable `fe71a5bae7da15f8` reached the race
HUD through six acknowledged normal menu inputs. The initializer completed
at least 25,344 times; the run remained muted, with no resource breach or
failed DX12 Present. The HUD appeared after 257.7 s. The final 15 s contained
43 Present intervals, with a 345.7 ms median and no interval at or below
33.3 ms. This single diagnostic run provides no evidence of an end-to-end
improvement and does not satisfy playability acceptance.

The checked build retained native and renderer optimization, batch GPU
timestamps, persistent 512 MiB texture retention and the recorded 4 GiB commit /
2 GiB physical-memory reserves. Original-loop and live validation reports
remain private at `temp/pvs-workspace-validation.json` and
`temp/pvs-workspace-live-validation.json`. Input processing and occluder setup
remain the next #282 contract boundaries to attribute before another rewrite.

Private evidence is in the run-stamped folders under
`temp/job-timeline-evidence/`. The reports retain binary identities, matched
slot cohorts, committed marker joins, route receipts and artifact hashes.


### Native US occluder plane preparation

The current #282 replacement prepares one aligned occluder after its input
DMA, from staged `0x50e0` to `0x5404`. It builds face orientation, boundary
edge parity, normalized edge planes and the final face plane in original
order. Native arithmetic retains the SPU estimates, refinement and fused
operation order. Original next-object DMA, sorting, epilogue and job
completion remain in control. This is CPU visibility work, separate from the
renderer's CPU vertex expansion and GPU queue budget.

Admission checks the entire original US module on every object, folding
64-bit words and excluding only the existing mutable orientation slot. It
also checks the post-DMA edge, aligned-mode registers, stack and geometry
bounds. At most 17 edges are admitted so edge planes and the final face plane
fit before the output record's metadata. Unsupported layouts, alternate
alignment and unsafe IRQ/reservation states retain the interpreter. The
unbudgeted leaf declines budgeted/stopped interpreter invocations through the
shared runtime contract. The existing batch opt-in enables this stage;
`MS_NATIVE_VISIBILITY_OCCLUDERS=0` retains it for comparison.

Private normal-route capture `20261119T180552.006771Z` supplied 96 nonempty
entries with two to five faces and five to eleven edges. Independent execution
of original bytes used 746 to 1,383 instructions per object. Scalar and SIMD
native execution matched every local-store byte for all 96 entries; 93 also
matched a recorded original exit. Production-adapter checks covered the same
states, whole-context preservation and read-only admission mutations. A
167-instruction continuation analysis confirmed all 34 live registers agree
through the next input boundary or the original caller's next argument setup.
Temporary full-state capture hooks were removed before the production build.
Authored public cases cover geometric plane constraints on both camera sides,
edge parity, reserved metadata and transactional rejection without game bytes.

A CPU-only replay used five alternating samples per implementation, each with
960 executions over the 96 captured inputs. Both arms used `/O2` and the
checked CRT. Production native admission, full-module hash, FP scope and
callback took a median 10.51 microseconds per object (range 10.29-11.24),
versus 38.12 microseconds (35.60-38.50) for the original production interpreter
run-until path. Outputs and live loop registers were checked after every
execution; the first output plane was poisoned beforehand to detect skipped
work. No native game or build was active; host CPU activity immediately before
the short replay was 30.3%. These are stage wall times, not exclusive CPU
attribution or evidence of a repeatable frame-time improvement.

Production executable `a96cb20da3f177bd` completed normal PLAY in private run
`20261119T182927.541397Z`, with six screen-gated inputs and 60 seconds of target
observation. Race HUD appeared at 198.84 seconds; at least 2,072,576 native
occluder preparations and 48,384 native classifiers executed. The run was
muted, with no resource breach or failed DX12 Present. Its final 15 seconds
had 40 Present intervals: median 399.9 ms, p95 477.8 ms and maximum 501.2 ms;
none met the requested 33 ms ceiling. This later race window is not a matched
comparison to the earlier 18-second observation, and establishes no overall
frame-time improvement.

In the final 12-second renderer bracket, 10.496 seconds were between batches.
Completed main-thread marker waits overlapping those gaps covered 3.540
seconds for vertex work (`0x727258`), 2.122 for vehicle work (`0x8ac670`) and
1.272 for visibility (`0x87d2d4`), with 6.946 seconds combined. These are wait
latencies, not exclusive CPU costs. Timestamped direct-queue work had a
32.987 ms median per complete Present group, with 14 of 29 groups over
33.3 ms; other GPU and CPU work remain separate. The current leading marker
stall is vertex work, requiring #155 priority selection and its own producer
contract rather than further speculative visibility micro-optimization.

Private evidence remains in `temp/occluder-replay-validation.json`,
`temp/occluder-live-register-proof.json`, `temp/occluder-benchmark-report.json`
and the run directory. Stable native PLAY against the requested 33 ms ceiling
remains unachieved.


### Explicit particle threshold activation

The producer investigation found that executable `a96cb20da3f177bd` had
`native_particle_thresholds=false`. The typed #204 operation existed, but this
binary could not execute it. The supported runner now provides
`--native-particle-thresholds 0|shadow|1`, with build capability/hash admission,
explicit inherited-environment override and launch identity recording.
Default reference behavior and unsupported-state fallback remain available.
Actual-source admission tests cover 1,728 mode combinations and reject an
inherited particle selector; the 8,192-case scalar oracle, its four unsafe
mutants and the source-binding output-preservation checks pass.

Build `06eac2623586ac49` enables the existing threshold operation alongside
native visibility preparation. Muted shadow run
`20261119T191740.590634Z` completed at least 4,096 whole-context comparisons
against original instruction execution, representing 3,072,000 original
instructions. No parity error was reported. Unsupported numeric inputs and
foreign code retained interpretation. The owned run stopped explicitly after
135.2 seconds; it is a semantic diagnostic, not a performance sample.

Normal PLAY run `20261119T192213.561155Z` used the same executable in native
mode, six screen-gated inputs, checked selective optimization, native depth,
persistent 512 MiB texture retention, batch GPU timestamps, job/renderer
profiling and 4/2 GiB commit/physical reserves. It reached the race HUD at
163.3 seconds and ended at 223.8 seconds after a 60-second observation. The
inspected frame shows the player, opponents and advancing race HUD. It was
muted, with no resource breach or failed DX12 Present. At least 599,040 scans
executed natively, accounting for 449,280,000 original instruction equivalents.
The last 15 seconds still had a 341.8 ms median Present interval, 400.1 ms
p95 and 461.5 ms maximum over 44 intervals; none met the frame budget.
This instrumented trial establishes no repeatable end-to-end speedup.

The fixed HUD+20-second capture delivered 43,043 records without pending
records, drops or append failures. Its 593 selection joins, 589 continuations
and 588 completion candidates yield ten uniquely joined vertex-marker waits.
The longest is 38.8572 ms: 30.3297 ms precedes selection, the selected vertex
call takes 8.2938 ms, return-to-commit takes 0.0253 ms, and observed completion
follows 0.2084 ms later. In the same context/host dispatch, a preceding
particle-system call spans publication and lasts 246.1713 ms. Publication to
vertex selection is 130.7292 ms; host admission itself is 0.0174 ms.
These are wall-time/lifetime bounds, including scheduling; publication alone
does not establish input readiness. The remaining upstream particle operation
still needs a larger typed producer boundary. Smaller tail vertex waits do
not establish that the long frame gaps are solved.

Private evidence is run-local `particle-shadow-validation.json`,
`particle-native-validation.json`, and
`job-capture/particle-upstream-stall.json`. Full graphics/playability and
the 33 ms goal remain unverified.

### Native engine comparison and particle producer boundary

A native engine comparison is useful at the level of data flow and scheduling.
MotorStorm already has an engine designed for Cell/RSX. Compiling parts of its
implementation for x86 retains guest register and memory semantics, local-store
buffers, DMA, policy scheduling and completion protocols. A typed native leaf
removes instruction dispatch within its extent; its surrounding pipeline can
remain expensive. Rust or C++ alone does not remove that pipeline.

The relevant reference practices are explicit data access and parallel systems
in [Bevy ECS](https://bevy.org/learn/quick-start/getting-started/ecs/), batching
and infrequent late waits in [Unity's job-system engineering notes](https://unity.com/blog/engine-platform/improving-job-system-performance-2022-2-part-2),
and lower-level asynchronous servers in [Godot's performance guide](https://docs.godotengine.org/en/stable/tutorials/performance/using_servers.html).
Godot also explains how queries that force server synchronization can stall
pending work. These practices are architectural references, not measurements
of an equivalent MotorStorm scene in those engines.

| Boundary | Current cost to inspect | Native target |
| --- | --- | --- |
| Work unit | Interpreted job body and guest policy surrounding small native leaves | One particle vertex-buffer operation over a meaningful batch |
| Data | Guest-endian loads, local-store scratch and transfer setup | Explicit input/output arrays with conversion at their ownership boundary |
| Scheduling | Publication, worker admission, output transfer and polled markers | Host dependencies with real output completion preserved |
| Rendering | RSX replay, CPU vertex expansion and surface synchronization | GPU-ready buffers and supported GPU decoding, tracked separately by #232 |
| Qualification | The current occluder leaf fingerprints the module per object | Wider qualified operations; cached identity requires a proved ownership/invalidation contract |

The measured limit is still frame time. In the final 12-second bracket of
`20261119T182927.541397Z`, 10.496 seconds were between renderer batches and
6.946 seconds of those gaps overlapped completed main-thread marker waits.
The remaining gap is unattributed by that join. Median timestamped direct-queue
work per complete Present group was 32.987 ms, with a 101.484 ms maximum.
CPU and GPU costs can overlap and must not be added as independent frame costs.
Both the long CPU-side path and the GPU tail need improvement for stable 33 ms.

Under #331, distinguish these falsifiable explanations before changing the
particle producer:

1. Interpreted execution dominates: selection-to-return remains large after
   admission, and replacing the whole operation reduces that same workload.
2. Queue admission dominates: publication-to-selection is large relative to
   execution; another small arithmetic leaf leaves the main wait intact.
3. Transfer or synchronization dominates: output becomes usable substantially
   after computation; preserve the real dependency while removing redundant
   conversion, copies or synchronization inside the replacement boundary.
4. Diagnostic configuration dominates: matched capture-off, logging-controlled
   runs materially change cadence. Checked selective optimization and replay
   microbenchmarks do not establish optimized native PLAY performance.

The first follow-up capture, `20261119T184352.014556Z`, retained 44,150 records
without drops or pending records. It joined 17 vertex publications to selected
calls and returns, with selected-call wall times of 0.893–28.324 ms and a
9.001 ms median. Those wall times include host scheduling. Completion joining
remained unproved because its execution filter omitted cleanup boundaries;
this capture cannot decide the full wait's cause. The corrected private plan
requires both `0x3180` and `0x317c`, as well as call/return boundaries, and waits
for an observed race HUD followed by an actual vertex wait of at least 80 ms.
The incomplete historical selector set is rejected before launch.


The corrected run `20261119T185643.218172Z` opened after an actual 109.894 ms
vertex wait, 13.766 seconds after HUD observation. Its snapshot delivered
40,886 records with zero drops, pending records or append failures. The full
pipeline joined 553 publications, 551 call continuations/completions and eight
unique real vertex-marker threshold crossings among 12 complete in-window
waits. Scheduler assignment counterexamples also rejected mismatched identity,
lane, generation, flags and timestamps.

The longest joined wait was 66.631 ms: 55.648 ms before vertex selection,
10.947 ms in its selected call, 0.026 ms from return to marker commit and
0.009 ms to the observed wait finish. Publication preceded selection by
148.937 ms. Its assigned host worker was already running before publication;
the observed admission-to-worker interval was bounded by 0.004–0.026 ms.
The same context and host dispatch executed an earlier `spuparticlesystem`
call (`0x16e20`, publisher `0x725ea4`) for 269.028 ms across that publication.
These are wall-time and lifetime observations, not exclusive CPU costs.
Publication alone does not establish that all input dependencies were ready.

This evidence moves the next producer investigation upstream to particle
processing. The vertex arithmetic operation alone cannot remove the preceding
55.648 ms in this joined path. Nineteen separately saved PC observations from
the older `20261119T175246.434951Z` diagnostic match #204's exact 200-byte
threshold loop and physical interpreter walks. Those suspended observations
are a lead, not a current time share; the existing guarded native threshold
operation must be tested on the observed particle workload before claiming a
gain. No scheduler priority, dependency or completion was bypassed.

The corrected run still missed the goal: final-15-second median Present
interval 341.3 ms, p95 400.0 ms and maximum 423.8 ms. This instrumented run
is not a controlled comparison with the preceding 399.9 ms trial. Native
race HUD observation and private identity/record checks do not establish
stable 33 ms or complete graphics/playability correctness. Private join,
assignment and counterexample reports remain under the run's `job-capture/`;
loop observations are in `temp/particle-threshold-physical-observations.json`.


## Standalone particle-box collision batch

[#337](https://github.com/robbe1912/motorstorm-mv-recomp/issues/337) selects
whole collision batches after checking the broader pipeline and the existing
[scheduling evidence](NATIVE_SCHEDULING.md). Diagnostic `20261119T232250.573215Z`
used executable `138aa3855129c43a`, the verified normal route, native threshold
scan and the existing visibility operations. Its private QPC/thread-cycle
recorder retained a complete 262,144-record prefix but dropped 474,276 suffix
attempts. The prefix closes 181 observed jobs, with no pending records; it is
not full-race coverage or a benchmark. Manual policy-service returns were
handled explicitly without inventing call frames or completions.

The largest observed SPU function cost was the particle collision operator at
`0xA700`. One fully closed particle job took 258.4896 ms wall and 912,162,110
thread cycles. Its 256 correctly paired collision calls consumed 71.652% of
that job's cycles. Original publication, selected return and host dispatch
`104909` independently bind that job to the same worker/queue lifetime as a
real vertex-marker threshold crossing. The later vertex wait was 38.8509 ms;
its selected vertex call had already begun 0.8168 ms before the wait and took
38.7028 ms. Publication preceded vertex selection by 121.9505 ms. This supports
removing the upstream computation, not guessing at scheduler priority or
bypassing a dependency. Cross-worker sums are not frame costs.

The surrounding pipeline still matters. Separate unsuspended CPU deltas and
80 main-thread physical walks retain marker, readback, flip and condition-wait
states. Frame-clock walks include CPU vertex expansion, draw recording and
GPU waits. Suspended counts are not exclusive elapsed shares. This selection
identifies the largest observed SPU function on the traced producer chain;
it does not claim one function explains every frame gap.

The [typed core](../../src/motorstorm/particle_box_collision.c) contains no guest
memory, interpreter dispatch or completion protocol. Its adapter executes the
whole backwards record loop from `0xA87C`, after original transforms, and resumes
the original epilogue at `0xABEC`. Contact append, scratch payload, full-list
behavior and optional 128-byte swap removal preserve original order. Code,
input/output extents, count/capacity, saved caller and ownership are qualified;
unsupported state retains original execution. No original instruction array or
generated guest source is included publicly.

Private original-byte replay matches every LS byte on 96 captured entries and
128 constructed cases, including hits, moving/rotated boxes, disabled records,
removal and full output lists. Those cases plus four non-finite/denormal W-lane stress cases (228 total)
also pass the production adapter in native and original-shadow modes through the real `0x12188` caller continuation,
matching saved registers. Twenty-one unsafe admission mutations per case
decline without context writes; the three mutable bookkeeping regions remain
admissible. A 220-node original-caller liveness check leaves no
volatile result live there; original epilogue restores the saved ABI. Public
fixtures add 4,096 independent double-precision slab checks away from rounding
boundaries, payload/order/removal/alias/FP checks and whole-context publication
preservation. The actual-source runner matrix checks 10,368 mode combinations
plus 16 native-query combinations and rejects unsafe mutants.

Production build `fd7beba9d58c1e13` enables the new optional capability. Live
shadow `20261120T000222.496540Z` compared at least 1,024 batches covering 112,812
records and 118 classified contacts without an LS mismatch. It retained original
execution, was muted and ended through its owned stop after 199.3 s, without a
resource breach. This is parity coverage, not a timing comparison.

The CPU-only warm-stage comparison uses five alternating samples per arm,
960 captured 128-record batches per sample, matching completed work/checksums
and all LS bytes against independently executed original output. Original uses
the real interpreter wrapper and SIMD scope; native includes production
admission, whole-module fingerprint and callback. Both are compiled O2 with
checked CRT, a stronger reference optimization than the game's O1 interpreter.
Median original time is 439.964 us (434.555–446.776); native 83.994 us
(82.448–86.355), about 5.24 times faster for this stage. Input reset and full
output verification are outside the timed operation. CPU use immediately before
the short test was 12.3%, with no native game or competing build. This excludes
prologue/epilogue, dispatcher, transfers and other producers; it is not an FPS
speedup. The first harness incorrectly assumed retained record buffers implied
unchanged scratch memory; its failed attempt is excluded and the final harness
checks actual original output, including full-list scratch writes.

Private evidence: `temp/particle-collision-adapter-validation.json`,
`temp/particle-collision-live-register-proof.json`,
`temp/particle-collision-benchmark-report.json`, and the run-local
`job-capture/pipeline-critical-owner.json` / `collision-shadow-validation.json`.
The full 33 ms goal remains open.


Native production run `20261120T003020.855683Z`, executable `fd7beba9d58c1e13`,
completed the verified six-input normal route and 60-second target observation.
It was muted, with no resource breach, collision error or failed DX12 Present.
HUD appeared at 145.1 s; closure was at 207.1 s. The final inspected image shows
player/opponents, BOOST, lap 0/2, position 15/15 and timer 00:49.57. Counters
prove at least 61,440 native batches, 7,691,599 records and 4,040 classified
contacts. Output buffers, appends and genuine marker publication remain owned
by their original path; counters alone are not completion proof.

The acknowledged HUD+20 s capture retains 42,823 records without drops, pending
records or append failures. It contains 343 qualified publication selections,
339 selected returns with real completion candidates, including 19 particle and
17 vertex jobs. All 768 fully observed collision calls used the native leaf,
uniquely bound to three complete particle jobs and their actual original atomic
marker commits. Each job has 256 collision calls; their summed observed collision
wall times are 28.461–30.397 ms within 88.351–96.472 ms job lifetimes. These wall
times include scheduling/observation costs; they are diagnostic observations,
not a controlled old/new job comparison. The 15 fully in-window vertex waits
finish on their first poll without cooperation: total clipped latency 0.0021 ms,
maximum 0.0003 ms. No unique in-wait crossing was joined; the actual completion
records remain separate evidence. This does not prove every future vertex wait
is solved.

The final 15 seconds still have 46 Present intervals with median 326.9 ms,
p95 352.5 and maximum 361.5; none meets 33 ms. Separate completed-marker tails
contain 2.830 s PVS, 2.697 s vehicle and 0.026 s vertex waits. In the last
12-second renderer bracket, 11.095 s lies between batches; 4.427 s overlaps
completed main marker waits, leaving about 6.668 s outside those unions.
Timestamped RTX 3080 direct-queue work has median 49.014 ms per complete Present
group; all 36 groups exceed 33.3 ms. CPU renderer phases total 0.905 s. The GPU
scope excludes CPU jobs/recording and work outside the timestamp pairs. These
observations keep [#155](https://github.com/robbe1912/motorstorm-mv-recomp/issues/155)
focused on the remaining PVS/vehicle producers and attribution of main-thread
readback/flip/condition gaps, rather than further speculative collision tuning.

An earlier native attempt reached HUD at 428 s after a long loaded-bike screen
gate, but its private controller had a 420 s target deadline and the launcher
closed at its 480 s cap. That attempt is not the qualified completion capture;
no faster loading or matched gameplay gain is inferred from the retry. The
standalone five-pair stage result is the established speedup. Overall native
playability, graphics correctness, driving/audio/saves and the 33 ms goal remain
unmet or unverified. New private evidence is run-local
`collision-native-validation.json`, `job-capture/collision-live-functions.json`
and the original publication/completion reports.

## Flip delivery and deformation readback in the native race

On executable `fd7beba9d58c1e13`, both normal menu replays reached the race
after six acknowledged inputs. Final images showed the rider, opponents and
the race HUD at 50 seconds. With the original flip settings, the final three
64-wait groups averaged 39.22, 35.82 and 29.19 ms with 45, 36 and 24 timeouts.
With `--prompt-flip`, the corresponding tail groups averaged 0.08, 0.05 and
0.11 ms, all with zero timeouts. Both used batch GPU timestamps, prompt
surface reads, native particle collisions, the same texture cache settings
and CPU-surface profiling. The original-setting run also sampled the main
thread for 20 seconds. The final 15-second median Present intervals were
321.0 and 288.8 ms respectively. A single diagnostic trial per setting
leaves the repeatable frame-time effect open.

The final 12 seconds of the original-setting run contained 492 four-byte
requests to the same deformation sample address on the publication thread.
They took 4.118 s, of which 3.998 s elapsed before renderer service began.
The 474 generation hits spent 2.059 s queued and 0.002 s in service.
The other 18 requests each copied a surface and spent 1.939 s queued and
0.115 s in service. In the prompt-flip run, the 29 copies for that address
still had a median request latency of 117.2 ms. The renderer can submit
offscreen draw batches during a request. Overlapping these intervals with
other waits would double count frame time.

The original debug-US ELF names the caller at `0x4612f8` as
`WheelCollisionCallback(WheelCollision&)`. It calls `GetDepth` at
`0x4614d0`, saves the returned float at `0x4614dc` and uses it in a
fused arithmetic operation at `0x461520` before the callback returns.
The wheel raycast and test routines dispatch callbacks indirectly.
A reusable surface view for [#326](https://github.com/robbe1912/motorstorm-mv-recomp/issues/326)
must preserve the value at each query and order it against pending and
submitted work. Matching sample addresses alone cannot establish freshness.

Private runs: `temp/runs/20261120T005324.676022Z` and
`temp/runs/20261120T005727.464651Z`.
