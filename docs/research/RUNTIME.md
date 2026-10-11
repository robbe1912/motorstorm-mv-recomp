# Shared runtime seams and bounded proof

Regression totals below are historical saved results, not tests rerun by the migration. Fixtures carrying original instructions remain private. Source resides in vendor/ps3recomp/runtime/{ppu,spu}, libs/spurs and libs/video. These seams do not establish current gameplay acceptance.

| Seam | Result | Semantics/limit |
|---|---|---|
| Private MFC virtual-owner overflow | 568/0; concurrent 2744/0 | Stable keyed owner beyond eight inline engines; reclaim on quiescent release |
| Coherence owner overflow | 60/0 | Notify all matching reservation owners with self-exclusion/lifetime cleanup |
| DMA list final-S | 46 red 5 → green 0; later 65/0 | Transfer S element, advance; park NEXT if any. FinalS completes; size 0 walks. Never reread same element |
| ILH | 16/0 | Replicate 16-bit immediate in all lanes |
| Interrupt return | saved-state correction | Return to actual saved state, not cached/stale PC |
| IRQ IE/mask/delivery | 36/0 | Respect IE/mask and every-instruction boundary |
| Signal notification/ACK | 4/0 | Shared-lock serialization |
| SPU context ID | 17/0 | Initialize spu_id before shared context use |
| Staged entry/continuation | 108/0; relocated 33/0; forced 30/0; unset 12/0 | Policy mode/image base and IRQ/STOP/HALT/cleanup continuation |
| Jobmod burst EA anchor | 19/19 | Record burst-start source EA, require target inside registered span |
| Codec caller return | 6/0 (red 2); sibling 19/0, 16/0 | Honor link on every context, zero link remains open-ended |

Task-exit clears running only; enabled changes on enable/disable/shutdown. Pending ready arm permits retained taskset redispatch. Task argument register image outranks marker descriptor; retained LS persists across ordinary taskset dispatches. Those boot proofs belong to the [parked retail lane](PARKED_MSTREAM.md), not a complete pipeline cure.

PPU callback ABI/TOC and nonlocal stack fixes are preserved. Historical RSX syscall slots were corrected 623–634, earlier 666–677 wrong; constructor walker/TLS/fs stat and import triage helped boot. Static HLE gaps 45/240 and old function counts are revision/window snapshots, not full native coverage. Silent stub success must not be interpreted as finished work.

Older F-fix 12/15 broad PM claim/cadence/retire wedge theories are superseded for the pre-menu issue by the six default-on probe controls documented in operations. Revert/adopt anecdotes are not a durable concurrency proof. Legal DMA-alignment rules and actual MFC EAs require hardware-shaped counterexamples; do not infer causes from capped logs or aliased probe addresses.

PM sequential walk-in enters staged code at 16270 without an indirect-call hook; exact registration does not cover middle-function resume. Experimental native handoff produced 7.8M redispatches/FPS 0 and stays default OFF. A release needs demonstrated continuation/parity, not disabling development interpretation. [SPURS](SPURS.md) narrows actual CPU/ownership findings; [graphics/audio](GRAPHICS_AUDIO.md) owns decoder/renderer seams.

## Load-time observation groundwork (#11)

`scripts/run.py --loadtime-trace` writes run-local monotonic JSONL events for
boot, consumed PAD_FILE presses, resource operations, observed SPU dispatch
windows, Havok hooks and first presentation. Paths are separate JSON fields.
Wait begin/return records preserve requested arguments, result and measured call
interval, including host and probe overhead. The interpreter and PPU work are
not fully covered; nested and concurrent SPU windows must not be summed as
useful-work wall time. First presentation does not establish visible content.

The analyzer rejects malformed/nonmonotonic records with line numbers, uses the
emitted boot vocabulary and preserves descriptor lifetime across stage boundaries.
Only measured returned waits enter clipped per-thread unions. Unreturned waits,
trace exhaustion and launcher outcomes are reported separately. Historical
malformed labels require explicit `--legacy`; frames.csv has a first-present
relative millisecond clock and cannot anchor a load trace.

Prior no-input captures recorded under EXE prefixes `94d408a3` and
`de9aef3b` ended in fatal177 and no-progress
respectively. Their timeout-only wait logs do not measure blocking. The earlier
96.6%/97% wait-coverage, unblocked-wall-time and sleep-paced-bottleneck conclusions
are withdrawn; file-descriptor reuse and partial SPU coverage also invalidate
cross-resource/useful-work inference. No normal PLAY latency or performance
benchmark is accepted from these captures. Native boundary validation and the
benchmark-checklist measurements remain open in #11.

The [combined review run](../OPERATIONS.md#combined-review-validation-2026-10-11)
parsed strictly with 2,151,087 events spanning 216.935 s, without an event-budget
truncation marker. It records 3,893 completed reads totaling 115,450,269 bytes
and wait begin/end counts 1,073,173/1,073,170; the three unmatched entries
remain unreturned observations at closure. Manual physical navigation has no
consumed-input boundary in this observer, which currently covers PAD_FILE
only. [Issue #44](https://github.com/robbe1912/motorstorm-mv-recomp/issues/44)
owns returned physical-packet transition tracing. The report therefore
establishes observer operation, not normal PLAY latency or a dominant
load bottleneck. Issue #11 remains open.
