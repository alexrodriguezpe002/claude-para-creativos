#!/usr/bin/env python3
"""Word times measured on the clip's own voice — what captions are timed by and checked against.

    python3 word_timing.py <project-dir> [--model small.en] [--force] [--words]

WHY. transcript.json is whisper.cpp small.en without DTW (`hyperframes transcribe`): its
words are right, its times are not. On CLC ep1 Snippet 3 (2026-10-03) the transcript of
the clean voice and the one of the same cut with its music bed disagree by up to 1.5 s
on the same word, and the rebuild timed by the first one showed cards up to 1.86 s
after the voice (the editor: "some words appear AFTER they are said"). The same drift had
put "you need" (said at 34.8 s) under a beat that starts at 35.12 s, so it was left out.
Nothing measured either thing.

HOW. The voice — a clean voice file in the project folder, else the a-roll, else the
<audio> (_common._audio_sources) — is read as 10 ms RMS levels under the clip's own
floor (the floor _common.voice_pauses uses). Runs of voice are split at every silence of
MIN_GAP; every silence of CHUNK_PAUSE or more is a boundary, and each stretch between
two such silences is heard ALONE by faster-whisper with word timestamps (no prompt, no
conditioning on the text before). A word can only land in the stretch where it is said:
the long-run drift cannot happen, and which side of a pause a short word is on is decided
by what each side says, not by a timestamp — CLB ep3 S1, "any questions. | And the
questions": large-v3 over the whole clip put "and" before the 0.44 s pause, heard on
each side alone both large-v3 and small.en put it after, where the editor had placed the card.
Then every word is anchored to the voice:
  * a word that spans a silence goes after it (Whisper glues a word that follows a pause
    to the end of the word before it: 40 % of the starts after a pause come early) unless
    its text closes a phrase (, . ? ! ; :) — then it ends where the silence starts. With
    every stretch heard alone this only happens to the transcript's words (energy-only);
  * a start inside a silence moves to where the voice comes back (<= ONSET_REACH);
  * the first word of a run starts where the run starts (<= RUN_SNAP);
  * an end never runs into the silence after the run that holds the word.

Without faster-whisper (or with no readable voice) the transcript's own words are
anchored the same way — status "energy-only": a start in a pause and a word across a
pause are fixed, the drift inside a stretch is not, and the caption gate says so
(timing-unverified). Cached in .gates-cache/word-timing.json per voice file (size,
mtime), model and version.

Also here, shared by the grouping script and the gate: `normalize`, `pair` (text
alignment that pairs "3,500" with "3" ",500", "100-man" with "hundred man", "workday"
with "work day" and "needed" with "need"), `heard_rule` (why a heard word may be left
out: filler, stutter, restart), `declared_removals` (`~~word~~` in the cleaned text: said
and left out by hand), `syllables`, `place` (a time for a word the voice pass did not hear,
inside the voice between its neighbours).
"""

import json
import os
import re
import sys
import time

import _common as C
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)

VERSION = 2
FRAME = 160            # 10 ms at 16 kHz, the frame voice_pauses uses
STEP = FRAME / 16000.0
MIN_GAP = 0.15         # a silence this long splits two runs of voice (stops inside a word are shorter)
MIN_RUN = 0.06         # a run of voice shorter than this is a click, not a word
MICRO_GAP = 0.06       # a silence this long inside a stretch may sit between two words (see _hear)
CHUNK_PAUSE = 0.15     # every silence this long is a boundary between the stretches heard alone
CHUNK_MAX = 25.0       # a stretch longer than this is cut at its quietest frame (Whisper hears 30 s)
ONSET_REACH = 0.60     # a start inside a silence moves to the voice when it comes back this soon
RUN_SNAP = 0.35        # the first word of a run starts on the run when the ASR puts it this close
PAD = 0.10             # audio given around a stretch, never more than half the silence next to it
DEFAULT_MODEL = "small"     # multilingual small: closest to large-v3 of the fast ones (2026-10-03)
HALLUCINATIONS = {"thank you", "thanks for watching", "thank you for watching", "you", "bye",
                  "thank you very much", "subtitles by the amaraorg community"}
CLOSES = (",", ".", "?", "!", ";", ":", "—", "–", "…")

# ── text ─────────────────────────────────────────────────────────────────────

_NUM = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
        "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
        "thirteen": "13", "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
        "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40",
        "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
        "hundred": "100", "thousand": "1000"}
_APOS = {"’": "'", "‘": "'", "ʼ": "'", "′": "'", "`": "'"}


def normalize(w):
    """The comparison form of a word: lower case, typewriter apostrophe, letters, digits and
    apostrophes only, a number word as its figure ("three" = "3")."""
    for a, b in _APOS.items():
        w = w.replace(a, b)
    w = w.replace("%", " percent ")
    t = re.sub(r"[^a-z0-9']", "", w.lower()).strip("'")
    return _NUM.get(t, t)


def _near(x, y):
    """Two spellings of one spoken word ("need"/"needed", "workday"/"work-day")."""
    if x == y:
        return True
    if not x or not y:
        return False
    if min(len(x), len(y)) >= 4 and (x.startswith(y[:4]) and y.startswith(x[:4])):
        return True
    if abs(len(x) - len(y)) > 2 or min(len(x), len(y)) < 3:
        return False
    prev = list(range(len(y) + 1))
    for i, cx in enumerate(x, 1):
        cur = [i]
        for j, cy in enumerate(y, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (cx != cy)))
        prev = cur
    return prev[-1] <= (1 if len(x) < 7 else 2)


def pair(a, b, ok=None, dist=None):
    """Global alignment of two token lists (already `normalize`d). Returns {i: [j, ...]}: the
    b tokens each a token stands for. Exact pairs beat near ones, one token may stand for two
    whose letters it holds ("3500" = "3" "500", "100man" = "100" "man", "workday" = "work"
    "day") and two for one; a skipped token costs less than a wrong pair. `ok(i, j)` may
    forbid a pair (too far apart in time); `dist(i, j)` (seconds between them) breaks ties
    between two equal words — CLB ep3 S2's "one question," paired with the "one … question."
    said under the next beat, 3.5 s later, before it cost something."""
    n, m = len(a), len(b)
    NEG = -1e9
    sc = [[NEG] * (m + 1) for _ in range(n + 1)]
    bk = [[None] * (m + 1) for _ in range(n + 1)]
    sc[0][0] = 0.0
    a2 = [a[i] + a[i + 1] if i + 1 < n else None for i in range(n)]
    b2 = [b[j] + b[j + 1] if j + 1 < m else None for j in range(m)]
    near = {}
    for i in range(n + 1):
        row, nrow = sc[i], (sc[i + 1] if i < n else None)
        x = a[i] if i < n else None
        for j in range(m + 1):
            cur = row[j]
            if cur == NEG:
                continue
            # skips
            if i < n and cur - 0.5 > nrow[j]:
                nrow[j], bk[i + 1][j] = cur - 0.5, (i, j, "a")
            if j < m and cur - 0.5 > row[j + 1]:
                row[j + 1], bk[i][j + 1] = cur - 0.5, (i, j, "b")
            if i < n and j < m and (ok is None or ok(i, j)):
                y = b[j]
                if x == y:
                    sv = 3.0
                else:
                    k = (x, y)
                    if k not in near:
                        near[k] = _near(x, y)
                    sv = 2.0 if near[k] else -2.0
                if dist is not None and sv > 0:
                    sv -= 0.15 * min(4.0, dist(i, j))
                if cur + sv > nrow[j + 1]:
                    nrow[j + 1], bk[i + 1][j + 1] = cur + sv, (i, j, "=" if sv > 0 else "x")
                if x and b2[j] is not None and x == b2[j] and cur + 3.5 > nrow[j + 2]:
                    nrow[j + 2], bk[i + 1][j + 2] = cur + 3.5, (i, j, "1:2")
                if y and a2[i] is not None and y == a2[i] and cur + 3.5 > sc[i + 2][j + 1]:
                    sc[i + 2][j + 1], bk[i + 2][j + 1] = cur + 3.5, (i, j, "2:1")
    out = {}
    i, j = n, m
    while (i, j) != (0, 0):
        pi, pj, how = bk[i][j]
        if how == "=":
            out[pi] = [pj]
        elif how == "1:2":
            out[pi] = [pj, pj + 1]
        elif how == "2:1":
            out[pi] = [pj]
            out[pi + 1] = [pj]
        i, j = pi, pj
    return out


FILLERS = {"um", "uh", "uhh", "uhm", "erm", "ah", "eh", "hmm", "mm", "mhm"}
FILLER_PAIRS = {("you", "know"), ("i", "mean")}
_RESTART_FN = set("a an the and or but so of to in into on at for with from as that this it i we you they he she".split())


def heard_rule(j, norm_words):
    """Why a word the voice pass heard may be absent from the captions on purpose, or None.

    The shared rules (podcast-captions, "Text"): a filler (um, uh…, "you know" / "I mean"), a
    word said twice in a row — a stutter, or a content word repeated that the text wrote once
    ("Video companies companies") — and a restart of two or three words ("that are that are",
    "the thing that, the thing you kick", CLA ep4 S3): the first, abandoned start is the one left out."""
    b = norm_words
    w = b[j]
    if w in FILLERS:
        return T("muletilla", "filler")
    if (j + 1 < len(b) and (w, b[j + 1]) in FILLER_PAIRS) or (j > 0 and (b[j - 1], w) in FILLER_PAIRS):
        return T("muletilla (you know / I mean)", "filler (you know / I mean)")
    if (j > 0 and b[j - 1] == w) or (j + 1 < len(b) and b[j + 1] == w):
        return T("repetida (tartamudeo)", "repeated (stutter)")
    # a function word, another function word, the first again: "ease back into the, into work" (CLB ep2 S1)
    # — not "awareness and skills. And I" (CLA ep4 S1, a content word in between)
    # (either copy may be the one the caption kept, as with a word said twice in a row)
    for s0 in (j, j - 1, j - 2):
        if 0 <= s0 and s0 + 2 < len(b) and b[s0] == b[s0 + 2] and b[s0] in _RESTART_FN \
                and b[s0 + 1] in _RESTART_FN and s0 <= j <= s0 + 2:
            return T("arranque repetido (1 palabra)", "restart (1 word)")
    for k in (2, 3):
        for m in (0, 1):                      # "the thing that, the thing …": one word between the two starts
            for s0 in range(max(0, j - 2 * k - m + 1), j + 1):
                if s0 + 2 * k + m <= len(b) and b[s0:s0 + k] == b[s0 + k + m:s0 + 2 * k + m] \
                        and s0 <= j < s0 + k + m:
                    return T("arranque repetido (%d palabras)", "restart (%d words)") % k
    return None


def judge_unpaired(words, b, used, hidden, declared=None, sure=0.70, floor=0.35, sure_p=None, confirmed=None):
    """The heard words no text word stands for, judged the same way by the grouping script and
    the gate. Consecutive ones form a phrase ("this weekend", "as we get?"). A phrase is sure
    when every word in it is heard at p >= `sure`, or when the other pass (transcript.json)
    has the same words there too (`confirmed`: indexes of `words` it has) — one sure word
    inside a doubtful phrase is not a word ("as we get?" at 50.2 s in CLC ep1 S3: the three
    models hear three phrases), and a weak word the other pass also heard is ("you need 120").
    Returns {"sure": [j], "doubtful": [j], "ruled": [(j, why)], "hidden": [j]}; under `floor`
    a word is ignored (Whisper filling a breath). `hidden(s, e)` says a full-frame beat covers
    it; `declared` (normalized words, consumed in order) were left out by hand (~~ ~~);
    `sure_p(j)` overrides a word's p (the transcript's words have none)."""
    declared = list(declared or [])
    out = {"sure": [], "doubtful": [], "ruled": [], "hidden": []}
    cand = []
    for j, w in enumerate(words):
        if j in used or not b[j]:
            continue
        if hidden(w["s"], w["e"]):
            out["hidden"].append(j)
            continue
        why = heard_rule(j, b)
        if why is None and b[j] in declared:
            declared.remove(b[j])
            why = T("a mano (~~ ~~)", "by hand (~~ ~~)")
        if why:
            out["ruled"].append((j, why))
            continue
        cand.append(j)
    phrases = []
    for j in cand:
        if phrases and j == phrases[-1][-1] + 1:
            phrases[-1].append(j)
        else:
            phrases.append([j])
    confirmed = confirmed or set()
    for ph in phrases:
        ps = [sure_p(j) if sure_p else float(words[j].get("p", 1.0)) for j in ph]
        if min(ps) >= sure or (all(j in confirmed for j in ph) and min(ps) >= floor):
            out["sure"] += ph
        else:
            out["doubtful"] += [j for j, p in zip(ph, ps) if p >= floor]
    return out


def confirmed_by(words, other):
    """Indexes of `words` that the other pass (`other`, e.g. transcript.json's words) also has,
    paired by text in order and within 3 s of each other."""
    a = [normalize(w["t"]) for w in words]
    o = [normalize(w["t"]) for w in other or []]
    if not a or not o:
        return set()

    def ok(i, j):
        s = other[j].get("s")
        return s is None or abs(s - words[i]["s"]) <= 3.0
    return set(pair(a, o, ok).keys())


def hidden_by(beats):
    """The shared "under a full-frame beat" test for a word (s, e): it starts inside the beat
    and its middle is not in the beat's last 0.10 s — a word said as the beat leaves is shown.
    Beats back to back count as one window. `beats` = [(visible_start, visible_end)]."""
    covered = []
    for b0, b1 in sorted(beats):
        if covered and b0 - covered[-1][1] <= 0.15:
            covered[-1][1] = max(covered[-1][1], b1)
        else:
            covered.append([b0, b1])

    def hidden(s, e):
        return any(b0 - 0.05 <= s and (s + e) / 2.0 <= b1 - 0.10 for b0, b1 in covered)
    return hidden


def declared_removals(path):
    """Words the cleaned text marks as said and left out on purpose — `~~you know,~~` — in order."""
    if not path or not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    out = []
    for m in re.finditer(r"~~(.+?)~~", raw, re.S):
        out += [normalize(w) for w in m.group(1).split() if normalize(w)]
    return out


def fill_gaps(a, b, pr):
    """Between two paired words, the unpaired words on each side are the same stretch of speech
    heard differently ("phase" heard "face", "is" heard "it's", "this weekend" heard "as we get"):
    pair them in order — the text keeps its spelling, the voice gives the time. As many on each
    side: one to one; one word more on one side: the heard words are shared out in order. Words a
    shared rule leaves out (heard_rule) do not count on the heard side. Returns `pr` completed."""
    anchors = sorted((i, js[0], js[-1]) for i, js in pr.items())
    bounds = [(-1, -1, -1)] + anchors + [(len(a), len(b), len(b))]
    for (i0, _, j0), (i1, j1, _) in zip(bounds, bounds[1:]):
        ti = [i for i in range(i0 + 1, i1) if a[i]]
        hj = [j for j in range(j0 + 1, j1) if b[j] and not heard_rule(j, b)]
        if not ti or not hj or abs(len(ti) - len(hj)) > 1:
            continue
        if len(ti) == len(hj):
            for i, j in zip(ti, hj):
                pr[i] = [j]
        elif len(hj) > len(ti):                  # one heard word more: the last text word takes two
            for k, i in enumerate(ti):
                pr[i] = [hj[k]] if k < len(ti) - 1 else hj[k:]
        else:                                    # one text word more: two text words share a heard one
            for k, i in enumerate(ti):
                pr[i] = [hj[min(k, len(hj) - 1)]]
    return pr


_VOWELS = re.compile(r"[aeiouy]+")


def syllables(w):
    t = re.sub(r"[^a-z0-9']", "", w.lower())
    if not t:
        return 1
    if t.isdigit():
        return max(1, len(t))
    n = len(_VOWELS.findall(t))
    if len(t) > 3 and t.endswith("e") and not t.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(1, n)


# ── the voice ────────────────────────────────────────────────────────────────

def _levels(samples):
    import math
    import operator
    n = len(samples) // FRAME
    out = []
    for i in range(n):
        seg = samples[i * FRAME:(i + 1) * FRAME]
        r = math.sqrt(sum(map(operator.mul, seg, seg)) / float(FRAME)) / 32768.0
        out.append(20.0 * math.log10(r + 1e-9))
    return out


def _floor(levels):
    """The pause floor voice_pauses uses: halfway from the quiet tenth to the median of the
    spoken frames, never above 18 dB under the loud tenth."""
    spoken = sorted(x for x in levels if x > -70.0) or [-90.0]

    def pct(q):
        return spoken[int(round(q * (len(spoken) - 1)))]
    p10, p50, p90 = pct(0.10), pct(0.50), pct(0.90)
    return min(p10 + 0.5 * (p50 - p10), p90 - 18.0)


def voice_runs(levels, floor):
    """[(start, end)] of voice, split at every silence of MIN_GAP or more."""
    out, i, n = [], 0, len(levels)
    while i < n:
        if levels[i] <= floor:
            i += 1
            continue
        j = i
        while j < n and levels[j] > floor:
            j += 1
        out.append([i * STEP, j * STEP])
        i = j
    merged = []
    for r in out:
        if merged and r[0] - merged[-1][1] < MIN_GAP:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [(round(a, 3), round(b, 3)) for a, b in merged if b - a >= MIN_RUN]


def stretches(runs, levels=None):
    """Runs joined across silences shorter than CHUNK_PAUSE: [[run, ...], ...]."""
    out, cur = [], []
    for r in runs:
        if cur and (r[0] - cur[-1][1] >= CHUNK_PAUSE or r[1] - cur[0][0] > CHUNK_MAX):
            out.append(cur)
            cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return out


def anchor(words, runs):
    """Words [{'t','s','e',...}] in time order, anchored to the runs of voice (see the module doc)."""
    gaps = [(runs[k][1], runs[k + 1][0]) for k in range(len(runs) - 1)]
    out = [dict(w, how=w.get("how") or "asr") for w in words]
    for w in out:
        for g0, g1 in gaps:
            if w["s"] < g0 - 0.02 and w["e"] > g1 + 0.02:
                if w["t"].rstrip().endswith(CLOSES):
                    w["e"], w["how"] = g0, "span->before"
                else:
                    w["s"], w["how"] = g1, "span->after"
                break
    for w in out:
        if not any(r0 - 0.02 <= w["s"] < r1 for r0, r1 in runs):
            nxt = next((r0 for r0, r1 in runs if r0 > w["s"]), None)
            if nxt is not None and nxt - w["s"] <= ONSET_REACH:
                w["s"], w["how"] = nxt, "silence->voice"
    for r0, r1 in runs:
        mine = [w for w in out if r0 - 0.02 <= w["s"] < r1]
        if mine and mine[0]["s"] - r0 <= RUN_SNAP and mine[0]["how"] in ("asr", "split-heard"):
            mine[0]["s"], mine[0]["how"] = r0, "run-onset"
    for k, w in enumerate(out):
        hold = next(((r0, r1) for r0, r1 in runs if r0 - 0.02 <= w["s"] < r1 + 0.02), None)
        nxt = out[k + 1]["s"] if k + 1 < len(out) else 1e9
        if hold and w["e"] > hold[1] + 0.02 and nxt >= hold[1]:
            w["e"] = hold[1]
        if k and w["s"] < out[k - 1]["s"]:
            w["s"] = out[k - 1]["s"]                 # never before the word before it
        w["s"] = round(w["s"], 3)
        w["e"] = round(max(w["e"], w["s"] + 0.03), 3)
    return out


def place(times, runs):
    """Fill None entries of `times` ([(s, e)] or None, in order) inside the voice between their
    timed neighbours, by syllables (`times` items may carry a word in a third slot)."""
    out = list(times)
    n = len(out)
    q = 0
    while q < n:
        if out[q] is not None and out[q][0] is not None:
            q += 1
            continue
        j = q
        while j < n and (out[j] is None or out[j][0] is None):
            j += 1
        lo = out[q - 1][1] if q > 0 else (out[j][0] - 0.25 * (j - q) if j < n else 0.0)
        hi = out[j][0] if j < n else lo + 0.25 * (j - q)
        spans = [(max(lo, r0), min(hi, r1)) for r0, r1 in runs if min(hi, r1) - max(lo, r0) > 0.02]
        if not spans:
            # no voice between the neighbours: never in the silence — against the next word when the
            # gap is a pause ("rather than | an engine.", CLE ep2 S2: "an" fell 0.5 s early into it)
            if hi - lo > 0.3 and j < n:
                spans = [(hi - 0.05 * (j - q), hi)]
            else:
                spans = [(lo, max(hi, lo + 0.05 * (j - q)))]
        talk = sum(b - a for a, b in spans)
        words = [(out[x][2] if out[x] is not None and len(out[x]) > 2 else "") for x in range(q, j)]
        wts = [syllables(w) + 0.6 for w in words]
        pos = 0.0

        def at(p):
            for a, b in spans:
                if p <= b - a + 1e-9:
                    return a + p
                p -= b - a
            return spans[-1][1]
        for x, wgt in zip(range(q, j), wts):
            dd = talk * wgt / sum(wts)
            out[x] = (round(at(pos), 3), round(at(pos + dd), 3)) + ((words[x - q],) if words[x - q] else ())
            pos += dd
        q = j
    return out


# ── the measurement ─────────────────────────────────────────────────────────

def _source(d, html):
    """(path, samples, skipped) of the voice: the order of _common._audio_sources, skipping a
    voice file that is not of this cut (its length is not the speech's)."""
    comp = C.speech_end(html, C.root(html)["duration"])
    voice = C.clean_voice_file(d)
    skipped = []
    for cand in C._audio_sources(d, html):
        a = C._pcm16(cand)
        if a is None:
            if cand == voice:
                skipped.append(T("%s no se pudo leer (ffmpeg)", "%s could not be read (ffmpeg)") % os.path.basename(cand))
            continue
        if cand == voice and comp and abs(len(a) / 16000.0 - comp) > 1.0:
            skipped.append(T("%s dura %.2fs y el habla del video %.2fs: no es de este corte", "%s lasts %.2fs and the video's speech %.2fs: it is not from this cut")
                           % (os.path.basename(cand), len(a) / 16000.0, comp))
            continue
        return cand, a, skipped
    return None, None, skipped


def timing_cfg():
    return dict((C.PROFILE.get("captions") or {}).get("timing") or {})


def _model_name(model=None):
    return model or os.environ.get("CAPTIONS_TIMING_MODEL") or timing_cfg().get("model") or DEFAULT_MODEL


def _clips(groups, total):
    out = []
    for k, g in enumerate(groups):
        before = groups[k - 1][-1][1] if k else 0.0
        after = groups[k + 1][0][0] if k + 1 < len(groups) else total
        out.append((max(0.0, g[0][0] - min(PAD, (g[0][0] - before) / 2.0)),
                    min(total, g[-1][1] + min(PAD, (after - g[-1][1]) / 2.0))))
    return out


def _transcribe(m, x, clips, lang):
    """[(clip index, word, start, end, p)] for clips [(a, b)] of the float samples x, each heard
    alone — batched when the installed faster-whisper can (BatchedInferencePipeline, 1.1+)."""
    import numpy as np
    got = []
    try:
        from faster_whisper import BatchedInferencePipeline
        bp = BatchedInferencePipeline(model=m)
        segs, _ = bp.transcribe(x, language=lang, clip_timestamps=[{"start": a, "end": b} for a, b in clips],
                                batch_size=8, beam_size=5, word_timestamps=True, vad_filter=False,
                                condition_on_previous_text=False)
        for s in segs:
            for w in s.words or []:
                mid = (w.start + w.end) / 2.0
                k = next((i for i, (a, b) in enumerate(clips) if a - 0.05 <= mid <= b + 0.05), None)
                if k is None:
                    k = min(range(len(clips)), key=lambda i: abs((clips[i][0] + clips[i][1]) / 2.0 - mid))
                got.append((k, w.word.strip(), w.start, w.end, w.probability))
        return got
    except Exception:                         # an older faster-whisper, or the batch failed: one by one
        got = []
    for k, (a, b) in enumerate(clips):
        seg = x[int(a * 16000):int(b * 16000)]
        if len(seg) < 1600:
            seg = np.concatenate([seg, np.zeros(1600 - len(seg), dtype=np.float32)])
        segs, _ = m.transcribe(seg, language=lang, beam_size=5, word_timestamps=True,
                               condition_on_previous_text=False, vad_filter=False)
        got += [(k, w.word.strip(), a + w.start, a + w.end, w.probability) for s in segs for w in (s.words or [])]
    return got


def _per_clip(got, n):
    out = []
    for k in range(n):
        mine = [g for g in got if g[0] == k and g[1]]
        text = " ".join(normalize(t) for _, t, _, _, _ in mine).strip()
        if mine and text in HALLUCINATIONS and sum(p for _, _, _, _, p in mine) / len(mine) < 0.6:
            mine = []                             # Whisper's filler for a breath or a click
        out.append([{"t": t, "s": round(s, 3), "e": round(e, 3), "p": round(p, 3)} for _, t, s, e, p in mine])
    return out


def micro_gaps(levels, floor, a, b):
    """Silences of MICRO_GAP..MIN_GAP inside [a, b] — too short to split a run (a stop inside a
    word can be that long), long enough to sit between two words."""
    out, i, n = [], max(0, int(a / STEP)), min(len(levels), int(b / STEP))
    while i < n:
        if levels[i] > floor:
            i += 1
            continue
        j = i
        while j < n and levels[j] <= floor:
            j += 1
        if MICRO_GAP <= (j - i) * STEP < MIN_GAP:
            out.append((round(i * STEP, 3), round(j * STEP, 3)))
        i = j
    return out


def _hear(samples, groups, model_name, language, levels=None, floor=None):
    """faster-whisper on each stretch alone, then — where a word seems to run across a short
    silence inside a stretch (0.06-0.15 s, too short to be a stretch boundary) — the stretch is
    heard again in pieces cut at that silence, and the pieces are kept only when they hear the
    very same words (a cut inside a word would change them). CLC ep1 S3: "… | there's", 0.11 s
    apart, timed 0.5 s early inside one stretch. Returns (words, extra boundaries, error)."""
    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except ImportError as e:
        return None, [], T("faster-whisper no está instalado (%s)", "faster-whisper is not installed (%s)") % e
    try:
        m = WhisperModel(model_name, device="cpu", compute_type="int8")
    except Exception as e:                      # no model and no internet, a broken cache…
        return None, [], T("no pude cargar el modelo %s de faster-whisper (%s)", "could not load the faster-whisper %s model (%s)") % (model_name, e)
    x = np.asarray(samples, dtype=np.float32) / 32768.0
    total = len(x) / 16000.0
    lang = None if model_name.endswith(".en") else (language or "en")
    clips = _clips(groups, total)
    try:
        per = _per_clip(_transcribe(m, x, clips, lang), len(clips))
    except Exception as e:
        return None, [], T("faster-whisper falló (%s)", "faster-whisper failed (%s)") % e
    extra = []
    if levels is not None:
        subs, owner = [], []
        for k, ws in enumerate(per):
            a, b = clips[k]
            cuts = [g for g in micro_gaps(levels, floor, a, b)
                    if any(w["s"] < g[0] - 0.05 and w["e"] > g[1] + 0.05 for w in ws)]
            if not cuts:
                continue
            # the longest one only: a second cut tends to leave a sliver (a word's final s) that hears
            # as nothing, and the pieces stop matching
            cuts = [max(cuts, key=lambda g: g[1] - g[0])]
            edges = [a] + [(g0 + g1) / 2.0 for g0, g1 in cuts] + [b]
            for e0, e1 in zip(edges, edges[1:]):
                subs.append((e0, e1))
                owner.append((k, cuts))
        if subs:
            try:
                sub_words = _per_clip(_transcribe(m, x, subs, lang), len(subs))
            except Exception:
                sub_words = None
            if sub_words is not None:
                by_k = {}
                for q, (k, cuts) in enumerate(owner):
                    by_k.setdefault(k, (cuts, []))[1].append(sub_words[q])
                for k, (cuts, pieces) in by_k.items():
                    flat = [w for piece in pieces for w in piece]
                    same = "".join(normalize(w["t"]) for w in flat) == "".join(normalize(w["t"]) for w in per[k])
                    if same and flat:
                        per[k] = [dict(w, how="split-heard") for w in flat]
                        extra += cuts
    words = []
    for k, ws in enumerate(per):
        words += [dict(w, stretch=k) for w in ws]
    words.sort(key=lambda w: (w["stretch"], w["s"]))
    return words, extra, None


def transcript_words(d):
    """transcript.json's own words with whisper.cpp token times ([] without one)."""
    return [w for w in C.read_transcript(d, tokens=True) if w["s"] is not None and w["e"] is not None]


def measure(d, html=None, model=None, force=False):
    """The clip's words timed on its voice. Returns
    {"status": "measured" | "energy-only" | "none", "why", "source", "model", "words",
     "runs", "stretches", "floor", "limited", "skipped", "seconds", "drift"}.
    "words": [{"t", "s", "e", "p", "how"}] in time order."""
    if html is None:
        html = C.read_html(d)
    model_name = _model_name(model)
    language = timing_cfg().get("language") or "en"
    src, samples, skipped = _source(d, html)
    tw = transcript_words(d)
    if src is None:
        return {"status": "none", "why": T("no pude leer el audio del clip (ffmpeg, o sin video ni audio)", "could not read the clip's audio (ffmpeg, or no video and no audio)"),
                "words": [], "runs": [], "source": None, "model": None, "skipped": skipped, "drift": None}
    st = os.stat(src)
    tpath = os.path.join(d, "transcript.json")
    tkey = os.stat(tpath).st_mtime if os.path.isfile(tpath) else None
    key = {"v": VERSION, "source": os.path.basename(src), "size": st.st_size, "mtime": round(st.st_mtime, 3),
           "model": model_name, "chunk_pause": CHUNK_PAUSE, "min_gap": MIN_GAP, "transcript": tkey}
    cache = os.path.join(d, ".gates-cache", "word-timing.json")
    if not force and os.path.isfile(cache):
        try:
            with open(cache, encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("key") == key and data.get("status") == "measured":
                return data
            if data.get("key") == key and data.get("status") == "energy-only" and not _can_hear():
                return data
        except Exception:
            pass
    t0 = time.time()
    levels = _levels(samples)
    floor = _floor(levels)
    allq = sorted(levels) or [-90.0]
    limited = floor - allq[int(round(0.10 * (len(allq) - 1)))] < C.PAUSE_BED_MARGIN
    runs = voice_runs(levels, floor)
    groups = stretches(runs)
    heard, extra, err = (_hear(samples, groups, model_name, language, levels, floor) if runs
                         else (None, [], T("sin voz medible", "no measurable voice")))
    if heard is not None:
        aruns = runs
        for g0, g1 in sorted(extra):             # the short silences the pieces confirmed split their run
            nxt = []
            for r0, r1 in aruns:
                if r0 < g0 and g1 < r1:
                    nxt += [(r0, g0), (g1, r1)]
                else:
                    nxt.append((r0, r1))
            aruns = nxt
        words, status, why = anchor(heard, aruns), "measured", ""
    else:
        words, status, why = anchor([dict(w, p=1.0) for w in tw], runs), "energy-only", err
    data = {"key": key, "status": status, "why": why, "source": os.path.basename(src),
            "model": model_name if status == "measured" else None, "words": words,
            "runs": [list(r) for r in runs], "stretches": len(groups), "floor": round(floor, 1),
            "split_at": [list(g) for g in sorted(extra)] if heard is not None else [],
            "limited": limited, "skipped": skipped, "seconds": round(time.time() - t0, 1)}
    data["drift"] = drift(tw, words) if status == "measured" else None
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError:
        pass
    return data


def _can_hear():
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def drift(tw, words):
    """How far transcript.json's times are from the measured ones, on the words both have."""
    if not tw or not words:
        return None
    a = [normalize(w["t"]) for w in tw]
    b = [normalize(w["t"]) for w in words]
    pr = pair(a, b)
    d = sorted(((tw[i]["s"] - words[js[0]]["s"]), tw[i]["t"], tw[i]["s"], words[js[0]]["s"])
               for i, js in pr.items() if a[i] and len(js) == 1)
    if not d:
        return None
    vals = sorted(x[0] for x in d)
    worst = sorted(d, key=lambda x: -abs(x[0]))[:5]
    return {"n": len(vals), "median": round(vals[len(vals) // 2], 3),
            "p10": round(vals[int(0.1 * (len(vals) - 1))], 3), "p90": round(vals[int(0.9 * (len(vals) - 1))], 3),
            "max_abs": round(max(abs(v) for v in vals), 3),
            "over_025": sum(1 for v in vals if abs(v) > 0.25),
            "worst": [[w, round(ts, 2), round(ms, 2)] for _, w, ts, ms in worst]}


def describe(data):
    """One line about a measurement, for the reports."""
    if data["status"] == "none":
        return T("tiempos NO medidos: ", "times NOT measured: ") + data["why"]
    base = T("%d palabras en %d tramos de voz (%s, piso %.1f dB%s)", "%d words in %d stretches of voice (%s, floor %.1f dB%s)") % (
        len(data["words"]), data.get("stretches") or 0, data["source"], data.get("floor", 0.0),
        T(", con cama o ruido debajo", ", with a bed or noise underneath") if data.get("limited") else "")
    if data["status"] == "energy-only":
        return T("tiempos del transcript anclados a la voz, SIN re-escuchar (%s): %s", "transcript times anchored to the voice, WITHOUT re-listening (%s): %s") % (data["why"], base)
    dr = data.get("drift")
    extra = ""
    if dr:
        extra = T(" · transcript.json vs medido: mediana %+.2fs, %d palabra(s) a más de 0.25 s, máx %.2fs", " · transcript.json vs measured: median %+.2fs, %d word(s) off by more than 0.25 s, max %.2fs") % (
            dr["median"], dr["over_025"], dr["max_abs"])
    return T("medidos sobre la voz con faster-whisper %s, cada tramo entre pausas por separado: %s%s", "measured on the voice with faster-whisper %s, each stretch between pauses on its own: %s%s") % (
        data["model"], base, extra)


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project")
    ap.add_argument("--model")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--words", action="store_true", help="print every measured word")
    args = ap.parse_args()
    d = C.project_dir(["x", args.project])
    data = measure(d, model=args.model, force=args.force)
    print(describe(data))
    if data.get("drift"):
        print("peores: " + " · ".join("%s %.2f→%.2f" % tuple(w) for w in data["drift"]["worst"]))
    if args.words:
        for w in data["words"]:
            print("%7.2f %7.2f  p%.2f  %-16s %s" % (w["s"], w["e"], w.get("p", 1.0), w["t"], w.get("how", "")))
    return 0 if data["status"] == "measured" else 1


if __name__ == "__main__":
    sys.exit(main())
