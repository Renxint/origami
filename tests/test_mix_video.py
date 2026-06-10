# -*- coding: utf-8 -*-
"""测试合集内作品视频获取"""
import sys, json, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

import src.webview_api as wapi

mix_id = '7514361363695683611'

# 完整指纹参数
params = {
    "mix_id": mix_id, "cursor": "0", "count": "5",
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
query = "&".join(f"{k}={v}" for k, v in params.items())

# ── 方法1: api-call.js (Puppeteer 轻量) ──
print("=== 方法1: api-call.js ===")
url = f"https://www.douyin.com/aweme/v1/web/mix/aweme/list/?{query}"
r = wapi._call_api(url, timeout=30)
if r.get('_error'):
    print(f"FAIL: {r['_error'][:120]}")
else:
    posts = r.get('aweme_list') or []
    print(f"作品数: {len(posts)}")
    for p in posts[:3]:
        print(f"  aweme_id={p.get('aweme_id')} desc={p.get('desc','')[:50]}")
    if not posts:
        print(f"  响应keys: {list(r.keys())[:12]}")
        print(f"  status: {r.get('status_code')} {r.get('status_msg','')}")

# ── 方法2: bootstrap.js 级别（完整SDK签名）──
print("\n=== 方法2: bootstrap.js (完整SDK) ===")
from src.cookie import load_cookie
from src.platforms.douyin import DouyinAdapter
cookie = load_cookie()
adapter = DouyinAdapter()

# bootstrap.js 设计用于单个 aweme detail，不能直接调 mix list
# 但我们可以尝试用 api-call.js 但先 navigated 到 mix 页面
# 试一下 mix 页面的 data API
try:
    from src.environ import NODE_CMD, BASE_DIR, CREATE_NO_WINDOW
    import subprocess, tempfile
    from pathlib import Path

    # 写一个临时 Node 脚本，导航到合集页再调API
    js_code = f'''
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
puppeteer.use(StealthPlugin());

(async () => {{
    const cookieStr = fs.readFileSync(process.argv[2], 'utf-8').trim();
    const browser = await puppeteer.launch({{ headless: 'new', args: ['--no-sandbox'] }});
    const page = await browser.newPage();

    try {{
        // 设置cookie
        const cookies = cookieStr.split('; ').map(item => {{
            const eq = item.indexOf('=');
            if (eq < 1) return null;
            return {{ name: item.substring(0,eq).trim(), value: item.substring(eq+1).trim(), domain: '.douyin.com', path: '/' }};
        }}).filter(c => c && c.name && c.value);
        await page.setCookie(...cookies);

        // 导航到合集页
        await page.goto('https://www.douyin.com/collection/{mix_id}', {{ waitUntil: 'domcontentloaded', timeout: 20000 }});
        await new Promise(r => setTimeout(r, 2000));

        // 尝试调用API
        const result = await page.evaluate(async () => {{
            try {{
                const r = await fetch('/aweme/v1/web/mix/aweme/list/?mix_id={mix_id}&count=5&cursor=0&device_platform=webapp&aid=6383&version_code=290100&version_name=29.1.0&cookie_enabled=true');
                return await r.json();
            }} catch(e) {{ return {{_error: e.message}}; }}
        }});
        console.log(JSON.stringify(result));
    }} catch(e) {{
        console.log(JSON.stringify({{_error: e.message}}));
    }} finally {{
        await browser.close();
    }}
}})();
'''
    tmp_js = Path(tempfile.mktemp(suffix='.js'))
    tmp_cookie = Path(tempfile.mktemp(suffix='.txt'))
    tmp_js.write_text(js_code, encoding='utf-8')
    tmp_cookie.write_text(cookie, encoding='utf-8')

    result = subprocess.run(
        ['node', str(tmp_js), str(tmp_cookie)],
        capture_output=True, text=True, encoding='utf-8', timeout=45,
        creationflags=CREATE_NO_WINDOW,
    )
    stdout = (result.stdout or '').strip()
    if stdout:
        data = json.loads(stdout)
        if data.get('_error'):
            print(f"FAIL: {data['_error'][:150]}")
        else:
            posts = data.get('aweme_list') or []
            print(f"作品数: {len(posts)}")
            for p in posts[:5]:
                awid = p.get('aweme_id', '?')
                d = p.get('desc', '')[:60]
                v = p.get('video')
                has_v = '有视频' if v else '无视频'
                print(f"  aweme_id={awid} {has_v} {d}")
            if not posts:
                print(f"  响应keys: {list(data.keys())[:12]}")
    else:
        print(f"stderr: {(result.stderr or '')[:200]}")
    tmp_js.unlink(missing_ok=True)
    tmp_cookie.unlink(missing_ok=True)
except Exception as e:
    print(f"ERROR: {e}")
    import traceback; traceback.print_exc()
