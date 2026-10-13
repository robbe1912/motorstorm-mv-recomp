# Translation provenance and methods

The named corpus has 50839 function names and 870 structs, not a retail 03.10 address map. Named-US debug compilation includes 41 CUs, GCC 4.0.2, CELL 4.1.15/rev 1141 plus older linked CELL comments. Sibling Pacific Rift/AP viewers with GCC 4.1.1/SDK mixtures do not establish retail compiler provenance. Symbols/DWARF/ABI guide matching but cannot uniquely recover original source. Reuse existing semantics/tools before inventing infrastructure.

PPU ELF/reloc/function-scoped RPCS3 hashes and LLVM host objects do not recover source/assets. SPU cache identity depends on complete LS content and entry, not a name/address. Independently written reader validates v1 BE 8-byte header (CRC 16/wordcount 16/entry 32), truncation and declared legacy no-CRC cases; payload is original opcodes with zero holes/overlays, kept private. Never merge variants into synthetic LS.

Exact debug export 2770 verified blocks/143 multi-code addresses. Final declared-base comparison 2663/2770 to 13 images, 7 ambiguous, 107 unmatched/17900 bytes. Initial base 0 wrapper 610 was misleading and superseded. Retail 2096 legacy blocks no CRC: 514 matches to debug images/11 ambiguous; not full compatibility or permission to mirror trees. Prefer smaller unmatched seams and full content verification.

Historical translation backlog (F-tr01..16) is research, not landed-completion proof:
- Named bounds + dataflow jump-table recovery; data-in-text guards to prevent silent no-ops; correct lswi/stswi where demonstrated.
- Position-independent SPU lifting requires correct PC-relative data/branches, absolute LS references, fixed host externs and resume contract; rebasing function addresses alone is insufficient.
- Function-level identification/DWARF ABI checks for missing DSP variants; staged image inventories should include real code extent/unsupported count/registration identity.
- Flat mapping/LTO/fence consolidation are profile-driven candidates, not measured wins.
- Shared upstream fixes are selective with attribution; no wholesale replacement of dirty runtime or GPL RPCS3 implementation copying.

Research method: identify target/version/data, capture exact input/operation, build independent bounded oracle, distinguish semantic bug from test setup, find first differing seam, prove red/green and real runtime effect separately. No original-game patches/forced completion. Source-only changes, coverage counts and FPS labels do not satisfy native acceptance.

Legacy RECOMP_PLAN/triage/milestone estimates and knowledge findings remain private provenance. Current [next steps](../NEXT_STEPS.md) supersedes their priority lists; [vendor](../VENDOR.md) owns upstream status.

## Reuse the existing Ghidra project through REA (2026-10-13)

[REA](https://github.com/morluto/rea) is useful as a query bridge over existing
analysis, not as a PS3 translator or a reason to recover the named corpus again.
Reviewed upstream main `653067d799591ce2b8fdc84e99c160ac17e2860f` and locally
installed `rea-agents@6.4.0` under ignored `temp/tools/rea`, with scripts disabled.
REA is MIT; Ghidra and other providers retain their own licenses. No global
agent registration, provider implementation change or external submission was made.

The supported Windows CLI provider admits native x86/x64 PE only. A direct
inspection of our PowerPC ELF exits 1 with `target_unavailable` / `unsupported
ELF architecture`; its normal launcher creates an ephemeral import rather than
attaching our saved project. Ghidra provider readiness passes locally with Node
22.23.2, Ghidra 12.1.4 and full JDK 21.0.12.1. Unrelated missing Hopper/IDA and
agent registrations do not invalidate that provider-specific result.

The unchanged packaged `ReaGhidraBridge.java` can instead be invoked manually
by Ghidra headless against an existing program. This experiment is outside
REA's supported Windows ELF admission and does not establish the CLI provider's
complete isolation guarantees. Preserve this distinction when using its output.

The saved private project is
`temp/legacy/recomp/out/research/ghidra_ms1_us_oct09/ms1_us_tools.gpr`, program
`EBOOT_MSMVdbgUS.ELF`. Pilot `temp/research/rea/query_existing.py` copies its GPR
and repository into a fresh ignored directory, then uses `-process
EBOOT_MSMVdbgUS.ELF -noanalysis -readOnly`. The unchanged bridge and our existing
`ExportPs3Focused.java` are copied into that directory's script path. Its private
authenticated loopback descriptor pins Ghidra 12.1.4 and ELF SHA-256
`3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706`.
The bridge rejects a mismatching executable hash or provider version. Tokens,
responses, pseudocode and guest instructions remain private. Shut down the
bridge after querying; never open the preserved project for modification.

Pilot `existing-20261013T005019` returns the expected
`PowerPC:BE:64:64-32addr` identity and 107 PixelBuffer, 17 GcRenderBuffer and
185 Vertex name matches. The saved project supplies the names, but several
selected graphics functions initially have a one-byte stored body. A bridge
`analysis_complete` flag or successful decompilation does not prove complete
function boundaries, caller inventories or semantic recovery.

The `--focus` pilot `existing-20261013T005212` reuses the original OPD-derived
TOCs and focused exporter on the disposable copy before querying the bridge.
Ghidra explicitly reports discarding the read-only program changes. Original
project file hashes match before and after. Independent `verify_existing.py`
compares every exported instruction and each bridge 32-byte read with the
original ELF and bounds them by its function symbols:

| Routine entry | Decoded instructions | ELF symbol bytes | Uncovered symbol bytes |
| --- | ---: | ---: | ---: |
| PixelBuffer::Init, `0x79C8CC` | 869 | 3596 | 120 |
| GcRenderBuffer::Create, `0xC80A6C` | 60 | 272 | 32 |
| VertexBuffer::Init, `0x7DAB44` | 160 | 768 | 128 |
| ICE vertex-format writer, `0xC8C980` | 38 | 152 | 0 |

All decoded bytes match; only the last routine has full symbol coverage.
Pseudocode and incoming-reference results are available, but some references
lack a source procedure, and the first three coverage gaps are not classified.
These observations make focused query reuse practical; they do not establish
whole-project analysis completeness, a new renderer fix or native acceptance.

## Read-only RPCS3 checkpoint decoding, 2026-10-13

The user-provided launch-US state is
`F:/Emulators/RPCS3/savestates/BCUS98137/BCUS98137_1_0.SAVESTAT.zst`,
51214995 bytes, SHA256
`30d91bc252d1ae74aa6377665e3bb6a704b1793002efa360de589f9cf9b204ed`.
Its header names RPCS3 `0.0.43-20273-987129bc Alpha | master`,
build commit `987129bc91191b42bfc17256641037c76c7a856e`, title BCUS98137
and state date `2026-10-13T02:00:47`. It was inspected offline without
restoring the emulator or changing the source. The private key field was
skipped and never printed. Exact-revision RPCS3 source is private inspection
material; no GPL implementation is adopted into this runtime.

Private readers under `temp/research/rpcs3-savestate` follow the recorded
serialization versions and bounded exact reads across Zstandard frames.
The successful `vm-index-v2` indexes41 shared and47 private VM images,
9 locations, with VM stream offsets298..132275500. Failed initial indexing
is retained separately. The sparse bitmap describes nonzero128-byte lines;
an explicit zero bit yields zero, while an absent map remains unknown.
Serialized payload hashes are checked before guest reads.

The candidate launch-US retail ELF has SHA256
`8e0abf4f611752f74f0f726f77f25e7bfef043c964451b96cffe5cf2089f3886`.
Three complete original debug routines have unique matches in its executable
segments, and the saved VM retains those exact retail bytes:

| Named-debug entry | Retail/state entry | Compared bytes |
| --- | --- | ---: |
| hkSemaphoreBusyWait::acquire `0xB15968` | `0xA925FC` | 108 |
| WWS marker wait `0xC5C424` | `0xBD910C` | 84 |
| WWS finalize `0xC5BA68` | `0xBD8750` | 72 |

These are individual routine anchors. They do not establish a universal
address map, entire-executable equivalence or matching native checkpoint.

FXO begins at stream offset132275500; its objects have no universal
name/length envelope. `decode_ppu_records.py` locates the PPU ID-map using
ID/type bounds and exact position-checksum tags, then requires all contiguous
records, both terminal tags, field bounds, stack/register validity and a unique
complete candidate. It decodes the version3 PPU layout, the first global
priority tag, packed CR/FPSCR, optional vector data, all GPR/FPR/vector storage
and status-dependent runnable order. It validates16 thread records at
offsets132276831..132295131. Earlier FXO objects are not sequentially decoded;
this is a structurally validated PPU map, not a complete state-file decoder.

Saved `main_thread` ID `0x01000000`, status2, has CIA `0xBD9124`, inside
the matched WWS wait. Its object `0x50054410` points to queue `0x50054480`,
and it requests marker4. The queue's policy is `0x10135180`, length11136,
hint8/taken4, minActive `[2, FFFF, 3, FFFF, FFFF, FFFF]`.
This is one scheduling instant, not evidence of a persistent reference stall
or that the state reaches controllable racing. Thread names/PCs, sparse VM,
raw state and opcode comparisons stay private.

The [native main wait](HAVOK_REFERENCE.md#native-physics-completion-wait-2026-10-13)
is independently established from its matching native dumps. The reference
and native main threads are in different waits; compare their identified
operation contracts rather than equating addresses or scheduling states.

## ps3recomp, REA and Ghidra grounding (2026-10-13, issue 24)

Re-read ps3recomp architecture, graphics, porting and contribution guidance
against upstream master `a2c20108af45174dbb7d3e2f87f6acaaef09c6b4` and REA
guidance against main `0bc422d7bed1184a6b9fc0ea2655e4b2c5e1c4f4`.
Reviewed current upstream candidates without adopting them. Curated native
and fork baselines differ; [selective fork-first practice](../VENDOR.md)
still applies. An upstream code difference is not a diagnosed native defect.

REA practice requires matching target identity, retained evidence, explicit
observation/inference/unknown distinctions, scope-compatible comparisons and
session closure. Current supported Windows CLI admission covers native PE
and raw NMOS 6502, not PPC ELF. The existing unchanged Java bridge against a
disposable copy of the named Ghidra project remains a manual workflow, not
supported Windows ELF admission. It used read-only/no-analysis processing,
original OPD TOCs, authenticated loopback and controlled shutdown. Original
project hashes remained unchanged; no original ELF/project was modified.

Focused exports checked every decoded instruction byte against named-US ELF
`3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706`.
Coverage was partial: ResourceInfo::Read `7FFB40`, 248 instructions and
108 of 1,100 symbol bytes uncovered; SkyMeshRenderable constructor
`6A3EF8`, 56 instructions and 100 of 324 bytes uncovered; EnvironmentType::Load
`6A9938`, 35 instructions and 28 of 168 bytes uncovered; EnvironmentMatrixCalc
`6A3A20`, 25 instructions and 816 of 916 bytes uncovered. The matrix routine's
decompiler switch recovery exceeds the exported function-body coverage;
its pseudocode is not a complete byte-verified transform contract. Local
resource-info fields supported by decoded instructions help check the
[environment buffer binding](GRAPHICS_AUDIO.md), but static flow does not
establish native execution or a rendering fix. Original code, pseudocode,
snapshots and bridge responses remain private.

A subsequent private matrix-export trial used the original ELF's 916-byte
symbol extent explicitly in the disposable copy, disassembled its aligned
addresses and retained separate declared-body versus decoded-byte counts.
It recovered 224 instructions (896 bytes), all exactly matching the original
ELF. Twenty bytes at `6A3A54` through `6A3A64` remain outside the decoded
instruction coverage; their role is not established by that verifier.
The initial strict body/decoded-count equality check rejected this result;
the extent-aware check reports the gap instead of calling the declared body
complete. Original project hashes remain unchanged. No native transform
execution or rendering correction is inferred.
