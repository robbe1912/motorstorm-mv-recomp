# Work tracking

[GitHub issues](https://github.com/robbe1912/motorstorm-mv-recomp/issues) are the authoritative atomic todo list. This page describes how to use it; it does not maintain a second backlog.

The main goal is stable 30 FPS on Windows DX12 at normal game start, while progressively replacing interpreted game workloads with native x86 game code. Performance has the highest priority. Use [the measured job producer (#155)](https://github.com/robbe1912/motorstorm-mv-recomp/issues/155) to select the next bounded replacement and [native acceptance (#27)](https://github.com/robbe1912/motorstorm-mv-recomp/issues/27) to judge the result. Vulkan and retail mstream remain parked.

The [modern-engine scheduling comparison](research/NATIVE_SCHEDULING.md) maps
the current persistent workers, policy execution, marker waits and renderer
handoffs to Unreal/Godot task mechanisms. It selects a visibility-job
publication-to-completion timeline before choosing between admission changes
and a complete typed native batch; adding workers alone is not that migration.
The [job-timeline checkpoint](research/NATIVE_JOB_TIMELINE.md) records the
bounded recorder, verified original descriptor/hint/marker bindings and opt-in
actual atomic observations. Admission/job hooks, lifetime-qualified identities
and a live timeline remain issue 219's next gates.

For each replacement, bind the actual workload and its inputs, outputs, ownership and completion ordering; implement the game operation directly with native data and execution; compare against the retained original behavior; then validate normal PLAY and frame times. Keep the interpreter as a migration bridge and correctness reference for work that has not yet been replaced. Interpreter optimization alone does not establish progress toward the native source architecture. Reusable toolkit corrections still follow the fork-first modular and combined workflow in [vendor provenance](VENDOR.md); game implementations belong in this repository.

Each issue has a bounded work unit, a completion test, dependencies, target and priority. Read its canonical evidence before changing code, including [the original native Havok failure (#1)](https://github.com/robbe1912/motorstorm-mv-recomp/issues/1) when following that dependency. A successful build, reference gameplay or unrelated control capture cannot close a native acceptance issue.

- [P0: immediate native blockers](https://github.com/robbe1912/motorstorm-mv-recomp/issues?q=is%3Aissue+is%3Aopen+label%3A%22priority%3A+P0%22).
- [P1: native correctness and playable-race work](https://github.com/robbe1912/motorstorm-mv-recomp/issues?q=is%3Aissue+is%3Aopen+label%3A%22priority%3A+P1%22).
- [P2: performance, reproducibility and final verification](https://github.com/robbe1912/motorstorm-mv-recomp/issues?q=is%3Aissue+is%3Aopen+label%3A%22priority%3A+P2%22).
- [Conditional branches](https://github.com/robbe1912/motorstorm-mv-recomp/issues?q=is%3Aissue+is%3Aopen+label%3A%22status%3A+conditional%22) are pursued only when their stated condition is proven.
- [Parked work](https://github.com/robbe1912/motorstorm-mv-recomp/issues?q=is%3Aissue+is%3Aopen+label%3A%22status%3A+parked%22) requires explicit direction to resume. Creating an issue does not unpark it.

Choose one ready issue, preserve input/build identities, and finish its bounded evidence or correction before opening another work unit. If a task exposes another seam, create a concrete follow-up and link the dependency instead of silently broadening the original issue. Close only with the declared proof and remaining limits; include code/PR references when applicable.

For the current malformed native selection scene, [graphics evidence](research/GRAPHICS_AUDIO.md)
records the AA layout correction and its remaining acceptance limits.
[Translation methods](research/TRANSLATION.md) records read-only REA queries of
the existing named Ghidra project, including incomplete function coverage.
Reuse that project for focused producer/caller questions; a successful query
or replay target does not close the graphics or playable-race issue.

For the optimized normal-PLAY freeze, the [native main-thread evidence](research/HAVOK_REFERENCE.md#native-physics-completion-wait-2026-10-13)
identifies the physics-completion condition wait in both retained dumps.
Bind its worker completion release and outstanding job state before changing
semantics. The [offline reference state](research/TRANSLATION.md#read-only-rpcs3-checkpoint-decoding-2026-10-13)
has individual routine anchors and a validated PPU map, but a different main
wait/checkpoint. Neither finding closes #13 or reopens an exonerated span.

The [constraint-consumer capture](research/HAVOK_REFERENCE.md#constraint-consumer-and-task-slot-exhaustion-2026-10-13)
binds seven queued entries to a consumer whose task creation exhausts all 128
enabled slots. [#71](https://github.com/robbe1912/motorstorm-mv-recomp/issues/71)
now targets the actual task-exit lifecycle and slot recycling; distinguish a
genuine destruction request from ordinary async entry return before a fix.

The initial native acceptance requires an observed race through normal PLAY, original main-menu assets displaying normally and stable 30 FPS on DX12 at game start. A 30 FPS cap is acceptable when gameplay, video and UI actually sustain it. Preserve driving, opponents, audio and saves as further verification requirements. A diagnostic checkpoint or present/title counter does not satisfy acceptance; report interpreter coverage and remaining migration work alongside performance.

Original binaries, assets, firmware, generated guest code, keys, dumps and captures stay local. Issue/PR comments may contain source changes, hashes, identities and non-payload findings; follow the [source boundary](REPOSITORY.md) and [operating rules](OPERATIONS.md).

Historical closed reference findings and scoped exclusions remain in [Havok/reference](research/HAVOK_REFERENCE.md) and [parked mstream](research/PARKED_MSTREAM.md). The closed top-right flashing defect is reopened only on a reproduced regression. Required PM interpretation remains a development dependency until compiled semantic parity or a validated native workload replacement removes that dependency; never blindly disable it. [Setup](BUILDING.md) owns target/architecture facts; research pages own evidence.

## Recovery checkpoint (2026-10-15)

The 2026-10-15 resume after storage cleanup is complete.
[Issue 104](https://github.com/robbe1912/motorstorm-mv-recomp/issues/104)
closed the single observed intro skip. The restored usable build, draft-stack
disposition and private tooling limits are recorded in
[native workflow](NATIVE_WORKFLOW.md). Sampler97/PR98 is explicitly
unaccepted and stays off combined; restoring the earlier baseline was never
a claim that race/graphics DoD is achieved.
