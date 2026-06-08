/**
 * 打开可见 Chrome，用户手动登录抖音，自动录制 HAR
 *
 * 用法:
 *   node record-har.js
 *
 * 浏览器打开后 → 用户扫码登录 douyin.com → 登录成功后关闭浏览器窗口
 * → HAR 自动保存到 ../login_har.json
 */

const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
puppeteer.use(StealthPlugin());

(async () => {
    const browser = await puppeteer.launch({
        headless: false,
        args: ['--no-sandbox', '--start-maximized'],
    });

    const page = await browser.newPage();

    // 启用 HAR 录制
    const client = await page.target().createCDPSession();
    await client.send('Network.enable');

    const requests = [];
    const responses = [];

    client.on('Network.requestWillBeSent', (params) => {
        requests.push({
            url: params.request.url,
            method: params.request.method,
            headers: params.request.headers,
            postData: params.request.postData || null,
            timestamp: params.timestamp,
        });
    });

    client.on('Network.responseReceived', (params) => {
        responses.push({
            url: params.response.url,
            status: params.response.status,
            headers: params.response.headers,
        });
    });

    // 监听响应体（关键 API）
    client.on('Network.loadingFinished', async (params) => {
        // 只抓取关键请求的响应体
        const req = requests.find(r => r.url.includes('qrcode') || r.url.includes('login') || r.url.includes('sso') || r.url.includes('check_qr') || r.url.includes('passport'));
        if (req) {
            try {
                const body = await client.send('Network.getResponseBody', {
                    requestId: params.requestId
                });
                req.responseBody = body.body;
            } catch (_) {}
        }
    });

    await page.goto('https://www.douyin.com/', {
        waitUntil: 'networkidle2',
        timeout: 30000,
    });

    console.log('=== 浏览器已打开 ===');
    console.log('请扫码登录抖音，登录成功后关闭浏览器窗口');
    console.log('HAR 将自动保存');

    // 等待浏览器关闭
    await new Promise((resolve) => {
        browser.on('disconnected', resolve);
    });

    // 保存 HAR
    const har = {
        log: {
            entries: requests.map((req, i) => ({
                request: {
                    method: req.method,
                    url: req.url,
                    headers: Object.entries(req.headers || {}).map(([name, value]) => ({ name, value })),
                    postData: req.postData ? { text: req.postData } : undefined,
                },
                response: responses[i] ? {
                    status: responses[i].status,
                    headers: Object.entries(responses[i].headers || {}).map(([name, value]) => ({ name, value })),
                    content: req.responseBody ? { text: req.responseBody } : undefined,
                } : undefined,
            })),
        },
    };

    const outPath = '../login_har.json';
    fs.writeFileSync(outPath, JSON.stringify(har, null, 2));
    console.log(`HAR saved: ${outPath} (${requests.length} requests)`);
})();
