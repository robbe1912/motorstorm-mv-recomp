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
