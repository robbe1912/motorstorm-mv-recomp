# WWS policy, ownership and CPU evidence

WWS job-list header: manager+0, list-size+4, BE16 hint+10, taken+12, six BE16 minActive markers+14. PM atomic publication sites 3180/32FC/3330. PPU wait is genuine. Native main SPURS 4003F380 with five physical SPUs/wids 0..3; audio 1027DC00. Heap EAs vary; 108D0100 is reservation payload, not a module (observed module 100E6F80).

## Allocations and retention

Initial reserved pages 0..15 and 248..255 = 24. Reserve C00 at 108D0100 requests 16..156 = 141; C10 at 9D580100 requests 157..244 = 88. Union 253, only 245..247 free. PM allocation commit 1B04/1B0C writes page maps, 1B14 descriptor, 1B1C command; new-job reset 2FA4..2FF8 clears selected descriptor/gather/logical maps **without clearing page maps**. Growth 1FF0/1FF4/classification 1FF8/1FFC; baseline removal 2CFC/2D00; release 20CC/20D8/20DC; retire 3130/314C/3150.

Later interrupt chronology demonstrates real 24→165→253 allocations. A zero descriptor plus retained map is not automatically a host leak: incomplete history cannot justify page clearing or a root-cause claim.

## Bounded independent replay

| Unit | Inputs/checks | Scope |
|---|---|---|
| Ownership commit/reset/release | 77/39616, 0 fail: 17 commit/12 reset/48 release | Canonical-byte scalar oracle, full 128 GPR/full LS, actual span bytechecked |
| Reservation predicate 2C34 continuation → 2750 → 1AB0 | 35/110, 0 fail; LS unchanged | Actual start 157, length 88 intersects retained maps: r18 FFFFFFFF, original refuses → 2178 clears r10 → 1A1C |
| Page-mask helper 2750 | 111/73953, 0 fail, 26 instructions | Actual BI r6=1A60, endpoints/nonuniform; corrected modulo 32 domain expectations |
| CPU span 2C34..2C98 before BI 2C9C | 17×26 instructions/8738, 0 fail | Full GPR/LS; watchdog 10s and instruction budget 64 |

Tests use literal original instruction fixtures and stay private. They exonerate tested spans/inputs, not helpers beyond the span, concurrency, lifetime or the full freeze. Initial bad test constants/types/math assertions were oracle/setup errors, not architectural failures. SELECT service keeps LS 1DC id and resumes r0 link; a “wi->0” diagnostic did not mean interceptor wrote wi_state 0.

Owner-read gate captured four owning-thread beforePC 1A40 snapshots across 45.281s with identical complete LS SHA256 f0a3b6372f699744582ddd3d2de49c651399d967ec163408fad180af01277e77, matching authentic PM bytes. PPU stalled ~166.5s; queuehint 2/taken 2/minSPU 4 = 1, other markers FFFF. Snapshots are not instruction chronology. Establish original provenance/live history rather than reinvestigating exonerated CPU spans.

A/B scheduling cap 2/burst 16 observed 18–22 presents/s vs cap 4/burst 1 at 26–27; defaults 4/1 retained. This is a diagnostic window, not a 60FPS benchmark, full-game improvement or license for title-specific scheduler policy.
