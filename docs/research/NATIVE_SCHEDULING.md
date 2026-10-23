# Native game scheduling and the migration boundary

Issue [217](https://github.com/robbe1912/motorstorm-mv-recomp/issues/217),
researched October 23, 2026. The target remains stable 30 FPS through normal
PLAY on Windows DX12, moving game workloads into typed native x86 code.
Ten milliseconds on each processor is a useful engineering target; current
evidence does not establish that budget. This research changes no runtime
behavior and required no new game launch or desktop input.

## Findings

The current game already uses persistent host threads and several typed native
operations. Its remaining compatibility path schedules virtual-SPU policy
modules and exchanges guest-memory state. A faster worker pool alone does not
turn that path into native game tasks. The migration should move complete,
verified game operations across the ABI boundary, then schedule independently
owned batches with explicit dependencies. Merely changing language or graphics
API would retain the same work and dependencies.

The latest saved gameplay packet has both a large CPU/synchronization gap and
meaningful GPU work. It does not support a single-core-only diagnosis or a
claim that the GPU already meets the frame budget. Attribution must distinguish
time waiting for a prerequisite, time ready but unscheduled, actual execution,
and time waiting for renderer/GPU work.

## Modern-engine mechanisms

[Unreal's Tasks System](https://dev.epicgames.com/documentation/en-us/unreal-engine/tasks-systems-in-unreal-engine)
documentation, returned as UE 5.8 during this research, describes callable
tasks with explicit prerequisites and nested completion dependencies. A
dependent task can remain pending without occupying a worker. It recommends
dependencies over blocking inside a task. Since UE 5.5, its former busy-wait
mechanism has been replaced by standby-thread oversubscription during waits;
the documentation explains the old risks of spinning, recursive waits and
unrelated work delaying a critical continuation. This is a design reference,
not evidence that importing that scheduler will accelerate this game.

[Godot's WorkerThreadPool](https://docs.godotengine.org/en/stable/classes/class_workerthreadpool.html)
uses startup workers and offers indexed group tasks. It warns that distributing
cheap work can cost more than it saves. In the inspected
[4.5-stable implementation](https://github.com/godotengine/godot/blob/876b290332ec6f2e6d173d08162a02aa7e6ca46d/core/object/worker_thread_pool.cpp),
`_process_task` claims group indices atomically and invokes native callbacks;
`_thread_function` waits on a condition variable when its queue is empty.
`_post_tasks` notifies workers. Pool callers may process other work while
awaiting a task; `wait_for_task_completion` rejects older-task waits that can
deadlock. This is a different mechanism from Unreal's current wait policy.
Neither design makes arbitrary game state safe to access concurrently.
[Godot's threading guidance](https://docs.godotengine.org/en/stable/tutorials/performance/thread_safe_apis.html)
also separates worker-safe data work from scene-tree mutation and warns about
GPU access causing synchronization stalls.

[Unreal Task Graph Insights](https://dev.epicgames.com/documentation/en-us/unreal-engine/task-graph-insights-in-unreal-engine-5)
records task lifecycle transitions and prerequisite/subsequent relations. That
separation is the useful profiling model here: a long parent wait does not
identify whether its producer was not ready, not admitted, preempted, doing
useful work, or blocked on another dependency.

## Actual source path

The comparison pins game-repository commit
`3b834ad81c6af18b8015882852d42afff37410f7`; it does not infer current behavior
from older scheduler captures. Fork and upstream master were independently
rechecked at `a6d76c895f77eb30b90a806c830544e61821b77f`. The fork's combined
integration remains separate, as described in [vendor provenance](../VENDOR.md).

| Concern | Current implementation | Native migration consequence |
| --- | --- | --- |
| Worker lifetime | `spurs_pm_worker` in [cellSpurs.c](../../vendor/ps3recomp/libs/spurs/cellSpurs.c) persists per configured virtual lane. Issue 209 removed the old join-all-workloads barrier. | Do not propose persistent workers as an unimplemented fix, or use old serialization evidence to describe this revision. |
| Admission | `spurs_kernel_thread` requests `Sleep(1)` before scanning guest eligibility, priority and contention. API unlock and worker completion notify the instance CV, but this coordinator does not wait on it. Idle probing also backs off by pass count. | Publication-to-admission delay is a real candidate. Requested sleep duration is not measured dispatch latency. Inline guest publishers mean API notifications alone cannot replace the fallback scan. |
| Unit of execution | [spurs_policy.c](../../vendor/ps3recomp/runtime/spu/spurs_policy.c) owns resident contexts per instance/workload/lane and invokes policy execution. The measured profile retains required PM interpretation. | A virtual lane executes guest policy/jobs, rather than receiving an immutable native game-operation batch. Preserve ownership while replacing the actual operation and its data protocol. |
| Completion wait | [job_wait.cpp](../../src/motorstorm/job_wait.cpp) reads the taken marker and six active lanes. After 64 unsuccessful polls it cooperates on each later iteration. The [adapter](../../src/motorstorm/job_wait_adapter.cpp) requests a 100-microsecond timer wait. | Cooperation yields CPU; it does not schedule a native dependent task. Removing the wait or changing its marker would violate completion semantics. Event-based completion needs every real writer and lost-wakeup/reuse protection. |
| Audio waits | `spu_taskset_wait_signal` in [spu_workload.c](../../vendor/ps3recomp/runtime/spu/spu_workload.c) uses a timed condition-variable wait. | A high-CPU audio thread cannot simply be labelled a busy-spinning waiter. Its execution and wait episodes need separate accounting. Retail mstream remains parked. |
| Typed work | [visibility_planes.h](../../src/motorstorm/visibility_planes.h) exposes boxes, planes and corners; [threshold_scan.h](../../src/motorstorm/threshold_scan.h) exposes records and flags. | These cores are already typed native operations. Progress means expanding verified ownership/data boundaries and reducing bridge crossings, rather than describing all their arithmetic as interpreted. |
| Whole scene operation | [scene_hierarchy.cpp](../../src/motorstorm/scene_hierarchy.cpp) already prepares typed world-transform buffers, validates spans/ownership and commits an entire supported scene-list transaction. | Do not duplicate this existing native PPU operation or confuse it with the remaining SPU visibility job. Its preparation/allocation cost needs attribution before any separate change. |
| ABI preparation | [visibility_adapter.cpp](../../src/motorstorm/visibility_adapter.cpp) snapshots bounded matrix/plane bytes, decodes them, invokes native math, rechecks ownership/data and reconstructs observable guest state. Its native preparation uses fixed arrays, not per-call heap vectors. | Shared immutable plane data might be prepared once for an owned batch, only after its lifetime and mutation rules are proved. Removing admission/revalidation without that proof introduces stale reads. |
| Render production | `frame_clock_iteration` in [main.cpp](../../src/main.cpp) drains FIFO and presents consumed flips; the thread has a FIFO kick event and high-resolution timer. | The name `frame_clock` does not mean its CPU time is sleeping or incidental. FIFO decoding, vertex expansion and command production still need attribution. |
| CPU surface read | [rsx_cpu_surface.inc](../../vendor/ps3recomp/libs/video/rsx_cpu_surface.inc) queues a real request to the renderer, services a GPU copy/fences, then releases its client. | A two-byte payload can still wait behind substantial work. Cache, prefetch or async replacement must preserve the producing surface generation and actual consumer deadline. |

Worker count currently follows the compatibility instance/lane model. It is
not a hardware-wide budget for native game tasks. On this six-core/twelve-thread
host, main/policy/audio/render work can compete, but the saved CPU totals alone
do not establish oversubscription stalls. Raising priority, pinning threads or
adding workers without ready-time/dependency evidence is not a justified fix.

## Retained gameplay evidence

This reuses issue 215 run `20261023T171441.594042Z`, PID 3004, checked
O2/Ob2 with Debug CRT, assertions and DX12 validation retained. EXE SHA256
`9a6b1977906bae5acf99708dd5638645198f832a76dd2637d174890358002ac4`,
PDB `af938a8ef2a5c0dbc3675ad2f6196f766e3e7fd26317324f8ff7922045ffb0ef`.
The [native acceptance record](../VENDOR.md#prepared-native-vertex-uploads-issue-215)
contains original menu/race observation, source/input identities, stop reason
and preserved diagnostics. It is not a controlled before/after performance
comparison. The protected private packet and its analyzers were reused;
original assets, dumps and generated code are not publication material.

| Unsuspended window evidence | Observation | What it establishes |
| --- | --- | --- |
| CPU accounting | 43 samples over 44.6114993 seconds; process resource median 4.924 logical CPUs. Async thread used 38.9375 CPU seconds; renderer 30.59375; five policy workers 18.94-21.11 each. | Several threads do substantial work. Totals are not exclusive function costs, critical-path lengths or proof of saturation of every core. |
| Own-PID PresentMon | 82 adjacent intervals wholly inside the CPU window; median API cadence 446.3919 ms, range 373.3846-711.6708; display-change median 465.227 ms. | The observed cadence misses stable 30 FPS badly. API/display intervals do not establish semantic game-frame identity. |
| PresentMon GPU | Median busy 101.1931 ms, wait 293.05985 ms; Present API 0.25785 ms. | GPU work is substantial alongside long gaps. These medians cannot be subtracted into an exclusive CPU budget; per-queue/pass timings are still needed. |
| Main marker waits | 3,264 contained visibility waits total 9.5135458 s; 380 vehicle waits total 4.477326 s. | Real producer dependencies hold up the main thread. The sums include other workers' execution and cooperation, not just polling overhead. |
| CPU surface requests | 95 contained two-byte requests total 7.5613673 s: queue 6.1034666 s, prior fence 1.3939703 s. One crossing request excluded. | Renderer scheduling/service ordering is relevant despite the tiny payload. This wall time can overlap worker/main waits and must not be added as another independent frame cost. |
| Resource I/O | Read-transfer counter increased 262,144 bytes in the selected resource interval. | Large sustained process read traffic is not visible in this window. Cached I/O and GPU residency/preload adequacy are not resolved by this counter. |

Later paused contexts identify original jobs and interpreted/native call paths,
but are separate from this unsuspended timing window. Partial native stacks and
sequential queue observations do not become weighted CPU profiles. The first
PresentMon file was intro-only due to a wrapper match error; only the corrected
own-PID gameplay trace above overlaps the CPU window. Both files and tool
warnings are retained. No new launch or timing result was produced here.

## Ranked hypotheses and discriminating checks

These are investigation priorities, not measured shares of frame time.

1. **Execution and marshalling across small guest/native boundaries.** If this
   dominates, real selected jobs spend most of their admitted lifetime running
   interpreter/bridge work, and an equivalent complete native batch reduces
   producer completion latency. Count actual operations, bytes prepared and
   bridge entries per owned job; compare the same outputs and completion state.
   Existing native SIMD leaves mean arithmetic-only replacement may miss the
   remaining cost. Do not optimize a hypothesized visibility heap allocation:
   that allocation is absent from native preparation.
2. **Late admission or unavailable virtual lanes.** If this dominates, published
   eligible critical work remains unadmitted, or admitted work is OS-ready but
   not running. Record publication, eligibility, slot assignment, worker start
   and genuine completion on the same clock. Existing notifications ignored
   by the coordinator are a specific candidate, not evidence that removing
   `Sleep(1)` would recover hundreds of milliseconds. Distinguish policy-owned
   requested demand from host dispatch tokens; issue 209's controls must remain.
3. **Renderer serialization and synchronous readback.** If this dominates,
   main-thread stalls line up with queued surface service or CPU command
   production, while GPU queue gaps remain. Correlate actual surface generation,
   request, command submission, fence release and consumer resumption. Keep
   required copies and writes; never return an old surface to make a wait short.
4. **GPU pass cost, resource traffic or residency.** If this dominates, timed
   submitted work/residency stalls consume the remaining critical budget even
   after CPU gaps shrink. Measure per-pass/queue execution and residency. The
   GPU model and the original PS3 target do not determine current DX12 cost.

## Next bounded implementation decision

The next required measurement boundary is the **main visibility job's actual
publication-to-completion timeline**, correlated to its consuming marker and
real submitted frame. This follows the bound producer in issue 155 and the
existing typed visibility core. Native particle work in issue 204 remains a
separate operation; its presence does not prove it is the dominant frame cost.

For one owned queue/job generation, collect publication, prerequisite-ready,
host admission, worker start, actual selected-job entry/exit and marker release.
Associate instance/workload/physical lane, queue identity and generation; thread
names or TIDs alone are insufficient. A policy dispatch can contain multiple
jobs, so policy return is not a substitute for each selected job's completion.
Inline guest publishers must be covered explicitly. Unknown coverage, clock
errors, incomplete intervals, ring overflow and context reuse remain visible.
Do not add overlapping intervals or assign a critical path through unknown
dependencies.

Use an opt-in bounded trace, with no per-event formatting or file writes in
hot execution. Generic runtime events belong on an atomic branch in our
ps3recomp fork and its one combined branch. Verified game job/marker binding
belongs here. Authored tests must reject swapped owners, reused queue/job
identities, missing completion/publication, overflow and reversed chronology;
enabling capture must preserve output, errors and real completion ordering.
Establish trace overhead separately before using it as performance evidence.

For OS execution/ready/wait and GPU queue correlation,
[PIX Timing Captures](https://learn.microsoft.com/en-us/windows/win32/direct3dtools/pix/articles/timing-captures/pix-timing-captures)
can collect CPU samples, context-switch stacks, GPU timings, I/O and residency
alongside application events. Collection options add overhead; exact PDBs,
loss/symbol coverage and capture privileges must be checked. This is a suitable
DX12 profiling option, not an installed or completed capture in this research.
An existing sampling profiler alone cannot recover guest-memory dependencies.

The candidate migration is a **complete PVS visibility object-range operation**,
distinct from the existing native PPU scene/world-transform transaction:
prepare owned shared plane/matrix inputs once, execute typed native batches,
then publish every required output and completion in original order. This is
an intended boundary to recover, not an already proved batch contract. Recover
the outer producer/consumer, DMA effects, mutable lifetimes, FP/interrupt
behavior and dependencies first. Compare full original results before changing
the scheduling unit. Split only independently owned ranges; keep unsupported
cases on visible original execution. A leaf microbenchmark cannot accept this
migration or close the performance issue.

One later normal-PLAY session should collect an unsuspended baseline window
before optional intrusive diagnostics, using the existing muted screen-gated
PAD_FILE route. Preserve original menu/race observation, identities and one
reusable evidence packet; rotate only the latest five ordinary runs. A claim
of improvement still needs controlled relevant comparisons and unchanged
outputs. Stable 30 FPS, geometry/shadows and full native rewrite acceptance
remain open under issues 27, 137 and 155. Vulkan and retail mstream stay parked.
