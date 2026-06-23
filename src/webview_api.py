# -*- coding: utf-8 -*-
"""
Origami v2 — 抖音 API 代理

通过 Playwright（真实 Chrome/Edge）调用抖音 API，替代 Node.js sign-server。
所有接口保持旧签名不变，上层调用方无需修改。
"""

import json
import time
from pathlib import Path

from src.environ import COOKIE_FILE, EXE_DIR, CREATE_NO_WINDOW
from src.signer import (
    get_signer, one_shot_fetch,
    BrowserFinder, _load_cookie_raw,
    _debug_log,
)

# ═══════════════════════════════════════════════════════════
# 内部工具
# ═══════════════════════════════════════════════════════════

def _call_api(url: str, timeout: float = 20) -> dict:
    """通过 Playwright 浏览器调用 API（替代旧 Node.js api-call.js）"""
    if not COOKIE_FILE.exists():
        return {"_error": "not_logged_in"}

    signer = get_signer()
    result = signer.call("call", url=url)
    if "_error" in result and "unavailable" in str(result.get("_error", "")):
        # 回退到 one-shot
        cookie = _load_cookie_raw()
        if not cookie:
            return {"_error": "no_cookie"}
        browser_path = BrowserFinder.find()
        if not browser_path:
            return {"_error": "no_browser_found"}
        from src.signer import StealthBrowser
        browser = StealthBrowser(browser_path, headless=True)
        try:
            browser.start(cookie_str=cookie)
            return browser.call_api(url)
        except Exception as e:
            return {"_error": str(e)}
        finally:
            browser.close()
    return result


def _call_api_signed(cursor: int = 0, timeout: float = 60) -> dict:
    """收藏列表 API（替代旧 Node.js api-signed.js）"""
    signer = get_signer()
    result = signer.call("call", url=(
        f"https://www.douyin.com/aweme/v1/web/aweme/favorite/list/item/?"
        f"cursor={cursor}&count=18"
        f"&device_platform=webapp&aid=6383&version_code=290100"
        f"&version_name=29.1.0&cookie_enabled=true"
    ))
    return result


# ═══════════════════════════════════════════════════════════
# 常驻服务管理（线程安全）
# ═══════════════════════════════════════════════════════════

def _is_server_ready():
    return get_signer().is_ready()


def _kill_orphan_nodes():
    """启动时清理残留 Node 进程（v2: 无 Node，仅保留兼容接口）"""
    pass


def _kill_sign_port():
    """清理端口（v2: 无 Node 监听端口，仅保留兼容接口）"""
    pass


def start_server():
    """启动常驻 Playwright 浏览器服务（对齐旧 start_server）"""
    _debug_log("=== start_server() called (playwright) ===")

    signer = get_signer()
    if signer.is_ready():
        _debug_log("fast path: signer already running")
        return True

    cookie = _load_cookie_raw()
    return signer.start(cookie_str=cookie)


def stop_server():
    """关闭常驻浏览器（对齐旧 stop_server）"""
    get_signer().stop()


def call_server(endpoint: str, **params) -> dict:
    """调用常驻服务端点（对齐旧 call_server，内置懒启动）"""
    signer = get_signer()

    for attempt in (1, 2, 3):
        if not signer.is_ready():
            _debug_log(f"attempt {attempt}: not ready, starting...")
            cookie = _load_cookie_raw()
            signer.start(cookie_str=cookie)
            # 等浏览器就绪
            for i in range(33):
                if signer.is_ready():
                    _debug_log(f"ready after {i+1} checks")
                    break
                time.sleep(1 if i < 5 else 2)
            else:
                _debug_log("WARN: signer not ready after 60s")
                if attempt < 3:
                    signer.stop()
                    time.sleep(1)
                    continue

        result = signer.call(endpoint, **params)
        if "_error" in result:
            _debug_log(f"signer error: {result['_error'][:200]}")
            if attempt < 3:
                _debug_log(f"retry {attempt+1}/3...")
                time.sleep(1)
                continue
        return result

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
    for key in ("avatar_300_url", "avatar_url", "avatar_medium_url", "avatar_thumb_url"):
        val = user.get(key, "")
        if isinstance(val, dict):
            val = (val.get("url_list") or [""])[0]
        if val and isinstance(val, str) and val.startswith("http"):
            return val
    return ""


def get_user_likes(sec_uid: str, max_cursor: int = 0, count: int = 18) -> dict:
    params = (f"sec_user_id={sec_uid}&max_cursor={max_cursor}&count={count}"
              f"&aid=6383&device_platform=webapp&version_code=290100"
              f"&version_name=29.1.0&cookie_enabled=true")
    return _call_api(f"https://www.douyin.com/aweme/v1/web/aweme/favorite/?{params}")


def get_favorite_collections(cursor: int = 0) -> dict:
    """获取收藏夹列表（v2: 通过 playwright 浏览器）"""
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
