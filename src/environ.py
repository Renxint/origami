# -*- coding: utf-8 -*-
"""
Origami — 环境路径解析

统一管理所有路径常量：开发模式 vs PyInstaller 打包模式。
所有模块通过此处获取路径，避免散落各处的 __file__ 计算。
"""

import sys, os
from pathlib import Path

# ── SSL 证书修复（PyInstaller 打包后 certifi 路径错误） ──────
import certifi

_cert_path = Path(certifi.where())
if not _cert_path.exists() and getattr(sys, "frozen", False):
    _cert_path = Path(sys._MEIPASS) / "certifi" / "cacert.pem"
os.environ["SSL_CERT_FILE"] = str(_cert_path)
os.environ["REQUESTS_CA_BUNDLE"] = str(_cert_path)

# ── Windows 进程标志 ──────────────────────────────────────
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# ── 路径解析 ──────────────────────────────────────────────
_FROZEN = getattr(sys, "frozen", False)

if _FROZEN:
    BASE_DIR = Path(sys._MEIPASS)           # _internal 目录
    EXE_DIR = Path(sys.executable).parent   # exe 所在目录
else:
    # 开发模式：src/environ.py → src/ → Origami/
    BASE_DIR = Path(__file__).resolve().parent.parent
    EXE_DIR = BASE_DIR

PROJECT_DIR = BASE_DIR

# ── 文件路径常量 ──────────────────────────────────────────
SETTINGS_FILE   = EXE_DIR / "settings.json"
CRASH_LOG       = EXE_DIR / "_crash.log"
COOKIE_FILE     = EXE_DIR / "data" / "Cookie.txt"
CONFIG_FILE     = EXE_DIR / "data" / "config.json"

# 输出目录
OUTPUT_BASE     = EXE_DIR / "output"
OUTPUT_SINGLE   = OUTPUT_BASE / "单作品"
OUTPUT_BATCH    = OUTPUT_BASE / "批量作品"
OUTPUT_OWN      = OUTPUT_BATCH / "用户目录"     # 自己主页
OUTPUT_OTHER    = OUTPUT_BATCH / "他人目录"     # 别人主页
OUTPUT_HOMEPAGE = OUTPUT_OTHER                 # 向后兼容

# Sign server
BOOTSTRAP_JS    = BASE_DIR / "sign-server" / "bootstrap.js"
SIGN_SERVER_JS  = BASE_DIR / "sign-server" / "server.js"
NODE_EXE        = BASE_DIR / "node.exe"
NODE_CMD        = str(NODE_EXE) if NODE_EXE.exists() else "node"
SIGN_SERVER_PORT = 9876
SIGN_SERVER_URL  = f"http://localhost:{SIGN_SERVER_PORT}"

# ── 窗口强置顶 ────────────────────────────────────────────

def force_raise_window(widget) -> bool:
    """强制将窗口置顶（模拟 Alt 键抢焦点 + HWND_TOPMOST）"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        hwnd = int(widget.winId())
        user32 = ctypes.windll.user32

        # 1. 恢复最小化
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE

        # 2. 模拟 Alt 键：骗 Windows 以为我们有用户输入，解锁 SetForegroundWindow
        VK_MENU = 0x12
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

        # 3. 让当前进程可设前台窗口
        kernel32 = ctypes.windll.kernel32
        user32.AllowSetForegroundWindow(kernel32.GetCurrentProcessId())

        # 4. 暂时置顶
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)

        # 5. 抢前台
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.ShowWindow(hwnd, 5)  # SW_SHOW

        # 6. 取消置顶
        user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags)

        return True
    except Exception:
        return False


# ── User-Agent ────────────────────────────────────────────
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36 "
    "SLBrowser/9.0.8.5161 SLBChan/111 SLBVPV/64-bit"
)
