#!/usr/bin/env python3
"""Gate: the text inside a beat renders on the lines it was written for.

Where a line breaks is a browser question, and the markup never shows it. On
CLA ep4 Snippet 4 a comparison column authored as three lines rendered as five
and spilled past the divider it belonged to, and a figure authored as one line
inside a flex-centred box wrapped to two and came out left-aligned — both
straight to the editor, neither caught by any gate.

    python3 check_text_fit.py <project-dir> [--fast]

--fast skips the browser and reports `fit-not-measured` as a WARN, never a PASS.
"""

import json
import os
import subprocess
import sys

import _common as C
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)

CENTRE_ALIGNS = ("center", "-webkit-center", "justify")


def main():
    d = C.project_dir(sys.argv)
    res = C.Result("text-fit", d)
    html = C.read_html(d)
    if not C.beats(html):
        res.warn("no-beats", T("no encontré beats — nada que medir", "no beats found — nothing to measure"))
        return res.emit()

    if "--fast" in sys.argv:
        res.warn("fit-not-measured", T("salteado por --fast: hay que medirlo antes de entregar", "skipped by --fast: it must be measured before delivery"))
        return res.emit()

    blocks = _measure(d)
    if blocks is None:
        res.warn("fit-not-measured",
                 T("no pude medir en el navegador (playwright/chrome) — sin medición no hay "
                 "recuento de líneas real",
                   "could not measure in the browser (playwright/chrome) — without a measurement there is no real line count"))
        return res.emit()
    if not blocks:
        res.warn("no-text", T("no encontré bloques de texto dentro de los beats", "no text blocks found inside the beats"))
        return res.emit()

    wraps, spills, offcentre, bleed = [], [], [], []
    for b in blocks:
        if b.get("svg"):
            continue          # SVG labels are sized by the size gate, not wrapped
        who = T("%s «%s»", "%s “%s”") % (b["beat"], b["text"])
        if b["lines"] > b["planned"]:
            wraps.append(T("%s: %d líneas escritas, %d renderizadas (%.0fpx en una caja de %d)", "%s: %d lines written, %d rendered (%.0fpx in a %dpx-wide box)")
                         % (who, b["planned"], b["lines"], b["fontSize"], b["box"]))
        if b["overflowX"] > 1 and (b["clipped"] or b["carded"]):
            spills.append(T("%s: se sale %dpx de su caja%s", "%s: runs %dpx past its box%s")
                          % (who, b["overflowX"],
                             T(" y algo la recorta", " and something clips it") if b["clipped"] else T(" (caja con borde/fondo)", " (box with a border/background)")))
        # A block that wraps is only centred if the *lines* are centred: a flex
        # container centres the box, not the text inside it.
        if b["lines"] > 1 and b["align"] not in CENTRE_ALIGNS:
            offcentre.append(T("%s: %d líneas con text-align:%s", "%s: %d lines with text-align:%s") % (who, b["lines"], b["align"]))

        if b["carded"] and b["texture"] and not b["panelled"]:
            bleed.append(T("%s: la textura pasa por dentro de la tarjeta", "%s: the texture shows through the card") % who)

    if bleed:
        res.warn("texture-through-card",
                 T("%d tarjeta(s) con texto y sin panel --ink debajo", "%d card(s) with text and no --ink panel underneath") % len(bleed),
                 " · ".join(bleed[:6]))
    if wraps:
        res.fail("text-unplanned-wrap",
                 T("%d bloque(s) rompen en más líneas de las escritas", "%d block(s) break into more lines than written") % len(wraps),
                 " · ".join(wraps[:6]))
    if spills:
        res.fail("text-overflows-box",
                 T("%d bloque(s) desbordan su contenedor", "%d block(s) overflow their container") % len(spills),
                 " · ".join(spills[:6]))
    if offcentre:
        res.warn("text-lines-not-centred",
                 T("%d bloque(s) de varias líneas sin centrar — revisá que sea a propósito", "%d multi-line block(s) not centred — check that it is on purpose")
                 % len(offcentre),
                 " · ".join(offcentre[:6]))

    res.note(T("%d bloque(s) de texto medidos con la fuente cargada", "%d text block(s) measured with the font loaded")
             % len([b for b in blocks if not b.get("svg")]))
    return res.emit()


def _measure(d):
    js = os.path.join(os.path.dirname(os.path.abspath(__file__)), "measure_beat_text.js")
    env = dict(os.environ, GATES_BEAT_SELECTOR=C.PROFILE.get("beat_selector") or '[id^="beat-"]')
    out = C.P.run_node(js, [d], timeout=300, env=env)
    if out is None or out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)["blocks"]
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
