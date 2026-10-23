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

## Remaining integration gates

1. Add generic opt-in observations on the fork for successful PPU conditional
   stores, actual SPU atomic publication, admission/worker boundaries and real
   transfers. Preserve native-leaf admission and all original failures. Event
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
