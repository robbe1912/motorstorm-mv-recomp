# Work tracking

[GitHub issues](https://github.com/robbe1912/motorstorm-mv-recomp/issues) are the authoritative atomic todo list. This page describes how to use it; it does not maintain a second backlog.

Begin with [the exact native Havok failure capture (#1)](https://github.com/robbe1912/motorstorm-mv-recomp/issues/1). Each issue has a bounded work unit, a completion test, dependencies, target and priority. Read its canonical evidence before changing code. A successful build, reference gameplay or unrelated control capture cannot close a native acceptance issue.

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

The current native acceptance DoD is entering a race through normal PLAY and seeing the original main-menu assets display normally. It requires observed native behavior. Keep driving, opponents, audio and saves as subsequent verification requirements. The user now accepts a 30 FPS cap, provided native gameplay, video and UI actually sustain 30; this is the current performance target. A diagnostic checkpoint or present/title counter does not satisfy acceptance.

Original binaries, assets, firmware, generated guest code, keys, dumps and captures stay local. Issue/PR comments may contain source changes, hashes, identities and non-payload findings; follow the [source boundary](REPOSITORY.md) and [operating rules](OPERATIONS.md).

Historical closed reference findings and scoped exclusions remain in [Havok/reference](research/HAVOK_REFERENCE.md) and [parked mstream](research/PARKED_MSTREAM.md). The closed top-right flashing defect is reopened only on a reproduced regression. Required PM interpretation is a development dependency to measure and correct through compiled semantic parity, never blindly disable. [Setup](BUILDING.md) owns target/architecture facts; research pages own evidence.
