# -*- coding: utf-8 -*-
"""单文件 exe 的解压目录：放在 AppData、运行期间占住、启动时清掉上次的残留。

exe 是 PyInstaller 的 onefile：每次启动由引导程序把 DLL、前端 dist、certifi 的 cacert.pem、
base_library.zip 等解压到 _MEIxxxx 再运行。默认解压在 %TEMP%，而存储感知 /「磁盘清理」的
计划任务会删掉 %TEMP% 里放了 7 天左右的文件——程序挂着跑一周，解压目录就被掏空：已加载的
DLL 被系统锁着删不掉，没锁的全没了。于是页面 500（index.html 不存在）、HTTPS 全挂（找不到
CA 证书包）、晚加载的模块 import 失败，进程却还活着，看起来就是「挂久了就死」。

所以分三层：

1. 解压到 %LOCALAPPDATA%\\PCResellingManager（pc_reselling.spec 的 runtime_tmpdir），系统清理
   不碰那里。不用 %APPDATA%：Roaming 在域环境里会跟着账户同步，上百 MB 的运行文件不该漫游。
   也不放 exe 旁边：runtime_tmpdir 的相对路径按的是当前工作目录而不是 exe 所在目录（实测），
   开机自启、快捷方式改了起始位置就解到别处去了。
2. lock_bundle()：给每个文件开一个只读句柄持有到进程结束。Python 在 Windows 上开文件不带
   FILE_SHARE_DELETE，有这个句柄在，任何进程删它都是「另一个程序正在使用此文件」，读不受影响。
   挡的是第三方清理软件这类第 1 层管不到的东西，同时也是第 3 层判断「有没有人在用」的依据。
3. sweep_stale()：AppData 不像 %TEMP% 有系统定期清。正常退出时引导程序会删掉自己的 _MEI，
   但被强杀、断电时来不及，不管的话每出一次事就多压一份上百 MB 的残留。
"""

from __future__ import annotations

import os
import shutil
import sys
import time

# 持有到进程结束：列表里的对象一旦被回收，句柄就关了，文件又变回可删。
_handles: list = []

# 与 pc_reselling.spec 里 runtime_tmpdir 的最后一级同名，两边改要一起改。只在这个专用目录里
# 清残留：解压位置万一回到 %TEMP%，那里的 _MEI* 可能是别的程序的，碰不得——对不上就什么都不做。
_RUNTIME_DIR_NAME = "PCResellingManager"
# 最近有改动的目录可能是另一份正在解压、还没来得及占住文件的实例，留给下次再清。
_STALE_AFTER_SECONDS = 600


def lock_bundle() -> int:
    """占住 sys._MEIPASS 下的全部文件，返回占住的个数。开发态没有解压目录，什么都不做。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass or sys.platform != "win32":
        return 0
    for dirpath, _dirnames, filenames in os.walk(meipass):
        for name in filenames:
            try:
                # buffering=0：要的只是句柄，别给上千个文件每个白占一块读缓冲。
                _handles.append(open(os.path.join(dirpath, name), "rb", buffering=0))
            except OSError:
                pass  # 个别文件打不开不影响其余的，大不了那一个回到原来的处境
    return len(_handles)


def sweep_stale() -> int:
    """删掉专用解压目录里上次没清掉的 _MEI*，返回删掉的个数。必须在 lock_bundle() 之后调。

    「没人在用」靠先改名来判断：Windows 下目录里有文件开着就改不了名，而活着的实例都已经
    lock_bundle() 占住了自己的全部文件，所以改名成功的一定是死掉的那份。改名之后再删，
    删到一半出错也不会留下一个看着还完整、实际缺文件的目录。
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass or sys.platform != "win32":
        return 0
    own = os.path.normcase(os.path.abspath(meipass))
    parent = os.path.dirname(own)
    if os.path.basename(parent) != os.path.normcase(_RUNTIME_DIR_NAME):
        return 0
    removed = 0
    for name in os.listdir(parent):
        path = os.path.join(parent, name)
        if not name.startswith("_MEI") or os.path.normcase(path) == own or not os.path.isdir(path):
            continue
        # 已经是 .stale 的是上回改了名却没删干净的，直接删。
        doomed = path if name.endswith(".stale") else path + ".stale"
        try:
            if doomed != path:
                if time.time() - os.path.getmtime(path) < _STALE_AFTER_SECONDS:
                    continue
                os.rename(path, doomed)
        except OSError:
            continue  # 改不了名 = 还有实例在用
        shutil.rmtree(doomed, ignore_errors=True)
        if not os.path.exists(doomed):
            removed += 1
    return removed
