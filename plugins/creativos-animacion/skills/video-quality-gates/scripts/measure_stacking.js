// Is a caption that `hyperframes check` saw overlapping a beat's text actually
// covered by that beat — painted underneath it, inside its box, while the beat
// is fully opaque on screen?
//
// `content_overlap` compares text boxes only; it does not know that a full-frame
// opaque beat sits on top of the caption layer. On CLA ep4 Snippet 2 it reported
// caption #20 ("caught") over the beat's own label for 0.75s,
// as an error — the rendered frames show only the beat. What paints over what,
// and how opaque it is at a given second, is a browser question: this seeks the
// composition's own timeline to each sampled time and asks.
//
//   node measure_stacking.js <project-dir> '<json>'
//
// json: [{"caption": "<selector>", "other": "<selector>", "beat": "<id>", "times": [s, ...]}]
// Prints one JSON object {results: [...]}, one entry per query with `covered`.
// Exit 3 means playwright is not installed here; the gate then keeps every
// finding exactly as hyperframes reported it — it never excuses one blind.
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
  const queries = JSON.parse(process.argv[3] || '[]');
  const file = B.fileUrl(path.join(proj, 'index.html'));
  let browser;
  try { browser = (await B.launch(pw)).browser; }
  catch (e) { console.error(e.message); process.exit(3); }
  try {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    // the HyperFrames runtime creates the registry before inline scripts run;
    // a bare page needs it too, or `window.__timelines[id] = tl` throws
    await page.addInitScript(() => { window.__timelines = window.__timelines || {}; });
    await page.goto(file, { waitUntil: 'load' });
    const size = await page.evaluate(() => {
      const r = document.querySelector('[data-composition-id]') || document.body;
      return { w: +(r.getAttribute('data-width') || 1080), h: +(r.getAttribute('data-height') || 1920) };
    });
    await page.setViewportSize({ width: size.w, height: size.h });
    await page.evaluate(async () => { try { await document.fonts.ready; } catch (e) {} });
    await page.waitForTimeout(600);

    const results = await page.evaluate((qs) => {
      const tls = Object.values(window.__timelines || {});
      function seek(t) {
        for (const tl of tls) { try { tl.pause(); tl.seek(t); } catch (e) { /* not a timeline */ } }
      }
      function alpha(color) {
        const m = (color || '').match(/rgba?\(([^)]+)\)/);
        if (!m) return 0;
        const parts = m[1].includes(',') ? m[1].split(',') : m[1].split('/');
        const a = m[1].includes(',') ? parts[3] : parts[1];
        if (a === undefined) return 1;
        return a.trim().endsWith('%') ? parseFloat(a) / 100 : parseFloat(a);
      }
      // what the viewer gets of the beat: its own opacity times every ancestor's
      function shownOpacity(el) {
        let o = 1;
        for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
          const cs = getComputedStyle(n);
          if (cs.display === 'none' || cs.visibility === 'hidden') return 0;
          o *= parseFloat(cs.opacity);
        }
        return o;
      }
      function lca(a, b) {
        const seen = new Set();
        for (let n = a; n; n = n.parentElement) seen.add(n);
        for (let n = b; n; n = n.parentElement) if (seen.has(n)) return n;
        return null;
      }
      function childOf(top, el) {
        let n = el;
        while (n && n.parentElement !== top) n = n.parentElement;
        return n;
      }
      // z-index at the level where the two subtrees meet: the first positioned
      // element with a z-index on the way down from that level
      function levelZ(top, el) {
        const chain = [];
        for (let n = el; n; n = n.parentElement) { chain.push(n); if (n === top) break; }
        chain.reverse();
        for (const n of chain) {
          const cs = getComputedStyle(n);
          if (cs.position !== 'static' && cs.zIndex !== 'auto') return parseInt(cs.zIndex, 10) || 0;
        }
        return 0;
      }
      const CAPTION = '.caption-group, .cap-layer, #cap-layer, [id^="cap"], [class*="caption"]';
      const out = [];
      for (const q of qs) {
        const r = { caption: q.caption, other: q.other, beat: q.beat, covered: false };
        const cap = document.querySelector(q.caption);
        const other = document.querySelector(q.other);
        const beat = document.getElementById(q.beat);
        if (!cap || !other || !beat) { r.why = T('no encontré el elemento', 'element not found'); out.push(r); continue; }
        r.isCaption = !!cap.closest(CAPTION);
        r.otherInBeat = beat.contains(other);
        if (!r.isCaption || !r.otherInBeat || beat.contains(cap)) {
          r.why = 'no es un caption contra el texto de un beat'; out.push(r); continue;
        }
        const top = lca(cap, beat);
        const a = childOf(top, cap), b = childOf(top, beat);
        r.capZ = levelZ(a, cap);
        r.beatZ = levelZ(b, beat);
        r.below = r.capZ < r.beatZ || (r.capZ === r.beatZ &&
          !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING));
        r.ground = alpha(getComputedStyle(beat).backgroundColor) >= 0.98;
        r.samples = [];
        let ok = r.below && r.ground;
        for (const t of q.times) {
          seek(t);
          const op = shownOpacity(beat);
          const br = beat.getBoundingClientRect();
          const cr = cap.getBoundingClientRect();
          const inside = br.left <= cr.left + 1 && br.top <= cr.top + 1 &&
                         br.right >= cr.right - 1 && br.bottom >= cr.bottom - 1;
          r.samples.push({ t: t, opacity: Math.round(op * 1000) / 1000, inside: inside });
          if (op < 0.98 || !inside) ok = false;
        }
        r.covered = ok && r.samples.length > 0;
        if (!r.covered) {
          r.why = !r.below ? 'el caption se pinta encima del beat'
            : !r.ground ? 'el beat no tiene un fondo opaco'
            : T('el beat no está opaco o no cubre el caption en todas las muestras',
                'the beat is not opaque or does not cover the caption in every sample');
        }
        out.push(r);
      }
      return out;
    }, queries);
    console.log(JSON.stringify({ results: results }));
  } finally {
    await browser.close();
  }
})();
