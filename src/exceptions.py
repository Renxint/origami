# -*- coding: utf-8 -*-
"""
Origami — 异常类体系

所有 Origami 异常继承自 OrigamiError，便于统一捕获和日志记录。
"""


class OrigamiError(Exception):
    """Origami 基础异常"""
    def __init__(self, message: str = "", code: str = ""):
        super().__init__(message)
        self.code = code


class CookieExpiredError(OrigamiError):
    """Cookie 过期或无效"""
    def __init__(self, message: str = "Cookie 已过期，请重新登录"):
        super().__init__(message, code="COOKIE_EXPIRED")


class CookieMissingError(OrigamiError):
    """Cookie 不存在"""
    def __init__(self, message: str = "未设置 Cookie，请先登录"):
        super().__init__(message, code="COOKIE_MISSING")


class RateLimitError(OrigamiError):
    """被限流"""
    def __init__(self, message: str = "请求过于频繁，请稍后重试"):
        super().__init__(message, code="RATE_LIMITED")


class ParseError(OrigamiError):
    """解析失败（链接/响应）"""
    def __init__(self, message: str = "解析失败"):
        super().__init__(message, code="PARSE_ERROR")


class SignServerError(OrigamiError):
    """签名服务异常（Node.js / Puppeteer）"""
    def __init__(self, message: str = "签名服务异常"):
        super().__init__(message, code="SIGN_SERVER_ERROR")


class DownloadError(OrigamiError):
    """下载失败"""
    def __init__(self, message: str = "下载失败"):
        super().__init__(message, code="DOWNLOAD_ERROR")


class NetworkError(OrigamiError):
    """网络异常"""
    def __init__(self, message: str = "网络连接失败"):
        super().__init__(message, code="NETWORK_ERROR")


class UnsupportedPlatformError(OrigamiError):
    """不支持的平台"""
    def __init__(self, message: str = "暂不支持该平台"):
        super().__init__(message, code="UNSUPPORTED_PLATFORM")
