/**
 * 截全页 + 输出 DOM 结构，用于分析二维码位置
 */
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
puppeteer.use(StealthPlugin());

(async () => {
    const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36');
    await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });

    await page.goto('https://www.douyin.com/', { waitUntil: 'networkidle2', timeout: 30000 });
    await new Promise(r => setTimeout(r, 5000));

    // 全页截图
    await page.screenshot({ path: '../_fullpage.png', fullPage: true });
    console.log('Full page saved');

    // 分析 DOM：找所有大图片
    const imgs = await page.evaluate(() => {
        return Array.from(document.querySelectorAll('img')).map(img => ({
            src: (img.src || '').substring(0, 150),
            w: img.width || img.naturalWidth,
            h: img.height || img.naturalHeight,
            alt: img.alt || '',
            className: (img.className || '').substring(0, 80),
        })).filter(i => i.w > 50 || i.h > 50);
    });
    console.log('Large images:', JSON.stringify(imgs, null, 2));

    // 找所有 canvas
    const canvases = await page.evaluate(() => {
        return Array.from(document.querySelectorAll('canvas')).map(c => ({
            w: c.width, h: c.height,
            className: (c.className || '').substring(0, 80),
        }));
    });
    console.log('Canvases:', JSON.stringify(canvases, null, 2));

    // 找登录相关元素
    const loginEls = await page.evaluate(() => {
        const els = [];
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const text = (el.textContent || '').trim();
            const cls = (el.className || '') + ' ' + (el.id || '');
            if (text === '登录' || cls.includes('login') || cls.includes('Login') ||
                cls.includes('qrcode') || cls.includes('QR')) {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    els.push({
                        tag: el.tagName,
                        text: text.substring(0, 30),
                        cls: cls.substring(0, 100),
                        rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
                    });
                }
            }
        }
        return els.slice(0, 20);
    });
    console.log('Login-related elements:', JSON.stringify(loginEls, null, 2));

    await browser.close();
})();
