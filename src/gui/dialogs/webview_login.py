# -*- coding: utf-8 -*-
"""
Origami — WebView 扫码登录对话框 + API 调用

从 src/cookie.py 抽离，纯 UI 组件，不属业务层。
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtCore import QUrl, QTimer, Qt, QEventLoop
from PyQt6.QtNetwork import QNetworkCookie


class WebViewLogin:
    """WebView 登录，登录后保持 WebView 存活供 API 调用"""

    DOUYIN_URL = "https://www.douyin.com/"
    _active_view = None

    def __init__(self):
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        except ImportError:
            raise RuntimeError("PyQt6-WebEngine 未安装")

    def run(self, parent=None) -> Optional[str]:
        dlg = QDialog(parent)
        dlg.setWindowTitle("抖音登录")
        dlg.resize(900, 560)
        dlg.setMinimumSize(720, 450)
        dlg.setStyleSheet("QDialog { background: #0A0A14; }")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hint = QLabel("  登录信息仅保存在本地，不会上传至任何服务器")
        hint.setStyleSheet(
            "color: #F1F5F9; font-size: 13px; font-weight: bold; "
            "padding: 8px 16px; background: #12122A;"
        )
        layout.addWidget(hint)

        view = QWebEngineView()
        layout.addWidget(view, 1)

        status = QLabel("正在加载页面...")
        status.setStyleSheet("color: #94A3B8; font-size: 11px; padding: 6px 16px;")
        layout.addWidget(status)

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(dlg.reject)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 6, 12, 10)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        # 拦截未知协议（如 bitbrowser://）防止弹窗
        class _SafePage(QWebEnginePage):
            def acceptNavigationRequest(self, url, nav_type, is_main_frame):
                if url.scheme() in ('http', 'https', 'data', 'about', 'blob', 'javascript'):
                    return super().acceptNavigationRequest(url, nav_type, is_main_frame)
                return False
        view.setPage(_SafePage(view))
        view.loadFinished.connect(lambda ok: status.setText("请登录抖音..." if ok else "加载失败"))
        view.load(QUrl(self.DOUYIN_URL))

        cookie_result = None
        collected = {}

        store = view.page().profile().cookieStore()

        def on_cookie_added(cookie):
            name = bytes(cookie.name().data()).decode("utf-8", errors="replace")
            value = bytes(cookie.value().data()).decode("utf-8", errors="replace")
            if not name or not value:
                return
            collected[name] = value
            if "sessionid" in collected and "ttwid" in collected:
                nonlocal cookie_result
                cookie_result = "; ".join(f"{k}={v}" for k, v in collected.items())
                status.setText("登录成功！")
                dlg.accept()
                QTimer.singleShot(300, dlg.accept)

        store.cookieAdded.connect(on_cookie_added)

        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted and cookie_result:
            dlg.hide()
            WebViewLogin._active_view = view
            return cookie_result
        return None

    @staticmethod
    def _ensure_view():
        """返回持久 WebView（仅限内置扫码登录创建的）。"""
        return WebViewLogin._active_view

    @staticmethod
    def api_call(cursor: int = 0, timeout: float = 30) -> dict:
        """通过 WebView 调用收藏 API（必须在主线程调用）。

        导航到收藏页，让 SDK 签名后拦截 listcollection 响应。
        使用 QEventLoop 阻塞等待（主线程安全）。
        """
        import json as _json

        view = WebViewLogin._ensure_view()
        if not view:
            return {"_error": "请用内置浏览器扫码登录（首页→点登录→扫码），\n"
                             "浏览器自动提取的 Cookie 缺少收藏功能所需的安全参数"}

        from PyQt6.QtNetwork import QNetworkAccessManager
        profile = view.page().profile()
        captured = []
        old_mgr = None

        class _CaptureManager(QNetworkAccessManager):
            def createRequest(self, op, req, outgoingData):
                reply = super().createRequest(op, req, outgoingData)
                if 'listcollection' in req.url().toString():
                    reply.finished.connect(lambda r=reply: _on_reply(r))
                return reply

        def _on_reply(reply):
            try:
                body = bytes(reply.readAll()).decode('utf-8', errors='replace')
                captured.append(body)
            except Exception:
                pass

        old_mgr = profile.networkAccessManager()
        profile.setNetworkAccessManager(_CaptureManager(profile))

        fav_url = ('https://www.douyin.com/user/self'
                   '?from_tab_name=main'
                   '&showSubTab=video'
                   '&showTab=favorite_collection')
        view.load(QUrl(fav_url))

        # QTimer 轮询直到捕获到响应或超时
        loop = QEventLoop()
        elapsed = [0]

        def _poll():
            elapsed[0] += 1
            if captured or elapsed[0] >= timeout:
                loop.quit()
            else:
                QTimer.singleShot(1000, _poll)

        QTimer.singleShot(1000, _poll)
        loop.exec()

        # 恢复原始 QNetworkAccessManager
        if old_mgr:
            profile.setNetworkAccessManager(old_mgr)

        if captured:
            for body in captured:
                try:
                    data = _json.loads(body)
                    if data.get('aweme_list'):
                        return data
                except Exception:
                    pass
            try:
                data = _json.loads(captured[0])
                return data if data.get('aweme_list') else {
                    "_error": "no_aweme_list",
                    "_raw": captured[0][:500]
                }
            except Exception:
                return {"_error": "json_parse", "_raw": captured[0][:500]}

        return {"_error": "no_capture"}
