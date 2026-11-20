#!/usr/bin/env python3
"""Gate: beat variety, count and pacing.

Runs across the whole episode, not one project: repetition is something the
viewer notices between deliverables as much as inside one.

    python3 check_variety.py <project-dir>          # + its sibling projects
    python3 check_variety.py <project-dir> --solo   # this project only
"""

import os
import re
import sys

import _common as C
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)

OPEN_ON_SPEAKER = 5.0     # no graphic before this
MAX_BEATS = [(60.0, 2), (90.0, 3), (1e9, 4)]   # snippet duration → beat cap
MAX_BEAT_DUR = 8.0        # hard cap per beat — the editor, 2026-09-09, CLA ep4
MIN_GAP = 5.0             # face time between two beats; 3s reads as a mistake
DEAD_HOLD = 2.5           # silence after the last reveal, or before the first
CUT_TOL = 0.05            # a beat may open or close on a cut, never across it


def main():
    d = C.project_dir(sys.argv)
    solo = "--solo" in sys.argv
    html = C.read_html(d)
    r = C.root(html)
    bts = C.beats(html)
    res = C.Result("variety", d)
    V = C.PROFILE["variety"]
    OPEN_ON_SPEAKER = float(V["open_on_speaker"])
    MAX_BEATS = [tuple(x) for x in V["beat_caps"]]
    MAX_BEAT_DUR = float(V["max_beat_dur"])
    MIN_GAP = float(V["min_gap"])
    DEAD_HOLD = float(V["dead_hold"])

    if not bts:
        res.warn("no-beats", T("no encontré beats", "no beats found"))
        return res.emit()

    # "the end of the video" is the end of the speech when a fixed outro card follows
    video_end = C.speech_end(html, r["duration"])
    res.note("%d beat(s) · video %.2fs%s" % (len(bts), r["duration"],
                                             (T(" · el outro empieza en %.2fs", " · the outro starts at %.2fs") % video_end)
                                             if video_end != r["duration"] else ""))
    pips = _pip_windows(html, V["pip_re"], r["duration"]) if V.get("pip_re") else []
    if pips:
        res.note(T("PiP del speaker visible: %s", "speaker PiP visible: %s")
                 % ", ".join("%.2f–%.2f" % w for w in pips))

    def pip_covers(a, b, tol=0.5):
        return any(s0 <= a + tol and e0 >= b - tol for s0, e0 in pips)

    # beats with no video between them form one block
    blocks, cur = [], [bts[0]]
    for a, b in zip(bts, bts[1:]):
        if abs(b["visible_start"] - a["visible_end"]) <= 0.05:
            cur.append(b)
        else:
            blocks.append(cur)
            cur = [b]
    blocks.append(cur)

    # 1 — the viewer meets a person before they meet a graphic
    if bts[0]["visible_start"] < OPEN_ON_SPEAKER - 0.01:
        res.fail("open-on-speaker",
                 T("el primer gráfico entra en %.2fs; el video abre viendo al speaker (mín %.1fs)", "the first graphic comes in at %.2fs; the video opens on the speaker (min %.1fs)")
                 % (bts[0]["visible_start"], OPEN_ON_SPEAKER))

    # 2 — beat count scales with duration, and the cap is a cap
    series = _series_map(bts) if V.get("series") else {}
    if series:
        groups = {}
        for b in bts:
            if b["id"] in series:
                groups.setdefault(series[b["id"]][0], []).append(series[b["id"]][1])
        for name, idx in groups.items():
            res.note(T("serie «%s»: %d punto(s) (%s) — cuenta como una sola animación para el tope", "series “%s”: %d point(s) (%s) — counts as a single animation toward the cap")
                     % (name, len(idx), ", ".join(str(i) for i in sorted(idx))))
            want = next((series[b["id"]][2] for b in bts
                         if b["id"] in series and series[b["id"]][0] == name and series[b["id"]][2]), None)
            expected = list(range(1, (want or max(idx)) + 1))
            if sorted(idx) != expected:
                res.fail("series-incomplete",
                         T("la serie «%s» tiene los puntos %s y la enumeración tiene %d", "series “%s” has points %s but the enumeration has %d")
                         % (name, ", ".join(str(i) for i in sorted(idx)), len(expected)),
                         T("una animación por cada punto que se enumera — ni uno menos, ni repetido", "one animation per enumerated point — none missing, none repeated"))

    if r["portrait"]:
        cap = next(n for lim, n in MAX_BEATS if r["duration"] <= lim)
        if series:
            counted = len([b for b in bts if b["id"] not in series]) + \
                len({v[0] for v in series.values()})
            unit = T("animación(es) contando cada serie como una", "animation(s) (each series counted as one)")
        else:
            counted, unit = len(bts), "beats"
        if counted > cap:
            res.fail("too-many-beats",
                     T("%d %s para un snippet de %.0fs — el máximo es %d", "%d %s for a %.0fs snippet — the maximum is %d")
                     % (counted, unit, r["duration"], cap))

    # 2b — a beat lasts as long as the line it illustrates, never more than 8s
    for b in bts:
        dur = b["visible_end"] - b["visible_start"]
        rides_out = video_end and b["visible_end"] >= video_end - 0.2
        if (rides_out and V.get("ride_out_exempt_with_pip")
                and pip_covers(b["visible_start"], b["visible_end"])):
            res.note(T("%s dura %.2fs y sale con el video con el speaker en PiP — exento del máximo", "%s lasts %.2fs and runs to the end of the video with the speaker in PiP — exempt from the maximum")
                     % (b["id"], dur))
            continue
        if dur > MAX_BEAT_DUR + 0.01:
            res.fail("beat-too-long",
                     T("%s dura %.2fs — el máximo es %.1fs", "%s lasts %.2fs — the maximum is %.1fs") % (b["id"], dur, MAX_BEAT_DUR),
                     T("una animación dura lo que dura la frase que ilustra; si el usuario pidió "
                     "explícitamente que ésta durara más, citá su pedido en el reporte",
                       "an animation lasts as long as the sentence it illustrates; if the user "
                     "explicitly asked for this one to last longer, quote their request in the report"))

    # 3 — holes between beats
    for a, b in zip(bts, bts[1:]):
        gap = b["visible_start"] - a["visible_end"]
        if (V.get("contiguous_with_pip") and abs(gap) <= 0.05
                and pip_covers(a["visible_start"], b["visible_end"])):
            continue          # one block, the speaker stays on screen in the PiP
        if -0.02 <= gap < MIN_GAP:
            res.fail("beat-gap",
                     T("%s y %s dejan %.2fs de video en el medio — el mínimo es %.1fs", "%s and %s leave %.2fs of video between them — the minimum is %.1fs")
                     % (a["id"], b["id"], gap, MIN_GAP),
                     T("menos que eso se ve como un error, y pegadas no se ve a nadie hablar; "
                     "entre dos animaciones va cara con captions",
                       "anything shorter looks like a mistake, and back to back no one is seen talking; "
                     "between two animations, show the face with captions"))
        elif gap < -0.02:
            res.fail("beat-overlap", T("%s y %s se superponen %.2fs", "%s and %s overlap by %.2fs") % (a["id"], b["id"], -gap))

    # 3b — the declared clip window must match what the timeline shows
    for b in bts:
        if abs(b["visible_start"] - b["start"]) > 0.25 or abs(b["visible_end"] - b["end"]) > 0.25:
            res.fail("beat-window-mismatch",
                     T("%s declara data-start/duration %.2f–%.2f pero el timeline lo muestra "
                     "%.2f–%.2f",
                       "%s declares data-start/duration %.2f–%.2f but the timeline shows it at "
                     "%.2f–%.2f") % (b["id"], b["start"], b["end"],
                                    b["visible_start"], b["visible_end"]),
                     T("el track y lo que se ve tienen que coincidir", "the track and what is on screen have to match"))

    # 4 — dead air inside a beat, at either end
    times = _event_times(html)
    for b in bts:
        vs, ve = b["visible_start"], b["visible_end"]
        inside = sorted(t for t in times if vs + 0.15 < t < ve - 0.05)
        if not inside:
            continue
        lead = inside[0] - vs
        tail = ve - inside[-1]
        if lead > DEAD_HOLD:
            res.fail("dead-lead",
                     T("%s se abre %.1fs antes de que aparezca su primer elemento", "%s opens %.1fs before its first element appears")
                     % (b["id"], lead),
                     T("visible desde %.2fs, primer evento en %.2fs", "visible from %.2fs, first event at %.2fs") % (vs, inside[0]))
        if tail > DEAD_HOLD and b is not bts[-1]:
            res.fail("dead-hold",
                     T("%s sostiene %.1fs sin mostrar nada nuevo antes de salir", "%s holds for %.1fs without showing anything new before it exits") % (b["id"], tail),
                     T("último evento en %.2fs, cierra en %.2fs", "last event at %.2fs, closes at %.2fs") % (inside[-1], ve))

    # 3c — how the video ends: on the speaker, never a moment after a graphic
    last = bts[-1]
    tail_gap = video_end - last["visible_end"] if video_end else None
    ef = V.get("end_flash")
    if ef and tail_gap is not None and ef[0] < tail_gap < ef[1]:
        res.fail("end-flash",
                 T("%s termina %.2fs antes del final — el video aparece un instante y corta", "%s ends %.2fs before the end — the video appears for an instant and cuts")
                 % (last["id"], tail_gap),
                 T("o la animación llega hasta el final, o deja al menos %.1fs de cara", "either the animation runs to the end, or it leaves at least %.1fs of face") % ef[1])
    if (V.get("end_on_graphic") and tail_gap is not None and tail_gap <= 0.2
            and not pip_covers(video_end - 1.0, video_end, tol=0.05)):
        res.fail("end-on-graphic",
                 T("%s llega hasta el final y el speaker no está en pantalla — el video cierra en él", "%s runs to the end and the speaker is not on screen — the video ends on the speaker")
                 % last["id"],
                 T("dejar la cara al final, o mantener el PiP visible hasta el último frame", "leave the face at the end, or keep the PiP visible until the last frame"))

    # 4b — one animation never covers two speakers. `beat_across_cut` is one value
    # for every format or one per format ({"snippet": false, "teaser": "detected"}):
    # false = off (one speaker, a cut under a beat is a jump cut it hides); true =
    # every cut, listed or detected; "detected" = only what scene detection sees —
    # a speaker change — because a two-host teaser also lists the jump cuts inside
    # each host's stretch, and a beat may cover those.
    bac = V.get("beat_across_cut", True)
    fmt = "snippet" if r["portrait"] else "teaser"
    if isinstance(bac, dict):
        bac = bac.get(fmt, True)
    ci = C.cut_info(d, html) if bac else None
    if not ci:
        cuts = False
    elif bac == "detected":
        cuts = ci["detected"]
    else:
        cuts = ci["cuts"]
    if cuts is False:
        pass                  # one speaker per video: a cut under a beat is a jump cut it hides
    elif cuts is None:
        res.warn("cut-detect-skipped",
                 T("no pude leer el video del proyecto ni hay cuts.txt — no verifiqué los cambios de plano", "could not read the project's video and there is no cuts.txt — camera cuts not checked"))
    else:
        res.note(T("cortes de cámara%s: %s (%s)", "camera cuts%s: %s (%s)")
                 % (T(" que ve la detección de escena (cambios de speaker; los de cuts.txt no cuentan)", " seen by scene detection (speaker changes; the ones in cuts.txt do not count)")
                    if bac == "detected" else "",
                    ", ".join("%.2f" % c for c in cuts) or T("ninguno", "none"), ci["summary"]))
        for b in bts:
            vs, ve = b["visible_start"], b["visible_end"]
            crossed = [c for c in cuts if vs + CUT_TOL < c < ve - CUT_TOL]
            if crossed:
                res.fail("beat-across-cut",
                         T("%s (%.2f–%.2f) cruza un cambio de plano en %s", "%s (%.2f–%.2f) crosses a camera cut at %s")
                         % (b["id"], vs, ve, ", ".join("%.2fs" % c for c in crossed)),
                         T("una animación no puede cubrir a dos speakers: tiene que terminar "
                         "antes del corte o empezar después",
                           "an animation cannot cover two speakers: it has to end "
                         "before the cut or start after it"))

    # 5 — device and structure across the episode
    projects = [d] if solo else _episode(d)
    rows = []
    for p in projects:
        try:
            ph = C.read_html(p)
        except OSError:
            continue
        pbts = C.beats(ph)
        smap = _series_map(pbts) if V.get("series") else {}
        for b in pbts:
            rows.append({
                "project": os.path.basename(p), "id": b["id"],
                "device": b["device"] or "(sin nombrar)",
                "shape": _fingerprint(b["html"]),
                "series": smap.get(b["id"], (None,))[0],
            })
    if len(projects) > 1:
        res.note(T("episodio: %d proyecto(s), %d beat(s)", "episode: %d project(s), %d beat(s)") % (len(projects), len(rows)))

    named = {}
    for row in rows:
        if row["device"] == "(sin nombrar)":
            continue
        named.setdefault(row["device"], []).append(row)
    dupes = {}
    for k, v in named.items():
        if len(v) < 2:
            continue
        keys = {(x["project"], x["series"]) for x in v}
        # an older comment that names the series ("RED FLAG 3") instead of the
        # device is not a repeated device — inside its own series it says nothing
        if len(keys) == 1 and list(keys)[0][1] and \
                (k in list(keys)[0][1] or list(keys)[0][1] in k):
            continue
        dupes[k] = ["%s/%s" % (x["project"], x["id"]) for x in v]
    if dupes:
        res.fail("device-repeat",
                 T("%d device(s) se repiten en el episodio", "%d device(s) repeated in the episode") % len(dupes),
                 " · ".join("%s → %s" % (k, ", ".join(v)) for k, v in dupes.items()))

    shapes = {}
    for row in rows:
        shapes.setdefault(row["shape"], []).append(row)
    # the numbered frame of a series repeats by design — a repeat counts only when
    # it leaves the series (another project, or a beat outside the series)
    shape_dupes = {}
    for k, v in shapes.items():
        if len(v) < 2:
            continue
        keys = {(x["project"], x["series"]) for x in v}
        if len(keys) == 1 and list(keys)[0][1]:
            continue
        shape_dupes[k] = ["%s/%s" % (x["project"], x["id"]) for x in v]
    if shape_dupes and not V.get("structure_repeat", True):
        # calibrated on CLA markup; on a client whose markup it cannot read it
        # flags different devices and misses real repeats — the profile turns it off
        shape_dupes = {}
    if shape_dupes:
        res.fail("structure-repeat",
                 T("%d forma(s) internas repetidas — la regla de cero repetición es de estructura, "
                 "no solo de nombre",
                   "%d repeated internal shape(s) — the zero-repetition rule is about structure, "
                 "not just the name") % len(shape_dupes),
                 " · ".join("[%s] → %s" % (k, ", ".join(v)) for k, v in shape_dupes.items()))

    if V.get("series"):
        with_series = sorted({r2["project"] for r2 in rows if r2["series"]})
        if len(with_series) > 1:
            res.warn("series-in-several",
                     T("%d proyecto(s) de la tanda tienen una serie numerada: %s", "%d project(s) in the batch have a numbered series: %s")
                     % (len(with_series), ", ".join(with_series)),
                     T("el marco numerado tiene que verse distinto en cada uno — the other editor lo marcó "
                     "como plantilla repetida en CLB ep2 (S2 y S4)",
                       "the numbered frame has to look different in each one — the other editor flagged it "
                     "as a repeated template in CLB ep2 (S2 and S4)"))

    if V.get("ground_repeat"):
        grounds = _beat_grounds(html)
        res.note(T("fondo de cada beat: %s", "ground of each beat: %s") % " · ".join("%s=%s" % (bid, _short_ground(bg)) for bid, bg, _ in grounds))
        # With few beats no two share a ground; with more beats than the brand has
        # grounds that is impossible, and only two in a row are forbidden
        # (`ground_unique_up_to`: the number of beats up to which no repeat is allowed)
        # The mode follows the number of beats, read or not, and "in a row" means two beats
        # next to each other: a beat whose ground cannot be read (ground-unread, below) is
        # still a beat between its neighbours, never a reason to compare them.
        known = [(bid, bg) for bid, bg, _ in grounds if bg]
        up_to = int(V.get("ground_unique_up_to", 3))
        by = {}
        if len(grounds) <= up_to:
            for bid, bg in known:
                by.setdefault(bg, []).append(bid)
        else:
            for (a_id, a_bg, _), (b_id, b_bg, _) in zip(grounds, grounds[1:]):
                if a_bg and a_bg == b_bg:
                    ids = by.setdefault(a_bg, [])
                    ids.extend(x for x in (a_id, b_id) if x not in ids)
        same = {bg: ids for bg, ids in by.items() if len(ids) > 1}
        if same:
            res.fail("ground-repeat",
                     T("%d fondo(s) se repiten dentro del proyecto — %s", "%d ground(s) repeated within the project — %s")
                     % (len(same), T("dos beats no comparten fondo", "no two beats share a ground") if len(grounds) <= up_to
                        else T("con %d beats, ningún par seguido comparte fondo", "with %d beats, no two beats in a row share a ground") % len(grounds)),
                     " · ".join("%s → %s" % (_short_ground(bg), ", ".join(ids)) for bg, ids in same.items()))
        unread = [bid for bid, bg, _ in grounds if not bg]
        if unread:
            res.warn("ground-unread",
                     T("no pude leer el fondo de %d beat(s) — no verifiqué que no repitan", "could not read the ground of %d beat(s) — not checked for repeats") % len(unread),
                     ", ".join(unread))

    sr = V.get("scheme_rotation")
    if sr and len(projects) > 1:
        doms = []
        for p in projects:
            try:
                doms.append((os.path.basename(p), _dominant_ground(C.read_html(p))))
            except OSError:
                continue
        res.note(T("fondo dominante por proyecto: %s", "dominant ground per project: %s")
                 % " · ".join("%s=%s" % (n, g or "?") for n, g in doms))
        repeats = [T("%s y %s (%s)", "%s and %s (%s)") % (a[0], b[0], a[1]) for a, b in zip(doms, doms[1:])
                   if a[1] and a[1] == b[1]]
        if repeats:
            res.fail("scheme-repeat",
                     T("%d par(es) de proyectos seguidos con el mismo fondo dominante", "%d pair(s) of consecutive projects with the same dominant ground") % len(repeats),
                     " · ".join(repeats[:6]))

    unnamed = [r2 for r2 in rows if r2["device"] == "(sin nombrar)"]
    if unnamed:
        res.warn("device-unnamed",
                 T("%d beat(s) sin comentario <!-- Beat N — device: ... --> — no puedo comparar", "%d beat(s) without a <!-- Beat N — device: ... --> comment — cannot compare")
                 % len(unnamed),
                 " · ".join("%s/%s" % (u["project"], u["id"]) for u in unnamed[:6]))

    return res.emit()


def _episode(d):
    """Every sibling HyperFrames project of the same episode."""
    parent = os.path.dirname(d.rstrip("/\\"))
    out = []
    try:
        for name in sorted(os.listdir(parent)):
            p = os.path.join(parent, name)
            if os.path.isfile(os.path.join(p, "index.html")):
                out.append(p)
    except OSError:
        return [d]
    return out or [d]


def _fingerprint(frag):
    """A shape signature: what the eye reads as 'the same graphic'.

    Nine features, not four. With four the signature had 12 possible slots, so
    nine beats in one episode collided by arithmetic — CLA ep4 reported a map
    outline, a ledger, a layout shift and a three-step chain as the same shape.
    A repeat now has to match on structure *and* on what is drawn.
    """
    has_box = bool(re.search(r'id="box|class="[^"]*(?:box|card|ledger)', frag)) or \
        bool(re.search(r"<rect[^>]*(?:stroke|fill=\"none\")", frag))
    has_leaders = "leader" in frag or bool(re.search(r'class="[^"]*leader', frag))
    rows = len(re.findall(r'class="[^"]*(?:row|label|sta|tile|bar|stamp|col)[\w-]*"', frag))
    cols = 2 if re.search(r"col-head|column|comparison|split", frag) else 1
    band = "rows0" if rows == 0 else ("rows1-3" if rows <= 3 else
                                      ("rows4-6" if rows <= 6 else "rows7+"))

    # what is actually drawn — two graphics with the same skeleton but one made
    # of strokes and the other of type do not read as the same picture
    strokes = len(re.findall(r"<(?:path|line|polyline|polygon)\b", frag))
    stroke_band = "s0" if strokes == 0 else ("s1-2" if strokes <= 2 else
                                             ("s3-6" if strokes <= 6 else "s7+"))
    dots = len(re.findall(r"<circle\b", frag))
    dot_band = "d0" if dots == 0 else ("d1-3" if dots <= 3 else "d4+")
    dashed = "dash" if "stroke-dasharray" in frag else "solid"
    axis = "axis" if re.search(r'class="[^"]*(?:axis|tick|scale|track|timeline|ruler)', frag) else "noaxis"
    quote = "quote" if re.search(r'class="[^"]*(?:quote|pull|mark)', frag) else "noquote"

    return "%s|%s|%s|%dcol|%s|%s|%s|%s|%s" % (
        "box" if has_box else "nobox",
        "leaders" if has_leaders else "noleaders", band, cols,
        stroke_band, dot_band, dashed, axis, quote)


CONST_RE = re.compile(r"(?:const|let|var)?\s*\b([A-Za-z_]\w*)\s*=\s*(-?\d+(?:\.\d+)?)\s*(?=[,;])")
CALL_RE = re.compile(r"tl\.(?:set|to|fromTo)\s*\(")
AT_RE = re.compile(r"\bat\s*:\s*([^,}\n]+)")
# Neither the beat container nor its background texture counts as "content
# appearing" — a beat can be on screen and still be empty.
NOT_CONTENT = ("#beat-", "topo", "tex", "grid-texture", "#frame-fx", "box-mask")


def _event_times(html):
    """Absolute times of every timeline event that puts content on screen."""
    script = C.script_text(html)
    consts = C.const_table(CONST_RE, script)
    times = []

    for m in CALL_RE.finditer(script):
        args = C.js_call_args(script, m.end() - 1)
        if not args:
            continue
        target = args[0]
        if any(k in target for k in NOT_CONTENT):
            continue
        v = _eval(_last_arg(args), consts)
        if v is not None:
            times.append(v)

    # positional helper calls — claTextReveal("#sel", T), popIn("#sel", T, D)
    for m in re.finditer(r"\b([a-zA-Z_]\w*)\s*\(\s*[\"'`]([^\"'`]+)[\"'`]\s*,", script):
        fn, target = m.group(1), m.group(2)
        if fn in ("getElementById", "querySelector", "querySelectorAll",
                  "createElementNS", "setAttribute", "addEventListener", "replace"):
            continue
        if any(k in target for k in NOT_CONTENT):
            continue
        args = C.js_call_args(script, script.index("(", m.start()))
        if len(args) < 2:
            continue
        v = _eval(args[1], consts)
        if v is not None:
            times.append(v)

    # helper calls — drawOn(sel, {at: T}), lineReveal(sel, {at: T, dur: D}) …
    for m in AT_RE.finditer(script):
        line_start = script.rfind("\n", 0, m.start()) + 1
        line = script[line_start:m.start()]
        if any(k in line for k in NOT_CONTENT):
            continue
        v = _eval(m.group(1), consts)
        if v is not None:
            times.append(v)

    return times


def _last_arg(args):
    return args[-1].strip() if args else None


EXPR_RE = re.compile(r"^([A-Za-z_]\w*|-?\d+(?:\.\d+)?)"
                     r"(?:\s*([+\-])\s*([A-Za-z_]\w*|-?\d+(?:\.\d+)?))?$")


def _eval(expr, consts):
    return C._expr(expr, consts) if expr is not None else None


SERIES_DECL_RE = re.compile(r"series\s*:\s*([A-Za-z][\w ]*?)\s+(\d+)\s*/\s*(\d+)", re.I)
SERIES_LABEL_RE = re.compile(r"\b([A-Za-z]{2,}(?:\s+[A-Za-z]{2,}){0,2})\s*#\s*(\d{1,2})\b")


def _series_map(bts):
    """beat id -> (series name, index, declared total or None).

    New builds declare it in the beat comment: `series: red flags 2/5`. Older
    projects carry it only as a numbered label on screen ("RED FLAG #2"); that
    counts as a series only when two or more beats share the label.
    """
    out, labels = {}, {}
    for b in bts:
        m = SERIES_DECL_RE.search(b.get("comment") or "")
        if m:
            out[b["id"]] = (m.group(1).strip().lower(), int(m.group(2)), int(m.group(3)))
            continue
        txt = re.sub(r"<[^>]+>", " ", b.get("html") or "")
        lm = SERIES_LABEL_RE.search(txt)
        if lm:
            labels.setdefault(lm.group(1).strip().lower(), []).append((b["id"], int(lm.group(2))))
    for name, items in labels.items():
        if len(items) >= 2:
            for bid, i in items:
                out[bid] = (name, i, None)
    return out


def _pip_windows(html, pip_re, duration):
    """When a picture-in-picture of the speaker is on screen, from the timeline.

    Every on → off stretch of every wrap is its own window. One window per id
    (first on, last off) used to cover the video between two runs that share a
    wrap, and forced a second wrap id on every closing beat.
    """
    script = C.script_text(html)
    consts = C.const_table(CONST_RE, script)
    out = []
    for pid in sorted(set(re.findall(r'\bid="(' + pip_re + r')"', html))):
        rx = re.compile(r"tl\.(set|to|from)\(\s*[\"'`]#" + re.escape(pid) +
                        r"[\"'`]\s*,\s*(\{[^}]*(?:opacity|autoAlpha):\s*([01])(?:\.0+)?(?![\d.])[^}]*\})\s*,\s*([^)]+)\)")
        events = []
        for m in rx.finditer(script):
            kind, obj, val, expr = m.groups()
            t = _eval(expr.strip(), consts)
            if t is None:
                continue
            if kind == "from":
                val = "1" if val == "0" else "0"
            if val == "1":
                events.append((t, 1))
            else:
                dm = re.search(r"duration:\s*([A-Za-z_]\w*|[\d.]+)", obj)
                dur = (_eval(dm.group(1), consts) or 0.0) if (dm and kind != "set") else 0.0
                events.append((t + dur, 0))
        on = None
        for t, up in sorted(events):
            if up and on is None:
                on = t
            elif not up and on is not None and t > on:
                out.append((on, t))
                on = None
        if on is not None:
            out.append((on, duration))
    return sorted(out)


def _short_ground(bg):
    """A ground for a message: the first colour of a gradient, else the value."""
    if not bg:
        return "?"
    m = re.search(r"#[0-9a-f]{3,8}\b|rgba?\([^)]*\)", bg)
    return m.group(0) if m else (bg if len(bg) <= 28 else bg[:27] + "…")


def _beat_grounds(html):
    """[(beat id, ground value or None, seconds visible)] — what each beat sits on."""
    style = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))
    tokens = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", style))
    out = []
    for b in C.beats(html):
        tag = re.search(r'<div[^>]*\bid="%s"[^>]*>' % re.escape(b["id"]), html)
        cm = re.search(r'class="([^"]*)"', tag.group(0)) if tag else None
        classes = cm.group(1).split() if cm else []
        bg = None
        im = re.search(r'style="[^"]*background(?:-color)?\s*:\s*([^;"]+)', tag.group(0)) if tag else None
        if im:
            bg = im.group(1).strip()
        else:
            for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", style):
                bgm = re.search(r"background(?:-color)?\s*:\s*([^;]+)", rule.group(2))
                if not bgm:
                    continue
                for sel in rule.group(1).split(","):
                    sel = sel.strip()
                    parts = re.findall(r"\.([\w-]+)", sel.split()[-1]) if sel else []
                    if parts and all(p in classes for p in parts):
                        bg = bgm.group(1).strip()
        dur = b["visible_end"] - b["visible_start"]
        if not bg:
            out.append((b["id"], None, dur))
            continue
        vm = re.match(r"var\((--[\w-]+)\)", bg)
        if vm and vm.group(1) in tokens:
            bg = tokens[vm.group(1)].strip()
        out.append((b["id"], bg.lower(), dur))
    return out


def _dominant_ground(html):
    """The background most of a project's beats sit on, resolved to a value."""
    counts = {}
    for _, bg, dur in _beat_grounds(html):
        if bg:
            counts[bg] = counts.get(bg, 0.0) + dur
    return max(counts, key=counts.get) if counts else None


if __name__ == "__main__":
    sys.exit(main())
