# -*- coding: utf-8 -*-
"""
Origami v2 — 抖音 API 代理

通过独立线程的 Playwright HTTP Daemon 调用抖音 API。
架构与旧版 Node.js sign-server 完全相同：Python → HTTP → Daemon → 浏览器。
这样 playwright 的浏览器完全隔离在独立线程中，不碰 Qt 的事件循环。
"""

import os
import time
import requests as _req

from src.environ import COOKIE_FILE, EXE_DIR, CREATE_NO_WINDOW
from src.signer import (
    get_signer, one_shot_fetch,
    BrowserFinder, _load_cookie_raw,
    _debug_log,
)

# ═══════════════════════════════════════════════════════════
# 内部工具
# ═══════════════════════════════════════════════════════════

def _daemon_url() -> str:
    return get_signer().url


def _call_api(url: str, timeout: float = 20) -> dict:
    """通过 HTTP Daemon 调用 API（替代旧 Node.js api-call.js）"""
    if not COOKIE_FILE.exists():
        return {"_error": "not_logged_in"}

    signer = get_signer()
    if signer.is_ready():
        try:
            r = _req.post(
                f"{_daemon_url()}/call?url={url}",
                timeout=timeout)
            return r.json()
        except Exception as e:
            _debug_log(f"_call_api HTTP failed: {e}")

    # 回退到 one-shot
    cookie = _load_cookie_raw()
    if not cookie:
        return {"_error": "no_cookie"}
    return one_shot_fetch(url.split("aweme_id=")[-1].split("&")[0]
                         if "aweme_id" in url else "", cookie)


def _call_api_signed(cursor: int = 0, timeout: float = 60) -> dict:
    """收藏列表 API（替代旧 Node.js api-signed.js）"""
    url = (f"https://www.douyin.com/aweme/v1/web/aweme/favorite/list/item/?"
           f"cursor={cursor}&count=18"
           f"&device_platform=webapp&aid=6383&version_code=290100"
           f"&version_name=29.1.0&cookie_enabled=true")
    return _call_api(url, timeout=timeout)


# ═══════════════════════════════════════════════════════════
# 常驻服务管理
# ═══════════════════════════════════════════════════════════

def _is_server_ready():
    return get_signer().is_ready()


def _kill_orphan_nodes():
    """v2: 无 Node 进程，仅保留兼容接口"""
    pass


def _kill_sign_port():
    """v2: 无 Node 端口，仅保留兼容接口"""
    pass


def start_server():
    """启动 Playwright HTTP Daemon（独立线程，不在 Qt 线程内）"""
    _debug_log("=== start_server() called (playwright daemon) ===")

    signer = get_signer()
    if signer.is_ready():
        _debug_log("fast path: daemon already running")
        return True

    _kill_orphan_nodes()

    cookie = _load_cookie_raw()
    ok = signer.start(cookie_str=cookie)
    _debug_log(f"daemon start: {ok}")
    return ok


def stop_server():
    """关闭 HTTP Daemon + 浏览器"""
    get_signer().stop()


def call_server(endpoint: str, **params) -> dict:
    """调用常驻服务端点（对齐旧 call_server，内置懒启动+重试）"""
    signer = get_signer()

    for attempt in (1, 2, 3):
        if not signer.is_ready():
            _debug_log(f"call_server attempt {attempt}: daemon not ready, starting...")
            cookie = _load_cookie_raw()
            signer.start(cookie_str=cookie)
            # 等 daemon 就绪
            for i in range(40):
                if signer.is_ready():
                    _debug_log(f"daemon ready after {i+1} checks")
                    break
                time.sleep(1 if i < 5 else 2)
            else:
                _debug_log("WARN: daemon not ready after 60s")
                if attempt < 3:
                    signer.stop()
                    time.sleep(1)
                    continue
                return {"_error": "sign_server_timeout"}

        try:
            if endpoint == "video":
                aweme_id = params.get("aweme_id", "")
                r = _req.post(
                    f"{_daemon_url()}/video?aweme_id={aweme_id}",
                    timeout=60)
                result = r.json()
            elif endpoint == "call":
                url = params.get("url", "")
                r = _req.post(
                    f"{_daemon_url()}/call?url={url}",
                    timeout=30)
                result = r.json()
            else:
                return {"_error": f"unknown endpoint: {endpoint}"}

            if "_error" in result:
                _debug_log(f"daemon error: {result['_error'][:200]}")
                if "browser" in str(result.get("_error", "")).lower() and attempt < 3:
                    _debug_log(f"retry {attempt+1}/3...")
                    signer.stop()
                    time.sleep(2)
                    continue
            return result

        except Exception as e:
            _debug_log(f"call_server HTTP failed: {e}")
            if attempt < 3:
                _debug_log(f"retry {attempt+1}/3...")
                signer.stop()
                time.sleep(1)
                continue
            return {"_error": str(e)}

    return {"_error": "sign_server_connection_failed"}


# ═══════════════════════════════════════════════════════════
# 公共 API（签名与旧接口完全一致）
# ═══════════════════════════════════════════════════════════

def get_user_posts(sec_uid: str, max_cursor: int = 0, count: int = 18) -> dict:
    params = (f"sec_user_id={sec_uid}&max_cursor={max_cursor}&count={count}"
              f"&aid=6383&device_platform=webapp&version_code=290100"
              f"&version_name=29.1.0&cookie_enabled=true")
    return _call_api(f"https://www.douyin.com/aweme/v1/web/aweme/post/?{params}")


def get_user_profile(sec_uid: str) -> dict:
    raw = _call_api(
        f"https://www.douyin.com/aweme/v1/web/user/profile/other/"
        f"?sec_user_id={sec_uid}&device_platform=webapp&aid=6383"
        f"&version_code=290100&version_name=29.1.0"
    )
    user = raw.get("user", {})
    return {
        "nickname": user.get("nickname", ""),
        "unique_id": user.get("unique_id", ""),
        "uid": user.get("uid", ""),
        "sec_uid": user.get("sec_uid", ""),
        "desc": user.get("signature", ""),
        "aweme_count": user.get("aweme_count", 0),
        "follower_count": user.get("follower_count", 0),
        "following_count": user.get("following_count", 0),
        "favoriting_count": user.get("favoriting_count", 0),
        "total_favorited": user.get("total_favorited", 0),
        "avatar_url": _get_avatar(user),
        "gender": user.get("gender", 0),
        "country": user.get("country", ""),
        "province": user.get("province", ""),
        "city": user.get("city", ""),
        "district": user.get("district", ""),
        "school": user.get("school_name", ""),
        "age": user.get("user_age", -1),
        "custom_verify": user.get("custom_verify", ""),
        "enterprise_verify_reason": user.get("enterprise_verify_reason", ""),
    }


def _get_avatar(user: dict) -> str:
    for key in ("avatar_larger", "avatar_300x300", "avatar_168x168",
                "avatar_medium", "avatar_thumb",
                "avatar_300_url", "avatar_url", "avatar_medium_url", "avatar_thumb_url"):
        val = user.get(key, "")
        if isinstance(val, dict):
            val = (val.get("url_list") or [""])[0]
        if isinstance(val, (list, tuple)):
            val = val[0] if val else ""
        if val and isinstance(val, str) and val.startswith("http"):
            return val
    return ""


def get_user_likes(sec_uid: str, max_cursor: int = 0, count: int = 18) -> dict:
    params = (f"sec_user_id={sec_uid}&max_cursor={max_cursor}&count={count}"
              f"&aid=6383&device_platform=webapp&version_code=290100"
              f"&version_name=29.1.0&cookie_enabled=true")
    return _call_api(f"https://www.douyin.com/aweme/v1/web/aweme/favorite/?{params}")


def get_favorite_collections(cursor: int = 0) -> dict:
    return _call_api(
        f"https://www.douyin.com/aweme/v1/web/favorite/list/?"
        f"cursor={cursor}&count=20"
        f"&device_platform=webapp&aid=6383&version_code=290100"
        f"&version_name=29.1.0&cookie_enabled=true"
    )


def get_favorite_videos(max_cursor: int = 0, count: int = 18) -> dict:
    params = (f"max_cursor={max_cursor}&count={count}"
              f"&aid=6383&device_platform=webapp&version_code=290100"
              f"&version_name=29.1.0&cookie_enabled=true"
              f"&media_type=4")
    return _call_api(
        f"https://www.douyin.com/aweme/v1/web/aweme/favorite/?{params}",
        timeout=30)


def get_favorite_items(fav_id: str, max_cursor: int = 0,
                       count: int = 18) -> dict:
    params = (f"favorite_id={fav_id}&max_cursor={max_cursor}&count={count}"
              f"&aid=6383&device_platform=webapp&version_code=290100"
              f"&version_name=29.1.0&cookie_enabled=true")
    return _call_api(
        f"https://www.douyin.com/aweme/v1/web/favorite/list/item/?{params}")
