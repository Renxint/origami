# -*- coding: utf-8 -*-
"""测试单视频可获取的信息：统计 + 评论"""
import sys, os, json, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from src.api import DouyinAPI
from src.cookie import load_cookie

cookie = load_cookie()
api = DouyinAPI(cookie_string=cookie)

# 你的短链里的一个视频 aweme_id
aweme_id = "7641165928193551078"  # 替换为实际测试的视频ID
print(f"测试 aweme_id: {aweme_id}")

# 1. 获取 aweme_detail
print("\n=== 视频详情 ===")
url = (f"https://www.douyin.com/aweme/v1/web/aweme/detail/?"
       f"aweme_id={aweme_id}&device_platform=webapp&aid=6383"
       f"&version_code=290100&version_name=29.1.0&cookie_enabled=true&pc_client_type=1")
resp = api.session.get(url, timeout=15)
data = resp.json()
detail = data.get("aweme_detail", {})
print(f"status_code: {data.get('status_code')}")

# 统计
stats = detail.get("statistics", {})
print(f"\n--- statistics ---")
for k, v in stats.items():
    print(f"  {k}: {v}")

# 作者
author = detail.get("author", {})
print(f"\n--- author ---")
print(f"  nickname: {author.get('nickname')}")
print(f"  unique_id: {author.get('unique_id')}")
print(f"  follower_count: {author.get('follower_count')}")

# 评论区相关字段
print(f"\n--- 评论相关顶层字段 ---")
for k in sorted(detail.keys()):
    if "comment" in k.lower():
        print(f"  {k}: {type(detail[k]).__name__} = {detail[k] if isinstance(detail[k], (str, int, bool)) else '...'}")

# 2. 评论列表
print(f"\n=== 评论列表 (前10条) ===")
comment_url = (f"https://www.douyin.com/aweme/v1/web/comment/list/?"
               f"aweme_id={aweme_id}&cursor=0&count=10"
               f"&device_platform=webapp&aid=6383"
               f"&version_code=290100&version_name=29.1.0&cookie_enabled=true&pc_client_type=1")
try:
    r = api.session.get(comment_url, timeout=15)
    cdata = r.json()
    print(f"status_code: {cdata.get('status_code')}")
    comments = cdata.get("comments") or []
    total = cdata.get("total", 0)
    print(f"评论总数: {total}, 本页: {len(comments)}")
    for i, c in enumerate(comments[:5]):
        user = c.get("user", {})
        text = c.get("text", "")
        like = c.get("digg_count", 0)
        reply = c.get("reply_comment_total", 0)
        print(f"  [{i+1}] {user.get('nickname','?')}: {text[:60]}  (赞{like} 回复{reply})")
    # 子评论
    if comments:
        sub = comments[0].get("reply_comment") or []
        print(f"\n  第1条的子评论({len(sub)}条):")
        for sc in sub[:3]:
            su = sc.get("user", {})
            print(f"    {su.get('nickname','?')}: {sc.get('text','')[:60]}")
except Exception as e:
    print(f"评论列表请求失败: {e}")

# 3. 统计字段完整性
print(f"\n=== 可获取的统计字段 ===")
known = {
    "digg_count": "点赞",
    "comment_count": "评论数",
    "share_count": "分享数",
    "collect_count": "收藏数",
    "play_count": "播放数",
    "download_count": "下载数",
    "forward_count": "转发数",
    "whatsapp_share_count": "WhatsApp分享",
}
for k, label in known.items():
    val = stats.get(k)
    if val is not None:
        print(f"  [OK] {label}: {val}")
    else:
        print(f"  [--] {label}: 无")
