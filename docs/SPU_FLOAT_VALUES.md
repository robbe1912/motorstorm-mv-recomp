# SPU single-precision values

This selective sync ports Robin Fröhlich’s `057c56c` runtime correction and
`daeb1575` scoped SIMD follow-up. Exponent255 is finite in SPU single precision;
host IEEE NaN/infinity behavior is incorrect. Exact integer significands
preserve truncation, flush and saturation for FA/FS/FM/FMA/FMS/FNMS/FI.
FPSCR exception accumulation remains separate and unchanged.

SIMD admits safe ordinary vectors and falls back for exceptional ranges.
Its enter/leave scopes preserve host FP state and thread-local nesting.
The curated drain and budgeted interpreter retain their observers, budgets,
IRQ/rejoin and policy code.

`python scripts/check_spu_float.py` compares actual helpers with an independent
Fraction oracle, rejects a compiled historical IEEE-multiply control, and
checks SIMD lanes across host rounding modes, fallback and state restoration.
Existing native-leaf, execution-observer, productive-IRET and thread-isolation
checks retain their assertions and link the new implementation.

The generic correction already exists in runtime combined. This candidate
keeps the same private generated inputs; included helper changes require a
fresh build, not regeneration. Its owner trial must establish any effect on
missing menu objects or race loading. Arithmetic fixtures do not attribute
those symptoms or establish a frame-rate improvement.
