#!/usr/bin/env python3
"""Run a command on a private desktop: its dialogs stay invisible.

Usage: python scripts/quiet_run.py [--timeout SECONDS] [--] <command> [args ...]

A diagnostic build (debug CRT) reports an assertion, an invalid CRT parameter
or a heap check in a modal dialog. Windows Error Reporting does the same for a
crash. The dialog stops the process until a person clicks it. This tool starts
the command on a new desktop of the current window station. A dialog is created
there, so the process still stops, but nobody sees it. After `--timeout`
seconds (default 0: no limit) the command and its children end, and the exit
code is 124. stdin, stdout and stderr stay those of the caller. Only the three
standard handles reach the command.

The tool changes no library and no setting. A program that calls
motorstorm::no_dialogs() (src/motorstorm/no_dialogs.h) writes its reports to
stderr and makes no dialog. Use this tool for programs that do not.
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

EXIT_TIMEOUT = 124
DESKTOP_ALL_ACCESS = 0x000F01FF
DESKTOP_ENUMERATE = 0x0040
DESKTOP_READOBJECTS = 0x0001
STARTF_USESTDHANDLES = 0x00000100
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE = 0xFFFFFFF6, 0xFFFFFFF5, 0xFFFFFFF4
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
INFINITE = 0xFFFFFFFF
WAIT_TIMEOUT_ = 0x00000102


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR),
                ("lpTitle", wt.LPWSTR), ("dwX", wt.DWORD), ("dwY", wt.DWORD),
                ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD), ("dwXCountChars", wt.DWORD),
                ("dwYCountChars", wt.DWORD), ("dwFillAttribute", wt.DWORD), ("dwFlags", wt.DWORD),
                ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD),
                ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)), ("hStdInput", wt.HANDLE),
                ("hStdOutput", wt.HANDLE), ("hStdError", wt.HANDLE)]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE),
                ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]


def _user32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.CreateDesktopW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p, wt.DWORD,
                                      wt.DWORD, ctypes.c_void_p]
    user32.CreateDesktopW.restype = wt.HANDLE
    user32.OpenDesktopW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.BOOL, wt.DWORD]
    user32.OpenDesktopW.restype = wt.HANDLE
    user32.CloseDesktop.argtypes = [wt.HANDLE]
    user32.CloseDesktop.restype = wt.BOOL
    return user32


def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetStdHandle.argtypes = [wt.DWORD]
    kernel32.GetStdHandle.restype = wt.HANDLE
    kernel32.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, wt.DWORD, wt.DWORD,
                                                          ctypes.POINTER(ctypes.c_size_t)]
    kernel32.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.c_size_t,
                                                   ctypes.c_void_p, ctypes.c_size_t,
                                                   ctypes.c_void_p, ctypes.c_void_p]
    kernel32.CreateProcessW.argtypes = [wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                        wt.BOOL, wt.DWORD, ctypes.c_void_p, wt.LPCWSTR,
                                        ctypes.c_void_p, ctypes.POINTER(PROCESS_INFORMATION)]
    kernel32.CreateProcessW.restype = wt.BOOL
    kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
    kernel32.WaitForSingleObject.restype = wt.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
    kernel32.GetExitCodeProcess.restype = wt.BOOL
    kernel32.CloseHandle.argtypes = [wt.HANDLE]
    return kernel32


def windows_on_desktop(name):
    """Return the titles of the visible top-level windows of the desktop `name`."""
    user32 = _user32()
    desktop = user32.OpenDesktopW(name, 0, False, DESKTOP_READOBJECTS | DESKTOP_ENUMERATE)
    if not desktop:
        return None
    titles = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def collect(window, _):
        length = user32.GetWindowTextLengthW(window)
        if user32.IsWindowVisible(window) and length:
            text = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(window, text, length + 1)
            titles.append(text.value)
        return True

    user32.EnumDesktopWindows(desktop, collect, 0)
    user32.CloseDesktop(desktop)
    return titles


def visible_window_titles():
    """Return the titles of the visible top-level windows of the desktop of this process."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    titles = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def collect(window, _):
        length = user32.GetWindowTextLengthW(window)
        if user32.IsWindowVisible(window) and length:
            text = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(window, text, length + 1)
            titles.append(text.value)
        return True

    user32.EnumWindows(collect, 0)
    return titles


def run(command, timeout=0, desktop_name=None):
    """Run `command` on a private desktop.

    Return (exit code, seconds, windows). `windows` is None when the command ends by itself.
    At the time limit it holds two title lists, read while the command is blocked: the visible
    windows of the private desktop and those of the desktop of this process.
    """
    kernel32 = _kernel32()
    user32 = _user32()
    name = desktop_name or "motorstorm_quiet_%d" % (time.time_ns() // 1000)
    desktop = user32.CreateDesktopW(name, None, None, 0, DESKTOP_ALL_ACCESS, None)
    if not desktop:
        raise OSError(ctypes.get_last_error(), "CreateDesktopW failed")
    handles = (wt.HANDLE * 3)(kernel32.GetStdHandle(STD_INPUT_HANDLE),
                              kernel32.GetStdHandle(STD_OUTPUT_HANDLE),
                              kernel32.GetStdHandle(STD_ERROR_HANDLE))
    for handle in handles:
        if handle:
            os.set_handle_inheritable(handle, True)
    size = ctypes.c_size_t()
    kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    attributes = (ctypes.c_ubyte * size.value)()
    if not kernel32.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)):
        raise OSError(ctypes.get_last_error(), "InitializeProcThreadAttributeList failed")
    if not kernel32.UpdateProcThreadAttribute(
            attributes, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, handles, ctypes.sizeof(handles), None, None):
        raise OSError(ctypes.get_last_error(), "UpdateProcThreadAttribute failed")
    startup = STARTUPINFOEXW()
    startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
    startup.StartupInfo.lpDesktop = "winsta0\\" + name
    startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES
    startup.StartupInfo.hStdInput, startup.StartupInfo.hStdOutput, startup.StartupInfo.hStdError = handles
    startup.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
    information = PROCESS_INFORMATION()
    line = ctypes.create_unicode_buffer(subprocess.list2cmdline(command))
    started = time.monotonic()
    if not kernel32.CreateProcessW(None, line, None, None, True, EXTENDED_STARTUPINFO_PRESENT,
                                   None, None, ctypes.byref(startup), ctypes.byref(information)):
        raise OSError(ctypes.get_last_error(), "CreateProcessW failed")
    kernel32.CloseHandle(information.hThread)
    timed_out = False
    windows = None
    try:
        wait = kernel32.WaitForSingleObject(information.hProcess,
                                            INFINITE if not timeout else int(timeout * 1000))
        if wait == WAIT_TIMEOUT_:
            timed_out = True
            # Windows while the command is blocked: on its desktop and on the desktop of this process.
            windows = (windows_on_desktop(name) or [], visible_window_titles())
            # The command is blocked: end it with its children. It is the process tree of this call.
            subprocess.run(["taskkill", "/PID", str(information.dwProcessId), "/T", "/F"], capture_output=True)
            kernel32.WaitForSingleObject(information.hProcess, 30000)
        code = wt.DWORD(1)
        kernel32.GetExitCodeProcess(information.hProcess, ctypes.byref(code))
    finally:
        kernel32.CloseHandle(information.hProcess)
        user32.CloseDesktop(desktop)
    return (EXIT_TIMEOUT if timed_out else code.value), time.monotonic() - started, windows


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run a command on a private desktop.")
    parser.add_argument("--timeout", type=float, default=0.0,
                        help="seconds until a blocked command ends (exit 124); 0 for no limit")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="the command, after --")
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command")
    code, seconds, windows = run(command, args.timeout)
    if code == EXIT_TIMEOUT:
        print("quiet_run: the command did not end in %.0f s; it is stopped. Windows on its desktop: %s; "
              "on the desktop of the caller: %s" % (args.timeout, windows[0], windows[1]), file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
