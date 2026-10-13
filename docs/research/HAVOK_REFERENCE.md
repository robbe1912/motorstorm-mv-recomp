# Havok resource and reference diagnosis

## Native failure and controls

Normal PLAY has reached original HavokResource line 177: “Could not find physics or animation data in root level object”, followed by sys_process_exit(0). This is failed gameplay. SELECT A BIKE showed MOHAWK/INDIANA with malformed art/no model before black submitted frames. No proof that SPU, PVS, schema or a default bike caused this fatal.

The migrated native run starting at 2026-10-10T21:50:51Z identified resource **000a8a45293a530c**, object 4E0860F0, raw length 42480, allocation/raw EA 0, root 360 and an empty lookup result. The observer rejected EA 0, so this run contains no pre-relocation raw dump. LR 72F180 was stale and is not a current PC. The read-only observer now accepts bounded readable EA 0, retains the raw stream and records explicit hook sites; its synthetic Windows regression fails with the old header and passes with the correction. This repairs evidence collection, not gameplay. The later native pairing below supersedes the raw-equality gap; [#1](https://github.com/robbe1912/motorstorm-mv-recomp/issues/1) retains its identity/PC audit.

Independent launch-US archive decoding found one matching index entry, `animations/havok_000a8a45293a530c.evo`: name hash 47D76482, decompressed offset 2631156092, container 42504 bytes. Chunks 80296/80297 start at compressed offsets 1354934368/1354953475, lengths 19107/18251, each decoding 32768 bytes. EVOSBIG resource ID is at +8, flags 10000 at +16, declared length 42480 at +20, raw at +24. Container SHA256 fdaef4b18082337b1a1e5bb1752f730f6565d3e4a32f7eea487318c7fa3e10f3; raw SHA256 24256e3c1ca78d7fb13219cf840307e5128dfe319528a77eb30777a723bc2182. Havok 4.1.0-r1/v4/layout [4,0,1,1], root hkRootLevelContainer at 360. Payloads remain private; [#2](https://github.com/robbe1912/motorstorm-mv-recomp/issues/2) closed after the native pairing below.

The rebuilt observer's latest muted run reached normal PLAY, SELECT A RACE and MOHAWK INDIANA through observed screens/acknowledged input. Screenshots show absent ticket artwork and vehicle model, malformed UI and a black background. After the race-start press, the screen stopped advancing; logs repeatedly reported the PVS wait. Two read-only 256-byte snapshots at 40044480 were identical, not an instruction trace or root-cause proof. The owned run was explicitly stopped at 466.562s with no Havok capture or fatal reproduced. EXE SHA256 627f27bd2c03c8cec5c496bb8b9373630e916a7ec339396537ce0d0b8f6b1195 has a matched PDB; this is failed gameplay and inconclusive live observer verification. Neither #1 nor #2 is closed.

Two IStream constructors 72E624/72EE9C both contain the gate; HavokType::Load 72F714 calls sibling 72EE9C. Initial observation covered only one; later broad 128-event quota exhausted on successful menu animations. Final raw/fatal observer reserves same-resource raw pairing; the instrumented tree retains five hooks. Root is r24 after reader, r22 is the 32-byte lookup result; allocation this+24 may differ from aligned raw destination; length this+20. Validate original field accesses, not stale analyzer labels.

Captured controls: 26 raw/root pairs, 8190 local/global fixups checked with 0 mismatch, 25 successful animation lookups. These do not exonerate failing physics/virtual fixes/scalars/finishing/source bytes. Packfiles use Havok 4.1.0-r1, version 4, pointer 4 big-endian layout [4,0,1,1], not Pacific Rift 5.5 assumptions.

| Original resource control | ID | Packfile offset/bytes | Root |
|---|---|---|---|
| animations/havok_000a0ebe40f7a99b.evo | 000a0ebe40f7a99b | 24/26240 | hkAnimationContainer |
| global/havok_000a7d721a8a8dc5.evo | 000a7d721a8a8dc5 | 24/22304 | hkPhysicsData |
| vehicles/bike01.rpk embedded record | 000ab2baec08ebb3 | 3459566/33872 | hkPhysicsData |

Animation raw SHA256 d89f5becc46c6ec634e647a87743cb94f286b1f3cae9a744bdb1bd9b8525f389 matches archive extraction. Global 9cacc297d64b075972bf4aecef0ac9faa225eb8eca6e8d007f6db8228b98bde1; bike 3cee8002cb2d6cdff28e34dbd1618299db9bb7459b0bc424e0b287432110b676. Bike01 is not identified as the failing/selected resource.

## PVS is separate

Matched EXE/PDB unwind 29 frames established PVSPPUThread::Wait 87D278 → JobListPrivate::StallForJobMarker C5C424, requested marker 8/min 6 in that capture. Other runs/PCs differ. This is a genuine wait with unresolved producer, not demonstrated cause of Havok 177. Do not bypass it. Earlier raw stack candidates were incorrectly promoted to running PCs; see operations for symbol/PC rules.

## Reference compatibility

Ordinary retail RPCS3 BCES00006 and BCUS98137 both work; a reference lap was completed. Old isolated debug used 20237-55a3aff3 while ordinary was 20273-987129bc with other effective config differences; those old crashes were not matched differentials. Corrected v2 uses 20273-987129bc, identical full configs including PSID and shared authentic disc/HDD baseline. Earlier PyYAML rewrote 16:9 to 969 and PSID to decimal; correction was byte-preserving volume-only edit with reverse reconstruction. Original shader warnings retained.

Authentic installed pack01 decrypted TOC contains extensionless modes/asset_time_attack plus CRLF. Original debug scanner calls strrchr('.') at 642468, receives NULL, unchecked underscore store 642478 faults (logged JIT CIA 64246c). Capture was frozen **post-fault**, not a successful pre-store breakpoint. This proves a debug/DLC incompatibility, not native Havok causality.

Private prelaunch pack01 quarantine preserved original data. Scanner checked pack00/04/03/02/01, all ENOENT, and passed. User normal PLAY→bike→race-start then debug null READ D46EC/main_thread at guesttime 1:21.597 (VehicleViewer class). Retail under identical quarantine completed race. Debug repair is bounded; use working retail with explicit address/callee mapping.

## Mapping evidence and next boundary

Debug constructors 72E624/72EE9C map to retail 6AFAA4/6B031C: each 542 instructions, 493 exact, 27 call and 22 TOC displacement differences only. Lookup A11980/98E614 exact 384 bytes; getName AF7AC0/A74754 exact 8 bytes. Eleven reader comparisons: 8 exact; remaining 3 only 3 TOC loads/1 call differences. Referenced callee/data equivalence still needs proof. Previously fixed generic TOC is not reopened by these results.

Capture exact failing asset, independently recover original bytes, compare raw first, then normalized relocation/virtual finishing, then lookup/ABI only if inputs match. No schema rewrite or forced non-null return is justified. Exact public fatal search found no applicable fix. [Frame-rate patch research](https://illusion0001.com/legacy-website/patches/2022/05/10/Motorstorm-Framerate-Patch/) is about timestep/frame modes, not this root lookup.

Private artifacts/atomic source ownership are indexed in [source coverage](../SOURCE_COVERAGE.md); logs known overwritten there cannot be reused as original evidence.

## Native raw pairing, 2026-10-11

Muted manual navigation in `20261011T135119.578937Z` confirmed a bike,
transitioned to black, then reached original fatal 177 and sys_process_exit(0).
The user called loading an assumption; no race rendered. The owned run ended
naturally at 235.578 s with return 0, no guard. EXE SHA256
`92aba648c923ccb9a6e91ac6d8aa45b1f38ece51643c0216f858bf35ba50ce7f`;
ELF SHA256 `3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706`.
Matched-build EXE/PDB are private. Executed guest observer sites were raw
72EF88/fatal72F640; LR72F180 remains stale. These are explicit hooks, not a
sampled native PC/unwind. Physical input timestamps remain unavailable.

Captured resource `000a8a45293a530c`, object4E0860F0, raw EA0/42480 bytes,
root360 and empty lookup result4E086060 belong to the same fatal event.
Pre-relocation SHA256
`24256e3c1ca78d7fb13219cf840307e5128dfe319528a77eb30777a723bc2182`
exactly matches the independently extracted span above and the independent
[whole-archive research](https://github.com/robbe1912/motorstorm-mv-recomp/issues/2#issuecomment-6109789311).
Archive-side naming is not a native filename observation. Earlier raw-byte
pairing gaps are superseded for this resource; #1's remaining identity/PC
verification is separate from #2's now-established original-byte pairing.

The exact v4 local/global fixup tables specify 315 pointer fields: 257 match
at fatal and 58 differ. Root is expected base+360, but its variants pointer
is zero instead of expected370. Post-state SHA256
`b0c44c6a129dba13cee54f2cf399ba16748d023ceabc9ba8906f1c5239825baa`.
This is the earliest captured post-load difference, not the first diverging
operation: relocation, finishing and later mutation remain unseparated.
[#5](https://github.com/robbe1912/motorstorm-mv-recomp/issues/5) owns the native
operation boundary; [#3](https://github.com/robbe1912/motorstorm-mv-recomp/issues/3)
owns the working reference capture/mapping. No selected-bike asset or known-good
control was substituted.

## Same-resource retail reference, 2026-10-11

The user created `BCUS98137_1_0.SAVESTAT.zst` in an isolated, muted retail
RPCS3 20273-987129bc instance using the original launch-US EBOOT.BIN and disc.
The state is 146382246 bytes, SHA256
`8cd2f328f6c6df864d26618f922c299ad3a55456cc7c4e9a5d27861247b6d686`.
RPCS3 EXE SHA256
`15f18e910b7368bf6ed5ff91e88ff1a5f6d8faf0c9d952385863cd3bba360f6d`;
pristine configuration/input manifest SHA256
`1ad3bfcb954cbfaf8137903a173fd9151f585ea22d1585d9342dd29919af00e9`.
Writable VFS/HDD/save paths stay in the cloned instance. No packs were quarantined.
The reference ELF SHA256 is
`8e0abf4f611752f74f0f726f77f25e7bfef043c964451b96cffe5cf2089f3886`;
encrypted EBOOT.BIN SHA256 is
`c468f959ed291f79e0b1563be59e1b812d60bb61846cbede4f352f70a748cfb0`.

The first state was saved before debugger attachment. A later save attempt with
the observer connected stalled RPCS3's GDB shutdown; the owned process aborted
at 186.453 s, host 0xC0000409. No armed constructor trap was captured. The
first reload also failed while an owned CLI-help process held the instance.
Both failed trials are retained. Successful `savestate-replay2` launched the
original state as PID19804/create_time1791728988.1404953, without a debugger.
The 600 s/resource guards remained active. These failures are tooling evidence,
not guest fatal177 or a successful stage trace.

A read-only live census validated guest base 0x300000000 against original
retail bytes at guest10000, scanned 401612800 readable bytes in 0.906 s, and
found one resource-shaped ID match with length42480: object59419E90,
packfile5945CAB0. A later bounded snapshot found root5945CE10, variants5945CE20,
one hkAnimationContainer variant and lookup result+8=5945CE70. Packfile hashes
before/after those unpaused reads were identical:
`a7d44827af90d0bdfe7719f60cebc21cd8b816685bb38ca3b43b1d96d7fccb6e`.
Header and all original section fixup/trailer regions equal the independently
extracted native raw span. All 315 local/global pointer expectations match
this retail base; native matches257 and differs58. The captured retail root
variants pointer and animation lookup are populated where native is zero.

Static original PT_LOAD descriptors identify these reader slots. The retail
three-slot table is unique in the audited image. The native fatal reader's
vtable matches the debug table; no live retail reader object was captured.

| Slot | Meaning | Debug code / descriptor | Retail code / descriptor |
| --- | --- | --- | --- |
| 14 | getContents | A158A8 / E6D758 | 99253C / DDC100 |
| 28 | getPackfileData | A0A6E4 / E6D348 | 987378 / DDBCF0 |
| 2C | loadEntireFileInplace | A0C09C / E6D468 | 988D30 / DDBE10 |

Debug vtable1006D9C8/reader TOCE9A128 maps to retail1006CD78/TOCE08F7C.
Existing constructor/reader instruction comparisons above remain scoped to
their measured displacement differences; full referenced callee/data parity
is unproved. These snapshots are post-load retained objects, not equivalent
entry/return traps or reference pre-relocation raw bytes. They establish the
same-resource final pointer/lookup difference, not whether native skipped
relocation or later cleared the fields. #3 stays open for those live operation
boundaries. No native gameplay, fix or performance acceptance follows.

Private evidence lives under `temp/issue3-reference`: `reader-map.json`,
`savestate-identity.json`, per-trial launch/final/resource logs, and replay2's
`census/report.json`, `loaded/report.json`, `fixup-comparison.json`. Source
observers, savestate, logs and payloads remain ignored.

## Native relocation store boundary, 2026-10-11

Run `20261011T151440.055108Z` used a copied generated tree with narrow
reader-return and local-store observers. Original instruction/call bytes were
validated privately before installation; preserved generated inputs were not
edited. The visible LANGUAGE window was verified before user navigation; the
user then reported completion of the requested transition. No later rendered
race was observed. PID9756/create_time1791731680.1860416, EXE SHA256
`44093642bbb96321ce5c59e45dee4c14e2dd76fc2338f19e438eb4a8d697d71e`,
named-US ELF SHA256
`3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706`.
It ended naturally at 209.031 s, host0, with the original fatal177. A later stop
marker did not terminate it. Muting and the normal 600 s/resource guards held.

All five boundaries belong to thread24076, resource4E0860F0/ID
`000a8a45293a530c`, reader4B9FDA00, result4E086060 and raw EA0/42480 bytes.
Each raw/header/fixup metadata identity was checked. These are executed observer
sites, not sampled native PCs or an unwind.

| Boundary | Observer site | Matching / zero local-global fields |
| --- | --- | --- |
| Before loadEntireFileInplace | 72F028 | 0 / 315, original unrelocated input |
| After loadEntireFileInplace | 72F054 | 257 / 58 |
| After getPackfileData | 72F0A4 | 257 / 58 |
| After getContents | 72F0E8 | 257 / 58 |
| After four animation lookups | 72F180 | 257 / 58 |

Before-load SHA256 equals the independently extracted raw span
`24256e3c1ca78d7fb13219cf840307e5128dfe319528a77eb30777a723bc2182`.
All four later complete packfile hashes equal
`b0c44c6a129dba13cee54f2cf399ba16748d023ceabc9ba8906f1c5239825baa`.
The 58 pointer differences therefore exist when relocation returns; the captured
later operations did not clear previously correct fields.

An observer immediately following the original local-fixup store at A0C234
recorded the computed value and a read-back. The first recorded store targeted
360 with expected370 but read back zero. The seven low stores were
360→370, 370→380, 374→3A0, 3C8→3F0, 3D0→400, 428→470 and 464→530;
all read back zero. The next 25 recorded local stores at6100 and above all
read back their computed values. The 32-store cap was reached; later local
stores and individual global-store execution were not observed.

The original low addresses are unchanged by alias normalization. Their widths
are within VM bounds. Fast stores below1000 delegate to vm_write32; its
vm_null_store path drops stores below1000 by default. Earlier explicit DROPPED
logs establish this mode was active before the capped print budget expired.
The observed first local-store difference matches that path: an expected pointer
was computed but the low-address store did not land. This identifies the first
observed divergent relocation operation for #5. It does not establish why the
input buffer's base was zero. Allowing null-page writes would obscure that
earlier defect rather than establish a valid allocation.

The complete private plan/report accounts for every one of the315 fields.
All58 differences are below1000: seven local and51 global sources360..528;
all257 matches are above the cutoff. Retail still matches315/315 after rebasing.
The same guard covers the global addresses, but their individual executed stores
were not traced. Another78 virtual/finishing records are inventoried separately;
they are not78 proven successful callbacks, vtables or registrations.

The format-independent audit and v4 BE32 plan builder are proposed upstream in
[ps3recomp PR232](https://github.com/sp00nznet/ps3recomp/pull/232), commit59b1a21.
Ten authored regressions cover missing/correct pointers, rebasing, identity and
shape rejection, ordering limits, overflow and preservation of inputs including
hard links. It reports every field and refuses raw-only success. Only source,
synthetic fixtures and a reusable capture guide are published.

Private evidence: `temp/issue5-stages/install.json`, `pointer-plan.json`,
`all-pointer-history.json`, `pointer-accounting.json`, `stage-manifest.json`,
`all-pointer-stages.json`, `native-stage-verification.json`, diagnostic EXE/PDB
and the run's stage/resource/reader/result/local-store captures. Temporary hooks
remain only in the ignored diagnostic copy; the ordinary generated tree is
selected again. The allocator/raw-base origin needs a bounded follow-up. #1's
PC/input audit and #3's equivalent reference operation mapping remain open;
native race, graphics, audio, saves and performance acceptance remain unproved.

## Native buffer producer boundary, 2026-10-11

[Issue52](https://github.com/robbe1912/motorstorm-mv-recomp/issues/52) traced the
earlier zero buffer without changing allocator, stream or relocation behavior.
Original named-US bytes and symbols distinguish the resource's allocation from
its stream read. Constructor72EE9C obtains length through the stream, requests
length+16 through allocator virtual slot+8 at72EF5C, stores the returned address
at object+24, and aligns it into r31. Operator889194 reads a Stream::Block into
that address and returns the original stream reference, not an allocation.

The muted manual native run `temp/runs/20261011T154742.134739Z` verified an owned
visible window before readiness. The user reported selecting a bike and trying
to start a race. Native PID12752/create1791733662.1584623 used diagnostic EXE
SHA256 `127ebf8b00770294280a074ac2be093267714a3383ba040e824a9bd74eb4997c`
and original debug ELF SHA256
`3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706`.
It exited naturally after190.938s, host return0, with the original fatal177.
No race rendering was established. Host0 is not successful race entry.

Nine executed captures identify the same ResourceID000A8A45293A530C,
object4E0860F0 and thread9476:

| Executed boundary | Observed value and meaning |
| --- | --- |
| Before allocator call72EF5C | Allocator object1013BA88, vtable10066160, slot+8 descriptorE5B310, code4F8FF8, TOCE8A6C0; request42496. |
| Allocator entry4F8FF8 | Same allocator object and request; original HavokAllocator::Alloc implementation. |
| Small call4F9170, return4F9174 | Requested42496 in r3; returned r3=0. Original thunk4F8D30 tail-calls guest mallocC1CCB4 with TOCE9A128. Interior malloc decisions were not captured. |
| Virtual allocator return72EF60 | Returned r3=0 before the constructor stores or aligns it. |
| Before block read72EF84 | Object+24=0, r31=0, Stream::Block destination0/length42480. Its readable64byte prefix was all zero. |
| After block read72EF88 | r31 remains0; r3 is stream0FEFEA00. The prefix now contains the original Havok header. This return is a stream reference. |
| Reader-constructor return72F028 | Object+24 and r31 remain0; r29 retains42480. Arguments r4/r5 for loadEntireFileInplace have not been prepared at this hook. |

Thus the first captured producer supplying the invalid base is the small
allocation call, whose zero return propagates unchanged through the allocator
and constructor. This is earlier than stream filling and relocation. It does
not establish why malloc returned null, nor whether its internal heap state,
failure handling, lower calls or translated control flow is wrong. The
pre-allocation object+24 contents are uninitialized storage, not evidence of a
valid pointer being lost. The null-page guard remained active; DROPPED entries
are retained. No replacement pointer, null-write override or forced success was
used.

Observers were installed only in ignored `build/generated/havok-origin-oct11`.
All77 original selected generated files and the original ELF hashes were
verified unchanged. Private `temp/issue52-origin/install.json`, original-byte
maps, EXE/PDB/build identity, and the run's `origin-audit.json` retain hook
identities and every capture hash. The audit initially rejected an incorrect
r4/r5 expectation at72F028; original code showed that hook is the previous
reader-constructor return. The corrected audit checks the retained r31/r29 and
records that limitation explicitly. It reports the observed null producer,
not a successful allocation. The ordinary generated selection was restored
and rebuilt afterward.

The next bounded seam is [the small allocator's guest malloc path (#54)](https://github.com/robbe1912/motorstorm-mv-recomp/issues/54): capture its
heap/arena state, requested size, selected failure/return branch and relevant
lower-call inputs/results, then identify the first divergence against an
equivalent working operation when available. A generic regression must
reproduce the proven instruction, call/ABI or memory-contract defect with a
valid initialized heap and sufficient space; asserting that every allocation
must succeed would incorrectly suppress legitimate failure. No allocator or
runtime fix is justified yet. #1 and #3 retain their independent proof gaps;
native acceptance remains unfulfilled.

### Malloc capture gap and fork capacity trial, 2026-10-11

The private malloc experiment adds entry, first-hit branch, lower-call,
syscall and return observers, selected by the same resource and thread as
the producer capture. It leaves original guest data and behavior unchanged.
One build failed on duplicate context declarations; its errors were retained
and the diagnostic declaration/include and two return-hook placements were
corrected before launching. Its EXE SHA256 is
`a7f18623ad29aecbfe1ca323ff7e4fae414f8f895adc86160ec6c9a802ffb259`;
the original ELF identity is unchanged from the producer run above.

Two muted 600-second trials did not reach the selected resource:

| Run / PID / creation time | Result |
| --- | --- |
| `20261011T160807.968606Z` / 30588 / 1791734887.9913192 | Visible window; no selected captures; duration guard at 600.485s |
| `20261011T162214.915838Z` / 12384 / 1791735734.9185293 | Screen-observed ordinary menu inputs; no selected captures; duration guard at 600.5s |

The second run visibly progressed from LANGUAGE through normal PLAY, race
instructions, race selection, SELECT A BIKE and the MOHAWK INDIANA variant.
The main-menu background was black; race selection showed oversized colored
bands instead of ticket art; the bike model was missing. A logo and triangular
bike icon did render. Confirmation did not produce a visible race. Run-local
navigation observations and PAD acknowledgments are retained privately.
These observations fail the native assets/race DoD. They do not establish the
selected malloc's internal failure path. Issue #54 stays open: the entry,
heap state, syscall arguments/result and actual null-producing branch are
still missing from an executed same-resource capture.

A separate synthetic test exercises real VM initialization, commitment and
memory syscall handlers, without guest payloads. On both the curated runtime
and a narrow fork baseline, allocation seven of eight 24 MiB requests fails
with CELL_ENOMEM while the API reports 69 MiB available. Alias collision gaps
exhaust the old virtual arena before the advertised 213 MiB physical pool.
This establishes a component defect, not its relation to the selected native
malloc. An isolated old-allocator trial with the updated alias helper still
reproduces that seventh-allocation failure.

The [fork trial](https://github.com/robbe1912/ps3recomp/tree/codex/memory-pool-capacity)
preserves the local collision-guard dependency separately in `8ad9fdb`,
the initial red fixture in `15b628c`, and the candidate in `dcd6f48`.
The candidate enlarges virtual space to 512 MiB, independently enforces the
existing 213 MiB physical budget, and resolves registered aliases above the
old arena end. Its Windows clang-cl fixture passes all eight requests and
alias checks, then verifies genuine physical exhaustion on request nine,
unchanged output and unchanged availability. Windows/Linux CI steps are
added; remote CI and Linux execution are pending. Reclamation, registration
lifecycle/capacity and commit-failure accounting remain inherited limitations.
The candidate is not adopted into the game runtime and no upstream PR was
opened. No null-write override, substituted buffer or forced success is used.

Config was restored byte-for-byte to the preserved original selection and
the ordinary build completed with EXE SHA256
`d070786a4cee10ccfe925e13ba65ade0bd71031b7078174ec950682d3d1e5186`,
logs `temp/builds/20261011T163331.364781Z`. Diagnostic trees, installers,
strict auditors, binaries and test result/hash manifests remain private.

### Executed guest malloc failure, 2026-10-11

The user navigated normal PLAY and attempted race start in the muted, visible
native run `temp/runs/20261011T204610.305634Z`. They reported that loading stayed
black. PID26228/create1791751570.4203024 used diagnostic EXE SHA256
`2f0a46058f43ca0eca55f243771e1ca4fdb1cfa8e60361e4935a444b03e09646`,
with the unchanged original ELF identity above. It exited naturally after
170.797s, host return0, with the original fatal177. This fails race acceptance.
An accidentally occluded desktop screenshot is explicitly invalid as native
rendering evidence; the user's black-screen report is separate evidence.

The same ResourceID000A8A45293A530C, object4E0860F0 and thread28812 are present
through36 executed observations. The original request42496 enters mallocC1CCB4
with TOCE9A128 and initialized heap1021E808. Its heap-extension path executes
syscall348 atC1D3F8: size1048576, flags400, outputEA0FEFE6B0. AtC1D3FC the
returned status is sign-extended CELL_ENOMEM80010004. The original guest
failure branch loads FFFFFFFF from its stack output atC1D40C, takesC1D67C and
returns0 atC1CED8 to small-call return4F9174. Virtual return72EF60 and the
constructor/payload buffer retain0. No guest failure was overridden.

Read-only, unlocked runtime snapshots around that syscall show the cursor
moving4E100000 to50000000, the old virtual arena end. All31 candidate1MiB
positions below that end conflict with recorded aliases. Both snapshots show
34 active slots totaling147849216bytes (141MiB), below the advertised213MiB
pool and1024-slot limit. The runtime's collision walk and subsequent arena
limit check explain the returned ENOMEM. These are observations around the
call, not an atomic allocator-internal snapshot or working-reference proof.

The original auditor correctly rejected two malloc return records. The
second occurs after the block read, belongs to a separate32-byte reader
allocation and returns nonzero. A separate primary-call audit bounds records
between the executed before-small-call and after-small-call hooks, requires
exactly one matching entry/return and return address4F9174, and retains the
later return separately. Identity, readability, syscall arguments, actual
failure branch and downstream null checks remain required. The initial
rejection and all raw records are preserved privately.

This completes the interior-null diagnosis in [#54](https://github.com/robbe1912/motorstorm-mv-recomp/issues/54).
[The generic runtime correction (#7)](https://github.com/robbe1912/motorstorm-mv-recomp/issues/7)
can now trial the narrow fork capacity change against this demonstrated seam.
The same synthetic regression on this project's unmodified runtime fails
allocation7 with69MiB advertised available; registered aliases also fail
above the old alias boundary. After the fork hunks, eight24MiB allocations
and all alias checks pass, while genuine physical exhaustion on request9
retains ENOMEM, the output sentinel and21MiB availability. Reproduce with
`python scripts/check_memory_capacity.py`; no game input is needed.
Private red/green evidence is in `temp/checks/memory-20261011T205218.740466Z`
and `memory-20261011T205234.022775Z`. Native allocation/race acceptance for
the candidate is recorded below; #1/#3 reference gaps remain independent.

The user repeated normal PLAY/vehicle selection in native trial
`temp/runs/20261011T205310.337110Z`, PID29220/create1791751990.446359,
EXE SHA256 `4d3f53750131c217020e7e0ff88fe626124d981a2d217d9a3042e1fd67c8267c`.
For the same ResourceID/object, thread8760 executes successful heap extension
and malloc returns52D00010 to4F9174. The virtual return, constructor field,
aligned block destination and reader-constructor return retain52D00010 with
resource length42480. Its readable64-byte header exactly matches the original
resource header from the baseline. The private green auditor requires the
original call interval and retains all55 observations. No fatal177 is captured
or logged in this trial; GAMEFLOWMANAGER::Construct executes later. This passes
the previously failing allocation boundary, not Havok finishing/race rendering.
The user's report establishes vehicle selection and an open window, not a
visible race. File reads/presents later stop advancing in the retained trace.
At the user's shift to menu-asset work, an identity-checked owned stop marker
ends the run at379.515s/guard return1. The wrapper restores ordinary generated
selection and rebuilds candidate runtime EXE
`2744656598efc6d3c6529bc40daf00c1d3c88615c19f89b4fff01713cccd52e9`.
Both Windows and Linux CI capacity checks pass in [PR57](https://github.com/robbe1912/motorstorm-mv-recomp/pull/57).
Issues #7/#13 remain scoped to their own acceptance; overall DoD is unfinished.

## Native physics-completion wait, 2026-10-13

The optimized muted run `temp/runs/20261012T234028.365932Z` used PID28224,
EXE SHA256 `1f003a531bcb20a84eb4ad99e37541e820bd246849f31b37b4773fb62a4f56f8`
and CodeView `525344536248f331c391b88b4c4c44205044422e01000000`.
The user reported attempting normal PLAY/race start and then a freeze.
The route was user-assisted: the replay recorded zero consumed inputs,
so it does not prove the exact navigation or accepted start packet.
The launcher closed at its 600 s bound; its return1 is a guard result,
not evidence of a crash. No controllable native race was observed.

Private `temp/issue13-route/unwind_mixed.py` extends the earlier
executable-only inspection across Windows frames. Before unwinding, it
checks dump/EXE/PDB CodeView and the launch EXE hash. Each additional PE
must match its captured timestamp, image size, checksum and CodeView;
the report records the file hash. Captured stack memory and bounded x64
unwind records recover callers; no stack scan is used. Unsupported records
stop. The only admitted syscall leaves are checked Nt/Zw export stubs
in the matching ntdll image, and the optimized executable's previously
checked volatile-only leaf. Nonvolatile registers are restored;
volatile caller registers are not recoverable by this method.

Both `race1` and `race2` dumps identify native TID31116 as the game main
thread through its startup/`ppu_run` callers. Their 26-frame chain reaches:

`NtWaitForAlertByThreadId → RtlSleepConditionVariableCS →
SleepConditionVariableCS → sys_cond_wait → lv2_try_syscall → lv2_syscall →
hkSemaphore::acquire (0xB15714) →
hkMultithreadingUtil::waitForStepWorldFinished (0xA012E8) →
HavokSystem::Update (0x4F05D0) → HavokUpdate (0x4F0BF0) →
MotorStorm::Update (0x4EBD10)`.

Function names are independently resolved from the original named ELF.
The wait belongs to physics completion; the two other semaphore stacks
remain Havok worker job waits. They are not the primary game thread.
This also supersedes using the old marker6 PVS diagnosis for this run:
its sampled WWS queue has hint/taken0 and all inactive markers.

`inspect_main_wait.py` independently checks that the matched
`sys_cond_wait` machine code assigns entry RCX to RSI exactly once before
the sampled wait return address. The OS unwind restores that nonvolatile
RSI as context pointer `0x34FC5EF120`. A freshly compiled header-layout
helper establishes `sizeof(ppu_context)=1104`, GPR offset0, LR1032,
CIA1064 and thread-id1072. Both dumps contain the same complete context
SHA256 `c7634ee4fddeb22317aee04008e130bb22edc80c9793a81d8d9a516cf00d524e`:
guest thread1, syscall107 (`SYS_COND_WAIT`), condition8, timeout0,
LR `0xA013F4`. CIA is0 and is not used as an executed-PC claim.

Original function bytes show the utility pointer in guest r27
`0x4BE34700` and completion semaphore in r29/r31 `0x4BE3470C`.
The semaphore acquisition loads its condition ID from object+0xC;
the enclosing wait acquires utility+0xC once per worker. Original worker
code contains the matching completion release to utility+0xC before
waiting for its next work. This identifies the producer contract, not
proof that a release executed in the frozen run.

Read-only REA query `temp/research/rea/wait-20261013T022331` preserves the
original Ghidra project. Independent ELF comparison gives full byte/body
coverage for semaphore acquire (168 bytes), wait-for-world-finished
(296 bytes) and start-world-step (164 bytes). The worker export covers
3020 of3504 symbol bytes: its matching release span is readable, but
its full body/caller inventory must not be claimed complete. Pseudocode,
instruction bytes, contexts and dumps remain private.

The two snapshot starts are 166.559 s apart. Their repeated wait/context
observations do not establish uninterrupted blocking or signal chronology.
Neither dump contains the guest utility object nor the host condition slot.
No condition corruption, lost wakeup, unfinished SPU job or instruction
translation defect has yet been demonstrated. Runtime/generated source
and the game executable were unchanged by this inspection.

The next bounded capture for [#13](https://github.com/robbe1912/motorstorm-mv-recomp/issues/13)
must bind the current main context, condition/mutex/waiter, utility/worker
objects and outstanding Havok job state to the actual producer threads.
The first hypothesis is unfinished work preventing the original worker
completion release; falsify it with an executed matching release. The
alternative is a semaphore/condition delivery mismatch; establish it only
with the matching guest release, syscall result and waiter state through
delivery. Compare an identified translation operation against an independent
oracle before changing runtime semantics. Retain the exonerated busy-wait
counter decrement and PM CPU spans; never force the completion wait through.
The separately decoded [reference checkpoint](TRANSLATION.md#read-only-rpcs3-checkpoint-decoding-2026-10-13)
is another executable/checkpoint and does not prove native race acceptance.

## Constraint consumer and task-slot exhaustion, 2026-10-13

The unchanged optimized executable was observed in owned muted run
`20261013T003649.802081Z`, PID25428. Its executable/ELF identities match the
preceding investigation. The English input and observed MOHAWK confirmation
have consumption receipts; intermediate navigation has no receipts and is
user-assisted. This does not establish an entirely automated normal-PLAY
route. The user requested termination: the launcher closed through its explicit
stop marker at 359.719 s, return code1/guard=true. This is not a natural crash.
No controllable race or performance result was obtained.

Two read-only completion supplements, 77.968 s apart, bind main native TID38544
to guest thread1 and native workers37984/26104 to guest threads8/9. Matched unwind
metadata and control-flow proof establish the recovered entry-context
registers; compiled header offsets bind the actual PPU/condition/mutex layouts.
The main utility is `0x4BE34700`, with outstanding-step byte 1 and worker count 2.
Its completion semaphore at +0xC has count 0, mutex 12 and condition 8. The active
host mutex has owner 0/depth 0; the condition address matches the unwound operand.
Exactly one linked waiter is present, next=null/signalled=0. Sequential reads
are not an atomic snapshot or evidence of release/signal chronology.

The workers' original `finishJobAndGetNextJob` prologue preserves the JobQueue
in r25 and ThreadType in r21. Their captured values bind queue `0x4BE20C00`
and selectors 0/1. Original `lockQueue` returns the DynamicData pointer held
in r31, here `0x4BE22D80`. That pointer is not the JobQueue object. The
captured queue lists select [0,1], [1,0] and [2] for selectors 0,1 and 2 respectively.
DynamicData has active count 0, waiting counts 2/0 and pending ring counts 0/0/7.
The third ring has buffer `0x4BADB800`, capacity 7 and head/tail 0. Its entries
were not captured. The entire 1024-byte DynamicData read is identical in both
supplements, SHA256 `efdc6c9d4b5fd5bfc84ca5a0304a64db7e493d93ded59e5551cb089a29a75ee0`.
Thus the two waiting workers' configured lists exclude the populated ring.

The retained log binds the constraint consumer to this same queue: taskset
`0x4B835600` on SPURS `0x4003F380` creates the ELF at `0x10076000`, with
argument words [0x4BE34C80,0x4BE20C00,0,index], index 0..3 and context 0.
The registered image is 2, `hkspursconstraint`, whole fingerprint
`6E32DC7CD6DED19D`. There are 128 successful logged creations; their printed
creation IDs 1..128 are not the taskset's zero-based slot indices. All occur
before the logged `GAMEFLOWMANAGER::Construct`. The error log retains 624
`CreateTask` failures for this taskset because all 128 enabled bits are set,
and 256 image 2 entry returns. Returns are not necessarily unique completed
tasks: the log also records redispatch. Counts do not provide cross-log wall
chronology or prove the original queued jobs retired.

There is now a full-program reference anchor. The original 124150-byte ELF
at named-debug file offset `0xF06000`, launch-US retail file offset `0xE75380`
and saved reference VM address `0x10075380` is byte-identical, SHA256
`ea699fabe5dbfdabea6c42cc8f920e2be446d13f627a22de3f9bd8f5acc79fbc`.
A bounded sparse-map search yields one structurally filtered taskset candidate,
`0x5683A400`, SPURS `0x5004F380`, workload 5. Its four nonzero TaskInfo ELF
references are slots 0..3 with arguments [0x56E39A80,0x56E25A00,0,index],
context 0 and all six task bitsets zero. That queue's DynamicData has active 0,
waiting 0/0 and pending 0/0/0. This is one different checkpoint, not executed
exit chronology or universal PPU executable equivalence. The saved-state
source hash remains unchanged. Original bytes and candidate-search outputs
remain private.

Focused original-byte verification fully covers `lockQueue` 140 bytes and
`setSpuQueueCapacity` 1516 bytes. Exported decoded bytes also match the original
for the constructors and launch helpers, but uncovered symbol bytes remain:
JobQueue constructor 544, utility State constructor 256, `initSpurs` 28,
`startSpursTask` 28 and HavokSystem constructor 716. Their pseudocode is not a
complete function-body proof. The named constraint ELF's `main` calls
`cellSpursMain` then `cellSpursExit`; the latter invokes the taskset syscall
entry with request 0. This is an original code path, not a captured executed exit.

The runtime's creation path allocates only from clear enabled bits, whereas
its async-entry return path clears only its host running bit. Exact-revision
RPCS3 inspection shows a distinct destroy-task request clears enabled state;
its EXIT handling additionally depends on exit-context fields. An unconditional
clear on every entry return is therefore not a justified fix. The next step
for [#71](https://github.com/robbe1912/motorstorm-mv-recomp/issues/71) is to
capture the actual exit request/context, taskset bitsets and subsequent creation
result, then test the identified lifecycle seam with independent authored
cases for genuine exit, yield and ordinary return. Runtime/generated code and
the executable remain unchanged. This evidence does not close #71 or #13,
reopen retail mstream, or justify forcing a completion wait.

## Executed constraint exit requests, 2026-10-13

An opt-in, image-filtered lifecycle trace was added first on own fork commit
`dbe0b4b`; only its logging hooks were overlaid, preserving curated cleanup.
The checked optimized build passed, EXE SHA256
`a0996b8aa794ddf49f7bc9b722ea35cd43b959be0e6487c272a35d582b7c6298`.
Owned muted run `20261013T011944.197576Z`, PID36928, records the same named
ELF identity and trace budget2048/image2 in its launch metadata.

Five consumed packets are retained: English, observed main-menu PLAY,
festival-help dismissal, SELECT A RACE and MOHAWK confirmation. The replay
reports four route inputs and a separate bike confirmation; one configured
class-selection step has no receipt. No fully acknowledged route or native
race control is claimed. Internal captures retain real intro video and the
malformed selection graphics.

The stderr trace contains 256 request0 events and 256 paired before/after
entry-return cleanup events. A bounded parser validates every triplet by
native thread, taskset `0x4B835600`, image2, task ID and monotonic tick order.
All requests have exit-context fields x2FC0=0/x2FD4=0; each selected enabled
bit remains1 after cleanup. Maximum enabled count is128. There are 126 distinct
observed task IDs, not128 unique completed tasks; duplicate/absent slot
identities require separate ownership investigation. The stderr SHA256 is
`a4eef55cb0b07d9cd50a84ad3044fce26571a5fb41add0f327435793420597c5`.
The trace budget was not exhausted. These are sequential reads and per-thread
event ordering, not an atomic taskset snapshot. Existing source handles this
request by halting, then clears only host running state after return.

The process later executes the original Havok allocator fatal for an 8320-byte
request and logs unresolved indirect target `0x88F50115` on guest thread8,
LR `0xB12350`. It calls `sys_process_exit(0)`; final metadata records349.906s,
return0, guard=false. Zero exit status does not make this successful gameplay.
No driving, playable race or minimum frame-rate result is claimed.

Upstream PR240 was rechecked and is now merged, commit
`308aeaeea9de306a084495916a6e61493bee3e3c`. It removes three native-struct
writes from the guest taskset. The curated creation path still increments
`taskset->taskCount`. An isolated compiled probe using the actual header
confirms native fields initialized/taskCount/shutdownRequested at offsets 0/4/8.
Incrementing the native counter changes byte4 of the real guest RUNNING
bitset. This probe is layout evidence, not an executed API regression or fix.

The next corrections must separate guest-layout corruption, explicit task
destruction, ordinary return/yield and fresh task incarnations. Validate the
merged upstream layout change on our fork first, then use an independent
lifecycle regression before retiring slots. Do not unconditionally clear
enabled state on every return, erase the original errors, or infer that slot
recycling alone proves a race. Raw trace/analysis/layout artifacts stay private;
#71 and #13 remain open.

## Guest taskset layout correction, 2026-10-13

[#73](https://github.com/robbe1912/motorstorm-mv-recomp/issues/73) adopts only
the three upstream PR240 native-field store removals after a fork-first trial.
The independent fixture compiles the complete affected API definitions and
real BE taskset builder. A preexisting RUNNING/ENABLED pattern makes slot1
the first free slot; creation may set only its READY and ENABLED bits, return
BE slot1 and dispatch once. Destroy/Shutdown preserve the header. The fixture
checks the other 128 header bytes, allocation guards and null-pointer errors.
It stubs image sizing/dispatch and executes no game/SPU code. Baselines
`dbe0b4b` (fork) and `b921cad` (curated) fail all three APIs; each corrected
tree passes. `scripts/check_spurs_guest_fields.py` retains identities and
logs privately. Attribution and exact adopted commits are in [vendor provenance](../VENDOR.md).

The checked optimized native build succeeds, EXE SHA256
`5ba10a87abd5667cc498317282b5236d51a4dcadad9cc117be7a592fb945c111`.
Muted run `20261013T132937.665001Z` acknowledges English, PLAY, festival-help
dismissal and SELECT A RACE. The next bike-class reference does not match;
replay ends at required step4 without target observation. The process closes
at its 600.718 s duration guard, return1. It contains no acknowledged MOHAWK
confirmation and cannot establish race-load behavior. Selection assets remain
malformed. Later intro-skip trial `20261013T134536.081481Z` reaches PLAY;
[operations](../OPERATIONS.md) owns that narrower proof.

The source-only layout contract is corrected; native race control, the physics
completion wait and genuine task-exit retirement remain open. In particular,
[#74](https://github.com/robbe1912/motorstorm-mv-recomp/issues/74) must distinguish
exit from ordinary return/yield and protect task incarnation ownership. This
three-store correction does not clear enabled state or suppress original errors.

## Explicit task dispatch identity, 2026-10-13

[#78](https://github.com/robbe1912/motorstorm-mv-recomp/issues/78) isolates the
owner handoff prerequisite to #74. The dispatcher previously read the last
caller's shared taskset/slot globals after fingerprint resolution. An authored
fingerprint adapter publishes caller B's taskset `0x20000`, slot7 before A's
capture. Both complete old dispatch functions capture B for A, and generic
policy dispatch inherits B as a task owner. Their actual-source fixtures fail
both checks. The new task API receives owner values explicitly; generic async
work receives zero ownership. CreateTask, return redispatch and signal redispatch
pass their local identities; worker context reads use the captured job owner.
The inherited optional event diagnostic remains a generic unowned dispatch;
it is disabled in native MotorStorm trials.

Both corrected trees pass 256 owner-preserving dispatches, generic ownership,
argument copies, invalid slot rejection, registry miss and spawn refusal. This
is a dispatch-boundary regression: thread creation, phantom registration and
timing are adapters, not executed host threads or guest tasks. Actual guest-header
API fixtures also pass after their dispatch adapter is updated. The full fork
workload unit compiles; the optimized curated native build succeeds, EXE SHA256
`09a7e77f35c7eebc741e95e60bd9749cf6eb235aa875060b1945b690728260a2`.
Fork provenance is in [VENDOR](../VENDOR.md), checker usage in [BUILDING](../BUILDING.md).

Muted native run `20261013T140401.886289Z` skips the observed Sony intro, reaches
PLAY and acknowledges help dismissal, race ticket, bike class and MOHAWK
confirmation. Internal captures show the original video, logo and bike-class
icon; race-selection tickets and the MOHAWK 3D preview remain malformed. Its
300 s duration guard closes at 301.610 s, return1, only seven seconds after
MOHAWK confirmation. This is an attempted normal race start, without race-entry
proof. Replay correction: two nested menus share SELECT A RACE: the ticket
points screen, then the Anything event screen. They require separate observed
confirmations. The class crop also included moving background
video, causing an exact-pixel gate failure. Private continuation gates now
require the observed ticket text and a crop inside the bike silhouette, with
the unchanged 0.95 correlation threshold. Captures and private profiles are ignored.

Longer run `20261013T140946.452559Z` with the same EXE acknowledges the two
race menus separately, bike class and MOHAWK confirmation. The captured trace
has 256 matching per-thread request0/before/after triplets, covers all128 slot
IDs, and retains the selected enabled bit in every cleanup pair. Maximum
enabled count is128, followed by all-enabled creation failures. The older run
covered126 IDs; the independent dispatcher regression establishes the ownership
fault, while this native comparison also includes the earlier guest-field fix
and cannot isolate every effect. Guest fields are sequential reads, not atomic
snapshots or generation proof. The selected bike preview remains malformed;
internal frame68 reaches the original track-map/loading advice screen, then
no further capture arrives before the 480.453 s duration guard closes the
process, return1. This is race loading, without native race entry or control.
Final stderr SHA256 is
`3fd53f1e2fd8ac5cf0817d43c1b833c6c088ff77cb046d01a5551f66fe9089d9`.
The earlier 8320-byte allocator fatal and unresolved indirect-call error do
not appear in this bounded run; this does not establish their correction.

Exit reason, incarnation generation, fresh versus suspended LS and atomic
creation/retirement remain #74. This ownership unit preserves the curated
enabled-bit cleanup policy and the original allocator/indirect-call errors;
dispatch counts are not a completion or gameplay claim. Retail mstream is parked.
