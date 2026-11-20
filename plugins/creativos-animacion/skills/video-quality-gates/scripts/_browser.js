// Where the browser measurements find playwright-core and a Chromium to drive.
//
// Shared by measure_captions.js, measure_beat_text.js, measure_stacking.js and
// podcast-captions/scripts/measure_caption_words.js, so the four look in the same
// places on a Mac, on Windows and on Linux:
//
// playwright — the npx cache, then this skill's own node_modules (the owner's Mac,
//   `npm install --prefix <skill> playwright-core`), then the per-user install that
//   `run_gates.py --doctor` makes in ~/.studio-video/node (never in git), then
//   a global one.
// browser — GATES_CHROME (a full path, to force one), then the installed Google
//   Chrome, then the Chrome HyperFrames downloads for its renders
//   (~/.cache/hyperframes/chrome), then puppeteer's, then Microsoft Edge (always
//   there on Windows), then playwright's own download if there is one. All of them
//   are Chromium: a line breaks in the same place in each.
//
//   node _browser.js --report     # prints {"playwright": …, "browser": …} (run_gates.py --doctor)
const fs = require('fs');
const T = (es, en) => (process.env.STUDIO_LANG === 'es' ? es : en);   // the user's language (_lang.py exports it)
const path = require('path');
const os = require('os');
const url = require('url');

function userNodeDir() {
  if (process.env.STUDIO_NODE_DIR) return process.env.STUDIO_NODE_DIR;
  const home = process.env.STUDIO_VIDEO_HOME || path.join(os.homedir(), '.studio-video');
  return path.join(home, 'node');
}

function loadPlaywright() {
  const roots = [];
  const npx = path.join(os.homedir(), '.npm', '_npx');
  try {
    for (const h of fs.readdirSync(npx)) {
      roots.push(path.join(npx, h, 'node_modules', 'playwright'));
    }
  } catch (e) { /* no npx cache */ }
  // next to the gates: npm install --prefix <skill> playwright-core (the owner's Mac)
  roots.push(path.join(__dirname, '..', 'node_modules', 'playwright-core'));
  roots.push(path.join(__dirname, '..', 'node_modules', 'playwright'));
  // per user, installed by run_gates.py --doctor (any computer, the plugin included)
  roots.push(path.join(userNodeDir(), 'node_modules', 'playwright-core'));
  roots.push('playwright-core');
  roots.push('playwright');
  for (const r of roots) {
    try {
      const pw = require(r);
      if (pw && pw.chromium) { pw.__from = r; return pw; }
    } catch (e) { /* keep looking */ }
  }
  return null;
}

function _version(dir) {
  const m = path.basename(dir).match(/(\d+(?:\.\d+)+)/);
  return m ? m[1].split('.').map(Number) : [0];
}

function _newestFirst(dirs) {
  return dirs.sort((a, b) => {
    const va = _version(a), vb = _version(b);
    for (let i = 0; i < Math.max(va.length, vb.length); i++) {
      const d = (vb[i] || 0) - (va[i] || 0);
      if (d) return d;
    }
    return 0;
  });
}

function _subdirs(dir) {
  try {
    return fs.readdirSync(dir).map((n) => path.join(dir, n))
      .filter((p) => { try { return fs.statSync(p).isDirectory(); } catch (e) { return false; } });
  } catch (e) { return []; }
}

// Chromium builds downloaded by HyperFrames and puppeteer: <root>/<platform>-<version>/<build>/<binary>
function downloadedChromes() {
  const win = process.platform === 'win32';
  const cache = path.join(os.homedir(), '.cache');
  const out = [];
  const shells = [path.join(cache, 'hyperframes', 'chrome', 'chrome-headless-shell'),
                  path.join(cache, 'puppeteer', 'chrome-headless-shell')];
  for (const root of shells) {
    for (const ver of _newestFirst(_subdirs(root))) {
      for (const build of _subdirs(ver)) {
        const bin = path.join(build, win ? 'chrome-headless-shell.exe' : 'chrome-headless-shell');
        if (fs.existsSync(bin)) out.push(bin);
      }
    }
  }
  for (const ver of _newestFirst(_subdirs(path.join(cache, 'puppeteer', 'chrome')))) {
    for (const build of _subdirs(ver)) {
      const cands = [path.join(build, 'chrome.exe'), path.join(build, 'chrome'),
        path.join(build, 'Google Chrome for Testing.app', 'Contents', 'MacOS', 'Google Chrome for Testing')];
      for (const bin of cands) if (fs.existsSync(bin)) { out.push(bin); break; }
    }
  }
  return out;
}

// Returns {browser, how}; throws when no Chromium can be started.
async function launch(pw) {
  const tries = [];
  if (process.env.GATES_CHROME) tries.push(['GATES_CHROME', { executablePath: process.env.GATES_CHROME }]);
  tries.push(['Google Chrome', { channel: 'chrome' }]);
  for (const bin of downloadedChromes()) tries.push([bin, { executablePath: bin }]);
  tries.push(['Microsoft Edge', { channel: 'msedge' }]);
  tries.push(['playwright chromium', {}]);
  const errors = [];
  for (const [how, opts] of tries) {
    try {
      const browser = await pw.chromium.launch(opts);
      return { browser, how };
    } catch (e) {
      errors.push(how + ': ' + String(e.message || e).split('\n')[0]);
    }
  }
  throw new Error(T('no pude abrir ningún Chromium (Chrome, el de HyperFrames, Edge): ',
                    'could not open any Chromium (Chrome, the HyperFrames one, Edge): ') + errors.join(' | '));
}

function fileUrl(p) {
  return url.pathToFileURL(path.resolve(p)).href;
}

module.exports = { loadPlaywright, launch, fileUrl, downloadedChromes, userNodeDir };

if (require.main === module && process.argv.includes('--report')) {
  (async () => {
    const pw = loadPlaywright();
    const rep = { playwright: pw ? pw.__from : null, version: null, browser: null, error: null,
                  node: process.version };
    if (pw) {
      try { rep.version = require(pw.__from + '/package.json').version; }
      catch (e) { /* unknown */ }
      try {
        const { browser, how } = await launch(pw);
        rep.browser = how;
        await browser.close();
      } catch (e) { rep.error = e.message; }
    } else {
      rep.error = T('playwright-core no está instalado', 'playwright-core is not installed');
    }
    console.log(JSON.stringify(rep));
  })();
}
