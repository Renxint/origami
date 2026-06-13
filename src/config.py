# -*- coding: utf-8 -*-
"""
Origami — 全局配置常量

版本号、API 端点、反馈 webhook 等集中管理。
路径相关常量统一走 src/environ.py。
"""

import json
from pathlib import Path

from src.environ import EXE_DIR

# ── 版本 ─────────────────────────────────────────────────
VERSION = "0.2.0"
VERSION_URL = "https://github.com/Renxint/origami/raw/main/version.json"

# ── 钉钉反馈 webhook ─────────────────────────────────────
_CONFIG_PATH = EXE_DIR / "data" / "config.json"
_DEFAULT_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=140b22bf4f35c675bf36c7441a78871f4678762df788dd7079dd0f565f312ee9"


def _load_dingtalk_webhook() -> str:
    try:
        if _CONFIG_PATH.exists():
            cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            return cfg.get("dingtalk_webhook", _DEFAULT_WEBHOOK)
    except Exception:
        pass
    return _DEFAULT_WEBHOOK


DINGTALK_WEBHOOK = _load_dingtalk_webhook()

# ── HTTP ─────────────────────────────────────────────────
HTTP_TIMEOUT = 30
PAGE_DELAY = 1.5
