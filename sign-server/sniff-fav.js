/**
 * 抓包脚本：导航到抖音收藏页，拦截 listcollection API 响应
 *
 * 用法: node sniff-fav.js
 * 输出: api-sniff.json（API 响应）+ api-sniff-url.txt（请求 URL）
 */

const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
puppeteer.use(StealthPlugin());

const COOKIE_FILE = process.argv[2] || 'D:/Pycharm环境/Claude/projects/Origami/data/Cookie.txt';

if (!fs.existsSync(COOKIE_FILE)) {
    console.error('Cookie 文件不存在: ' + COOKIE_FILE);
    console.error('请先在 Origami 里登录抖音');
    process.exit(1);
}

// 解码 base64 cookie
const encoded = fs.readFileSync(COOKIE_FILE, 'utf-8').trim();
let cookieStr = encoded;
try {
    cookieStr = Buffer.from(encoded, 'base64').toString('utf-8');
} catch (e) {}

console.error('[sniff] Cookie 长度:', cookieStr.length);

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
    if (!exePath) {
        console.error('[sniff] 未找到浏览器');
        process.exit(1);
    }
    console.error('[sniff] 浏览器:', exePath);

    const browser = await puppeteer.launch({
        headless: 'new',
        executablePath: exePath,
        args: ['--no-sandbox', '--disable-blink-features=AutomationControlled'],
    });

    const page = await browser.newPage();
    await page.setViewport({ width: 1920, height: 1080 });
    await page.setUserAgent(
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36'
    );

    // 收集所有 listcollection 响应
    const captured = [];

    page.on('response', async (resp) => {
        const url = resp.url();
        if (url.includes('listcollection')) {
            console.error('[sniff] 捕获:', url.substring(0, 100));
            try {
                const json = await resp.json();
                captured.push({ url, data: json });
                fs.writeFileSync('api-sniff.json', JSON.stringify(captured, null, 2));
                fs.writeFileSync('api-sniff-url.txt', url);
                console.error('[sniff] 已保存 api-sniff.json');
            } catch (e) {
                console.error('[sniff] JSON 解析失败:', e.message);
                const text = await resp.text();
                captured.push({ url, error: e.message, text: text.substring(0, 500) });
                fs.writeFileSync('api-sniff.json', JSON.stringify(captured, null, 2));
            }
        }
    });

    // 先加载首页初始化
    console.error('[sniff] 加载抖音首页...');
    await page.goto('https://www.douyin.com/', { waitUntil: 'domcontentloaded', timeout: 30000 });

    // 等待 SDK 就绪
    try {
        await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 15000 });
        await page.evaluate(() => {
            window.bdms.init({ aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5 });
        });
        console.error('[sniff] SDK 初始化 OK');
    } catch (e) {
        console.error('[sniff] SDK 未就绪:', e.message);
    }

    // 注入 Cookie + 重新初始化 SDK
    const cookies = cookieStr.split(';').map(c => {
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
    console.error('[sniff] Cookie 已注入 (' + cookies.length + ' 条)');

    // 重新加载首页让 Cookie 生效
    await page.goto('https://www.douyin.com/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    try {
        await page.waitForFunction(() => window.bdms && window.bdms.init, { timeout: 15000 });
        await page.evaluate(() => {
            window.bdms.init({
                aid: 6383, pageId: 6241, boe: false, ddrt: 8.5, ic: 8.5,
                paths: ['^/aweme/v1/', '^/aweme/v2/', '/douplus/', '^/live/', '^/captcha/', '^/ecom/', '^/luna/pc']
            });
        });
        console.error('[sniff] SDK 二次初始化 OK');
    } catch (e) {
        console.error('[sniff] SDK 二次初始化失败:', e.message);
    }

    // 导航到收藏→视频页面
    console.error('[sniff] 导航到收藏页...');
    await page.goto(
        'https://www.douyin.com/user/self?from_tab_name=main&showSubTab=video&showTab=favorite_collection',
        { waitUntil: 'domcontentloaded', timeout: 60000 }
    );

    // 等待页面发出 listcollection 请求
    console.error('[sniff] 等待 listcollection 请求...');
    await new Promise(r => setTimeout(r, 10000));

    if (captured.length === 0) {
        // 兜底：从页面 body 读
        const body = await page.evaluate(() => document.body.innerText);
        console.error('[sniff] 页面内容:', body.substring(0, 500));
        fs.writeFileSync('api-sniff.json', JSON.stringify({ no_capture: true, body: body.substring(0, 2000) }));
    }

    console.error('[sniff] 完成，共捕获', captured.length, '条');
    console.log(JSON.stringify(captured.length > 0 ? captured[0].data : { _error: 'no_capture' }));

    await browser.close();
})();
