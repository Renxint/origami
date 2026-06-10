# -*- coding: utf-8 -*-
"""测试：获取头像 + 喜欢总数（增强诊断版）"""

import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from src.api import DouyinAPI
from src.cookie import load_cookie
import requests

cookie = load_cookie()
if not cookie:
    print("[FAIL] 没有 Cookie，请先登录")
    sys.exit(1)

api = DouyinAPI(cookie_string=cookie)

# ── 1. 获取自己的 sec_uid ──
print("1. 获取 sec_uid...")
sec_uid = api.get_own_sec_uid()
print(f"   sec_uid: {sec_uid}")

# 备用
if not sec_uid:
    r = api.session.get("https://www.douyin.com/", timeout=15)
    import re
    m = re.search(r'"sec_uid":"(MS4wLjAB[A-Za-z0-9_\-]+)"', r.text)
    if m:
        sec_uid = m.group(1)
        print(f"   从首页提取: {sec_uid[:30]}...")

if not sec_uid:
    print("[FAIL] 拿不到 sec_uid")
    sys.exit(1)

# ── 2. 获取原始用户数据（不经过 _get_avatar 过滤）──
print("\n2. 获取原始 user 对象...")
url = f"https://www.douyin.com/aweme/v1/web/user/profile/other/?sec_user_id={sec_uid}&device_platform=webapp&aid=6383&version_code=290100&version_name=29.1.0"
resp = api.session.get(url, timeout=30)
raw = resp.json()
user = raw.get("user", {})

# 保存原始 JSON 看看有什么
Path("data/test_user_raw.json").write_text(
    json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"   原始数据已保存: data/test_user_raw.json")

# 列出 user 对象里所有以 avatar 开头的 key
avatar_keys = [k for k in user.keys() if "avatar" in k.lower()]
print(f"   avatar 相关 key: {avatar_keys}")
if avatar_keys:
    for k in avatar_keys:
        val = user.get(k, "")
        if isinstance(val, dict):
            val = val.get("url_list", val)
        print(f"     {k}: {str(val)[:120]}")

# ── 3. 头像下载 ──
print("\n3. 尝试下载头像...")
from src.api import _get_avatar
avatar_url = _get_avatar(user)
if avatar_url:
    print(f"   URL: {avatar_url}")
    r = requests.get(avatar_url, headers={"User-Agent": api.session.headers["User-Agent"]}, timeout=30)
    Path("data/test_avatar.jpg").write_bytes(r.content)
    print(f"   [OK] data/test_avatar.jpg ({len(r.content)/1024:.1f} KB)")
else:
    print("   _get_avatar 返回空，尝试从所有 url_list 字段中找...")
    # 暴力搜索：所有包含 url_list 的字段
    def find_urls(obj, depth=0):
        if depth > 5 or obj is None:
            return []
        if isinstance(obj, str) and obj.startswith("http") and ("jpeg" in obj.lower() or "jpg" in obj.lower() or "png" in obj.lower() or "webp" in obj.lower()):
            return [obj]
        if isinstance(obj, dict):
            result = []
            if "url_list" in obj:
                result.extend([u for u in obj["url_list"] if isinstance(u, str)])
            for v in obj.values():
                result.extend(find_urls(v, depth+1))
            return result
        if isinstance(obj, list):
            result = []
            for item in obj:
                result.extend(find_urls(item, depth+1))
            return result
        return []
    image_urls = find_urls(user)
    print(f"   找到 {len(image_urls)} 个图片URL")
    for u in image_urls[:5]:
        print(f"     {u[:120]}")

# ── 4. 喜欢列表 ──
print("\n4. 翻页获取喜欢列表...")
total = 0
cursor = 0
page = 0
while page < 100:
    data = api.get_user_likes(sec_uid, max_cursor=cursor, count=18)
    items = data.get("aweme_list", [])
    status = data.get("status_code", "?")
    status_msg = data.get("status_msg", "")

    if page == 0:
        print(f"   API返回: status_code={status}, status_msg={status_msg}")

    if not items:
        if status_msg and "block" not in status_msg.lower() and page == 0:
            # 试试 webview_api 的 Puppeteer 版本
            print("   HTTP 方式返回空，尝试 Puppeteer 版本...")
            try:
                from src.webview_api import get_user_likes as puppeteer_likes
                data2 = puppeteer_likes(sec_uid, max_cursor=0, count=5)
                items2 = data2.get("aweme_list", [])
                print(f"   Puppeteer 返回: {len(items2)} 条, status_code={data2.get('status_code')}")
                if data2.get("_error"):
                    print(f"   Puppeteer 错误: {data2['_error']}")
            except Exception as e:
                print(f"   Puppeteer 失败: {e}")
        break

    total += len(items)
    page += 1
    has_more = data.get("has_more", 0)
    cursor = data.get("max_cursor", 0)
    print(f"   第{page}页: +{len(items)}, 累计{total}, has_more={has_more}")

    if not has_more:
        break
    time.sleep(0.3)

print(f"\n===== 结果 =====")
print(f"  昵称: {user.get('nickname', '?')}")
print(f"  抖音号: {user.get('unique_id', '?')}")
print(f"  头像: {'data/test_avatar.jpg' if avatar_url else '未获取到'}")
print(f"  喜欢总数: {total} 条")
