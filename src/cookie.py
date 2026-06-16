# -*- coding: utf-8 -*-
"""
Origami — Cookie 获取与管理

通过 WebView 扫码登录获取抖音 Cookie，Base64 编码本地持久化。
"""

import base64
import time
from pathlib import Path
from typing import Optional

from src.environ import COOKIE_FILE


# ═══════════════════════════════════════════════════════════
# Base64 编解码
# ═══════════════════════════════════════════════════════════

def encode_cookie(cookie_str: str) -> str:
    return base64.b64encode(cookie_str.encode("utf-8")).decode("ascii")

def decode_cookie(encoded: str) -> str:
    try:
        return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    except Exception:
        return encoded


# ═══════════════════════════════════════════════════════════
# 持久化
# ═══════════════════════════════════════════════════════════

def save_cookie(cookie_str: str):
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(encode_cookie(cookie_str), encoding="utf-8")

def load_cookie() -> str:
    if not COOKIE_FILE.exists():
        return ""
    content = COOKIE_FILE.read_text(encoding="utf-8").strip()
    return decode_cookie(content) if content else ""


# ═══════════════════════════════════════════════════════════
# 校验
# ═══════════════════════════════════════════════════════════

def validate_cookie(cookie_str: str) -> bool:
    return bool(cookie_str) and "sessionid=" in cookie_str and "ttwid=" in cookie_str

def get_cookie_status() -> dict:
    if not COOKIE_FILE.exists():
        return {"ok": False, "length": 0, "mtime": None}
    try:
        cookie = load_cookie()
        mtime = COOKIE_FILE.stat().st_mtime
        return {"ok": validate_cookie(cookie), "length": len(cookie), "mtime": mtime}
    except Exception:
        return {"ok": False, "length": 0, "mtime": None}

def get_cookie_age_days() -> Optional[float]:
    status = get_cookie_status()
    if status["mtime"]:
        return (time.time() - status["mtime"]) / 86400
    return None


# ═══════════════════════════════════════════════════════════
# 扫码登录 → src/gui/dialogs/webview_login.py
# ═══════════════════════════════════════════════════════════
