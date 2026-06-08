# -*- coding: utf-8 -*-
"""
Origami — 设置持久化存储

线程安全的 JSON 读写，原子写入（先写 .tmp 再替换）。
借鉴 clawd-on-desk 的 settings-store.js：不可变快照 + 变更通知。
"""

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

from src.environ import SETTINGS_FILE
from src.settings.schema import get_defaults, SCHEMA_VERSION, MIGRATIONS

# ── 线程安全锁 ────────────────────────────────────────────
_file_lock = threading.Lock()

# ── 订阅者列表 ────────────────────────────────────────────
_subscribers: list[Callable] = []


def subscribe(callback: Callable[[dict, dict], None]):
    """
    订阅设置变更。

    回调签名: callback(changes: dict, snapshot: dict)
      - changes: 本次变更的键值对
      - snapshot: 变更后的完整配置快照
    """
    _subscribers.append(callback)


def _notify(changes: dict, snapshot: dict):
    """通知所有订阅者"""
    for cb in _subscribers:
        try:
            cb(changes, snapshot)
        except Exception:
            pass


# ── 底层文件操作 ──────────────────────────────────────────
def _read_raw() -> str:
    """线程安全读原始文本"""
    with _file_lock:
        if SETTINGS_FILE.exists():
            return SETTINGS_FILE.read_text(encoding="utf-8").strip()
    return ""


def _write_raw(content: str):
    """线程安全写（原子替换）"""
    with _file_lock:
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(SETTINGS_FILE)


# ── 公共 API ──────────────────────────────────────────────
def load() -> dict:
    """
    加载设置，自动合并默认值 + 执行迁移。

    返回完整配置 dict，保证所有 schema 定义的 key 都存在。
    """
    defaults = get_defaults()

    try:
        raw = _read_raw()
        if not raw:
            return defaults

        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return defaults

    # 版本迁移
    current_version = data.get("version", 0)
    for v in range(current_version, SCHEMA_VERSION):
        migrator = MIGRATIONS.get(v + 1)
        if migrator:
            data = migrator(data)
            data["version"] = v + 1

    # 合并默认值（保证新字段有默认值）
    merged = {**defaults, **data}

    return merged


def save(data: dict):
    """
    保存完整配置（原子写入）。

    用法:
        settings = store.load()
        settings["theme"] = "light"
        store.save(settings)
    """
    data["version"] = SCHEMA_VERSION
    _write_raw(json.dumps(data, ensure_ascii=False, indent=2))


def get(key: str, default: Any = None) -> Any:
    """读取单个配置项"""
    data = load()
    return data.get(key, default)


def set(key: str, value: Any):
    """
    设置单个配置项（原子写入 + 通知订阅者）。

    用法:
        store.set("theme", "light")
    """
    data = load()
    old = data.get(key)
    if old == value:
        return  # 值未变，跳过

    data[key] = value
    save(data)
    _notify({key: value}, data)
