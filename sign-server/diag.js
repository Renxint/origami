// sign-server 环境诊断 + Puppeteer 启动测试
const fs = require('fs');
const path = require('path');
const os = require('os');

const log = (msg) => {
    const ts = new Date().toISOString().substring(11, 19);
    const line = `[${ts}] ${msg}`;
    console.error(line);
};

async function main() {
    log('=== DIAG START ===');
    log(`Node: ${process.version}`);
    log(`Platform: ${os.platform()} ${os.release()}`);
    log(`cwd: ${process.cwd()}`);
    log(`__dirname: ${__dirname}`);

    // 1. 检查 Puppeteer 模块
    try {
        const ppt = require.resolve('puppeteer-extra');
        log(`puppeteer-extra found: ${ppt}`);
    } catch (e) {
        log(`puppeteer-extra NOT FOUND: ${e.message}`);
    }

    try {
        const stealth = require.resolve('puppeteer-extra-plugin-stealth');
        log(`puppeteer-extra-plugin-stealth found: ${stealth}`);
    } catch (e) {
        log(`puppeteer-extra-plugin-stealth NOT FOUND: ${e.message}`);
    }

    // 2. 检查浏览器
    const candidates = [
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        (process.env.LOCALAPPDATA || '') + '\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
        'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    ];
    let exePath = null;
    for (const p of candidates) {
        const ok = fs.existsSync(p);
        log(`Browser: ${ok ? 'FOUND' : ' miss '} ${p}`);
        if (ok && !exePath) exePath = p;
    }
    if (!exePath) {
        log('FATAL: no browser found');
        return;
    }

    // 3. 检查浏览器能否直接运行
    log(`Testing direct launch: ${exePath}`);
    const { execFile } = require('child_process');
    execFile(exePath, ['--version'], { timeout: 15000 }, (err, stdout, stderr) => {
        if (err) {
            log(`Direct launch FAILED: ${err.message}`);
            log(`stderr: ${(stderr || '').substring(0, 300)}`);
        } else {
            log(`Direct launch OK: ${(stdout || '').trim()}`);
        }
    });
    await new Promise(r => setTimeout(r, 5000));

    // 4. 检查 PATH
    log(`PATH first 300: ${(process.env.PATH || '').substring(0, 300)}`);

    // 5. 尝试 puppeteer.launch()
    log('Attempting puppeteer.launch()...');
    try {
        const puppeteer = require('puppeteer-extra');
        const StealthPlugin = require('puppeteer-extra-plugin-stealth');
        puppeteer.use(StealthPlugin());

        log(`Launching: ${exePath}`);
        const browser = await puppeteer.launch({
            headless: 'new',
            executablePath: exePath,
            args: ['--no-sandbox', '--disable-blink-features=AutomationControlled',
                   '--enable-logging', '--v=1'],
            timeout: 45000,
            dumpio: true,  // pipe browser stdout/stderr to node
        });
        log(`PUPPETEER OK: ${await browser.version()}`);

        // 6. 测试页面
        const page = await browser.newPage();
        log('Navigating to douyin...');
        await page.goto('https://www.douyin.com/?recommend=1', { waitUntil: 'domcontentloaded', timeout: 30000 });
        log('Page loaded OK');
        await browser.close();
        log('=== DIAG SUCCESS ===');
    } catch (e) {
        log(`PUPPETEER FAILED: ${e.message}`);
        if (e.stack) {
            log(`Stack: ${e.stack.substring(0, 500)}`);
        }
        log('=== DIAG FAILED ===');
    }
}

main().catch(e => {
    log(`Unhandled: ${e.message}`);
    log('=== DIAG CRASHED ===');
});
