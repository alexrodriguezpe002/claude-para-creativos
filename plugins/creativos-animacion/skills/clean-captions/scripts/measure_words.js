// Measures the rendered width of caption words in headless Chromium, with the
// caption font loaded. Called by `captions.py measure`; not meant to be run by hand.
//
//   node measure_words.js <probe.html> <words.json>
//
// probe.html has a #probe element styled exactly like a caption word. Prints a
// JSON object {word: width_px}. Finds puppeteer-core in the npx cache that
// HyperFrames uses and the Chromium headless shell from ms-playwright.
const fs = require('fs');
const path = require('path');
const os = require('os');

function findPuppeteer() {
  const roots = [];
  const npx = path.join(os.homedir(), '.npm', '_npx');
  try {
    for (const h of fs.readdirSync(npx)) roots.push(path.join(npx, h, 'node_modules', 'puppeteer-core'));
  } catch (e) { /* no npx cache */ }
  roots.push('puppeteer-core', 'puppeteer');
  for (const r of roots) {
    try { return require(r); } catch (e) { /* keep looking */ }
  }
  return null;
}

function findChrome() {
  const base = path.join(os.homedir(), 'Library', 'Caches', 'ms-playwright');
  let dirs = [];
  try { dirs = fs.readdirSync(base).filter(d => d.startsWith('chromium_headless_shell')).sort().reverse(); } catch (e) {}
  for (const d of dirs) {
    for (const sub of ['chrome-headless-shell-mac-arm64', 'chrome-headless-shell-mac-x64', 'chrome-headless-shell-linux64']) {
      const p = path.join(base, d, sub, 'chrome-headless-shell');
      if (fs.existsSync(p)) return p;
    }
  }
  return null;
}

(async () => {
  const [probe, wordsFile] = process.argv.slice(2);
  const pp = findPuppeteer();
  if (!pp) { console.error('puppeteer-core not found (run any `npx hyperframes` command once)'); process.exit(3); }
  const chrome = findChrome();
  if (!chrome) { console.error('Chromium headless shell not found in ~/Library/Caches/ms-playwright'); process.exit(3); }
  const words = JSON.parse(fs.readFileSync(wordsFile, 'utf8'));
  const browser = await pp.launch({ executablePath: chrome, headless: true, args: ['--allow-file-access-from-files'] });
  const page = await browser.newPage();
  await page.goto('file://' + path.resolve(probe));
  const out = await page.evaluate(async (ws) => {
    await document.fonts.ready;
    const fam = getComputedStyle(document.getElementById('probe')).fontFamily;
    const wt = getComputedStyle(document.getElementById('probe')).fontWeight;
    await document.fonts.load(wt + ' 64px ' + fam);
    const e = document.getElementById('probe');
    const o = {};
    for (const w of ws) { e.textContent = w; o[w] = Math.round(e.getBoundingClientRect().width * 100) / 100; }
    return o;
  }, words);
  console.log(JSON.stringify(out));
  await browser.close();
})().catch(e => { console.error(String(e && e.stack || e)); process.exit(1); });
