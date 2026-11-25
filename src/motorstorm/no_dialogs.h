/* Keep a diagnostic build silent on the desktop.
 *
 * The debug CRT shows each assertion, each invalid CRT parameter and each heap
 * check result in a modal dialog. The dialog stops its thread until a person
 * clicks it. An owned run has nobody at the window, so the same text goes to
 * stderr instead. The run directory keeps stderr (native.err). A program that
 * runs to a false assertion continues after the report. Windows Error
 * Reporting gets no dialog either: the launcher owns the exit path.
 *
 * Call this first in main, before any library code runs. A test program that
 * links the debug CRT includes this header and calls it first too.
 */
#ifndef MOTORSTORM_NO_DIALOGS_H
#define MOTORSTORM_NO_DIALOGS_H

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <crtdbg.h>

namespace motorstorm {

inline void no_dialogs() {
#if defined(_DEBUG)
    /* Debug CRT: send each report to stderr. The default is a dialog. */
    _CrtSetReportMode(_CRT_WARN, _CRTDBG_MODE_FILE);
    _CrtSetReportFile(_CRT_WARN, _CRTDBG_FILE_STDERR);
    _CrtSetReportMode(_CRT_ERROR, _CRTDBG_MODE_FILE);
    _CrtSetReportFile(_CRT_ERROR, _CRTDBG_FILE_STDERR);
    _CrtSetReportMode(_CRT_ASSERT, _CRTDBG_MODE_FILE);
    _CrtSetReportFile(_CRT_ASSERT, _CRTDBG_FILE_STDERR);
#endif
    /* No critical error box, no error report box, no open file error box. */
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);
}

}   // namespace motorstorm

#else
namespace motorstorm {
inline void no_dialogs() {}
}   // namespace motorstorm
#endif

#endif
