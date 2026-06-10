# -*- coding: utf-8 -*-
"""对比前3个作品的 aweme 原始字段差异，输出到文件"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.api import DouyinAPI
from src.cookie import load_cookie
from src.utils import parse_sec_user_id, clean_name
from pathlib import Path

cookie = load_cookie()
api = DouyinAPI(cookie_string=cookie)
raw_url = "https://www.iesdouyin.com/share/user/MS4wLjABAAAAzuZa5e-KyfaOTDZIrychDHQ2bqJH9NYnQd9yb3WslPw"
sec_uid = parse_sec_user_id(raw_url)

# 只取前3页就够了
all_posts = []
cursor = 0
for page in range(1, 5):
    data = api.get_user_posts(sec_uid, max_cursor=cursor, count=18)
    items = data.get("aweme_list", [])
    if not items:
        break
    all_posts.extend(items)
    cursor = data.get("max_cursor", 0)
    if not data.get("has_more", 0):
        break
    import time; time.sleep(0.3)

# 取前3个
targets = all_posts[:3]
results = []
for i, aw in enumerate(targets):
    desc = clean_name(aw.get("desc", ""), 60) or "(无描述)"
    aweme_id = aw.get("aweme_id", "")
    is_live_photo = aw.get("is_live_photo", False)
    images = aw.get("images") or []
    video = aw.get("video") or {}
    music = aw.get("music") or {}

    # 摘取关键字段用于对比
    summary = {
        "index": i + 1,
        "desc": desc,
        "aweme_id": aweme_id,
        "is_live_photo": is_live_photo,
        "images_count": len(images),
        "video_keys": sorted(video.keys()) if video else [],
        "music_keys": sorted(music.keys()) if music else [],
        # 顶层字段
        "aweme_keys": sorted([k for k in aw.keys() if not k.startswith('_')]),
        # 关键差异字段
        "media_type": aw.get("media_type", "N/A"),
        "aweme_type": aw.get("aweme_type", "N/A"),
        "image_infos": aw.get("image_infos"),
    }
    results.append(summary)

    # 完整原始数据导出
    out_dir = Path("data")
    out_dir.mkdir(exist_ok=True)
    raw_file = out_dir / f"post_{i+1:02d}_raw.json"
    # 精简导出（去掉太长的 URL 字段方便阅读）
    def simplify(obj, depth=0):
        if depth > 4:
            return "..."
        if isinstance(obj, dict):
            return {k: simplify(v, depth+1) if k not in ("url_list",) else f"[{len(v) if isinstance(v, list) else 0} urls]"
                    for k, v in obj.items()}
        if isinstance(obj, list):
            if len(obj) > 3:
                return [simplify(obj[0], depth+1), f"...({len(obj)-1} more)"]
            return [simplify(x, depth+1) for x in obj]
        return obj
    raw_file.write_text(json.dumps(simplify({"aweme": aw}), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {raw_file}")

# 输出对比表
out = ["", "=" * 60, "字段对比", "=" * 60]
all_keys = set()
for r in results:
    for k in r:
        if k not in ("index", "desc", "aweme_keys", "video_keys", "music_keys"):
            all_keys.add(k)
all_keys = sorted(all_keys)

for key in all_keys:
    out.append(f"\n--- {key} ---")
    for r in results:
        out.append(f"  #{r['index']} [{r['desc'][:30]}]: {r.get(key, 'N/A')}")

# 顶层字段对比
out.append(f"\n--- 顶层 aweme 字段 ---")
for r in results:
    out.append(f"  #{r['index']}: {r['aweme_keys']}")
out.append(f"\n--- video 字段 ---")
for r in results:
    out.append(f"  #{r['index']}: {r['video_keys']}")
out.append(f"\n--- music 字段 ---")
for r in results:
    out.append(f"  #{r['index']}: {r['music_keys']}")

result_text = "\n".join(out)
Path("data/compare_result.txt").write_text(result_text, encoding="utf-8")
print(result_text)
print("\n[OK] 完整原始数据: data/post_01_raw.json ~ post_03_raw.json")
