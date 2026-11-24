/* Fixture of scripts/check_no_dialogs.py.
 *
 * The program links the debug CRT, like the game. argv[1] selects a report;
 * argv[2] "quiet" calls motorstorm::no_dialogs() first.
 *
 *   box      MessageBoxW: a dialog that no CRT setting controls
 *   assert   _ASSERTE with a false expression
 *   param    fclose(NULL): an invalid CRT parameter
 *   heap     write past the end of a heap block; the debug heap reports it
 *            at free through _CRT_ERROR
 *
 * Each mode prints "fixture: <mode> start" and, when the process continues,
 * "fixture: <mode> end". The exit code is 4 when the program runs to its end.
 */
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include <windows.h>
#include <crtdbg.h>

#include "motorstorm/no_dialogs.h"

int main(int argc, char** argv) {
    const char* mode = argc > 1 ? argv[1] : "";
    const bool quiet = argc > 2 && !std::strcmp(argv[2], "quiet");
    std::printf("fixture: %s start\n", mode);
    std::fflush(stdout);
    if (quiet) motorstorm::no_dialogs();
    if (!std::strcmp(mode, "box")) {
        MessageBoxW(nullptr, L"probe body", L"MOTORSTORM_QUIET_RUN_PROBE_TITLE", MB_OK);
    } else if (!std::strcmp(mode, "assert")) {
        _ASSERTE(mode == nullptr);
    } else if (!std::strcmp(mode, "param")) {
        std::fclose(nullptr);
    } else if (!std::strcmp(mode, "heap")) {
        unsigned char* block = static_cast<unsigned char*>(std::malloc(16));
        /* Only the 4 guard bytes after the block: the headers of the heap stay whole. */
        std::memset(block, 0x5A, 20);
        std::free(block);
    } else {
        std::fprintf(stderr, "fixture: unknown mode\n");
        return 2;
    }
    std::printf("fixture: %s end\n", mode);
    return 4;
}
