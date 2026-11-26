# Compile options of the lifted guest units (the output of the lifter).
#
# The lifted units are machine-generated and can run to hundreds of thousands of
# lines each, so they get their own flags:
#
#   - warnings off. They are about generated code, and at this volume they bury
#     the diagnostics that matter.
#   - no floating-point contraction. A PPC fmadd is spelt as one where the
#     lifter means one.
#   - /bigobj on MSVC. A single lifted file passes the 65,536-section limit of
#     the default object format.
#   - AVX2 and FMA. The fused VMX family of ppu_vmx.h calls fmaf. Without FMA
#     in the unit, each call goes to the C runtime. With FMA, the compiler
#     makes one vfmadd instruction. The global option turns contraction off,
#     so an ordinary product and sum keeps its two roundings.
#   - optimization. PORT_OPTIMIZE_NATIVE gives all native code checked O1 with
#     no automatic inlining. PORT_OPTIMIZE_GUEST gives the lifted units O2 with
#     automatic inlining instead. The memory helpers of ppu_fastmem.h carry an
#     inline hint; at O1 the compiler keeps out-of-line copies of them in most
#     lifted units, so every guest load and store pays a call.
#
# PORT_OPTIMIZE_GUEST requires PORT_OPTIMIZE_NATIVE. Call this once, after the
# source list exists and before the target is defined.
function(motorstorm_guest_compile_options sources)
    if(NOT sources)
        message(FATAL_ERROR "motorstorm_guest_compile_options needs the lifted source list")
    endif()
    if(PORT_OPTIMIZE_GUEST AND NOT PORT_OPTIMIZE_NATIVE)
        message(FATAL_ERROR "PORT_OPTIMIZE_GUEST requires PORT_OPTIMIZE_NATIVE")
    endif()
    if(MSVC)
        if(PORT_OPTIMIZE_GUEST)
            # Later /clang:-O and /Ob arguments replace the O1 pair of the global options.
            set_source_files_properties(${sources} PROPERTIES
                COMPILE_OPTIONS "/w;/bigobj;/clang:-O2;/Ob2;/arch:AVX2")
        else()
            set_source_files_properties(${sources} PROPERTIES
                COMPILE_OPTIONS "/w;/bigobj;/arch:AVX2")
        endif()
    else()
        if(PORT_OPTIMIZE_GUEST)
            set_source_files_properties(${sources} PROPERTIES
                COMPILE_OPTIONS "-w;-ffp-contract=off;-O2;-mavx2;-mfma")
        else()
            set_source_files_properties(${sources} PROPERTIES
                COMPILE_OPTIONS "-w;-ffp-contract=off;-mavx2;-mfma")
        endif()
    endif()
endfunction()
