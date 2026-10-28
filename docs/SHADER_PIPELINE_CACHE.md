# Checked shader disk cache

Race-start compilation can hold the renderer long enough for a guest GPU wait
to expire. This cache reuses successful FXC output without changing source,
compile flags, draw order or pipeline-state identity.

RSX_SHADER_DISK_CACHE=0 disables disk reuse. With no override the cache uses
LocalAppData/ps3recomp/shader-cache-v2; an explicit local directory selects another
cache. This preserves the validated R48 default. Failure to initialize or write
is a miss, and the first attempted store failure reports its path, stage and
Win32 error once. Explicit disablement stays quiet.

Version 2 keys include the exact source, source name, entry, target, both flags
and SHA256 of the DLL containing the loaded D3DCompile export. The executable's
import thunk is rejected. Every read checks the complete key, file lengths,
DXBC bounds and payload SHA256. Missing, damaged, stale or incompatible entries
fall back to original compilation. Stores use unique temporary files and a
same-directory replacement; reader/removal/replacement operations share a lock.
Directory recreation preserves the reparse-point refusal. There is currently
no total directory quota; per-entry limits are 1 MiB source and 16 MiB bytecode.

The renderer coordinator owns disk access, bytecode caches and PSO creation.
A PSO rejection involving disk-origin bytecode invalidates those entries,
compiles the affected original sources and retries once. Device loss and
out-of-memory do not trigger that retry. A disk-loaded VS retains its original
HLSL within a 32 MiB budget; when that source cannot be retained, the disk blob
is refused and compilation proceeds normally.

Run the authored Windows checks with Python and a configured Windows compiler:
python tests/check_shader_pipeline.py --cc clang-cl in the runtime, or
python scripts/check_shader_pipeline.py --cc clang-cl in the curated game.
They cover exact keys, compiler changes, corrupt entries, concurrent replacement,
a 65 MiB authored executable and a distinct executable sharing one compiler,
once-only failure logs, quiet disablement, actual coordinator provenance and
PSO recovery, and deliberately broken import-thunk/integrity/recovery controls.
The complete backend translation unit is checked. No game inputs are required.
The runtime exposes this through its Windows CTest suite as well.

These tests establish storage/recovery behavior, not a native game deadline or
minimum FPS. The prior R48 owner runs motivate this port; the new public source
candidate still requires owner acceptance. Readable-span caching and unrelated
renderer fixes are outside this change.

## Compile-only workers and prefetch

RSX_FXC_THREADS defaults to min(8, logical processors minus one), matching R48.
One logical processor uses synchronous compilation. The valid override is
0..16; 0 disables the pool. Compile flags remain 0/0. This default reduces cold
race-start serialization while retaining an explicit synchronous fallback.

Workers receive complete deep-copied compiler inputs, and return only compiler
blobs. They do not read guest memory, modify renderer/disk caches or call D3D12
device functions. The pool bounds itself to 192 jobs, 16 MiB source and 32 MiB
completed blobs. Exact source/name/entry/target/flags comparisons resolve hash
collisions. Failed compilation or capacity refusal uses the synchronous path.
The renderer claims results and creates PSOs in the original draw order.

The existing view-resolution walk queues compile-only work. A second owner
walk creates any missing PSOs after the views are resolved and before command
replay. Speculative mode is scoped to one owner helper call, so an early frame
exit cannot leave it enabled. Prefetch cannot insert a failed/negative PSO or
create a PSO. It can warm successful bytecode. A 4096-slot/16 MiB exact-key table
bounds duplicate suppression; full/oversized keys never suppress work.

The combined fork still emits literal fragment constants, so its prefetch
identity includes the original program payloads. This curated game uses buffered
constants: canonical instruction bytes preserve inline-constant positions but
zero those payloads, and exact rewrite state (including alias masks/remaps,
dimensions and shader controls) completes the key. The existing 4096-byte
program admission limit and both decompiler ABIs are unchanged. Shader extent
and other renderer corrections require separate changes.

Shutdown stops new work and joins workers/claimants. A timed-out join retains
pool storage and immutable keys for any still-running callback; no device or
renderer state is passed to workers. Backend teardown may safely retain this
compile-only storage until process exit. No compiler deadline is guaranteed.

The standalone checks add real Windows worker ordering, lease/reclamation and
shutdown tests; actual coordinator callbacks with real FXC and an authored
owner/device spy; pool-disabled fallback; exact-prefetch collision/overflow
controls; and a wrong-owner negative control. The spy checks the actual owner
helper, while source checks bound the production worker callbacks and place the
prefetch exit before PSO creation. This is not a WARP/native race acceptance run.

The compile-only preparation pass and explicit owner-resolution walk run
independently of the optional legacy duplicate-lookup setting. In the curated
game, RSX_PSO_SINGLE_LOOKUP still defaults to 1; with the pool disabled it
continues to select replay-only lookup (0 retains the old extra prepass).
It cannot suppress required pool work. The integration fixture executes the
actual preparation/draw functions with the production default lookup and
worker settings, real FXC and an authored device spy. Restoring the former
consumer gate must fail the queued-work assertion. Disk storage is disabled
in that cold-source fixture to make a compile miss deterministic.
