// Measure every text block inside every beat, in a real browser with the real
// font loaded, and report how many lines it actually renders on.
//
// The reason this exists: on CLA ep4 Snippet 4 the left column of a comparison
// split was authored as three lines with <br>, rendered as five, and pushed the
// text past the bottom of the divider it was supposed to sit beside. In the same
// project "TEN GRAND" was authored as one line inside a flex-centred box,
// wrapped to two, and the two lines came out left-aligned. Neither is visible in
// the markup and neither was caught by any gate — the browser is the only thing
// that knows where a line breaks.
//
//   node measure_beat_text.js <project-dir>
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
  try {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    await page.goto(file, { waitUntil: 'load' });
    const size = await page.evaluate(() => {
      const r = document.querySelector('[data-composition-id]') || document.body;
      return { w: +(r.getAttribute('data-width') || 1080), h: +(r.getAttribute('data-height') || 1920) };
    });
    await page.setViewportSize({ width: size.w, height: size.h });
    await page.evaluate(async () => { try { await document.fonts.ready; } catch (e) {} });
    await page.waitForTimeout(600);

    const out = await page.evaluate((SEL) => {
      const res = [];
      // the classes of every element between a text and its beat (an SVG <g class="primary">
      // names the role of the labels inside it, as an HTML block does)
      function chainOf(el, beat) {
        const c = [];
        let n = el;
        while (n && n !== beat) {
          const k = typeof n.className === 'string' ? n.className : (n.getAttribute && n.getAttribute('class')) || '';
          if (k) c.push(k);
          n = n.parentElement || n.parentNode;
        }
        return c.join(' ');
      }
      function opaque(node) {
        const bg = getComputedStyle(node).backgroundColor || '';
        const m = bg.match(/rgba?\(([^)]+)\)/);
        if (!m) return false;
        const parts = m[1].split(',').map((x) => parseFloat(x));
        return parts.length < 4 || parts[3] >= 0.98;
      }
      const beats = document.querySelectorAll(SEL);
      for (const beat of beats) {
        for (const el of beat.querySelectorAll('*')) {
          if (el.tagName === 'BR' || el.tagName === 'SVG') continue;
          if (el.closest('svg')) continue;
          const kids = [...el.children].filter((c) => c.tagName !== 'BR');
          if (kids.length) continue;                       // not a leaf text block
          const text = (el.textContent || '').trim();
          if (!text) continue;
          const cs = getComputedStyle(el);
          const range = document.createRange();
          range.selectNodeContents(el);
          const rects = [...range.getClientRects()].filter((r) => r.width > 0.5);
          const tops = [];
          for (const r of rects) {
            const t = Math.round(r.top);
            if (!tops.some((x) => Math.abs(x - t) <= 4)) tops.push(t);
          }
          res.push({
            beat: beat.id,
            id: el.id || null,
            cls: el.className || '',
            // the classes of every container between the text and the beat: a role
            // (headline, foot, primary label) is named on the block, not on the
            // span of its last word
            chain: (function () {
              const c = [];
              let n = el;
              while (n && n !== beat) {
                const k = typeof n.className === 'string' ? n.className : (n.getAttribute && n.getAttribute('class')) || '';
                if (k) c.push(k);
                n = n.parentElement;
              }
              return c.join(' ');
            })(),
            text: text.replace(/\s+/g, ' ').slice(0, 48),
            fontSize: parseFloat(cs.fontSize),
            align: cs.textAlign,
            lines: tops.length,
            planned: el.querySelectorAll('br').length + 1,
            widest: Math.round(Math.max(0, ...rects.map((r) => r.width))),
            box: Math.round(el.clientWidth || el.getBoundingClientRect().width),
            overflowX: Math.max(0, el.scrollWidth - el.clientWidth),
            // Overflow past a bare positioning div is invisible and fine — a
            // centred nowrap label doing it is idiomatic. It only matters when
            // something clips the text away or when the text escapes a card.
            clipped: (function () {
              let n = el;
              while (n && n !== beat) {
                const s = getComputedStyle(n);
                if (s.overflowX === 'hidden' || s.overflowY === 'hidden' || s.overflow === 'hidden') return true;
                n = n.parentElement;
              }
              return false;
            })(),
            carded: (function () {
              let n = el;
              while (n && n !== beat) {
                if (parseFloat(getComputedStyle(n).borderTopWidth || 0) > 0) return true;
                n = n.parentElement;
              }
              return opaque(el);
            })(),
            // A card holding text must sit on a solid --ink panel, or the
            // background texture runs straight through the type. The panel may
            // be the card's own background or a sibling behind it.
            // a texture is a low-opacity group of many strokes (cla-brand
            // recipes draw them at 0.09-0.12), whatever it is called
            texture: [...beat.querySelectorAll('svg, svg g')].some(function (g) {
              const op = parseFloat(getComputedStyle(g).opacity);
              return (isNaN(op) ? 1 : op) <= 0.25 &&
                     g.querySelectorAll('path,line,circle,rect,polyline').length >= 6;
            }),
            panelled: (function () {
              // the card is the nearest bordered box around the type — usually a
              // parent, not the text element itself
              let card = null, n = el;
              while (n && n !== beat) {
                if (parseFloat(getComputedStyle(n).borderTopWidth || 0) > 0) { card = n; break; }
                n = n.parentElement;
              }
              if (!card) return true;                       // no card, nothing to protect
              let a = card;
              while (a && a !== beat) { if (opaque(a)) return true; a = a.parentElement; }
              const r = card.getBoundingClientRect();
              for (const o of beat.querySelectorAll('*')) {
                if (o === card || card.contains(o) || o.contains(card)) continue;
                if (!opaque(o)) continue;
                const q = o.getBoundingClientRect();
                if (q.left <= r.left + 1 && q.right >= r.right - 1 &&
                    q.top <= r.top + 1 && q.bottom >= r.bottom - 1) return true;
              }
              return false;
            })(),
          });
        }
      }
      // SVG labels: the type a viewer reads inside a chart or an icon. Their size
      // is the computed font-size scaled by the SVG's own viewBox — static, so a
      // from-state scale set at load time does not shrink the reading.
      for (const beat of beats) {
        for (const t of beat.querySelectorAll('svg text')) {
          if ([...t.children].some((c) => c.tagName.toLowerCase() === 'tspan' && (c.textContent || '').trim())) continue;
          const text = (t.textContent || '').trim();
          if (!text) continue;
          const svg = t.ownerSVGElement;
          let k = 1;
          try {
            const vb = svg && svg.viewBox && svg.viewBox.baseVal;
            if (vb && vb.width > 0 && svg.clientWidth > 0) k = svg.clientWidth / vb.width;
          } catch (e) { /* no viewBox */ }
          const cs = getComputedStyle(t);
          res.push({ beat: beat.id, id: t.id || null, cls: (t.getAttribute('class') || ''),
                     chain: chainOf(t, beat),
                     text: text.replace(/\s+/g, ' ').slice(0, 48),
                     fontSize: Math.round(parseFloat(cs.fontSize) * k * 10) / 10,
                     svg: true, lines: 1, planned: 1 });
        }
        for (const t of beat.querySelectorAll('svg tspan')) {
          const text = (t.textContent || '').trim();
          if (!text) continue;
          const svg = t.ownerSVGElement;
          let k = 1;
          try {
            const vb = svg && svg.viewBox && svg.viewBox.baseVal;
            if (vb && vb.width > 0 && svg.clientWidth > 0) k = svg.clientWidth / vb.width;
          } catch (e) { /* no viewBox */ }
          const cs = getComputedStyle(t);
          res.push({ beat: beat.id, id: t.id || null, cls: (t.getAttribute('class') || ''),
                     chain: chainOf(t, beat),
                     text: text.replace(/\s+/g, ' ').slice(0, 48),
                     fontSize: Math.round(parseFloat(cs.fontSize) * k * 10) / 10,
                     svg: true, lines: 1, planned: 1 });
        }
      }
      return res;
    }, process.env.GATES_BEAT_SELECTOR || '[id^="beat-"]');
    console.log(JSON.stringify({ blocks: out }));
  } finally {
    await browser.close();
  }
})();
