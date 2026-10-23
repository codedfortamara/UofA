// End to end test of the real app in a real browser, with a synthesised cello
// tone fed through Chromium's fake microphone.
//
// This is the test that matters most: the unit tests prove the maths, but only
// this proves that getUserMedia, the AudioWorklet, the detector and the
// interface are actually wired together and show the right thing.
//
// Run: node cello/tools/verify_browser.mjs

import pw from '/opt/node-tools/node_modules/playwright/index.js';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const { chromium } = pw;
const here = dirname(fileURLToPath(import.meta.url));
const webDir = resolve(here, '../build/claudecello');
const toneDir = process.argv[2] || '/tmp/tones';
const PORT = 8731;
const CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

const server = spawn('python3', ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1'], {
  cwd: webDir,
  stdio: 'ignore',
});
const shutdown = () => { try { server.kill(); } catch { /* already gone */ } };
process.on('exit', shutdown);

await new Promise((r) => setTimeout(r, 900));

const CASES = [
  { file: 'd3_intune.wav', note: 'D', octave: '3', cents: 0, string: 'D', verdict: 'In tune', device: 'Done' },
  { file: 'a3_flat30.wav', note: 'A', octave: '3', cents: -30, string: 'A', verdict: 'Flat', device: 'Use the fine tuner' },
  { file: 'g2_sharp18.wav', note: 'G', octave: '2', cents: 18, string: 'G', verdict: 'Sharp', device: 'Use the fine tuner' },
  // 58.27 Hz really is A sharp 1, so the app naming it that is correct.
  { file: 'c2_flat200.wav', note: 'A#', octave: '1', cents: -200, string: 'C', verdict: 'Far too flat', device: 'Use the peg' },
  // F sharp 3 is a stopped note, 300 cents from the nearest open string. The
  // tuner must say so rather than claim the A string is catastrophically flat.
  { file: 'fsharp3_intune.wav', note: 'F#', octave: '3', cents: 0, string: null, stray: true },
];

let failures = 0;
function check(label, ok, extra = '') {
  if (!ok) failures++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label.padEnd(52)} ${extra}`);
}

console.log('\nEnd to end browser test, real audio pipeline\n');

for (const c of CASES) {
  const wav = resolve(toneDir, c.file);
  const browser = await chromium.launch({
    executablePath: CHROME,
    args: [
      '--use-fake-device-for-media-stream',
      '--use-fake-ui-for-media-stream',
      `--use-file-for-fake-audio-capture=${wav}%noloop`.replace('%noloop', ''),
      '--autoplay-policy=no-user-gesture-required',
      '--no-sandbox',
    ],
  });
  const context = await browser.newContext({ permissions: ['microphone'] });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(`http://127.0.0.1:${PORT}/index.html`);
  await page.waitForSelector('#mic-allow', { state: 'visible' });
  await page.click('#mic-allow');

  // Wait for the tuner to settle on a reading.
  await page.waitForFunction(
    () => {
      const n = document.querySelector('#tn-note');
      const r = document.querySelector('#tn-readout');
      return n && r && !r.classList.contains('quiet') && n.textContent.trim() !== '-' && n.textContent.trim() !== '–';
    },
    { timeout: 20000 }
  ).catch(() => {});
  await page.waitForTimeout(1600);

  const got = await page.evaluate(() => ({
    note: document.querySelector('#tn-note')?.textContent?.trim(),
    oct: document.querySelector('#tn-oct')?.textContent?.trim(),
    cents: document.querySelector('#tn-cents')?.textContent?.trim(),
    hz: document.querySelector('#tn-hz')?.textContent?.trim(),
    verdict: document.querySelector('#tn-verdict')?.textContent?.trim(),
    mode: document.querySelector('#tn-mode')?.textContent?.trim(),
    device: document.querySelector('#tn-advice .device')?.textContent?.trim(),
    advice: document.querySelector('#tn-advice p')?.textContent?.trim(),
  }));

  console.log(`\n${c.file}`);
  console.log(`   reads: ${got.note}${got.oct}  ${got.cents}  |  ${got.verdict}  |  ${got.mode}`);
  console.log(`   ${got.hz}`);
  if (got.device) console.log(`   advice: [${got.device}] ${got.advice}`);

  check('detects the right note name', got.note === c.note, `expected ${c.note}, got ${got.note}`);
  check('detects the right octave', got.oct === c.octave, `expected ${c.octave}, got ${got.oct}`);

  // Parse the cents reading back out of the interface text.
  const m = /([+−-])?\s*(\d+)\s*cents/.exec(got.cents || '');
  const shown = got.cents === 'spot on' ? 0 : m ? (m[1] === '+' ? 1 : -1) * Number(m[2]) : NaN;
  if (c.string) {
    check('cents reading is accurate', Math.abs(shown - c.cents) <= 4, `expected ${c.cents}, showed ${shown}`);
    check('picks the right string', (got.mode || '').includes(c.string), got.mode);
    check('verdict is right', got.verdict === c.verdict, `expected "${c.verdict}", got "${got.verdict}"`);
    check('recommends the right device', got.device === c.device, `expected "${c.device}", got "${got.device}"`);
  }
  if (c.stray) {
    check('a stopped note is not treated as a string', (got.mode || '') === 'Not an open string', got.mode);
    check('it names the note instead', (got.verdict || '').includes('F sharp'), got.verdict);
    check('it gives no peg or fine tuner advice', got.device === 'Not a tuning reading', got.device);
  }
  check('no page errors', errors.length === 0, errors.slice(0, 2).join(' | '));

  await browser.close();
}

// The lessons tab must render its course list.
{
  const browser = await chromium.launch({
    executablePath: CHROME,
    args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
           `--use-file-for-fake-audio-capture=${resolve(toneDir, 'd3_intune.wav')}`,
           '--autoplay-policy=no-user-gesture-required', '--no-sandbox'],
  });
  const context = await browser.newContext({ permissions: ['microphone'] });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${PORT}/index.html`);
  await page.click('#mic-allow');
  await page.waitForTimeout(1200);
  await page.click('#tab-learn');
  await page.waitForTimeout(400);

  const lessonCount = await page.locator('#view-learn [data-lesson]').count();
  check('\nlesson list renders every lesson', lessonCount === 14, `${lessonCount} lessons`);

  // Open lesson 3, which has a listening step, and walk to it.
  await page.locator('#view-learn [data-lesson="l3"]').click();
  await page.waitForTimeout(300);
  let sawListen = false;
  for (let i = 0; i < 8; i++) {
    if (await page.locator('#li-start').count()) { sawListen = true; break; }
    const next = page.locator('#ls-next');
    if (await next.count()) { await next.click(); await page.waitForTimeout(220); } else break;
  }
  check('a lesson reaches its listening step', sawListen);

  if (sawListen) {
    await page.click('#li-start');
    // The fake microphone is playing D3, which is what lesson 3 asks for, so
    // this should score a pass and advance the rep counter.
    await page.waitForFunction(() => document.querySelectorAll('#li-reps .pip.hit').length > 0, { timeout: 25000 })
      .then(() => check('listening step scores a correct note as a pass', true))
      .catch(() => check('listening step scores a correct note as a pass', false, 'no hit registered in 25 s'));
    const fb = await page.locator('#li-feedback .feedback').first().textContent().catch(() => '');
    console.log(`   feedback: ${(fb || '').trim().slice(0, 150)}`);
  }

  await page.click('#tab-practise');
  await page.waitForTimeout(400);
  const hasTools = await page.locator('#pr-drone').count();
  check('practice tools render', hasTools === 1);
  check('no page errors across tabs', errors.length === 0, errors.slice(0, 2).join(' | '));

  await browser.close();
}

shutdown();
console.log(`\n${failures === 0 ? 'All browser checks passed.' : failures + ' check(s) failed.'}\n`);
process.exit(failures === 0 ? 0 : 1);
