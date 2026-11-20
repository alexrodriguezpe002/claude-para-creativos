#!/usr/bin/env python3
"""Caption engine proven on the Prospect P videos (Sept 2026).

Turns a word-level transcript (list of {"w","s","e","p"} in MASTER time) plus the
list of cuts taken from that master into caption cards: one physical line, 2-5
words, >= 0.7 s on screen, with the per-word timing needed to highlight the word
being spoken. On top of the grouping it cleans what the editor does not want written:
fillers, "you know," / "I mean," used as crutches, repeated function words from a
stutter, and wrong capitalization after a cut.

Use it as a module (build_captions) or from the command line:

    python3 captions.py text  <project>/index.html        # full caption text + flags
    python3 captions.py measure --widths caption-widths.json --font Font-600.woff2 \
            --from-html <project>/index.html                # measure missing widths

Everything here is deterministic: same input, same cards.
"""
import argparse
import html as _html
import json
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent

# ----------------------------------------------------------------- vocabulary
# A line never ends on one of these (unless it is the end of a sentence): it
# leaves the next line limping. "than" and a final period are fine.
CONNECTORS = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into",
              "is", "it", "its", "my", "of", "on", "or", "our", "so", "that", "the",
              "their", "there", "these", "this", "to", "was", "we", "with", "you",
              "your", "i", "he", "she", "they", "like", "just", "have", "has",
              "there's", "here's", "it's", "that's", "we're", "they're", "i'm",
              "what", "when", "if", "not", "no", "some", "all",
              "across", "after", "against", "among", "because",
              "before", "behind", "below", "beneath", "beside", "between", "beyond",
              "during", "except", "including", "inside", "near", "onto",
              "outside", "per", "since", "throughout",
              "toward", "towards", "under", "until", "upon", "via", "while",
              "within", "without", "how", "why", "which", "who", "whose", "whom",
              "am", "are", "be", "been", "being", "were", "will", "would", "can",
              "could", "should", "may", "might", "must", "do", "does", "did",
              "had", "his", "her", "him", "them", "us", "me", "one", "any",
              "both", "each", "every", "very", "more", "most", "much", "many"}

# Particles that cannot open a line: they belong to the phrasal verb before them
# ("figure | out" reads broken).
PARTICLES = {"out", "up", "in", "on", "off", "down", "over", "back", "away",
             "through", "apart", "together", "around", "about"}

# Heard, never written.
FILLERS = {"uh", "um", "ah", "er", "erm", "hmm", "mm"}

# Fixed spellings, keyed by the lowercase word as the transcript writes it.
CASE_FIX = {"3d": "3D"}

# Layout defaults (Space Grotesk 600 at 64 px on a 1080-wide frame).
MAXW = 5      # words per line, hard cap
CAPW = 892    # usable line width in px: 1080 - 50*2 margin - 44*2 padding
MINT = 0.7    # minimum time on screen; below this a card is a blink
MAXT = 2.4    # soft cap on time per card


class Widths:
    """Real rendered widths of each word, measured in a browser with the caption
    font loaded (see `measure`). fontTools and character counts both come out
    narrower than the render and let through lines that later wrap."""

    def __init__(self, path):
        self.path = pathlib.Path(path)
        d = json.loads(self.path.read_text())
        self.size, self.space, self.table = d["size"], d["space"], d["w"]

    def word(self, w):
        return self.table.get(w, len(w) * 0.52 * self.size)

    def line(self, ws):
        return sum(self.word(w["w"]) for w in ws) + self.space * (len(ws) - 1)

    def missing(self, words):
        return sorted({w for w in words if w not in self.table})


# ------------------------------------------------------------------- grouping
def group_words(ws, widths, maxw=MAXW, capw=CAPW, mint=MINT, maxt=MAXT):
    """Split words into caption lines.

    First by sentence: a period closes the line and never leaves a lone word
    after it. Then each sentence is split into chunks of 1..maxw words choosing
    the minimum-cost partition, not the first one that fits. The cost punishes
    what the editor marked as errors: a line that ends on a connector, an orphan word,
    a blink under `mint`, a line wider than the frame. It rewards cutting where
    there is already a comma.
    """
    def is_end(w):
        return w["w"].rstrip().endswith((".", "?", "!"))

    def is_comma(w):
        return w["w"].rstrip().endswith((",", ";", ":", "—"))

    def conn(w):
        return w["w"].strip(",.!?;:—").lower() in CONNECTORS

    def cost(g, nxt, last, nwords):
        d = g[-1]["e"] - g[0]["s"]
        c = 3.0 * abs(len(g) - 4)                       # 4 words is the comfortable length
        if conn(g[-1]) and not is_end(g[-1]):
            c += 60                                     # dangling connector
        elif not is_end(g[-1]) and g[-1]["w"].strip(",.!?;:").lower() in PARTICLES:
            c += 18                                     # closes a phrasal verb: lighter
        if d < mint:
            c += 40                                     # blink
        if len(g) == 1 and nwords > 1:
            c += 25                                     # orphan word
        if nxt is not None and nxt["w"].strip(",.!?;:").lower() in PARTICLES:
            c += 30                                     # splits a phrasal verb: figure | out
        if widths.line(g) > capw:
            c += 80                                     # does not fit on one physical line
        if d > maxt:
            c += 6 * (d - maxt)
        if is_comma(g[-1]) or is_end(g[-1]):
            c -= 6                                      # cut where punctuation already is
        return c

    def split(sent):
        n = len(sent)
        best = [None] * (n + 1)
        best[0] = (0.0, [])
        for i in range(1, n + 1):
            for L in range(1, maxw + 1):
                j = i - L
                if j < 0 or best[j] is None:
                    continue
                g = sent[j:i]
                cand = best[j][0] + cost(g, sent[i] if i < n else None, i == n, n)
                if best[i] is None or cand < best[i][0]:
                    best[i] = (cand, best[j][1] + [g])
        return best[n][1]

    sents, cur = [], []
    for w in ws:
        cur.append(w)
        if is_end(w):
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)
    groups = []
    for sent in sents:
        groups.extend(split(sent))
    return groups


# ------------------------------------------------------------------- building
def assign_words(words, cuts, drop=(), fillers=FILLERS):
    """Which cut each word belongs to.

    A word belongs to the cut where it STARTS. If it starts in a gap between two
    cuts, it belongs to the next cut as long as at least 0.08 s of it falls
    inside. The word is then clipped to its cut. Two Whisper habits made the old
    rule ("must start inside and end within 0.3 s of the cut") lose words:
      - Whisper stretches a word over the silence that follows; if that silence
        was cut, the word ended near no cut ("like", "20 blocks").
      - Whisper starts the word after a pause EARLY; if the pause was cut, the
        word started in a hole ("that", "how").
    `drop` holds master start times (rounded to 0.01) of words that are heard
    but not written. Returns one list per cut; each word keeps its original
    start as "s0".
    """
    drop = {round(t, 2) for t in drop}
    bucket = [[] for _ in cuts]
    for w in words:
        if round(w["s"], 2) in drop or w["w"].strip(",.!?;:").lower() in fillers:
            continue
        for k, (i0, i1) in enumerate(cuts):
            if i0 - .02 <= w["s"] < i1:
                break
            if w["s"] < i0:
                k = k if w["e"] - i0 >= .08 else None
                break
        else:
            k = None
        if k is not None:
            i0, i1 = cuts[k]
            bucket[k].append(dict(w, s=max(w["s"], i0), e=min(w["e"], i1), s0=w["s"]))
    return bucket


def clean_disfluencies(bucket, text_fix=None):
    """Remove what a speaker says by mistake, over the text AS IT WILL BE SHOWN.

      - "you know," / "I mean," used as a crutch (the second word carries a comma)
      - a lone "Okay." and "Well," opening a sentence
      - a function word repeated back to back ("a, a more advanced") stays once;
        content words stay repeated ("far, far more advanced" is emphasis)

    False starts ("a term, a word") are not detected: list them in `drop`.
    `text_fix` maps a master start time (0.01) to corrected text, for the comma
    left dangling when a filler goes ("advanced, | system of, | on, off").
    """
    norm = lambda t: re.sub(r"[^a-z0-9']", "", t.lower())
    seq = [w for ws in bucket for w in ws]
    kill = set()
    for i, w in enumerate(seq):
        low = w["w"].lower()
        nxt = seq[i + 1]["w"].lower() if i + 1 < len(seq) else ""
        if (norm(low), nxt) in {("you", "know,"), ("i", "mean,")}:
            kill |= {i, i + 1}
        if low in ("okay.", "okay,"):
            kill.add(i)
        if low == "well," and (i == 0 or seq[i - 1]["w"][-1:] in ".?!"):
            kill.add(i)
        if nxt and norm(low) == norm(nxt) and norm(low) in CONNECTORS:
            kill.add(i)
    gone = {id(seq[i]) for i in kill}
    fix = {round(t, 2): txt for t, txt in (text_fix or {}).items()}
    return [[dict(w, w=fix.get(round(w["s0"], 2), w["w"])) for w in ws if id(w) not in gone]
            for ws in bucket]


def fix_case(bucket, case_fix=CASE_FIX):
    """A sentence that starts after a period gets a capital letter, looking at
    the text as shown (the cut may have removed what came before), and fixed
    spellings are applied ("3d" -> "3D")."""
    prev = "."
    for ws in bucket:
        for w in ws:
            t = case_fix.get(w["w"].lower(), w["w"])
            if prev[-1:] in ".?!" and t[:1].isalpha() and t[:1].islower():
                t = t[0].upper() + t[1:]
            w["w"] = t
            prev = t
    return bucket


def build_captions(words, cuts, seg_map, widths, *, cont=(), joins=(), drop=(),
                   text_fix=None, case_fix=CASE_FIX, fillers=FILLERS,
                   maxw=MAXW, capw=CAPW, mint=MINT, maxt=MAXT):
    """Caption cards for a whole video.

    words    transcript in master time: [{"w","s","e","p"}, ...]
    cuts     [(master_in, master_out), ...] in playback order
    seg_map  master time -> video time (None if the instant is not in the video)
    widths   Widths instance for the caption font
    cont     master starts of cuts that only removed a silence: the line goes on
    joins    master starts of cuts that join one sentence: the line goes on
    Any other cut closes the line (a camera cut must never carry a caption over).

    Returns [{"start", "dur", "words": [(text, t_in, t_out), ...]}, ...] in video time.
    """
    joins = {round(t, 2) for t in joins}
    cont = {round(t, 3) for t in cont}
    bucket = assign_words(words, cuts, drop=drop, fillers=fillers)
    bucket = clean_disfluencies(bucket, text_fix=text_fix)
    bucket = fix_case(bucket, case_fix=case_fix)

    groups, run = [], []
    for (i0, i1), ws in zip(cuts, bucket):
        if run and round(i0, 2) not in joins and round(i0, 3) not in cont:
            groups.extend(group_words(run, widths, maxw, capw, mint, maxt))
            run = []
        run.extend(ws)
    if run:
        groups.extend(group_words(run, widths, maxw, capw, mint, maxt))

    out = []
    for g in groups:
        ws = []
        for w in g:
            a, b = seg_map(w["s"]), seg_map(w["e"])
            if a is None or b is None:
                continue
            ws.append((w["w"], a, b))
        if not ws:
            continue
        start = ws[0][1]
        end = max(ws[-1][2], start + 0.7)
        out.append(dict(start=start, dur=end - start, words=ws))
    out.sort(key=lambda g: g["start"])
    # overlaps: the earlier card gives way down to `mint`; the rest is eaten by the next
    for k in range(len(out) - 1):
        over = (out[k]["start"] + out[k]["dur"]) - out[k + 1]["start"]
        if over > 0:
            room = out[k]["dur"] - mint
            take = min(over + 0.02, max(0.0, room))
            out[k]["dur"] -= take
            rest = (out[k]["start"] + out[k]["dur"]) - out[k + 1]["start"]
            if rest > 0:
                out[k + 1]["start"] += rest
                out[k + 1]["dur"] = max(mint, out[k + 1]["dur"] - rest)
    return out


# ------------------------------------------------------------- reading a page
CARD_RE = re.compile(r'<div id="cap-\d+" class="clip cap" data-start="([\d.]+)"[^>]*>(.*?)</div>')
WORD_RE = re.compile(r'<span id="c\d+-\d+" class="w[^"]*">(.*?)</span>')


def cards_from_html(path):
    page = pathlib.Path(path).read_text(encoding="utf-8")
    cards = []
    for m in CARD_RE.finditer(page):
        ws = [_html.unescape(x) for x in WORD_RE.findall(m.group(2))]
        cards.append((float(m.group(1)), ws))
    return cards


def text_report(path, widths=None):
    """Full caption text of a project, one card per line, with the flags a human
    should look at before delivering: lowercase after a period, repeated words,
    fillers, crutches, words without a measured width."""
    cards = cards_from_html(path)
    if not cards:
        print("no caption cards found in %s" % path)
        return 2
    norm = lambda t: re.sub(r"[^a-z0-9']", "", t.lower())
    flat = [(t, w) for t, ws in cards for w in ws]
    flags = []
    prev = "."
    for i, (t, w) in enumerate(flat):
        if prev[-1:] in ".?!" and w[:1].isalpha() and w[:1].islower():
            flags.append((t, "lowercase after period", w))
        if i + 1 < len(flat) and norm(w) and norm(w) == norm(flat[i + 1][1]):
            flags.append((t, "repeated word", "%s %s" % (w, flat[i + 1][1])))
        if norm(w) in FILLERS:
            flags.append((t, "filler", w))
        if i + 1 < len(flat) and (norm(w), flat[i + 1][1].lower()) in {("you", "know,"), ("i", "mean,")}:
            flags.append((t, "crutch", "%s %s" % (w, flat[i + 1][1])))
        if widths and w not in widths.table:
            flags.append((t, "width not measured", w))
        prev = w
    print("%s — %d cards, %d words\n" % (path, len(cards), len(flat)))
    print(" | ".join(" ".join(ws) for _, ws in cards))
    print("\n%d flag(s)" % len(flags))
    for t, kind, w in flags:
        print("  %6.2fs  %-20s %s" % (t, kind, w))
    return 0


# ---------------------------------------------------------------- measuring
def measure(words, font, size=64, weight=600, letter_spacing="-.01em"):
    """Rendered width of each word in headless Chromium with `font` loaded.
    Needs node + puppeteer-core (the one HyperFrames installs under ~/.npm/_npx)
    and a Chromium headless shell (~/Library/Caches/ms-playwright)."""
    js = HERE / "measure_words.js"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "font.woff2").write_bytes(pathlib.Path(font).read_bytes())
        (tmp / "probe.html").write_text(
            '<!doctype html><meta charset="utf-8"><style>@font-face{font-family:"Probe";'
            'font-weight:%d;src:url("font.woff2") format("woff2")}#probe{position:absolute;'
            'visibility:hidden;white-space:pre;font-family:"Probe";font-weight:%d;'
            'font-size:%dpx;letter-spacing:%s}</style><div id="probe"></div>'
            % (weight, weight, size, letter_spacing))
        (tmp / "words.json").write_text(json.dumps(sorted(set(words))))
        r = subprocess.run(["node", str(js), str(tmp / "probe.html"), str(tmp / "words.json")],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("measure_words.js failed:\n" + r.stderr[-1500:])
        return json.loads(r.stdout)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("text", help="full caption text of a project + flags")
    t.add_argument("html")
    t.add_argument("--widths")
    m = sub.add_parser("measure", help="measure words missing from a widths JSON and add them")
    m.add_argument("--widths", required=True)
    m.add_argument("--font", required=True, help="woff2 of the caption font (the exact weight)")
    m.add_argument("--from-html", help="take the words from a project's index.html")
    m.add_argument("--weight", type=int, default=600)
    m.add_argument("--size", type=int, default=64)
    m.add_argument("--letter-spacing", default="-.01em")
    m.add_argument("words", nargs="*")
    m.add_argument("--control", help="word already in the table, re-measured as a check (default: the first one in the table)")
    m.add_argument("--space", action="store_true", help="(re)measure the width of a space too (new font)")
    a = ap.parse_args()

    if a.cmd == "text":
        sys.exit(text_report(a.html, Widths(a.widths) if a.widths else None))

    wt = Widths(a.widths)
    if a.space:
        got = measure(["a a", "a"], a.font, a.size, a.weight, a.letter_spacing)
        d = json.loads(wt.path.read_text())
        d["size"], d["space"] = a.size, round(got["a a"] - 2 * got["a"], 2)
        wt.path.write_text(json.dumps(d, ensure_ascii=False))
        print("space = %.2f px at %d px" % (d["space"], a.size))
        wt = Widths(a.widths)
    words = list(a.words)
    if a.from_html:
        words += [w for _, ws in cards_from_html(a.from_html) for w in ws]
    todo = wt.missing(words)
    if not a.control and wt.table:
        a.control = "DNA" if "DNA" in wt.table else next(iter(wt.table))
    probe = todo + ([a.control] if a.control in wt.table else [])
    if not todo:
        print("all %d words already measured" % len(set(words)))
        return
    if not a.control or a.control not in wt.table:
        print("empty table (new font): measuring without a control word; measure --space too")
    got = measure(probe, a.font, a.size, a.weight, a.letter_spacing)
    if a.control in wt.table:
        ok = abs(got[a.control] - wt.table[a.control]) < 0.5
        print("control %s: table %.2f, measured %.2f -> %s" % (
            a.control, wt.table[a.control], got[a.control], "OK" if ok else "MISMATCH, not saved"))
        if not ok:
            sys.exit(2)
    d = json.loads(wt.path.read_text())
    for w in todo:
        d["w"][w] = round(got[w], 2)
    wt.path.write_text(json.dumps(d, ensure_ascii=False))
    print("added %d width(s): %s" % (len(todo), ", ".join("%s=%.2f" % (w, got[w]) for w in todo)))


if __name__ == "__main__":
    main()
