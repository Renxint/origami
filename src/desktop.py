# -*- coding: utf-8 -*-
"""
Origami v2 — Desktop Shell

入口：python src/desktop.py
"""

import sys
import os
import subprocess
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class DesktopApi:
    """pywebview JS-Python 桥"""

    def startLogin(self):
        """独立进程启动登录窗口 → 等 Cookie 保存 → 通知前端"""
        login_script = os.path.join(ROOT, "src", "main.py")
        # 用 subprocess 跑独立进程，完全避开 pywebview 线程限制
        subprocess.run(
            [sys.executable, login_script, "login"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,  # 消掉 cookie 解析警告
        )
        # 检查是否登录成功
        from src.cookie import load_cookie
        cookie = load_cookie()
        return {"ok": bool(cookie and "sessionid=" in cookie)}

    def getApiBase(self):
        return f"http://127.0.0.1:{_port}"


_port = 8765


def run():
    global _port

    # 1. 后台 API Server
    from src.server import create_app, find_available_port, API_PORT
    from aiohttp import web

    _port = find_available_port(API_PORT)
    app = create_app()

    def _start_server():
        web.run_app(app, host="127.0.0.1", port=_port, print=lambda *_: None)

    threading.Thread(target=_start_server, daemon=True, name="api-server").start()

    # 等 server 就绪
    import requests
    for _ in range(20):
        try:
            requests.get(f"http://127.0.0.1:{_port}/api/version", timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    print(f"[Origami] http://127.0.0.1:{_port}")

    # 2. pywebview 窗口
    import webview

    api = DesktopApi()
    window = webview.create_window(
        "Origami",
        f"http://127.0.0.1:{_port}/pages/home.html",
        js_api=api,
        width=800, height=600, min_size=(520, 420),
    )
    webview.start()


if __name__ == "__main__":
    run()
