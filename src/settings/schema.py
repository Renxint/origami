# -*- coding: utf-8 -*-
"""
Origami — 设置 Schema

定义所有配置项的默认值、类型、校验规则。
借鉴 clawd-on-desk 的 prefs.js：schema → load → validate → migrate。
"""

from typing import Any

# Schema 版本（每次新增/修改字段时递增）
SCHEMA_VERSION = 1

# ── 平台 key 列表（随平台扩展更新） ──────────────────────────
KNOWN_PLATFORMS = ["douyin", "bilibili", "weibo", "youtube", "kuaishou", "instagram", "xiaohongshu"]

# ── Schema 定义 ─────────────────────────────────────────
SETTINGS_SCHEMA: dict[str, dict[str, Any]] = {
    "version": {
        "default": SCHEMA_VERSION,
        "type": int,
        "desc": "Schema 版本号，用于自动迁移",
    },
    "font_family": {
        "default": "",
        "type": str,
        "desc": "字体名称，空字符串表示使用系统默认",
    },
    "font_size": {
        "default": 15,
        "type": int,
        "min": 8,
        "max": 24,
        "desc": "字体大小 (pt)",
    },
    "auto_raise": {
        "default": True,
        "type": bool,
        "desc": "剪贴板检测到链接时自动弹窗到最前",
    },
    "tray_enabled": {
        "default": False,
        "type": bool,
        "desc": "是否启用系统托盘",
    },
    "download_paths": {
        "default": {
            "single": "",
            "homepage": "",
        },
        "type": dict,
        "desc": "下载路径（空字符串 = 使用默认 output/ 目录）",
    },
    "cookie": {
        "default": {},
        "type": dict,
        "desc": "各平台 Cookie（base64 编码存储），key 为平台标识",
        # 示例: {"douyin": "c2Vzc2lvbmlkPXh4eDt0dHdpZD15eXk="}
    },
    "geometry": {
        "default": None,
        "type": (dict, type(None)),
        "desc": "窗口几何信息，包含 'geo' hex 字符串",
    },
    # ── 预留给后续版本 ──
    "platforms": {
        "default": {},
        "type": dict,
        "desc": "各平台独立设置（如 bilibili.cookie, weibo.quality 等）",
    },
    "shortcuts": {
        "default": {
            "home": "Ctrl+H",
            "settings": "Ctrl+,",
            "quit": "Ctrl+Q",
            "toggle_tray": "Escape",
        },
        "type": dict,
        "desc": "快捷键绑定（修改后需重启生效）",
    },
    "high_speed": {
        "default": False,
        "type": bool,
        "desc": "高速模式：提高并发，加载更快但有一定风控风险",
    },
    "proxy": {
        "default": {"enabled": False, "http": "", "https": ""},
        "type": dict,
        "desc": "代理设置",
    },
}


def get_defaults() -> dict:
    """返回所有配置项的默认值"""
    return {key: meta["default"] for key, meta in SETTINGS_SCHEMA.items()}


def validate_value(key: str, value: Any) -> list[str]:
    """
    校验单个配置值，返回错误消息列表（空列表 = 通过）。

    用法:
        errors = validate_value("font_size", 5)
        if errors: ...
    """
    if key not in SETTINGS_SCHEMA:
        return [f"未知配置项: {key}"]

    meta = SETTINGS_SCHEMA[key]
    expected_type = meta.get("type")

    # 类型检查
    if expected_type is not None and not isinstance(value, expected_type):
        return [f"{key}: 期望 {expected_type.__name__}, 实际 {type(value).__name__}"]

    # 枚举检查
    if "enum" in meta and value not in meta["enum"]:
        return [f"{key}: 期望 {meta['enum']} 之一, 实际 '{value}'"]

    # 范围检查
    if isinstance(value, (int, float)):
        if "min" in meta and value < meta["min"]:
            return [f"{key}: 最小 {meta['min']}, 实际 {value}"]
        if "max" in meta and value > meta["max"]:
            return [f"{key}: 最大 {meta['max']}, 实际 {value}"]

    return []


def validate_all(data: dict) -> list[str]:
    """校验全部数据，返回所有错误"""
    errors = []
    for key in data:
        errors.extend(validate_value(key, data[key]))
    return errors


# ── 迁移链 ──────────────────────────────────────────────
# 每个版本号对应一个迁移函数，接收旧数据返回新数据
MIGRATIONS: dict[int, callable] = {
    # 1: lambda d: d,  # v1 = 初始版本，无需迁移
    # 2: lambda d: {**d, "proxy": get_defaults()["proxy"]},
}
