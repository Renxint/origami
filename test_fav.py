# -*- coding: utf-8 -*-
"""测试收藏 API — 模拟点击视频标签"""
import sys, json
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget, QLabel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEnginePage
from PyQt6.QtCore import QUrl, QTimer

app = QApplication(sys.argv)

win = QWidget()
win.setWindowTitle("收藏 API 测试 — 自动点击")
win.resize(800, 600)
layout = QVBoxLayout(win)
status = QLabel("初始化...")
status.setStyleSheet("color:#22C55E;font-size:14px;padding:4px;")
layout.addWidget(status)
view = QWebEngineView()
layout.addWidget(view, 1)
log_label = QLabel("等待...")
log_label.setStyleSheet("color:#F1F5F9;font-size:12px;font-family:monospace;background:#12122A;padding:8px;")
layout.addWidget(log_label)

# 拦截器 + 文件日志
all_urls = []
lc_urls = []
LOG_FILE = "D:/_fav_test_log.txt"
open(LOG_FILE, 'w').write("=== 收藏API抓包日志 ===\n")
class _Interceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        all_urls.append(url)
        if 'listcollection' in url or 'favorite' in url or 'collection' in url or 'aweme/v1' in url:
            lc_urls.append(url)
            msg = f"[HIT] {url[:300]}\n"
            status.setText(msg.strip())
            open(LOG_FILE, 'a').write(msg)
view.page().profile().setUrlRequestInterceptor(_Interceptor(view.page().profile()))

# 协议拦截
class _SafePage(QWebEnginePage):
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() in ('http', 'https', 'data', 'about', 'blob', 'javascript'):
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)
        return False
view.setPage(_SafePage(view))

# 从文件读 Cookie
from src.cookie import load_cookie
cookie = load_cookie()
if not cookie or "sessionid=" not in cookie:
    status.setText("[FAIL] 未登录")
    win.show()
    app.exec()
    sys.exit()

# Step 1: 加载首页 + Cookie
status.setText("[1/5] 加载首页...")
def _step1(ok):
    view.loadFinished.disconnect(_step1)
    store = view.page().profile().cookieStore()
    from PyQt6.QtNetwork import QNetworkCookie
    for c in cookie.split("; "):
        if "=" in c:
            name, val = c.split("=", 1)
            ck = QNetworkCookie(name.encode(), val.encode())
            ck.setDomain(".douyin.com")
            ck.setPath("/")
            store.setCookie(ck)
    status.setText("[2/5] Cookie已注入，等SDK...")
    QTimer.singleShot(5000, _step2)
view.loadFinished.connect(_step1)
view.load(QUrl("https://www.douyin.com/"))

# Step 2: 重新加载首页激活登录态
def _step2():
    status.setText("[3/5] 重载首页激活登录...")
    view.load(QUrl("https://www.douyin.com/"))
    view.loadFinished.connect(_step3)
def _step3(ok):
    view.loadFinished.disconnect(_step3)
    status.setText("[4/5] 等页面完全渲染...")
    QTimer.singleShot(8000, _step4)

# Step 4: 导航到收藏页
def _step4():
    status.setText("[5/5] 导航到收藏页...")
    view.load(QUrl("https://www.douyin.com/user/self?from_tab_name=main&showTab=favorite_collection"))
    view.loadFinished.connect(_step5)
def _step5(ok):
    view.loadFinished.disconnect(_step5)
    status.setText("[OK] 收藏页已加载，5s后模拟点击视频标签...")
    # 等页面 JS 渲染完，模拟点击视频标签
    QTimer.singleShot(5000, _click_video)

# 模拟点击：用 JS 找到视频标签按钮并点击
def _click_video():
    status.setText("[CLICK] 模拟点击视频标签...")
    js = """
    (function() {
        // 找包含"视频"文字的标签/按钮
        var tabs = document.querySelectorAll('div,span,a,button,li');
        for (var i = 0; i < tabs.length; i++) {
            var t = tabs[i];
            if (t.innerText && t.innerText.trim() === '视频' && t.offsetParent !== null) {
                t.click();
                return 'clicked: ' + t.tagName + ' ' + t.className;
            }
        }
        return 'not found';
    })()
    """
    view.page().runJavaScript(js, _on_click)
def _on_click(result):
    status.setText(f"[CLICK] 结果: {result}")
    log_label.setText("等待 listcollection...每 2s 更新统计")
    QTimer.singleShot(1000, _poll)

# 每 2s 等结果
_elapsed = [0]
def _poll():
    _elapsed[0] += 1
    lc = len(lc_urls)
    api = [u for u in all_urls if ('aweme/v1' in u or 'aweme/v2' in u) and 'douyinstatic' not in u][-5:]
    log_label.setText(
        f"已等 {_elapsed[0]}s | 总请求:{len(all_urls)} | 命中:{lc}\n"
        + "\n".join(lc_urls[-3:])[:500] if lc_urls else "等待中...\n"
        + f"最近API:\n" + "\n".join(api)[:400]
    )
    if lc_urls or _elapsed[0] >= 60:
        if lc_urls:
            status.setText(f"[SUCCESS] 捕获到 listcollection!")
            log_label.setText("抓到URL:\n" + "\n".join(lc_urls))
        else:
            status.setText("[FAIL] 60s 仍未捕获")
        open(LOG_FILE, 'a').write(f"\n=== TIMEOUT ===\n共{len(all_urls)}请求\n")
        for u in all_urls:
            if 'aweme' in u or 'favorite' in u or 'collection' in u:
                open(LOG_FILE, 'a').write(f"  {u[:400]}\n")
        open(LOG_FILE, 'a').write("[DONE]\n")
        return
    QTimer.singleShot(2000, _poll)

win.show()
app.exec()
