# -*- coding: utf-8 -*-
"""
Origami v2 — Desktop Shell

双击 .exe 入口：启动后台 API Server + 前台 pywebview 窗口。
用户看到的是一个独立的桌面窗口，不需要浏览器。
"""

import sys
import os
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def run():
    """启动桌面应用"""
    # 1. 后台启动 API Server
    from src.server import create_app, find_available_port, API_PORT
    from aiohttp import web

    port = find_available_port(API_PORT)
    app = create_app()

    def _start_server():
        web.run_app(app, host="127.0.0.1", port=port, print=lambda *_: None)

    server_thread = threading.Thread(target=_start_server, daemon=True, name="api-server")
    server_thread.start()

    # 等 server 就绪
    import requests
    for _ in range(20):
        try:
            r = requests.get(f"http://127.0.0.1:{port}/api/version", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        print("[Origami] API Server 启动超时")
        return

    print(f"[Origami] API Server → http://127.0.0.1:{port}")

    # 2. 前台 pywebview 窗口
    try:
        import webview
    except ImportError:
        print("请安装 pywebview: pip install pywebview")
        return

    # 把 API 地址注入前端
    def _inject_api_url(window):
        window.evaluate_js(f"""
            window.API_BASE = 'http://127.0.0.1:{port}';
            window.WS_URL = 'ws://127.0.0.1:{port}/ws/events';
            if (window.wsConnect) window.wsConnect();
        """)

    window = webview.create_window(
        f"Origami", f"http://127.0.0.1:{port}/pages/home.html",
        width=820, height=640, min_size=(520, 380),
        on_top=False, confirm_close=False)

    # 页面加载后注入 API 地址
    window.events.loaded += lambda: _inject_api_url(window)

    webview.start()


if __name__ == "__main__":
    run()
