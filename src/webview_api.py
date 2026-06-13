# -*- coding: utf-8 -*-
"""
Origami — 抖音 API 代理

通过 Node.js Puppeteer（真实 Chrome）调用抖音 API，
自动携带 a_bogus / msToken 等浏览器签名。

每次调用启动独立进程，用完即退，无生命周期问题。
"""

import json
import subprocess
import tempfile
from pathlib import Path

from src.environ import (NODE_CMD, BASE_DIR, CREATE_NO_WINDOW,
                        COOKIE_FILE, SIGN_SERVER_JS, SIGN_SERVER_URL)

_API_SCRIPT = BASE_DIR / "sign-server" / "api-call.js"
_SIGNED_SCRIPT = BASE_DIR / "sign-server" / "api-signed.js"


def _call_api(url: str, timeout: float = 20) -> dict:
    """通过 Puppeteer 调用 API，返回 JSON dict"""
    if not COOKIE_FILE.exists():
        return {"_error": "not_logged_in"}

    from src.cookie import load_cookie

    # 写一份明文 Cookie 供 Node.js 读取
    plain_cookie = load_cookie()
    if not plain_cookie:
        return {"_error": "no_cookie"}

    # 过滤空 name 的 Cookie
    clean = "; ".join(c for c in plain_cookie.split("; ") if "=" in c and c.split("=", 1)[0])

    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".txt"))
    tmp.write_text(clean, encoding="utf-8")

    try:
        result = subprocess.run(
            [NODE_CMD, str(_API_SCRIPT), str(tmp), url],
            capture_output=True, text=True, encoding='utf-8', timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        stdout = (result.stdout or "").strip()
        if result.returncode != 0 or not stdout:
            return {"_error": f"exit={result.returncode} err={result.stderr[:100]}"}
        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        return {"_error": "timeout"}
    except Exception as e:
        return {"_error": str(e)}
    finally:
        tmp.unlink(missing_ok=True)


def _call_api_signed(cursor: int = 0, timeout: float = 60) -> dict:
    """收藏列表 API（POST，SDK 签名）"""
    if not COOKIE_FILE.exists():
        return {"_error": "not_logged_in"}

    from src.cookie import load_cookie
    plain_cookie = load_cookie()
    if not plain_cookie:
        return {"_error": "no_cookie"}
    clean = "; ".join(c for c in plain_cookie.split("; ") if "=" in c and c.split("=", 1)[0])

    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".txt"))
    tmp.write_text(clean, encoding="utf-8")

    try:
        result = subprocess.run(
            [NODE_CMD, str(_SIGNED_SCRIPT), str(tmp), str(cursor)],
            capture_output=True, text=True, encoding='utf-8', timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        stdout = (result.stdout or "").strip()
        if result.returncode != 0 or not stdout:
            return {"_error": f"exit={result.returncode} err={(result.stderr or '')[:200]}"}
        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        return {"_error": "timeout"}
    except Exception as e:
        return {"_error": str(e)}
    finally:
        tmp.unlink(missing_ok=True)


# ── 常驻浏览器服务 ──
_server_process = None

def start_server():
    """启动常驻 Node 浏览器服务（软件启动时调用一次）"""
    global _server_process
    import subprocess, time
    try:
        r = __import__('requests').get(f"{SIGN_SERVER_URL}/health", timeout=2)
        if r.json().get('ok'):
            return True  # 已在运行
    except Exception:
        pass
    _server_process = subprocess.Popen(
        [NODE_CMD, str(SIGN_SERVER_JS)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )
    # 等待服务就绪
    for _ in range(30):
        try:
            r = __import__('requests').get(f"{SIGN_SERVER_URL}/health", timeout=1)
            if r.json().get('ok'):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def stop_server():
    """关闭常驻服务"""
    global _server_process
    if _server_process:
        _server_process.terminate()
        _server_process = None

def call_server(endpoint, **params):
    """调用常驻服务端点，返回 JSON"""
    import requests as _r
    url = f"{SIGN_SERVER_URL}/{endpoint}"
    try:
        r = _r.post(url, params=params, timeout=60)
        return r.json()
    except Exception as e:
        return {"_error": str(e)}


def get_user_posts(sec_uid: str, max_cursor: int = 0, count: int = 18) -> dict:
    params = (f"sec_user_id={sec_uid}&max_cursor={max_cursor}&count={count}"
              f"&aid=6383&device_platform=webapp&version_code=290100"
              f"&version_name=29.1.0&cookie_enabled=true")
    return _call_api(f"https://www.douyin.com/aweme/v1/web/aweme/post/?{params}")


def get_user_profile(sec_uid: str) -> dict:
    """获取用户信息，返回扁平化 dict"""
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
    """获取收藏→视频列表（导航 WebView + 拦截网络响应）"""
    from src.gui.dialogs.webview_login import WebViewLogin
    return WebViewLogin.api_call(cursor=cursor, timeout=30)


def get_favorite_videos(max_cursor: int = 0, count: int = 18) -> dict:
    """获取收藏的视频列表（翻页，Puppeteer）"""
    params = (f"max_cursor={max_cursor}&count={count}"
              f"&aid=6383&device_platform=webapp&version_code=290100"
              f"&version_name=29.1.0&cookie_enabled=true"
              f"&media_type=4")
    return _call_api(
        f"https://www.douyin.com/aweme/v1/web/aweme/favorite/?{params}",
        timeout=30)


def get_favorite_items(fav_id: str, max_cursor: int = 0,
                       count: int = 18) -> dict:
    """获取指定收藏夹的作品列表（Puppeteer）"""
    params = (f"favorite_id={fav_id}&max_cursor={max_cursor}&count={count}"
              f"&aid=6383&device_platform=webapp&version_code=290100"
              f"&version_name=29.1.0&cookie_enabled=true")
    return _call_api(
        f"https://www.douyin.com/aweme/v1/web/favorite/list/item/?{params}")
