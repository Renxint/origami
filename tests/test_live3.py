# -*- coding: utf-8 -*-
"""测试第3个作品（实况）的完整视频数据获取"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from src.api import DouyinAPI
from src.cookie import load_cookie
from src.utils import parse_sec_user_id, pick_best_video_url, clean_name

cookie = load_cookie()
api = DouyinAPI(cookie_string=cookie)
sec_uid = parse_sec_user_id(
    "https://www.iesdouyin.com/share/user/MS4wLjABAAAAzuZa5e-KyfaOTDZIrychDHQ2bqJH9NYnQd9yb3WslPw"
)

# 拉取前几页，取第3个作品
all_posts = []
cursor = 0
for page in range(1, 5):
    data = api.get_user_posts(sec_uid, max_cursor=cursor, count=18)
    items = data.get("aweme_list", [])
    if not items: break
    all_posts.extend(items)
    cursor = data.get("max_cursor", 0)
    if not data.get("has_more", 0): break
    import time; time.sleep(0.3)

aw = all_posts[2]  # 第3个（0-indexed）
aweme_id = aw.get("aweme_id", "")
desc = aw.get("desc", "")
media_type = aw.get("media_type", "?")
is_live_photo = aw.get("is_live_photo", False)
images = aw.get("images") or []
video = aw.get("video") or {}

print(f"作品: {desc}")
print(f"aweme_id: {aweme_id}")
print(f"media_type: {media_type}  is_live_photo: {is_live_photo}")
print(f"images: {len(images)} 张")
print(f"video keys: {sorted(video.keys())}")
print()

# 检查 video 里的关键字段
for key in ("play_addr", "play_addr_live_photo", "bit_rate", "cover", "origin_cover", "dynamic_cover", "duration"):
    val = video.get(key)
    if key in ("play_addr", "play_addr_live_photo", "cover", "origin_cover", "dynamic_cover"):
        urls = (val or {}).get("url_list", [])
        print(f"  video.{key}: {len(urls)} urls, first={urls[0][:80] if urls else 'EMPTY'}")
    elif key == "bit_rate":
        brs = val or []
        print(f"  video.bit_rate: {len(brs)} entries")
        for br in brs[:3]:
            br_urls = (br.get("play_addr") or {}).get("url_list", [])
            print(f"    bit_rate={br.get('bit_rate','?')} urls={len(br_urls)}")
    else:
        print(f"  video.{key}: {val}")

print()

# 检查每个 image 是否包含 live_photo 数据
print("--- 每张图片的实况数据 ---")
for j, img in enumerate(images):
    is_live_img = img.get("live_photo_type", 0)
    img_video = img.get("video") or {}
    img_urls = img.get("url_list", [])
    print(f"  [{j}] live_photo_type={is_live_img}  urls={len(img_urls)}  video_keys={sorted(img_video.keys()) if img_video else 'None'}")
    if img_video:
        for vk in ("play_addr", "play_addr_live_photo", "bit_rate"):
            vv = img_video.get(vk)
            if vv:
                vu = (vv.get("url_list") or [""])[0] if isinstance(vv, dict) else str(vv)[:80]
                print(f"       {vk}: {vu[:80]}")

print()

# === 用 sign-server 获取完整详情 ===
print("--- sign-server 获取详情 ---")
try:
    from src.platforms.douyin import DouyinAdapter
    adapter = DouyinAdapter()
    detail = adapter._call_sign_server(aweme_id, cookie)
    if detail.get("_error"):
        print(f"  FAIL: {detail['_error']}")
    else:
        dv = detail.get("video") or {}
        print(f"  detail.video keys: {sorted(dv.keys())}")
        for key in ("play_addr", "play_addr_live_photo", "bit_rate"):
            val = dv.get(key)
            if key in ("play_addr", "play_addr_live_photo"):
                urls = (val or {}).get("url_list", [])
                print(f"  detail.video.{key}: {len(urls)} urls, first={urls[0][:100] if urls else 'EMPTY'}")
            elif key == "bit_rate":
                brs = val or []
                print(f"  detail.video.bit_rate: {len(brs)} entries")
                for br in brs[:3]:
                    br_urls = (br.get("play_addr") or {}).get("url_list", [])
                    print(f"    br={br.get('bit_rate','?')} urls={len(br_urls)} first={br_urls[0][:80] if br_urls else 'EMPTY'}")

        # 提取可下载的 URL
        lv_url = pick_best_video_url(dv) or ""
        if not lv_url:
            lv_url = ((dv.get("play_addr_live_photo") or {}).get("url_list") or [""])[0]
        if not lv_url:
            lv_url = ((dv.get("play_addr") or {}).get("url_list") or [""])[0]
        print(f"\n  最终提取: lv_url={'OK' if lv_url else 'EMPTY'}")
        if lv_url:
            print(f"  {lv_url[:120]}")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()

# === 检查每个 image 的 live_photo 数据（sign-server 返回的 detail 里） ===
print("\n--- detail 中的 images 实况数据 ---")
dimgs = detail.get("images") or []
for j, img in enumerate(dimgs):
    is_live = img.get("live_photo_type", 0)
    iv = img.get("video") or {}
    print(f"  [{j}] live_photo_type={is_live}  video_keys={sorted(iv.keys()) if iv else 'None'}")
    if iv:
        plp = iv.get("play_addr_live_photo") or {}
        plp_urls = plp.get("url_list", [])
        print(f"       play_addr_live_photo: {plp_urls[0][:100] if plp_urls else 'EMPTY'}")
