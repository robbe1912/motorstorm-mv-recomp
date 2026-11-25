# Setup and build

Developer tooling, not a ready-to-play distribution. The SPU stage recreates the embedded images 1-3 and job modules 210-219 from the named debug EBOOT, but **not** all 24 private images currently used. Firmware codecs and captured DSP modules need separate inputs/stages. An automated clean-clone boot has not been verified.

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

PPU: loader/import metadata, named executable .symtab bounds, preserved lifter with HLE imports and C++ nonlocal jumps. Stripped retail needs independently validated function metadata. SPU: embedded ELF extraction, symtab-named job/policy extraction (`scripts/spu/extract_ms1_named.py`, identity-checked against `scripts/spu/jobmod_meta.json`), build_spu_workloads and the job-module lift. Review unsupported-instruction diagnostics and registration; firmware codecs (9-13) and DSP captures (14, 15, 20, 21) remain outside this stage.

The named extractor requires `--out` to be absent or completely empty. Its
`--images` directory may contain the class-A ELFs, but an existing policy ELF
is preserved by refusing extraction. All named inputs are validated before
publication; a write failure removes only files and directories created by
that invocation. Move previous outputs aside before regenerating.

Additional scripts accept explicit inputs/outputs; inspect `--help`:

- `scripts/spu/lift_ms1_jobmods.py`: original job-module extraction/lifting; retain unique IDs and staged span identity.
- `scripts/spu/lift_coverage.py report --tree TREE --jobmods DIR --check` checks static branch targets in the ten debug-US job modules. Use `diff OLD NEW --check` to detect changed or removed function bodies. A coverage pass is not a replay result. Keep the selected tree until the replacement passes replay.
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


The selected debug-US build binds native hierarchy work and cooperative job waits by default. Its original ELF and reference functions must match the verified contracts; the build copies generated inputs locally and changes only the copied binding TUs. See [native binding and reference mode](NATIVE_GAME.md#build-and-scene-bridge). Use `--no-native-world-transforms --no-native-job-wait --no-native-visibility` for an unbound reference build. Other targets require their own verified bindings.

The visibility prototype is opt-in: `--native-visibility` binds its verified SPU module, while runtime `MS_NATIVE_VISIBILITY=0` remains the default reference mode. `shadow` compares current operations and `1` selects native work; checked normal-PLAY shadow and native invocation are validated, with remaining performance limits in [Native game operations](NATIVE_GAME.md). Stable 30 FPS is unachieved. Direct CMake uses `PORT_NATIVE_VISIBILITY=ON`. Keep `--no-native-visibility` for a fully unbound reference build.

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

Renderer evaluation can additionally use `--optimize-renderer` with `--optimize`.
This defaults off and selects O2 (plus automatic `/Ob2` inlining on clang-cl)
only for eight native video/FIFO translation units. Guest PPU/SPU compilation,
assertions, Debug CRT, strict arithmetic and GPU retirement checks retain their
existing settings. `renderer_optimization` in build identity records the selected
source list, and the helper hash is retained. This is an experimental build
comparison under issue #296; compilation alone proves no frame-rate improvement.

Guest evaluation can additionally use `--optimize-guest` with `--optimize`.
This defaults off. It gives O2 (plus automatic `/Ob2` inlining on clang-cl) to
the lifted PPU translation units only; the runtime keeps checked O1. The flags
are in `src/guest_optimization.cmake`; `scripts/check_guest_optimization.py`
configures a fixture with the actual flags and rejects eight mutants. Build
identity records `guest_optimization`. Measured on the diagnostic race run
`20261124T010716.205010Z` against `20261124T002840.355595Z` (same switches,
O1 and O2 guest units): median frame interval 184.7 ms against 241.8 ms; main
thread CPU 30.0 ms per frame against 43.4 ms. The memory helpers of
`ppu_fastmem.h` stay out of line in the largest guest functions at both levels.
With `--ppu-fastmem3 0`, the read accessors stay out of line in that way.

The PPU fast memory step is on by default: `python scripts/project.py build
--ppu-fastmem3 0` builds the path before that step, for a comparison build.
The switch sets `PORT_PPU_FM3` and the compile definition `PPU_FM3=1` or
`PPU_FM3=0` for each unit. Value 1 removes the label address from the read
accessors of `ppu_fastmem.h`, so Clang inlines them, and the gate gives the
alias answer of a page of the alias window inline. Build identity records
`ppu_fastmem3`, and the launch record of `scripts/run.py` holds that value.
`python scripts/check_ppu_fastmem3.py` builds both paths and rejects 29
mutants. See [PPU fast memory step 3](NATIVE_GAME.md#ppu-fast-memory-step-3-alias-window-and-gate).

The Havok worker count switch is opt-in: `python scripts/project.py build
--havok-threads`. This defaults off. It sets `PORT_HAVOK_THREADS=ON` only for
the verified production ELF. The build binds the lifted
`hkMultithreadingUtil::initMultithreading` (`0xA01220`) to
`src/motorstorm/havok_threads.cpp` through the existing native binding. Build
identity records the flag `havok_threads` and the binding manifest. The build
does not change the worker count. The count changes only when the launcher sets
`MS_HAVOK_THREADS`; see [Havok worker threads](OPERATIONS.md#havok-worker-threads).
`python scripts/check_havok_threads.py` checks the registration, the hook and
the identity of the lifted body.

`--optimize-runtime` (with `--optimize`; CMake `PORT_OPTIMIZE_RUNTIME`, default off)
applies O2, plus `/Ob2` on clang-cl, to the whole `ps3recomp_runtime` library:
renderer, GCM/FIFO, SPU runtime and HLE. The toolkit asks for `-O2` in non-Debug
builds only, and under clang-cl the forwarded `/clang:-O1` wins over it, so the
level is appended last; a Debug build has no toolkit level to lose. Guest PPU/SPU
compilation, assertions, aliasing and floating-point contraction settings are
unchanged. `runtime_optimization` in build identity records the mode, and the
helper hash is retained. `check_runtime_optimization.py` checks the scope in
Debug and RelWithDebInfo. It compiles only authored targets. It does not call
the game build wrapper. Measured result: none. No run yet.

The renderer option's first native evaluation changed exactly eight object commands, leaving 207
others unchanged. With matching executable/PDB identity, normal gated PLAY
reached original menu/bike assets and a race. Its unsuspended diagnostic window
still ended at about 3.81 successful API Presents/s; no controlled game gain was
established and the option remains off by default. Assertions, Debug CRT and
strict arithmetic stayed enabled. The actual O2 backend passed GPU readback,
descriptor, blocked-fence and historical negative controls on an RTX 3080 with
zero validation messages. Native graphics defects and the 30 FPS goal remain
unresolved; matched alternating trials are required before promoting a speedup.

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

## VP upload capacity regression

`python scripts/check_rsx_vp_upload.py` compiles the six actual VP upload
functions, the shared two-parity growth helper and the actual retirement gate
against authored vertex/storage/fence adapters. It checks 128 complete uploads
over 16 schedules, preserving earlier bytes in both halves across repeated
growth. It also covers allocation/retirement rollback and arithmetic limits,
and requires independently broken parity-copy and unchecked-retirement controls
to fail. `--baseline 614798b9f2348e08e9e54c95fb1b4c111409fe2f` must reproduce
the original strip returning zero where six vertices are required; that revision
must exist locally. The ordinary command requires no historical Git objects.

Windows uses the normal clang-cl setup. For a GNU-style compiler, including
MinGW on Windows, set `CC=clang` or use `--cc clang`. On Linux, the default is
`CC` or `cc`. Python 3.10+ and a C11 compiler suffice; no game inputs, native
game executable or GPU are used. Source/executable hashes and full logs stay
under `temp/checks/vp-upload-*`. The Windows/Linux source workflow runs the
ordinary command, but wiring a job is not a hosted test result.

The existing `check_rsx_restart.py` and `check_rsx_indexed_strip.py` also accept
GNU-style `CC` on Windows. Their original restart, decoded-attribute, winding,
split-packet and cache-work checks remain; the indexed boundary check now
requires the full draw and preserved prior bytes after growth. These tests do
not prove GPU resource lifetime or presentation; see the qualified
[vendor adoption](VENDOR.md#vp-upload-capacity-adoption-issue-129).

## SPU lane trace

The SPU runtime prints its lane diagnostic lines only when the environment
variable `SPU_LANE_TRACE` is set, is not empty and is not `0`. The default
run prints no line of the nine gated kinds. Set `SPU_LANE_TRACE=1` for a
diagnosis run. Error lines and halt lines do not change. The kinds and the
commits are in [vendor provenance](VENDOR.md#spu-lane-print-gate-step-0).
`python scripts/check_spu_lane_trace.py` runs the check.

Measured result: none. No run yet.

## SPU SIMD helper forms and SSSE3

The build compiles the lifted SPU units with SSSE3 enabled:
`/clang:-mssse3` with clang-cl, `-mssse3` with a GNU-style compiler.
SSSE3 is a host requirement from now on. The forms make no CPUID test.
The option `PORT_SPU_SIMD` (ON) defines `SPU_SIMD=1`. With it, `rotqby`,
`rotqbyi`, `shufb`, `cwd`, `cwx`, `fm` and the local store quadword swap use
x86 SIMD forms. Each form is bit-exact to its scalar body. The commits are
in [vendor provenance](VENDOR.md#spu-simd-helper-forms).

Build with `--no-spu-simd` for a comparison build with the scalar bodies:

    python scripts/project.py build --no-spu-simd

The switch sets `PORT_SPU_SIMD` to `OFF` and the compile definition
`SPU_SIMD=0` for each unit. The build identity holds `spu_simd` `0` or `1`.
Without SSSE3 in a unit, only the SSE2 forms (`cwd`, `cwx`, `fm`) are
active, and `shufb` keeps its checked dispatch.

`python scripts/quiet_run.py --timeout 900 -- python scripts/check_spu_simd.py`
runs the oracle of the forms. It needs no game input.

Measured result: none. No run yet.
