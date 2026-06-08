/**
 * Origami 扫码登录服务
 *
 * 用 Puppeteer + stealth 打开抖音移动版，截取二维码图片，
 * 轮询检测登录状态，成功时输出 Cookie。
 *
 * 输出格式（stdout，每行一条 JSON）：
 *   {"status":"qrcode","file":"/tmp/qr.png","token":"xxx"}
 *   {"status":"waiting"}
 *   {"status":"scanned"}
 *   {"status":"success","cookie":"sessionid=xxx; ttwid=yyy"}
 *   {"status":"error","message":"..."}
 *
 * 用法:
 *   node login-server.js <qrcode_output.png>
 */

const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
puppeteer.use(StealthPlugin());

const QR_OUTPUT = process.argv[2] || './qr_temp.png';

const MOBILE_UA = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36';
const VIEWPORT = { width: 390, height: 844, deviceScaleFactor: 2 };

function emit(obj) {
    process.stdout.write(JSON.stringify(obj) + '\n');
}

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
    let browser;
    try {
        const exePath = findBrowser();
        const launchOpts = {
            headless: 'new',
            args: ['--no-sandbox', '--disable-setuid-sandbox'],
        };
        if (exePath) launchOpts.executablePath = exePath;

        browser = await puppeteer.launch(launchOpts);
        const page = await browser.newPage();
        await page.setUserAgent(MOBILE_UA);
        await page.setViewport(VIEWPORT);

        // 导航到抖音
        await page.goto('https://www.douyin.com/', {
            waitUntil: 'networkidle2',
            timeout: 30000,
        });

        // 等待二维码出现（抖音移动版登录弹窗）
        // 尝试多种选择器
        let qrElement = null;
        const selectors = [
            'img[src*="qrcode"]',
            'img[class*="qr"]',
            'img[class*="Qr"]',
            'canvas[class*="qr"]',
            'canvas[class*="Qr"]',
            '.qrcode-img',
            '[class*="qrcode"] img',
            '[class*="QR"] img',
            // 抖音专用
            '.login-modal img',
            '[class*="login"] canvas',
            '[class*="Login"] img',
        ];

        for (const sel of selectors) {
            try {
                await page.waitForSelector(sel, { timeout: 3000 });
                qrElement = await page.$(sel);
                if (qrElement) {
                    const box = await qrElement.boundingBox();
                    if (box && box.width > 100 && box.height > 100) {
                        break;
                    }
                    qrElement = null;
                }
            } catch (_) {}
        }

        if (!qrElement) {
            // 兜底：截取页面中央区域作为二维码
            emit({ status: 'qrcode_fallback', file: QR_OUTPUT });
            await page.screenshot({ path: QR_OUTPUT, clip: {
                x: 50, y: 200, width: 290, height: 290
            }});
        } else {
            // 截取二维码元素
            await qrElement.screenshot({ path: QR_OUTPUT });
            emit({ status: 'qrcode', file: QR_OUTPUT });
        }

        // 轮询登录（最多 120 秒）
        for (let i = 0; i < 60; i++) {
            await new Promise(r => setTimeout(r, 2000));

            const cookies = await page.cookies();
            const sessionCookie = cookies.find(c => c.name === 'sessionid');
            const ttwidCookie = cookies.find(c => c.name === 'ttwid');

            if (sessionCookie && ttwidCookie) {
                const allCookies = cookies
                    .filter(c => c.domain.includes('douyin.com'))
                    .map(c => `${c.name}=${c.value}`)
                    .join('; ');
                emit({ status: 'success', cookie: allCookies });
                await browser.close();
                process.exit(0);
            }

            // 检查是否已扫码
            const hasLogin = await page.evaluate(() => {
                return document.cookie.indexOf('sessionid=') !== -1;
            });
            if (hasLogin) {
                emit({ status: 'scanned' });
            }
        }

        emit({ status: 'error', message: '登录超时，请重试' });

    } catch (e) {
        emit({ status: 'error', message: e.message });
    } finally {
        if (browser) await browser.close();
        process.exit(0);
    }
})();
