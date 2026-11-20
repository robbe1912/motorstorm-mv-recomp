# SPU single-precision values

This selective sync ports Robin Fröhlich’s `057c56c` runtime correction and
`daeb1575` scoped SIMD follow-up. Exponent255 is finite in SPU single precision;
host IEEE NaN/infinity behavior is incorrect. Exact integer significands
preserve truncation, flush and saturation for FA/FS/FM/FMA/FMS/FNMS/FI.
FPSCR exception accumulation remains separate and unchanged.

SIMD admits safe ordinary vectors and falls back for exceptional ranges.
Enter/leave scopes nest per thread and leave restores the caller's MXCSR
exactly. Inside a scope the MXCSR is held in SPU mode (truncation, FTZ, DAZ,
all exceptions masked), so SIMD add/multiply/FMA run without a per-operation
MXCSR switch. Each operation still checks the MXCSR and switches around itself
when SPU mode is not present (for example after a longjmp to a point saved
outside the scope). Helpers that compute with ordinary host arithmetic
(single/double conversions, double precision) run in the environment recorded
by the outermost scope, so their results do not depend on the scope. FCEQ,
FCGT, FCMEQ and FCMGT are integer comparisons that keep the earlier host IEEE
results (exponent255 with a nonzero fraction compares unordered, -0 equals +0,
denormals compare by value).
The curated drain and budgeted interpreter retain their observers, budgets,
IRQ/rejoin and policy code.

`python scripts/check_spu_float.py` compares actual helpers with an independent
Fraction oracle, rejects a compiled historical IEEE-multiply control, and
checks SIMD lanes across host rounding modes, fallback and state restoration.
The scope fixture also checks the held mode, exact results when SPU mode is
not held, host-arithmetic helpers inside and outside a scope, and the integer
comparisons against host IEEE comparisons, and the runner rejects two compiled
mutants (host helpers left in SPU mode; -0 ordered below +0).
Existing native-leaf, execution-observer, productive-IRET and thread-isolation
checks retain their assertions and link the new implementation.

The generic correction already exists in runtime combined. This candidate
keeps the same private generated inputs; included helper changes require a
fresh build, not regeneration. Its owner trial must establish any effect on
missing menu objects or race loading. Arithmetic fixtures do not attribute
those symptoms or establish a frame-rate improvement.
