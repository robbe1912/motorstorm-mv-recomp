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
