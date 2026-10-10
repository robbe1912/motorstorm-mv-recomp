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
