#!/usr/bin/env python3
"""Gate: captions.

Every rule here traces to a correction the editor had to make more than once. Static
analysis of the CAPTIONS array against transcript.json — no browser needed.

    python3 check_captions.py <project-dir> [--teaser]
"""

import difflib
import json
import os
import re
import subprocess
import sys

import _common as C
import word_timing as WT
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)

CUT_TOL = 0.02          # a card may open or close on a cut, never across it
NEAR_LIMIT = 60         # px from max-width: one word away from breaking
# Duration floor, word band and client spelling come from the client profile
# (_profile.py) — CLA's defaults: 0.5s fail / 0.7s warn, 5 words on a snippet,
# 10 on a teaser, at least 3 unless the group closes a sentence.
MAX_WORDS_CLD = 3       # Barlow/DM Sans at 60px in a 900px track
MIN_WORDS_CLD = 2

# A caption line may not end on a word that is still reaching for the next one.
CONNECTORS = set("""
a an the and or but nor so yet
of to in at by with from into onto for than that this these those
about against among around before behind below beneath beside between beyond
during near through toward towards under until via within without
my your his her its our their whose
""".split())
CONNECTORS.discard("than")   # "more than" reads fine as a line ending

SENTENCE_END = (".", "!", "?", '."', '!"', '?"', ".”", "!”", "?”")

# a card ending on "going on," has closed its clause; the profile decides whether
# that exempts the connector (captions.connector_comma_closes)
CLAUSE_CLOSE = (",", ";", ":", "—", "–")     # the en dash too: "on–" closes like "on—"

# Fillers are dropped from the display on purpose (the editor, 2026-09-10: "elimina de
# los captions las palabras que son muletillas o que no llevan a nada, por
# ejemplo 'you know'"). They still sit in transcript.json, so word-for-word
# reconciliation would report them as lost every time. A word from this list is
# reported as dropped, not as missing; anything else is still a FAIL.
FILLER_WORDS = {"um", "uh", "uhh", "uhm", "erm", "ah", "eh", "hmm", "mm", "mhm"}
FILLER_PHRASES = [("you", "know"), ("i", "mean"), ("sort", "of", "of")]



def _spellings(prof):
    out = []
    for v in prof.get("vocabulary") or []:
        flags = re.I if "i" in (v.get("flags") or "") else 0
        out.append((re.compile(v["re"], flags), v["fix"]))
    return out


def main():
    d = C.project_dir(sys.argv)
    teaser = "--teaser" in sys.argv
    fast = "--fast" in sys.argv
    html = C.read_html(d)
    r = C.root(html)
    if not teaser:
        teaser = not r["portrait"]
    caps = C.captions(html)
    beats = C.beats(html)
    res = C.Result("captions", d)
    K = C.PROFILE["captions"]
    MIN_DUR_FAIL = float(K["min_dur_fail"])
    MIN_DUR_WARN = float(K["min_dur_warn"])
    MAX_WORDS_SNIPPET = int(K["max_words_snippet"])
    MAX_WORDS_TEASER = int(K["max_words_teaser"])
    MIN_WORDS = int(K["min_words"])
    BAD_SPELLINGS = _spellings(K)
    global NUMERALS_EQUAL
    NUMERALS_EQUAL = bool(K.get("numerals_equal"))
    CONT_TOL = float(K.get("continuity_tol", 0.011))

    def under_beat(t):
        """A full-screen beat hides the captions beneath it, so a gap or an
        uncaptioned word inside a beat window is by design, not a defect. The
        window is the one the timeline shows (`visible_*`), not the declared
        `data-start`/`data-duration`: CLD's segments declare the whole video and
        only appear for a few seconds, and every word read as "under a beat"."""
        return any(b["visible_start"] - 0.05 <= t <= b["visible_end"] + 0.05 for b in beats)

    def gap_is_a_beat(a, b):
        """True when a hole between two caption groups is a beat, not a bug."""
        span = b - a
        if span <= 0:
            return False
        # summed over every beat: a counted series runs back to back under a
        # PiP (CLB), and no single beat of the run covers the whole hole
        covered = sum(max(0.0, min(b, bt["visible_end"]) - max(a, bt["visible_start"])) for bt in beats)
        return covered / span > 0.8

    if not caps:
        res.fail("no-captions", "no CAPTIONS/GROUPS array found in index.html")
        return res.emit()

    # CLD is the one brand whose captions enter word by word and whose cards are
    # three words wide. Detected from its own design tokens rather than a flag,
    # so a CLD project cannot be checked against CLA's numbers by accident.
    cld = "--cld-" in html
    max_words = MAX_WORDS_CLD if cld else (MAX_WORDS_TEASER if teaser else MAX_WORDS_SNIPPET)
    min_words = MIN_WORDS_CLD if cld else MIN_WORDS
    res.note(T("%d grupos · %s%s · video %.2fs", "%d groups · %s%s · video %.2fs") % (
        len(caps), "teaser" if teaser else "snippet",
        T(" · marca CLD", " · CLD brand") if cld else "", r["duration"]))

    sp_end = C.speech_end(html, r["duration"])     # where the outro card starts, if the brand has one
    if sp_end != r["duration"]:
        res.note(T("outro desde %.2fs: el fin del habla es %.2fs (el video dura %.2fs)", "outro from %.2fs: the speech ends at %.2fs (the video lasts %.2fs)")
                 % (sp_end, sp_end, r["duration"]))

    # 1 — entrance/exit is a hard cut, unless the brand declares how its cards move
    animated = []
    for body in C.caption_bind_blocks(html):
        # fromTo, from and to all animate a card; only tl.set cuts it (a `tl.from` fade used to
        # pass as a cut — no caption block of CLA, CLB, CLE or CLD used one, 2026-10-03)
        animated.extend(re.findall(r"tl\.(?:fromTo|from|to)\(", body))
    decl = K.get("entrance")
    fmt = "teaser" if teaser else "snippet"
    if decl and fmt in (decl.get("applies_to") or ["snippet", "teaser"]):
        _check_entrance(res, html, decl, fmt, animated)
    elif animated and cld:
        # CLD's own style: each word drops in over 0.16s (`power3.out`) and the
        # card leaves with a 0.08s fade. Shipped in CLD ep1; the editor has never asked
        # CLD for the hard cut the other clients use.
        res.note(T("entrada palabra por palabra — estilo propio de CLD, no es un fade prohibido", "word-by-word entrance — CLD's own style, not a forbidden fade"))
    elif animated and teaser:
        # Approved by the editor on 2026-09-09 for the CLA teaser only: the line slides
        # in the way a headline does. "Probemos poner esa animación… Solo en
        # teaser" → confirmed as a keeper after seeing it.
        res.warn("caption-animated-teaser",
                 T("entrada animada de captions — aprobada sólo para teaser, nunca en snippet", "animated caption entrance — approved for the teaser only, never on a snippet"),
                 T("%d llamada(s) tl.fromTo/tl.from/tl.to dentro del bloque de captions", "%d tl.fromTo/tl.from/tl.to call(s) inside the captions block") % len(animated))
    elif animated:
        res.fail("caption-fade",
                 T("los captions están animados; en un snippet entran y salen por corte (tl.set)", "the captions are animated; on a snippet they enter and exit on a hard cut (tl.set)"),
                 T("%d llamada(s) tl.fromTo/tl.from/tl.to dentro del bloque de captions", "%d tl.fromTo/tl.from/tl.to call(s) inside the captions block") % len(animated))

    # 1b — one colour for every caption word (CLB: all white)
    aw = [c.lower() for c in (K.get("all_white") or [])]
    if aw:
        style = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))
        tinted = []
        for m in re.finditer(r"([^{}]*\.cap-word[^{}]*|[^{}]*caption-group[^{}]*)\{([^{}]*)\}", style):
            cm = re.search(r"(?<![-\w])color\s*:\s*([^;]+)", m.group(2))
            if cm and not any(a in cm.group(1).lower() for a in aw):
                tinted.append("%s { color: %s }" % (m.group(1).strip()[:40], cm.group(1).strip()))
        coloured = any(re.search(r"\bcolor\s*:", body) for body in C.caption_bind_blocks(html))
        if tinted or coloured:
            res.fail("caption-colour",
                     T("los captions llevan un color que no es el blanco de la marca", "the captions use a color that is not the brand's white"),
                     " · ".join(tinted[:4]) or T("tween de color dentro del bloque de captions", "color tween inside the captions block"))

    # 2 — a line that flickers cannot be read
    short = [(i, g) for i, g in enumerate(caps) if g["end"] - g["start"] < MIN_DUR_WARN]
    hard = [(i, g) for i, g in short if g["end"] - g["start"] < MIN_DUR_FAIL]
    if hard:
        res.fail("caption-flicker",
                 T("%d grupo(s) duran menos de %.1fs — ilegibles", "%d group(s) last under %.1fs — unreadable") % (len(hard), MIN_DUR_FAIL),
                 " · ".join('#%d "%s" %.2fs' % (i, g["text"], g["end"] - g["start"])
                            for i, g in hard[:6]))
    elif short:
        res.warn("caption-brief",
                 T("%d grupo(s) entre %.1f y %.1fs — al límite", "%d group(s) between %.1f and %.1fs — borderline") % (len(short), MIN_DUR_FAIL, MIN_DUR_WARN),
                 " · ".join('#%d "%s" %.2fs' % (i, g["text"], g["end"] - g["start"])
                            for i, g in short[:6]))

    # 3 — one line replaces the next with no gap and no overlap
    breaks = []
    for i in range(len(caps) - 1):
        gap = caps[i + 1]["start"] - caps[i]["end"]
        if gap > CONT_TOL and gap_is_a_beat(caps[i]["end"], caps[i + 1]["start"]):
            continue
        if abs(gap) > CONT_TOL:
            breaks.append("#%d→#%d %+.3fs" % (i, i + 1, gap))
    if breaks:
        res.fail("caption-continuity",
                 T("%d corte(s) con hueco o superposición", "%d card change(s) with a gap or an overlap") % len(breaks),
                 " · ".join(breaks[:8]))

    # 4 — a period always closes its line
    spill = []
    for i, g in enumerate(caps):
        for w in g["words"][:-1]:
            if w.endswith(SENTENCE_END):
                spill.append('#%d "%s"' % (i, g["text"]))
                break
    if spill:
        res.fail("caption-sentence-spill",
                 T("%d grupo(s) siguen después de un punto", "%d group(s) continue after a period") % len(spill),
                 " · ".join(spill[:6]))

    # 5 — length band
    long_g = [(i, g) for i, g in enumerate(caps) if len(g["words"]) > max_words]
    if long_g:
        res.fail("caption-too-long",
                 T("%d grupo(s) superan %d palabras", "%d group(s) have more than %d words") % (len(long_g), max_words),
                 " · ".join('#%d (%d) "%s"' % (i, len(g["words"]), g["text"]) for i, g in long_g[:6]))

    tiny = [(i, g) for i, g in enumerate(caps)
            if len(g["words"]) < min_words
            and not g["words"][-1].endswith(SENTENCE_END)
            and i != len(caps) - 1]
    if tiny:
        res.warn("caption-choppy",
                 T("%d grupo(s) de menos de %d palabras sin cerrar oración", "%d group(s) under %d words that do not close a sentence") % (len(tiny), min_words),
                 " · ".join('#%d "%s"' % (i, g["text"]) for i, g in tiny[:8]))

    # 6 — no connector left hanging at the end of a line — unless the speaker
    # pauses right there: what is said after a pause opens the next card, so a
    # connector before a measured pause of the profile's minimum stays (the editor,
    # 2026-09-22: "por como está hablando… queda mejor")
    pz = K.get("pauses")
    vp = C.voice_pauses(d, html) if pz else None
    long_pauses = [(s0, s1) for s0, s1 in (vp or {}).get("pauses") or []
                   if pz and s1 - s0 >= float(pz.get("min", 0.40))]
    connectors = CONNECTORS | set(K.get("connectors_extra") or [])
    comma_closes = bool(K.get("connector_comma_closes"))
    dangling, forgiven, comma_ok = [], [], []
    # the last card too: a sentence a beat cuts off ("Having your" before CLB ep3 S1's beat 4, the 3
    # said as the beat enters) hangs on screen the same — it was the one card never looked at
    for i, g in enumerate(caps):
        last = g["words"][-1].lower().strip(",;:—–-")
        if last in connectors:
            if comma_closes and g["words"][-1].rstrip().endswith(CLAUSE_CLOSE):
                comma_ok.append('#%d …"%s"' % (i, " ".join(g["words"][-3:])))
                continue            # "what's going on," — the comma closed the clause
            if i + 1 < len(caps):
                nxt = caps[i + 1]["start"]
                if any(s0 >= g["start"] and s0 - 0.05 <= nxt <= s1 + 0.15 for s0, s1 in long_pauses):
                    forgiven.append('#%d …"%s"' % (i, " ".join(g["words"][-3:])))
                    continue
            dangling.append('#%d …"%s"%s' % (i, " ".join(g["words"][-3:]),
                                              T(" (la última tarjeta: lo que sigue no tiene tarjeta)",
                                                " (the last card: what follows has no card)") if i + 1 == len(caps) else ""))
    if dangling:
        # rules first, with flexibility (the editor, 2026-10-03: "lo mejor es que una caption no termine con
        # un conector, pero si llega a pasar, pues listo"): one connector left hanging among many good
        # cards does not hurt the video — a warning; two or more is the grouping failing — a fail
        (res.warn if len(dangling) == 1 else res.fail)(
                 "caption-dangling",
                 T("%d línea(s) terminan en conector — pasa a abrir la siguiente", "%d line(s) end on a connector — move it to open the next one") % len(dangling)
                 + (T(" (un caso aislado: se acepta si moverlo rompe la frase)", " (a single case: accepted when moving it breaks the phrase)") if len(dangling) == 1 else ""),
                 " · ".join(dangling[:8]))
    if forgiven:
        res.note(T("%d conector(es) al final de tarjeta se quedan: los sigue una pausa medida — "
                 "lo dicho después abre la tarjeta siguiente (%s)",
                   "%d connector(s) at the end of a card stay: a measured pause follows them — "
                 "what is said after it opens the next card (%s)") % (len(forgiven), " · ".join(forgiven[:6])))
    if comma_ok:
        res.note(T("%d conector(es) con coma al final de tarjeta se quedan: la coma cerró la cláusula "
                 "(captions.connector_comma_closes) (%s)",
                   "%d connector(s) with a comma at the end of a card stay: the comma closed the clause "
                 "(captions.connector_comma_closes) (%s)") % (len(comma_ok), " · ".join(comma_ok[:6])))

    # 7 — client vocabulary, captions and animation text alike
    for rx, fix in BAD_SPELLINGS:
        hits = rx.findall(html)
        if hits:
            res.fail("vocabulary",
                     T("%d uso(s) de una grafía prohibida → %s", "%d use(s) of a forbidden spelling → %s") % (len(hits), fix),
                     " · ".join(sorted(set(h if isinstance(h, str) else h[0] for h in hits))[:6]))

    # 8 — every said word is on a card, or a declared rule took it out (the editor, 2026-10-03, CLC ep1
    # S3: "it seems some words are MISSING"). Measured against what the clip's voice says
    # (word_timing: each stretch between pauses heard alone), not against transcript.json —
    # which misses words ("who") and, timing them wrong, counts a word said before a beat as
    # under it ("you need", 0.3 s before beat 2)
    TCFG = dict(K.get("timing") or {})
    wt = None
    if not TCFG.get("off"):
        wt = WT.measure(d, html)
        if wt["status"] == "none":
            wt = None
    words = C.read_transcript(d)
    if wt is not None:
        _said_check(res, d, caps, wt, TCFG, beats, words)
    elif words:
        spoken = [_norm(w["t"]) for w in words
                  if not (w["s"] is not None and under_beat(w["s"]))]
        spoken = [w for w in spoken if w]
        shown = []
        for g in caps:
            shown.extend(_norm(w) for w in g["words"])
        shown = [w for w in shown if w]
        missing = _missing(spoken, shown)
        missing, fillers = _split_fillers(missing)
        if fillers:
            res.note(T("%d muletilla(s) fuera del display a propósito: %s", "%d filler(s) left out of the display on purpose: %s")
                     % (len(fillers), " · ".join(fillers[:12])))
        if missing:
            res.fail("caption-missing-word",
                     T("%d palabra(s) del transcript no aparecen en ningún caption (contra transcript.json: "
                     "la voz no se pudo medir)",
                       "%d transcript word(s) do not appear in any caption (checked against transcript.json: "
                     "the voice could not be measured)") % len(missing),
                     " · ".join(missing[:12]))
        res.note(T("transcript: %d palabras · captions: %d — sin medir sobre la voz", "transcript: %d words · captions: %d — not measured on the voice") % (len(spoken), len(shown)))
    else:
        res.warn("no-transcript", T("sin transcript.json — no pude verificar palabras faltantes", "no transcript.json — could not check for missing words"))

    # 9 — the last line never outlives the video
    last = caps[-1]
    if r["duration"] and last["end"] > r["duration"] + 0.02:
        res.fail("caption-overrun",
                 T("el último caption termina en %.2fs, el video dura %.2fs", "the last caption ends at %.2fs, the video lasts %.2fs")
                 % (last["end"], r["duration"]))
    elif sp_end != r["duration"] and last["end"] > sp_end + 0.02:
        # the outro card (opaque, above the captions) hides it, but the card is
        # still on the timeline: it ends where the speech does
        res.warn("caption-into-outro",
                 T("el último caption termina en %.2fs y el outro empieza en %.2fs", "the last caption ends at %.2fs and the outro starts at %.2fs")
                 % (last["end"], sp_end),
                 T("cerrar la última tarjeta donde empieza el outro", "close the last card where the outro starts"))
    elif sp_end and (
            _uncovered(last["end"], sp_end, beats) if K.get("early_end_ignores_beats")
            else sp_end - last["end"]) > 2.05:
        res.warn("caption-early-end",
                 T("quedan %.2fs de %s después del último caption", "%.2fs of %s left after the last caption")
                 % (sp_end - last["end"], T("habla", "speech") if sp_end != r["duration"] else "video"))

    # 10 — no caption survives a change of shot (cuts.txt + scene detection)
    ci = C.cut_info(d, html)
    cuts = ci["cuts"]
    if ci["listed_bad"]:
        res.warn("cuts-list-unreadable",
                 T("%d línea(s) de cuts.txt no son un tiempo — no las leí", "%d line(s) of cuts.txt are not a time — skipped") % ci["listed_bad"],
                 T("una línea por corte, en segundos (podcast-beat-plan, paso 2b)", "one line per cut, in seconds (podcast-beat-plan, step 2b)"))
    if ci["require_list"] and ci["listed"] is None:
        res.warn("cuts-not-listed",
                 T("sin cuts.txt: la detección automática no ve los cortes de este cliente, "
                 "así que no verifiqué que ninguna tarjeta cruce un corte",
                   "no cuts.txt: automatic detection does not see this client's cuts, "
                 "so I did not check whether any card crosses a cut"),
                 T("%s — generá cuts.txt desde el corte (podcast-beat-plan, paso 2b)", "%s — generate cuts.txt from the edit (podcast-beat-plan, step 2b)") % ci["summary"])
    if cuts is None:
        res.warn("cut-detect-skipped",
                 T("no pude leer el video ni hay cuts.txt — no verifiqué los cambios de plano", "could not read the video and there is no cuts.txt — I did not check the shot changes"))
    else:
        crossing = []
        for c in cuts:
            if any(b["visible_start"] - 0.01 <= c <= b["visible_end"] + 0.01 for b in beats):
                continue          # the cut happens under a full-screen graphic
            for i, g in enumerate(caps):
                if g["start"] < c - CUT_TOL and g["end"] > c + CUT_TOL:
                    crossing.append((c, i, g))
        across, allowed = [], []
        if crossing:
            # a card may cross a jump cut of the SAME shot when splitting it there would leave a
            # single dangling word or a flash (the editor, 2026-10-03) — never a camera or speaker change.
            # Same shot is measured on the picture; the card is split the way the grouping script does.
            kinds = C.cut_kinds(d, html, sorted(set(c for c, _, _ in crossing)), ci)
            # word-level times for the split of a card at a cut: the words measured on the voice — the
            # times the grouping script splits by. transcript.json's drift put CLB ep3 S2's "your" after
            # the 44.37 cut and failed a card the script had let cross with reason (heard on each side
            # alone, 2026-10-03); without a measurement, the transcript
            if wt is not None and wt.get("words"):
                flat = _measured_word_times(caps, wt["words"])
            else:
                flat = _caption_word_times(caps, C.read_transcript(d, tokens=True) or words) if words else None
            by_voice = bool(K.get("cut_word_by_voice"))
            flash_under = float((K.get("cross_cut") or {}).get("flash_under") or MIN_DUR_FAIL)
            vpc = vp if vp is not None else (C.voice_pauses(d, html) if by_voice else None)
            pause_runs = [tuple(p) for p in (vpc or {}).get("pauses") or []]
            cards = {}
            for c, i, g in crossing:
                cards.setdefault(i, []).append(c)
            for i, cs in sorted(cards.items()):
                g = caps[i]
                same = []
                for c in sorted(cs):
                    old = T('#%d "%s" cruza el corte de %.2fs (%.2fs sobre el plano nuevo)', '#%d "%s" crosses the cut at %.2fs (%.2fs over the new shot)') % (i, g["text"], c, g["end"] - c)
                    kind = kinds.get(c) if kinds else None
                    if kind is None:
                        across.append(old + T(" — no pude medir si es el mismo plano (sin video o sin ffmpeg: run_gates.py --doctor)", " — could not measure whether it is the same shot (no video or no ffmpeg: run_gates.py --doctor)"))
                    elif not kind["same"]:
                        across.append(old + " — " + kind["why"])
                    else:
                        same.append((c, old, kind))
                if not same:
                    continue
                sp = [(c, _cut_split(i, flat, c, pause_runs, connectors, by_voice) if flat else None) for c, _, _ in same]
                spans = []
                for (c, old, kind), (_, parts) in zip(same, sp):
                    if parts is None:
                        across.append(old + T(" — mismo plano, pero no pude ubicar sus palabras en el transcript", " — same shot, but I could not place its words in the transcript"))
                    elif not parts[0] or not parts[1]:
                        # every word is on one side: the card only lingers (or opens early) around the cut
                        across.append(old + T(" — mismo plano (%s), pero todas sus palabras están %s del corte: "
                                      "la tarjeta %s en el corte",
                                              " — same shot (%s), but all its words are %s the cut: "
                                      "the card %s at the cut") % (
                                          kind["ev"], T("antes", "before") if not parts[1] else T("después", "after"),
                                          T("cierra", "closes") if not parts[1] else T("abre", "opens")))
                    else:
                        spans.append((len(parts[0]), c))
                if not spans:
                    continue
                ws = [w for ci_, w, _ in flat if ci_ == i]
                judged = crossing_reasons(ws, spans, g["start"], g["end"], connectors, flash_under, comma_closes)
                for j in judged:
                    c = j["cut"]
                    kind = next(kd for cc, _, kd in same if abs(cc - c) < 1e-9)
                    if j["reasons"]:
                        allowed.append(T('#%d "%s" cruza el corte de %.2fs: %s (%s)', '#%d "%s" crosses the cut at %.2fs: %s (%s)')
                                       % (i, g["text"], c, T(" y ", " and ").join(j["reasons"]), kind["ev"]))
                    else:
                        across.append(T('#%d "%s" cruza el corte de %.2fs (%.2fs sobre el plano nuevo) — corte de salto '
                                      'del mismo plano (%s), pero partirla ahí deja «%s» (%.2f s) y «%s» (%.2f s), que '
                                      'están bien: la tarjeta cierra en el corte',
                                        '#%d "%s" crosses the cut at %.2fs (%.2fs over the new shot) — a jump cut '
                                      'within the same shot (%s), but splitting it there leaves “%s” (%.2f s) and “%s” (%.2f s), which '
                                      'are fine: the card closes at the cut')
                                      % (i, g["text"], c, g["end"] - c, kind["ev"], " ".join(j["before"]),
                                         j["dur_before"], " ".join(j["after"]), j["dur_after"]))
                # two cuts in the same gap between two words split the card the same way, and
                # crossing_reasons judges them once: the other one gets that verdict, said aloud
                by_k = {j["k"]: j for j in judged}
                for k_, c in spans:
                    j = by_k.get(k_)
                    if j is None or abs(j["cut"] - c) < 1e-9:
                        continue
                    line = (T('#%d "%s" cruza también el corte de %.2fs, en el mismo hueco entre palabras que el de %.2fs', '#%d "%s" also crosses the cut at %.2fs, in the same gap between words as the one at %.2fs')
                            % (i, g["text"], c, j["cut"]))
                    if j["reasons"]:
                        allowed.append(line + ": " + T(" y ", " and ").join(j["reasons"]))
                    else:
                        across.append(line + T(", y partirla ahí estaba bien: la tarjeta cierra en el primero", ", and splitting it there was fine: the card closes at the first one"))
        if across:
            res.fail("caption-across-cut",
                     T("%d caption(s) siguen en pantalla después de un cambio de plano", "%d caption(s) stay on screen after a shot change")
                     % len(across),
                     " · ".join(across[:6]))
        if allowed:
            res.note(T("%d tarjeta(s) cruzan un corte de salto del mismo plano, como deja la regla (el editor, 2026-10-03: "
                     "solo si partirlas dejaba una palabra colgando o un parpadeo; mismo plano = %s): %s",
                       "%d card(s) cross a jump cut within the same shot, as the rule allows (the editor, 2026-10-03: "
                     "only if splitting them would leave a dangling word or a flash; same shot = %s): %s")
                     % (len(allowed), C.shot_limits_text(C.PROFILE["captions"]["cross_cut"]),
                        " | ".join(allowed[:6])))
        res.note(T("%d corte(s) de cámara verificados (%s)", "%d camera cut(s) checked (%s)") % (len(cuts), ci["summary"]))

    # 11 — a sentence starts with a capital
    lower = []
    for i in range(len(caps) - 1):
        a, b = caps[i], caps[i + 1]
        if not a["words"][-1].endswith(SENTENCE_END):
            continue
        if gap_is_a_beat(a["end"], b["start"]):
            continue              # the sentence started behind the graphic
        first = b["words"][0].lstrip('"\u201c\u2018\'')
        if first[:1].isalpha() and first[:1].islower():
            lower.append('#%d "%s" → #%d "%s"' % (i, a["text"], i + 1, b["text"]))
    if lower:
        res.fail("caption-lowercase-start",
                 T("%d oración(es) arrancan en minúscula después de un punto", "%d sentence(s) start in lowercase after a period") % len(lower),
                 " · ".join(lower[:6]))

    # 11b — a period the transcript has and the caption lost
    if words:
        dropped = _lost_punctuation(words, caps)
        if dropped:
            res.warn("caption-lost-period",
                     T("%d palabra(s) cierran oración en el transcript y no en el caption", "%d word(s) close a sentence in the transcript but not in the caption")
                     % len(dropped),
                     " · ".join(dropped[:8]))

    # 11c — nothing waits on screen (the editor, CLB ep3, 2026-10-01, for every video):
    # what is said after a pause opens the next card, and a card after a pause
    # opens where the voice comes back — measured on the clip's own audio
    early_by_pause = set()
    if pz:
        early_by_pause = _pause_check(res, vp, caps, beats, cuts, r["duration"], pz) or set()

    # 11d — every card opens with its voice (the editor, 2026-10-03, CLC ep1 S3: "some words appear
    # AFTER they are said"): the card's first word measured on the voice, against when the
    # card shows
    if TCFG.get("off"):
        res.note(T("tiempo de las tarjetas contra la voz: apagado en el perfil (captions.timing.off)", "card timing against the voice: turned off in the profile (captions.timing.off)"))
    elif wt is None:
        res.warn("timing-not-measured",
                 T("no pude medir la voz del clip — no verifiqué que cada tarjeta aparezca cuando se dice "
                 "su primera palabra",
                   "could not measure the clip's voice — I did not check that each card appears when "
                 "its first word is said"), T("ffmpeg y el audio del clip (run_gates.py --doctor)", "ffmpeg and the clip's audio (run_gates.py --doctor)"))
    else:
        _timing_check(res, caps, beats, cuts or [], wt, TCFG, early_by_pause)

    # 12 — one physical line, measured with the real font
    if fast:
        res.warn("width-not-measured",
                 T("medición de ancho salteada (--fast) — no es un PASS de una sola línea", "width measurement skipped (--fast) — this is not a single-line PASS"))
    else:
        measured = _measure_lines(d)
        if measured is None:
            res.warn("width-not-measured",
                     T("no pude medir el ancho en el navegador (playwright/chrome) — "
                     "una sola línea queda sin verificar",
                       "could not measure the width in the browser (playwright/chrome) — "
                     "the single line is left unchecked"))
        else:
            two = [g for g in measured if g["lines"] > 1]
            if two:
                res.fail("caption-two-lines",
                         T("%d tarjeta(s) ocupan más de una línea física", "%d card(s) take up more than one physical line") % len(two),
                         " · ".join(T('#%d (%d líneas) "%s"', '#%d (%d lines) "%s"') % (g["i"], g["lines"], g["text"])
                                    for g in two[:6]))
            over = [g for g in measured
                    if g["lines"] == 1 and g.get("limit")
                    and g["width"] > g["limit"] + 1]
            if over:
                res.fail("caption-overflow",
                         T("%d tarjeta(s) se pasan del ancho disponible", "%d card(s) go past the available width") % len(over),
                         " · ".join('#%d %d/%dpx "%s"'
                                    % (g["i"], g["width"], g["limit"], g["text"])
                                    for g in over[:6]))
            near = [g for g in measured
                    if g["lines"] == 1 and g.get("limit")
                    and 0 <= g["limit"] - g["width"] < NEAR_LIMIT]
            if near:
                res.warn("caption-near-limit",
                         T("%d tarjeta(s) a menos de %dpx del límite de ancho", "%d card(s) within %dpx of the width limit")
                         % (len(near), NEAR_LIMIT),
                         " · ".join('#%d %d/%dpx "%s"'
                                    % (g["i"], g["width"], g["limit"], g["text"])
                                    for g in near[:6]))
            res.note(T("%d tarjeta(s) medidas con la fuente cargada", "%d card(s) measured with the font loaded") % len(measured))

    return res.emit()


# ── A declared entrance ──────────────────────────────────────────────────────
#
# The shared rule is a hard cut (`tl.set` in and out). A brand that animates its
# cards declares how in `gates.json` → captions.entrance, once, and this checks
# the project's own tween calls against it — duration, ease and offset of each
# side — instead of calling every animated card a fade. CLE's captions fade in
# 0.25 s (expo.out, from y −14) and out 0.18 s (power3.in, to y +10), read off the
# approved CLE ep2 sources (the editor, 2026-10-03).

ENTRANCE_TOL = 0.006      # seconds, and px for the offsets: GSAP durations are written to 2–3 decimals


def _alpha(txt):
    m = re.search(r"(?<![\w.])(?:autoAlpha|opacity)\s*:\s*(-?\d*\.?\d+)", txt or "")
    return float(m.group(1)) if m else None


def _num_key(txt, key):
    m = re.search(r"(?<![\w.])%s\s*:\s*(-?\d*\.?\d+)" % key, txt or "")
    return float(m.group(1)) if m else None


def _str_key(txt, key):
    m = re.search(r"(?<![\w.])%s\s*:\s*([\"'`])([^\"'`]*)\1" % key, txt or "")
    return m.group(2) if m else None


def _caption_tweens(html):
    """The tween calls of the blocks that bind caption cards to the timeline, once each."""
    consts = C.const_table(C._CONST_RE, C.script_text(html))
    seen, out = set(), []
    for body in C.caption_bind_blocks(html):
        for m in re.finditer(r"tl\.(fromTo|from|to|set)\(", body):
            args = C.js_call_args(body, m.end() - 1)
            kind = m.group(1)
            if kind == "fromTo" and len(args) >= 3:
                frm, to = args[1], args[2]
            elif kind in ("to", "set") and len(args) >= 2:
                frm, to = "", args[1]
            elif kind == "from" and len(args) >= 2:
                frm, to = args[1], ""
            else:
                continue
            key = (kind, re.sub(r"\s+", "", frm + "|" + to))
            if key in seen:
                continue
            seen.add(key)
            vars_ = args[1] if kind == "from" else to        # the object that carries duration and ease
            dm = re.search(r"(?<![\w.])(?:duration|dur)\s*:\s*([^,}]+)", vars_)
            if kind == "from":
                # from {autoAlpha: 0} to the card's own value: an entrance (from 1: a way out)
                a = _alpha(frm)
                alpha_to = None if a is None else (1.0 if a <= 0.01 else (0.0 if a >= 0.99 else None))
            else:
                alpha_to = _alpha(to)
            out.append({"kind": kind, "alpha_to": alpha_to,
                        "dur": C._expr(dm.group(1).strip(), consts) if dm else None,
                        "ease": _str_key(vars_, "ease"),
                        "y_from": _num_key(frm, "y"), "y_to": None if kind == "from" else _num_key(to, "y")})
    return out


def _fmt_tween(d):
    bits = []
    dur = d.get("dur", d.get("duration"))        # a found call says dur, the declaration says duration
    if dur is not None:
        bits.append("%.2f s" % float(dur))
    if d.get("ease"):
        bits.append(d["ease"])
    for k, label in (("y_from", T("y desde %+g", "y from %+g")), ("y_to", T("y hasta %+g", "y to %+g"))):
        if d.get(k) is not None:
            bits.append(label % d[k])
    return " ".join(bits) or T("sin valores", "no values")


def _differs(found, want, y_key):
    """What in one tween call is not what the brand declared."""
    out = []
    if want.get("duration") is not None and (found["dur"] is None or abs(found["dur"] - float(want["duration"])) > ENTRANCE_TOL):
        out.append(T("duración %s (declarado %.2f s)", "duration %s (declared %.2f s)")
                   % ("%.2f s" % found["dur"] if found["dur"] is not None else T("no legible", "unreadable"), float(want["duration"])))
    if want.get("ease") and found["ease"] != want["ease"]:
        out.append(T("ease %s (declarado %s)", "ease %s (declared %s)") % (found["ease"] or T("ninguno", "none"), want["ease"]))
    if want.get(y_key) is not None:
        got = found.get(y_key)
        if got is None or abs(got - float(want[y_key])) > 0.5:
            out.append(T("%s %s (declarado %+g)", "%s %s (declared %+g)") % (y_key.replace("_", " "),
                                                  "%+g" % got if got is not None else T("ninguno", "none"), float(want[y_key])))
    return out


def _check_entrance(res, html, decl, fmt, animated):
    """FAIL when the caption tweens are not what the brand declared; a note when they are."""
    calls = _caption_tweens(html)
    ins = [c for c in calls if c["kind"] in ("fromTo", "from") and (c["alpha_to"] or 0) >= 0.99]
    outs = [c for c in calls if c["kind"] == "to" and c["alpha_to"] is not None and c["alpha_to"] <= 0.01]
    others = [c for c in calls if c["kind"] != "set" and c not in ins and c not in outs]
    din, dout = decl.get("in"), decl.get("out")
    missing, differs = [], []
    for name, found, want, y_key in ((T("entrada", "entrance"), ins, din, "y_from"), (T("salida", "exit"), outs, dout, "y_to")):
        if not want:
            if found:
                differs.append(T("%s: el proyecto anima (%s) y la marca declara corte", "%s: the project animates (%s) and the brand declares a cut") % (name, _fmt_tween(found[0])))
        elif not found:
            missing.append(T("%s: la marca declara %s y el proyecto corta", "%s: the brand declares %s and the project cuts") % (name, _fmt_tween(want)))
        else:
            for c in found:
                bad = _differs(c, want, y_key)
                if bad:
                    differs.append("%s: %s" % (name, " · ".join(bad)))
    if others:
        differs.append(T("tween que la marca no declara: ", "tween the brand does not declare: ") + " · ".join(_fmt_tween(c) for c in others[:3]))
    mode = decl.get("mode", "fade")
    if missing:
        res.fail("caption-entrance-missing",
                 T("la marca declara captions con %s y %s no los lleva", "the brand declares captions with %s and %s does not have them") % (mode, T("este proyecto", "this project")),
                 " · ".join(missing) + T(" — captions.entrance en gates.json", " — captions.entrance in gates.json"))
    if differs:
        res.fail("caption-entrance-mismatch",
                 T("los captions no se mueven como declara la marca (%s)", "the captions do not move the way the brand declares (%s)") % mode,
                 " · ".join(sorted(set(differs))[:4]) + T(" — captions.entrance en gates.json", " — captions.entrance in gates.json"))
    if not missing and not differs:
        total = (float(din["duration"]) if din else 0.0) + (float(dout["duration"]) if dout else 0.0)
        res.note(T("entrada declarada por la marca (%s, %d llamada(s) del proyecto coinciden): %s%s%s — "
                 "una tarjeta queda a plena opacidad su duración − %.2f s",
                   "entrance declared by the brand (%s, %d call(s) in the project match): %s%s%s — "
                 "a card stays at full opacity for its duration − %.2f s")
                 % (mode, len(ins) + len(outs),
                    (T("entra ", "enters ") + _fmt_tween(din)) if din else T("entra por corte", "enters on a cut"),
                    "; ",
                    (T("sale ", "exits ") + _fmt_tween(dout)) if dout else T("sale por corte", "exits on a cut"), total))


def _pause_check(res, vp, caps, beats, cuts, duration, pz):
    """caption-holds-pause (FAIL) and caption-opens-early (WARN), with how much was measured.

    Calibrated on CLB ep3 (2026-10-03): the delivered Snippets 1 and 2 pass; the
    two cards the editor sent back in round 1 fail when rebuilt on a copy — one
    holds the 0.64 s pause after "1," (Snippet 2), and the other opened on
    Whisper's time inside the 0.44 s pause before it (Snippet 1).
    """
    if vp is None:
        res.warn("pauses-not-measured",
                 T("no pude leer el audio del clip — no verifiqué que ninguna tarjeta espere en pantalla", "could not read the clip's audio — I did not check whether any card waits on screen"))
        return set()
    min_p = float(pz.get("min", 0.40))
    tol = float(pz.get("early_tol", 0.10))
    end = duration or vp["duration"]
    pauses = [(s, e) for s, e in vp["pauses"] if e - s >= min_p and s > 0.05 and e < end - 0.05]

    def under(t):
        return any(b["visible_start"] - 0.05 <= t <= b["visible_end"] + 0.05 for b in beats)

    cuts = cuts or []
    holds, early, early_idx = [], [], set()
    for i, g in enumerate(caps):
        a, b = g["start"], g["end"]
        for s0, s1 in pauses:
            if under(s0) or under(s1) or any(s0 - 0.05 <= c <= s1 + 0.05 for c in cuts):
                continue          # hidden by a beat, or the cut is the boundary there
            if a + 0.05 < s0 and s1 < b - 0.15:
                holds.append(T('#%d "%s" (%.2f–%.2f) sigue en pantalla durante la pausa %.2f–%.2f (%.2fs)', '#%d "%s" (%.2f–%.2f) stays on screen during the pause %.2f–%.2f (%.2fs)')
                             % (i, g["text"], a, b, s0, s1, s1 - s0))
        if i == 0 or under(a) or any(abs(a - c) <= 0.05 for c in cuts):
            continue              # a card opens on a cut on purpose
        for s0, s1 in pauses:
            if s0 < a < s1 - tol:
                early.append(T('#%d "%s" abre en %.2f y la voz vuelve en %.2f (%.2fs antes)', '#%d "%s" opens at %.2f and the voice comes back at %.2f (%.2fs early)')
                             % (i, g["text"], a, s1, s1 - a))
                early_idx.add(i)
    if holds:
        res.fail("caption-holds-pause",
                 T("%d tarjeta(s) muestran palabras que se dicen después de una pausa — "
                 "lo dicho tras la pausa abre la tarjeta siguiente",
                   "%d card(s) show words said after a pause — "
                 "what is said after the pause opens the next card") % len(holds),
                 " · ".join(holds[:6]))
    if early:
        res.warn("caption-opens-early",
                 T("%d tarjeta(s) abren antes de que vuelva la voz después de una pausa — "
                 "abren donde termina el silencio",
                   "%d card(s) open before the voice comes back after a pause — "
                 "they open where the silence ends") % len(early),
                 " · ".join(early[:6]))
    res.note(T("%d pausa(s) de %.2fs o más en la voz (%s, RMS 10 ms bajo %.1f dB · p10 %.1f · p50 %.1f)", "%d pause(s) of %.2fs or more in the voice (%s, RMS 10 ms below %.1f dB · p10 %.1f · p50 %.1f)")
             % (len(pauses), min_p, vp["source"], vp["floor"], vp["p10"], vp["p50"]))
    for why in vp.get("skipped") or []:
        res.note(T("voz limpia salteada: ", "clean voice skipped: ") + why)
    if vp.get("limited"):
        # a bed under the voice fills the pauses: this can only find fewer than there are, so a
        # clean result here is not a PASS of the pause rule (P4, CLA ep4 S1: 1 pause with the bed, 4 clean)
        res.warn("pauses-limited",
                 T("el audio medido (%s) lleva una cama o un ruido constante bajo la voz: su décimo más "
                 "silencioso queda a %.1f dB del umbral de pausa (con cama, 0.5–2.2 dB en CLA ep4; con la voz "
                 "limpia, 6 dB o más) — puede haber pausas que no vi",
                   "the measured audio (%s) has a bed or a constant noise under the voice: its quietest "
                 "tenth is %.1f dB from the pause threshold (with a bed, 0.5–2.2 dB in CLA ep4; with the clean "
                 "voice, 6 dB or more) — there may be pauses I did not see") % (vp["source"], vp.get("margin", 0.0)),
                 T("poné la voz limpia de este corte en la carpeta del proyecto como voice.wav "
                 "(ffmpeg -i <export> -vn voice.wav, o la de AUDIO RENDERS) y se mide sobre ella",
                   "put the clean voice of this cut in the project folder as voice.wav "
                 "(ffmpeg -i <export> -vn voice.wav, or the one from AUDIO RENDERS) and it gets measured on that"))
    return early_idx


# ── The cards against the voice ─────────────────────────────────────────────
#
# The editor, 2026-10-03, on the CLC ep1 S3 rebuild next to their approved version: "some words
# appear AFTER they are said, and it seems some words are MISSING". The rebuild was timed by
# transcript.json (whisper.cpp small.en, no DTW), whose times had drifted up to 1.5 s, and no
# gate measured a card against the voice. Both checks below read word_timing.py: the words
# the clip's own voice says, each stretch between pauses heard alone, every word anchored to
# where the voice is. Against large-v3 run the same way it agrees within 0.16 s on 91-93 % of the
# words of five clips (median +0.06 s); where they disagreed by more, hearing the audio cut in two
# sided with it in every case checked.

TIMING_DEFAULTS = {"late_warn": 0.20, "late_fail": 0.35, "early_warn": 0.35, "early_fail": 0.70,
                   "missing_p": 0.70, "doubtful_p": 0.35}
FIRST_CARD_OPEN = 0.5      # the video opens on its first card when the voice starts this soon


def _tcfg(t):
    out = dict(TIMING_DEFAULTS)
    out.update({k: v for k, v in (t or {}).items() if v is not None})
    return out


def _caption_pairs(caps, words):
    """Caption words paired with the measured words: (flat, pairs) — flat = [(card, word)],
    pairs = {flat index: [measured index, ...]} (WT.pair: "3,500" = "3" ",500", "work day" =
    "workday"), a pair allowed only within 4 s of its card."""
    flat = [(gi, w) for gi, g in enumerate(caps) for w in g["words"]]
    a = [WT.normalize(w) for _, w in flat]
    b = [WT.normalize(w["t"]) for w in words]

    def ok(i, j):
        g = caps[flat[i][0]]
        return g["start"] - 4.0 <= words[j]["s"] <= g["end"] + 4.0

    def dist(i, j):
        g = caps[flat[i][0]]
        t = words[j]["s"]
        return max(0.0, g["start"] - 0.5 - t, t - g["end"] - 0.5)
    pr = WT.fill_gaps(a, b, WT.pair(a, b, ok, dist))
    # a gap pair is kept only within the same 4 s
    return flat, {i: js for i, js in pr.items() if all(ok(i, j) for j in js)}


def _said_check(res, d, caps, wt, tcfg, beats, transcript):
    """caption-missing-word (FAIL), caption-doubtful-word / caption-unheard-word (WARN)."""
    cfg = _tcfg(tcfg)
    words = wt["words"]
    flat, pr = _caption_pairs(caps, words)
    used = {j for js in pr.values() for j in js}
    b = [WT.normalize(w["t"]) for w in words]
    energy_only = wt["status"] != "measured"
    jd = WT.judge_unpaired(words, b, used,
                           WT.hidden_by([(x["visible_start"], x["visible_end"]) for x in beats]),
                           WT.declared_removals(os.path.join(d, "captions-text.txt")),
                           sure=float(cfg["missing_p"]), floor=float(cfg["doubtful_p"]),
                           sure_p=(lambda j: 1.0) if energy_only else None,
                           confirmed=set() if energy_only else WT.confirmed_by(words, transcript))

    def item(j):
        return T("«%s» %.2fs (p %.2f)", "“%s” %.2fs (p %.2f)") % (words[j]["t"], words[j]["s"], 1.0 if energy_only else words[j].get("p", 1.0))
    missing = [item(j) for j in jd["sure"]]
    doubtful = [item(j) for j in jd["doubtful"]]
    ruled = {}
    for j, why in jd["ruled"]:
        ruled.setdefault(why, []).append("%s@%.2f" % (words[j]["t"], words[j]["s"]))
    hidden = len(jd["hidden"])
    if missing:
        res.fail("caption-missing-word",
                 T("%d palabra(s) que se dicen no están en ninguna tarjeta y ninguna regla las sacó "
                 "(muletilla, tartamudeo, bajo un beat, ~~a mano~~)",
                   "%d spoken word(s) are not on any card and no rule took them out "
                 "(filler, stutter, under a beat, ~~by hand~~)") % len(missing),
                 " · ".join(missing[:12]) + T(" — lo que se dice manda: ponela en el texto (group_captions.py "
                 "la agrega sola), o marcala ~~así~~ si sale a propósito",
                                              " — what is said wins: put it in the text (group_captions.py "
                 "adds it by itself), or mark it ~~like this~~ if it is left out on purpose"))
    if doubtful:
        res.warn("caption-doubtful-word",
                 T("%d palabra(s) que la pasada sobre la voz oye sin seguridad (p %.2f–%.2f) y no están en "
                 "las tarjetas — second_pass.py decide",
                   "%d word(s) the voice pass hears with low confidence (p %.2f–%.2f) and that are not on "
                 "the cards — second_pass.py decides") % (len(doubtful), float(cfg["doubtful_p"]),
                                                          float(cfg["missing_p"])),
                 " · ".join(doubtful[:10]))
    # caption words the voice pass does not hear
    tb = [WT.normalize(w["t"]) for w in transcript or []]
    flat_n = [WT.normalize(w) for _, w in flat]
    in_tw = set(WT.pair(flat_n, tb).keys()) if tb else set()
    unheard = [T("«%s» (#%d%s)", "“%s” (#%d%s)") % (w, gi, T(", transcript.json la tiene", ", transcript.json has it") if k in in_tw else T(", nadie la oye", ", nobody hears it"))
               for k, (gi, w) in enumerate(flat) if k not in pr and flat_n[k]]
    if unheard and not energy_only:
        res.warn("caption-unheard-word",
                 T("%d palabra(s) de las tarjetas que la pasada sobre la voz no oye — second_pass.py decide; "
                 "si no se dice, sale",
                   "%d card word(s) the voice pass does not hear — second_pass.py decides; "
                 "if it is not said, it goes") % len(unheard), " · ".join(unheard[:10]))
    res.note(T("palabras contra la voz (%s): %d dichas · %d en tarjetas · bajo un beat %d · fuera por regla %s", "words against the voice (%s): %d spoken · %d on cards · under a beat %d · out by rule %s")
             % (T("medidas", "measured") if not energy_only else T("del transcript, sin re-escuchar", "from the transcript, without re-listening"), len(words),
                sum(1 for k in range(len(flat)) if k in pr), hidden,
                ("%d (%s)" % (sum(len(v) for v in ruled.values()),
                              "; ".join("%s: %s" % (k, ", ".join(v[:6])) for k, v in ruled.items())))
                if ruled else "0"))


def _timing_check(res, caps, beats, cuts, wt, tcfg, early_by_pause):
    """caption-late / caption-late-near and caption-early / caption-early-near, with the numbers."""
    cfg = _tcfg(tcfg)
    words = wt["words"]
    flat, pr = _caption_pairs(caps, words)
    by_card = {}
    for k, (gi, _) in enumerate(flat):
        by_card.setdefault(gi, []).append(k)
    late_f, late_w, early_f, early_w, by_rule, rows, unmeasured, hidden = [], [], [], [], [], [], [], 0
    for gi, g in enumerate(caps):
        vis = g["start"]
        for bt in beats:
            if bt["visible_start"] - 0.02 <= vis < bt["visible_end"] - 0.02:
                vis = max(vis, bt["visible_end"])
        if vis >= g["end"] - 0.02:
            hidden += 1                   # under a full-frame beat for all its life: nobody sees it
            continue
        ks = by_card.get(gi) or []
        k0 = next((k for k in ks if k in pr), None)
        if k0 is None:
            unmeasured.append("#%d" % gi)
            continue
        w = words[pr[k0][0]]
        on = w["s"]
        # the earliest the card may open: the cut it waits for (the editor cuts inside the first
        # word after a cut), the beat it waits for
        floor = on
        for c in cuts:
            if on < c <= max(w["e"], on + 0.05) + 0.05 and c - on <= 0.6:
                floor = max(floor, c)
        for bt in beats:
            if bt["visible_start"] - 0.05 <= on <= bt["visible_end"] + 0.05:
                floor = max(floor, bt["visible_end"])
        late, early = vis - floor, on - vis
        first = "" if k0 == ks[0] else T(" (medida desde «%s»: la primera no se oye)", " (measured from “%s”: the first word cannot be heard)") % flat[k0][1]
        rows.append(late)
        desc = T('#%d "%s" aparece en %.2f y «%s» se dice en %.2f', '#%d "%s" appears at %.2f and “%s” is said at %.2f') % (gi, g["text"], vis, flat[k0][1], on)
        if floor > on + 0.005:
            desc += T(" (puede abrir desde %.2f)", " (may open from %.2f)") % floor
        if late > float(cfg["late_fail"]):
            late_f.append((late, desc + T(" — %.2fs TARDE%s", " — %.2fs LATE%s") % (late, first)))
        elif late > float(cfg["late_warn"]):
            late_w.append((late, desc + T(" — %.2fs tarde%s", " — %.2fs late%s") % (late, first)))
        if early > float(cfg["early_warn"]):
            on_cut = any(abs(vis - c) <= 0.03 for c in cuts)
            opening = gi == 0 and on <= FIRST_CARD_OPEN
            if on_cut or opening:
                by_rule.append('#%d %s' % (gi, T("abre en el corte", "opens on the cut") if on_cut else T("abre el video", "opens the video")))
            elif gi in early_by_pause:
                pass                      # caption-opens-early already says it, with the pause
            elif early > float(cfg["early_fail"]):
                early_f.append((early, desc + T(" — %.2fs ANTES", " — %.2fs EARLY") % early))
            else:
                early_w.append((early, desc + T(" — %.2fs antes", " — %.2fs early") % early))
    bed = bool(wt.get("limited"))
    if late_f and bed:
        # a bed under the measured voice hides the pauses the measurement anchors to: report, do not block
        res.warn("caption-late-bed",
                 T("%d tarjeta(s) aparecen más de %.2fs después de su primera palabra — medido sobre un audio con cama "
                 "debajo, sin pausas donde anclar: poné la voz limpia (voice.wav) y vuelve a ser FAIL",
                   "%d card(s) appear more than %.2fs after their first word — measured on audio with a bed "
                 "underneath, with no pauses to anchor to: add the clean voice (voice.wav) and it becomes a FAIL again")
                 % (len(late_f), float(cfg["late_fail"])),
                 " · ".join(x for _, x in sorted(late_f, reverse=True)[:6]))
        late_f = []
    if early_f and bed:
        res.warn("caption-early-bed",
                 T("%d tarjeta(s) aparecen más de %.2fs antes de su primera palabra — medido con cama debajo", "%d card(s) appear more than %.2fs before their first word — measured with a bed underneath")
                 % (len(early_f), float(cfg["early_fail"])),
                 " · ".join(x for _, x in sorted(early_f, reverse=True)[:6]))
        early_f = []
    if late_f:
        res.fail("caption-late",
                 T("%d tarjeta(s) aparecen más de %.2fs después de que se dice su primera palabra", "%d card(s) appear more than %.2fs after their first word is said")
                 % (len(late_f), float(cfg["late_fail"])),
                 " · ".join(x for _, x in sorted(late_f, reverse=True)[:6])
                 + T(" — re-agrupá con group_captions.py (abre cada tarjeta en la voz medida)", " — regroup with group_captions.py (it opens each card on the measured voice)"))
    if late_w:
        res.warn("caption-late-near",
                 T("%d tarjeta(s) entre %.2f y %.2fs tarde", "%d card(s) between %.2f and %.2fs late") % (len(late_w), float(cfg["late_warn"]),
                                                            float(cfg["late_fail"])),
                 " · ".join(x for _, x in sorted(late_w, reverse=True)[:6]))
    if early_f:
        res.fail("caption-early",
                 T("%d tarjeta(s) aparecen más de %.2fs antes de que se diga su primera palabra", "%d card(s) appear more than %.2fs before their first word is said")
                 % (len(early_f), float(cfg["early_fail"])),
                 " · ".join(x for _, x in sorted(early_f, reverse=True)[:6]))
    if early_w:
        res.warn("caption-early-near",
                 T("%d tarjeta(s) entre %.2f y %.2fs antes de su voz", "%d card(s) between %.2f and %.2fs ahead of their voice") % (len(early_w), float(cfg["early_warn"]),
                                                                      float(cfg["early_fail"])),
                 " · ".join(x for _, x in sorted(early_w, reverse=True)[:6]))
    if not rows:
        res.warn("timing-not-measured",
                 T("ninguna tarjeta visible se pudo medir contra la voz (%d bajo un beat, %d sin par)", "no visible card could be measured against the voice (%d under a beat, %d with no match)")
                 % (hidden, len(unmeasured)))
    else:
        rs = sorted(rows)
        res.note(T("%d tarjeta(s) medidas contra la voz (%s): tarde mediana %+.0f ms · p90 %+.0f · máx %+.0f · "
                 "más de %.2fs: %d · ocultas bajo un beat %d%s%s",
                   "%d card(s) measured against the voice (%s): median lateness %+.0f ms · p90 %+.0f · max %+.0f · "
                 "over %.2fs: %d · hidden under a beat %d%s%s")
                 % (len(rs), WT.describe(wt), 1000 * rs[len(rs) // 2], 1000 * rs[int(0.9 * (len(rs) - 1))],
                    1000 * rs[-1], float(cfg["late_warn"]), sum(1 for x in rs if x > float(cfg["late_warn"])),
                    hidden, (T(" · sin par en la voz: ", " · no match in the voice: ") + " ".join(unmeasured[:8])) if unmeasured else "",
                    (T(" · antes por regla: ", " · early by rule: ") + ", ".join(by_rule[:6])) if by_rule else ""))
    if wt["status"] != "measured":
        res.warn("timing-unverified",
                 T("los tiempos de las palabras son los de transcript.json anclados a la voz, sin re-escuchar "
                 "(%s): dentro de una frase pueden ir corridos hasta 1.5 s",
                   "the word times are the ones from transcript.json anchored to the voice, without re-listening "
                 "(%s): within a phrase they can be off by up to 1.5 s") % wt.get("why"),
                 T("instalá faster-whisper (run_gates.py --doctor) y volvé a correr el gate", "install faster-whisper (run_gates.py --doctor) and run the gate again"))


# ── A card that crosses a jump cut of the same shot ─────────────────────────
#
# The editor, 2026-10-03 ("sí, para todos"): a card MAY cross a jump cut of the SAME shot
# when splitting it at the cut would leave a single dangling word or a flash (a card
# under the FAIL floor, 0.5 s); it NEVER crosses a camera change or a change of
# speaker. Same shot = measured on the picture (`_common.cut_kinds`). The grouping
# script and this gate share the two functions below, so what the script lets cross
# is what the gate lets stand: CLB ep3 S2 "And ask" (0.26 s between a full stop and a
# jump cut, EDL cuts 54.13 / 54.83) and CLE ep2 S2 "without | …" (the cut falls between
# a connector and the rest of its phrase).

PUNCT_END = (",", ";", ":", ".", "!", "?", "—", "–", "-", "…")


APOSTROPHES = {"\u2019": "'", "\u2018": "'", "\u02bc": "'", "\u2032": "'", "`": "'"}


def apostrophes(w):
    """A typographic apostrophe is the typewriter one: a cleaned text from Google Docs writes
    "don’t" where Whisper writes "don't", and the two have to be one word."""
    for a, b in APOSTROPHES.items():
        w = w.replace(a, b)
    return w


def bare(w):
    return re.sub(r"[^a-z0-9']", "", apostrophes(w).lower())


def dangling_word(w, connectors, comma_closes=False):
    """A card ending on this word hangs on a connector (the profile's list; with
    `connector_comma_closes`, "what's going on," has closed its clause)."""
    if comma_closes and w.rstrip().endswith(CLAUSE_CLOSE):
        return False
    return w.lower().strip(",;:—–-") in connectors


def word_after_cut(s0, e0, w, prev_w, c, pauses, connectors, by_voice):
    """True when a word (audio s0-e0, text w, the word before it prev_w) sits on the far side of a cut at c.

    Whisper stretches the last word before a cut over it, and the editor cuts inside
    the first word after one (49 of 51 cuts in one workshop recording): a word that
    straddles the cut goes with the side its punctuation says, else with the side
    most of it is on, the first word after the cut winning ties; a short word right
    before the cut ("so" 0.08 s before it) is the first word after it. For a profile
    that asks (`captions.cut_word_by_voice`) a word whose voice ended before the cut —
    the audio is silent from inside the word up to the cut, and the word has 0.08 s of
    voice before that silence — is the last one before it ("like, really": CLE ep2 S2,
    voice 8.19-8.54, silence to the cut at 8.84). That is a switch and not the rule
    because the same silence also precedes a word that starts after it (CLB ep3 S2,
    "Everyone": silence 59.23-59.51, cut 59.39, Whisper starts the word at 59.20), and
    there the word must stay after the cut. The grouping script and the gate both
    decide this here."""
    if s0 >= c - 0.005:
        return True
    if e0 <= c + 0.005:
        return c - s0 < 0.15 and not w.endswith(PUNCT_END)
    if by_voice and any(s0 + 0.08 <= p0 < c - 0.02 and p1 >= c - 0.03 for p0, p1 in pauses):
        return False
    if w.endswith(PUNCT_END):
        return False
    if prev_w is not None and prev_w.endswith(PUNCT_END):
        return True
    # ambiguous: keep it before the cut sooner when the word before it is a connector
    # that would otherwise hang ("what the | next two weeks")
    share = 0.35 if prev_w is not None and bare(prev_w) in connectors else 0.6
    return (c - s0) < share * (e0 - s0)


def split_reasons(before, after, dur_before, dur_after, connectors, min_fail, comma_closes=False):
    """Why a card may not be split at a jump cut — [] means splitting is fine, so the card must not cross.

    `before` / `after`: the card's words on each side of the cut; the durations are
    the two cards the split would make (the first from the card's start to the cut,
    the second from the cut to the card's end). The reasons are the two the editor named:
    a single dangling word, and a flash — a card under `min_fail` seconds."""
    out = []
    if not before or not after:
        return out
    for side, ws, dur in ((T("antes", "before"), before, dur_before), (T("después", "after"), after, dur_after)):
        if dur < min_fail:
            out.append(T("«%s» duraría %.2f s (un parpadeo, menos de %.1f s)", "“%s” would last %.2f s (a flash, under %.1f s)") % (" ".join(ws), dur, min_fail))
    last = before[-1]
    if dangling_word(last, connectors, comma_closes) and not last.endswith(SENTENCE_END):
        if len(before) == 1:
            out.append(T("«%s» quedaría sola y colgando", "“%s” would be left alone and dangling") % last)
        else:
            out.append(T("«%s» quedaría colgando al final de «%s»", "“%s” would be left dangling at the end of “%s”") % (last, " ".join(before[-3:])))
    elif len(before) == 1 and not last.endswith(SENTENCE_END):
        out.append(T("«%s» quedaría sola", "“%s” would be left alone") % last)
    if len(after) == 1 and not after[0].endswith(SENTENCE_END):
        out.append(T("«%s» quedaría sola", "“%s” would be left alone") % after[0])
    return out


def crossing_reasons(ws, spans, start, end, connectors, flash, comma_closes=False):
    """The reasons, cut by cut, for a card that spans jump cuts of the same shot.

    `ws` are the card's words, `start`/`end` its times and `spans` = [(k, c)]: a cut at
    time c falls after the first k words (0 < k < len(ws)). With one cut that is
    `split_reasons` on the two halves. With several, each cut is judged on the two
    segments next to it, the card being split at every cut it spans — so a word left
    alone between two cuts (a flash on both sides) justifies crossing both. Returns
    [{"cut": c, "k": k, "reasons": [...], "before": [...], "after": [...], "dur_before",
    "dur_after"}] in time order; the card may cross a cut only where its reasons are
    not empty."""
    cuts, seen = [], set()
    for k, c in sorted(spans, key=lambda x: x[1]):
        if k not in seen and 0 < k < len(ws):
            seen.add(k)
            cuts.append((k, c))
    ks = [0] + [k for k, _ in cuts] + [len(ws)]
    ts = [start] + [c for _, c in cuts] + [end]
    out = []
    for m, (k, c) in enumerate(cuts):
        before, after = ws[ks[m]:k], ws[k:ks[m + 2]]
        db, da = c - ts[m], ts[m + 2] - c
        out.append({"cut": c, "k": k, "before": before, "after": after, "dur_before": db, "dur_after": da,
                    "reasons": split_reasons(before, after, db, da, connectors, flash, comma_closes)})
    return out


def _caption_word_times(caps, words):
    """[(card index, text, (start, end) or None)] for every caption word in order, with the
    Whisper time of its counterpart in the transcript; a word with none gets the time of its neighbours."""
    flat = [(i, w) for i, g in enumerate(caps) for w in g["words"]]
    spoken = [_norm(w["t"]) for w in words]
    shown = [_norm(w) for _, w in flat]
    times = [None] * len(flat)
    sm = difflib.SequenceMatcher(a=spoken, b=shown, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("equal", "replace") and (i2 - i1) == (j2 - j1):
            for k in range(i2 - i1):
                s, e = words[i1 + k]["s"], words[i1 + k]["e"]
                if s is not None and e is not None:
                    times[j1 + k] = (s, e)
    for j, t in enumerate(times):
        if t is None:
            prev = next((times[x] for x in range(j - 1, -1, -1) if times[x]), None)
            nxt = next((times[x] for x in range(j + 1, len(times)) if times[x]), None)
            if prev and nxt:
                times[j] = (prev[1], nxt[0])
            elif prev:
                times[j] = (prev[1], prev[1] + 0.2)
            elif nxt:
                times[j] = (nxt[0] - 0.2, nxt[0])
    return [(i, w, times[j]) for j, (i, w) in enumerate(flat)]


def _measured_word_times(caps, words):
    """[(card index, text, (start, end) or None)] like _caption_word_times, from the words measured
    on the voice (word_timing.py), paired the way the timing gate pairs them (_caption_pairs); a
    caption word the voice pass did not hear gets the time between its neighbours."""
    flat, pr = _caption_pairs(caps, words)
    times = [(words[pr[k][0]]["s"], words[pr[k][-1]]["e"]) if k in pr else None for k in range(len(flat))]
    for j, t in enumerate(times):
        if t is None:
            prev = next((times[x] for x in range(j - 1, -1, -1) if times[x]), None)
            nxt = next((times[x] for x in range(j + 1, len(times)) if times[x]), None)
            if prev and nxt:
                times[j] = (prev[1], max(prev[1], nxt[0]))
            elif prev:
                times[j] = (prev[1], prev[1] + 0.2)
            elif nxt:
                times[j] = (nxt[0] - 0.2, nxt[0])
    return [(i, w, times[j]) for j, (i, w) in enumerate(flat)]


def _cut_split(card_index, flat, c, pauses, connectors, by_voice):
    """The card's words on each side of the cut at c: (before, after), or None when they have no times."""
    ws = [(w, t) for i, w, t in flat if i == card_index]
    if not ws or any(t is None for _, t in ws):
        return None
    before, after = [], []
    for k, (w, (s0, e0)) in enumerate(ws):
        prev_w = ws[k - 1][0] if k else None
        (after if word_after_cut(s0, e0, w, prev_w, c, pauses, connectors, by_voice) else before).append(w)
    return before, after


def _uncovered(a, b, beats):
    """Seconds of [a, b] that no full-frame beat covers — captions are hidden under one."""
    spans = sorted((max(a, x["visible_start"]), min(b, x["visible_end"])) for x in beats)
    covered, cur = 0.0, a
    for s0, e0 in spans:
        if e0 <= cur:
            continue
        s0 = max(s0, cur)
        if s0 < e0:
            covered += e0 - s0
            cur = e0
    return (b - a) - covered


def _measure_lines(d):
    """Caption line counts from a real browser, or None when it cannot run."""
    js = os.path.join(os.path.dirname(os.path.abspath(__file__)), "measure_captions.js")
    out = C.P.run_node(js, [d], timeout=300)
    if out is None or out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])["groups"]
    except (ValueError, KeyError, IndexError):
        return None


def _lost_punctuation(words, caps):
    """Transcript words that close a sentence where the caption does not.

    The case that hides from a card-by-card read: the caption is spelled right
    and the period simply never made it across, so the next card looks like a
    legitimate lowercase continuation.
    """
    spoken = [_norm(w["t"]) for w in words]
    raw = [w["t"] for w in words]
    shown, shown_raw = [], []
    for g in caps:
        for w in g["words"]:
            shown.append(_norm(w))
            shown_raw.append(w)
    out = []
    sm = difflib.SequenceMatcher(a=spoken, b=shown, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            continue
        for k in range(i2 - i1):
            t, c = raw[i1 + k], shown_raw[j1 + k]
            if t.endswith(SENTENCE_END) and not c.endswith(SENTENCE_END) \
                    and not c.endswith((",", ";", ":", "—", "-")):
                out.append('"%s" → "%s"' % (t, c))
    return out


_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
    "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90", "hundred": "100",
}


NUMERALS_EQUAL = False     # set per client profile in main()


def _norm(w):
    """Comparison form of a word. With `numerals_equal` in the client profile, a
    number in figures and the same number spelled out are one word — "9 times out
    of 10" is how the line is captioned when the transcript says "nine times out
    of ten", and it is not a lost word."""
    t = re.sub(r"[^a-z0-9']", "", apostrophes(w).lower())
    return _NUMBER_WORDS.get(t, t) if NUMERALS_EQUAL else t


def _split_fillers(missing):
    """Separate the fillers dropped on purpose from words genuinely lost.

    Phrases first ("you know" is two words that only count as a filler
    together), then single interjections. What is left is a real miss.
    """
    rest = list(missing)
    found = []
    for phrase in FILLER_PHRASES:
        n = len(phrase)
        i = 0
        while i <= len(rest) - n:
            if tuple(rest[i:i + n]) == phrase:
                found.append(" ".join(phrase))
                del rest[i:i + n]
            else:
                i += 1
    keep = []
    for w in rest:
        if w in FILLER_WORDS:
            found.append(w)
        else:
            keep.append(w)
    return keep, found


def _missing(spoken, shown):
    """Spoken words with no counterpart in the captions.

    Aligned with difflib rather than a greedy scan, so one real miss does not
    cascade into dozens of phantom ones. A block whose letters survive intact
    across a word boundary — "on line" captioned as "online" — is not a miss.
    """
    out = []
    sm = difflib.SequenceMatcher(a=spoken, b=shown, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        gone = spoken[i1:i2]
        if not gone:
            continue
        if "".join(gone) == "".join(shown[j1:j2]):
            continue
        out.extend(gone)
    return out


if __name__ == "__main__":
    sys.exit(main())
