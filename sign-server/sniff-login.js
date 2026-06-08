/**
 * 抖音登录流程网络抓包
 *
 * 拦截页面加载 + 登录弹窗期间的所有网络请求，
 * 输出 URL、方法、请求头、响应体等完整信息。
 *
 * 用法:
 *   node sniff-login.js > login_traffic.json
 */

const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
puppeteer.use(StealthPlugin());

const MOBILE_UA = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36';
const VIEWPORT = { width: 390, height: 844, deviceScaleFactor: 2 };

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
    const allRequests = [];
    const allResponses = [];

    const exePath = findBrowser();
    const launchOpts = {
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox'],
    };
    if (exePath) launchOpts.executablePath = exePath;

    const browser = await puppeteer.launch(launchOpts);
    const page = await browser.newPage();
    await page.setUserAgent(MOBILE_UA);
    await page.setViewport(VIEWPORT);

    // 拦截所有请求
    await page.setRequestInterception(true);
    page.on('request', (req) => {
        const entry = {
            type: 'request',
            url: req.url(),
            method: req.method(),
            headers: req.headers(),
            postData: req.postData() || null,
            resourceType: req.resourceType(),
        };
        allRequests.push(entry);
        // 实时输出关键请求
        if (req.url().includes('qrcode') || req.url().includes('qr') ||
            req.url().includes('login') || req.url().includes('sso') ||
            req.url().includes('passport') || req.url().includes('token') ||
            req.url().includes('check')) {
            console.error(`[REQ] ${req.method()} ${req.url().substring(0, 150)}`);
            if (req.postData()) console.error(`  POST: ${req.postData().substring(0, 200)}`);
        }
        req.continue();
    });

    // 拦截所有响应
    page.on('response', async (resp) => {
        const url = resp.url();
        const entry = {
            type: 'response',
            url: url,
            status: resp.status(),
            headers: resp.headers(),
        };
        // 对关键请求抓取响应体
        if (url.includes('qrcode') || url.includes('qr') ||
            url.includes('login') || url.includes('sso') ||
            url.includes('passport') || url.includes('check_qr')) {
            try {
                const body = await resp.text();
                entry.body = body.substring(0, 5000);
                console.error(`[RESP] ${resp.status()} ${url.substring(0, 120)}`);
                console.error(`  Body: ${body.substring(0, 500)}`);
            } catch (_) {}
        }
        allResponses.push(entry);
    });

    // 导航
    console.error('Navigating to douyin.com...');
    await page.goto('https://www.douyin.com/', {
        waitUntil: 'networkidle2',
        timeout: 30000,
    });

    // 等待页面稳定
    await new Promise(r => setTimeout(r, 5000));

    // 截图页面看看登录弹窗在哪
    await page.screenshot({ path: './sniff_fullpage.png' });
    console.error('Full page screenshot saved to sniff_fullpage.png');

    // 获取页面 cookie
    const cookies = await page.cookies();
    console.error('Page cookies:');
    cookies.forEach(c => console.error(`  ${c.name}=${c.value.substring(0, 30)}... (domain=${c.domain})`));

    // 输出所有与 qrcode/login/sso 相关的请求
    console.log(JSON.stringify({
        relevantRequests: allRequests.filter(r =>
            r.url.includes('qrcode') || r.url.includes('qr') ||
            r.url.includes('login') || r.url.includes('sso') ||
            r.url.includes('passport') || r.url.includes('token') ||
            r.url.includes('check') || r.url.includes('verify')
        ),
        relevantResponses: allResponses.filter(r =>
            r.url.includes('qrcode') || r.url.includes('qr') ||
            r.url.includes('login') || r.url.includes('sso') ||
            r.url.includes('passport') || r.url.includes('check_qr')
        ),
        allCookies: cookies.map(c => ({
            name: c.name, value: c.value.substring(0, 50),
            domain: c.domain, httpOnly: c.httpOnly,
        })),
    }, null, 2));

    await browser.close();
})();
