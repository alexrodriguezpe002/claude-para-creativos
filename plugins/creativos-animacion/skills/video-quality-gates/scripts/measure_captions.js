// Measure the caption cards in a real browser, with the real font loaded.
//
// The captions gate can count words, and a word count is not a line: CLA ep4
// shipped eleven two-line cards that passed the gate, and one that measured
// 952 of 952px — a pixel from breaking. Line count is a browser question, so
// this asks the browser: how many line boxes do this card's words sit on.
//
//   node measure_captions.js <project-dir>
//
// Prints one JSON object. Exit 3 means playwright is not installed here, which
// the Python gate reports as a WARN — never as a pass.
const fs = require('fs');
const T = (es, en) => (process.env.STUDIO_LANG === 'es' ? es : en);   // the user's language (_lang.py exports it)
const path = require('path');

// playwright and the browser come from the shared helper, the same for the four
// measurements on Mac, Windows and Linux (video-quality-gates/scripts/_browser.js)
const B = require('./_browser.js');

(async () => {
  const pw = B.loadPlaywright();
  if (!pw) { console.error(T('playwright no está instalado', 'playwright is not installed')); process.exit(3); }
  const proj = process.argv[2];
  const file = B.fileUrl(path.join(proj, 'index.html'));
  let browser;
  try { browser = (await B.launch(pw)).browser; }
  catch (e) { console.error(e.message); process.exit(3); }
  // The viewport has to be the composition's own frame: a teaser laid out in a
  // portrait window wraps every card and reports two lines that do not exist.
  let vw = 1080, vh = 1920;
  try {
    const html = fs.readFileSync(path.resolve(proj, 'index.html'), 'utf8');
    const root = (html.match(/id="root"[^>]*/) || [''])[0];
    const w = root.match(/data-width="([\d.]+)"/);
    const h = root.match(/data-height="([\d.]+)"/);
    if (w) vw = Math.round(parseFloat(w[1]));
    if (h) vh = Math.round(parseFloat(h[1]));
  } catch (e) { /* defaults */ }
  const page = await browser.newPage({ viewport: { width: vw, height: vh }, deviceScaleFactor: 1 });
  await page.goto(file, { waitUntil: 'load' });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise(r => setTimeout(r, 300));
  });
  const out = await page.evaluate(() => {
    const groups = Array.from(document.querySelectorAll('.caption-group, [class*="caption-group"]'));
    return groups.map((g, i) => {
      const holder = g.querySelector('.cap-text') || g;
      const words = Array.from(holder.querySelectorAll('.cap-word, span'));
      const tops = new Set(words.map(w => Math.round(w.offsetTop)));
      const cs = getComputedStyle(holder);
      const probe = holder.cloneNode(true);
      probe.style.maxWidth = 'none';
      probe.style.width = 'max-content';
      probe.style.position = 'absolute';
      probe.style.visibility = 'hidden';
      document.body.appendChild(probe);
      const natural = probe.getBoundingClientRect().width;
      probe.remove();
      // Two layout styles ship in these projects: the card wraps inside a
      // max-width (CLA), or it is `nowrap` inside a padded track (CLD). The
      // first breaks into two lines, the second overflows the frame silently —
      // so the limit is whichever one the card actually has.
      const pad = parseFloat(cs.paddingLeft || 0) + parseFloat(cs.paddingRight || 0);
      let maxW = Math.round(parseFloat(cs.maxWidth) || 0);
      // The line is the text holder's content box: a brand whose plate is the holder's
      // own padding and background (max-width 940, 44 px each side) has its words in
      // 852. The natural width above is the holder's border box, so the padding comes
      // off it; and off the max-width too when that counts the padding (border-box).
      // Only when the text has a holder of its own — a group that is its own holder
      // (padding on the track) keeps the old reading.
      const hpad = holder !== g
        ? pad + parseFloat(cs.borderLeftWidth || 0) + parseFloat(cs.borderRightWidth || 0) : 0;
      if (hpad > 0 && maxW && cs.boxSizing === 'border-box') maxW = Math.round(maxW - hpad);
      // The room the group itself leaves: its width less its own padding (and the holder's,
      // when the text has one). The line wraps at the narrower of that and the max-width —
      // the same number the grouping script's word measure uses
      // (podcast-captions/scripts/measure_caption_words.js), so a card the script built to
      // fit is measured against the width it was built for.
      // measured on a copy of the group whose text is one word wider than any frame: a group
      // of fixed width keeps it, a group that shrinks to its card grows to all the room it has
      const gcs = getComputedStyle(g);
      const room = g.cloneNode(true);
      room.removeAttribute('id');
      room.style.visibility = 'hidden';
      const rh = room.querySelector('.cap-text') || room;
      rh.textContent = 'W'.repeat(400);
      g.parentNode.appendChild(room);
      const roomW = room.getBoundingClientRect().width || 0;
      room.remove();
      const avail = Math.max(0, Math.round(roomW
        - parseFloat(gcs.paddingLeft || 0) - parseFloat(gcs.paddingRight || 0) - hpad));
      const limit = maxW && avail > 0 ? Math.min(maxW, avail) : (maxW || avail);
      return {
        i: i,
        text: words.length ? words.map(w => w.textContent.trim()).filter(Boolean).join(' ')
                          : (holder.textContent || '').replace(/\s+/g, ' ').trim(),
        lines: Math.max(tops.size, 1),
        width: Math.round(natural - hpad),
        maxWidth: maxW,
        avail: avail,
        limit: limit,
        nowrap: cs.whiteSpace.indexOf('nowrap') >= 0,
        fontSize: Math.round(parseFloat(cs.fontSize) || 0),
      };
    });
  });
  await browser.close();
  console.log(JSON.stringify({ groups: out }));
})().catch(e => { console.error(e.message); process.exit(4); });
