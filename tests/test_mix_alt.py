# -*- coding: utf-8 -*-
"""探索合集内容获取的替代方案"""
import sys, json, re, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

import requests
from src.cookie import load_cookie
from src.environ import USER_AGENT
import src.webview_api as wapi

cookie = load_cookie()
s = requests.Session()
s.headers.update({'User-Agent': USER_AGENT, 'Cookie': cookie})

mix_id = '7514361363695683611'
sec_uid = 'MS4wLjABAAAAHF8JXaEZVBqv6zs6-DFpYEaJXiiVTmfNKpBs4NLPKHs'

# ── 方法1: 抓取合集页HTML，提取SSR数据 ──
print("=== 方法1: 抓取合集页HTML ===")
r = s.get(f'https://www.douyin.com/collection/{mix_id}', timeout=15, headers={
    'Accept': 'text/html,application/xhtml+xml',
})
html = r.text
# 搜索嵌入的JSON数据
# 常见模式: window.__INITIAL_STATE__ = {...}; 或 <script id="__NEXT_DATA__">
for pattern in [
    r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*;</script>',
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>\s*(\{.+?\})\s*</script>',
    r'<script[^>]*id="RENDER_DATA"[^>]*>\s*(\{.+?\})\s*</script>',
    r'"aweme_list"\s*:\s*\[',
    r'"mixInfo"\s*:\s*\{',
    r'"mix_info"\s*:\s*\{',
]:
    m = re.search(pattern, html, re.DOTALL)
    print(f'  {pattern[:60]}: {"FOUND" if m else "NOT FOUND"}')
    if m:
        print(f'    match: {m.group(0)[:200]}')

# 检查HTML大小和关键片段
print(f'  HTML大小: {len(html)} bytes')
for tag in ['mixInfo', 'mix_info', 'aweme_list', 'collection', 'RENDER_DATA', '__NEXT_DATA__', '__INITIAL_STATE__']:
    count = html.count(tag)
    if count > 0:
        print(f'  "{tag}" 出现 {count} 次')

# ── 方法2: 尝试不同的API路径 ──
print("\n=== 方法2: 不同API路径 ===")
endpoints = [
    f'/aweme/v2/web/mix/aweme/list/?mix_id={mix_id}&count=5&cursor=0',
    f'/web/api/mix/{mix_id}/aweme/',
    f'/aweme/v1/web/mix/{mix_id}/aweme/',
]
for ep in endpoints:
    try:
        r2 = wapi._call_api(f'https://www.douyin.com{ep}&device_platform=webapp&aid=6383&version_code=290100&version_name=29.1.0&cookie_enabled=true', timeout=30)
        err = r2.get('_error', '')
        if err:
            print(f'  {ep[:60]}: {err[:80]}')
        else:
            print(f'  {ep[:60]}: keys={list(r2.keys())[:8]}')
    except Exception as e:
        print(f'  {ep[:60]}: {e}')

# ── 方法3: 通过搜索合集名找作品 ──
print("\n=== 方法3: 搜索合集名 ===")
from src.api import DouyinAPI
api = DouyinAPI(cookie_string=cookie)
# 获取合集名
url = f'https://www.douyin.com/aweme/v1/web/mix/detail/?mix_id={mix_id}&device_platform=webapp&aid=6383&version_code=290100&version_name=29.1.0&cookie_enabled=true'
r3 = api.session.get(url, timeout=15)
mix_data = r3.json()
mix_name = (mix_data.get('mix_info') or {}).get('mix_name', '')
print(f'  合集名: {mix_name}')

# ── 方法4: 从用户作品列表中过滤合集作品 ──
print("\n=== 方法4: 用户作品列表是否能关联合集 ===")
data = api.get_user_posts(sec_uid, max_cursor=0, count=5)
posts = data.get('aweme_list', [])
print(f'  获取到 {len(posts)} 条作品')
for p in posts[:3]:
    awid = p.get('aweme_id', '?')
    # 检查是否有合集相关字段
    mix_keys = [k for k in p.keys() if 'mix' in k.lower() or 'collection' in k.lower() or 'album' in k.lower()]
    print(f'  aweme_id={awid} mix_keys={mix_keys}')
    if 'mix_info' in p:
        print(f'    mix_info={json.dumps(p["mix_info"], ensure_ascii=False)[:200]}')
