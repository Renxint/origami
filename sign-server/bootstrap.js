/**
 * 抖音单视频数据提取 — 一次性 Puppeteer
 *
 * 完全对齐 puppeteer-server 的 /set_cookies 流程:
 *   导航 → 注入Cookie → 初始化SDK → 注入指纹 → 请求API → 输出JSON → 关闭
 *
 * 用法:
 *   node bootstrap.js <video_id> <cookie_string>
 */

const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
puppeteer.use(StealthPlugin());

const VIDEO_ID = process.argv[2];
let COOKIE_STR = process.argv[3];

if (!VIDEO_ID || !COOKIE_STR) {
    console.error('用法: node bootstrap.js <video_id> <cookie_string_or_file>');
    process.exit(1);
}

// 如果第三个参数是文件路径，从文件读取 Cookie
if (fs.existsSync(COOKIE_STR)) {
    COOKIE_STR = fs.readFileSync(COOKIE_STR, 'utf-8').trim();
}

/**
 * 自动检测系统中可用的浏览器路径
 */
function findBrowser() {
    // 1. 按优先级检查已知路径
    const candidates = [
        (process.env.LOCALAPPDATA || '') + '\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
        'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
        (process.env.LOCALAPPDATA || '') + '\\Microsoft\\Edge\\Application\\msedge.exe',
        'C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',
        'C:\\Program Files (x86)\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',
        (process.env.LOCALAPPDATA || '') + '\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',
        'C:\\Program Files\\Chromium\\Application\\chrome.exe',
        (process.env.LOCALAPPDATA || '') + '\\Chromium\\Application\\chrome.exe',
        (process.env.LOCALAPPDATA || '') + '\\Vivaldi\\Application\\vivaldi.exe',
        'C:\\Program Files\\Opera\\opera.exe',
        (process.env.LOCALAPPDATA || '') + '\\Programs\\Opera\\opera.exe',
    ];
    for (const p of candidates) {
        if (fs.existsSync(p)) {
            console.error('[bootstrap] found: ' + p);
            return p;
        }
    }
    // 2. 扫描 Program Files 下所有 chrome.exe / msedge.exe
    try {
        const { execSync } = require('child_process');
        const result = execSync(
            'where /R "%ProgramFiles%" chrome.exe msedge.exe brave.exe 2>nul & ' +
            'where /R "%LOCALAPPDATA%" chrome.exe msedge.exe brave.exe 2>nul',
            { timeout: 5000, encoding: 'utf8', shell: 'cmd.exe' }
        ).trim();
        const lines = result.split(/\r?\n/).filter(l => l && fs.existsSync(l));
        if (lines.length > 0) {
            console.error('[bootstrap] scanned: ' + lines[0]);
            return lines[0];
        }
    } catch (e) {}
    // 3. Puppeteer 缓存
    try {
        const cacheDir = (process.env.LOCALAPPDATA || process.env.USERPROFILE + '/.cache') + '/puppeteer';
        if (fs.existsSync(cacheDir)) {
            const dirs = fs.readdirSync(cacheDir);
            for (const d of dirs) {
                const chromePath = cacheDir + '/' + d + '/chrome-win64/chrome.exe';
                if (fs.existsSync(chromePath)) {
                    console.error('[bootstrap] cache: ' + chromePath);
                    return chromePath;
                }
            }
        }
    } catch (e) {}
    return null;
}

const FINGERPRINTS = {
    webid: '7385142668127356466',
    verifyFp: 'verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD',
    fp: 'verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD',
    uifid: '7db62a7064f9afdec5c11ec3d692d7372ef41f2765cba0856d9e1b7b4940be6ed1b35a0f14230c327616b958a98d663b4443e89c625dc584c6b48e03ecc9c0ad',
};

(async () => {
    let browser;
    try {
        console.error('[bootstrap] launching browser...');
        const os = require('os');
        const tmpDir = os.tmpdir() + '/origami-' + Date.now();
        require('fs').mkdirSync(tmpDir, { recursive: true });

        const launchOpts = {
            headless: 'new',
            args: [
                '--no-sandbox',
                '--disable-gpu',
                '--disable-blink-features=AutomationControlled',
                '--user-data-dir=' + tmpDir,
            ],
        };
        const browserPath = findBrowser();
        if (browserPath) {
            launchOpts.executablePath = browserPath;
            console.error('[bootstrap] using: ' + browserPath);
        } else {
            console.error('[bootstrap] auto-detecting browser...');
            try {
                const p = require('puppeteer');
                const ep = await p.executablePath();
                if (ep) { launchOpts.executablePath = ep; console.error('[bootstrap] puppeteer: ' + ep); }
            } catch(e) {}
        }

        browser = await puppeteer.launch(launchOpts);
        const page = await browser.newPage();

        await page.evaluateOnNewDocument(() => {
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        });
        await page.setViewport({ width: 1920, height: 1080 });
        await page.setUserAgent(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36'
        );

        // ==========================================
        // Step 1: 首次加载 → 初始化 SDK (对齐 puppeteer-server launchBrowser)
        // ⚠️ 必须先做一次不带 Cookie 的 init，第二次带 Cookie 的 init 才会生效
        // ==========================================
        console.error('[bootstrap] 首次加载抖音...');
        await page.goto('https://www.douyin.com/?recommend=1', {
            waitUntil: 'domcontentloaded',
            timeout: 60000,
        });
        await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 30000 });
        await page.evaluate(() => {
            window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5 });
        });
        console.error('[bootstrap] SDK 初次初始化 OK');

        // ==========================================
        // Step 2: 导航到抖音 → 注入Cookie → 重新初始化 SDK
        // (对齐 puppeteer-server /set_cookies)
        // ==========================================
        console.error('[bootstrap] 重新加载并注入Cookie...');
        await page.goto('https://www.douyin.com/?recommend=1', {
            waitUntil: 'domcontentloaded',
            timeout: 30000,
        });

        const cookies = COOKIE_STR.split(';').map(c => {
            const eq = c.trim().indexOf('=');
            if (eq < 0) return null;
            return {
                name: c.substring(0, eq).trim(),
                value: c.substring(eq + 1).trim(),
                domain: '.douyin.com',
                path: '/',
            };
        }).filter(Boolean);
        await page.setCookie(...cookies);
        console.error(`[bootstrap] Cookie 已注入 (${cookies.length}条)`);

        // ==========================================
        // Step 3: 初始化 SDK (Cookie 已就位)
        // ==========================================
        console.error('[bootstrap] 初始化 SDK...');
        await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 30000 });
        await page.evaluate(() => {
            window.bdms.init({
                aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5,
                paths: ['^/aweme/v1/', '^/aweme/v2/', '/douplus/', '/v1/message/', '^/live/', '^/captcha/', '^/ecom/', '^/luna/pc']
            });
        });
        console.error('[bootstrap] SDK 初始化 OK');

        // ==========================================
        // Step 3: 注入设备指纹
        // ==========================================
        await page.evaluate((fp) => {
            if (fp.webid) localStorage.setItem('webid', fp.webid);
            if (fp.verifyFp) localStorage.setItem('verifyFp', fp.verifyFp);
            if (fp.fp) localStorage.setItem('fp', fp.fp);
            if (fp.uifid) localStorage.setItem('uifid', fp.uifid);
        }, FINGERPRINTS);
        console.error('[bootstrap] 指纹已注入');

        // ==========================================
        // Step 4: 请求视频详情 (对齐 puppeteer-server /fetch)
        // ==========================================
        console.error('[bootstrap] 请求视频详情...');
        const params = {
            aweme_id: VIDEO_ID,
            device_platform: 'webapp',
            aid: '6383',
            channel: 'channel_pc_web',
            pc_client_type: '1',
            version_code: '290100',
            version_name: '29.1.0',
            cookie_enabled: 'true',
            screen_width: '2560',
            screen_height: '1440',
            browser_language: 'zh-CN',
            browser_platform: 'Win32',
            browser_name: 'Smart+Lenovo+Browser',
            browser_version: '9.0.8.5161',
            browser_online: 'true',
            engine_name: 'Blink',
            engine_version: '141.0.0.0',
            os_name: 'Windows',
            os_version: '10',
            cpu_core_num: '32',
            device_memory: '8',
            platform: 'PC',
            downlink: '10',
            effective_type: '4g',
            round_trip_time: '50',
        };
        const query = Object.entries(params).map(([k, v]) => `${k}=${v}`).join('&');
        const apiUrl = `https://www.douyin.com/aweme/v1/web/aweme/detail/?${query}`;

        const result = await page.evaluate(async (url) => {
            const resp = await fetch(url, { credentials: 'include' });
            const text = await resp.text();
            try {
                return JSON.parse(text);
            } catch (e) {
                return { _error: 'json_parse_failed', _raw: text.substring(0, 500) };
            }
        }, apiUrl);

        console.error('[bootstrap] 完成!');
        console.log(JSON.stringify(result));

    } catch (err) {
        console.error('[bootstrap] 错误:', err.message);
        console.log(JSON.stringify({ _error: err.message }));
    } finally {
        if (browser) {
            await browser.close();
            console.error('[bootstrap] 浏览器已关闭');
        }
    }
})();
