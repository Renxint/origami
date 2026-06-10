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
from PyQt6.QtCore import Qt, pyqtSignal
from pathlib import Path

from src.fonts import font_scale
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

    def __init__(self):
        super().__init__()
        self._build()
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
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(28)

        pt = QApplication.instance().font().pointSize()

        # ── 标题 ──
        title = QLabel("Origami")
        title_sz = pt * 2 + 4
        title.setStyleSheet(
            f"font-size: {title_sz}px; font-weight: 800; color: #F1F5F9; "
            "letter-spacing: 2px;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        ver = QLabel(f"v{VERSION}")
        ver.setStyleSheet(
            f"font-size: {max(9, pt-6)}px; color: #000; background: #E11D48; "
            "border-radius: 4px; padding: 2px 8px;"
        )
        ver.setFixedHeight(font_scale(20))
        ver_row = QHBoxLayout()
        ver_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver_row.addWidget(ver)
        layout.addLayout(ver_row)

        sub = QLabel("选择平台开始下载")
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
        settings_btn.setMinimumWidth(font_scale(100))
        bottom.addWidget(settings_btn)

        feedback_btn = QPushButton("反馈")
        feedback_btn.setObjectName("secondaryBtn")
        feedback_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        feedback_btn.clicked.connect(self._send_feedback)
        feedback_btn.setMinimumWidth(font_scale(80))
        bottom.addWidget(feedback_btn)
        layout.addLayout(bottom)


    def _platform_card(self, name: str, svg_file: str, available: bool) -> QPushButton:
        """平台卡片：SVG 图标 + 名称"""
        btn = QPushButton()
        btn.setObjectName("modeBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor if available else Qt.CursorShape.ForbiddenCursor)
        btn.setMinimumSize(font_scale(180), font_scale(180))

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
        self.refresh_cookie_status()
        self.cookie_updated.emit()

    # ── 状态 ──

    def refresh_cookie_status(self):
        """仅检查状态，UI 显示在各平台页中"""
        pass

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
