#!/usr/bin/env python3
"""Gate: every animation leaves the way it came in.

Default since 2026-09-09 (the editor, on CLA ep4): "Quiero que la regla del espejo se
ponga por defecto… La única ocasión donde sé que no aplica el espejo es cuando
una animación está hasta el final del video."

The rule was already written in `podcast-beat-build` and nothing verified it, so
all nine beats of CLA ep4 exited on a hard cut and passed five gates. That is the
hole this closes.

    python3 check_exits.py <project-dir>

The one automatic exemption is a beat that rides out with the video. Any other
exception is the user's call on the frame — when they make it, quote them in the
report instead of silencing the gate.

A brand can make that call once, for all its beats, in its `gates.json`:
`exits.cut_out: true` (CLE — its approved CLE ep2 renders cut each graphic out in
one frame with everything still on screen; the editor, 2026-10-03). A beat with no
retreat is then a note ("sale por corte, declarado por la marca"), not
beat-exit-hard-cut. A beat that does retreat is still held to the rest: its
coverage (beat-exit-partial), the stroke drawn and never drawn off, and landing
on the cut (beat-exit-early).
"""

import os
import re
import sys

import _common as C
from check_variety import CONST_RE, _eval
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)

EXIT_WINDOW = 1.8       # how long before the close a retreat may start
RIDES_OUT_TOL = 0.20    # "ends with the video"
COVERAGE_MIN = 0.60     # share of what entered that has to leave
LANDING_TOL = 0.12      # the retreat has to finish at the cut, not before it

EXIT_STYLE = re.compile(r"EASE_EXIT|power\d?\.in\b|drawOff")
CALL_RE = re.compile(r"tl\.(set|to|fromTo)\s*\(")
HELPER_RE = re.compile(r"\b(drawOff|drawOn|lineReveal|[a-zA-Z_]\w*)\s*\(")
# the background texture is the beat's own furniture: it fades with the
# container and is never counted as an element that entered on its own
FURNITURE = ("tex", "topo", "grid", "cross", "box-mask", "#frame-fx", "scrim")


def _container_re():
    return re.compile(r"^#?(?:" + C.beat_id_re() + r")$")


def _furniture():
    return FURNITURE + tuple(C.PROFILE.get("exits", {}).get("furniture_extra") or ())


def script_of(html):
    return C.script_text(html)


def var_to_id(script):
    """variable name -> element id, for the beats written inside an IIFE."""
    out = {}
    for m in re.finditer(
            r"\b(\w+)\s*=\s*(?:\$|document\.getElementById|document\.querySelector"
            r"|document\.querySelectorAll)\(\s*[\"'`]#?\.?([\w-]+)", script):
        out[m.group(1)] = m.group(2)
    return out


def _ids(raw, var2id):
    out = set(re.findall(r"[#.]([\w-]+)", raw))
    for v in re.findall(r"\b(\w+)\b", raw):
        if v in var2id:
            out.add(var2id[v])
    return out


def calls(script, consts, var2id):
    """Every timeline event as a dict.

    Parsed from the call's own arguments, not from its source line: the exit
    blocks wrap `tl.to([a, b], {...})` over three lines, and a line-based reader
    silently drops those.
    """
    out = []

    def add(t, raw, body, is_set):
        if t is None:
            return
        dur = 0.0
        dm = re.search(r"(?:duration|dur)\s*:\s*([A-Za-z_]\w*|[\d.]+)", body)
        if dm:
            dur = _eval(dm.group(1), consts) or 0.0
        out.append({
            "t": t, "raw": raw.strip(), "ids": _ids(raw, var2id), "dur": dur,
            "exit": bool(EXIT_STYLE.search(body)) and not is_set,
            "container": bool(_container_re().match(raw.strip().strip("\"'`"))),
            "furniture": any(k in raw for k in _furniture()),
        })

    for m in CALL_RE.finditer(script):
        args = C.js_call_args(script, m.end() - 1)
        if not args:
            continue
        add(_eval(args[-1].strip(), consts), args[0],
            " ".join(args[1:]), m.group(1) == "set")

    for m in HELPER_RE.finditer(script):
        if m.group(1) in ("set", "to", "fromTo", "if", "for", "while", "function",
                          "getElementById", "querySelector", "querySelectorAll",
                          "forEach", "map", "push", "setAttribute"):
            continue
        args = C.js_call_args(script, m.end() - 1)
        if len(args) < 2 or "at" not in args[-1]:
            continue
        am = re.search(r"\bat\s*:\s*([^,}\n]+)", args[-1])
        if not am:
            continue
        body = " ".join(args[1:]) + (" drawOff" if m.group(1) == "drawOff" else "")
        add(_eval(am.group(1), consts), args[0], body, False)

    return out


def own_targets(beat_html):
    out = set(re.findall(r'id="([\w-]+)"', beat_html))
    for chunk in re.findall(r'class="([^"]*)"', beat_html):
        out |= set(chunk.split())
    return out


TAG_RE = re.compile(r"<(/?)([a-zA-Z][\w-]*)([^>]*?)(/?)>", re.S)


def ancestors(beat_html):
    """target -> every id/class above it, so a group's exit covers its children.

    A ledger whose rows leave because the document they sit in scales away is
    mirrored; flagging each row would be noise.
    """
    out, stack = {}, []
    for m in TAG_RE.finditer(beat_html):
        closing, name, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        keys = set()
        im = re.search(r'id="([\w-]+)"', attrs)
        if im:
            keys.add(im.group(1))
        cm = re.search(r'class="([^"]*)"', attrs)
        if cm:
            keys |= set(cm.group(1).split())
        if closing:
            if stack:
                stack.pop()
            continue
        above = set().union(*stack) if stack else set()
        for k in keys:
            out.setdefault(k, set()).update(above)
        if not selfclose:
            stack.append(keys)
    return out


def exit_start(html, beat, script=None, consts=None, var2id=None):
    """When this beat starts retreating, or None when it just cuts out.

    `check_balance.py` needs this too: with a mirrored exit the last reveal is no
    longer the resting frame, and sampling after it measures the retreat.
    """
    if script is None:
        script = script_of(html)
    if consts is None:
        consts = C.const_table(CONST_RE, script)
    if var2id is None:
        var2id = var_to_id(script)
    key = "B%s_EXIT" % beat["id"].replace("beat-", "").upper()
    if key in consts:
        return consts[key]
    own = own_targets(beat["html"])
    vs, ve = beat["visible_start"], beat["visible_end"]
    ts = [c["t"] for c in calls(script, consts, var2id)
          if c["exit"] and not c["container"] and (c["ids"] & own)
          and vs < c["t"] <= ve + 0.01 and c["t"] >= ve - EXIT_WINDOW]
    return min(ts) if ts else None


def main():
    d = C.project_dir(sys.argv)
    html = C.read_html(d)
    r = C.root(html)
    bts = C.beats(html)
    res = C.Result("exits", d)
    cut_out = bool((C.PROFILE.get("exits") or {}).get("cut_out"))
    # "the end of the video" is the end of the speech when a fixed outro card follows
    video_end = C.speech_end(html, r["duration"])

    if not bts:
        res.warn("no-beats", T("no encontré beats — nada que verificar", "no beats found — nothing to check"))
        return res.emit()

    script = script_of(html)
    consts = C.const_table(CONST_RE, script)
    var2id = var_to_id(script)
    evs = calls(script, consts, var2id)

    for b in bts:
        vs, ve = b["visible_start"], b["visible_end"]
        own = own_targets(b["html"])
        up = ancestors(b["html"])

        if video_end and ve >= video_end - RIDES_OUT_TOL:
            res.note(T("%s sale con el video (%.2fs) — exento del espejo", "%s runs to the end of the video (%.2fs) — exempt from the mirrored exit") % (b["id"], ve))
            continue

        mine = [c for c in evs if (c["ids"] & own) and not c["container"]
                and vs - 0.01 <= c["t"] <= ve + 0.01]
        exits = [c for c in mine if c["exit"] and c["t"] >= ve - EXIT_WINDOW]

        if not exits and cut_out:
            res.note(T("%s sale por corte, declarado por la marca (exits.cut_out)", "%s exits on a cut, declared by the brand (exits.cut_out)") % b["id"])
            continue
        if not exits:
            res.fail("beat-exit-hard-cut",
                     T("%s sale por corte duro — el default es salir como entró", "%s exits on a hard cut — the default is to leave the way it came in") % b["id"],
                     T("ninguna retirada con EASE_EXIT/drawOff en los %.1fs previos a %.2fs", "no retreat with EASE_EXIT/drawOff in the %.1fs before %.2fs")
                     % (EXIT_WINDOW, ve))
            continue

        start = min(c["t"] for c in exits)
        res.note(T("%s se retira desde %.2fs (cierra %.2fs)", "%s retreats from %.2fs (closes at %.2fs)") % (b["id"], start, ve))

        entered = set()
        for c in mine:
            if c["t"] < start - 0.01 and not c["exit"] and not c["furniture"]:
                entered |= (c["ids"] & own)
        left = set()
        for c in exits:
            left |= (c["ids"] & own)
        covered = {t for t in entered if t in left or (up.get(t, set()) & left)}
        missing = sorted(entered - covered)
        if entered and len(covered) < COVERAGE_MIN * len(entered):
            res.warn("beat-exit-partial",
                     T("%s: %d de %d elementos entran y no se retiran", "%s: %d of %d elements enter and never retreat")
                     % (b["id"], len(missing), len(entered)),
                     " · ".join(missing[:8]))

        # what was drawn has to be un-drawn: a fade leaves the stroke standing
        for sel in set(re.findall(r"drawOn\(\s*[\"'`]?#?\.?([\w-]+)", script)):
            target = var2id.get(sel, sel)
            if target not in own:
                continue
            if re.search(r"drawOff\(\s*[\"'`]?#?\.?%s\b" % re.escape(sel), script):
                continue
            if target in left or (up.get(target, set()) & left):
                continue
            res.fail("beat-exit-stroke-left",
                     T("%s: `%s` se dibuja con drawOn y nunca se des-dibuja", "%s: `%s` is drawn on with drawOn and never drawn off") % (b["id"], sel),
                     T("lo que se dibujó se des-dibuja: es la salida que se lee", "what was drawn on gets drawn off: that is the exit the viewer reads"))

        # the retreat lands on the cut — otherwise the last frames are empty.
        # Every exit-style event inside the window counts, background texture
        # included: beats never overlap, so the window identifies the owner, and
        # the texture is exactly what holds the frame until the cut.
        window_exits = [c for c in evs if c["exit"]
                        and start - 0.01 <= c["t"] <= ve + 0.01] or exits
        landing = ve - max(c["t"] + c["dur"] for c in window_exits)
        if landing > LANDING_TOL:
            res.warn("beat-exit-early",
                     T("%s termina de retirarse %.2fs antes del corte", "%s finishes retreating %.2fs before the cut") % (b["id"], landing),
                     T("acortar la ventana de retirada para que el último elemento termine "
                     "justo en el corte, o el frame queda vacío antes de cerrar",
                       "shorten the retreat window so the last element finishes "
                     "right on the cut, or the frame is left empty before it closes"))

    return res.emit()


if __name__ == "__main__":
    sys.exit(main())
