# SPU image inventory

The private baseline contains 24 SPU image variants; 22 are enabled and the two duplicate named MP3 registrations (220/221) are commented out (see [operations](../OPERATIONS.md)). This page records each image by non-payload identity, byte provenance, producing stage and clean-checkout status. Issue [#28](https://github.com/robbe1912/motorstorm-mv-recomp/issues/28) requested this matrix. Follow-ups for the missing stages: [#36](https://github.com/robbe1912/motorstorm-mv-recomp/issues/36), [#37](https://github.com/robbe1912/motorstorm-mv-recomp/issues/37), [#38](https://github.com/robbe1912/motorstorm-mv-recomp/issues/38).

Setup facts, generation commands and the no-clean-clone caveat live in [building](../BUILDING.md). SPURS ownership evidence lives in [SPURS](SPURS.md). Method cautions live in [translation](TRANSLATION.md).

## Evidence basis

Identities were cross-checked on 2026-10-11 against these private artifacts (read-only; none are committed):

- Registrations: `build/generated/named/spu/spu_workloads.c`, `jobmods_register.c`, `jobmods_manifest.json`.
- Embedded-image provenance: `temp/legacy/recomp/out/debug_feasibility/named_lift_inventory/spu_named_inventory.{md,json}` and `named_jobmods_audit/{extract_manifest.json,jobmod_meta.json,raw/}`.
- Firmware and retail roles: `temp/legacy/recomp/spu/spu_elfs.tsv`, `images/`, `images_dbg/`, `dumps/`, `named_lifts/`.
- Captures: `temp/legacy/recomp/out/debug_feasibility/spu_staged_miss_*.bin`.
- Byte-derived fingerprints were recomputed with the FNV-1a-64 implementations the runtime uses.

The named debug EBOOT symbol table identifies embedded inputs. Derive guest EAs from the containing ELF PT_LOAD: guest EA = segment virtual address + file offset - segment file offset. For example, file offset 0x00FC5E00 lies in the segment at file 0x00EF0000 / guest 0x10060000 and maps to guest 0x10135E00.

## Stage classes

| Class | Stage | Public state |
|---|---|---|
| A | Embedded scan: `vendor/ps3recomp/tools/extract_spu_images.py` + `build_spu_workloads.py` via `python scripts/project.py generate --stage spu` | Committed; reproduces ids 1-2 from a user-supplied debug EBOOT |
| B | Embedded named extraction: symtab-driven C0DEC0DE job binaries, MP3 job objects and the jobmanager policy template | Private driver `temp/legacy/recomp/spu/spu_named_inventory.py`; port in [#36](https://github.com/robbe1912/motorstorm-mv-recomp/issues/36) |
| C | Firmware codecs: user-supplied `dev_flash/sys/external/*.pic`, module lift plus per-base lifts with `scripts/spu/lift_flash_codec_at_base.py` | Lift scripts committed; input acquisition and wiring undocumented, [#37](https://github.com/robbe1912/motorstorm-mv-recomp/issues/37) |
| D | Capture: probe-miss local-store dumps rebuilt and lifted with `scripts/spu/lift_ms1_debug_dsp.py` | Script committed; bytes exist only as private run captures, [#38](https://github.com/robbe1912/motorstorm-mv-recomp/issues/38) |

## Image matrix

Entries are absolute local-store addresses. For codec and DSP stage probes, add the lift base to the registered module-relative entry offset; unrelocated module entries have base zero. "Whole" is the FNV-1a-64 over the full image; "text" over the executable PT_LOAD; "staged" over the exact byte span the runtime fingerprints (job images: image minus the 0x20-byte trailer; DSP: staged PT_LOAD slice).

| Id | Image | Size (B) | Entry | Lift base | Identity (FNV-1a-64) | Byte source | Stage | Clean checkout |
|---|---|---|---|---|---|---|---|---|
| 1 | `spu_0000_at_00EDE500` (libmstreamSPURS) | 57200 | 0x3010 | 0 | whole 154AD8ECE9E6C238, text 5549EF2556F77C6A | debug EBOOT file [0x00EDE500, +57200), `_binary_libmstreamSPURS_spu_elf_start` | A | reproducible |
| 2 | `spu_0001_at_00F06000` (hkspursconstraint) | 124150 | 0x3010 | 0 | whole 6E32DC7CD6DED19D, text 8398CCB34C1644BF | debug EBOOT file [0x00F06000, +124150) | A | reproducible |
| 3 | `spu_0002_policy_10135e00` (jobmanager PM) | 11372 | 0x0A00 | 0 | whole DF936AC685721F53, text C042E76A9A90E5BF | EBOOT file [0x00FC5E00, +11120) template plus 16 zero bytes, `_binary_jobmanager_file_start`, guest EA 0x10135E00 | B | bytes derivable; wrap/lift private ([#36](https://github.com/robbe1912/motorstorm-mv-recomp/issues/36)) |
| 9 | `flashATRAC` | 35131 | 0x90 | 0 | whole 43E2420C4A0F57D5, text 4787E96D1AC1C41A | firmware `dev_flash/sys/external/flashATRAC.pic` | C | needs firmware input ([#37](https://github.com/robbe1912/motorstorm-mv-recomp/issues/37)) |
| 10 | `flashMP3` | 69695 | 0x74A0 | 0 | whole C3EDFB0022BEBEF5, text DC18E4EBD06A8047 | firmware `dev_flash/sys/external/flashMP3.pic` | C | needs firmware input ([#37](https://github.com/robbe1912/motorstorm-mv-recomp/issues/37)) |
| 11 | `flashATRAC_b32880` | 35131 | 0x32910 | 0x32880 | text 4787E96D1AC1C41A (probe) | same bytes as id 9 | C | needs firmware input |
| 12 | `flashATRAC_b33880` | 35131 | 0x33910 | 0x33880 | text 4787E96D1AC1C41A (probe) | same bytes as id 9 | C | needs firmware input |
| 13 | `flashATRAC_b2F780` | 35131 | 0x2F810 | 0x2F780 | text 4787E96D1AC1C41A (probe) | same bytes as id 9 | C | needs firmware input |
| 14 | `mstream_dsp_dbg_compressor` | 3328 (PT_LOAD) | 0x90 | 0 | whole 587D22C114B9C1C0 (rebuilt .pic), staged 3F57764801E41780 | capture `spu_staged_miss_2F010.bin`, LS window [0x2EC10, 0x37010) | D | capture-only ([#38](https://github.com/robbe1912/motorstorm-mv-recomp/issues/38)) |
| 15 | `mstream_dsp_dbg_reverb` | 8576 (PT_LOAD) | 0xA0 | 0 | whole D8649C39710A04DE (rebuilt .pic), staged 9D123B5450D8248F | same capture window | D | capture-only ([#38](https://github.com/robbe1912/motorstorm-mv-recomp/issues/38)) |
| 20 | `mstream_dsp_dbg_compressor_b2EF80` | 3328 | 0x2F430 primary | 0x2EF80 | staged 3F57764801E41780 (probes at module +0x4B0/+0x888/+0x90/+0x3C0) | same bytes as id 14 | D | capture-only |
| 21 | `mstream_dsp_dbg_reverb_b2FD00` | 8576 | 0x2FDA0 | 0x2FD00 | staged 9D123B5450D8248F (probe) | same bytes as id 15 | D | capture-only |
| 210 | `jobmod_056ac0eea1a6_e12270` (spupvs) | 75360 | 0x16270 | 0x4000 | staged 1D912920D52B9FE0; 958 funcs | EBOOT file [0x00F76F80, +75360) | B | bytes derivable; extractor private ([#36](https://github.com/robbe1912/motorstorm-mv-recomp/issues/36)) |
| 211 | `jobmod_0c12886b2f86_e2100` (spuconstraints) | 9008 | 0x6100 | 0x4000 | staged B103D0BED870FD18; 143 funcs | EBOOT file [0x00F4EB00, +9008) | B | bytes derivable; extractor private |
| 212 | `jobmod_16b664ad80c1_e7850` (spuvertexbuffer) | 31376 | 0xB850 | 0x4000 | staged BCAE4F4D8FE977EE; 315 funcs | EBOOT file [0x00F6F500, +31376) | B | bytes derivable; extractor private |
| 213 | `jobmod_556b30b5e654_e12e20` (spuparticlesystem) | 79088 | 0x16E20 | 0x4000 | staged 3547CC163D6E1A54; 801 funcs | EBOOT file [0x00F5C000, +79088) | B | bytes derivable; extractor private |
| 214 | `jobmod_9b7dc8fddc7c_e1540` (spuxform) | 5936 | 0x5540 | 0x4000 | staged AB8F5CD64EEA2166; 82 funcs | EBOOT file [0x00F89600, +5936) | B | bytes derivable; extractor private |
| 215 | `jobmod_b4196ba13cc2_eaf80` (spugroundrush) | 45360 | 0xEF80 | 0x4000 | staged 35986289503E9DF5; 522 funcs | EBOOT file [0x00F50E80, +45360) | B | bytes derivable; extractor private |
| 216 | `jobmod_0b04db5f915b_e6230` (spucodec_sase) | 122288 | 0xA230 | 0x4000 | staged FAA4A92841B958F4; 1614 funcs, 241 data-in-text words | EBOOT file [0x00FA8000, +122288) | B | bytes derivable; extractor private |
| 217 | `jobmod_218cf6782924_ea9b0` (bytes of mp3SurroundJobCode) | 60112 | 0xE9B0 | 0x4000 | staged 270672D46A0816D3; 792 funcs, 105 data-in-text words | EBOOT file [0x00F3CF80, +60112), `mp3SurroundJobCode` STT_OBJECT | B | bytes derivable; extractor private |
| 218 | `jobmod_3dfb7150a008_e12928` (bytes of mp3StereoJobCode) | 96688 | 0x16928 | 0x4000 | staged 9CF193289333F04F; 1095 funcs, 52 data-in-text words | EBOOT file [0x00F25500, +96688), `mp3StereoJobCode` STT_OBJECT | B | bytes derivable; extractor private |
| 219 | `jobmod_8de1770ee613_e1cd40` (spuvehicle) | 119440 | 0x20D40 | 0x4000 | staged 4F93B96EBF624615; 995 funcs | EBOOT file [0x00F8AD80, +119440) | B | bytes derivable; extractor private |
| 220 | `nli_mp3StereoJobCode` (named lift of id 218 bytes) | 96688 | 0x16928 | 0x4000 | staged 9CF193289333F04F | same bytes as id 218 | B | registration disabled (A/B 2026-10-09 wedge test); extractor private |
| 221 | `nli_mp3SurroundJobCode` (named lift of id 217 bytes) | 60112 | 0xE9B0 | 0x4000 | staged 270672D46A0816D3 | same bytes as id 217 | B | registration disabled; extractor private |

Notes on the matrix:

- Codec per-base lifts use `--code-end 0x7DC0` (flashATRAC) and restore extern stubs from the module lift; flashMP3 has no observed base yet and exists only as the module lift plus interpreter fallback.
- The two DSP modules carry a GCC 4.0.2 (CELL 4.1.11) vintage. Retail EBOOT DSP twins are GCC 4.1.1 with different bytes and are not interchangeable.
- Jobmods stage at link base 0x4000 through the policy-module path; the runtime identifies them by the FNV-1a-64 of the staged span (image minus 0x20-byte trailer).
- The PM registered as id 3 equals the embedded jobmanager template plus a 16-byte zero tail. A second private PM capture (`temp/legacy/recomp/spu/dumps/`, identity 46EAABFB56B7B1B5, 11136 B) differs from the template in most bytes and belongs to an older investigation; the current tree does not register it.

## Deduplication

The 24 inventoried variants carry 17 unique byte streams (22 variants are enabled): two embedded SPU ELFs, one PM template, two firmware codecs, two captured DSP modules and ten job binaries. Duplicate registrations by design: 9=11=12=13, 14=20, 15=21, 217=221, 218=220.

## Missing images

Four debug-vintage DSP modules were not recovered in the audited private inputs: mstream_dsp distortion, eq, filter and IR. Interpreter fallback is available; this inventory does not prove their execution. They gain images only through the capture stage in [#38](https://github.com/robbe1912/motorstorm-mv-recomp/issues/38).

## What a clean checkout reproduces

With a user-supplied debug EBOOT, the public stage rebuilds ids 1 and 2 only. Ids 3 and 210-221 need the named extraction stage ([#36](https://github.com/robbe1912/motorstorm-mv-recomp/issues/36)). Ids 9-13 need firmware files and wiring ([#37](https://github.com/robbe1912/motorstorm-mv-recomp/issues/37)). Ids 14/15/20/21 need private captures ([#38](https://github.com/robbe1912/motorstorm-mv-recomp/issues/38)). The current registration file also mixes generated output with hand-appended blocks, so regeneration alone would not reproduce it even where inputs exist.
