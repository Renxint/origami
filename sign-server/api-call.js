/**
 * 抖音 API 代理 — Puppeteer 一次性调用
 *
 * 接收 Cookie + API URL，在真实浏览器中执行 fetch()，输出 JSON 后退出。
 *
 * 用法:
 *   node api-call.js <cookie_file> <api_url>
 *
 * 输出（stdout）:
 *   纯 JSON 响应体
 */

const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
puppeteer.use(StealthPlugin());

const COOKIE_FILE = process.argv[2];
const API_URL = process.argv[3];

if (!COOKIE_FILE || !API_URL) {
    console.error('用法: node api-call.js <cookie_file> <api_url>');
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
        // 设置 Cookie（只保留 name/value/domain/path，去掉不相容字段）
        const cookies = COOKIE_STR.split('; ').map(item => {
            const eqIdx = item.indexOf('=');
            if (eqIdx < 1) return null;
            return {
                name: item.substring(0, eqIdx).trim(),
                value: item.substring(eqIdx + 1).trim(),
                domain: '.douyin.com',
                path: '/',
            };
        }).filter(c => c && c.name && c.value);
        await page.setCookie(...cookies);

        // 先访问抖音首页初始化 session
        await page.goto('https://www.douyin.com/', {
            waitUntil: 'domcontentloaded',
            timeout: 15000,
        });

        // 在浏览器上下文中调用 API
        const result = await page.evaluate(async (url) => {
            try {
                const r = await fetch(url, { credentials: 'include' });
                return await r.json();
            } catch (e) {
                return { _error: e.message };
            }
        }, API_URL);

        console.log(JSON.stringify(result));
    } catch (e) {
        console.log(JSON.stringify({ _error: e.message }));
    } finally {
        await browser.close();
    }
})();
