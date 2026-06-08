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

from src.environ import NODE_CMD, BASE_DIR, CREATE_NO_WINDOW, COOKIE_FILE

_API_SCRIPT = BASE_DIR / "sign-server" / "api-call.js"


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
    return _call_api(f"https://www.douyin.com/aweme/v1/web/favorite/post/?{params}")
