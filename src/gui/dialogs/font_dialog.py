# -*- coding: utf-8 -*-
"""Origami — 字体选择对话框"""

from PyQt6.QtWidgets import (
    QDialog, QFontComboBox, QSpinBox, QLabel,
    QVBoxLayout, QHBoxLayout, QDialogButtonBox,
)
from PyQt6.QtGui import QFont

from src.fonts import font_scale


def choose_font_dialog(parent, current_font: QFont = None) -> tuple[bool, QFont | None]:
    """
    显示字体选择对话框。

    返回:
        (accepted: bool, font: QFont | None)
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle("字体设置")
    dlg.resize(400, 150)
    dlg.setStyleSheet("QDialog { background: #0A0A14; } QLabel { color: #F1F5F9; }")

    layout = QVBoxLayout(dlg)

    # 字体选择
    r1 = QHBoxLayout()
    r1.addWidget(QLabel("字体:"))
    combo = QFontComboBox()
    combo.setEditable(False)
    r1.addWidget(combo, 1)
    layout.addLayout(r1)

    # 字号选择
    r2 = QHBoxLayout()
    r2.addWidget(QLabel("字号:"))
    spin = QSpinBox()
    spin.setRange(8, 48)
    spin.setValue(10)
    r2.addWidget(spin)
    r2.addStretch()
    layout.addLayout(r2)

    # 预览
    preview = QLabel("预览效果 ABC 中文")
    preview.setMinimumHeight(font_scale(40))
    preview.setStyleSheet(
        "border: 1px solid #252550; border-radius: 8px; "
        "padding: 8px; background: #12122A;"
    )
    layout.addWidget(preview)

    if current_font is None:
        current_font = parent.font()
    combo.setCurrentFont(current_font)
    spin.setValue(current_font.pointSize())

    def on_change():
        f = combo.currentFont()
        f.setPointSize(spin.value())
        preview.setFont(f)

    combo.currentFontChanged.connect(on_change)
    spin.valueChanged.connect(on_change)
    on_change()

    btns = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    layout.addWidget(btns)

    if dlg.exec() == QDialog.DialogCode.Accepted:
        font = combo.currentFont()
        font.setPointSize(spin.value())
        return (True, font)
    return (False, None)
