# -*- coding: utf-8 -*-
"""
Origami — 抖音功能页
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from src.theme import font_scale
from src.cookie import get_cookie_status
from src.gui.dialogs.cookie_dialog import show_login_dialog


class DouyinPage(QWidget):
    """抖音平台页：单视频 + 主页批量"""

    back_clicked = pyqtSignal()
    single_clicked = pyqtSignal()
    homepage_clicked = pyqtSignal()
    cookie_updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._build()


    def _build(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        pt = QApplication.instance().font().pointSize()

        # 顶栏
        top = QHBoxLayout()
        top.setContentsMargins(16, 12, 16, 0)
        back = QPushButton("  < 返回")
        back.setObjectName("secondaryBtn")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_clicked.emit)
        back.setMinimumSize(font_scale(80), font_scale(32))
        top.addWidget(back)
        top.addStretch()
        layout.addLayout(top)

        # 标题
        title = QLabel("抖音")
        title_sz = pt * 2
        title.setStyleSheet(f"font-size: {title_sz}px; font-weight: 800; color: #F1F5F9;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("选择下载模式")
        sub.setStyleSheet(f"font-size: {max(12, pt-2)}px; color: #64748B;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setMinimumWidth(font_scale(280))
        sep.setStyleSheet("background: #252550; max-height: 1px; border: none;")
        sep_row = QHBoxLayout()
        sep_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sep_row.addWidget(sep)
        layout.addLayout(sep_row)

        # 功能卡片
        card_row = QHBoxLayout()
        card_row.setSpacing(36)
        card_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        single_btn = self._card("[>]", "单视频下载", "分享链接下载视频/图集/实况")
        single_btn.clicked.connect(self.single_clicked.emit)
        card_row.addWidget(single_btn)

        hp_btn = self._card("[=]", "主页批量下载", "用户主页链接下载全部作品")
        hp_btn.clicked.connect(self.homepage_clicked.emit)
        card_row.addWidget(hp_btn)

        layout.addLayout(card_row)
        layout.addStretch()

        # ── 登录状态（抖音专属） ──
        small = max(8, pt - 6)
        self._status_label = QLabel()
        self._status_label.setStyleSheet(f"color: #64748B; font-size: {small}px; padding: 8px 0;")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_cookie_status()
        layout.addWidget(self._status_label)

    def _card(self, icon: str, title: str, desc: str) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("modeBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumSize(font_scale(260), font_scale(190))

        cl = QVBoxLayout(btn)
        cl.setContentsMargins(20, 20, 20, 20)
        cl.setSpacing(8)

        pt = QApplication.instance().font().pointSize()
        icon_sz = font_scale(44)

        ic = QLabel(icon)
        ic.setStyleSheet(
            f"font-size:{pt+8}px; font-weight:800; color:#FFFFFF; "
            f"background:#1A1A1A; border-radius:{font_scale(12)}px; "
            f"min-width:{icon_sz}px; max-width:{icon_sz}px; "
            f"min-height:{icon_sz}px; max-height:{icon_sz}px;"
        )
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(ic)

        tl = QLabel(title)
        tl.setStyleSheet(f"font-size:{pt+2}px; font-weight:700; color:#F1F5F9;")
        cl.addWidget(tl)

        ds = QLabel(desc)
        ds.setStyleSheet(f"font-size:{max(10, pt-2)}px; color:#64748B;")
        cl.addWidget(ds)
        cl.addStretch()
        return btn

    # ── 登录状态 ──

    def _on_login_clicked(self):
        show_login_dialog(self)
        self.refresh_cookie_status()
        self.cookie_updated.emit()

    def refresh_cookie_status(self):
        cs = get_cookie_status()
        if cs["ok"]:
            dot, txt = "#22C55E", "已登录"
            click_hint = ""
            self._status_label.setCursor(Qt.CursorShape.ArrowCursor)
            self._status_label.mousePressEvent = None
        elif cs["length"] > 0:
            dot, txt = "#F59E0B", "登录可能已过期"
            click_hint = " [点击重新登录]"
            self._status_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self._status_label.mousePressEvent = lambda e: self._on_login_clicked()
        else:
            dot, txt = "#EF4444", "未登录"
            click_hint = " [点击登录]"
            self._status_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self._status_label.mousePressEvent = lambda e: self._on_login_clicked()

        pt = QApplication.instance().font().pointSize()
        self._status_label.setText(f"● {txt}{click_hint}")
        self._status_label.setStyleSheet(f"color: {dot}; font-size: {pt-1}pt; padding: 8px 0;")
