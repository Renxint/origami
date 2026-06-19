# -*- coding: utf-8 -*-
"""
Origami — 抖音 API 代理

通过 Node.js Puppeteer（真实 Chrome）调用抖音 API，
自动携带 a_bogus / msToken 等浏览器签名。

每次调用启动独立进程，用完即退，无生命周期问题。
"""

import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from src.environ import (NODE_CMD, BASE_DIR, EXE_DIR, CREATE_NO_WINDOW,
                        COOKIE_FILE, SIGN_SERVER_JS, SIGN_SERVER_PORT)

_API_SCRIPT = BASE_DIR / "sign-server" / "api-call.js"
_SIGNED_SCRIPT = BASE_DIR / "sign-server" / "api-signed.js"


def _call_api(url: str, timeout: float = 20) -> dict:
    """通过 Puppeteer 调用 API，返回 JSON dict"""
    if not COOKIE_FILE.exists():
        return {"_error": "not_logged_in"}

    from src.cookie import load_cookie

    # 写一份明文 Cookie 供 Node.js 读取
    plain_cookie = load_cookie()
    if not plain_cookie:
        return {"_error": "no_cookie"}

    # 过滤空 name 的 Cookie
    clean = "; ".join(c for c in plain_cookie.split("; ") if "=" in c and c.split("=", 1)[0])

    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".txt"))
    tmp.write_text(clean, encoding="utf-8")

    try:
        result = subprocess.run(
            [NODE_CMD, str(_API_SCRIPT), str(tmp), url],
            capture_output=True, text=True, encoding='utf-8', timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        stdout = (result.stdout or "").strip()
        if result.returncode != 0 or not stdout:
            return {"_error": f"exit={result.returncode} err={result.stderr[:100]}"}
        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        return {"_error": "timeout"}
    except Exception as e:
        return {"_error": str(e)}
    finally:
        tmp.unlink(missing_ok=True)


def _call_api_signed(cursor: int = 0, timeout: float = 60) -> dict:
    """收藏列表 API（POST，SDK 签名）"""
    if not COOKIE_FILE.exists():
        return {"_error": "not_logged_in"}

    from src.cookie import load_cookie
    plain_cookie = load_cookie()
    if not plain_cookie:
        return {"_error": "no_cookie"}
    clean = "; ".join(c for c in plain_cookie.split("; ") if "=" in c and c.split("=", 1)[0])

    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".txt"))
    tmp.write_text(clean, encoding="utf-8")

    try:
        result = subprocess.run(
            [NODE_CMD, str(_SIGNED_SCRIPT), str(tmp), str(cursor)],
            capture_output=True, text=True, encoding='utf-8', timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        stdout = (result.stdout or "").strip()
        if result.returncode != 0 or not stdout:
            return {"_error": f"exit={result.returncode} err={(result.stderr or '')[:200]}"}
        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        return {"_error": "timeout"}
    except Exception as e:
        return {"_error": str(e)}
    finally:
        tmp.unlink(missing_ok=True)


# ── 常驻浏览器服务 ──
_server_process = None
_server_lock = threading.Lock()
_active_port = SIGN_SERVER_PORT  # 运行时端口，启动时自动探测可用端口


def _get_sign_url():
    """返回当前 sign-server URL（端口可能不同于默认值）"""
    return f"http://localhost:{_active_port}"


def _find_available_port(start: int, max_tries: int = 50) -> int:
    """从 start 开始扫描，返回第一个可绑定端口"""
    import socket
    for port in range(start, start + max_tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(('127.0.0.1', port))
            s.close()
            return port
        except OSError:
            s.close()
            continue
    return start  # 全部失败则返回默认值兜底


def _is_server_ready():
    """检查 sign-server 健康状态（快速探测，不阻塞）"""
    import requests as _r
    try:
        r = _r.get(f"{_get_sign_url()}/health", timeout=1)
        return r.json().get('sdkReady', False)
    except Exception:
        return False


def _kill_orphan_nodes():
    """启动时清理上一次强杀遗留的 sign-server 孤儿进程"""
    try:
        subprocess.run(
            'wmic process where "name=\'node.exe\' and commandline like \'%sign-server%\'" call terminate 2>nul',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        pass


def _debug_log(msg: str):
    """写调试日志到 _sign_debug.log"""
    try:
        _ts = time.strftime("%H:%M:%S")
        with open(EXE_DIR / "_sign_debug.log", "a", encoding="utf-8") as f:
            f.write(f"[{_ts}] {msg}\n")
    except Exception:
        pass


def start_server():
    """启动常驻 Node 浏览器服务（线程安全，自动探可用端口，失败重试）"""
    global _server_process, _active_port

    _debug_log("=== start_server() called ===")
    _kill_orphan_nodes()

    # 快速路径：已经在跑，直接返回（无锁）
    if _server_process and _server_process.poll() is None and _is_server_ready():
        _debug_log("fast path: server already running")
        return True

    with _server_lock:
        if _server_process and _server_process.poll() is None and _is_server_ready():
            _debug_log("double-check: server already running")
            return True

        _active_port = _find_available_port(SIGN_SERVER_PORT)
        _debug_log(f"using port: {_active_port}")
        _kill_sign_port()
        time.sleep(0.3)

        # 环境变量诊断
        _debug_log(f"NODE_CMD: {NODE_CMD}")
        _debug_log(f"NODE_CMD exists: {os.path.exists(NODE_CMD)}")
        _debug_log(f"SIGN_SERVER_JS: {SIGN_SERVER_JS}")
        _debug_log(f"SIGN_SERVER_JS exists: {os.path.exists(SIGN_SERVER_JS)}")
        _debug_log(f"BASE_DIR: {BASE_DIR}")
        _debug_log(f"EXE_DIR: {EXE_DIR}")
        _debug_log(f"frozen: {getattr(__import__('sys'), 'frozen', False)}")

        # DLL 搜索路径诊断
        _qt_bin = str(BASE_DIR / "PyQt6" / "Qt6" / "bin")
        _debug_log(f"Qt bin exists: {os.path.isdir(_qt_bin)} -> {_qt_bin}")

        # PATH 前 500 字符
        _raw_path = os.environ.get("PATH", "")
        _debug_log(f"raw PATH (first 500): {_raw_path[:500]}")

        # 构建清理后的环境：彻底删除 Qt bin，只保留浏览器目录
        _clean_env = os.environ.copy()
        _clean_path = _clean_env.get("PATH", "")
        # 删掉所有出现的 Qt bin（可能重复多次）
        _clean_path = _clean_path.replace(_qt_bin + ";", "").replace(_qt_bin, "")
        _edge_dirs = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application",
            r"C:\Program Files\Microsoft\Edge\Application",
            r"C:\Program Files\Google\Chrome\Application",
        ]
        _found_edges = [d for d in _edge_dirs if os.path.isdir(d)]
        _debug_log(f"found browser dirs: {_found_edges}")
        _extra = ";".join(_found_edges)
        if _extra:
            _clean_path = _extra + ";" + _clean_path
        _clean_env["PATH"] = _clean_path
        _debug_log(f"cleaned PATH (first 300): {_clean_path[:300]}")

        # 关键修复：临时关闭 os.add_dll_directory(Qt bin)
        from src.environ import _qt_dll_cookie as _cookie, QT_BIN_PATH as _qtp
        if _cookie is not None:
            _debug_log("closing AddDllDirectory cookie for sign-server spawn...")
            _cookie.close()
            src.environ._qt_dll_cookie = os.add_dll_directory(_qtp)
            _debug_log("cookie restored for main process")

        for attempt in (1, 2):
            _debug_log(f"--- attempt {attempt} ---")
            _err_log = EXE_DIR / "_sign_err.log"
            _debug_log(f"log file: {_err_log}")
            try:
                _err_f = open(_err_log, "w", encoding="utf-8")
                _server_process = subprocess.Popen(
                    [NODE_CMD, str(SIGN_SERVER_JS), str(_active_port)],
                    stdout=_err_f, stderr=_err_f,
                    env=_clean_env,
                    creationflags=CREATE_NO_WINDOW,
                )
                _err_f.close()
                _debug_log(f"Popen ok, PID: {_server_process.pid}")
                _debug_log(f"sign_err.log: {_err_log.read_text(encoding='utf-8')[:500]}")
            except Exception as e:
                _debug_log(f"Popen FAILED: {e}")
                if attempt == 1:
                    time.sleep(2)
                    continue
                return False

            time.sleep(3)
            _rc = _server_process.poll()
            _debug_log(f"after 3s, poll()={_rc}")
            if _rc is None:
                _debug_log("process alive, checking health...")
                if _is_server_ready():
                    _debug_log("health OK, start_server SUCCESS")
                    return True
                else:
                    _debug_log("process alive but health check failed, will wait in call_server")
                    return True
            # 进程已死
            _debug_log(f"process died (rc={_rc}), reading stderr...")
            if _err_log.exists():
                _stderr_tail = _err_log.read_text(encoding="utf-8")[-500:]
                _debug_log(f"stderr tail: {_stderr_tail}")
            if attempt == 1:
                _debug_log("retrying...")
                time.sleep(2)
                _kill_sign_port()
                time.sleep(1)
                # EADDRINUSE 时换端口
                if "EADDRINUSE" in (_stderr_tail if '_stderr_tail' in dir() else ""):
                    _active_port = _find_available_port(_active_port + 1)
                    _debug_log(f"EADDRINUSE, new port: {_active_port}")
    _debug_log("start_server: all attempts exhausted")
    return True


def stop_server():
    """关闭常驻服务（杀进程 + 等退出 + 清端口残留）"""
    global _server_process
    with _server_lock:
        if _server_process:
            try:
                _server_process.kill()
                _server_process.wait(timeout=3)  # 等待进程彻底退出
            except Exception:
                pass
            _server_process = None
    # 始终清端口（杀本 session 残留 + 上次 os._exit 遗留的僵尸）
    _kill_sign_port()


def _kill_sign_port():
    """清理 sign-server 端口上的残留进程"""
    try:
        subprocess.run(
            f'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :{_active_port}\') do taskkill /F /PID %a >nul 2>&1',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        pass


def call_server(endpoint, **params):
    """调用常驻服务端点（自动启动 sign-server，线程安全）

    内置懒启动：如果 sign-server 没在跑，自动拉起并等待就绪。
    调用方无需关心服务器状态。
    """
    import requests as _r

    url = f"{_get_sign_url()}/{endpoint}"
    _debug_log(f"call_server: {endpoint}")

    for attempt in (1, 2):
        if not _is_server_ready():
            _debug_log(f"attempt {attempt}: not ready, starting...")
            start_server()
            for i in range(20):
                if _is_server_ready():
                    _debug_log(f"ready after {i+1} checks")
                    break
                time.sleep(0.5 if i < 10 else 1)
            else:
                _debug_log("WARN: not ready after 20 checks")

        try:
            r = _r.post(url, params=params, timeout=60)
            result = r.json()
            if "_error" in result:
                _debug_log(f"server error: {result['_error'][:200]}")
            return result
        except Exception as e:
            err = str(e)
            _debug_log(f"request failed: {err[:200]}")
            if "Connection refused" in err and attempt == 1:
                _debug_log("restarting and retry...")
                stop_server()
                time.sleep(0.5)
                continue
            return {"_error": err}
    return {"_error": "sign-server 连接失败，已重试"}


def get_user_posts(sec_uid: str, max_cursor: int = 0, count: int = 18) -> dict:
    params = (f"sec_user_id={sec_uid}&max_cursor={max_cursor}&count={count}"
              f"&aid=6383&device_platform=webapp&version_code=290100"
              f"&version_name=29.1.0&cookie_enabled=true")
    return _call_api(f"https://www.douyin.com/aweme/v1/web/aweme/post/?{params}")


def get_user_profile(sec_uid: str) -> dict:
    """获取用户信息，返回扁平化 dict"""
    raw = _call_api(
        f"https://www.douyin.com/aweme/v1/web/user/profile/other/"
        f"?sec_user_id={sec_uid}&device_platform=webapp&aid=6383"
        f"&version_code=290100&version_name=29.1.0"
    )
    user = raw.get("user", {})
    return {
        "nickname": user.get("nickname", ""),
        "unique_id": user.get("unique_id", ""),
        "uid": user.get("uid", ""),
        "sec_uid": user.get("sec_uid", ""),
        "desc": user.get("signature", ""),
        "aweme_count": user.get("aweme_count", 0),
        "follower_count": user.get("follower_count", 0),
        "following_count": user.get("following_count", 0),
        "favoriting_count": user.get("favoriting_count", 0),
        "total_favorited": user.get("total_favorited", 0),
        "avatar_url": _get_avatar(user),
        "gender": user.get("gender", 0),
        "country": user.get("country", ""),
        "province": user.get("province", ""),
        "city": user.get("city", ""),
        "district": user.get("district", ""),
        "school": user.get("school_name", ""),
        "age": user.get("user_age", -1),
        "custom_verify": user.get("custom_verify", ""),
        "enterprise_verify_reason": user.get("enterprise_verify_reason", ""),
    }


def _get_avatar(user: dict) -> str:
    for key in ("avatar_300_url", "avatar_url", "avatar_medium_url", "avatar_thumb_url"):
        val = user.get(key, "")
        if isinstance(val, dict):
            val = (val.get("url_list") or [""])[0]
        if val and isinstance(val, str) and val.startswith("http"):
            return val
    return ""


def get_user_likes(sec_uid: str, max_cursor: int = 0, count: int = 18) -> dict:
    params = (f"sec_user_id={sec_uid}&max_cursor={max_cursor}&count={count}"
              f"&aid=6383&device_platform=webapp&version_code=290100"
              f"&version_name=29.1.0&cookie_enabled=true")
    return _call_api(f"https://www.douyin.com/aweme/v1/web/aweme/favorite/?{params}")


def get_favorite_collections(cursor: int = 0) -> dict:
    """获取收藏→视频列表（导航 WebView + 拦截网络响应）"""
    from src.gui.dialogs.webview_login import WebViewLogin
    return WebViewLogin.api_call(cursor=cursor, timeout=30)


def get_favorite_videos(max_cursor: int = 0, count: int = 18) -> dict:
    """获取收藏的视频列表（翻页，Puppeteer）"""
    params = (f"max_cursor={max_cursor}&count={count}"
              f"&aid=6383&device_platform=webapp&version_code=290100"
              f"&version_name=29.1.0&cookie_enabled=true"
              f"&media_type=4")
    return _call_api(
        f"https://www.douyin.com/aweme/v1/web/aweme/favorite/?{params}",
        timeout=30)


def get_favorite_items(fav_id: str, max_cursor: int = 0,
                       count: int = 18) -> dict:
    """获取指定收藏夹的作品列表（Puppeteer）"""
    params = (f"favorite_id={fav_id}&max_cursor={max_cursor}&count={count}"
              f"&aid=6383&device_platform=webapp&version_code=290100"
              f"&version_name=29.1.0&cookie_enabled=true")
    return _call_api(
        f"https://www.douyin.com/aweme/v1/web/favorite/list/item/?{params}")
