/**
 * Origami — 常驻浏览器服务
 * 启动时初始化 SDK + Cookie，后续请求复用浏览器会话
 *
 * 用法: node server.js [port]
 * 默认端口: 18765
 *
 * 端点:
 *   POST /video?aweme_id=xxx  → 获取视频详情（含水印链接）
 *   POST /call?url=xxx         → 通用 API 代理
 *   GET  /health               → 健康检查
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

// ── 找浏览器 ──
function findBrowser() {
    console.error('[srv] findBrowser: searching...');

    // 1. 搜索 PATH（where 命令）
    for (const name of ['chrome', 'msedge', 'chromium']) {
        try {
            const result = require('child_process').execSync(`where ${name} 2>nul`, { encoding: 'utf-8', timeout: 3000 });
            const lines = result.trim().split('\n');
            for (const p of lines) {
                const exe = p.trim();
                if (exe && fs.existsSync(exe)) {
                    console.error(`[srv]   PATH -> ${exe}`);
                    return exe;
                }
            }
        } catch (e) { /* not found in PATH */ }
    }

    // 2. 搜索注册表
    const regKeys = [
        'HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe',
        'HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe',
        'HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe',
    ];
    for (const key of regKeys) {
        try {
            const result = require('child_process').execSync(
                `reg query "${key}" /ve 2>nul`, { encoding: 'utf-8', timeout: 3000 });
            const m = result.match(/REG_SZ\s+(.+)/);
            if (m && m[1] && fs.existsSync(m[1].trim())) {
                console.error(`[srv]   registry -> ${m[1].trim()}`);
                return m[1].trim();
            }
        } catch (e) { /* not in registry */ }
    }

    // 3. 兜底：常见路径
    const commonPaths = [
        process.env.LOCALAPPDATA + '\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
        'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    ];
    for (const p of commonPaths) {
        if (fs.existsSync(p)) {
            console.error(`[srv]   common -> ${p}`);
            return p;
        }
    }

    console.error('[srv]   NOT FOUND');
    return null;
}

// 启动时输出诊断信息
console.error(`[srv] Node version: ${process.version}`);
console.error(`[srv] cwd: ${process.cwd()}`);
console.error(`[srv] __dirname: ${__dirname}`);
console.error(`[srv] PATH first 300: ${(process.env.PATH || '').substring(0, 300)}`);

const PORT = parseInt(process.argv[2]) || 18765;
const COOKIE_FILE = path.resolve(__dirname, '..', 'data', 'Cookie.txt');

// 解码 base64 cookie
function loadCookie() {
    if (!fs.existsSync(COOKIE_FILE)) return '';
    const raw = fs.readFileSync(COOKIE_FILE, 'utf-8').trim();
    try { return Buffer.from(raw, 'base64').toString('utf-8'); }
    catch (e) { return raw; }
}

function cookieToArray(str) {
    return str.split(';').map(c => {
        const eq = c.trim().indexOf('=');
        if (eq < 0) return null;
        return { name: c.substring(0, eq).trim(), value: c.substring(eq + 1).trim(), domain: '.douyin.com', path: '/' };
    }).filter(Boolean);
}

// ── 浏览器状态 ──
let browser = null;
let page = null;
let sdkReady = false;

async function ensureBrowser() {
    if (browser && sdkReady) return page;

    const puppeteer = require('puppeteer-extra');
    const StealthPlugin = require('puppeteer-extra-plugin-stealth');
    puppeteer.use(StealthPlugin());

    const exePath = findBrowser();
    if (!exePath) throw new Error('No browser found');

    // 把浏览器目录加入 PATH（确保 Chrome/Edge 能找到自己的 DLL）
    const browserDir = path.dirname(exePath);
    if (!process.env.PATH.includes(browserDir)) {
        process.env.PATH = browserDir + ';' + (process.env.PATH || '');
        console.error(`[srv] prepended to PATH: ${browserDir}`);
    }

    // .exe 首次启动时 Defender 扫描可能拖慢 Chrome，加重试
    for (let attempt = 1; attempt <= 3; attempt++) {
        try {
            browser = await puppeteer.launch({
                headless: 'new',
                executablePath: exePath,
                args: ['--no-sandbox', '--disable-blink-features=AutomationControlled',
                       '--enable-logging', '--v=1'],
                timeout: 45000,
                dumpio: true,
                env: { PATH: process.env.PATH || '' },
            });
            break;
        } catch (e) {
            console.error(`[srv] launch attempt ${attempt} failed: ${e.message}`);
            if (attempt === 3) throw e;
            await new Promise(r => setTimeout(r, 3000));
        }
    }
    page = await browser.newPage();
    await page.evaluateOnNewDocument(() => {
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
    });
    await page.setViewport({ width: 1920, height: 1080 });
    await page.setUserAgent(
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36'
    );

    // SDK init (同 bootstrap.js)
    console.error('[srv] SDK init...');
    await page.goto('https://www.douyin.com/?recommend=1', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 30000 });
    await page.evaluate(() => { window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5 }); });

    // 注入 Cookie
    const cookie = loadCookie();
    if (cookie) {
        await page.goto('https://www.douyin.com/?recommend=1', { waitUntil: 'domcontentloaded', timeout: 30000 });
        await page.setCookie(...cookieToArray(cookie));
        await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 30000 });
        await page.evaluate(() => {
            window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5,
                paths: ['^/aweme/v1/', '^/aweme/v2/', '/douplus/', '^/live/', '^/captcha/', '^/ecom/', '^/luna/pc'] });
        });
    }

    // 注入指纹
    await page.evaluate(() => {
        localStorage.setItem('webid', '7385142668127356466');
        localStorage.setItem('verifyFp', 'verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD');
        localStorage.setItem('fp', 'verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD');
        localStorage.setItem('uifid', '7db62a7064f9afdec5c11ec3d692d7372ef41f2765cba0856d9e1b7b4940be6ed1b35a0f14230c327616b958a98d663b4443e89c625dc584c6b48e03ecc9c0ad');
    });

    sdkReady = true;
    console.error('[srv] Ready');
    return page;
}

// ── HTTP Server ──
http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    const url = new URL(req.url, `http://localhost:${PORT}`);

    // CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    if (req.method === 'OPTIONS') { res.writeHead(200); res.end('{}'); return; }

    try {
        // Health check
        if (url.pathname === '/health') {
            res.writeHead(200);
            res.end(JSON.stringify({ ok: true, sdkReady, cookie: !!loadCookie() }));
            return;
        }

        const p = await ensureBrowser();

        // Reload cookies if changed
        const cookie = loadCookie();
        if (cookie) await p.setCookie(...cookieToArray(cookie));

        // POST /video?aweme_id=xxx
        if (url.pathname === '/video' && url.searchParams.get('aweme_id')) {
            const awemeId = url.searchParams.get('aweme_id');
            console.error(`[srv] /video ${awemeId}`);
            const params = {
                aweme_id: awemeId, device_platform: 'webapp', aid: '6383', channel: 'channel_pc_web',
                pc_client_type: '1', version_code: '290100', version_name: '29.1.0',
                cookie_enabled: 'true', screen_width: '2560', screen_height: '1440',
                browser_language: 'zh-CN', browser_platform: 'Win32',
                browser_name: 'Smart+Lenovo+Browser', browser_version: '9.0.8.5161',
                browser_online: 'true', engine_name: 'Blink', engine_version: '141.0.0.0',
                os_name: 'Windows', os_version: '10', cpu_core_num: '32',
                device_memory: '8', platform: 'PC', downlink: '10', effective_type: '4g', round_trip_time: '50',
            };
            const q = Object.entries(params).map(([k, v]) => `${k}=${v}`).join('&');
            const apiUrl = `https://www.douyin.com/aweme/v1/web/aweme/detail/?${q}`;
            const result = await p.evaluate(async (u) => {
                try { const r = await fetch(u, { credentials: 'include' }); return await r.json(); }
                catch (e) { return { _error: e.message }; }
            }, apiUrl);
            res.writeHead(200);
            res.end(JSON.stringify(result));
            return;
        }

        // POST /call?url=xxx
        if (url.pathname === '/call' && url.searchParams.get('url')) {
            const apiUrl = url.searchParams.get('url');
            console.error(`[srv] /call ${apiUrl.substring(0, 80)}`);
            const result = await p.evaluate(async (u) => {
                try { const r = await fetch(u, { credentials: 'include' }); return await r.json(); }
                catch (e) { return { _error: e.message }; }
            }, apiUrl);
            res.writeHead(200);
            res.end(JSON.stringify(result));
            return;
        }

        res.writeHead(404);
        res.end(JSON.stringify({ _error: 'not_found' }));
    } catch (e) {
        console.error('[srv] Error:', e.message);
        sdkReady = false;
        res.writeHead(500);
        res.end(JSON.stringify({ _error: e.message }));
    }
}).listen(PORT, () => {
    console.error(`[srv] Listening on http://localhost:${PORT}`);
    ensureBrowser().catch(e => console.error('[srv] Init failed:', e.message));
});
