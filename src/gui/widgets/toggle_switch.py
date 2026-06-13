# -*- coding: utf-8 -*-
"""
Origami — iOS 风格开关控件

借鉴 clawd-on-desk 的 .switch CSS 实现：
40x24px 胶囊，渐变动画，cubic-bezier 过渡。

用法:
    sw = ToggleSwitch()
    sw.toggled.connect(lambda on: print("ON" if on else "OFF"))
"""

from PyQt6.QtWidgets import QCheckBox, QApplication
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont

from src.gui.fonts import font_scale


class ToggleSwitch(QCheckBox):
    """iOS 风格开关，替代默认 QCheckBox"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()

    def _apply_style(self):
        pt = QApplication.instance().font().pointSize()
        w = font_scale(44, 12)
        h = font_scale(24, 12)
        self.setStyleSheet(f"""
            QCheckBox {{
                spacing: 10px;
                font-size: {pt}pt;
                color: #F1F5F9;
            }}
            QCheckBox::indicator {{
                width: {w}px;
                height: {h}px;
                border-radius: {h//2}px;
                border: 2px solid #334155;
                background-color: #1E1E3A;
            }}
            QCheckBox::indicator:checked {{
                background-color: #E11D48;
                border-color: #E11D48;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: #1E1E3A;
                border-color: #334155;
            }}
            QCheckBox::indicator:hover {{
                border-color: #94A3B8;
            }}
            QCheckBox::indicator:checked:hover {{
                border-color: #FF3566;
            }}
        """)
