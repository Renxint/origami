# -*- coding: utf-8 -*-
"""
Origami — 抖音 API 客户端

Python requests + Cookie 直连，不依赖签名服务。

关键发现:
  - 不需要 a_bogus，不需要 msToken
  - 仅需 Cookie + 正确的 browser_name/browser_version + 设备指纹即可翻页
  - browser_name 必须匹配真实 UA (Smart+Lenovo+Browser, 而非 Chrome)
"""

import json
from pathlib import Path
from typing import Dict, Optional

import requests

from src.environ import USER_AGENT
from src.cookie import load_cookie

# ── 设备指纹（从真实浏览器提取，跨账号通用） ──────────────────
WEBID = "7385142668127356466"
VERIFY_FP = "verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD"
FP = "verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD"
UIFID = "7db62a7064f9afdec5c11ec3d692d7372ef41f2765cba0856d9e1b7b4940be6ed1b35a0f14230c327616b958a98d663b4443e89c625dc584c6b48e03ecc9c0ad"

TIMEOUT = 30


def _get_avatar(user: dict) -> str:
    """从 user 对象提取头像 URL

    抖音返回的 key 可能有两种格式:
      - 旧格式: avatar_300_url, avatar_url (url_list 嵌套)
      - 新格式: avatar_300x300, avatar_larger (直接字符串数组)
    """
    # 优先匹配新格式 (尺寸最大的在前)
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


class DouyinAPI:
    """抖音 API 客户端 — Cookie 直连方式"""

    def __init__(self, cookie_string: str = ""):
        if cookie_string:
            self.cookie = cookie_string
        else:
            self.cookie = self._load_cookie()

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Referer": "https://www.douyin.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cookie": self.cookie,
        })

    def _load_cookie(self) -> str:
        return load_cookie()

    @staticmethod
    def _build_post_params(sec_user_id: str, max_cursor: int = 0,
                           count: int = 18) -> Dict[str, str]:
        """构建 /aweme/v1/web/aweme/post/ 请求参数"""
        return {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "sec_user_id": sec_user_id,
            "max_cursor": str(max_cursor),
            "locate_query": "false",
            "show_live_replay_strategy": "1",
            "need_time_list": "0",
            "time_list_query": "0",
            "whale_cut_token": "",
            "cut_version": "1",
            "count": str(count),
            "publish_video_strategy_type": "2",
            "from_user_page": "1",
            "update_version_code": "170400",
            "pc_client_type": "1",
            "pc_libra_divert": "Windows",
            "support_h265": "1",
            "support_dash": "1",
            "cpu_core_num": "32",
            "version_code": "290100",
            "version_name": "29.1.0",
            "cookie_enabled": "true",
            "screen_width": "2560",
            "screen_height": "1440",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Smart+Lenovo+Browser",
            "browser_version": "9.0.8.5161",
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": "141.0.0.0",
            "os_name": "Windows",
            "os_version": "10",
            "device_memory": "8",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "round_trip_time": "50",
            "webid": WEBID,
            "uifid": UIFID,
            "verifyFp": VERIFY_FP,
            "fp": FP,
        }

    def check_cookie(self) -> bool:
        """校验 Cookie 是否有效"""
        try:
            resp = self.session.get(
                "https://www.douyin.com/aweme/v1/web/user/profile/other/"
                "?sec_user_id=MS4wLjABAAAAnsZ-gU2aYmYUiMq2a1dTwH0Bst9fK3s9mEpQnvVsosI"
                "&device_platform=webapp&aid=6383",
                timeout=10,
            )
            data = resp.json()
            return data.get("status_msg") != "blocked" and bool(data.get("user", {}))
        except Exception:
            return False

    def get_user_profile(self, sec_user_id: str) -> Dict:
        """获取用户资料"""
        url = (f"https://www.douyin.com/aweme/v1/web/user/profile/other/"
               f"?sec_user_id={sec_user_id}&device_platform=webapp&aid=6383"
               f"&version_code=290100&version_name=29.1.0")
        try:
            resp = self.session.get(url, timeout=TIMEOUT)
            data = resp.json()
            user = data.get("user", {})
            aweme_count = 0
            for src in (user, data):
                for key in ("aweme_count", "aweme_total", "max_aweme_count",
                            "total_post", "post_count", "item_count"):
                    val = src.get(key, None)
                    if isinstance(val, (int, float)) and val > 0:
                        aweme_count = int(val)
                        break
                if aweme_count > 0:
                    break
            return {
                "nickname": user.get("nickname", ""),
                "unique_id": user.get("unique_id", ""),
                "short_id": user.get("short_id", ""),
                "uid": user.get("uid", ""),
                "sec_uid": user.get("sec_uid", ""),
                "desc": user.get("desc", "") or user.get("signature", ""),
                "aweme_count": aweme_count,
                "follower_count": user.get("follower_count", 0) or 0,
                "following_count": user.get("following_count", 0) or 0,
                "favoriting_count": user.get("favoriting_count", 0) or 0,
                "total_favorited": user.get("total_favorited", 0) or 0,
                "country": user.get("country", ""),
                "province": user.get("province", ""),
                "city": user.get("city", ""),
                "district": user.get("district", ""),
                "school": user.get("school", ""),
                "age": user.get("age", ""),
                "gender": user.get("gender", ""),
                "custom_verify": user.get("custom_verify", ""),
                "enterprise_verify_reason": user.get("enterprise_verify_reason", ""),
                "avatar_url": _get_avatar(user),
            }
        except Exception:
            return {}

    def get_user_posts(self, sec_user_id: str, max_cursor: int = 0,
                       count: int = 18) -> Dict:
        """获取用户作品列表（翻页）"""
        params = self._build_post_params(sec_user_id, max_cursor, count)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"https://www.douyin.com/aweme/v1/web/aweme/post/?{query}"
        try:
            resp = self.session.get(url, timeout=TIMEOUT)
            return resp.json()
        except Exception:
            return {}

    def get_user_likes(self, sec_user_id: str, max_cursor: int = 0,
                       count: int = 18) -> Dict:
        """获取用户喜欢列表（翻页）

        端点: /aweme/v1/web/favorite/post/
        复用设备指纹参数，不需要签名。
        返回结构与 get_user_posts 相同（含 aweme_list, has_more, max_cursor）。
        """
        params = self._build_post_params(sec_user_id, max_cursor, count)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"https://www.douyin.com/aweme/v1/web/aweme/favorite/?{query}"
        try:
            resp = self.session.get(url, timeout=TIMEOUT)
            return resp.json()
        except Exception:
            return {}

    def get_own_sec_uid(self) -> str:
        """获取当前登录用户的 sec_uid

        方案:
          1. 尝试 /aweme/v1/web/user/profile/self/ 获取自己资料
          2. 失败则从 Cookie 中解析 uid 特征

        Returns:
            sec_uid 字符串，获取失败返回空字符串
        """
        # 方案1: self profile endpoint
        try:
            url = ("https://www.douyin.com/aweme/v1/web/user/profile/self/"
                   "?device_platform=webapp&aid=6383"
                   "&version_code=290100&version_name=29.1.0")
            resp = self.session.get(url, timeout=TIMEOUT)
            data = resp.json()
            user = data.get("user", {})
            sec_uid = user.get("sec_uid", "")
            if sec_uid:
                return sec_uid
        except Exception:
            pass

        # 方案2: 从 Cookie 中提取 uid，构造 sec_uid
        # 抖音 sec_uid 格式: MS4wLjAB{base64(uid)}
        try:
            import re
            import base64
            # 尝试从 Cookie 中找 uid
            match = re.search(r'(?:^|;\s*)uid=(\d+)', self.cookie)
            if match:
                uid = match.group(1)
                # 抖音 sec_uid 前缀
                encoded = base64.b64encode(
                    f'{{"uid":"{uid}","sec_uid":""}}'.encode()
                ).decode()
                # 实际 sec_uid 格式通常为 MS4wLjAB...
                # 尝试通过 profile API 用已知测试 ID 回推
                pass
        except Exception:
            pass

        return ""
