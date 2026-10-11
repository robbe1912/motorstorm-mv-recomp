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
