# Consumer-side tuning of the whole ps3recomp runtime library; guest units keep
# their own settings. The library asks for -O2 outside Debug only, and
# PORT_OPTIMIZE_NATIVE's /clang:-O1 overrides that under clang-cl, so the level
# has to be appended last.
option(PORT_OPTIMIZE_RUNTIME "Use checked O2 and automatic inlining for the ps3recomp runtime" OFF)

function(motorstorm_configure_runtime_optimization)
    if(PORT_OPTIMIZE_RUNTIME)
        if(NOT PORT_OPTIMIZE_NATIVE)
            message(FATAL_ERROR "Runtime optimization requires checked native optimization")
        endif()
        if(NOT CMAKE_BUILD_TYPE STREQUAL "Debug" AND NOT CMAKE_BUILD_TYPE STREQUAL "RelWithDebInfo")
            message(FATAL_ERROR "Runtime optimization requires a Debug or RelWithDebInfo build")
        endif()
        if(NOT TARGET ps3recomp_runtime)
            message(FATAL_ERROR "Runtime optimization requires the runtime target")
        endif()
        if(MSVC)
            if(NOT CMAKE_C_COMPILER_ID STREQUAL "Clang")
                message(FATAL_ERROR "Checked runtime optimization requires clang-cl on Windows")
            endif()
            target_compile_options(ps3recomp_runtime PRIVATE /clang:-O2 /Ob2)
        else()
            target_compile_options(ps3recomp_runtime PRIVATE -O2)
        endif()
        set(enabled true)
    else()
        set(enabled false)
    endif()
    file(WRITE "${CMAKE_BINARY_DIR}/runtime-optimization.json"
         "{\"enabled\":${enabled},\"target\":\"ps3recomp_runtime\"}\n")
endfunction()
