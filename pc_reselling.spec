# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包规格：把后端 + 前端 dist 打成单个 exe。

前端 webside/dist 通过 datas 塞进 exe，运行时 web_static.py 会从 sys._MEIPASS 里读；
也支持在 exe 同目录放一个 webside/dist 来热替换前端而不重新打包。

产物是 **windowed**（无 CMD 黑框）：双击后显示运行窗口（backend/src/log_window.py），
点 X 可选「收入任务栏」，托盘图标由 backend/src/tray.py 驻留。由此带来三条打包侧的约束，
改这个文件时别把它们改没了：

  - `console=False`。改回 True 的话控制台又回来了，而控制台窗口的 X 是杀进程、拦不住的，
    「收入任务栏」也就无从谈起。
  - **tkinter 不能进 excludes**，运行窗口就是 Tk 写的；排掉它 exe 能打出来、跑起来窗口
    不出现（start() 那里 import 失败静默返回 False），只剩一个看不见的隐藏控制台。
  - 托盘图标 logo.png 必须打进 _MEIPASS/static，tray.icon_path() 按这个路径找。
"""

import os
import sys
from PyInstaller.utils.hooks import collect_submodules

# ===== conda 环境的 DLL 必须优先于 PATH 上的同名文件 =====
# 扩展模块（_ssl / _hashlib / _sqlite3 / _lzma / _bz2 / _ctypes / _tkinter / pyexpat）依赖的
# 那批 DLL 在 conda 里不跟 python.exe 放一起，而是单独住在 <env>\Library\bin。PyInstaller 解析
# 依赖时按 PATH 找，于是随手捞到的是 anaconda base 或者 Git for Windows 里的同名 DLL——版本对
# 不上，打出来的 exe 一启动就 "DLL load failed while importing _ssl: 找不到指定的程序"
# （ERROR_PROC_NOT_FOUND：DLL 找到了，但缺少 _ssl.pyd 要的导出符号）。
#
# sys.prefix 就是跑这次打包的那个环境，把它自己的三个目录顶到 PATH 最前面，PyInstaller 便只会
# 拿到配套的版本。PATH 是解析时才读的，所以在这里改来得及。
# 注意这不是「装了什么依赖」的问题，pip 装不出来——纯粹是 conda 的 DLL 布局与 PyInstaller 的
# 查找顺序对不上，换台机器、装了别的软件都可能捞到另一份。
_ENV_DLL_DIRS = [
    os.path.join(sys.prefix, "Library", "bin"),
    os.path.join(sys.prefix, "DLLs"),
    sys.prefix,
]
os.environ["PATH"] = os.pathsep.join(
    [d for d in _ENV_DLL_DIRS if os.path.isdir(d)] + [os.environ.get("PATH", "")]
)
print("[pc_reselling.spec] DLL 搜索目录已前置：%s" % os.path.join(sys.prefix, "Library", "bin"))

ROOT = os.path.abspath(os.getcwd())
BACKEND = os.path.join(ROOT, "backend")
DIST_WEB = os.path.join(ROOT, "webside", "dist")
STATIC = os.path.join(ROOT, "webside", "public", "static")

datas = []
if os.path.isdir(DIST_WEB):
    datas.append((DIST_WEB, os.path.join("webside", "dist")))

# 托盘 / 运行窗口的图标。png 给 pystray 与 Tk（两者都读不了 SVG），
# ico 给 exe 自身（PyInstaller 的 icon 只收 .ico）。都由 logo.svg 的图形转出。
ICON_PNG = os.path.join(STATIC, "logo.png")
ICON_ICO = os.path.join(STATIC, "favicon.ico")
if os.path.isfile(ICON_PNG):
    datas.append((ICON_PNG, "static"))
else:
    print("[pc_reselling.spec] 警告：未找到 logo.png，托盘会退回一个纯色方块图标")
icon_arg = ICON_ICO if os.path.isfile(ICON_ICO) else None
if icon_arg is None:
    print("[pc_reselling.spec] 警告：未找到 favicon.ico，exe 用 PyInstaller 默认图标")

# uvicorn / pymysql 有大量运行时动态导入的子模块，收集全避免打包后缺模块
hidden = []
for pkg in ("uvicorn", "pymysql", "email", "anyio"):
    hidden += collect_submodules(pkg)
hidden += ["pymysql.cursors"]

# 桌面外壳：tkinter 的 import 写在函数里，pystray 的 Windows 后端（pystray._win32）是
# 运行时按平台挑的，两者都躲得过静态分析，必须显式声明。
hidden += ["tkinter", "tkinter.font"]
hidden += collect_submodules("pystray")
hidden += ["PIL.Image", "PIL.ImageDraw", "PIL._tkinter_finder"]

a = Analysis(
    [os.path.join(BACKEND, "main.py")],
    pathex=[BACKEND],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    # tkinter 不在此列：运行窗口要用它（见模块头的说明）。
    excludes=["matplotlib", "numpy", "torch", "cv2"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PCResellingManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # 无控制台：日志改由运行窗口显示，退出与收起走窗口的 X 和托盘菜单。
    console=False,
    disable_windowed_traceback=False,  # 启动期崩溃仍要弹出堆栈，否则 exe 就是双击没反应
    icon=icon_arg,
)
