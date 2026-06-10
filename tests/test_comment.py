# -*- coding: utf-8 -*-
"""测试评论区图片/表情包获取"""
import sys, os, json, re, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from src.cookie import load_cookie
from src.environ import USER_AGENT

# ── 1. 解析短链 → aweme_id ──
raw = "8.25 09/19 C@h.bn TlP:/ :3pm 聊天表情包 不来一套吗# 表情包 # 发给对象表情包 # 搞笑图片 # 沙雕表情包 # 抖音图文   https://v.douyin.com/tr61FTGjYXg/ 复制此链接，打开Dou音搜索，直接观看视频！"
m = re.search(r'https?://v\.douyin\.com/[A-Za-z0-9_\-/]+', raw)
short_url = m.group(0)
print(f"短链: {short_url}")

s = requests.Session()
s.headers.update({"User-Agent": USER_AGENT})
r = s.get(short_url, allow_redirects=True, timeout=15, stream=True)
r.close()
resolved = r.url
print(f"解析: {resolved}")

m2 = re.search(r'/(?:video|note)/(\d+)', resolved)
aweme_id = m2.group(1)
print(f"aweme_id: {aweme_id}")

# ── 2. Puppeteer 拉取评论 ──
fingerprint = {
    "aweme_id": aweme_id, "cursor": "0", "count": "20",
    "device_platform": "webapp", "aid": "6383", "channel": "channel_pc_web",
    "pc_client_type": "1", "version_code": "290100", "version_name": "29.1.0",
    "cookie_enabled": "true", "screen_width": "2560", "screen_height": "1440",
    "browser_language": "zh-CN", "browser_platform": "Win32",
    "browser_name": "Smart+Lenovo+Browser", "browser_version": "9.0.8.5161",
    "browser_online": "true", "engine_name": "Blink", "engine_version": "141.0.0.0",
    "os_name": "Windows", "os_version": "10", "cpu_core_num": "32",
    "device_memory": "8", "platform": "PC", "downlink": "10",
    "effective_type": "4g", "round_trip_time": "50",
}
query = "&".join(f"{k}={v}" for k, v in fingerprint.items())
api_url = f"https://www.douyin.com/aweme/v1/web/comment/list/?{query}"

print(f"\n=== Puppeteer 拉取评论 ===")
import src.webview_api as wapi
result = wapi._call_api(api_url, timeout=30)

if result.get("_error"):
    print(f"[FAIL] {result['_error']}")
    sys.exit(1)

comments = result.get("comments") or []
total = result.get("total", 0)
print(f"评论总数: {total}, 本页: {len(comments)}")

# ── 3. 逐条扫描图片/表情相关字段 ──
image_comments = []
for i, c in enumerate(comments):
    user = c.get("user", {})
    text = c.get("text", "")
    # 扫描所有可能含图片的字段
    img_fields = {}
    for key in c:
        val = c[key]
        if isinstance(val, dict):
            url_list = val.get("url_list") or val.get("urls")
            if url_list:
                img_fields[key] = url_list[:3]
        elif isinstance(val, list) and val:
            # 检查 list 中的 dict 是否含 url_list
            sub_imgs = {}
            for j, item in enumerate(val[:5]):
                if isinstance(item, dict):
                    ul = item.get("url_list") or item.get("urls")
                    if ul:
                        sub_imgs[f"{key}[{j}]"] = ul[:2]
            if sub_imgs:
                img_fields.update(sub_imgs)
    if img_fields:
        image_comments.append((i, c, img_fields))
        print(f"\n  [{i+1}] {user.get('nickname','?'):16s}: {text[:60]}")
        for fk, fv in img_fields.items():
            print(f"      字段 {fk}:")
            for url in fv:
                print(f"        {url[:120]}")

print(f"\n=== 含图片/表情的评论: {len(image_comments)}/{len(comments)} ===")

# ── 4. 保存完整原始数据（第1条评论展开所有字段）──
from pathlib import Path
out_dir = Path("data")
out_dir.mkdir(exist_ok=True)

if comments:
    # 展开第1条评论的所有 key
    first = comments[0]
    print(f"\n=== 第1条评论完整字段 ===")
    for k in sorted(first.keys()):
        v = first[k]
        t = type(v).__name__
        if isinstance(v, (str, int, float, bool)):
            print(f"  {k}: {v}  ({t})")
        elif isinstance(v, dict):
            print(f"  {k}: dict keys={list(v.keys())[:10]}  ({t})")
        elif isinstance(v, list):
            print(f"  {k}: list len={len(v)}  ({t})")
        elif v is None:
            print(f"  {k}: None")
        else:
            print(f"  {k}: {t}")

    # 查找所有评论中出现的图片URL
    print(f"\n=== 全局搜索评论中的图片URL ===")
    raw_str = json.dumps(comments, ensure_ascii=False)
    img_urls = re.findall(r'https?://[^"\s]+\.(?:jpg|jpeg|png|webp|gif|heic)[^"\s]*', raw_str, re.IGNORECASE)
    print(f"找到 {len(img_urls)} 个图片URL:")
    for u in list(set(img_urls))[:20]:
        print(f"  {u[:150]}")

    # 展示所有 sticker 和 image_list 内容
    print(f"\n=== 表情/图片评论汇总 ===")
    for i, c in enumerate(comments):
        sticker = c.get("sticker")
        img_list = c.get("image_list") or []
        ct = c.get("content_type")
        t = c.get("text", "")
        u = c.get("user", {}).get("nickname", "?")
        has_content = sticker or img_list
        if has_content:
            print(f"\n  [{i+1}] content_type={ct} {u}: {t[:60]}")
            if sticker:
                print(f"       sticker keys={list(sticker.keys())} id={sticker.get('id','?')}")
                for sk in sticker:
                    sv = sticker[sk]
                    if isinstance(sv, str) and sv.startswith("http"):
                        print(f"       sticker.{sk}: {sv[:120]}")
            if img_list:
                for j, img in enumerate(img_list):
                    urls = img.get("url_list", []) if isinstance(img, dict) else []
                    print(f"       image[{j}]: {len(urls)} urls")
                    for uu in urls[:3]:
                        print(f"         {uu[:120]}")
    total_media = sum(1 for c in comments if c.get("sticker") or c.get("image_list"))
    print(f"\n共 {total_media} 条含表情/图片的评论")

# 保存原始JSON
raw_file = out_dir / "comments_img_raw.json"
with open(raw_file, "w", encoding="utf-8") as f:
    json.dump({"comments": comments, "total": total}, f, ensure_ascii=False, indent=2)
print(f"\n[OK] 原始数据: {raw_file}")
