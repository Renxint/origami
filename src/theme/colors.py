# -*- coding: utf-8 -*-
"""
Origami — 主题色板（Cinema Dark 红黑配色）
"""

DARK_THEME = {
    "bg_primary": "#0A0A14",
    "bg_secondary": "#12122A",
    "bg_tertiary": "#0B0B1A",
    "bg_hover": "#18183A",
    "bg_input": "#12122A",
    "bg_input_focus": "#161632",

    "accent": "#E11D48",
    "accent_hover": "#FF3566",
    "accent_pressed": "#C0183D",
    "accent_bg": "#1A1030",

    "text_primary": "#F1F5F9",
    "text_secondary": "#94A3B8",
    "text_tertiary": "#64748B",
    "text_muted": "#475569",
    "text_white": "#FFFFFF",

    "border": "#252550",
    "border_hover": "#E11D48",
    "border_focus": "#E11D48",

    "success": "#22C55E",
    "warning": "#F59E0B",
    "error": "#EF4444",

    "scrollbar_bg": "#0A0A14",
    "scrollbar_handle": "#334155",
    "scrollbar_handle_hover": "#475569",

    "menu_bg": "#12122A",
    "menu_border": "#252550",
    "tooltip_bg": "#1A1A3E",

    "overlay_bg": "rgba(0,0,0,0.88)",

    "btn_secondary_bg": "#18183A",
    "btn_secondary_hover": "#1E1E48",
    "btn_secondary_pressed": "#12122A",
    "btn_disabled_bg": "#1A1A2E",
    "btn_disabled_text": "#475569",

    "card_bg": "#12122A",
    "card_border": "#252550",
    "card_radius": "12px",

    "input_radius": "8px",

    "separator": "#334155",
}

LIGHT_THEME = {
    "bg_primary": "#FFFEFB",
    "bg_secondary": "#F5F4F1",
    "bg_tertiary": "#E8E8E8",
    "bg_hover": "#D4EAF7",
    "bg_input": "#F5F4F1",
    "bg_input_focus": "#FFFEFB",

    "accent": "#00668C",
    "accent_hover": "#71C4EF",
    "accent_pressed": "#005577",
    "accent_bg": "#D4EAF7",

    "text_primary": "#1D1C1C",
    "text_secondary": "#313D44",
    "text_tertiary": "#888888",
    "text_muted": "#AAAAAA",
    "text_white": "#FFFFFF",

    "border": "#CCCBc8",
    "border_hover": "#00668C",
    "border_focus": "#00668C",

    "success": "#16A34A",
    "warning": "#D97706",
    "error": "#DC2626",

    "scrollbar_bg": "#FFFEFB",
    "scrollbar_handle": "#CCCBc8",
    "scrollbar_handle_hover": "#888888",

    "menu_bg": "#FFFEFB",
    "menu_border": "#CCCBc8",
    "tooltip_bg": "#F5F4F1",

    "overlay_bg": "rgba(255,254,251,0.92)",

    "btn_secondary_bg": "#F5F4F1",
    "btn_secondary_hover": "#CCCBc8",
    "btn_secondary_pressed": "#B0B0B0",
    "btn_disabled_bg": "#E8E8E8",
    "btn_disabled_text": "#888888",

    "card_bg": "#F5F4F1",
    "card_border": "#CCCBc8",
    "card_radius": "12px",

    "input_radius": "8px",

    "separator": "#CCCBc8",
}


def get_theme(name: str = "dark") -> dict:
    themes = {"dark": DARK_THEME, "light": LIGHT_THEME}
    return themes.get(name, DARK_THEME)
