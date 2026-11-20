#!/usr/bin/env python3
"""Gate: type size and scale.

A 1080px-wide frame on a ~390pt phone renders 1 frame pixel as 0.36pt, so a 40px
label is 14pt — under iOS body text. This gate is the reason "las letras son muy
chicas" stops being a manual correction.

    python3 check_text_size.py <project-dir>
"""

import re
import sys

import _common as C
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)


def _role_floors(TX, portrait):
    """[(role, class regex, min px)] from the profile's text.role_floors.

    A role is a size under which a headline, a takeaway line or a primary label
    stops reading as what it is, higher than the floor of the smallest label —
    the corrections of CLE ep2 (a 34 px gauge label → 42, a 44 px foot → 52) that
    the general floor cannot see. A landscape frame is held to a role only when
    the entry gives `min_landscape`.
    """
    out = []
    for rf in TX.get("role_floors") or []:
        mn = rf.get("min") if portrait else rf.get("min_landscape")
        if mn is None or not rf.get("class_re"):
            continue
        try:
            out.append((rf.get("role") or rf["class_re"], re.compile(rf["class_re"]), float(mn)))
        except re.error:
            continue
    return out


def _role_of(roles, classes, size, seen=None):
    """(role, floor) the element must clear, when its own or a container's class names one and it is under it.

    `seen` (a dict) counts the texts each role found, under its floor or not: a role that finds
    none is printed as such — a build that forgot the class is a silent pass otherwise."""
    worst = None
    for name, rx, mn in roles:
        if any(rx.search(c) for c in classes):
            if seen is not None:
                seen[name] = seen.get(name, 0) + 1
            if size is not None and size < mn - 0.5 and (worst is None or mn > worst[1]):
                worst = (name, mn)
    return worst


def _roles_note(roles, seen):
    return T("pisos por rol: %s", "floors per role: %s") % " · ".join(
        "%s ≥%.0f (%s)" % (n, m, (T("%d texto(s)", "%d text(s)") % seen[n]) if seen.get(n) else
                           T("ningún texto con esa clase — si el beat tiene uno, falta la clase", "no text with that class — if the beat has one, the class is missing"))
        for n, _, m in roles)

# Floors, the size budget per beat and the exempt roles come from the client
# profile (_profile.py). CLA's defaults: 48px floor (17.3pt on the phone — iOS
# body size), 56px comfortable, 24px on a teaser, 3 sizes per beat, eyebrow exempt.


def main():
    d = C.project_dir(sys.argv)
    html = C.read_html(d)
    r = C.root(html)
    sizes = C.css_sizes(html)
    bts = C.beats(html)
    res = C.Result("text-size", d)
    TX = C.PROFILE["text"]
    FLOOR_PORTRAIT = float(TX["floor_portrait"])
    COMFORT_PORTRAIT = float(TX["comfort_portrait"])
    FLOOR_LANDSCAPE = float(TX["floor_landscape"])
    MAX_SIZES_PER_BEAT = int(TX["max_sizes_per_beat"])
    EXEMPT = tuple(TX.get("exempt_classes") or ())

    if not bts:
        res.warn("no-beats", T("no encontré beats en index.html", "no beats found in index.html"))
        return res.emit()

    portrait = r["portrait"]
    floor = FLOOR_PORTRAIT if portrait else FLOOR_LANDSCAPE
    roles = _role_floors(TX, r["portrait"])
    if TX.get("measure_in_browser") and "--fast" not in sys.argv:
        return _browser(d, res, bts, r, floor, MAX_SIZES_PER_BEAT, EXEMPT, roles)
    res.note(T("%s %dx%d · %d beat(s) · piso %.0fpx", "%s %dx%d · %d beat(s) · floor %.0fpx")
             % ("snippet" if portrait else "teaser", r["width"], r["height"], len(bts), floor))

    too_small, unresolved, scale_issues, role_small = [], [], [], []
    seen_roles = {}

    for b in bts:
        els = C.text_elements(b["html"], sizes)
        seen = []
        for el in els:
            if any(x in " ".join(el["classes"]).lower() for x in EXEMPT):
                continue
            if el["size"] is None:
                unresolved.append(T("%s «%s»", "%s “%s”") % (b["id"], _clip(el["text"])))
                continue
            seen.append(el["size"])
            hit = _role_of(roles, el.get("chain") or el["classes"], el["size"], seen_roles)
            if hit:
                role_small.append(T("%s %s «%s» %.0fpx (mín %.0f)", "%s %s “%s” %.0fpx (min %.0f)")
                                  % (hit[0], b["id"], _clip(el["text"]), el["size"], hit[1]))
            if el["size"] < floor:
                too_small.append(T("%s «%s» %.0fpx (%.1fpt en el teléfono)", "%s “%s” %.0fpx (%.1fpt on the phone)")
                                 % (b["id"], _clip(el["text"]), el["size"],
                                    el["size"] * 390.0 / r["width"]))
        distinct = sorted(set(seen), reverse=True)
        if len(distinct) > MAX_SIZES_PER_BEAT:
            scale_issues.append(T("%s usa %d tamaños: %s", "%s uses %d sizes: %s")
                                % (b["id"], len(distinct),
                                   ", ".join("%.0f" % s for s in distinct)))

    if roles:
        res.note(_roles_note(roles, seen_roles))
    if too_small:
        res.fail("text-below-floor",
                 T("%d texto(s) por debajo del piso de %.0fpx", "%d text(s) below the %.0fpx floor") % (len(too_small), floor),
                 " · ".join(too_small[:8]))

    if role_small:
        res.fail("text-below-role-floor",
                 T("%d texto(s) por debajo del piso de su rol", "%d text(s) below the floor of their role") % len(role_small),
                 " · ".join(role_small[:8]))

    if scale_issues:
        res.fail("type-scale",
                 T("más de %d tamaños distintos en un beat — un solo salto por frame", "more than %d different sizes in a beat — one size jump per frame")
                 % MAX_SIZES_PER_BEAT,
                 " · ".join(scale_issues))

    if unresolved:
        res.warn("size-unresolved",
                 T("%d texto(s) sin font-size resoluble estáticamente — revisar a mano", "%d text(s) with no statically resolvable font-size — check by hand")
                 % len(unresolved),
                 " · ".join(unresolved[:6]))

    # A headline mask shorter than its own ink clips the type permanently.
    for cls, fs in sizes.items():
        if "headline" not in cls or ".mask" in cls:
            continue
        mask = None
        for c2, _ in sizes.items():
            pass
        mh = re.search(re.escape(cls) + r"\s+\.mask\s*\{[^}]*height:\s*(\d+(?:\.\d+)?)px", html)
        if not mh:
            mh = re.search(r"\.headline\s+\.mask\s*\{[^}]*height:\s*(\d+(?:\.\d+)?)px", html)
        if mh:
            mask = float(mh.group(1))
        if mask is not None:
            ratio = mask / fs
            if ratio < 0.90 or ratio > 1.05:
                res.fail("headline-mask",
                         T("la máscara del headline no acompaña al font-size", "the headline mask does not follow the font-size"),
                         T("%s: font-size %.0fpx, mask %.0fpx (ratio %.2f, esperado ~0.94)", "%s: font-size %.0fpx, mask %.0fpx (ratio %.2f, expected ~0.94)")
                         % (cls, fs, mask, ratio))

    # line-height under 1.0 inside an overflow:hidden box clips the glyph for good
    for m in re.finditer(r"([.#][\w-]+)\s*\{([^}]*)\}", html):
        body = m.group(2)
        lh = re.search(r"line-height:\s*(0?\.\d+)\b", body)
        if lh and "overflow: hidden" in body.replace("overflow:hidden", "overflow: hidden"):
            res.fail("line-height-clip",
                     T("line-height < 1 dentro de overflow:hidden corta el glifo de forma permanente", "line-height < 1 inside overflow:hidden clips the glyph permanently"),
                     "%s: line-height %s" % (m.group(1), lh.group(1)))

    if portrait and not too_small:
        content = [s for s in sizes.values() if floor <= s < 90]
        if content and min(content) < COMFORT_PORTRAIT:
            res.note(T("el texto de contenido más chico es %.0fpx (cómodo desde %.0fpx)", "the smallest content text is %.0fpx (comfortable from %.0fpx)")
                     % (min(content), COMFORT_PORTRAIT))

    return res.emit()


def _browser(d, res, bts, r, floor, max_sizes, exempt, roles=()):
    """Sizes as the browser computes them, for compositions whose type is set
    inline or through selectors the static reader cannot resolve. A gate that
    reports "unresolved" for every label is a gate that never checks the floor."""
    import check_text_fit as F
    blocks = F._measure(d)
    if blocks is None:
        res.warn("size-not-measured",
                 T("no pude medir en el navegador — el piso de %.0fpx queda sin verificar", "could not measure in the browser — the %.0fpx floor is left unchecked") % floor)
        return res.emit()
    res.note(T("%s %dx%d · %d beat(s) · piso %.0fpx · medido en el navegador (%d textos)", "%s %dx%d · %d beat(s) · floor %.0fpx · measured in the browser (%d texts)")
             % ("snippet" if r["portrait"] else "teaser", r["width"], r["height"],
                len(bts), floor, len(blocks)))
    too_small, per_beat, role_small = [], {}, []
    seen_roles = {}
    for b in blocks:
        cls = (b.get("cls") or "").lower()
        if any(x in cls for x in exempt):
            continue
        fs = float(b.get("fontSize") or 0)
        if fs <= 0:
            continue
        per_beat.setdefault(b["beat"], set()).add(round(fs))
        hit = _role_of(roles, (b.get("chain") or b.get("cls") or "").split(), fs, seen_roles)
        if hit:
            role_small.append(T("%s %s «%s» %.0fpx (mín %.0f)", "%s %s “%s” %.0fpx (min %.0f)")
                              % (hit[0], b["beat"], _clip(b["text"]), fs, hit[1]))
        if fs < floor - 0.5:
            too_small.append(T("%s «%s» %.0fpx%s (%.1fpt en el teléfono)", "%s “%s” %.0fpx%s (%.1fpt on the phone)")
                             % (b["beat"], _clip(b["text"]), fs, " svg" if b.get("svg") else "",
                                fs * 390.0 / r["width"]))
    if too_small:
        res.fail("text-below-floor",
                 T("%d texto(s) por debajo del piso de %.0fpx", "%d text(s) below the %.0fpx floor") % (len(too_small), floor),
                 " · ".join(too_small[:8]))
    if role_small:
        res.fail("text-below-role-floor",
                 T("%d texto(s) por debajo del piso de su rol", "%d text(s) below the floor of their role") % len(role_small),
                 " · ".join(role_small[:8]))
    scale = [T("%s usa %d tamaños: %s", "%s uses %d sizes: %s") % (k, len(v), ", ".join("%d" % x for x in sorted(v, reverse=True)))
             for k, v in per_beat.items() if len(v) > max_sizes]
    if scale:
        res.fail("type-scale",
                 T("más de %d tamaños distintos en un beat — un solo salto por frame", "more than %d different sizes in a beat — one size jump per frame") % max_sizes,
                 " · ".join(scale))
    content = [x for v in per_beat.values() for x in v]
    if content:
        res.note(T("texto más chico %dpx · más grande %dpx", "smallest text %dpx · largest %dpx") % (min(content), max(content)))
    if roles:
        res.note(_roles_note(roles, seen_roles))
    return res.emit()


def _clip(t, n=34):
    t = t.strip()
    return t if len(t) <= n else t[: n - 1] + "…"


if __name__ == "__main__":
    sys.exit(main())
