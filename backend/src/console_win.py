# -*- coding: utf-8 -*-
"""Windows：给无控制台（windowed）打包的 exe 补一个隐藏的日志控制台。

打包成 windowed 之后进程没有 stdout/stderr，`print` 与 logging 的 StreamHandler 写到
None 上会抛异常。这里在启动最早期分配一个控制台并把三个标准流接上去，后续所有日志
才有真实落点；窗口本身默认隐藏，内容由运行窗口（log_window.py）实时显示出来。

它的关闭按钮被摘掉：Windows 在控制台窗口被关闭时会**强制**结束进程，而且那次关闭拦不住、
取消不了——留着 X 就等于留了一个「点一下直接杀进程」的按钮。隐藏/退出统一走托盘与运行窗口。

只在 Windows 冻结态使用，其余情况全部 no-op。
"""

from __future__ import annotations

import sys

_SW_HIDE = 0
_SW_RESTORE = 9
_SC_CLOSE = 0xF060
_MF_BYCOMMAND = 0x0000


def _kernel32():
    import ctypes

    return ctypes.windll.kernel32


def _user32():
    import ctypes

    return ctypes.windll.user32


def _reopen_std_streams() -> None:
    """AllocConsole 之后把 stdout/stderr/stdin 接到新控制台（CONOUT$ / CONIN$）。"""
    for name, target, mode in (
        ("stdout", "CONOUT$", "w"),
        ("stderr", "CONOUT$", "w"),
        ("stdin", "CONIN$", "r"),
    ):
        try:
            stream = open(target, mode, encoding="utf-8", buffering=1 if mode == "w" else -1)
            setattr(sys, name, stream)
        except Exception:  # noqa: BLE001
            pass


def _disable_close(hwnd: int) -> None:
    """从系统菜单里删掉「关闭」，X 随之变灰。"""
    try:
        u = _user32()
        menu = u.GetSystemMenu(hwnd, False)
        if menu:
            u.DeleteMenu(menu, _SC_CLOSE, _MF_BYCOMMAND)
    except Exception:  # noqa: BLE001
        pass


def setup_hidden_console() -> bool:
    """分配隐藏控制台并接管标准流。返回 True 表示这次新分配了一个。"""
    if sys.platform != "win32":
        return False
    try:
        k = _kernel32()
        # 已经有控制台（从 CMD 里跑 exe）：不重复分配，也不隐藏——那反而把用户自己的窗口藏了。
        existing = k.GetConsoleWindow()
        if existing:
            return False
        if not k.AllocConsole():
            return False
        try:
            k.SetConsoleOutputCP(65001)  # UTF-8，中文日志才不是乱码
            k.SetConsoleCP(65001)
        except Exception:  # noqa: BLE001
            pass
        _reopen_std_streams()
        hwnd = k.GetConsoleWindow()
        if hwnd:
            _disable_close(hwnd)
            _user32().ShowWindow(hwnd, _SW_HIDE)
        try:
            k.SetConsoleTitleW("PC Reselling Manager - 日志")
        except Exception:  # noqa: BLE001
            pass
        return True
    except Exception:  # noqa: BLE001
        return False


def show_console() -> None:
    """显示控制台。仅作为运行窗口不可用（无 tkinter）时的回退。"""
    if sys.platform != "win32":
        return
    try:
        hwnd = _kernel32().GetConsoleWindow()
        if hwnd:
            u = _user32()
            u.ShowWindow(hwnd, _SW_RESTORE)
            u.SetForegroundWindow(hwnd)
    except Exception:  # noqa: BLE001
        pass


def hide_console() -> None:
    if sys.platform != "win32":
        return
    try:
        hwnd = _kernel32().GetConsoleWindow()
        if hwnd:
            _user32().ShowWindow(hwnd, _SW_HIDE)
    except Exception:  # noqa: BLE001
        pass
