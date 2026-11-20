// Width of every caption word in the project's own page — its caption CSS, its
// frame size, its font loaded — so the grouping measures exactly what the
// caption gate (video-quality-gates/scripts/measure_captions.js) will measure.
//
//   node measure_caption_words.js <project-dir> <spec.json>
//
// spec: { "words": ["Every", "company", …],
//         "dom": { "layer": "#cap-layer", "group": "caption-group",
//                  "text": "cap-text", "word": "cap-word" } }
// Prints { "loaded": bool, "font": "<computed font>", "limit": px, "gap": px,
//          "nowrap": bool, "widths": { "<word>": px, … } }.
// Exit 3: playwright or Chrome missing. Exit 4: the page has no caption CSS for
// those classes. Never a silent guess — a fallback face measures narrower.
const fs = require('fs');
const T = (es, en) => (process.env.STUDIO_LANG === 'es' ? es : en);   // the user's language (_lang.py exports it)
const path = require('path');

// playwright and the browser come from the shared helper, the same for the four
// measurements on Mac, Windows and Linux (video-quality-gates/scripts/_browser.js)
const B = require(path.join(__dirname, '..', '..', 'video-quality-gates', 'scripts', '_browser.js'));

(async () => {
  const pw = B.loadPlaywright();
  if (!pw) { console.error(T('playwright no está instalado', 'playwright is not installed')); process.exit(3); }
  const proj = process.argv[2];
  const spec = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
  const dom = Object.assign({ layer: '#cap-layer', group: 'caption-group', text: 'cap-text', word: 'cap-word' },
                            spec.dom || {});
  let vw = 1080, vh = 1920;
  try {
    const html = fs.readFileSync(path.resolve(proj, 'index.html'), 'utf8');
    const root = (html.match(/id="root"[^>]*/) || [''])[0];
    const w = root.match(/data-width="([\d.]+)"/);
    const h = root.match(/data-height="([\d.]+)"/);
    if (w) vw = Math.round(parseFloat(w[1]));
    if (h) vh = Math.round(parseFloat(h[1]));
  } catch (e) { /* defaults */ }
  let browser;
  try { browser = (await B.launch(pw)).browser; }
  catch (e) { console.error(e.message); process.exit(3); }
  const page = await browser.newPage({ viewport: { width: vw, height: vh }, deviceScaleFactor: 1 });
  await page.goto(B.fileUrl(path.join(proj, 'index.html')), { waitUntil: 'load' });
  const out = await page.evaluate(async ({ words, dom }) => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    await document.fonts.ready;
    const layer = document.querySelector(dom.layer) || document.getElementById('root') || document.body;
    const g = document.createElement('div');
    g.className = dom.group; g.id = '__caption_probe';
    let holder = g;
    if (dom.text) { holder = document.createElement('div'); holder.className = dom.text; g.appendChild(holder); }
    const a = document.createElement('span'); a.className = dom.word; a.textContent = 'Hamburgefonstiv';
    const b = document.createElement('span'); b.className = dom.word; b.textContent = 'x';
    holder.appendChild(a); holder.appendChild(b);
    layer.appendChild(g);
    const cs = getComputedStyle(a);
    const family = cs.fontFamily.split(',')[0].trim().replace(/^["']|["']$/g, '');
    const font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} "${family}"`;
    try { await document.fonts.load(font, 'Hamburgefonstiv 0123'); } catch (e) { /* checked below */ }
    await document.fonts.ready;
    await sleep(300);
    const widths = {};
    for (const w of words) { a.textContent = w; widths[w] = a.getBoundingClientRect().width; }
    await document.fonts.ready;
    for (const w of words) { a.textContent = w; widths[w] = a.getBoundingClientRect().width; }
    // the face counts as loaded only when the page declares it and it is loaded
    let declared = false, loaded = false;
    document.fonts.forEach((f) => {
      if (f.family.replace(/^["']|["']$/g, '') === family) {
        declared = true;
        if (f.status === 'loaded') loaded = true;
      }
    });
    const gap = parseFloat(cs.marginRight) || 0;
    const hcs = getComputedStyle(holder);
    const gcs = getComputedStyle(g);
    // The line is the holder's CONTENT box. A brand whose plate is the holder's own
    // padding and background (CLE's first build: max-width 940 with 44 px each side)
    // lays its words in 940 - 88 = 852 px when box-sizing is border-box, and in
    // whatever width is left after the padding when there is no max-width at all.
    const num = (v) => parseFloat(v) || 0;
    const padX = num(hcs.paddingLeft) + num(hcs.paddingRight) + num(hcs.borderLeftWidth) + num(hcs.borderRightWidth);
    // the room the group gives a line, read with one word wider than any frame inside it: a
    // group of fixed width (left/right set, the template's shape) keeps its width; a group
    // that shrinks to its text grows to all the room it has — never the probe's two words
    a.textContent = 'W'.repeat(400); b.textContent = '';
    const groupInner = g.getBoundingClientRect().width - num(gcs.paddingLeft) - num(gcs.paddingRight)
                       - (holder === g ? 0 : padX);
    let limit = parseFloat(hcs.maxWidth);
    if (!limit || isNaN(limit)) {
      limit = groupInner;
    } else {
      if (holder !== g && hcs.boxSizing === 'border-box') limit -= padX;
      // the group's own width can be the narrower of the two (a plate with padding
      // inside a group that already has side padding): the line wraps at the smaller
      if (groupInner > 0 && groupInner < limit) limit = groupInner;
    }
    const styled = cs.fontSize !== getComputedStyle(document.body).fontSize || cs.fontFamily !== getComputedStyle(document.body).fontFamily;
    g.remove();
    return { loaded: loaded, declared: declared, font: font, limit: Math.round(limit), gap: gap,
             nowrap: (hcs.whiteSpace || '').indexOf('nowrap') >= 0, styled: styled, widths: widths };
  }, { words: spec.words, dom });
  await browser.close();
  if (!out.styled) { console.error(T('la página no tiene CSS para .', 'the page has no CSS for .') + dom.word + T(' — primero el DOM y el CSS de la marca', ' — first the DOM and the brand\'s CSS')); process.exit(4); }
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e.message); process.exit(4); });
