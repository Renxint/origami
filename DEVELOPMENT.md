# Origami v2 — Development Log

> v2 分支，目标：前后端分离架构，安装包 <100MB，跨平台

---

## 2026-06-24 — M1: Scaffolding (✅)

- [x] v2 branch, DEVELOPMENT.md, Claude memory
- [x] requirements.txt (PyQt6/WebEngine → playwright/aiohttp)
- [x] src/server.py (15 endpoints + WebSocket)
- [x] src/main.py (server/cli/dev modes)

## 2026-06-24 — M2: Playwright Signer (✅)

- [x] src/signer.py: BrowserFinder + StealthBrowser + SignerDaemon
- [x] src/webview_api.py: Node subprocess → HTTP daemon client
- [x] src/platforms/douyin.py: bootstrap.js → call_server('video')
- [x] sign-server/ deleted (-3271 lines, 13 files)

## 2026-06-24 — M3: Backend Integration + CLI (✅)

- [x] CLI single: `python -m src.main cli single "<url>" [--images 1,3-5]`
- [x] CLI batch: `python -m src.main cli batch "<url>" [--count N] [--dir PATH]`
- [x] WebSocket progress push (download_start → progress → download_done)
- [x] pywebview login endpoint (POST /api/login/webview)
- [x] CLI directory structure matches GUI (flat, hash naming, data/)
- [x] .downloaded.json tracker for incremental downloads
- [x] data/ 主页简介.md fully matches GUI
- [x] Avatar/cover image download with Cookie headers
- [x] Batch handles shared口令 text + short link resolution
- [x] Image range filter (--images 1,3,5-8)
- [x] Type detection (🎬 video / 🖼️ gallery)

## 2026-06-24 — M4: Web UI Foundation (🚧)

- [x] Cherry-pick HTML/CSS pages from feature/webui-migration
- [x] New ui/js/api.js: fetch() + WebSocket bridge (replaces QWebChannel)
- [x] server.py serves ui/ as static files
- [x] Platform icons + logo added
- [x] http://localhost:8765 → redirects to pages/home.html
- [ ] Rewrite each HTML page to use Origami.* API calls (in progress)

---

## Bug fixes (v2 + main)

- [x] main: preserve _img_filter when fetching fresh aweme (batch gallery selection)
- [x] v2: non-blocking daemon start (start(block=False))
- [x] v2: JS cookie injection via document.cookie
- [x] v2: likes endpoint → direct HTTP
- [x] v2: crash on cancel+restart (SingleDownloadThread cancel)
- [x] v2: SignerDaemon thread isolation (greenlet/Qt conflict)

## Commits

```
1bb3a75 fix: explicit / redirect to /pages/home.html
a4bc4cb fix: move static route after API routes
cad8663 fix: add platform icons + logo from webui branch
0421d78 fix: add index.html redirect to pages/home.html
756728c feat(v2): M4 — Web UI foundation with HTTP API bridge
... 18 commits total on v2
```
