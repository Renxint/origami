# -*- coding: utf-8 -*-
"""
Origami — 样式表生成器

从主题色板 token 动态生成 QSS，所有颜色和间距参数化。
借鉴 clawd-on-desk 的 CSS 自定义属性思路。
"""

from PyQt6.QtWidgets import QApplication
from src.theme.colors import DARK_THEME


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


def build_stylesheet(theme: dict = None, base_pt: int = 11) -> str:
    """
    根据主题色板和基础字号动态生成全局 QSS 样式表。

    参数:
        theme: 主题色板 dict（DARK_THEME / LIGHT_THEME）
        base_pt: 基础字号 (pt)
    """
    if theme is None:
        theme = DARK_THEME

    t = theme  # 简写别名

    # 字号层级
    s  = base_pt                   # body: 标签/按钮/输入框
    sm = max(7,  base_pt - 1)      # small: 提示/状态
    xs = max(6,  base_pt - 2)      # xsmall: 工具提示
    lg = base_pt + 2               # large: 模式卡片
    mono = max(7, base_pt - 1)     # monospace: 日志

    py = max(2, base_pt // 3)      # 垂直内边距
    px = max(4, base_pt // 2 + 1)  # 水平内边距

    return f"""
/* ═══════════════ Origami 全局样式 ═══════════════ */
QMainWindow, QWidget {{
    background-color: {t['bg_primary']};
    color: {t['text_primary']};
    font-size: {s}pt;
}}

/* ── 输入框 ── */
QLineEdit {{
    background-color: {t['bg_input']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: {t['input_radius']};
    padding: {py+2}px {px+2}px;
    font-size: {s}pt;
}}
QLineEdit:focus {{
    border: 1px solid {t['border_focus']};
    background: {t['bg_input_focus']};
}}
QLineEdit:disabled {{
    background: {t['bg_tertiary']};
    color: {t['text_muted']};
    border-color: {t['btn_disabled_bg']};
}}

/* ── 主按钮 ── */
QPushButton {{
    background-color: {t['accent']};
    color: {t['text_white']};
    border: none;
    border-radius: {t['input_radius']};
    padding: {py+2}px {px+6}px;
    font-size: {s}pt;
    font-weight: bold;
}}
QPushButton:hover {{ background-color: {t['accent_hover']}; }}
QPushButton:pressed {{ background: {t['accent_pressed']}; }}

/* ── 次按钮 ── */
QPushButton#secondaryBtn {{
    background-color: {t['btn_secondary_bg']};
    border: 1px solid {t['border']};
    color: {t['text_primary']};
    font-weight: normal;
}}
QPushButton#secondaryBtn:hover {{ background-color: {t['btn_secondary_hover']}; }}
QPushButton#secondaryBtn:pressed {{ background: {t['btn_secondary_pressed']}; }}

/* ── 模式选择卡片 ── */
QPushButton#modeBtn {{
    background-color: {t['card_bg']};
    color: {t['text_primary']};
    border: 2px solid {t['card_border']};
    border-radius: 16px;
    padding: {py+12}px;
    font-size: {lg}pt;
    text-align: left;
}}
QPushButton#modeBtn:hover {{
    background-color: {t['bg_hover']};
    border-color: {t['accent']};
}}
QPushButton#modeBtn:pressed {{
    background: {t['bg_tertiary']};
    border-color: {t['accent_pressed']};
}}

/* ── 幽灵按钮 ── */
QPushButton#ghostBtn {{
    background: transparent;
    color: {t['text_secondary']};
    border: 1px solid transparent;
    font-weight: normal;
}}
QPushButton#ghostBtn:hover {{
    background: {t['bg_hover']};
    color: {t['text_primary']};
    border-color: {t['border']};
}}

/* ── 禁用按钮 ── */
QPushButton:disabled {{
    background: {t['btn_disabled_bg']};
    color: {t['btn_disabled_text']};
    border-color: {t['btn_disabled_bg']};
}}

/* ── 日志区域 ── */
QTextEdit {{
    background-color: {t['bg_tertiary']};
    color: {t['text_secondary']};
    border: 1px solid {t['border']};
    border-radius: {t['input_radius']};
    padding: {py}px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: {mono}pt;
}}

/* ── 进度条 ── */
QProgressBar {{
    background-color: {t['bg_secondary']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    min-height: {max(4, py)}px;
    text-align: center;
    font-size: {max(7, s-1)}pt;
    color: {t['text_primary']};
}}
QProgressBar::chunk {{
    background-color: {t['accent']};
    border-radius: 3px;
}}

/* ── 标签 ── */
QLabel {{ color: {t['text_secondary']}; font-size: {s}pt; }}

/* ── 下拉框 ── */
QComboBox {{
    background-color: {t['bg_input']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: {t['input_radius']};
    padding: {py}px {px}px;
    font-size: {s}pt;
    min-width: 90px;
}}
QComboBox:hover {{ border: 1px solid {t['accent']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {t['text_secondary']};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: {t['bg_secondary']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    selection-background: {t['accent']};
    outline: none;
    padding: 4px;
}}

/* ── 列表 ── */
QListWidget {{
    background-color: {t['bg_secondary']};
    border: 1px solid {t['border']};
    border-radius: {t['input_radius']};
    padding: 4px;
    font-size: {s}pt;
    outline: none;
}}
QListWidget::item {{
    padding: {py+2}px {px+2}px;
    border-radius: 6px;
    margin: 1px 0;
}}
QListWidget::item:selected {{ background: {t['accent']}; color: {t['text_white']}; }}
QListWidget::item:hover {{ background: {t['bg_hover']}; }}

/* ── 分割器 ── */
QSplitter::handle {{ background-color: {t['btn_secondary_hover']}; width: 2px; }}

/* ── 滚动条 ── */
QScrollBar:vertical {{
    background: {t['scrollbar_bg']};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t['scrollbar_handle']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {t['scrollbar_handle_hover']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{
    background: {t['scrollbar_bg']};
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {t['scrollbar_handle']};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {t['scrollbar_handle_hover']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── 菜单 ── */
QMenu {{
    background: {t['menu_bg']};
    color: {t['text_primary']};
    border: 1px solid {t['menu_border']};
    border-radius: 8px;
    padding: 4px;
    font-size: {sm}pt;
}}
QMenu::item {{
    padding: {py+1}px {px+10}px {py+1}px {px+2}px;
    border-radius: 4px;
}}
QMenu::item:selected {{ background: {t['accent']}; }}

/* ── 工具提示 ── */
QToolTip {{
    background: {t['tooltip_bg']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: {py+1}px {px+2}px;
    font-size: {xs}pt;
}}

/* ── 对话框 ── */
QMessageBox {{ background: {t['bg_primary']}; }}
QMessageBox QLabel {{ color: {t['text_primary']}; font-size: {s}pt; }}
QMessageBox QPushButton {{ min-width: 80px; padding: {py+1}px {px+4}px; }}

/* ── 滚动区域 ── */
QScrollArea {{ background: transparent; border: none; }}
"""
