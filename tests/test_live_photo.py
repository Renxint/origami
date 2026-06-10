# -*- coding: utf-8 -*-
"""测试实况识别 — 拉取 vlllv 主页并打印每个作品的类型检测结果"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from src.api import DouyinAPI
from src.cookie import load_cookie
from src.utils import parse_sec_user_id, pick_best_video_url, clean_name

cookie = load_cookie()
if not cookie or "sessionid=" not in cookie:
    print("[FAIL] 未登录，请先登录")
    sys.exit(1)

api = DouyinAPI(cookie_string=cookie)

# 解析 vlllv 的 sec_uid
raw_url = "https://www.iesdouyin.com/share/user/MS4wLjABAAAAzuZa5e-KyfaOTDZIrychDHQ2bqJH9NYnQd9yb3WslPw"
sec_uid = parse_sec_user_id(raw_url)
print(f"sec_uid: {sec_uid[:30]}...")

# 获取用户信息
profile = api.get_user_profile(sec_uid)
print(f"用户: {profile.get('nickname', '?')}  作品: {profile.get('aweme_count', 0)}")

# 翻页获取所有作品
all_posts = []
cursor = 0
for page in range(1, 20):
    data = api.get_user_posts(sec_uid, max_cursor=cursor, count=18)
    items = data.get("aweme_list", [])
    if not items:
        break
    all_posts.extend(items)
    cursor = data.get("max_cursor", 0)
    if not data.get("has_more", 0):
        break
    import time
    time.sleep(0.3)

print(f"\n共获取 {len(all_posts)} 个作品\n")

# 逐作品分析类型
live_count = 0
gallery_count = 0
video_count = 0
unknown_count = 0

for i, aw in enumerate(all_posts):
    aweme_id = aw.get("aweme_id", "")
    desc = clean_name(aw.get("desc", ""), 40) or "(无描述)"
    video = aw.get("video")
    images = aw.get("images") or []
    is_live_flag = aw.get("is_live_photo", False)
    is_top = aw.get("is_top", 0)

    # 检测逻辑（和 batch_page.py 一致）
    is_live = is_live_flag
    if not is_live and bool(video) and bool(images):
        has_play = (
            (video or {}).get("play_addr")
            or (video or {}).get("play_addr_live_photo")
            or (video or {}).get("bit_rate")
        )
        if has_play:
            is_live = True

    is_pure_video = bool(video) and not images and not is_live
    is_gallery = bool(images) and not is_live

    # 实况详情：检查能否获取完整 video
    detail_ok = False
    if is_live:
        try:
            from src.platforms.douyin import DouyinAdapter
            adapter = DouyinAdapter()
            detail = adapter._call_sign_server(aweme_id, cookie)
            lv_video = detail.get("video") or video or {}
            lv_url = pick_best_video_url(lv_video) or ""
            if not lv_url:
                lv_url = ((lv_video.get("play_addr_live_photo") or {}).get("url_list") or [""])[0]
            if not lv_url:
                lv_url = ((lv_video.get("play_addr") or {}).get("url_list") or [""])[0]
            detail_ok = bool(lv_url)
        except Exception as e:
            print(f"    签名失败: {e}")

    # 综合类型
    if is_pure_video:
        typ = "视频"
        video_count += 1
    elif is_live:
        typ = "实况" + (" [视频可获取]" if detail_ok else " [视频缺失]")
        live_count += 1
    elif is_gallery:
        typ = f"图集({len(images)}图)"
        gallery_count += 1
    else:
        typ = "未知"
        unknown_count += 1

    top_mark = " [置顶]" if is_top else ""
    video_keys = list(video.keys())[:8] if video else []
    print(f"{i+1:2d}. [{typ}]{top_mark} {desc}")
    print(f"    aweme_id={aweme_id}  is_live_photo={is_live_flag}  images={len(images)}  video_keys={video_keys}")

print(f"\n===== 统计 =====")
print(f"实况: {live_count}  图集: {gallery_count}  视频: {video_count}  未知: {unknown_count}")
