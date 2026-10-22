# Setup and build

Developer tooling, not a ready-to-play distribution. The initial embedded SPU stage does **not** recreate all 24 private images currently used. Extra firmware codecs, runtime-built PM and captured DSP modules need separate inputs/stages. An automated clean-clone boot has not been verified.

## Target and native architecture

The current diagnostic target is named-US debug `EBOOT_MSMVdbgUS.ELF` with authentic launch-US BCUS98137 PS3_GAME data (VERSION 01.00/FW 1.80). ELF SHA256: `3e68c72f8fbd6a30ef30d4535462cf70f1cc86d111f56574adb7dd2c255e0706`. BCES00006 Complete APP_VER 03.10 is a separate revision; do not mix generated trees or assume address/data compatibility. External original inputs remain at their configured paths and need not be duplicated.

The port is moving toward native x86 game operations, with translated code and interpretation retained for unreplaced work. [Native game operations](NATIVE_GAME.md) documents the hierarchy rewrite and its verified binding. Compatible host services include real host media decoding. Original binary patches, title-specific toolkit bypasses, fabricated assets or suppressed errors do not establish acceptance. The current fatal/resource evidence belongs to [Havok/reference](research/HAVOK_REFERENCE.md); pending work belongs in [GitHub issues](https://github.com/robbe1912/motorstorm-mv-recomp/issues).

## Dependencies

Windows x64; Visual Studio 2022 Build Tools Desktop C++/Windows SDK; LLVM/clang-cl, Ninja and CMake 3.20 or newer on PATH; Python 3.10+ and `python -m pip install -r requirements.txt`. The wrapper imports vcvars64 through vswhere. Supply an LGPL **shared** FFmpeg development distribution with matching `include/`, import libraries in `lib/`, DLLs in `bin/` (avcodec, avutil, swscale). D3D12/DXGI/D3DCompiler/DXGUID and Windows audio libraries are linked.

RPCS3 and Ghidra are optional research/reference dependencies, not the native runner. The asset-name audit requires an explicitly supplied RA/LZH reader; it is not bundled.

## Private inputs

Supply your own decrypted executable, matching PS3_GAME, firmware and keys where applicable. No acquisition service/payload is included. External paths work; originals need not be copied.

| Ignored location | Contents |
|---|---|
| `game/elf/`, `game/disc/` | Optional local original inputs |
| `game/private_keys/` | Private C headers and Python key JSON |
| `game/userdata/` | Isolated writable native HDD/save tree |
| `build/generated/named/ppu/`, `spu/` | Generated translations/registrations |
| `build/metadata/`, `build/spu-inputs/` | Loader data/extracted inputs |
| `build/native/`, `build/preserved/` | Current and preserved EXE/PDB |
| `temp/deps/`, `temp/runs/`, `temp/builds/` | Dependencies, captures and diagnostics |
| `temp/legacy/` | Local migrated history, tools and fixtures |

Also ignored: `config/local.json`. Generated registry source stays private even when named differently from spu_recomp.c.

## Private key interface

C builds require two user-supplied headers in `game/private_keys/` or `--keys-dir`:

- `ps3_sdata_keys.h`: guarded definitions of `static const uint8_t SDAT_KEY[16]` and `EDAT_KEY_0[16]`.
- `ps3_edat_keys.h`: guarded `static const uint8_t` definitions of `EDAT_KEY_0[16]`, `EDAT_KEY_1[16]`, `SDAT_KEY[16]`, `NP_OMAC_KEY_2[16]`, `NP_OMAC_KEY_3[16]`; `static const uint8_t KLIC_CANDIDATES[][16]` with your own supported candidates; `static const size_t NUM_KLIC_CANDIDATES = sizeof(KLIC_CANDIDATES) / sizeof(KLIC_CANDIDATES[0])`.

Provide actual private bytes; no placeholder keys are distributed. Missing headers intentionally fail configure. Content may also require its own EDAT license key via the original interface.

Python extraction reads `PS3_KEYS_FILE`: an absolute path to private JSON with `SDAT_KEY`, `EDAT_KEY_0`, `PS3_GPKG_KEY`, `PSP_PKG_KEY`, each holding your own 32 hexadecimal characters (16 bytes). Set `$env:PS3_KEYS_FILE` before invoking vendor tools. Missing/invalid keys fail explicitly. Captured instruction fixtures are not needed to compile.

## Configure

From the repository root, replacing these example paths with your own:

```powershell
python scripts/project.py setup --elf 'D:/YourDump/EBOOT_MSMVdbgUS.ELF' --disc 'D:/YourDump/PS3_GAME' --ffmpeg 'temp/deps/ffmpeg' --keys-dir 'game/private_keys'
```

This validates ELF/disc/FFmpeg presence and writes local.json. The public example describes the schema. Presence is not executable/disc compatibility; verify identities.

Install the local staged-source protection once: `python scripts/install_hooks.py`. Before committing, run `python scripts/check_repository.py` and `python scripts/check_docs.py`; see [repository audit](REPOSITORY.md).

## Generate

Generation refuses overwriting existing trees. Preserve a baseline and select a fresh ignored tree in local config for regeneration.

```powershell
python scripts/project.py generate --stage ppu
python scripts/project.py generate --stage spu
```

PPU: loader/import metadata, named executable .symtab bounds, preserved lifter with HLE imports and C++ nonlocal jumps. Stripped retail needs independently validated function metadata. SPU: embedded ELF extraction and build_spu_workloads. Review unsupported-instruction diagnostics and registration; this is only the initial set.

Additional scripts accept explicit inputs/outputs; inspect `--help`:

- `scripts/spu/lift_ms1_jobmods.py`: original job-module extraction/lifting; retain unique IDs and staged span identity.
- `scripts/spu/lift_flash_codec_at_base.py --elf INPUT --base BASE --prefix NAME --code-end END --out OUTPUT`: observed link-base codec lift, fixed-low-LS extern restoration; `--module-lift` is the separate module-relative form.
- `scripts/spu/lift_ms1_debug_dsp.py --dump INPUT --trees OUTPUT_TREE[,OUTPUT_TREE]`: capture-based reconstruction; trees need existing target-specific workload files. Observed bases/content provenance remain necessary.
- `scripts/analysis/debug_elf_functions.py ELF --out OUTPUT`: executable function bounds, rejects empty/overlapping spans.
- `scripts/analysis/audit_ms1_asset_names.py`: requires `--ra-tool`, `--index`, `--elf`; optional `--dat`, `--cnk`, `--extract`, `--out-dir` for explicit read-only extraction.

Guest inputs/output belong in ignored folders. Debug and retail modules are not interchangeable. Firmware/PM/DSP extraction is not yet one automated pipeline: the archived private recipes and [translation evidence](research/TRANSLATION.md) provide context, not a clean-clone completeness claim.

## Build

For an additional checkout, follow [private worktree setup](WORKTREES.md) before building. Required ignored inputs are not copied by Git.

```powershell
python scripts/project.py build
```

The wrapper kills ms1_recomp.exe before relinking, configures root CMake into build/native, uses clang-cl and at most eight jobs. Full warnings/errors go to unique temp/builds/TIMESTAMP/configure.log and build.log. Failure prints a bounded tail and full log path; no warning suppression added. Success records EXE/ELF hashes/tree paths/log directory in build_identity.json.

It also records selected runtime capabilities, the capability-source SHA256 and
the toolkit checkout's revision/dirty status when available. The default remains
the curated `vendor/ps3recomp`; `build --ps3recomp-dir PATH` explicitly selects
another source root through the existing CMake `PS3RECOMP_DIR` interface. This
does not make arbitrary runtime/generated-tree combinations compatible. A change
to the recorded capability source or revision during compilation rejects the
new identity. Launching requires a matching recorded build; see
[runtime profile admission](OPERATIONS.md#runtime-profile-admission-issue-149).

The selected debug-US build binds native hierarchy work and cooperative job waits by default. Its original ELF and reference functions must match the verified contracts; the build copies generated inputs locally and changes only the copied binding TUs. See [native binding and reference mode](NATIVE_GAME.md#build-and-scene-bridge). Use both `--no-native-world-transforms --no-native-job-wait` for an unbound reference build. Other targets require their own verified bindings.

Public vendor tests exclude unreviewed guest fixtures. PS3RECOMP_BUILD_TESTS=ON fails clearly; review upstream synthetic tests separately. Build success establishes compilation, not native gameplay. Use [operations](OPERATIONS.md) for live work.

For performance evaluation, `python scripts/project.py build --optimize` enables
`PORT_OPTIMIZE_NATIVE`: native O1 for the PPU/application and shared runtime,
with Debug symbols and assertions retained. Explicit aliasing and floating-point
contraction flags preserve guest numeric behavior; generated SPU units keep O2.
On Windows this mode requires the configured clang-cl toolchain. The ordinary
build command explicitly disables the option again. Inspect actual compiler
commands rather than inferring optimization from the CMake cache: checked mode
removes `/Od` and `/Ob0` in directory scope while retaining cached defaults.
Build identity records `optimized_checked`. A configured or compiled optimized
binary is not evidence of a speedup, correct graphics or an achieved FPS target.

`python scripts/check_spurs_guest_fields.py` compiles the complete affected
SPURS API definitions and the real BE taskset builder against an authored
guest-header fixture. Dispatch is stubbed; no game or SPU execution occurs.
It checks CreateTask, DestroyTaskset and ShutdownTaskset writes, neighboring
bits, guards, returned slot and null-pointer errors. `--baseline REV
--expect-failure` checks the three original-store failures from a Git revision.
Each run preserves source and binary hashes plus build/run logs under
`temp/checks`. Both CI platforms run the corrected contract.

`python scripts/check_task_dispatch_identity.py` compiles complete actual async
dispatch APIs with an authored fingerprint adapter that publishes another
caller's identity before capture. It checks 256 owner-preserving dispatches,
unowned generic work, copied arguments, invalid slots, registry misses and
spawn refusal. Thread creation, phantom registration and diagnostic timing
are adapters; no guest code or real host threads execute. Raw source, fixture
and executable hashes and build/run logs remain under `temp/checks`. This
checks dispatcher ownership, without proving task recycling or race entry.
`--baseline f8d6a35 --expect-failure` reproduces both old ownership failures.

The authored lifecycle regression, `python scripts/check_task_lifecycle.py`, links
actual lifecycle code for 512 recycled and 1024 concurrent lifetimes, neighbor
bits, stale/duplicate ownership, dispatch cancellation and generation-based LS
reset. Its second fixture uses the actual inline runner to distinguish EXIT,
ordinary return and generic STOP, checking fresh context and no-entry handling.
`python scripts/check_task_exit_source.py` extracts the complete actual cleanup
API. Baseline `--baseline fc0322b --expect-failure` reproduces retained ENABLED
and stale-cleanup damage; corrected source passes. Fixtures use empty authored
VM/header data and host adapters, with no original instructions. Logs and
source/fixture/executable hashes are retained under `temp/checks`; source-only
lifetimes do not establish executed game work or native race entry.

The authored scalar-u64 policy-entry regression,
`python scripts/check_spurs_policy_arguments.py`, compiles the actual four r4
stores with authored register/context adapters. Five zero/low/high/mixed/all-ones
cases check the preferred high32/low32 pair. Production also clears the trailing
words; that clearing is not an assertion in this fixture. Old packing fails
three preferred-pair cases. This checks entry representation, not guest execution
or native menu/race acceptance; hashes and logs remain private.


`python scripts/check_spu_iret_progress.py` compiles the actual interpreter and
`scripts/fixtures/spu_iret_progress.c`, an authored CPU program that increments
a register and IRETs to one continuation seven times before its own STOP. The
old curated idle classifier halts after five increments; the corrected runtime
reaches eight and STOP. Unused channel/lift/recovery hooks trap. This tests
productive returns, not native assets/race acceptance; source/executable hashes
and full build/run logs remain in ignored `temp/checks/iret-progress-*`.

On Windows, `python scripts/check_rsx_texture_alias.py` uses actual production
packed-XY16F shader adaptation and authored texels for D3D float readback.
Unpatched sampling must fail; WARP must pass. `--device hardware` explicitly
selects hardware without fallback. The fixture covers signed half pairs,
decoding before filtering, clamp/wrap, remapping, named units and LOD/bias;
it also rejects insufficient source capacity and cube overlap. Logs and hashes
remain in ignored `temp/checks/rsx-alias-*`. This is a sampling-contract test,
not native race or performance acceptance.
