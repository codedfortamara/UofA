// Render the SVG app icon to the PNG sizes Android's launcher needs.
// Run: node cello/tools/gen_icons.mjs
import pw from '/opt/node-tools/node_modules/playwright/index.js';
const { chromium } = pw;
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const iconsDir = resolve(here, '../web/icons');
const svg = readFileSync(resolve(iconsDir, 'icon.svg'), 'utf8');

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });

async function render(size, { maskable = false } = {}) {
  const page = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
  // A maskable icon must survive being cropped to a circle, so the artwork is
  // inset to the 80% safe zone and the background bleeds to the full square.
  const inset = maskable ? 0.74 : 1;
  await page.setContent(`<!doctype html><html><body style="margin:0;background:#003152">
    <div style="width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;background:#003152">
      <div style="width:${Math.round(size * inset)}px;height:${Math.round(size * inset)}px">${svg}</div>
    </div></body></html>`);
  const buf = await page.screenshot({ type: 'png' });
  await page.close();
  return buf;
}

for (const size of [192, 512]) {
  writeFileSync(resolve(iconsDir, `icon-${size}.png`), await render(size));
  console.log(`icon-${size}.png`);
}
writeFileSync(resolve(iconsDir, 'icon-maskable-512.png'), await render(512, { maskable: true }));
console.log('icon-maskable-512.png');

await browser.close();
