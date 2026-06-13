# -*- coding: utf-8 -*-
"""
Origami — 字体大小工具函数

从原 src/fonts.py 移入 gui/，纯 UI 工具，不属业务层。
"""

from PyQt6.QtWidgets import QApplication


def _app_font_pt() -> int:
    """获取当前应用字体大小 (pt)"""
    try:
        return QApplication.instance().font().pointSize()
    except Exception:
        return 17


def scaled_font(relative: int, base: int = 16) -> int:
    """根据当前字体缩放字号。relative=期望大小, base=基准字体(16px@12pt)"""
    return max(6, round(relative * _app_font_pt() / 12))


def font_scale(base_px: int, base_pt: int = 12) -> int:
    """根据当前应用字体大小缩放像素值"""
    try:
        pt = QApplication.instance().font().pointSize()
    except Exception:
        pt = base_pt
    return max(2, round(base_px * pt / base_pt))
