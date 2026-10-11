"""Read-only Win32 readiness check for the owned D3D12 game window."""
import ctypes
from ctypes import wintypes


def is_ready_window(state, pid, desktop):
    left, top, right, bottom = state['rect']
    x, y, width, height = desktop
    return (state['pid'] == pid and state['class_name'] == 'ps3recomp_d3d12'
            and state['visible'] and not state['minimized']
            and min(right, x + width) - max(left, x) > 0
            and min(bottom, y + height) - max(top, y) > 0)


def visible_native_window(pid):
    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    desktop = tuple(user.GetSystemMetrics(i) for i in (76, 77, 78, 79))
    found = []

    @callback_type
    def inspect(hwnd, _):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid:
            return True
        name = ctypes.create_unicode_buffer(256)
        rect = wintypes.RECT()
        if not user.GetClassNameW(hwnd, name, len(name)) or not user.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        state = dict(hwnd=int(hwnd), pid=owner.value, class_name=name.value,
                     rect=[rect.left, rect.top, rect.right, rect.bottom],
                     visible=bool(user.IsWindowVisible(hwnd)), minimized=bool(user.IsIconic(hwnd)))
        if is_ready_window(state, pid, desktop):
            found.append(state)
        return True

    if not user.EnumWindows(inspect, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if len(found) > 1:
        raise RuntimeError('Multiple owned game windows; cannot identify readiness')
    return found[0] if found else None
