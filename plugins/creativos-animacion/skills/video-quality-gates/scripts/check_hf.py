#!/usr/bin/env python3
"""Gate: the HyperFrames framework's own check, made blocking.

`npx hyperframes check` knows the framework contract better than any parser
here: it flags GSAP writing `autoAlpha` on a clip element (the framework owns
clip visibility), caption exits with no hard kill, layout overflow and WCAG
contrast. On CLB ep2 it reported `caption_exit_missing_hard_kill` 39 times over
12 sessions; it was read as noise until it turned out to be the missing kill
behind a visible double exposure. A check whose red is normal stops being read,
so here it blocks — except for the codes the client profile lists, each with
the reason it does not apply.

`content_overlap` compares text boxes and nothing else, so a caption hidden
under a full-frame opaque beat "overlaps" the beat's own text. With
`hf_check.caption_under_beat` in the profile, each such overlap is measured in
Chrome (measure_stacking.js): the timeline is sought to every sampled second
and the overlap is dropped only when the caption paints below the beat, inside
its box, while the beat is 100% opaque — and the drop is printed, never silent.
On CLA ep4 Snippet 2 the check called caption #20 over the beat's own label an
error for 0.75s; the frames show only the beat.

    python3 check_hf.py <project-dir>

Runs only when the client profile sets `hf_check`. Exit 2 when the CLI cannot
run or its output cannot be read — never a silent pass.
"""

import json
import os
import re
import subprocess
import sys

import _common as C
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)

# the caption side of a content_overlap, as hyperframes names it in a selector
CAPTION_SEL_RE = re.compile(r"#cap[\w-]*|caption")
SAMPLE_STEP = 0.1        # seconds between the times the stacking is checked at


def main():
    d = C.project_dir(sys.argv)
    res = C.Result("hf-check", d)
    cfg = C.PROFILE.get("hf_check") or {}
    if not cfg:
        res.note(T("el perfil del cliente no pide este gate", "the client profile does not ask for this gate"))
        return res.emit()
    ignore = cfg.get("ignore") or {}

    npx = C.P.npx_command()
    try:
        if not npx:
            raise OSError(T("Node.js no está instalado (falta npx) — run_gates.py --doctor", "Node.js is not installed (npx is missing) — run_gates.py --doctor"))
        out = C.P.run_text(npx + ["--yes", "hyperframes", "check", "--json",
                                  "--samples", str(cfg.get("samples", 5))],
                           cwd=d, timeout=600)
    except (OSError, subprocess.SubprocessError) as e:
        res.warn("hf-check-not-run", T("no pude correr `npx hyperframes check`: %s", "could not run `npx hyperframes check`: %s") % e)
        res.emit()
        return 2
    raw = out.stdout or ""
    try:
        data = json.loads(raw[raw.find("{"):])
    except ValueError:
        res.warn("hf-check-unreadable", T("la salida de `hyperframes check --json` no se pudo leer", "could not read the output of `hyperframes check --json`"))
        res.emit()
        return 2

    under_beat = bool(cfg.get("caption_under_beat"))
    beats = C.beats(C.read_html(d)) if under_beat else []
    pending = []
    seen = 0
    for section in ("lint", "runtime", "layout", "motion", "contrast"):
        block = data.get(section) or {}
        for f in block.get("findings") or []:
            seen += 1
            code = f.get("code") or "?"
            sev = (f.get("severity") or "").lower()
            where = f.get("selector") or ""
            msg = (f.get("message") or "").replace("\n", " ")
            if code in ignore:
                continue
            text = "%s/%s %s — %s" % (section, code, where, msg[:150])
            q = _under_beat_query(f, beats) if under_beat else None
            if q:
                pending.append((sev, code, text, f, q))
                continue
            _report(res, sev, code, text)

    if pending:
        results = _measure_stacking(d, [p[4] for p in pending])
        dropped = []
        for i, (sev, code, text, f, q) in enumerate(pending):
            r = results[i] if results else None
            if r and r.get("covered"):
                dropped.append(T("«%s» %.2f–%.2fs bajo %s (caption z%s, beat z%s, opaco en %d muestra(s))", "“%s” %.2f–%.2fs under %s (caption z%s, beat z%s, opaque in %d sample(s))")
                               % (f.get("text") or q["caption"], q["times"][0], q["times"][-1],
                                  q["beat"], r.get("capZ"), r.get("beatZ"), len(r.get("samples") or [])))
            else:
                _report(res, sev, code, text,
                        T("no se descarta: %s", "not dropped: %s") % r["why"] if r and r.get("why") else None)
        if results is None:
            res.warn("stacking-not-measured",
                     T("no pude medir en el navegador si el caption queda tapado por el beat — "
                     "%d encimado(s) quedan como los reporta hyperframes",
                       "could not measure in the browser whether the caption is covered by the beat — "
                     "%d overlap(s) stay as hyperframes reports them") % len(pending))
        if dropped:
            res.note(T("%d encimado(s) de caption tapado por un beat opaco, descartados: %s", "%d caption overlap(s) hidden under an opaque beat, dropped: %s")
                     % (len(dropped), " · ".join(dropped)))

    ver = (data.get("_meta") or {}).get("version", "?")
    res.note(T("hyperframes check %s · %d hallazgo(s) leídos · ignorados por el perfil: %s", "hyperframes check %s · %d finding(s) read · ignored by the profile: %s")
             % (ver, seen, ", ".join(sorted(ignore)) or T("ninguno", "none")))
    return res.emit()


def _report(res, sev, code, text, evidence=None):
    if sev == "error":
        res.fail("hf-" + code, text, evidence)
    elif sev == "warning":
        res.warn("hf-" + code, text, evidence)


def _under_beat_query(f, beats):
    """The stacking question for a content_overlap between a caption and a beat's
    text that lasts, start to end, inside one beat's visible window — or None."""
    if f.get("code") != "content_overlap":
        return None
    a, b = f.get("selector") or "", f.get("containerSelector") or ""
    if CAPTION_SEL_RE.search(a):
        cap, other = a, b
    elif CAPTION_SEL_RE.search(b):
        cap, other = b, a
    else:
        return None
    t0 = f.get("firstSeen", f.get("time"))
    t1 = f.get("lastSeen", t0)
    if not other or t0 is None:
        return None
    t1 = t0 if t1 is None else t1
    for bt in beats:
        if bt["visible_start"] - 0.01 <= t0 and t1 <= bt["visible_end"] + 0.01:
            n = max(1, int(round((t1 - t0) / SAMPLE_STEP)))
            times = sorted({round(t0 + (t1 - t0) * k / n, 3) for k in range(n + 1)})
            return {"caption": cap, "other": other, "beat": bt["id"], "times": times}
    return None


def _measure_stacking(d, queries):
    """measure_stacking.js results in query order, or None when Chrome cannot answer."""
    js = os.path.join(os.path.dirname(os.path.abspath(__file__)), "measure_stacking.js")
    out = C.P.run_node(js, [d, json.dumps(queries)], timeout=300)
    if out is None or out.returncode != 0:
        return None
    try:
        got = json.loads(out.stdout.strip().splitlines()[-1])["results"]
    except (ValueError, KeyError, IndexError):
        return None
    return got if len(got) == len(queries) else None


if __name__ == "__main__":
    sys.exit(main())
