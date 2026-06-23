/**
 * Origami v2 — Frontend API Bridge
 *
 * 替代 QWebChannel，通过 fetch() + WebSocket 与后端通信。
 * 所有页面引用此文件即可调用后端 API。
 */

// 自动检测 API 地址
var API_BASE = 'http://127.0.0.1:8765';
var WS_BASE = 'ws://127.0.0.1:8765';

// 优先：页面被 server 加载 → 取当前 origin
if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
    API_BASE = window.location.origin;
    WS_BASE = window.location.origin.replace('http', 'ws');
}

// 桌面模式：pywebview 会注入正确的地址
async function _initApiBase() {
    if (typeof window.pywebview !== 'undefined' && window.pywebview.api) {
        try {
            API_BASE = await window.pywebview.api.getApiBase();
            WS_BASE = await window.pywebview.api.getWsUrl();
        } catch(e) {}
    }
}

let _ws = null;
let _eventHandlers = {};

// ═══════════ WebSocket 实时事件 ═══════════

function wsConnect() {
    if (_ws && _ws.readyState === WebSocket.OPEN) return;
    _ws = new WebSocket(WS_BASE + '/ws/events');
    _ws.onmessage = (e) => {
        try {
            const evt = JSON.parse(e.data);
            const handlers = _eventHandlers[evt.event] || [];
            handlers.forEach(fn => fn(evt));
            // 也触发 '*' 通配符
            (_eventHandlers['*'] || []).forEach(fn => fn(evt));
        } catch (_) {}
    };
    _ws.onclose = () => { _ws = null; setTimeout(wsConnect, 3000); };
}

function onEvent(eventName, fn) {
    if (!_eventHandlers[eventName]) _eventHandlers[eventName] = [];
    _eventHandlers[eventName].push(fn);
    wsConnect();
}

// ═══════════ HTTP API ═══════════

async function api(path, body) {
    const opts = {
        method: body ? 'POST' : 'GET',
        headers: { 'Content-Type': 'application/json' },
    };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(API_BASE + path, opts);
    return r.json();
}

// ═══════════ 便捷方法 ═══════════

const Origami = {
    // 版本
    version: () => api('/api/version'),

    // Cookie
    cookieStatus: () => api('/api/cookie'),

    // 登录（触发 WebView 扫码）
    login: () => api('/api/login/webview'),

    // 设置
    getSettings: () => api('/api/settings'),
    saveSettings: (s) => api('/api/settings', s),

    // 解析链接
    resolveUrl: (url) => api('/api/resolve-url', { url }),

    // 单作品
    fetchMedia: (itemId) => api('/api/fetch-media', { item_id: itemId }),

    // 下载（进度通过 WS 推送）
    download: (url, saveDir) => api('/api/download', { url, save_dir: saveDir }),

    // 作者
    fetchAuthor: (url) => api('/api/fetch-author', { url }),

    // 作品列表
    fetchPosts: (authorId, cursor, count) =>
        api('/api/fetch-posts', { author_id: authorId, cursor, count }),

    // 喜欢列表
    fetchLikes: (authorId, cursor, count) =>
        api('/api/fetch-likes', { author_id: authorId, cursor, count }),

    // 评论
    fetchComments: (awemeId, cursor, count) =>
        api('/api/fetch-comments', { aweme_id: awemeId, cursor, count }),

    // 文件操作
    browseFolder: () => api('/api/browse-folder'),
    openFolder: (path) => api('/api/open-folder', { path }),

    // WebSocket 事件
    onEvent,
    wsConnect,
};

// 页面加载时初始化 API 地址 + 连接 WebSocket
document.addEventListener('DOMContentLoaded', async function() {
    await _initApiBase();
    wsConnect();
});
