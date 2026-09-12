# -*- coding: utf-8 -*-
"""Uvicorn 启动。后端只监听普通 HTTP，需要 HTTPS 就在前面放 nginx。

打包成 exe（冻结态）时这里还顺带把桌面外壳装起来：托盘图标 + 运行窗口的退出回调，
见 _start_desktop_shell。开发态一概不装。
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Optional

import uvicorn
from fastapi import FastAPI

from src import conf

log = logging.getLogger(__name__)


def _reload_enabled() -> bool:
    # 热重载只在开发时开：设 PC_RESELLING_RELOAD=1（start.bat 会设）。打包成 exe 后
    # 冻结态不能用 reload（会重新 spawn 自身导致递归/找不到模块），所以冻结时强制关闭。
    if getattr(sys, "frozen", False):
        return False
    return (os.environ.get("PC_RESELLING_RELOAD") or "").strip().lower() in ("1", "true", "yes")


def _enable_windows_console_ansi() -> None:
    """在 Windows 控制台开启 VT 处理，让 uvicorn 日志的颜色码正常渲染，
    而不是显示成 ``[32m...[0m`` 这样的乱码（打包成 exe 后在 CMD 里跑尤其明显）。
    只开 VT，不改代码页，避免影响中文输出。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        for handle_id in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:  # noqa: BLE001
        pass


def run(app: FastAPI, import_string: Optional[str] = None) -> None:
    """启动服务。

    ``import_string``（如 ``"main:app"``）只在开启热重载时用得上——uvicorn 的 reload
    必须拿一个「模块:变量」字符串才能在文件改动后重新导入应用；直接传 app 对象是没法
    reload 的。不重载时就用传进来的 app 对象，省一次导入。
    """
    _enable_windows_console_ansi()
    cfg = conf.server_config()
    reload = _reload_enabled() and bool(import_string)

    common = dict(
        host=cfg["host"],
        port=cfg["port"],
        log_level="info",
        # 前置 nginx 时要让后端认得 X-Forwarded-Proto / X-Forwarded-For，
        # 否则日志里的客户端 IP 全是 127.0.0.1。
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )

    if reload:
        log.info("后端启动（热重载已开启）：http://%s:%s", cfg["host"], cfg["port"])
        # 只监视 backend 目录下的 .py，改前端不触发后端重启（前端有 Vite 自己的 HMR）。
        from src.app_paths import backend_root

        uvicorn.run(
            import_string,
            reload=True,
            reload_dirs=[str(backend_root())],
            **common,
        )
    else:
        log.info("后端启动：http://%s:%s", cfg["host"], cfg["port"])
        _serve(app, common)


def _serve(app: FastAPI, options: dict) -> None:
    """非热重载路径：自己建 uvicorn.Server，而不是图省事用 uvicorn.run()。

    uvicorn.run() 把 Server 实例藏在函数里，外面拿不到 should_exit，也就没法从托盘菜单
    触发优雅停机——而 windowed 打包之后，托盘和运行窗口是仅有的退出入口。
    """
    config = uvicorn.Config(
        app,
        # 优雅停机上限：在途请求（比如一次慢查询）不该把停机卡住，否则点了「退出程序」
        # 托盘图标已经消失、进程却还占着端口赖在后台。
        timeout_graceful_shutdown=5,
        **options,
    )
    server = uvicorn.Server(config)
    _start_desktop_shell(server)
    server.run()

    # 冻结态：优雅停机后 Tk / pystray / 连接池这些后台线程未必全退干净，直接结束进程。
    if getattr(sys, "frozen", False):
        os._exit(0)


def _start_desktop_shell(server: uvicorn.Server) -> None:
    """冻结态（Windows）挂上托盘图标，并把「退出程序」接到优雅停机上。

    开发态直接跳过：命令行里跑着的时候 Ctrl+C 就是退出，再弹一个托盘图标只会碍事。
    """
    if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
        return

    def _quit() -> None:
        # 先摘掉托盘图标再停机：停机要好几秒，图标该立刻消失，否则看着像点了没反应。
        try:
            from src.tray import stop_tray

            stop_tray()
        except Exception:  # noqa: BLE001
            pass
        server.should_exit = True

        # 看门狗兜底：万一停机彻底卡死（主循环停不下来），到点强制结束进程——
        # 托盘图标都没了还有个进程占着 9910，下次启动会直接报端口被占用。
        def _watchdog() -> None:
            time.sleep(8)
            os._exit(0)

        threading.Thread(target=_watchdog, daemon=True).start()

    try:
        from src.log_window import set_on_quit

        set_on_quit(_quit)
    except Exception:  # noqa: BLE001
        pass

    try:
        from src.tray import start_tray

        if not start_tray(on_quit=_quit):
            log.warning("系统托盘未启动（pystray / Pillow 缺失？），程序继续运行")
    except Exception:  # noqa: BLE001
        log.warning("系统托盘启动失败，程序继续运行", exc_info=True)
