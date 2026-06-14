# -*- coding: utf-8 -*-
"""
Origami — 首页：平台选择
"""

import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QMessageBox, QInputDialog,
    QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from pathlib import Path

from src.gui.fonts import font_scale
from src.config import VERSION, DINGTALK_WEBHOOK
from src.cookie import get_cookie_status
from src.gui.dialogs.cookie_dialog import show_login_dialog


# 图标目录
_ICONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"

# 平台列表：(id, 名称, svg文件名, 是否可用)
PLATFORMS = [
    ("douyin",   "抖音",   "douyin.png",    True),
    ("bilibili", "B站",    "bilibili.png",  False),
]


class ModePage(QWidget):
    """首页：平台选择"""

    platform_selected = pyqtSignal(str)
    settings_clicked = pyqtSignal()
    cookie_updated = pyqtSignal()
    _login_signal = pyqtSignal(str, object)  # (nickname, avatar_data) 后台→主线程

    def __init__(self):
        super().__init__()
        self._login_signal.connect(self._set_login_ui)
        self._build()
        QTimer.singleShot(500, self.refresh_login_status)
    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        pt = QApplication.instance().font().pointSize()

        # ── 顶栏：右侧登录状态 ──
        top_bar = QHBoxLayout()
        top_bar.addStretch()

        self._login_avatar = QLabel()
        av_sz = font_scale(32)
        self._login_avatar.setFixedSize(av_sz, av_sz)
        self._login_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._login_avatar.setStyleSheet(
            f"border: 2px solid #334155; border-radius: {av_sz//2}px;"
        )
        self._login_avatar.hide()

        # 抖音小图标（在头像前）
        self._login_icon = QLabel()
        icon_sz = font_scale(18)
        icon_path = _ICONS_DIR / "douyin.png"
        if icon_path.exists():
            from PyQt6.QtGui import QPixmap
            pix = QPixmap(str(icon_path)).scaled(icon_sz, icon_sz, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self._login_icon.setPixmap(pix)
        self._login_icon.setFixedSize(icon_sz, icon_sz)
        self._login_icon.hide()
        top_bar.addWidget(self._login_icon)
        top_bar.addWidget(self._login_avatar)

        self._login_name = QPushButton("点击登录 →")
        self._login_name.setObjectName("ghostBtn")
        self._login_name.setCursor(Qt.CursorShape.PointingHandCursor)
        self._login_name.clicked.connect(self._on_login_clicked)
        top_bar.addWidget(self._login_name)

        # 退出登录按钮（仅登录时显示）
        self._logout_btn = QPushButton("退出")
        self._logout_btn.setObjectName("ghostBtn")
        self._logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logout_btn.setStyleSheet(
            f"QPushButton#ghostBtn {{ color: #EF4444; font-size: {max(10, pt-3)}px; padding: 2px 6px; }}"
            f"QPushButton#ghostBtn:hover {{ color: #FFF; background: #EF4444; }}"
        )
        self._logout_btn.clicked.connect(self._logout)
        self._logout_btn.hide()
        top_bar.addWidget(self._logout_btn)

        layout.addLayout(top_bar)

        # ── 标题（图标 + 名称居中） ──
        title_row = QHBoxLayout()
        title_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.setSpacing(10)

        icon_path = Path(__file__).resolve().parent.parent.parent.parent / "app.ico"
        from PyQt6.QtGui import QIcon
        icon_lbl = QLabel()
        if icon_path.exists():
            icon_lbl.setPixmap(QIcon(str(icon_path)).pixmap(32, 32))
        icon_lbl.setFixedSize(32, 32)
        title_row.addWidget(icon_lbl)

        title = QLabel("Origami")
        title_sz = pt * 2 + 14
        title.setStyleSheet(
            f"font-size: {title_sz}px; font-weight: 800; color: #F1F5F9; "
            "letter-spacing: 2px; font-family: 'Copperplate Gothic Bold';"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.addWidget(title)

        ver = QLabel(f"v{VERSION}")
        ver.setStyleSheet(
            f"font-size: {max(11, pt-3)}px; font-weight: bold; color: #000; background: #E11D48; "
            "border-radius: 4px; padding: 2px 8px;"
        )
        ver.setFixedHeight(font_scale(24))
        title_row.addWidget(ver)
        layout.addLayout(title_row)

        sub = QLabel("折你所爱，存你所想")
        sub.setStyleSheet(f"font-size: {max(12, pt-2)}px; color: #64748B;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        # ── 分隔线 ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setMinimumWidth(font_scale(240))
        sep.setStyleSheet(f"background: #252550; max-height: 1px; border: none;")
        sep_row = QHBoxLayout()
        sep_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sep_row.addWidget(sep)
        layout.addLayout(sep_row)
        layout.addSpacing(8)

        # ── 平台卡片 ──
        card_row = QHBoxLayout()
        card_row.setSpacing(32)
        card_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for pid, name, icon_char, available in PLATFORMS:
            card = self._platform_card(name, icon_char, available)
            card.clicked.connect(lambda checked, p=pid, a=available: self._on_platform(p, a))
            card_row.addWidget(card)

        layout.addLayout(card_row)
        layout.addStretch()

        # ── 底部按钮 ──
        bottom = QHBoxLayout()
        bottom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bottom.setSpacing(12)

        settings_btn = QPushButton("设置")
        settings_btn.setObjectName("secondaryBtn")
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self.settings_clicked.emit)
        settings_btn.setFixedWidth(font_scale(100))
        bottom.addWidget(settings_btn)

        feedback_btn = QPushButton("反馈")
        feedback_btn.setObjectName("secondaryBtn")
        feedback_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        feedback_btn.clicked.connect(self._send_feedback)
        feedback_btn.setFixedWidth(font_scale(100))
        bottom.addWidget(feedback_btn)
        layout.addLayout(bottom)

        # 免责声明
        disclaimer = QLabel("仅供个人学习研究，请勿用于违法用途")
        disclaimer.setStyleSheet(
            f"color: #EF4444; font-size: {max(8, QApplication.instance().font().pointSize() - 6)}px; "
            "padding-top: 4px;"
        )
        disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(disclaimer)


    def _platform_card(self, name: str, svg_file: str, available: bool) -> QPushButton:
        """平台卡片：SVG 图标 + 名称"""
        btn = QPushButton()
        btn.setObjectName("modeBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor if available else Qt.CursorShape.ForbiddenCursor)
        btn.setMinimumSize(font_scale(160), font_scale(160))

        cl = QVBoxLayout(btn)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setContentsMargins(20, 20, 20, 20)
        cl.setSpacing(14)

        pt = QApplication.instance().font().pointSize()
        icon_sz = font_scale(72)

        # PNG 图标
        from PyQt6.QtGui import QPixmap
        icon_path = _ICONS_DIR / svg_file
        icon_label = QLabel()
        icon_label.setFixedSize(icon_sz, icon_sz)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icon_path.exists():
            pix = QPixmap(str(icon_path)).scaled(icon_sz, icon_sz, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            icon_label.setPixmap(pix)
        else:
            icon_label.setText(name[0])
            icon_label.setStyleSheet(
                f"font-size: {pt+16}px; font-weight: 800; color: #E11D48; "
                f"background: #1A1030; border-radius: {font_scale(18)}px; "
            )
        cl.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # 名称
        tl = QLabel(name)
        if available:
            tl.setStyleSheet(f"font-size: {pt+4}px; font-weight: 700; color: #F1F5F9;")
        else:
            tl.setStyleSheet(f"font-size: {pt+4}px; font-weight: 700; color: #888;")
        tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(tl)

        if not available:
            badge = QLabel("即将支持")
            badge.setStyleSheet(
                f"font-size: {max(8, pt-5)}px; color: #475569; "
                "background: #0E0E1E; border-radius: 4px; padding: 2px 8px;"
            )
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(badge)
            btn.setEnabled(False)

        return btn

    # ── 平台选择 → 检查登录 ──

    def _on_platform(self, platform_id: str, available: bool):
        if not available:
            return
        if not get_cookie_status()["ok"]:
            show_login_dialog(self)
            self.refresh_cookie_status()
            self.cookie_updated.emit()
        if get_cookie_status()["ok"]:
            self.platform_selected.emit(platform_id)

    def _on_login_clicked(self):
        show_login_dialog(self)
        self.refresh_login_status()
        self.cookie_updated.emit()

    def _logout(self):
        """退出登录：清除 Cookie + 重置 UI"""
        from src.cookie import save_cookie
        save_cookie("")
        self._login_avatar.hide()
        self._login_icon.hide()
        self._login_name.setText("点击登录 →")
        self._login_name.setEnabled(True)
        self._logout_btn.hide()
        self.cookie_updated.emit()

    # ── 登录状态 ──

    def refresh_login_status(self):
        """后台拉取登录账号信息，更新右上角"""
        from src.cookie import load_cookie
        cookie = load_cookie()
        if not cookie or "sessionid=" not in cookie:
            self._login_avatar.hide()
            self._login_icon.hide()
            self._login_name.setText("点击登录 →")
            self._login_name.setEnabled(True)
            self._logout_btn.hide()
            return
        self._login_name.setText("加载中...")
        self._login_name.setEnabled(False)
        self._logout_btn.hide()

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
        """主线程更新登录状态 UI（头像圆形裁剪）"""
        pt = QApplication.instance().font().pointSize()
        self._login_name.setText(nickname)
        self._login_name.setEnabled(False)
        self._login_name.setStyleSheet(
            f"color: #22C55E; font-size: {max(10, pt-3)}px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        self._logout_btn.show()
        if avatar_data:
            from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QBrush
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
            self._login_icon.show()
        else:
            self._login_avatar.hide()
            self._login_icon.hide()

    def refresh_cookie_status(self):
        """检查登录状态并更新右上角"""
        self.refresh_login_status()

    # ── 反馈 ──

    def _send_feedback(self):
        text, ok = QInputDialog.getMultiLineText(
            self, "反馈建议", "请描述问题或建议（含 Origami 或 折纸）：", ""
        )
        if not ok or not text.strip():
            return
        if "Origami" not in text and "折纸" not in text:
            QMessageBox.warning(self, "发送失败", "请包含关键词：Origami 或 折纸")
            return
        try:
            import requests as req
            import platform as pf
            payload = {"msgtype": "text", "text": {
                "content": f"[Origami]\nWin{pf.release()} v{VERSION}\n{text.strip()}"
            }}
            r = req.post(DINGTALK_WEBHOOK, json=payload, timeout=10)
            if r.json().get("errcode") == 0:
                QMessageBox.information(self, "发送成功", "感谢反馈!")
            else:
                QMessageBox.warning(self, "发送失败", f"服务器异常\n({r.text[:200]})")
        except Exception as e:
            QMessageBox.warning(self, "发送失败", f"网络异常\n({e})")
