#!/usr/bin/env python3
"""Gate: build hygiene and brand invariants.

Seek-safety, timeline shape, and the brand rules that can be checked without
rendering — texture present, coordinate crosses, green never used as a fill.

    python3 check_build.py <project-dir>
"""

import re
import sys

import _common as C
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)

# Brand numbers (crosses, texture, green, ground) come from the client profile —
# see _profile.py. The defaults there are CLA's.


EP_LABEL_RE = re.compile(r"\b(?:EP|EPS|EPISODE|EPISODIO)\b\.?\s*#?\s*\d{1,4}", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_SLUG_RE = re.compile(r"\b([A-Za-z]{2,4})[ _-]*0*(\d{1,4})\b")


def _visible_text(fragment):
    """Text a viewer actually reads: markup out, <br> as a space."""
    txt = re.sub(r"<br\b[^>]*>", " ", fragment, flags=re.I)
    txt = re.sub(r"<(script|style)\b.*?</\1>", " ", txt, flags=re.I | re.S)
    txt = _TAG_RE.sub(" ", txt)
    return re.sub(r"\s+", " ", txt)


def _episode_slug(d, html):
    """Regex matching this episode's own label, from the project folder name.

    Derived, never hardcoded, so it follows the client and the episode. Returns
    None when the folder is not named '<ABBR> <NNN> ...' — no guessing.
    """
    import os
    name = os.path.basename(os.path.abspath(d))
    m = _SLUG_RE.match(name)
    if not m:
        vid = VIDEO_SRC_NAME_RE.search(html)
        m = _SLUG_RE.match(vid.group(1)) if vid else None
    if not m:
        return None
    abbr, num = m.group(1), m.group(2).lstrip("0") or "0"
    return re.compile(r"\b%s[ _-]*0*%s\b" % (re.escape(abbr), re.escape(num)), re.I)


VIDEO_SRC_NAME_RE = re.compile(r'<video[^>]*src="([^"/]+)"')


def _beat_background(html, beat):
    """The background a beat container declares, inline or through its classes."""
    tag = re.search(r'<div[^>]*\bid="%s"[^>]*>' % re.escape(beat["id"]), html)
    if not tag:
        return None
    t = tag.group(0)
    inline = re.search(r'style="[^"]*background(?:-color)?\s*:\s*([^;"]+)', t)
    if inline:
        return inline.group(1).strip()
    cm = re.search(r'class="([^"]*)"', t)
    classes = cm.group(1).split() if cm else []
    style = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))
    found = None
    for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", style):
        sels = [x.strip() for x in rule.group(1).split(",")]
        bgm = re.search(r"background(?:-color)?\s*:\s*([^;]+)", rule.group(2))
        if not bgm:
            continue
        for sel in sels:
            parts = re.findall(r"\.([\w-]+)", sel.split()[-1]) if sel else []
            ids = re.findall(r"#([\w-]+)", sel)
            if (parts and all(p in classes for p in parts)) or beat["id"] in ids:
                found = bgm.group(1).strip()       # later, more specific rules win
    return found


_HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_RGBA_RE = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")
_GENERIC_FONTS = {"sans-serif", "serif", "monospace", "system-ui", "ui-monospace",
                  "ui-sans-serif", "ui-serif", "-apple-system", "blinkmacsystemfont",
                  "inherit", "initial", "cursive", "fantasy", "emoji"}


def _colours(text):
    out = set()
    for m in _HEX_RE.finditer(text):
        h = m.group(1).lower()
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        out.add(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)))
    for m in _RGBA_RE.finditer(text):
        out.add(tuple(int(m.group(i)) for i in (1, 2, 3)))
    return out


def _rgb(hexstr):
    h = hexstr.lstrip("#").lower()
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _brand_check(res, html, sets):
    """Colours and fonts against the brand of the person on screen.

    The project names the person on its root: data-brand="<set>". A project that
    does not is measured against the set it matches best and gets a WARN: two
    people share this client and each has her own palette and type.
    """
    clean = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    style = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", clean, re.S))
    style = re.sub(r"/\*.*?\*/", " ", style, flags=re.S)
    attrs = " ".join(re.findall(r'(?:style|fill|stroke|stop-color|color)="([^"]*)"', clean))
    seen = _colours(style + " " + attrs + " " + C.script_text(clean))

    declared = re.search(r'id="root"[^>]*data-brand="([\w-]+)"', clean) or \
        re.search(r'data-brand="([\w-]+)"[^>]*id="root"', clean)
    name = declared.group(1) if declared else None

    def near(c, pal, tol=10):
        return any(sum((a - b) ** 2 for a, b in zip(c, p)) <= tol * tol for p in pal)

    pals = {k: [_rgb(x) for x in v.get("colors", [])] for k, v in sets.items()}
    neutral = [(0, 0, 0), (255, 255, 255)]
    if name not in sets:
        score = {k: sum(1 for c in seen if near(c, p)) for k, p in pals.items()}
        name = max(score, key=score.get) if score else None
        res.warn("brand-undeclared",
                 T("el proyecto no declara de quién es (data-brand en #root) — lo mido como «%s»", "the project does not declare whose brand it is (data-brand on #root) — measuring it as “%s”")
                 % name, "valores posibles: %s" % ", ".join(sorted(sets)))
    if not name:
        return
    allowed = pals[name] + neutral
    off = sorted("#%02x%02x%02x" % c for c in seen if not near(c, allowed))
    if off:
        res.fail("off-palette",
                 T("%d color(es) fuera de la paleta de «%s»", "%d color(s) outside the “%s” palette") % (len(off), name),
                 " · ".join(off[:10]))

    tokens = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", style))
    fams = set()
    for m in re.finditer(r"font-family\s*:\s*([^;\"}]+)", style + " " + attrs):
        val = m.group(1)
        for vm in re.finditer(r"var\((--[\w-]+)\)", val):
            val += "," + tokens.get(vm.group(1), "")
        for f in val.split(","):
            f = f.strip().strip("'\"").strip()
            if f and not f.startswith("var(") and f.lower() not in _GENERIC_FONTS:
                fams.add(f)
    for m in re.finditer(r"font\s*:\s*[^;\"}]*?\d+px(?:/[\d.]+)?\s+([^;\"}]+)", style + " " + attrs):
        for f in m.group(1).split(","):
            f = f.strip().strip("'\"").strip()
            if f.startswith("var("):
                vm = re.match(r"var\((--[\w-]+)\)", f)
                f = tokens.get(vm.group(1), "").split(",")[0].strip().strip("'\"") if vm else ""
            if f and f.lower() not in _GENERIC_FONTS:
                fams.add(f)
    ok_fonts = {x.lower() for x in sets[name].get("fonts", [])}
    bad_fonts = sorted(f for f in fams if f.lower() not in ok_fonts)
    if bad_fonts:
        res.fail("off-brand-font",
                 T("tipografía fuera de la marca de «%s»: %s", "typeface(s) outside the “%s” brand: %s") % (name, ", ".join(bad_fonts)),
                 "permitidas: %s" % ", ".join(sets[name].get("fonts", [])))
    res.note(T("marca «%s» · %d color(es) leídos · %d tipografía(s)", "brand “%s” · %d color(s) read · %d typeface(s)") % (name, len(seen), len(fams)))


def _translucent(bg):
    bg = bg.lower()
    if "transparent" in bg:
        return True
    m = re.search(r"rgba\(\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*,\s*([\d.]+)\s*\)", bg)
    return bool(m and float(m.group(1)) < 0.98)


def main():
    d = C.project_dir(sys.argv)
    html = C.read_html(d)
    low = html.lower()
    r = C.root(html)
    bts = C.beats(html)
    script = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.S))
    res = C.Result("build", d)
    P = C.PROFILE["build"]
    res.note("%d beat(s) · %dx%d · %.2fs" % (len(bts), r["width"], r["height"], r["duration"]))

    # ---- seek safety -------------------------------------------------------
    cb = re.findall(r"\b(onUpdate|onComplete|onStart|onRepeat)\s*:", script)
    if cb:
        res.fail("seek-callback",
                 T("%d callback(s) %s — HyperFrames renderiza por seek y los suprime; "
                 "el valor se congela",
                   "%d callback(s) %s — HyperFrames renders by seeking and suppresses them; "
                 "the value freezes") % (len(cb), "/".join(sorted(set(cb)))))

    if re.search(r"repeat\s*:\s*-\s*1", script):
        res.fail("infinite-repeat",
                 T("repeat: -1 rompe el render determinista; usar un número de ciclos acotado", "repeat: -1 breaks the deterministic render; use a bounded number of cycles"))

    standalone = [m.group(0) for m in re.finditer(r"(?<![.\w])gsap\.(?:to|fromTo)\s*\(", script)]
    if standalone:
        res.fail("standalone-tween",
                 T("%d tween(s) fuera del timeline principal — el seek no los alcanza", "%d tween(s) outside the main timeline — the seek does not reach them")
                 % len(standalone))

    # every fromTo needs its from-state pinned, or it leaks before its own time
    unpinned = []
    for m in re.finditer(r"tl\.fromTo\s*\(", script):
        args = C.js_call_args(script, m.end() - 1)
        if not args:
            continue
        target = args[0].strip()
        if not re.match(r'^["\'`]', target):
            continue          # a variable — the helper usually pins it
        sel = target.strip("\"'`")
        pinned = re.search(r"(?:gsap|tl)\.set\s*\(\s*[\"'`]" + re.escape(sel), script)
        if not pinned:
            unpinned.append(sel)
    if unpinned:
        res.fail("unpinned-fromto",
                 T("%d fromTo sin gsap.set/tl.set previo — el estado inicial se filtra "
                 "fuera de su ventana",
                   "%d fromTo without a prior gsap.set/tl.set — the initial state leaks "
                 "outside its window") % len(unpinned),
                 " · ".join(unpinned[:6]))

    # ---- timeline shape ----------------------------------------------------
    # counted on the script without comments: a comment that spells the
    # assignment out ("// window.__timelines['main'] = tl — always last") is not one
    assigns = re.findall(r'window\.__timelines\s*\[\s*["\']main["\']\s*\]\s*=(?!=)',
                         C.script_text(html))
    if len(assigns) != 1:
        res.fail("timeline-assign",
                 T("hay %d asignaciones a window.__timelines['main'] — tiene que haber exactamente 1", "there are %d assignments to window.__timelines['main'] — there must be exactly 1")
                 % len(assigns))

    subcomp = re.findall(r'data-composition-id="(?!main")([^"]+)"', html)
    if subcomp:
        res.fail("sub-composition",
                 T("sub-composiciones detectadas (%s) — los captions y beats van inline", "sub-compositions detected (%s) — captions and beats go inline")
                 % ", ".join(sorted(set(subcomp))))

    # ---- beat wiring -------------------------------------------------------
    flat = C.script_text(html)       # comments out, chained calls written out
    for a, b in zip(bts, bts[1:]):
        if abs(b["visible_start"] - a["visible_end"]) < 0.05:
            fade = re.search(
                r'tl\.to\(\s*["\'`]#' + re.escape(a["id"]) +
                r'["\'`]\s*,\s*\{[^}]*(?:opacity|autoAlpha):\s*0(?![.\d])', flat)
            fade = fade or re.search(
                r'tl\.from\(\s*["\'`]#' + re.escape(b["id"]) +
                r'["\'`]\s*,\s*\{[^}]*(?:opacity|autoAlpha):\s*0(?![.\d])[^}]*duration', flat)
            if fade:
                res.fail("contiguous-fade",
                         T("%s sale con fade y %s entra de inmediato — durante el fundido se ve "
                         "el video real. Con beats pegados el corte va con tl.set",
                           "%s exits with a fade and %s enters immediately — during the fade the real video shows through. "
                         "With back-to-back beats, make the cut with tl.set")
                         % (a["id"], b["id"]))

    texture_re = re.compile(P["texture_re"]) if P.get("texture_re") else None
    for b in bts:
        frag = b["html"].lower()
        if P.get("texture_required") and texture_re is not None:
            # the texture may be generated at load time by a builder, e.g. claTexture(<beat>, …)
            built = P.get("texture_builder_re") and re.search(
                P["texture_builder_re"] + r"\s*\([^)]*" + re.escape(b["id"]), script, re.I)
            if not texture_re.search(frag) and not built:
                res.fail("no-texture",
                         (P.get("texture_message") or
                          T("%s no tiene textura de fondo — en CLA todo beat la lleva, snippet o teaser", "%s has no background texture — in CLA every beat carries one, snippet or teaser"))
                         % b["id"])
        if P.get("coord_crosses"):
            cmin, cmax = P["coord_crosses"]
            crosses = len(re.findall(r'class="[^"]*(?:coord-cross|cross)\b', b["html"])) + \
                len(re.findall(r'id="[^"]*coord-cross', b["html"]))
            if crosses < cmin:
                res.fail("coord-crosses",
                         T("%s tiene %d cruces de coordenada — el rango de marca es %d a %d", "%s has %d coordinate crosses — the brand range is %d to %d")
                         % (b["id"], crosses, cmin, cmax))
            elif crosses > cmax:
                res.warn("coord-crosses",
                         T("%s tiene %d cruces de coordenada — el rango de marca es %d a %d", "%s has %d coordinate crosses — the brand range is %d to %d")
                         % (b["id"], crosses, cmin, cmax))

    # ---- nothing on screen may name the episode ----------------------------
    # the other editor sent CLA ep4 back twice for this: an eyebrow reading "<podcast
    # abbreviation> <episode number> · <beat title>". The podcast abbreviation and the episode number are
    # internal labels — a viewer reads them as part of what the speaker said.
    # The rule was already written in cla-brand/vocabulary.md ("Things that
    # never appear on screen") and shipped anyway, so it is a gate now.
    slug = _episode_slug(d, html)
    screened = 0
    for b in bts:
        txt = _visible_text(b["html"])
        screened += len(txt)
        hits = []
        if slug:
            hits += [m.group(0) for m in slug.finditer(txt)]
        hits += [m.group(0) for m in EP_LABEL_RE.finditer(txt)]
        if hits:
            res.fail("episode-label",
                     T("%s muestra la etiqueta del episodio — la sigla del podcast y el "
                     "número de episodio nunca van en pantalla",
                       "%s shows the episode label — the podcast abbreviation and the "
                     "episode number never go on screen") % b["id"],
                     " · ".join(sorted(set(h.strip() for h in hits))[:4]))
    res.note(T("%d caracter(es) de texto de beat leídos buscando etiquetas de episodio", "%d character(s) of beat text read looking for episode labels")
             % screened)

    # ---- brand invariants that do not need a render ------------------------
    green_tokens = tuple(P.get("green_tokens") or ())
    if green_tokens:
        for m in re.finditer(r"background(?:-color)?\s*:\s*([^;\"'}]+)", low):
            val = m.group(1)
            if any(g in val for g in green_tokens) and "rgba" not in val:
                res.fail("green-fill",
                         T("el verde nunca es fondo ni relleno de área", "green is never a background or an area fill"),
                         "background: %s" % m.group(1).strip())
                break

    gr = P.get("ground")
    if gr:
        ground = re.search(gr["selector"] + r"\s*\{[^}]*background:\s*([^;]+)", low)
        if ground and not any(a in ground.group(1) for a in gr["allowed"]):
            res.fail("ground", gr["message"], T("encontrado: %s", "found: %s") % ground.group(1).strip())

    # a beat covers the video completely, or it reads as a cheap sticker
    if P.get("opaque_beats"):
        for b in bts:
            bg = _beat_background(html, b)
            if bg is None:
                res.fail("beat-ground",
                         T("%s no declara un fondo propio — el beat tiene que tapar el video", "%s does not declare its own ground — the beat has to cover the video") % b["id"])
            elif _translucent(bg):
                res.fail("beat-ground",
                         T("%s tiene fondo translúcido — el beat cubre el video al 100%%", "%s has a translucent ground — the beat covers the video 100%%") % b["id"],
                         "background: %s" % bg)

    # no bounce, no overshoot: an executive brand reads a rebound as a toy
    fe = [x.lower() for x in (P.get("forbidden_eases") or [])]
    if fe:
        eases = re.findall(r"ease\s*:\s*[\"'`]([^\"'`]+)[\"'`]", C.script_text(html))
        bad = [e for e in eases if any(e.strip().lower().startswith(x) for x in fe)]
        if bad:
            res.fail("forbidden-ease",
                     T("%d tween(s) con rebote o sobre-paso (%s) — la marca no los admite", "%d tween(s) with bounce or overshoot (%s) — the brand does not allow them")
                     % (len(bad), ", ".join(sorted(set(bad)))),
                     T("entradas con expo.out o power2.out, salidas con power2.in", "entrances with expo.out or power2.out, exits with power2.in"))

    # every colour and typeface on screen belongs to the person's own brand
    bs = P.get("brand_sets")
    if bs:
        _brand_check(res, html, bs)

    # rotating an SVG part around the wrong point only shows mid-motion
    if P.get("svg_origin_check"):
        mixed = []
        for m in re.finditer(r"\{[^{}]*\}", script):
            obj = m.group(0)
            if "svgOrigin" in obj and "transformOrigin" in obj:
                mixed.append(re.sub(r"\s+", " ", obj)[:80])
        if mixed:
            res.fail("svg-origin-mix",
                     T("%d tween(s) mezclan transformOrigin y svgOrigin — dos sistemas de referencia; "
                     "en SVG se usa solo svgOrigin",
                       "%d tween(s) mix transformOrigin and svgOrigin — two reference systems; "
                     "in SVG use only svgOrigin") % len(mixed),
                     " · ".join(mixed[:3]))

    # ---- the timeline must not outlive the video ---------------------------
    consts = C.const_table(
        re.compile(r"(?:const|let|var)?\s*\b([A-Za-z_]\w*)\s*=\s*(-?\d+(?:\.\d+)?)\s*(?=[,;])"),
        script)
    end = 0.0
    for m in re.finditer(r"tl\.(?:to|fromTo)\s*\(", script):
        args = C.js_call_args(script, m.end() - 1)
        if len(args) < 2:
            continue
        at = C._expr(args[-1].strip(), consts)
        if at is None:
            continue
        dur = 0.0
        dm = re.search(r"duration:\s*([A-Za-z_]\w*|[\d.]+)", args[-2])
        if dm:
            dur = C._expr(dm.group(1), consts) or 0.0
        rm = re.search(r"repeat:\s*(\d+)", args[-2])
        if rm:
            dur *= (int(rm.group(1)) + 1)
        end = max(end, at + dur)
    if r["duration"] and end > r["duration"] + 0.05:
        res.fail("timeline-overrun",
                 T("el timeline llega a %.2fs y el video dura %.2fs — el render sale más largo", "the timeline runs to %.2fs and the video lasts %.2fs — the render comes out longer")
                 % (end, r["duration"]))

    return res.emit()


if __name__ == "__main__":
    sys.exit(main())
