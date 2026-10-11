# WWS policy, ownership and CPU evidence

WWS job-list header uses hexadecimal offsets: policy-module EA +0x0, policy-module byte length +0x4, BE16 hint +0x10, taken +0x12, six BE16 minActive markers +0x14. PM atomic publication sites 3180/32FC/3330. PPU wait is genuine. Native main SPURS 4003F380 with five physical SPUs/wids 0..3; audio 1027DC00. Heap EAs vary; 108D0100 is reservation payload, not a module (observed module 100E6F80).

## Current native producer binding

The muted run starting at 2026-10-10T22:40:10Z stopped at the malformed MOHAWK INDIANA bike menu. Only three of four recorded PAD_FILE presses were acknowledged; the race-start press remained unconsumed. This is a menu stall, not a verified race-load attempt. No Havok fatal or playable race occurred. EXE SHA256 was `627f27bd2c03c8cec5c496bb8b9373630e916a7ec339396537ce0d0b8f6b1195`, using the named-US debug ELF and launch-US disc. The matched EXE/PDB CodeView identity and prelaunch config/userdata identities remain private.

Two matched minidumps, with sequential guest/LS samples 80.741 s apart, bind the wait to native thread 31380. PE unwind metadata reaches C5C424 through actual sampled native PCs. The matched executable's argument-spill instructions locate its PPU context without scanning candidate pointers: r3 is 0x40044410, r4 requests marker 8, and r8 is queue 0x40044480. The sampled object pointer at r3 +0x4 agrees. Both queue samples have hint/taken 8 and minActive `[FFFF, FFFF, FFFF, FFFF, 6, FFFF]`; their identical SHA256 is `8ea4f17d008a10a974529a14a4eadf218ec9e21264c49b736ebfcb209c7e11fd`.

The same metadata procedure binds native thread 27668's `spu_pm_interp_trampoline` argument to registry context slot 21. Its LS field at 0x1340 records physical SPU index 4, corresponding to the queue's active marker 6. Registry slot 21 is not a physical SPU number. Its job records at LS 0x1450 and 0x1470 reference this queue and markers 6 and 7 respectively. Queue descriptor 6 points to command-list EA 0x4C6AAA00, with descriptor word 0x00500001 specifying 80 command bytes. The manager EA is 0x10135E00.

The two complete LS reads for that context have SHA256 `38e0edbd1441eb5af9a509f4fe5e7156142fccb26d896f05e63bf8f91ccd8e0a`. Their diagnostic context PCs differ (0x1A20 and 0x2C88); these fields are not promoted to actual sampled guest instructions. The original ELF's PT_LOAD mapping independently supplies the 11136-byte policy at file offset 16539136, SHA256 `44c7436c82f40ced9377ed6abf3293d6792e70e1b34923c4572bb2a3fcc4d616`. Its load base is LS 0xA00. Both captured publication spans 0x3180..0x33A7 match those original bytes, without reinterpreting the previously exonerated CPU spans. A private offline check reports the captured blocked wait with exit 2 for both samples; this checks the actual captured context/header relationship, not a repaired execution.

[Issue #8](https://github.com/robbe1912/motorstorm-mv-recomp/issues/8) remains open. The outstanding job and active native producer are identified, but sequential reads do not establish instruction or writer chronology. The next trace must distinguish an unfinished job/service, a returned job without retirement, and retirement whose queue publication did not persist. No wait bypass, runtime fix, Havok causal link or performance result follows from this binding.

## Chronological probe limits

The isolated muted probe starting at 2026-10-10T23:30:06Z stopped explicitly after 108.375 s. Its EXE SHA256 was `62c0bcbcd733a9cf527e875743494679f57c9f46ac86a98721a4e571cf984197`; sampled dump, EXE and PDB CodeView identities matched. The observer recorded 100000 actual fetched instructions for queue 0x40044480 on physical SPU 4, all matching the independently mapped original ELF policy bytes. The trace includes 171 visits each to publication sites 0x3180 and 0x3330..0x333C, but its job-record markers are only 0, 1 and FFFF. The budget exhausted before the requested-8/job-6 case. These early publication visits do not establish the missing operation in that later stall.

Screenshots reached language selection; one eight-poll CROSS was acknowledged, followed by a black screen. Normal PLAY, race load and Havok failure were not reached. This diagnostic run reused compiled game objects and added read-only runtime observers; it is neither a clean-build proof nor a performance measurement. An earlier probe was rejected because its file sharing and thread-ID reuse caused capture failures. Corrected disabled/enabled/filter fixtures verified no context or LS writes, but they do not replay the game defect. The temporary runtime hooks were removed, and matching sources, binaries, identities, traces and dumps remain private. A narrower marker filter was prepared but not run; its coverage must be validated before drawing absence-of-event conclusions. Issue #8 remains open.

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

## Combined-build stall confirmation (2026-10-11)

In the [combined review run](../OPERATIONS.md#combined-review-validation-2026-10-11),
the user reported confirming a bike to start, but the observed screen
remained SELECT A BIKE. HOTREAD diagnostics again reported queue/object
0x40044480/0x40044414 and LR 0x87D2D4. These diagnostics are not a fresh
actual-PC unwind or proof of consumed start input.

Two read-only 1024-byte queue samples, taken more than 30 s apart after
matching owned PID/create_time/executable and validating guest VM bytes
against the selected ELF, are identical. Both decode hint/taken 8 and
minActive [FFFF, FFFF, FFFF, FFFF, 6, FFFF], with the same SHA256
`8ea4f17d008a10a974529a14a4eadf218ec9e21264c49b736ebfcb209c7e11fd`
as the earlier bound producer capture. This reproduces the blocked header
state with the reviewed diagnostics combined; it does not prove identical
producer history or identify the missing operation. No Havok fatal was
captured. Issue #8 remains open for the already planned narrow chronological
trace; the exonerated instruction spans are not reopened.
