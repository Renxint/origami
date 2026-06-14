/**
 * 抖音 收藏 API 代理 — Puppeteer 签名版
 *
 * 用法:
 *   node api-signed.js <cookie_file> [cursor]
 *
 * 输出（stdout）:
 *   纯 JSON 响应体
 */

const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
puppeteer.use(StealthPlugin());

const COOKIE_FILE = process.argv[2];
const CURSOR = process.argv[3] || '0';

if (!COOKIE_FILE) {
    console.error('用法: node api-signed.js <cookie_file> [cursor]');
    process.exit(1);
}

const COOKIE_STR = fs.readFileSync(COOKIE_FILE, 'utf-8').trim();

function findBrowser() {
    const candidates = [
        (process.env.LOCALAPPDATA || '') + '\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
        'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
        (process.env.LOCALAPPDATA || '') + '\\Microsoft\\Edge\\Application\\msedge.exe',
        'C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',
        (process.env.LOCALAPPDATA || '') + '\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',
        'C:\\Program Files\\Chromium\\Application\\chrome.exe',
        (process.env.LOCALAPPDATA || '') + '\\Chromium\\Application\\chrome.exe',
        (process.env.LOCALAPPDATA || '') + '\\Vivaldi\\Application\\vivaldi.exe',
        'C:\\Program Files\\Opera\\opera.exe',
    ];
    for (const p of candidates) {
        if (fs.existsSync(p)) return p;
    }
    try {
        const { execSync } = require('child_process');
        const result = execSync(
            'where /R "%ProgramFiles%" chrome.exe msedge.exe brave.exe 2>nul & ' +
            'where /R "%LOCALAPPDATA%" chrome.exe msedge.exe brave.exe 2>nul',
            { timeout: 5000, encoding: 'utf8', shell: 'cmd.exe' }
        ).trim();
        const lines = result.split(/\r?\n/).filter(l => l && fs.existsSync(l));
        if (lines.length > 0) return lines[0];
    } catch (e) {}
    try {
        const cacheDir = (process.env.LOCALAPPDATA || process.env.USERPROFILE + '/.cache') + '/puppeteer';
        if (fs.existsSync(cacheDir)) {
            for (const d of fs.readdirSync(cacheDir)) {
                const p = cacheDir + '/' + d + '/chrome-win64/chrome.exe';
                if (fs.existsSync(p)) return p;
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
    const launchOpts = {
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox'],
    };
    const exePath = findBrowser();
    if (exePath) {
        launchOpts.executablePath = exePath;
    } else {
        try {
            const p = require('puppeteer');
            const ep = await p.executablePath();
            if (ep) launchOpts.executablePath = ep;
        } catch(e) {}
    }

    const browser = await puppeteer.launch(launchOpts);
    const page = await browser.newPage();

    try {
        // Step 1: 首次加载 → 初始化 SDK
        await page.goto('https://www.douyin.com/?recommend=1', {
            waitUntil: 'domcontentloaded',
            timeout: 30000,
        });
        await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 30000 });
        await page.evaluate(() => {
            window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5 });
        });

        // Step 2: 注入 Cookie 后重新导航
        const cookies = COOKIE_STR.split(';').map(c => {
            const eqIdx = c.trim().indexOf('=');
            if (eqIdx < 0) return null;
            return {
                name: c.substring(0, eqIdx).trim(),
                value: c.substring(eqIdx + 1).trim(),
                domain: '.douyin.com',
                path: '/',
            };
        }).filter(Boolean);
        await page.setCookie(...cookies);

        await page.goto('https://www.douyin.com/?recommend=1', {
            waitUntil: 'domcontentloaded',
            timeout: 30000,
        });
        await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 30000 });
        await page.evaluate(() => {
            window.bdms.init({
                aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5,
                paths: ['^/aweme/v1/', '^/aweme/v2/', '/douplus/', '/v1/message/', '^/live/', '^/captcha/', '^/ecom/', '^/luna/pc']
            });
        });

        // Step 3: 注入指纹
        await page.evaluate((fp) => {
            if (fp.webid) localStorage.setItem('webid', fp.webid);
            if (fp.verifyFp) localStorage.setItem('verifyFp', fp.verifyFp);
            if (fp.fp) localStorage.setItem('fp', fp.fp);
            if (fp.uifid) localStorage.setItem('uifid', fp.uifid);
        }, FINGERPRINTS);

        // Step 4: POST 收藏 API
        const result = await page.evaluate(async (cursor) => {
            try {
                const r = await fetch('https://www.douyin.com/aweme/v1/web/favorite/listcollection/', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: 'count=10&cursor=' + cursor,
                });
                return await r.json();
            } catch (e) {
                return { _error: e.message };
            }
        }, CURSOR);

        console.log(JSON.stringify(result));
    } catch (e) {
        console.log(JSON.stringify({ _error: e.message }));
    } finally {
        await browser.close();
    }
})();
