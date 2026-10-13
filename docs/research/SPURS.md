# WWS policy, ownership and CPU evidence

WWS job-list header uses hexadecimal offsets: policy-module EA +0x0, policy-module byte length +0x4, BE16 hint +0x10, taken +0x12, six BE16 minActive markers +0x14. PM atomic publication sites 3180/32FC/3330. PPU wait is genuine. Native main SPURS 4003F380 with five physical SPUs/wids 0..3; audio 1027DC00. Heap EAs vary; 108D0100 is reservation payload, not a module (observed module 100E6F80).

## Post-incarnation native PVS binding, 2026-10-13

After PR #80, muted normal-PLAY run `20261013T164817.294475Z` still stops
presenting at malformed MOHAWK bike selection (last internal frame 79).
Eight screen-gated receipts acknowledge English, Sony skip, PLAY, help,
ticket, Anything, class and attempted MOHAWK confirmation. Skip correlation
is 0.9682716418. Consumption is not scene-transition or gameplay proof.
EXE SHA256 is
`c360957f7496b66bf931673dd137deae21ef6a0e3213f71cef62b44f09b6b4a4`,
with the matching named-US ELF/launch-US data. PM interpretation is required;
all six wedge probes are zero; sampling is `RSX_CAP=1:480:25`. Duration guard
closes at 301.469s, return code 1. Stderr SHA256 is
`57e2ad5be1ca2795526f68a9b622803fe26e3b063a293a1b2ed20f260797c234`.
There are 1,656 accepted explicit EXIT records, no task-ID exhaustion and no
unresolved-indirect line within this bound. Earlier errors remain evidence.

Exact EXE/PDB/dump CodeView and metadata-only unwinds place main native thread
31124 at `JobListPrivate::StallForJobMarker` through `PVSPPUThread::Wait`,
scene rendering and `ShadowMapModule::GenShadowMap`, rather than the earlier
Havok completion semaphore. A CFG-dominating RSI=entry-RCX assignment plus
restored nonvolatile register proves the actual PPU context argument. Two
sequential live reads, about 40.68s apart, bind guest thread 1, object
`0x40044410`, queue `0x40044480`, requested marker 8, hint/taken 8 and
minActive `[FFFF, FFFF, 6, FFFF, FFFF, FFFF]`. Neither is an atomic history
or captured producer operation.

The same argument proof at `spu_pm_interp_trampoline` binds native thread
11568 (`spurs_pm2`) to registry slot 6, physical SPU 2 and local job records
6/7 for that queue. Three complete 256-KiB local stores spanning about
183.34s have identical SHA256
`15af0ff61c2dffa2fca46eb38fbea07fb866a70e97a703c18bc8d81acbfa7518`.
Third unwind stops at an unsupported leaf; no third trampoline-frame claim
is made. Context diagnostic PCs are not executed instruction PCs. Private
records are `postexit*_stall_snapshot.json`, matched unwinds,
`postexit1/2_pvs_wait.json` and `postexit2_producer_binding.json` beneath
`temp/runs/20261013T164817.294475Z`.

This satisfies issue #8's conditional trigger without identifying the first
missing producer operation or proving a Havok relationship. Next evidence
must distinguish job-6 execution, retirement and shared-marker publication.
Exonerated CPU spans stay closed; #71 remains separate; retail mstream stays
parked. No native race, graphics correctness or frame-time acceptance.

### First chronology probe: physical ownership changes

Read-only probe run `20261013T170551.582315Z` used EXE
`a0a1e74da3f9dc765425f19761315f4bbd9b2fe269498ec58778780a72b3d2bb`,
normal acknowledged input/intro skipping, queue filtering and physical SPU 2.
Its authored fork fixture verified unchanged context, LS and synthetic guest
memory, filtering and retained observation after a local retirement clears
its job record. Native trace contains 998 filtered fetch records: local
marker 6 clears and the shared active markers become all FFFF. That is
positive evidence for this wave, not proof that the whole PVS wait completes.
A later matched operand capture still has requested8/min6, now on physical
SPU 3; its local records are 6/7. The SPU-2 filter excludes this later owner.
The queue address/marker number alone must not identify a unique job lifetime.
Snapshot chronology and these filtered records cannot establish whether this
is a new submission or ownership handoff. Broader observation must preserve
context and actual physical identity across the same queue.

The 181s guard terminates with return1. Stderr SHA256 is
`d4c55043bc8a0b80fc578bdca95a73dcc50dd0740db198f51eaca1fb4707673d`.
Private evidence is `producer-final-summary.json`, `chronology1_pvs_wait.json`
and context/LS files. Neither probe timing nor retirement establishes a race;
probe-off baseline above remains authoritative for the ordinary stall.

### Second chronology probe: all-physical filter and cap

The second private observer run `20261013T171346.818831Z`, EXE SHA256
`eda1c840c3b39ec60e2e198d94887c719ec5dfa465725864682d25ad1b13221b`,
admitted all physical SPUs on the same queue and retained an armed context
across policy-mode changes. Its 20000-event interpreter budget exhausted on
one context, physical SPU 0. Local marker 6 clears, and both publication sites
are fetched twice; the sequential shared header changes from hint8/taken8 to
hint2/taken1. Queue address and marker alone therefore cannot identify a unique
submission lifetime. No matched late wait capture was made in this run, and
absence after the cap has no verdict. Internal frame 71 still shows malformed
blue geometry at SELECT A BIKE, not gameplay. The 181.046s duration guard ends
with return1. Trace SHA256 is
`288c35aceefd36007dc9aa391e98e8456746b92db50138fe3b22d6011560189d`;
stderr SHA256 is
`79e378e657135b9f86e2de4d4d03c139fc7a66dfe03ccf01b1bb41520e3fa7fa`.
All three temporary runtime hooks were restored byte-for-byte in both trees;
the supported optimized rebuild succeeds with EXE SHA256
`d767b40e2ace342d60ccaa7623cf272863f2a2848a4af1f6a09d337a62b5cb0a`.
Private summaries and EXE/PDB pairs are retained. No producer correction or
race acceptance follows from these observations.

### Published clipping fix: fresh PVS binding (2026-10-13)

The clipping correction in own PR #87 removes the oversized environment
triangles, but does not establish completion of vehicle loading or normal PLAY.
Supported optimized build `20261013T195103.541804Z` produces EXE SHA256
`61b74e4d10efcdaf7f38a9a87be8b14c60097c85f1713f2fbe3948a01a8249ff`.
A private layout program compiled against the current SPU/PPU headers independently
matches the stored offsets and sizes (268,960 and 1,104 bytes). No temporary
runtime hooks are installed for this capture.

Muted named-US run `20261013T201913.840310Z` follows the ordinary observed route,
including an observed Evolution skip and acknowledged MOHAWK confirmation.
After 30 seconds, bounded read-only sampling produces a minidump, matched
EXE/PDB CodeView admission, actual-PC metadata unwinds and sequential live reads.
Main native TID 39524 is in `JobListPrivate::StallForJobMarker` (`C5C424`) through
`PVSPPUThread::Wait` (`87D278`). The CFG-dominating RSI=entry-RCX assignment and
restored Windows nonvolatile register bind PPU context `0x489B52F670`, guest
thread 1. Object `40044410` points to queue `40044480`; requested/hint/taken are
8/8/8, active markers `[FFFF, FFFF, FFFF, 6, FFFF, FFFF]`, minimum 6.

The PM trampoline argument proof binds TID 32932 (`spurs_pm3`) to context
`0x22300539280`, registry slot 7. Its captured LS independently identifies
physical SPU 3 and queue `40044480`, with local record words 6/7. The context's
`spu_id` field is 0; neither that field, registry slot nor thread name substitutes
for the physical-number proof. LS SHA256 is
`2271d01b108b487de42e7399e3f3984e458c59016d40424caebd477ef3a1b593`.
All 22 registered contexts were covered without registry truncation. Diagnostic
context PC `2178` is not promoted to an executed guest instruction. The actual
native producer unwind reaches `interp_run_until_impl` and the PM trampoline.

Explicit stop at 108.688 seconds terminates the owned run with return 1. Stderr
SHA256 is `49113434d6ea0e69990a2634ddab438ef520b893134367205dbbca955a924d53`.
Eight acknowledged inputs do not prove a race successor. This single snapshot
and later live reads are not atomic, a unique-submission identity or instruction
chronology; they do not identify the first missing operation. Issues #8/#13/#24
remain open, #71 remains separate and retail mstream remains parked. Next trace
the late producer's state transitions and submission lifetime without allowing
early interpreter-fetch churn to exhaust coverage. Existing compared CPU spans
remain scoped and are not reopened by this binding.

Two preceding attempts yield no memory evidence: run `200352.667867Z` rejected
the diagnostic log's reserved evidence prefix before creating a dump (explicit
stop at 106.625 seconds); corrected-log run `200854.236002Z` timed out after
English, missed caption gates and exhausted its finite internal-capture budget
during the intro (explicit stop at 201.047 seconds). Both failures are retained.
The successful run adds a validated private observed-movie optional gate, but
uses the existing Evolution gate; the new movie gate is not runtime-verified.

## Earlier native producer binding

The muted normal-menu run `temp/runs/20261012T230343.828131Z` reproduces the
wait with the AA-corrected EXE SHA256
`3822b2341dbbf26e670189cb392a00b680a56434aa8c58f5860c784967177fc2`.
Frame 25 shows race selection with distorted yellow/black/white bands; frame
30 shows the bike menu with a white central scene. The user reports selecting
the bike. Only LANGUAGE-English CROSS4 has an automated receipt; the external
screen-gated controller observed race selection, but did not acknowledge the
other planned inputs. This is assisted normal-menu observation, not a fully
automated route or a playable race.

Matched EXE/PDB metadata unwinds and freshly compiled context offsets bind both
`bike1` and `bike2` samples to requested marker 8, minimum 6, queue
`0x40044480`. The actual trampoline argument binds native thread 34576 to
physical SPU 2, rather than treating a registry slot as its physical index.
The process remained alive and rendering stopped. The launcher subsequently
terminated it at its 600-second bound: final return code 1,
`terminated_by_guard=true`. That termination is not proof of an earlier game
crash. Both guarded captured-wait analyses report BLOCKED with exit 2.

REA's unchanged Java bridge queried a disposable read-only copy of the existing
named Ghidra project, with the original project hashes unchanged. Private
evidence is `temp/research/rea/wait-20261013T011515/verification.json`.
Independent original-ELF byte and symbol-bound checks give full coverage for
`StallForJobMarker` at `0xC5C424` (84 bytes), `WaitForJobListEnd` at `0xC5C478`
(220), `PVSPPUThread::Wait` at `0x87D278` (136), the unblended scene-list
renderable at `0x6C379C` (428), and `CommandListBuilder::FinalizeJob` at
`0xC5BA68` (72). `RenderCommandExecutor::Execute` at `0x7765B0` has 192 of
200 symbol bytes decoded; the eight-byte gap and unresolved caller identities
remain qualified. This is the manual bridge path described in
[translation methods](TRANSLATION.md), not supported Windows ELF CLI admission.

The original names and matched native frames locate the wait in scene
rendering through `PVSPPUThread::Wait`; they do not identify the missing SPU
operation. Test three alternatives with a bounded chronological producer
trace: job 6 has not returned; it returned without reaching retirement; or
retirement ran but the queue publication did not persist. The earlier probe
exhausted its budget before this marker, so its missing events do not distinguish
these cases. No forced retirement, repaired execution, Havok causal link or
performance acceptance follows.

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

## Marker-6 observer refinement, 2026-10-11

Private read-only hooks ran against the current runtime. Four fixture modes
verified disabled/wrong-queue exclusion, marker arming/retirement, caps and
unchanged full context/LS. First run `20261011T133917.527458Z` exhausted
100000 fetch records in14.105 s and reproduced the earlier8/min6 queue hash;
no later absence can be inferred. Publication visited predecessor5 while6
remained active.

Refined run `20261011T135119.578937Z` compressed loop samples by command/LS
state; other GPR changes lie outside that loop identity. It retained2008
selected fetch records over5.314 s and44 full context/LS pairs. Every recorded
instruction matched original policy SHA256
`44c7436c82f40ced9377ed6abf3293d6792e70e1b34923c4572bb2a3fcc4d616`.
Embedded and separate LS copies agreed for all44 pairs. Snapshot quota44
exhausted; later transitions are unobserved. Retirement shows253 ->112 ->24
reserved pages; allocation24 ->165 ->253. A later worker wave clears local
marker6 and visits publication; persisted shared-queue publication and the
first missing operation in previous stalls remain unproved. No new blocked
PPU/producer PE unwind was taken.

User bike confirmation transitioned to black, then original fatal177 at
235.578 s. Probe timing differs; this is not a fix, speedup or PVS/Havok causal
proof. Hooks restored byte-for-byte, diagnostic EXE/PDB retained privately,
all61 preserved generated-source hashes unchanged. Ordinary use requires
rebuilding restored runtime. #8 remains conditional/open; the exact failing
bytes now advance #1/#2 and #3. No exonerated CPU span was reopened.
