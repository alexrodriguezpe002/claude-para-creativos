#!/usr/bin/env python3
"""Group a clip's words into caption cards — one process for every client.

    python3 group_captions.py <project-dir> --text <words.txt> [--write] [--teaser]
    python3 group_captions.py <project-dir> --dump-text > words.txt

Where each thing comes from — nothing here names a client:

* the WORDS: --text, the clip's part of the cleaned transcript (the brand's
  `references/captions.md` says which file). A speaker label opening a line
  ("[00:12] Jane Doe:" or "Jane Doe:") starts a new card and is
  dropped. A `||` between two words forces a card break there — no label
  needed (written apart, or glued to either word: it never reaches the
  screen). `*word*` marks the emphasis word where the brand has emphasis.
  `~~words~~` are said and left out on purpose (a restart, "Okay." alone):
  they never reach the screen and the gate counts them as declared.
  What is SAID decides which words appear: a word the voice pass hears with
  confidence (p >= captions.timing.add_p) that the text lacks is added, spelled as
  heard; a text word nobody hears is kept and flagged for the second pass. The
  text decides spelling and punctuation.
  --dump-text prints the clip's words (the voice pass's, else Whisper's) as plain
  text, to correct when the brand has no cleaned transcript.
* the TIMING: the words measured on the clip's own voice (video-quality-gates
  `word_timing.py`: each stretch between pauses heard alone, every word anchored
  to where the voice is) — never transcript.json's own times, which drift up to
  1.5 s (CLC ep1 S3, 2026-10-03). A text word the voice pass did not hear gets a
  time inside the voice between its neighbours. Without faster-whisper the
  transcript's words are anchored to the voice instead, and the report says so.
* the CUTS: cuts.txt plus scene detection at the client's threshold.
* the PAUSES: the clip's own audio (video-quality-gates `_common.voice_pauses`).
* the NUMBERS: the client's profile — `<client>-brand/references/gates.json`
  merged with what this computer learned (`learned.py`): words per card, the
  0.5 / 0.7 s floors, connectors, the pause minimum, the target length.
* the LOOK: the project's own caption CSS, measured in Chrome with its font
  loaded — the same measurement the caption gate makes.

Grouping is a dynamic programme over each stretch between hard boundaries — a
sentence end, a cut, a beat, a speaker turn, a pause of the profile's minimum
(0.40 s) — that keeps every card on one physical line and minimises cards
under 0.7 s, lines ending on a connector, one-word cards, a number split from
its word ("round | 2"), and the distance from the target length. Shorter pauses
are preferred places to break. A card opens where the voice comes back after a
pause and on the cut after a cut, and runs until the next one opens (or the
beat that covers it, or 2 s after its last word at the very end — never past
where a fixed outro card starts: the profile's `outro.id_re`).

Prints the CAPTIONS array and a report. --write replaces `const CAPTIONS = […];`
in index.html and keeps the old array in .captions-backup/. A first pass, not
the verdict: check_captions.py decides.
"""

import argparse
import datetime
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
try:  # the user's language (video-quality-gates/scripts/_lang.py, a sibling skill)
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                    "video-quality-gates", "scripts"))
    from _lang import T  # noqa: E402
except ImportError:  # pragma: no cover — the plugin always ships video-quality-gates
    def T(es, en):
        return en

HERE = os.path.dirname(os.path.abspath(__file__))
# skills sit side by side (~/.claude/skills/ on the owner's Mac, the plugin's skills/
# folder anywhere else); the gates are the sibling skill video-quality-gates
GATES = os.path.join(os.path.dirname(os.path.dirname(HERE)), "video-quality-gates", "scripts")
if not os.path.isdir(GATES):
    sys.exit(T("no encuentro la skill video-quality-gates junto a podcast-captions (%s) — "
             "las dos se instalan juntas",
               "cannot find the video-quality-gates skill next to podcast-captions (%s) — "
             "the two are installed together") % GATES)
sys.path.insert(0, GATES)
import _common as C          # noqa: E402
import _profile              # noqa: E402
import check_captions as K   # noqa: E402
import word_timing as WT     # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")   # Windows consoles default to cp1252
    except (AttributeError, ValueError):
        pass

HOLD_LAST = 2.0       # the last card holds 2 s when nothing follows — never past the video
PAUSE_PREFER = 0.15   # a measured pause this long is a preferred place to break
HOLD_BASE = 3.0       # … and a card that holds one inside costs this (the mirror of the -3 for breaking
HOLD_SCALE = 12.0     # there) plus up to this much more as the pause nears the hard split (0.40 s): the
                      # words after it wait on screen (the editor, 2026-10-01: nothing waits on screen). CLB ep3
                      # S1/S2 regrouped on the measured voice held "you bring | are one" (0.22 s),
                      # "answered, | wastes" (0.36 s) where the editor's approved arrays break (2026-10-03)
ONSET_MAX = 0.60      # a pause end is the onset only this close to Whisper's start
BEAT_SNAP = 0.15      # a card after a beat opens on the beat's exit when the word is this close
LATE_MAX = 0.18       # in continuous speech a card may close (and the next open) this much after
                      # the next card's first word, to keep a card off the 0.5 s floor — CLB ep3 S1
                      # shipped "At the end" 0.02–0.67 with "of" said at 0.45. It was 0.25 and only
                      # one card at a time until 2026-10-03; now a chain of short cards borrows from
                      # the one that closes the phrase, and no card opens more than 0.18 s after its
                      # word — under the gate's caption-late-near (captions.timing.late_warn, 0.20)
ADD_P = 0.70          # a word the voice pass hears this surely and the text lacks is added
                      # (captions.timing.add_p) — what is said decides which words appear
NEAR = 60             # px — the gate's caption-near-limit
CROSS_COST = 25       # a card spanning a same-shot jump cut: under a flash (45+) or a hanging
                      # connector (50), over a lone word (15) — see `cost_of`
PUNCT_END = (",", ";", ":", ".", "!", "?", "—", "–", "-", "…")
DOM_DEFAULT = {"layer": "#cap-layer", "group": "caption-group", "text": "cap-text", "word": "cap-word"}

FILLERS = set(K.FILLER_WORDS)
# a word repeated once, glued — "the the", "I I" — is a stutter when it is a
# function word; a content word said twice is emphasis and stays ("far, far
# more"). Two- and three-word repeats ("that are that are") are restarts.
FUNCTION_WORDS = set("""
a an the and or but nor so yet of to in on at by with from into onto for as than that this these those
i you he she it we they me him her us them my your his its our their is are was were be been am
do does did have has had will would can could should just like there then if when what who
""".split())
SUBJECT_PRONOUNS = {"i", "you", "we", "they", "he", "she"}
OBJECT_WORDS = {"us", "them", "him", "me", "up", "out", "down", "off"}
NUMBER_WORDS = {"two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
                "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
                "eighty", "ninety", "hundred", "thousand", "million", "billion"}
SPEAKER_RE = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*[A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*){0,3}"
    r"|[A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*){1,3}"
    r"|[A-Z]{2,})\s*:\s+")
STAMP_RE = re.compile(r"^\s*\[[^\]]*\]\s*")
BREAK_MARK = "||"     # a standalone token in the cleaned text: the card breaks here


def norm(w):
    t = re.sub(r"[^a-z0-9']", "", K.apostrophes(w).lower())
    return K._NUMBER_WORDS.get(t, t)


def bare(w):
    return re.sub(r"[^a-z0-9']", "", K.apostrophes(w).lower())


def is_number(w):
    x = re.sub(r"[\"'“”‘’()]", "", w).rstrip(",.;:!?")
    return bool(re.match(r"^\$?\d[\d,.]*%?$", x)) or bare(x) in NUMBER_WORDS


def ends_sentence(w):
    return w.endswith(K.SENTENCE_END)


# ── inputs ──────────────────────────────────────────────────────────────────

def whisper_words(d):
    """Word-level timing from transcript.json: whisper.cpp tokens, a flat list,
    or (with a warning) the segment-level spread the gates use."""
    with open(os.path.join(d, "transcript.json"), encoding="utf-8") as fh:
        raw = json.load(fh)
    out = []
    if isinstance(raw, list):
        for w in raw:
            t = str(w.get("text", "")).strip()
            if t:
                out.append({"t": t, "s": float(w["start"]), "e": float(w["end"]),
                            "p": float(w.get("p", w.get("probability", 1.0)))})
        return out, "word list"
    segs = raw.get("transcription") or raw.get("segments") or []
    if segs and all(isinstance(sg, dict) and sg.get("tokens") for sg in segs):
        for seg in segs:
            for tok in seg.get("tokens") or []:
                text = tok.get("text", "")
                if not text or text.strip().startswith("[_"):
                    continue
                off = tok.get("offsets") or {}
                s, e = off.get("from", 0) / 1000.0, off.get("to", 0) / 1000.0
                p = float(tok.get("p", 1.0))
                if text.startswith(" ") or not out:
                    out.append({"t": text.strip(), "s": s, "e": e, "p": p})
                else:
                    out[-1]["t"] += text.strip()
                    out[-1]["e"] = e
                    out[-1]["p"] = min(out[-1]["p"], p)
        return [w for w in out if w["t"]], "whisper.cpp tokens"
    words = C.read_transcript(d)
    return ([{"t": w["t"], "s": w["s"], "e": w["e"], "p": 1.0} for w in words
             if w["s"] is not None and w["e"] is not None],
            "SEGMENT TIMES SPREAD EVENLY — no word tokens in transcript.json; re-transcribe with word "
            "timestamps before trusting the timing")


def read_text(path, declared=None):
    """[{'t', 'turn', 'e', 'brk'}] from the cleaned text: speaker labels open a turn,
    a standalone `||` forces a card break before the next word, *word* is emphasis,
    `~~words~~` are said and left out on purpose (appended to `declared`)."""
    out = []
    labels = []
    pending = False                       # a `||` waiting for the word that follows it
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()

    def _strike(m):
        if declared is not None:
            declared.append(m.group(1).strip())
        return " "
    raw = re.sub(r"~~(.+?)~~", _strike, raw, flags=re.S)
    lines = raw.splitlines()
    for line in lines:
        if not line.strip():
            continue
        turn = False
        m = SPEAKER_RE.match(line)
        if m:
            labels.append(m.group(0).strip())
            line = line[m.end():]
            turn = True
        else:
            line = STAMP_RE.sub("", line)
        first = True                      # the line's first word carries its speaker turn
        for tok in line.split():
            # `||` alone — or glued to a word ("two||", "||three", "a||b"), which would
            # otherwise go on screen with its pipes — marks a break before the next word
            for j, t in enumerate(tok.split(BREAK_MARK)):
                if j:
                    pending = True
                if not t:
                    continue
                e = False
                mm = re.match(r"^\*(.+?)\*([,.;:!?\"”’)]*)$", t)
                if mm:
                    t, e = mm.group(1) + mm.group(2), True
                out.append({"t": t, "turn": turn and first and bool(out), "e": e,
                            "brk": pending and bool(out)})
                pending = first = False
    return out, labels


def _pass_turn(tokens, i, k):
    """Words i..i+k-1 come out: a speaker turn or a forced break they opened moves to the word after them."""
    if i + k < len(tokens):
        if any(x["turn"] for x in tokens[i:i + k]):
            tokens[i + k]["turn"] = True
        if any(x.get("brk") for x in tokens[i:i + k]):
            tokens[i + k]["brk"] = True


def clean(tokens):
    """Fillers out, stutters once. Returns the kept tokens and what came out."""
    out, removed = [], []
    i = 0
    while i < len(tokens):
        t = tokens[i]["t"]
        n = bare(t)
        if n in FILLERS:
            removed.append(t)
            _pass_turn(tokens, i, 1)
            i += 1
            continue
        # ", you know," and ", I mean," as a parenthesis — the comma goes with them
        if i + 1 < len(tokens) and (n, bare(tokens[i + 1]["t"])) in (("you", "know"), ("i", "mean")) \
                and (tokens[i + 1]["t"].endswith(",") or (out and out[-1]["t"].endswith(","))):
            removed.append(t + " " + tokens[i + 1]["t"])
            _pass_turn(tokens, i, 2)
            nxt = tokens[i + 1]["t"]
            if out and out[-1]["t"].endswith(",") and not nxt.endswith((".", "?", "!")):
                out[-1]["t"] = out[-1]["t"][:-1]
            elif out and nxt.endswith((".", "?", "!")) and not ends_sentence(out[-1]["t"]):
                out[-1]["t"] = out[-1]["t"].rstrip(",;:") + nxt[-1]
            i += 2
            continue
        hit = False
        for k in (3, 2, 1):
            if i + 2 * k <= len(tokens) and \
                    [bare(x["t"]) for x in tokens[i:i + k]] == [bare(x["t"]) for x in tokens[i + k:i + 2 * k]] \
                    and not any(x["turn"] or x.get("brk") for x in tokens[i + 1:i + 2 * k]):
                if k == 1 and n not in FUNCTION_WORDS:
                    break          # a content word said twice is emphasis
                removed.append(" ".join(x["t"] for x in tokens[i:i + k]))
                _pass_turn(tokens, i, k)
                i += k
                hit = True
                break
        if hit:
            continue
        out.append(dict(tokens[i]))
        i += 1
    return out, removed


def align(tokens, ww):
    """A time for every cleaned word from the Whisper words: [(start, end, p)], dropped words."""
    a = [norm(w["t"]) for w in ww]
    b = [norm(x["t"]) for x in tokens]
    out = [None] * len(tokens)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    ops = sm.get_opcodes()
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            for k in range(i2 - i1):
                out[j1 + k] = (ww[i1 + k]["s"], ww[i1 + k]["e"], ww[i1 + k]["p"])
        elif tag == "replace":
            s, e = ww[i1]["s"], ww[i2 - 1]["e"]
            n = j2 - j1
            for k in range(n):
                out[j1 + k] = (s + (e - s) * k / n, s + (e - s) * (k + 1) / n, 0.5)
    for i, v in enumerate(out):
        if v is None:          # a word the cleanup added: between its neighbours
            prev = next((out[j] for j in range(i - 1, -1, -1) if out[j]), None)
            nxt = next((out[j] for j in range(i + 1, len(out)) if out[j]), None)
            s = prev[1] if prev else (nxt[0] - 0.2 if nxt else 0.0)
            e = nxt[0] if nxt else s + 0.2
            out[i] = (s, max(s + 0.05, e), 0.5)
    dropped = []
    for tag, i1, i2, j1, j2 in ops:
        if tag in ("delete", "replace") and i2 > i1:
            dropped += [ww[k]["t"] for k in range(i1, i2)]
    return out, dropped


_SENT = (".", "!", "?")


def _lower_first(w):
    """Whisper capitalises the first word of every stretch it hears; an added word in the middle
    of a sentence is written in lower case ("I" and acronyms stay)."""
    core = re.sub(r"[^\w']", "", w)
    if core in ("I", "I'm", "I've", "I'll", "I'd") or (len(core) > 1 and core.isupper()):
        return w
    return w[:1].lower() + w[1:]


def reconcile(tokens, heard, tw, add_p, runs, beats_hidden):
    """The text's words with the times measured on the voice, and the words the voice says
    that the text lacks — what is said decides which words appear; the text decides spelling
    and punctuation.

    Returns (tokens, times, rep): `times` [(start, end, p)] for every token; `rep` lists
    "added" (said with p >= add_p, not in the text: now on the cards), "ruled" (heard and left
    out by a shared rule: filler, stutter, restart — with the rule), "doubtful" (heard under
    add_p: the second pass decides), "unheard" (text words the voice pass did not hear; whether
    transcript.json has them), "hidden_heard" (heard, not in the text, under a full-frame beat)."""
    tokens = [dict(x) for x in tokens]
    a = [WT.normalize(x["t"]) for x in tokens]
    b = [WT.normalize(w["t"]) for w in heard]
    # rough times for the text from transcript.json (it drifts, but by a second or two, not by a
    # beat): two equal words — "one … question" said twice, once under a beat — go to the nearer
    tb = [WT.normalize(w["t"]) for w in tw]
    rough = [None] * len(a)
    if tb:
        for i, js in WT.pair(a, tb).items():
            rough[i] = tw[js[0]]["s"]
    known = [i for i, r in enumerate(rough) if r is not None]
    for i in range(len(a)):
        if rough[i] is None and known:
            lo = max((k for k in known if k < i), default=None)
            hi = min((k for k in known if k > i), default=None)
            rough[i] = rough[lo] if hi is None else (rough[hi] if lo is None else
                                                      rough[lo] + (rough[hi] - rough[lo]) * (i - lo) / (hi - lo))
    dist = (lambda i, j: max(0.0, abs(rough[i] - heard[j]["s"]) - 1.5)) if known else None
    pr = WT.fill_gaps(a, b, WT.pair(a, b, None, dist))
    used = {j for js in pr.values() for j in js}
    rep = {"added": [], "ruled": [], "doubtful": [], "unheard": [], "hidden_heard": []}
    inserts = {}
    paired_at = sorted((js[-1], i) for i, js in pr.items())
    # heard words the text lacks, judged as the gate judges them (WT.judge_unpaired): a phrase
    # is added only when every word of it is heard surely
    jd = WT.judge_unpaired(heard, b, used, beats_hidden, sure=add_p, confirmed=WT.confirmed_by(heard, tw))
    rep["ruled"] = [(heard[j]["t"], heard[j]["s"], why) for j, why in jd["ruled"]]
    rep["hidden_heard"] = [(heard[j]["t"], heard[j]["s"]) for j in jd["hidden"]]
    rep["doubtful"] = [(heard[j]["t"], heard[j]["s"], heard[j].get("p", 1.0)) for j in jd["doubtful"]]
    for j in jd["sure"]:
        pos = 0
        for jj, i in paired_at:
            if jj < j:
                pos = max(pos, i + 1)
        inserts.setdefault(pos, []).append(j)
    # text words with no counterpart in the voice pass, and whether transcript.json has them
    tb = [WT.normalize(w["t"]) for w in tw]
    in_tw = set(WT.pair(a, tb).keys()) if tb else set()
    for i in range(len(tokens)):
        if i not in pr and a[i]:
            rep["unheard"].append((tokens[i]["t"], i in in_tw))
    # times for the text's own tokens
    times = []
    for i in range(len(tokens)):
        js = pr.get(i)
        if not js:
            times.append(None)
            continue
        s, e = heard[js[0]]["s"], heard[js[-1]]["e"]
        p = min(heard[j].get("p", 1.0) for j in js)
        share = [x for x, y in pr.items() if y == js]
        if len(share) > 1:                       # two text words for one heard word: by syllables
            wts = [WT.syllables(tokens[x]["t"]) for x in sorted(share)]
            k = sorted(share).index(i)
            span = e - s
            s, e = s + span * sum(wts[:k]) / sum(wts), s + span * sum(wts[:k + 1]) / sum(wts)
        times.append((s, e, p))
    # splice the added words in, the text's punctuation kept where the sentence ends
    out_t, out_times = [], []
    for i in range(len(tokens) + 1):
        if i in inserts:
            new = []
            for j in inserts[i]:
                w = re.sub(r"[.,;:!?…]+$", "", heard[j]["t"]).strip("\"“”") or heard[j]["t"]
                new.append({"t": _lower_first(w), "turn": False, "e": False, "brk": False, "added": True})
                rep["added"].append((heard[j]["t"], heard[j]["s"], heard[j].get("p", 1.0)))
            if out_t:
                prev = out_t[-1]
                nxt = tokens[i]["t"] if i < len(tokens) else ""
                m = re.search(r"([.!?…]+[\"”’)]*)$", prev["t"])
                if m and (not nxt or nxt[:1].isupper()):
                    # "money?" + "this weekend" -> "money this weekend?": the sentence ended later
                    prev["t"] = prev["t"][:m.start()]
                    new[-1]["t"] += m.group(1)
            elif new:
                new[0]["t"] = new[0]["t"][:1].upper() + new[0]["t"][1:]
            for x, j in zip(new, inserts[i]):
                out_t.append(x)
                out_times.append((heard[j]["s"], heard[j]["e"], heard[j].get("p", 1.0)))
        if i < len(tokens):
            out_t.append(tokens[i])
            out_times.append(times[i])
    # a time for the text words nobody heard: inside the voice between their neighbours
    filled = WT.place([((t[0], t[1], out_t[k]["t"]) if t else (None, None, out_t[k]["t"]))
                       for k, t in enumerate(out_times)], runs)
    final = []
    for k, t in enumerate(out_times):
        final.append(t if t else (filled[k][0], max(filled[k][1], filled[k][0] + 0.05), 0.5))
    return out_t, final, rep


def measure(d, words, dom):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump({"words": sorted(set(words)), "dom": dom}, fh)
        path = fh.name
    try:
        out = C.P.run_node(os.path.join(HERE, "measure_caption_words.js"), [d, path], timeout=240)
    finally:
        os.unlink(path)
    if out is None:
        sys.exit(T("no pude medir las palabras: Node.js no está instalado (run_gates.py --doctor)", "could not measure the words: Node.js is not installed (run_gates.py --doctor)"))
    if out.returncode == 4:
        sys.exit(T("no hay CSS de captions en index.html para .%s — escribí primero el DOM y el CSS del "
                 "estilo de la marca (<cliente>-brand/references/captions.md): %s",
                   "no caption CSS in index.html for .%s — first write the DOM and the CSS of the "
                 "brand's style (<client>-brand/references/captions.md): %s")
                 % (dom.get("word"), out.stderr.strip()))
    if out.returncode != 0:
        sys.exit(T("no pude medir las palabras en el navegador (%s) — sin medición no hay una sola línea", "could not measure the words in the browser (%s) — without measuring, cards cannot be kept to one line")
                 % out.stderr.strip())
    data = json.loads(out.stdout.strip().splitlines()[-1])
    if not data.get("loaded"):
        sys.exit(T("la fuente de los captions (%s) no cargó en la página — medir con otra fuente da números "
                 "falsos; revisá el <link>/@font-face del proyecto",
                   "the caption font (%s) did not load on the page — measuring with another font gives false "
                 "numbers; check the project's <link>/@font-face") % data.get("font"))
    return data


def old_emphasis(html):
    """[(word, emph)] of the CAPTIONS array already in the file, in order."""
    m = re.search(r"const CAPTIONS\s*=\s*\[(.*?)\];", html, re.S)
    if not m:
        return []
    out = []
    for w in re.finditer(r"\{\s*t\s*:\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')\s*(?:,\s*e\s*:\s*(true|false))?",
                         m.group(1)):
        out.append((w.group(1)[1:-1], w.group(2) == "true"))
    return out


# ── grouping ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project")
    ap.add_argument("--text", help="the clip's cleaned words, plain text")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--teaser", action="store_true", help="teaser numbers (default: from the frame)")
    ap.add_argument("--dump-text", action="store_true", help="print the clip's Whisper words as text")
    ap.add_argument("--explain", action="store_true", help="print why each card was cut where it was")
    args = ap.parse_args()

    d = C.project_dir(["x", args.project])
    html = C.read_html(d)
    r = C.root(html)
    ww, timing_src = whisper_words(d)
    if args.dump_text:
        # the voice pass hears each stretch alone and misses less than the full Whisper pass
        # (CLC ep1 S3: "who" and the words before a beat); its words, else transcript.json's
        wtm = WT.measure(d, html)
        src = wtm["words"] if wtm["status"] == "measured" else ww
        sys.stderr.write(T("texto de: %s\n", "text from: %s\n") % (T("la pasada sobre la voz (%s)", "the voice pass (%s)") % wtm["model"]
                                             if wtm["status"] == "measured" else "transcript.json"))
        line = []
        for w in src:
            line.append(w["t"])
            if ends_sentence(w["t"]) and len(line) > 12:
                print(" ".join(line))
                line = []
        if line:
            print(" ".join(line))
        return 0
    if not args.text:
        sys.exit(T("falta --text: el texto limpio del clip (o --dump-text para sacarlo del transcript y corregirlo)", "missing --text: the clip's clean text (or --dump-text to pull it from the transcript and correct it)"))

    P = C.PROFILE
    K_ = P["captions"]
    teaser = args.teaser or not r["portrait"]
    max_words = int(K_["max_words_teaser"] if teaser else K_["max_words_snippet"])
    min_fail, min_warn = float(K_["min_dur_fail"]), float(K_["min_dur_warn"])
    target = float(K_.get("target_words_teaser" if teaser else "target_words_snippet") or (6.0 if teaser else 3.5))
    connectors = (set(K.CONNECTORS) | set(K_.get("connectors_extra") or []))
    pz = K_.get("pauses") or {}
    pause_split = float(pz["min"]) if pz else None
    comma_closes = bool(K_.get("connector_comma_closes"))
    by_voice = bool(K_.get("cut_word_by_voice"))
    # the last card and the end of every chunk stop where the speech does: a fixed
    # outro card (profile `outro.id_re`) starts there, and a card must not run into it
    sp_end = C.speech_end(html, r["duration"]) or 1e9
    emphasis_ok = not K_.get("all_white")
    dom = dict(DOM_DEFAULT, **(K_.get("dom") or {}))
    report = ["podcast-captions · " + _profile.describe(P)]
    report += _profile.learned_lines(P, "grouping")
    tcfg = dict(K_.get("timing") or {})
    add_p = float(tcfg.get("add_p", ADD_P))

    declared = []
    tokens, labels = read_text(args.text, declared)
    marked = sum(1 for x in tokens if x["e"])
    tokens, removed = clean(tokens)

    beats = [(b["visible_start"], b["visible_end"]) for b in C.beats(html)]
    # under a full-frame beat (beats back to back hide the video as one window): it starts
    # inside the beat and its middle is not in the beat's last 0.10 s — a word said as the
    # beat leaves is shown. The gate asks the same function (WT.hidden_by)
    hidden_at = WT.hidden_by(beats)

    # TIMES: measured on the clip's own voice — each stretch between pauses heard alone,
    # every word anchored to where the voice is (video-quality-gates word_timing.py)
    wtm = WT.measure(d, html)
    report.append(T("tiempos: ", "times: ") + WT.describe(wtm))
    rec = None
    if wtm["status"] in ("measured", "energy-only"):
        tokens, times, rec = reconcile(tokens, wtm["words"], ww if wtm["status"] == "measured" else [],
                                       add_p, [tuple(x) for x in wtm["runs"]], hidden_at)
        dropped = []
        if wtm["status"] == "energy-only":
            report.append(T("OJO: sin la pasada sobre la voz (%s) los tiempos son los de transcript.json, solo "
                          "corregidos en las pausas — pueden ir corridos hasta 1.5 s dentro de una frase; "
                          "instalá faster-whisper (run_gates.py --doctor)",
                            "WARNING: without the voice pass (%s) the times are transcript.json's, corrected only "
                          "at the pauses — they can be off by up to 1.5 s inside a sentence; "
                          "install faster-whisper (run_gates.py --doctor)") % wtm["why"])
    else:
        times, dropped = align(tokens, ww)
        report.append(T("OJO: no pude leer la voz del clip (%s): tiempos de transcript.json sin medir — el gate "
                      "lo marca (timing-not-measured)",
                        "WARNING: could not read the clip's voice (%s): transcript.json times, not measured — the gate "
                      "flags it (timing-not-measured)") % wtm["why"])
        report.append("timing: %s" % timing_src)
    if not emphasis_ok:
        if marked:
            report.append(T("la marca no lleva énfasis: ignoré %d *marca(s)*", "the brand uses no emphasis: ignored %d *mark(s)*") % marked)
        for x in tokens:
            x["e"] = False
    else:
        prev = old_emphasis(html)
        if prev:
            a = [norm(w) for w, _ in prev]
            b = [norm(x["t"]) for x in tokens]
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
                if tag == "equal":
                    for k in range(i2 - i1):
                        if prev[i1 + k][1]:
                            tokens[j1 + k]["e"] = True

    ci = C.cut_info(d, html)
    cuts = ci["cuts"] or []
    # A card may cross a jump cut of the SAME shot when splitting it there would leave a single
    # dangling word or a flash (the editor, 2026-10-03: "sí, para todos"); a camera or speaker change
    # is always a boundary. Same shot is measured on the picture (C.cut_kinds) and the cuts that
    # qualify are the "soft" ones: they no longer split the stretch, and a card that spans one
    # is legal only when check_captions.split_reasons gives a reason — the gate's own test.
    kinds = C.cut_kinds(d, html, cuts, ci) if cuts else {}
    soft = {c for c, k in (kinds or {}).items() if k["same"]}
    flash_under = float((K_.get("cross_cut") or {}).get("flash_under") or min_fail)
    vp = C.voice_pauses(d, html)
    pauses = [tuple(p) for p in (vp or {}).get("pauses") or []]
    mid = [(s + e) / 2.0 for s, e, _ in times]
    n_all = len(tokens)

    def under(i):
        return hidden_at(times[i][0], times[i][1])

    # A word said as a beat enters — its voice starts before the beat is on screen, inside the
    # 0.05 s the "under a beat" test allows — joins the card before the beat when that card would
    # otherwise end on a connector: CLB ep3 S1 "Having your 3" (the 3 at 30.21, beat 4 at 30.25), as
    # the editor approved it, never "Having your" hanging. The mirror of a word said as the beat leaves.
    entering = set()
    for i in range(n_all - 1):
        if under(i) and i not in entering:
            continue
        j = i + 1
        w = tokens[i]["t"]
        if not under(j) or tokens[j]["turn"] or tokens[j].get("brk") or ends_sentence(w) \
                or bare(w) not in connectors or (comma_closes and w.rstrip().endswith(K.CLAUSE_CLOSE)):
            continue
        b0 = next((b0 for b0, b1 in beats if b0 - 0.05 <= times[j][0] < b1), None)
        if b0 is not None and times[j][0] < b0:
            entering.add(j)

    def hidden(i):
        return i not in entering and under(i)

    # the pause that sits between word i and word i+1 (by midpoints: Whisper
    # stretches the word before a pause and starts the next one early)
    gap_pause = {}
    for s0, s1 in pauses:
        pm = (s0 + s1) / 2.0
        for i in range(n_all - 1):
            if mid[i] < pm <= mid[i + 1]:
                cur = gap_pause.get(i)
                if cur is None or (s1 - s0) > (cur[1] - cur[0]):
                    gap_pause[i] = (s0, s1)
                break

    def after_cut(i, c):
        """Which side of the cut word i is on — decided in check_captions.word_after_cut, the
        same function the gate uses to split a card that crosses a cut."""
        return K.word_after_cut(times[i][0], times[i][1], tokens[i]["t"],
                                tokens[i - 1]["t"] if i > 0 else None, c, pauses, connectors, by_voice)

    # every cut, as the index of the first word on its far side
    cut_at = {}
    for c in cuts:
        b = next((i for i in range(n_all) if times[i][1] > c - 1.0 and after_cut(i, c)), None)
        if b is not None and (b not in cut_at or (cut_at[b] in soft and c not in soft)):
            # two cuts before the same word: the first one, unless a later one is a camera
            # change and the first a jump cut a card may cross — the camera change is the boundary
            cut_at[b] = c

    def cut_between(p, i):
        return [cut_at[b] for b in range(p + 1, i + 1) if b in cut_at]

    def hard_cut_between(p, i):
        return [c for c in cut_between(p, i) if c not in soft]

    def soft_between(p, i):
        return [c for c in cut_between(p, i) if c in soft]

    def onset_after_silence(i, after):
        """Where the voice comes back before word i: the end of a measured pause
        that starts after `after` and ends close to Whisper's start."""
        s = times[i][0]
        best = None
        for s0, s1 in pauses:
            if s0 >= after - 0.01 and s0 < s and abs(s1 - s) <= ONSET_MAX:
                best = s1 if best is None else max(best, s1)
        return best

    keep = [i for i in range(n_all) if not hidden(i)]
    # onset of a card that would open on word i
    st, open_from = {}, {}
    for k, i in enumerate(keep):
        s = times[i][0]
        p = keep[k - 1] if k > 0 else None
        cb = [c for c in cut_between(p if p is not None else -1, i)
              if not any(b0 + 0.05 < c < b1 - 0.05 for b0, b1 in beats)
              and (p is not None or c > s - 0.4)]
        beat_ends = [b1 for b0, b1 in beats if b1 <= mid[i] and (p is None or b1 > times[p][0])]
        if cb:
            s = cb[-1]                          # after a cut: on the cut
        elif p is not None and i == p + 1:
            gp = gap_pause.get(p)
            if gp and abs(gp[1] - s) <= ONSET_MAX:
                s = gp[1]                       # after a pause: where the voice comes back
        else:                                   # the first word, or the first after a beat
            floor_t = max(beat_ends) if beat_ends else 0.0
            o = onset_after_silence(i, floor_t)
            if o is not None:
                s = o
            elif beat_ends and 0 <= s - floor_t <= BEAT_SNAP:
                s = floor_t
        if beat_ends:
            s = max(s, max(beat_ends))          # never under the beat it follows
        st[i] = max(0.0, s)
        # how early a card on word i may open when it needs the time to reach
        # the floor: into the gap after the previous word, never before that
        # word ends — and only when nothing (a cut, a pause, a beat) placed it.
        # The measured times already start a word after a pause where the voice
        # comes back, so "nothing placed it" is asked of the pause itself: a card
        # never opens early into a silence (nothing waits on screen)
        open_from[i] = (max(times[p][1], st.get(p, 0.0)) if p is not None and i == p + 1
                        and s == times[i][0] and not gap_pause.get(p) else st[i])
        if p is None and st[i] < 0.4:
            open_from[i] = 0.0      # the video opens on its first card (CLB ep3 S1: 0.02, voice at 0.20)

    # hard boundaries
    frags, cur = [], []
    split_why = {"sentence": 0, "cut": 0, "beat": 0, "turn": 0, "forced": 0, "pause": 0}
    for i in keep:
        if cur:
            p = cur[-1]
            why = None
            if ends_sentence(tokens[p]["t"]):
                why = "sentence"
            elif i != p + 1 or any(times[p][0] < s0 < times[i][0] for s0, _ in beats):
                why = "beat"
            elif hard_cut_between(p, i):
                why = "cut"
            elif tokens[i]["turn"]:
                why = "turn"
            elif tokens[i].get("brk"):
                why = "forced"
            elif pause_split and gap_pause.get(p) and gap_pause[p][1] - gap_pause[p][0] >= pause_split:
                why = "pause"
            if why:
                split_why[why] += 1
                frags.append(cur)
                cur = []
        cur.append(i)
    if cur:
        frags.append(cur)

    def boundary_after(i):
        """When the card holding word i must end at the latest: the next beat or cut."""
        t0 = times[i][0]
        nxt = [s for s, _ in beats if s > t0] + [c for b, c in cut_at.items() if b > i]
        return min(nxt) if nxt else None

    words_needed = [tokens[i]["t"] for i in keep]
    m = measure(d, words_needed, dom) if words_needed else {"widths": {}, "gap": 0, "limit": 1e9}
    widths, gap, limit = m["widths"], float(m["gap"]), float(m["limit"])

    def card_px(ws):
        return sum(widths[w] for w in ws) + gap * (len(ws) - 1)

    def clause_closed(w):
        """"what's going on," — the comma closed the clause, the connector is not hanging
        (only for a brand that says so: captions.connector_comma_closes)."""
        return comma_closes and w.rstrip().endswith(K.CLAUSE_CLOSE)

    def whisper_gap(i):
        return times[i + 1][0] - times[i][1] if i + 1 < n_all else 9.0

    def cost_of(idx, i, j, chunk_end):
        """(cost, why) of one card holding idx[i:j]; None when it does not fit one line."""
        n = len(idx)
        k = j - i
        ws = [tokens[x]["t"] for x in idx[i:j]]
        px = card_px(ws)
        if px > limit:
            return None
        why = []
        start = st[idx[i]]
        end = st[idx[j]] if j < n else chunk_end
        # a card that spans a jump cut of the same shot is legal only when splitting it there would
        # leave a single dangling word or a flash — the gate's test (K.split_reasons) — and costs
        # CROSS_COST, so it is the last resort and not a way to build longer cards
        spans = [(q - i, c) for q in range(i + 1, j) for c in soft_between(idx[q - 1], idx[q])]
        if spans:
            if not all(jr["reasons"] for jr in K.crossing_reasons(ws, spans, start, end, connectors,
                                                                   flash_under, comma_closes)):
                return None
            why.append(("crosses a same-shot jump cut", CROSS_COST * len(spans)))
        dur = end - start
        if dur < min_warn:              # it may open a little earlier (see open_from) …
            start = min(start, max(open_from[idx[i]], end - min_warn))
            if j < n and st[idx[j]] == times[idx[j]][0] and end - start < min_fail:
                end = min(end + LATE_MAX, start + min_fail + 0.02)   # … or, under the FAIL floor, close later
            dur = end - start
        if dur < min_fail:              # a gate FAIL, worse the shorter it is
            why.append(("flicker %.2fs" % dur, 45 + 100 * (min_fail - dur)))
        elif dur < min_warn:            # a gate WARN
            why.append(("brief %.2fs" % dur, 12))
        if limit - px < NEAR:           # a WARN only: the width is measured with the real font
            why.append(("near limit %d/%d" % (px, limit), 1))
        if j < n and bare(ws[-1]) in connectors and not ends_sentence(ws[-1]) and not clause_closed(ws[-1]):
            why.append(("ends on connector", 50))     # a gate FAIL
        if k == 1 and n > 1:
            why.append(("one word", 15))
        if k == 2 and n > 2:
            why.append(("two words", 3))
        why.append(("length", abs(k - target) * 0.6))
        if ws[-1].endswith((",", ";", ":")):
            why.append(("ends on a comma", -2))
        if any(w.endswith((",", ";", ":")) for w in ws[:-1]):
            why.append(("a comma inside", 3))      # the phrase breaks there, so should the card
        for q in range(i, j - 1):                  # a pause inside: the words after it wait on screen
            gp = gap_pause.get(idx[q])
            if gp and gp[1] - gp[0] >= PAUSE_PREFER:
                lim = pause_split or 0.40
                why.append(("holds a %.2fs pause" % (gp[1] - gp[0]),
                            HOLD_BASE + HOLD_SCALE * min(1.0, (gp[1] - gp[0] - PAUSE_PREFER)
                                                         / max(0.01, lim - PAUSE_PREFER))))
        if j < n:
            a_w, b_w = ws[-1], tokens[idx[j]]["t"]
            gp = gap_pause.get(idx[j - 1])
            if gp and gp[1] - gp[0] >= PAUSE_PREFER:
                why.append(("breaks at a %.2fs pause" % (gp[1] - gp[0]), -3))
            elif vp is None and whisper_gap(idx[j - 1]) > 0.35:
                why.append(("breaks at a Whisper gap", -3))
            if not a_w.endswith(PUNCT_END):
                if is_number(b_w):
                    why.append(("splits a word from its number", 20))      # "round | 2"
                elif is_number(a_w) and b_w[:1].isalpha():
                    why.append(("splits a number from its word", 8))       # "3 | things"
                # the phrase shape a line break follows: a phrase opens on its
                # function word; a subject stays with its verb, a verb with its object
                if bare(b_w) in connectors:
                    why.append(("next opens a phrase", -1))
                if bare(a_w) in SUBJECT_PRONOUNS:
                    why.append(("splits a subject from its verb", 2))       # "the questions you | bring"
                if bare(b_w) in OBJECT_WORDS:
                    why.append(("splits a verb from its object", 2))        # "tell | us"
        return sum(c for _, c in why), why

    def partition(idx, chunk_end):
        n = len(idx)
        INF = float("inf")
        best = [INF] * (n + 1)
        back = [0] * (n + 1)
        best[0] = 0.0
        for j in range(1, n + 1):
            for k in range(1, max_words + 1):
                i = j - k
                if i < 0:
                    break
                cw = cost_of(idx, i, j, chunk_end)
                if cw is None:
                    continue
                if best[i] + cw[0] < best[j]:
                    best[j] = best[i] + cw[0]
                    back[j] = i
        if best[n] == INF:
            return [[x] for x in idx]
        cards, j = [], n
        while j > 0:
            cards.append((idx[back[j]:j], cost_of(idx, back[j], j, chunk_end)))
            j = back[j]
        return cards[::-1]

    cards = []
    for fi, fr in enumerate(frags):
        nxt = st[frags[fi + 1][0]] if fi + 1 < len(frags) else None
        hard = boundary_after(fr[-1])
        chunk_end = nxt if nxt is not None else min(times[fr[-1]][1] + HOLD_LAST, sp_end)
        if hard is not None and hard < chunk_end:
            chunk_end = hard
        for c, cw in partition(fr, chunk_end):
            cards.append(c)
            if args.explain:
                sys.stderr.write("  %-34s %6.1f  %s\n" % ('"' + " ".join(tokens[x]["t"] for x in c) + '"',
                                 cw[0] if cw else 0, " · ".join("%s %+g" % (a, b) for a, b in (cw[1] if cw else [])
                                                                if b)))

    out = []
    for ci_, c in enumerate(cards):
        start = st[c[0]]
        if ci_ + 1 < len(cards):
            end = st[cards[ci_ + 1][0]]
        else:
            end = min(times[c[-1]][1] + HOLD_LAST, sp_end)
        hard = boundary_after(c[-1])
        if hard is not None and hard < end:
            end = hard
        out.append({"start": round(start, 3), "end": round(max(end, start + 0.05), 3),
                    "words": [tokens[i]["t"] for i in c], "e": [tokens[i]["e"] for i in c],
                    "px": card_px([tokens[i]["t"] for i in c]), "voice": times[c[0]][0],
                    "first": c[0], "last": c[-1]})
    for a, b in zip(out, out[1:]):
        if b["start"] < a["end"]:
            a["end"] = b["start"]
    # a card short of the floor may open a little earlier, into the gap after
    # the previous word — never before that word ends, never on a cut or after
    # a pause it was moved to, and never taking the previous card under its floor
    rescued = []
    if out and out[0]["end"] - out[0]["start"] < min_warn and open_from[out[0]["first"]] < out[0]["start"]:
        b = out[0]
        new_start = round(max(open_from[b["first"]], b["end"] - min_warn), 3)
        rescued.append('"%s" %.2f→%.2f' % (" ".join(b["words"]), b["start"], new_start))
        b["start"] = new_start
    for k in range(1, len(out)):
        a, b = out[k - 1], out[k]
        dur = b["end"] - b["start"]
        if dur >= min_warn or abs(a["end"] - b["start"]) > 0.011:
            continue
        if open_from[b["first"]] >= b["start"] - 0.005:
            continue          # a cut, a pause or a beat placed it: it stays
        lo = max(open_from[b["first"]], a["start"] + min_warn)
        want = b["end"] - min_warn
        new_start = round(max(lo, want), 3)
        if new_start < b["start"] - 0.005:
            rescued.append('"%s" %.2f→%.2f' % (" ".join(b["words"]), b["start"], new_start))
            b["start"] = a["end"] = new_start
    # … and, still under the FAIL floor, close a little later when the next card opens in the
    # middle of continuous speech (not on a cut, a pause or a beat) — card after card: in fast
    # speech two or three short cards in a row borrow from the longer one that closes the phrase,
    # each opening at most LATE_MAX after its first word (CLC ep1 S3, "Hey, what does | he want to
    # make | some extra money | this weekend?", 1.3 s for three cards: 0.16 s late at most)
    def free(k):
        c = out[k]
        return (abs(c["start"] - round(times[c["first"]][0], 3)) < 0.006
                and not any(abs(c["start"] - x) < 0.01 for x in cuts)
                and not gap_pause.get(c["first"] - 1) and abs(out[k - 1]["end"] - c["start"]) <= 0.011)
    for k in range(len(out) - 1):
        b = out[k]
        if b["end"] - b["start"] >= min_fail:
            continue
        q = k + 1
        want = b["start"] + min_fail + 0.02
        moved = []
        while q < len(out) and free(q) and out[q - 1]["end"] < want - 0.005:
            c = out[q]
            onset = times[c["first"]][0]
            new_start = round(min(want, onset + LATE_MAX), 3)
            if new_start <= c["start"] + 0.005:
                break
            moved.append((q, c["start"], new_start))
            out[q - 1]["end"] = c["start"] = new_start
            if c["end"] - c["start"] >= min_fail + 0.02:
                break                              # the next one still holds: done
            want = c["start"] + min_fail + 0.02    # it got short in turn: push the one after
            q += 1
        if moved:
            rescued.append(T("cadena desde \"%s\": %s", "chain from \"%s\": %s") % (" ".join(b["words"]), ", ".join(
                T("«%s» abre %.2f→%.2f (%.2fs tras su palabra)", "“%s” opens %.2f→%.2f (%.2fs after its word)") % (out[x]["words"][0], o, n_, n_ - times[out[x]["first"]][0])
                for x, o, n_ in moved)))

    lines = ["const CAPTIONS = ["]
    for g in out:
        ws = ",".join(("{t:%s,e:true}" if e else "{t:%s}") % json.dumps(w, ensure_ascii=False)
                      for w, e in zip(g["words"], g["e"]))
        lines.append("  { start: %.3f, end: %.3f, words: [%s] }," % (g["start"], g["end"], ws))
    lines.append("];")
    js = "\n".join(lines)

    short = [g for g in out if g["end"] - g["start"] < min_warn]
    dangling = [g for g in out[:-1] if bare(g["words"][-1]) in connectors
                and not ends_sentence(g["words"][-1]) and not clause_closed(g["words"][-1])]
    low = ["%s@%.2f" % (w["t"], w["s"]) for w in (wtm["words"] if wtm["status"] == "measured" else ww)
           if w.get("p", 1.0) < 0.5]
    waits = [T('"%s" abre en el corte %.2f y la voz llega en %.2f', '"%s" opens on the cut at %.2f and the voice arrives at %.2f') % (g["words"][0], g["start"], g["voice"])
             for g in out if any(abs(g["start"] - c) < 0.01 for c in cuts) and g["voice"] - g["start"] > 0.5]
    under = [(tokens[i]["t"], times[i][0]) for i in range(n_all) if hidden(i)]
    report.append(T("texto: %d palabras%s", "text: %d words%s") % (len(tokens), (T(" · %d rótulo(s) de speaker", " · %d speaker label(s)") % len(labels)) if labels else ""))
    # every said word that does not reach the screen, with the rule that took it out
    report.append(T("FUERA DE PANTALLA, con su regla — muletillas/tartamudeos del texto: %s · a mano (~~ ~~): %s · "
                  "bajo un beat (no se ven): %s%s",
                    "OFF SCREEN, each with its rule — fillers/stutters in the text: %s · by hand (~~ ~~): %s · "
                  "under a beat (not visible): %s%s")
                  % (", ".join(removed) or T("nada", "none"), " | ".join(declared) or T("nada", "none"),
                     ("%d (%s … %s)" % (len(under), "%s@%.2f" % under[0], "%s@%.2f" % under[-1])) if under else T("nada", "none"),
                     (T(" · la limpieza sacó o cambió: ", " · the cleanup removed or changed: ") + ", ".join(dropped)) if dropped else ""))
    if entering:
        report.append(T("dichas cuando entra un beat (la voz arranca antes de que se vea): van en la tarjeta anterior, "
                        "que si no terminaba en conector: %s",
                        "said as a beat enters (the voice starts before it shows): on the card before it, which "
                        "would otherwise end on a connector: %s")
                      % ", ".join("%s@%.2f" % (tokens[i]["t"], times[i][0]) for i in sorted(entering)))
    hang = [g for g in out if g is out[-1] or any(abs(g["end"] - b0) < 0.02 for b0, _ in beats)]
    hang = [g for g in hang if bare(g["words"][-1]) in connectors and not ends_sentence(g["words"][-1])
            and not clause_closed(g["words"][-1])]
    if hang:
        report.append(T("OJO, terminan en conector y lo que sigue se dice bajo un beat (el gate falla "
                        "caption-dangling: mover el beat a donde cierra la frase, o decide el usuario): ",
                        "WARNING, these end on a connector and what follows is said under a beat (the gate fails "
                        "caption-dangling: move the beat to where the phrase closes, or the user decides): ")
                      + " · ".join('"%s"' % " ".join(g["words"]) for g in hang))
    if rec:
        report.append(T("LO QUE SE DICE manda: agregadas (se oyen con p ≥ %.2f y el texto no las tenía): %s · "
                      "oídas y fuera por regla: %s · DUDOSAS (p < %.2f, no van — segundo pase): %s · "
                      "oídas bajo un beat: %d",
                        "WHAT IS SAID decides: added (heard at p ≥ %.2f and missing from the text): %s · "
                      "heard and left out by a rule: %s · DOUBTFUL (p < %.2f, left out — second pass): %s · "
                      "heard under a beat: %d")
                      % (add_p, ", ".join("%s@%.2f (p %.2f)" % x for x in rec["added"]) or T("nada", "none"),
                         ", ".join("%s@%.2f %s" % x for x in rec["ruled"]) or T("nada", "none"), add_p,
                         ", ".join("%s@%.2f (p %.2f)" % x for x in rec["doubtful"]) or T("nada", "none"),
                         len(rec["hidden_heard"])))
        if rec["unheard"]:
            report.append(T("del texto y la pasada sobre la voz no las oye (van, con tiempo entre sus vecinas — "
                          "second_pass.py decide; si nadie las oye, salen): %s",
                            "in the text, not heard by the voice pass (kept, timed between their neighbours — "
                          "second_pass.py decides; if nobody hears them, they come out): %s")
                          % ", ".join("%s (%s)" % (w, T("transcript.json sí", "transcript.json hears it") if t else T("NADIE la oye", "NOBODY hears it"))
                                      for w, t in rec["unheard"]))
    report.append(T("cortes: %d (%s) · pausas medidas: %s · beats: %d", "cuts: %d (%s) · measured pauses: %s · beats: %d")
                  % (len(cuts), ci["summary"],
                     (T("%d de %.2fs o más (piso %.1f dB, %s)", "%d of %.2fs or more (floor %.1f dB, %s)") % (
                         sum(1 for s0, s1 in pauses if pause_split and s1 - s0 >= pause_split),
                         pause_split or 0, vp["floor"], vp["source"])) if vp else T("NO — no pude leer el audio", "NO — could not read the audio"),
                     len(beats)))
    if vp and vp.get("limited"):
        report.append(T("OJO: %s lleva una cama o ruido bajo la voz (el décimo más silencioso queda a %.1f dB del "
                      "umbral): hay pausas que no se ven y las tarjetas no se parten en ellas — poné la voz limpia "
                      "de este corte como voice.wav en la carpeta del proyecto",
                        "WARNING: %s has a bed or noise under the voice (the quietest tenth sits %.1f dB from the "
                      "threshold): some pauses are not seen and the cards do not split at them — put the clean voice "
                      "of this cut as voice.wav in the project folder") % (vp["source"], vp.get("margin", 0.0)))
    if kinds is None:
        report.append(T("OJO: no pude medir si los cortes son del mismo plano (sin video o sin ffmpeg: "
                      "run_gates.py --doctor): todos cortan la tarjeta, como antes",
                        "WARNING: could not measure whether the cuts are of the same shot (no video or no ffmpeg: "
                      "run_gates.py --doctor): every cut splits the card, as before"))
    elif cuts and (K_.get("cross_cut") or {}).get("same_shot"):
        other = [c for c, k in kinds.items() if not k["same"]]
        report.append(T("cortes del mismo plano (una tarjeta puede cruzarlos solo si partirla deja una palabra colgando "
                      "o un parpadeo): %d de %d · otro plano o sin medir, siempre fronteras: %d%s",
                        "same-shot cuts (a card may cross them only if splitting it would leave a dangling word "
                      "or a flash): %d of %d · different shot or not measured, always boundaries: %d%s")
                      % (len(soft), len(cuts), len(other),
                         (" (%s)" % "; ".join("%.2f %s" % (c, re.split(r" \((?:mismo plano|same shot) (?:si|if) ", kinds[c]["why"])[0]) for c in other[:4]))
                         if other else ""))
    report.append(T("fronteras duras: %s", "hard boundaries: %s") % ", ".join("%s %d" % kv for kv in split_why.items() if kv[1]))
    report.append(T("%d tarjetas · %d bajo %.1fs · %d terminan en conector · ancho máx %d/%dpx (%s)", "%d cards · %d under %.1fs · %d end on a connector · max width %d/%dpx (%s)")
                  % (len(out), len(short), min_warn, len(dangling),
                     max((g["px"] for g in out), default=0), limit, m.get("font")))
    crossed, doubtful = [], []
    for g in out:
        # only the cuts the grouping saw as the start of a word's far side (two cuts inside one word
        # share a far-side word and one of them is not seen: the gate is the judge of those)
        spans, nwords = [], len(g["words"])
        for c in sorted(set(cut_at.values()) & soft):
            if g["start"] + 0.02 < c < g["end"] - 0.02:
                k = sum(1 for x in range(g["first"], g["last"] + 1) if not after_cut(x, c))
                if 0 < k < nwords:
                    spans.append((k, c))
                else:
                    doubtful.append(T('«%s» cruza el corte de %.2f con todas sus palabras %s del corte', '“%s” crosses the cut at %.2f with all its words %s the cut')
                                    % (" ".join(g["words"]), c, T("antes", "before") if k else T("después", "after")))
        if spans:
            for jr in K.crossing_reasons(g["words"], spans, g["start"], g["end"], connectors, flash_under,
                                         comma_closes):
                line = T('«%s» cruza el corte de %.2f (%s): %s', '“%s” crosses the cut at %.2f (%s): %s') % (" ".join(g["words"]), jr["cut"],
                                                                 kinds[jr["cut"]]["ev"],
                                                                 T(" y ", " and ").join(jr["reasons"]) or T("no hace falta", "not needed"))
                (crossed if jr["reasons"] else doubtful).append(line)
    if crossed:
        report.append(T("tarjetas que cruzan un corte de salto del mismo plano (el editor, 2026-10-03; partirlas dejaba una "
                      "palabra colgando o un parpadeo): ",
                        "cards that cross a same-shot jump cut (the editor, 2026-10-03; splitting them would leave a "
                      "dangling word or a flash): ") + " · ".join(crossed))
    if doubtful:
        report.append(T("OJO, el gate no va a dejar pasar estas (partirlas en el corte no deja ni una palabra colgando "
                      "ni un parpadeo con los tiempos finales): ",
                        "WARNING, the gate will not pass these (splitting them at the cut leaves neither a dangling word "
                      "nor a flash with the final times): ") + " · ".join(doubtful))
    if rescued:
        report.append(T("ajustadas para no quedar cortas (abren en el hueco tras la palabra anterior, "
                      "o cierran apenas después): ",
                        "adjusted so they are not too short (they open in the gap after the previous word, "
                      "or close slightly later): ") + " · ".join(rescued))
    if waits:
        report.append(T("esperan en pantalla tras un corte (mirarlas): ", "waiting on screen after a cut (look at them): ") + " · ".join(waits))
    report.append(T("segundo pase de ASR (p<0.5): %s", "ASR second pass (p<0.5): %s") % (", ".join(low) or T("nada", "none")))
    if ci["require_list"] and ci["listed"] is None:
        report.append(T("OJO: sin cuts.txt y este cliente lo necesita — los cortes no se vieron (podcast-beat-plan 2b)", "WARNING: no cuts.txt and this client needs it — the cuts were not seen (podcast-beat-plan 2b)"))
    sys.stderr.write("\n".join(report) + "\n")

    if args.write:
        mm = re.search(r"const CAPTIONS\s*=\s*\[.*?\];", html, re.S)
        if mm:
            old = mm.group(0)
            comments = len(re.findall(r"^\s*//", old, re.M))
            bdir = os.path.join(d, ".captions-backup")
            os.makedirs(bdir, exist_ok=True)
            bfile = os.path.join(bdir, "CAPTIONS-%s.js" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
            with open(bfile, "w", encoding="utf-8") as fh:
                fh.write(old + "\n")
            new = html[:mm.start()] + js + html[mm.end():]
            sys.stderr.write(T("array anterior guardado en %s%s\n", "previous array saved in %s%s\n")
                             % (bfile, (T(" (tenía %d línea(s) de comentario que no pasan al nuevo)", " (it had %d comment line(s) that do not carry over to the new one)") % comments)
                                if comments else ""))
        else:
            anchor = html.find("const capLayer")
            if anchor < 0:
                sys.exit(T("no encontré `const CAPTIONS` ni el builder (`const capLayer`) para insertar", "could not find `const CAPTIONS` or the builder (`const capLayer`) to insert the array"))
            new = html[:anchor] + js + "\n\n      " + html[anchor:]
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(new)
        sys.stderr.write(T("CAPTIONS escrito en index.html — ahora check_captions.py\n", "CAPTIONS written to index.html — now run check_captions.py\n"))
    else:
        print(js)
    return 0


if __name__ == "__main__":
    sys.exit(main())
