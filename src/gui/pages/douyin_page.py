# -*- coding: utf-8 -*-
"""
Origami — 抖音功能页
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

from src.gui.fonts import font_scale
from src.cookie import get_cookie_status, load_cookie
from src.gui.dialogs.cookie_dialog import show_login_dialog


class DouyinPage(QWidget):
    """抖音平台页：单个作品 + 批量下载"""

    back_clicked = pyqtSignal()
    single_clicked = pyqtSignal()
    batch_clicked = pyqtSignal()
    cookie_updated = pyqtSignal()
    _login_signal = pyqtSignal(str, object)

    def __init__(self):
        super().__init__()
        self._login_signal.connect(self._set_login_ui)
        self._build()
        QTimer.singleShot(300, self.refresh_cookie_status)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        pt = QApplication.instance().font().pointSize()

        # ── 顶栏：返回 + 登录状态（右对齐） ──
        top = QHBoxLayout()
        top.setContentsMargins(16, 12, 16, 0)
        back = QPushButton("  < 返回")
        back.setObjectName("secondaryBtn")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_clicked.emit)
        back.setMinimumSize(font_scale(80), font_scale(32))
        top.addWidget(back)
        top.addStretch()

        # 登录状态（右）
        self._login_avatar = QLabel()
        av_sz = font_scale(28)
        self._login_avatar.setFixedSize(av_sz, av_sz)
        self._login_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._login_avatar.setStyleSheet(
            f"border: 2px solid #334155; border-radius: {av_sz//2}px;")
        self._login_avatar.hide()
        top.addWidget(self._login_avatar)

        self._login_name = QPushButton("点击登录 →")
        self._login_name.setObjectName("ghostBtn")
        self._login_name.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_name.clicked.connect(self._on_login_clicked)
        top.addWidget(self._login_name)
        layout.addLayout(top)

        # 图标 + 标题
        import pathlib
        from PyQt6.QtGui import QPixmap
        title_row = QHBoxLayout()
        title_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.setSpacing(12)

        icon_path = pathlib.Path(__file__).resolve().parent.parent / "assets" / "icons" / "douyin.png"
        if icon_path.exists():
            icon_label = QLabel()
            pix = QPixmap(str(icon_path)).scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            icon_label.setPixmap(pix)
            title_row.addWidget(icon_label)

        title = QLabel("抖音")
        title_sz = pt * 2
        title.setStyleSheet(f"font-size: {title_sz}px; font-weight: 800; color: #F1F5F9;")
        title_row.addWidget(title)
        layout.addLayout(title_row)

        sub = QLabel("选择下载模式")
        sub.setStyleSheet(f"font-size: {max(12, pt-2)}px; color: #64748B;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setMinimumWidth(font_scale(280))
        sep.setStyleSheet(f"background: #252550; max-height: 1px; border: none;")
        sep_row = QHBoxLayout()
        sep_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sep_row.addWidget(sep)
        layout.addLayout(sep_row)

        # 功能按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(24)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        single_btn = self._big_btn("📥", "单个作品下载", "粘贴分享链接，下载视频/图集/实况")
        single_btn.clicked.connect(self.single_clicked.emit)
        btn_row.addWidget(single_btn)

        batch_btn = self._big_btn("📦", "批量作品下载", "下载他人主页或自己主页的全部作品")
        batch_btn.clicked.connect(self.batch_clicked.emit)
        btn_row.addWidget(batch_btn)

        layout.addLayout(btn_row)
        layout.addStretch()

    def _big_btn(self, icon: str, title: str, desc: str) -> QPushButton:
        """大按钮：图标 + 标题 + 描述"""
        btn = QPushButton()
        btn.setObjectName("modeBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumSize(font_scale(240), font_scale(160))

        cl = QVBoxLayout(btn)
        cl.setContentsMargins(16, 18, 16, 18)
        cl.setSpacing(6)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pt = QApplication.instance().font().pointSize()

        ic = QLabel(icon)
        ic.setStyleSheet(f"font-size:{pt+12}px; background:transparent; border:none;")
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(ic)

        tl = QLabel(title)
        tl.setStyleSheet(f"font-size:{pt+2}px; font-weight:700; color:#F1F5F9; background:transparent; border:none;")
        tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(tl)

        ds = QLabel(desc)
        ds.setStyleSheet(f"font-size:{max(10, pt-2)}px; color:#64748B; background:transparent; border:none;")
        ds.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ds.setWordWrap(True)
        cl.addWidget(ds)
        return btn

    # ── 登录状态（与 ModePage 统一） ──

    def _on_login_clicked(self):
        show_login_dialog(self)
        self.refresh_cookie_status()
        self.cookie_updated.emit()

    def refresh_cookie_status(self):
        """后台拉取抖音账号信息，更新右上角"""
        cookie = load_cookie()
        if not cookie or "sessionid=" not in cookie:
            self._login_avatar.hide()
            self._login_name.setText("点击登录 →")
            self._login_name.setEnabled(True)
            return
        self._login_name.setText("加载中...")
        self._login_name.setEnabled(False)

        import threading, requests as req
        def _fetch():
            try:
                from src.api import DouyinAPI, _get_avatar
                from src.environ import USER_AGENT
                api = DouyinAPI(cookie_string=cookie)
                sec_uid = api.get_own_sec_uid()
                if not sec_uid:
                    self._login_signal.emit("已登录", None)
                    return
                profile = api.get_user_profile(sec_uid)
                nickname = profile.get("nickname", "") or "已登录"
                avatar_url = _get_avatar(profile)
                avatar_data = None
                if avatar_url:
                    try:
                        r = req.get(avatar_url, headers={"User-Agent": USER_AGENT}, timeout=10)
                        avatar_data = r.content
                    except Exception:
                        pass
                self._login_signal.emit(nickname, avatar_data)
            except Exception:
                self._login_signal.emit("已登录", None)
        threading.Thread(target=_fetch, daemon=True).start()

    def _set_login_ui(self, nickname: str, avatar_data):
        """主线程更新登录态 UI（圆形头像）"""
        pt = QApplication.instance().font().pointSize()
        self._login_name.setText(nickname)
        self._login_name.setEnabled(False)
        self._login_name.setStyleSheet(
            f"color: #22C55E; font-size: {max(10, pt-3)}px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        if avatar_data:
            from PyQt6.QtGui import QPixmap, QPainter, QPainterPath
            from PyQt6.QtCore import QRectF
            pix = QPixmap(); pix.loadFromData(avatar_data)
            av_sz = self._login_avatar.width()
            scaled = pix.scaled(av_sz, av_sz, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
            result = QPixmap(av_sz, av_sz)
            result.fill(Qt.GlobalColor.transparent)
            painter = QPainter(result)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addEllipse(QRectF(0, 0, av_sz, av_sz))
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, scaled)
            painter.end()
            self._login_avatar.setPixmap(result)
            self._login_avatar.show()
        else:
            self._login_avatar.hide()
