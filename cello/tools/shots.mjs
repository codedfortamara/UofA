import pw from '/opt/node-tools/node_modules/playwright/index.js';
import { spawn } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const { chromium } = pw;
const here = dirname(fileURLToPath(import.meta.url));
const PORT = 8745;
const out = process.argv[3] || '/tmp/shots';
const server = spawn('python3', ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1'],
  { cwd: resolve(here, '../build/claudecello'), stdio: 'ignore' });
await new Promise(r => setTimeout(r, 900));
const browser = await chromium.launch({
  executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
         `--use-file-for-fake-audio-capture=${process.argv[2]}`,
         '--autoplay-policy=no-user-gesture-required', '--no-sandbox'],
});
const ctx = await browser.newContext({ viewport: { width: 412, height: 915 }, deviceScaleFactor: 2, permissions: ['microphone'] });
const page = await ctx.newPage();
await page.goto(`http://127.0.0.1:${PORT}/index.html`);
await page.click('#mic-allow');
await page.waitForTimeout(2500);
await page.screenshot({ path: `${out}/01-tuner.png` });
await page.click('#tab-learn'); await page.waitForTimeout(500);
await page.screenshot({ path: `${out}/02-lessons.png`, fullPage: false });
await page.locator('[data-lesson="l7"]').click(); await page.waitForTimeout(400);
await page.screenshot({ path: `${out}/03-lesson-info.png` });
for (let i = 0; i < 6; i++) {
  if (await page.locator('#li-start').count()) break;
  const n = page.locator('#ls-next'); if (await n.count()) { await n.click(); await page.waitForTimeout(250); } else break;
}
if (await page.locator('#li-start').count()) {
  await page.click('#li-start'); await page.waitForTimeout(6000);
  await page.screenshot({ path: `${out}/04-listening.png` });
}
await page.click('#tab-practise'); await page.waitForTimeout(500);
await page.screenshot({ path: `${out}/05-practise.png` });
await browser.close(); server.kill();
console.log('shots written');
