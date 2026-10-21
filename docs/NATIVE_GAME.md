# Native game operations

[Issue 177](https://github.com/robbe1912/motorstorm-mv-recomp/issues/177) owns native scene-hierarchy integration. [Issue 27](https://github.com/robbe1912/motorstorm-mv-recomp/issues/27) owns sustained 30 FPS acceptance. The public kernel is implemented; its game adapter and build binding are still in progress.

## World transforms

[`world_transforms.h`](../src/motorstorm/world_transforms.h) defines caller-owned host matrices, parent indices, root indices and dirty flags. [`world_transforms.cpp`](../src/motorstorm/world_transforms.cpp) evaluates the operation directly on x86, without guest registers, local-store access or instruction dispatch. Parents precede children. A root's translation is restored after the relative hierarchy composition. CPU-only translation scratch is outside this interface.

Compile this operation separately with AVX2/FMA and strict floating-point behavior. Its paired fused products use toward-zero rounding and flush subnormal results. The complete caller MXCSR is restored on normal and exceptional exits. Parent/root ownership, non-finite inputs and arithmetic range violations throw. Callers must use pending host outputs and discard them on failure; the kernel does not provide a transaction over caller buffers. A production adapter must check host instruction support before entering this compiled operation.

Run `python scripts/check_native_world_transforms.py` on an x86-64 AVX2/FMA host with a C++ compiler. Windows accepts `MV_CLANG`; other hosts accept `CXX`. The authored fixture checks independent rounding, fusion, rotation, translation, roots, dirty flags, rejected inputs and caller FP state. A deliberately wrong-rounding implementation must fail the independent product oracle. Build products remain under ignored `build/self-tests/`.

## Runtime evidence and remaining coverage

The private original-work shadow run `20261021T155524.955563Z` compared 3,744 hierarchy snapshots / 18,896 nodes from 936 objects. World bits, roots, scratch, flags, inputs and layouts matched exactly, without tolerances. It covered 900 dirty snapshots and no topology-dirty snapshots. The public kernel independently replayed the same inputs against original job outputs with zero differences.

An opt-in private adapter then ran the public kernel through normal PLAY in native DX12 run `20261021T162204.182417Z`, executable SHA256 `f2291c150bc49e73d9177677995805db8efed5ba406ca9a37c3bdb9b47aba26b`. Original menu assets and the racing HUD were internally observed. The last cumulative checkpoint recorded 20,224 native operations and 2,699,314 nodes, with 16 visible numeric-range fallbacks to unchanged original work. This does not establish topology-dirty gameplay parity or complete interpreter removal. The adapter computes and validates pending outputs before guest writes; it does not change job markers or the game's implementation flag.

This diagnostic is not a controlled speed comparison. Its late Present API interval median was 553.151 ms; that is not displayed or simulation FPS. Stable 30 FPS remains unachieved. Raw inputs, outputs, captures, original code and provenance manifests stay private outside disposable run retention. The next integration must retain the original path for uncovered inputs, preserve observable diagnostics, and identify the remaining critical wait using matched native symbols.
