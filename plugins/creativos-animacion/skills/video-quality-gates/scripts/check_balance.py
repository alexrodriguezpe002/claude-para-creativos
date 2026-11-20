#!/usr/bin/env python3
"""Gate: negative space, measured on the rendered frame.

The correction the editor has had to make more than any other. It is not checkable
from the CSS — font leading shifts the visible ink, and a symmetric outer margin
can still sit around a big internal hole. So this renders real frames with
`hyperframes snapshot` and counts pixels.

    python3 check_balance.py <project-dir> [--keep]

--keep leaves the PNGs in <project>/snapshots/ so they can be shown to the user.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

import _common as C
import check_exits as X
import check_variety as V
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)

try:
    from PIL import Image
except ImportError:
    sys.stderr.write(T("Pillow no está instalado: python3 -m pip install pillow\n", "Pillow is not installed: python3 -m pip install pillow\n"))
    sys.exit(2)

INK = 80              # luminance above this counts as content, not texture
OUTER_TOL = 0.025     # |top-bottom| over frame height
SIDE_TOL = 0.150      # |left-right| — left-aligned layouts are legitimate;
                      # this catches only an element stranded against one edge
GAP_ABS = 200         # a hole smaller than this never matters
GAP_SHARE = 0.25      # …nor one under this share of the content's own height.
                      # Calibrated on the case the editor rejected twice in CLA ep3:
                      # a headline stranded 340px above 1242px of content.
GREEN_MAX = 0.10      # green is an accent, never a surface
INK_MODE = "luminance"  # or "distance": colour distance from the frame's own ground,
                        # for clients whose grounds are not black (light schemes)


def main():
    d = C.project_dir(sys.argv)
    keep = "--keep" in sys.argv
    html = C.read_html(d)
    r = C.root(html)
    bts = C.beats(html)
    res = C.Result("balance", d)
    global INK, OUTER_TOL, SIDE_TOL, GAP_ABS, GAP_SHARE, GREEN_MAX, INK_MODE
    B = C.PROFILE["balance"]
    INK_MODE = B["ink"]["mode"]
    INK = B["ink"]["threshold"]
    OUTER_TOL, SIDE_TOL = B["outer_tol"], B["side_tol"]
    GAP_ABS, GAP_SHARE = B["gap_abs"], B["gap_share"]
    GREEN_MAX = B.get("green_max")

    if not bts:
        res.warn("no-beats", T("no encontré beats — nada que medir", "no beats found — nothing to measure"))
        return res.emit()

    # Sample each beat when its last element has landed — a mid-reveal frame
    # measures a layout that never exists. The same is true of the exit: since
    # the mirrored retreat became the default, the last event inside a beat is
    # the start of the retreat, and sampling after it measures a layout that
    # exists even less. So the window closes at the retreat, not at the cut.
    events = V._event_times(html)
    script = C.script_text(html)
    consts = C.const_table(V.CONST_RE, script)
    var2id = X.var_to_id(script)
    shots = []
    for b in bts:
        vs, ve = b["visible_start"], b["visible_end"]
        ex = X.exit_start(html, b, script, consts, var2id)
        top = (ex - 0.05) if ex and ex > vs + 0.2 else (ve - 0.05)
        inside = [t for t in events if vs - 0.01 <= t <= top]
        t = min(max(inside) + 0.6, top) if inside else vs + (top - vs) * 0.75
        shots.append((b["id"], round(max(t, vs + 0.2), 2)))

    outdir = os.path.join(d, "snapshots") if keep else tempfile.mkdtemp(prefix="gates-")
    pngs = _snapshot(d, [t for _, t in shots], outdir)
    if not pngs:
        res.fail("snapshot-failed",
                 T("no pude renderizar frames con `npx hyperframes snapshot` — sin frames no hay "
                 "medición, y medir sobre el CSS no vale",
                   "could not render frames with `npx hyperframes snapshot` — no frames means no measurement, and measuring from the CSS does not count"))
        return res.emit()

    res.note(T("%d frame(s) medidos en %s", "%d frame(s) measured at %s") % (len(pngs), ", ".join("%.2fs" % t for _, t in shots)))

    pip = _pip_box(html, r)
    if pip:
        res.note(T("PiP del speaker en x %d–%d · y %d–%d: cuenta para el balance vertical, no "
                 "para el horizontal",
                   "speaker PiP at x %d–%d · y %d–%d: it counts for the vertical balance, not the horizontal") % pip)
    for (bid, t), png in zip(shots, pngs):
        m = _measure(png, pip)
        if m is None:
            res.warn("empty-frame", T("%s @%.2fs: el frame salió vacío", "%s @%.2fs: the frame came out empty") % (bid, t))
            continue

        h, w = m["h"], m["w"]
        delta_v = abs(m["top"] - m["bottom"])
        if delta_v > OUTER_TOL * h:
            res.fail("vertical-balance",
                     T("%s @%.2fs: margen superior %dpx vs inferior %dpx (dif %dpx, %.1f%%)", "%s @%.2fs: top margin %dpx vs bottom %dpx (diff %dpx, %.1f%%)")
                     % (bid, t, m["top"], m["bottom"], delta_v, 100.0 * delta_v / h),
                     T("mover el bloque %d px hacia %s", "move the block %d px toward the %s") % (delta_v // 2,
                                                         T("arriba", "top") if m["top"] > m["bottom"] else T("abajo", "bottom")))

        delta_h = abs(m["left"] - m["right"])
        if delta_h > SIDE_TOL * w:
            res.fail("horizontal-balance",
                     T("%s @%.2fs: margen izquierdo %dpx vs derecho %dpx (dif %dpx, %.1f%%)", "%s @%.2fs: left margin %dpx vs right %dpx (diff %dpx, %.1f%%)")
                     % (bid, t, m["left"], m["right"], delta_h, 100.0 * delta_h / w),
                     T("agrandar un elemento no lo centra — medir los dos lados", "enlarging an element does not centre it — measure both sides"))

        eb = C.PROFILE["balance"].get("max_empty_bottom")
        ebw = C.PROFILE["balance"].get("warn_empty_bottom")
        if ebw and eb and ebw * h < m["bottom"] <= eb * h:
            res.warn("empty-bottom",
                     T("%s @%.2fs: %dpx vacíos debajo del último elemento (%.0f%% del frame)", "%s @%.2fs: %dpx empty below the last element (%.0f%% of the frame)")
                     % (bid, t, m["bottom"], 100.0 * m["bottom"] / h),
                     T("al límite — el perfil pide no más de ~%.0f%%", "at the limit — the profile asks for no more than ~%.0f%%") % (100.0 * ebw))
        if eb and m["bottom"] > eb * h:
            res.fail("empty-bottom",
                     T("%s @%.2fs: %dpx vacíos debajo del último elemento (%.0f%% del frame, máximo %.0f%%)", "%s @%.2fs: %dpx empty below the last element (%.0f%% of the frame, max %.0f%%)")
                     % (bid, t, m["bottom"], 100.0 * m["bottom"] / h, 100.0 * eb),
                     T("el contenido no llena el frame — agrandar o bajar el elemento de abajo", "the content does not fill the frame — enlarge or lower the bottom element"))

        span = max(h - m["top"] - m["bottom"], 1)
        if m["gap"] > GAP_ABS and m["gap"] > GAP_SHARE * span:
            res.fail("internal-gap",
                     T("%s @%.2fs: hueco interno de %dpx (%d–%d) sobre %dpx de contenido (%.0f%%)", "%s @%.2fs: internal gap of %dpx (%d–%d) out of %dpx of content (%.0f%%)")
                     % (bid, t, m["gap"], m["gap_from"], m["gap_to"], span,
                        100.0 * m["gap"] / span),
                     T("el margen exterior está parejo pero la masa visual no — comprimir el hueco "
                     "y volver a balancear",
                       "the outer margin is even but the visual mass is not — shrink the gap and rebalance"))

        if GREEN_MAX is not None and m["green"] > GREEN_MAX:
            res.fail("green-coverage",
                     T("%s @%.2fs: el verde cubre %.1f%% del frame (máximo %.0f%%)", "%s @%.2fs: green covers %.1f%% of the frame (max %.0f%%)")
                     % (bid, t, 100.0 * m["green"], 100.0 * GREEN_MAX))

        res.note(T("%s @%.2fs · top %d / bottom %d · izq %d / der %d · hueco máx %d · verde %.1f%%", "%s @%.2fs · top %d / bottom %d · left %d / right %d · max gap %d · green %.1f%%")
                 % (bid, t, m["top"], m["bottom"], m["left"], m["right"], m["gap"],
                    100.0 * m["green"]))

    if keep:
        res.note(T("frames en %s", "frames in %s") % outdir)
    else:
        shutil.rmtree(outdir, ignore_errors=True)
    _save_state(d, html, res, len(pngs))
    return res.emit()


def _save_state(d, html, res, frames):
    """What this measurement saw, so `run_gates.py --fast` knows when to measure again."""
    import json
    import time
    status = "FAIL" if res.fails else ("WARN" if res.warns else "PASS")
    try:
        os.makedirs(os.path.join(d, ".gates-cache"), exist_ok=True)
        with open(os.path.join(d, C.BALANCE_STATE), "w", encoding="utf-8") as fh:
            json.dump({"layout": C.layout_hash(html), "status": status,
                       "when": time.strftime("%Y-%m-%d %H:%M"), "frames": frames}, fh)
    except OSError:
        pass


def _snapshot(project, times, outdir):
    os.makedirs(outdir, exist_ok=True)
    import time
    started = time.time() - 1.0
    npx = C.P.npx_command()
    if not npx:
        return []
    cmd = npx + ["--yes", "hyperframes", "snapshot", ".", "--no-end",
                 "--at", ",".join("%.2f" % t for t in times),
                 "-o", outdir, "--describe", "false"]
    try:
        subprocess.run(cmd, cwd=project, check=False, timeout=600,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except (OSError, subprocess.TimeoutExpired):
        return []
    # new by time, not by name: a re-run with --keep writes the same file names
    # over the old frames, and comparing names reported "no frames" every time
    made = [f for f in os.listdir(outdir)
            if f.lower().endswith(".png") and not f.startswith("._")
            and os.path.getmtime(os.path.join(outdir, f)) >= started]
    made.sort(key=lambda f: _num(f))
    return [os.path.join(outdir, f) for f in made]


def _num(name):
    nums = re.findall(r"(\d+(?:[._]\d+)?)", name)
    return [float(n.replace("_", ".")) for n in nums] or [0.0]


RULE_COVER = 0.85     # a row this full of ink is a rule, not content
RULE_THICK = 5        # …if it is also this thin


def _pip_box(html, r):
    """Frame box (x0, x1, y0, y1) of the speaker PiP, from its inline style.

    The bubble sits in a corner on purpose. It is mass, so it counts for the
    vertical balance (the editor balances the space above the content against the
    space below the bubble), but a corner element always reads as "stranded"
    to a left/right comparison — so the horizontal check ignores it.
    """
    pr = C.PROFILE.get("variety", {}).get("pip_re")
    if not pr:
        return None
    m = re.search(r'<div[^>]*\bid="(' + pr + r')"[^>]*style="([^"]*)"', html)
    if not m:
        return None
    st = m.group(2)
    def px(k):
        mm = re.search(r"(?:^|;)\s*" + k + r"\s*:\s*(-?[\d.]+)px", st)
        return float(mm.group(1)) if mm else None
    w, h = px("width"), px("height")
    if not w or not h:
        return None
    W, H = r["width"], r["height"]
    left = px("left")
    if left is None and px("right") is not None:
        left = W - px("right") - w
    top = px("top")
    if top is None and px("bottom") is not None:
        top = H - px("bottom") - h
    if left is None or top is None:
        return None
    pad = 14            # the ring around the bubble
    return (int(left - pad), int(left + w + pad), int(top - pad), int(top + h + pad))


def _measure(path, pip=None):
    """Ink extents, largest internal hole and green share, ignoring structure.

    Thin full-width or full-height strokes — a persistent frame border, a ledger
    rule — are the drawing's furniture, not its content. Counting them makes any
    framed beat measure as perfectly balanced, which is how the CLA ep3 layouts
    passed a visual check while still reading top-heavy.
    """
    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()
    step = max(1, w // 360)
    xs = list(range(0, w, step))
    is_ink = _ink_test(img, px, w, h, xs)

    rows, green = [], 0
    for y in range(h):
        count = 0
        for x in xs:
            rr, gg, bb = px[x, y]
            if is_ink(rr, gg, bb):
                count += 1
            if gg > 110 and gg > rr + 40 and gg > bb + 40:
                green += 1
        rows.append(count)
    green_frac = green / float(h * len(xs)) if xs else 0.0

    rows = _strip_rules(rows, len(xs))
    if C.PROFILE["balance"].get("strip_edge_bands"):
        rows = _strip_edge_bands(rows)
    top, bottom_y = _extent(rows)
    if top is None:
        return None
    occupied = [y for y in range(top, bottom_y + 1) if rows[y]]
    thresh = max(2, int(0.004 * len(xs)))

    gap = gap_from = gap_to = 0
    run = None
    for y in range(top, bottom_y + 1):
        if rows[y] < thresh:
            if run is None:
                run = y
        else:
            if run is not None and y - run > gap:
                gap, gap_from, gap_to = y - run, run, y
            run = None

    cols = [0] * w
    for x in xs:
        for y in occupied:
            if pip and pip[0] <= x <= pip[1] and pip[2] <= y <= pip[3]:
                continue
            rr, gg, bb = px[x, y]
            if is_ink(rr, gg, bb):
                cols[x] += 1
    colprof = _strip_rules([cols[x] for x in xs], len(occupied))
    ci, cj = _extent(colprof)
    left = xs[ci] if ci is not None else 0
    right = (w - 1 - xs[cj]) if cj is not None else 0

    return {"w": w, "h": h, "top": top, "bottom": h - 1 - bottom_y,
            "left": left, "right": right,
            "gap": gap, "gap_from": gap_from, "gap_to": gap_to,
            "green": green_frac}


def _ink_test(img, px, w, h, xs):
    """Which pixels are content.

    luminance: brighter than INK — right for a black ground (CLA), where
    everything that is not ground is lighter than it.
    distance:  further than INK (RGB distance) from the frame's own ground — the
    most common colour on the frame. Needed when the ground is a colour or is
    light: on a cream frame every pixel is "bright" and luminance reads all of it
    as content. Textures and ghost icons at 4–6% opacity sit within ~25 of the
    ground and stay out; text, linework, accents and the speaker PiP are in.
    """
    if INK_MODE != "distance":
        return lambda r, g, b: (r * 299 + g * 587 + b * 114) // 1000 > INK
    hist = {}
    for y in range(0, h, 8):
        for x in xs[::4]:
            r, g, b = px[x, y]
            k = (r >> 3, g >> 3, b >> 3)
            hist[k] = hist.get(k, 0) + 1
    k = max(hist, key=hist.get)
    br, bgc, bb = (k[0] << 3) + 4, (k[1] << 3) + 4, (k[2] << 3) + 4
    t2 = INK * INK
    return lambda r, g, b: (r - br) ** 2 + (g - bgc) ** 2 + (b - bb) ** 2 > t2


MASS_TRIM = 0.005     # ignore the outer 0.5% of ink — specks are not the layout


def _extent(profile):
    """First and last index holding the bulk of the ink.

    A mass percentile rather than a fixed threshold: one stray 3px mark at the
    frame edge should not decide where the composition begins.
    """
    total = float(sum(profile))
    if total <= 0:
        return None, None
    lo, run = None, 0.0
    for i, c in enumerate(profile):
        run += c
        if run >= MASS_TRIM * total:
            lo = i
            break
    hi, run = None, 0.0
    for i in range(len(profile) - 1, -1, -1):
        run += profile[i]
        if run >= MASS_TRIM * total:
            hi = i
            break
    return lo, hi


def _strip_edge_bands(rows, thick=8, gap=GAP_ABS):
    """Drop a thin band of ink that sits alone at the top or bottom edge.

    A progress hairline filling along the bottom of the frame is furniture, not
    the composition: counted as content it moves the bottom margin to ~70px and
    reports a phantom hole between it and the real block.
    """
    out = list(rows)
    occ = [i for i, c in enumerate(out) if c]
    if not occ:
        return out
    for edge in ("bottom", "top"):
        occ = [i for i, c in enumerate(out) if c]
        if not occ:
            break
        seq = occ[::-1] if edge == "bottom" else occ
        band = [seq[0]]
        for i in seq[1:]:
            if abs(i - band[-1]) == 1:
                band.append(i)
            else:
                break
        rest = [i for i in occ if i not in band]
        if len(band) <= thick and rest:
            dist = (min(band) - max(rest)) if edge == "bottom" else (min(rest) - max(band))
            if dist > gap:
                for i in band:
                    out[i] = 0
    return out


def _strip_rules(profile, span):
    """Zero out thin runs of near-fully-covered lines."""
    out = list(profile)
    full = [i for i, c in enumerate(profile) if c >= RULE_COVER * span]
    i = 0
    while i < len(full):
        j = i
        while j + 1 < len(full) and full[j + 1] == full[j] + 1:
            j += 1
        if (j - i + 1) <= RULE_THICK:
            for k in range(i, j + 1):
                out[full[k]] = 0
        i = j + 1
    return out


if __name__ == "__main__":
    sys.exit(main())
