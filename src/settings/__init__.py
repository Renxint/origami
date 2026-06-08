# -*- coding: utf-8 -*-
"""Origami — 设置系统"""
from src.settings.schema import SETTINGS_SCHEMA, get_defaults, validate_value, validate_all
from src.settings.store import load, save, get, set, subscribe
