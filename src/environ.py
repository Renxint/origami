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
OUTPUT_SINGLE   = OUTPUT_BASE / "单视频"
OUTPUT_HOMEPAGE = OUTPUT_BASE / "主页下载"

# Sign server
BOOTSTRAP_JS    = BASE_DIR / "sign-server" / "bootstrap.js"
NODE_EXE        = BASE_DIR / "node.exe"
NODE_CMD        = str(NODE_EXE) if NODE_EXE.exists() else "node"

# ── User-Agent ────────────────────────────────────────────
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36 "
    "SLBrowser/9.0.8.5161 SLBChan/111 SLBVPV/64-bit"
)
