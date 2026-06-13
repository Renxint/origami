# -*- coding: utf-8 -*-
"""
Origami — 暗色 QSS 样式表

硬编码暗色主题样式，不再依赖色板 dict 切换。
原 build_stylesheet(DARK_THEME, base_pt) 的所有 token 已展开为实际值。
"""


def build_stylesheet(base_pt: int = 11) -> str:
    """
    返回暗色全局 QSS 样式表。

    参数:
        base_pt: 基础字号 (pt)
    """
    s = base_pt                       # body: 标签/按钮/输入框
    sm = max(7,  base_pt - 1)         # small: 提示/状态
    xs = max(6,  base_pt - 2)         # xsmall: 工具提示
    lg = base_pt + 2                  # large: 模式卡片
    mono = max(7, base_pt - 1)        # monospace: 日志

    py = max(2, base_pt // 3)        # 垂直内边距
    px = max(4, base_pt // 2 + 1)     # 水平内边距

    return f"""
/* ═══════════════ Origami 全局样式 ═══════════════ */
QMainWindow, QWidget {{
    background-color: #0A0A14;
    color: #F1F5F9;
    font-size: {s}pt;
}}

/* ── 输入框 ── */
QLineEdit {{
    background-color: #12122A;
    color: #F1F5F9;
    border: 1px solid #252550;
    border-radius: 8px;
    padding: {py+2}px {px+2}px;
    font-size: {s}pt;
}}
QLineEdit:focus {{
    border: 1px solid #E11D48;
    background: #161632;
}}
QLineEdit:disabled {{
    background: #0B0B1A;
    color: #475569;
    border-color: #1A1A2E;
}}

/* ── 主按钮 ── */
QPushButton {{
    background-color: #E11D48;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: {py+2}px {px+6}px;
    font-size: {s}pt;
    font-weight: bold;
}}
QPushButton:hover {{ background-color: #FF3566; }}
QPushButton:pressed {{ background: #C0183D; }}

/* ── 次按钮 ── */
QPushButton#secondaryBtn {{
    background-color: #18183A;
    border: 1px solid #252550;
    color: #F1F5F9;
    font-weight: normal;
}}
QPushButton#secondaryBtn:hover {{ background-color: #1E1E48; }}
QPushButton#secondaryBtn:pressed {{ background: #12122A; }}

/* ── 模式选择卡片 ── */
QPushButton#modeBtn {{
    background-color: #12122A;
    color: #F1F5F9;
    border: 2px solid #252550;
    border-radius: 16px;
    padding: {py+12}px;
    font-size: {lg}pt;
    text-align: left;
}}
QPushButton#modeBtn:hover {{
    background-color: #18183A;
    border-color: #E11D48;
}}
QPushButton#modeBtn:pressed {{
    background: #0B0B1A;
    border-color: #C0183D;
}}

/* ── 幽灵按钮 ── */
QPushButton#ghostBtn {{
    background: transparent;
    color: #94A3B8;
    border: 1px solid transparent;
    font-weight: normal;
}}
QPushButton#ghostBtn:hover {{
    background: #18183A;
    color: #F1F5F9;
    border-color: #252550;
}}

/* ── 禁用按钮 ── */
QPushButton:disabled {{
    background: #1A1A2E;
    color: #475569;
    border-color: #1A1A2E;
}}

/* ── 日志区域 ── */
QTextEdit {{
    background-color: #0B0B1A;
    color: #94A3B8;
    border: 1px solid #252550;
    border-radius: 8px;
    padding: {py}px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: {mono}pt;
}}

/* ── 进度条 ── */
QProgressBar {{
    background-color: #12122A;
    border: 1px solid #252550;
    border-radius: 4px;
    min-height: {max(4, py)}px;
    text-align: center;
    font-size: {max(7, s-1)}pt;
    color: #F1F5F9;
}}
QProgressBar::chunk {{
    background-color: #E11D48;
    border-radius: 3px;
}}

/* ── 标签 ── */
QLabel {{ color: #94A3B8; font-size: {s}pt; }}

/* ── 下拉框 ── */
QComboBox {{
    background-color: #12122A;
    color: #F1F5F9;
    border: 1px solid #252550;
    border-radius: 8px;
    padding: {py}px {px}px;
    font-size: {s}pt;
    min-width: 90px;
}}
QComboBox:hover {{ border: 1px solid #E11D48; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #94A3B8;
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: #12122A;
    color: #F1F5F9;
    border: 1px solid #252550;
    selection-background: #E11D48;
    outline: none;
    padding: 4px;
}}

/* ── 列表 ── */
QListWidget {{
    background-color: #12122A;
    border: 1px solid #252550;
    border-radius: 8px;
    padding: 4px;
    font-size: {s}pt;
    outline: none;
}}
QListWidget::item {{
    padding: 0px {px+2}px;
    border-radius: 6px;
    margin: 1px 0;
}}
QListWidget::item:selected {{ background: #E11D48; color: #FFFFFF; }}
QListWidget::item:hover {{ background: #18183A; }}

/* ── 分割器 ── */
QSplitter::handle {{ background-color: #1E1E48; width: 2px; }}

/* ── 滚动条 ── */
QScrollBar:vertical {{
    background: #0A0A14;
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #334155;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #475569; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{
    background: #0A0A14;
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: #334155;
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: #475569; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── 菜单 ── */
QMenu {{
    background: #12122A;
    color: #F1F5F9;
    border: 1px solid #252550;
    border-radius: 8px;
    padding: 4px;
    font-size: {sm}pt;
}}
QMenu::item {{
    padding: {py+1}px {px+10}px {py+1}px {px+2}px;
    border-radius: 4px;
}}
QMenu::item:selected {{ background: #E11D48; }}

/* ── 工具提示 ── */
QToolTip {{
    background: #1A1A3E;
    color: #F1F5F9;
    border: 1px solid #252550;
    border-radius: 6px;
    padding: {py+1}px {px+2}px;
    font-size: {xs}pt;
}}

/* ── 对话框 ── */
QMessageBox {{ background: #0A0A14; }}
QMessageBox QLabel {{ color: #F1F5F9; font-size: {s}pt; }}
QMessageBox QPushButton {{ min-width: 80px; padding: {py+1}px {px+4}px; }}

/* ── 滚动区域 ── */
QScrollArea {{ background: transparent; border: none; }}
"""
