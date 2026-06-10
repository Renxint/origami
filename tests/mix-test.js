/**
 * 合集页 — 监听页面真实API请求
 */
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
puppeteer.use(StealthPlugin());

const COOKIE_FILE = process.argv[2];
const MIX_ID = '7514361363695683611';
if (!COOKIE_FILE) { console.error('用法: node mix-test.js <cookie_file>'); process.exit(1); }
const COOKIE_STR = fs.readFileSync(COOKIE_FILE, 'utf-8').trim();

(async () => {
    let browser;
    try {
        browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox', '--disable-blink-features=AutomationControlled'] });
        const page = await browser.newPage();
        await page.evaluateOnNewDocument(() => {
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        });

        // 拦截所有XHR/fetch请求
        const capturedRequests = [];
        await page.setRequestInterception(true);
        page.on('request', (req) => {
            const url = req.url();
            if (url.includes('/aweme/') || url.includes('/mix/') || url.includes('/collection/')) {
                capturedRequests.push({ url: url, method: req.method() });
            }
            req.continue();
        });

        // 注入Cookie
        const cookies = COOKIE_STR.split(';').map(c => {
            const eq = c.trim().indexOf('=');
            if (eq < 0) return null;
            return { name: c.substring(0, eq).trim(), value: c.substring(eq + 1).trim(), domain: '.douyin.com', path: '/' };
        }).filter(Boolean);
        await page.setCookie(...cookies);

        // 直接导航到合集页
        console.error('[mix] 导航到合集页...');
        await page.goto(`https://www.douyin.com/collection/${MIX_ID}`, {
            waitUntil: 'networkidle2',
            timeout: 60000,
        });

        // 等待页面加载
        await new Promise(r => setTimeout(r, 5000));

        console.error(`[mix] 捕获到 ${capturedRequests.length} 个API请求`);
        for (const req of capturedRequests) {
            console.error(`  ${req.method} ${req.url.substring(0, 150)}`);
        }

        // 尝试在页面上下文中直接获取数据
        const ssrData = await page.evaluate(() => {
            // 检查 __NUXT__ 或 __INITIAL_STATE__
            const nuxt = window.__NUXT__;
            const initState = window.__INITIAL_STATE__;
            return {
                hasNuxt: !!nuxt,
                hasInitState: !!initState,
            };
        });
        console.error('SSR data:', JSON.stringify(ssrData));

        // 尝试用 fetch 调用（页面上下文）
        const result = await page.evaluate(async (mixId) => {
            const urls = [
                `/aweme/v1/web/mix/aweme/list/?mix_id=${mixId}&count=5&cursor=0&device_platform=webapp&aid=6383`,
                `/aweme/v1/web/mix/list/aweme/?mix_id=${mixId}&count=5&cursor=0`,
                `/aweme/v1/web/aweme/mix/list/?mix_id=${mixId}&count=5&cursor=0`,
            ];
            const results = {};
            for (const u of urls) {
                try {
                    const r = await fetch(u);
                    results[u.substring(0, 60)] = await r.text().then(t => t.substring(0, 100));
                } catch (e) {
                    results[u.substring(0, 60)] = 'ERROR: ' + e.message;
                }
            }
            return results;
        }, MIX_ID);

        console.log(JSON.stringify({ captured: capturedRequests.length, apiResults: result }));
    } catch (e) {
        console.log(JSON.stringify({ _error: e.message }));
    } finally {
        if (browser) { await browser.close(); }
    }
})();
