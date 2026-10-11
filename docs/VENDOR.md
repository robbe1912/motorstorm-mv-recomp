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
