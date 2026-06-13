/**
 * 抖音 收藏 API 代理 — Puppeteer 签名版
 *
 * 收藏 listcollection 是 POST 端点，需要：
 *   - SDK 初始化 + 指纹注入（同 bootstrap）
 *   - POST body: count=10&cursor=0
 *   - referer: /user/self?showSubTab=video&showTab=favorite_collection
 *
 * 用法:
 *   node api-signed.js <cookie_file> <cursor>
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
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        (process.env.LOCALAPPDATA || '') + '\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
        'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    ];
    for (const p of candidates) {
        if (fs.existsSync(p)) return p;
    }
    return null;
}

const FINGERPRINTS = {
    webid: '7385142668127356466',
    verifyFp: 'verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD',
    fp: 'verify_moblf7od_dhWzqJO5_JDbN_44xu_86lf_8A6KqJjdqijD',
    uifid: '7db62a7064f9afdec5c11ec3d692d7372ef41f2765cba0856d9e1b7b4940be6ed1b35a0f14230c327616b958a98d663b4443e89c625dc584c6b48e03ecc9c0ad',
};

(async () => {
    const exePath = findBrowser();
    const launchOpts = {
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox'],
    };
    if (exePath) launchOpts.executablePath = exePath;

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

        // Step 2: 重新加载 + Cookie + 再初始化 SDK
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

        await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 30000 });
        await page.evaluate(() => {
            window.bdms.init({
                aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5,
                paths: ['^/aweme/v1/', '^/aweme/v2/', '/douplus/',
                        '^/live/', '^/captcha/', '^/ecom/', '^/luna/pc']
            });
        });

        // Step 3: 注入设备指纹
        await page.evaluate((fp) => {
            if (fp.webid) localStorage.setItem('webid', fp.webid);
            if (fp.verifyFp) localStorage.setItem('verifyFp', fp.verifyFp);
            if (fp.fp) localStorage.setItem('fp', fp.fp);
            if (fp.uifid) localStorage.setItem('uifid', fp.uifid);
        }, FINGERPRINTS);

        // Step 4: POST 请求收藏列表 API（XMLHttpRequest 版，SDK 会拦截）
        const result = await page.evaluate((cursor) => {
            return new Promise((resolve) => {
                const xhr = new XMLHttpRequest();
                const url = 'https://www.douyin.com/aweme/v1/web/aweme/listcollection/';
                const body = `count=20&cursor=${cursor}`;
                xhr.open('POST', url, true);
                xhr.withCredentials = true;
                xhr.setRequestHeader('accept', 'application/json, text/plain, */*');
                xhr.setRequestHeader('content-type', 'application/x-www-form-urlencoded; charset=UTF-8');
                xhr.setRequestHeader('referer', 'https://www.douyin.com/user/self?from_tab_name=main&showSubTab=video&showTab=favorite_collection');
                xhr.setRequestHeader('origin', 'https://www.douyin.com');
                const uifid = localStorage.getItem('uifid') || '';
                if (uifid) xhr.setRequestHeader('uifid', uifid);
                xhr.onload = () => {
                    try { resolve(JSON.parse(xhr.responseText)); }
                    catch(e) { resolve({_error:'parse', _raw: xhr.responseText.substring(0,500)}); }
                };
                xhr.onerror = () => resolve({_error: 'xhr_error'});
                xhr.timeout = 25000;
                xhr.ontimeout = () => resolve({_error: 'timeout'});
                xhr.send(body);
            });
        }, CURSOR);

        console.log(JSON.stringify(result));
    } catch (e) {
        console.log(JSON.stringify({ _error: e.message }));
    } finally {
        await browser.close();
    }
})();
