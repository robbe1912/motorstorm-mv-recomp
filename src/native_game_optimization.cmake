# Consumer-side tuning of the authored native game sources of the game target
# (src/motorstorm): the kernels and adapters that are written as native C and
# C++. The lifted guest units and the runtime keep their own settings.
# PORT_OPTIMIZE_NATIVE adds /clang:-O1 /Ob1 to every target. A source option
# comes after it on the command line, so this level wins.
option(PORT_OPTIMIZE_NATIVE_GAME "Use checked O2 and automatic inlining for the native game sources of src/motorstorm; requires PORT_OPTIMIZE_NATIVE" OFF)

function(motorstorm_configure_native_game_optimization game_target)
    set(source_root "${CMAKE_CURRENT_SOURCE_DIR}/src/motorstorm")
    set(count 0)
    if(PORT_OPTIMIZE_NATIVE_GAME)
        if(NOT PORT_OPTIMIZE_NATIVE)
            message(FATAL_ERROR "Native game optimization requires checked native optimization")
        endif()
        if(MSVC)
            if(NOT CMAKE_C_COMPILER_ID STREQUAL "Clang")
                message(FATAL_ERROR "Checked native game optimization requires clang-cl on Windows")
            endif()
            set(options /clang:-O2 /Ob2)
        else()
            set(options -O2)
        endif()
        if(NOT TARGET ${game_target})
            message(FATAL_ERROR "Native game optimization requires the game target")
        endif()
        # Call this after the last function adds sources to the game target.
        get_target_property(game_sources ${game_target} SOURCES)
        set(native_sources "")
        foreach(source IN LISTS game_sources)
            get_filename_component(source_abs "${source}" ABSOLUTE)
            string(REPLACE "\\" "/" source_abs "${source_abs}")
            string(FIND "${source_abs}" "${source_root}/" position)
            if(position EQUAL 0 AND source_abs MATCHES "\\.(c|cpp)$")
                list(APPEND native_sources "${source_abs}")
            endif()
        endforeach()
        list(LENGTH native_sources count)
        if(count EQUAL 0)
            message(FATAL_ERROR "Native game optimization found no source of the game target under src/motorstorm")
        endif()
        set_property(SOURCE ${native_sources} TARGET_DIRECTORY ${game_target}
                     APPEND PROPERTY COMPILE_OPTIONS ${options})
        set(enabled true)
    else()
        set(enabled false)
    endif()
    file(WRITE "${CMAKE_BINARY_DIR}/native-game-optimization.json"
         "{\"enabled\":${enabled},\"target\":\"${game_target}\",\"sources\":${count}}\n")
endfunction()
