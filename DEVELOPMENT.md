# Origami v2 — Development Log

> v2 分支，目标：前后端分离架构，安装包 <100MB，跨平台

---

## 2026-06-24 — M1: Scaffolding (✅ completed)

- [x] v2 branch created from main
- [x] DEVELOPMENT.md created + Claude memory
- [x] requirements.txt updated (PyQt6/WebEngine/scrapling → playwright/aiohttp)
- [x] src/environ.py updated (Node constants → API_PORT/CHROME_PATH + backward compat)
- [x] src/server.py created (15 endpoints + WebSocket)
- [x] src/main.py created (server/cli/dev modes)
- [x] Verify: /api/version, /api/settings, /api/cookie, WS all working

---

## 2026-06-24 — M2: Playwright Signer (✅ completed)

- [x] src/signer.py created (~350 lines)
  - BrowserFinder: 六层发现 (PATH → registry → common paths → puppeteer cache)
  - StealthBrowser: playwright + stealth evasions + douyin bdms SDK
  - SignServer: 常驻浏览器，线程安全
  - one_shot_fetch(): 一次性调用 (bootstrap.js 等价)
- [x] src/webview_api.py rewritten (Node subprocess → playwright SignServer)
  - All public signatures unchanged (backward compat)
  - _kill_orphan_nodes, _kill_sign_port → no-op stubs
- [x] src/platforms/douyin.py updated
  - _call_sign_server(): subprocess bootstrap.js → call_server('video', ...)
  - Removed Node/subprocess imports
- [x] src/server.py API endpoints wired to real implementations
  - POST /api/resolve-url → DouyinAdapter.resolve_url
  - POST /api/fetch-media → DouyinAdapter.fetch_media
  - POST /api/fetch-posts → DouyinAdapter.fetch_posts
  - POST /api/fetch-author → DouyinAdapter.fetch_author
  - POST /api/fetch-likes → DouyinAdapter.fetch_likes
  - POST /api/fetch-comments → DouyinAdapter.fetch_comments
  - POST /api/download → simple sync path (M3 upgrade)
- [x] Verify: BrowserFinder → Edge found, cookie valid (4287 chars), imports OK
- [ ] sign-server/ directory NOT yet deleted (keep until end-to-end verified)

### Blockers
- (none)

### Decisions
- playwright-stealth for evasion (pip package, tested)
- Sync playwright API in SignServer (simpler, no asyncio mixing)
- Browser discovery mirrors JS findBrowser() exactly
- Cookie/fingerprint/SDK init flow mirrors bootstrap.js exactly
- Old environ constants kept as backward-compat aliases (will clean after sign-server/ delete)

---

## M3: Backend Integration + CLI (next)

- [ ] Add SSL cert fix at server startup
- [ ] Async download with thread pool + WebSocket progress push
- [ ] CLI mode: `python -m src.main cli single <url>` 
- [ ] CLI mode: `python -m src.main cli batch <url>`
- [ ] Login endpoint: pywebview WebView2 window
- [ ] Full error handling (no browser, SDK fail, cookie expired)
- [ ] Verify: end-to-end download via CLI, no GUI needed
