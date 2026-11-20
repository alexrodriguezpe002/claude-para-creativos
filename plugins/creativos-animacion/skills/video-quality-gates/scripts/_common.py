"""Shared parsing for the HyperFrames quality gates.

Every gate reads the same three things: the composition root, the beats, and the
caption array. Parsing lives here so a change to the project shape is a one-file
fix. Deliberately regex-based — these compositions are hand-written, single-file
and small, and a real HTML parser would still not resolve the CSS cascade.
"""

import json
import os
import re
import sys

import _platform as P   # noqa: F401 — UTF-8 console and the Windows PATH, for every gate
import _profile
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)

# The client profile of the project being measured. Set by project_dir(); every
# parser below reads the beat id pattern from it, so a client whose containers
# are named differently is parsed without a branch in any gate. The import-time
# value is a placeholder (strict=False): project_dir() is where a project with
# no profile stops.
PROFILE = _profile.load(".", strict=False)

GREEN = "\033[32m"
RED = "\033[31m"
YEL = "\033[33m"
DIM = "\033[90m"
OFF = "\033[0m"


class Result(object):
    """Collects findings for one gate and prints a machine-readable verdict."""

    def __init__(self, gate, project):
        self.gate = gate
        self.project = project
        self.fails = []
        self.warns = []
        self.notes = []

    def fail(self, code, msg, evidence=None):
        self.fails.append({"code": code, "msg": msg, "evidence": evidence})

    def warn(self, code, msg, evidence=None):
        self.warns.append({"code": code, "msg": msg, "evidence": evidence})

    def note(self, msg):
        self.notes.append(msg)

    def emit(self):
        name = os.path.basename(self.project.rstrip("/\\"))
        status = "FAIL" if self.fails else ("WARN" if self.warns else "PASS")
        color = RED if self.fails else (YEL if self.warns else GREEN)
        print("%s%s %s%s  %s" % (color, status, self.gate, OFF, name))
        # a number this computer learned from its user is in force: say so, every time
        for line in _profile.learned_lines(PROFILE, self.gate):
            print("  " + line)
        for f in self.fails:
            print("  %sFAIL%s [%s] %s" % (RED, OFF, f["code"], f["msg"]))
            if f["evidence"]:
                print("       %s%s%s" % (DIM, f["evidence"], OFF))
        for w in self.warns:
            print("  %sWARN%s [%s] %s" % (YEL, OFF, w["code"], w["msg"]))
            if w["evidence"]:
                print("       %s%s%s" % (DIM, w["evidence"], OFF))
        for n in self.notes:
            print("  %s· %s%s" % (DIM, n, OFF))
        if os.environ.get("GATES_JSON"):
            print("##JSON## " + json.dumps({
                "gate": self.gate, "project": name, "status": status,
                "fails": self.fails, "warns": self.warns,
            }))
        return 1 if self.fails else 0


def project_dir(argv):
    global PROFILE
    d = argv[1] if len(argv) > 1 else "."
    if not os.path.isfile(os.path.join(d, "index.html")):
        sys.stderr.write("no index.html in %s\n" % d)
        sys.exit(2)
    d = os.path.abspath(d)
    PROFILE = _profile.load(d)
    return d


def beat_id_re():
    """The beat container id pattern of the current profile, as a group-free regex."""
    return PROFILE.get("beat_id") or r"beat-[\w-]+"


def read_html(d):
    with open(os.path.join(d, "index.html"), encoding="utf-8", errors="replace") as fh:
        return fh.read()


def read_transcript(d, tokens=None):
    """Whisper words as [{'t': word, 's': start, 'e': end}], or [].

    `tokens=True` asks for whisper.cpp's own token times even when the client's profile does
    not (the profile's `transcript_tokens` decides when it is None): a gate that has to say
    which side of a cut a word is on cannot use the even spread over a segment.

    Two shapes turn up in these projects:
      * a flat list of {"text","start","end"} — one entry per word
      * whisper.cpp's {"transcription":[{"timestamps":{...},"text":...}]} —
        one entry per segment, which we split into words
    """
    p = os.path.join(d, "transcript.json")
    if not os.path.isfile(p):
        return []
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            raw = json.load(fh)
    except Exception:
        return []

    if isinstance(raw, list) and raw and isinstance(raw[0], dict) and "text" in raw[0]:
        return [{"t": w.get("text", "").strip(),
                 "s": _sec(w.get("start")), "e": _sec(w.get("end"))}
                for w in raw if str(w.get("text", "")).strip()]

    segs = None
    if isinstance(raw, dict):
        segs = raw.get("transcription") or raw.get("segments")
    if not segs:
        return []

    # whisper.cpp also writes every token with its own time; a client profile can
    # ask for those instead of spreading each segment evenly over its words —
    # the even spread puts words on the wrong side of a beat boundary
    if (PROFILE.get("transcript_tokens") if tokens is None else tokens) \
            and any(isinstance(sg, dict) and sg.get("tokens") for sg in segs):
        words = []
        for seg in segs:
            for tok in (seg.get("tokens") or []):
                text = tok.get("text", "")
                if not text or text.strip().startswith("[_"):
                    continue
                off = tok.get("offsets") or {}
                ts, te = off.get("from"), off.get("to")
                ts = ts / 1000.0 if ts is not None else None
                te = te / 1000.0 if te is not None else None
                if text.startswith(" ") or not words:
                    words.append({"t": text.strip(), "s": ts, "e": te})
                else:
                    words[-1]["t"] += text.strip()
                    words[-1]["e"] = te
        return [w for w in words if w["t"]]

    words = []
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        ts = seg.get("timestamps") or {}
        off = seg.get("offsets") or {}
        start = seg.get("start")
        if start is None:
            start = ts.get("from")
        if start is None and "from" in off:
            start = off["from"] / 1000.0
        end = seg.get("end")
        if end is None:
            end = ts.get("to")
        if end is None and "to" in off:
            end = off["to"] / 1000.0
        s, e = _sec(start), _sec(end)
        toks = [t for t in str(seg.get("text", "")).split() if t]
        if not toks:
            continue
        step = ((e - s) / len(toks)) if (s is not None and e is not None) else None
        for i, t in enumerate(toks):
            words.append({
                "t": t,
                "s": (s + i * step) if step is not None else None,
                "e": (s + (i + 1) * step) if step is not None else None,
            })
    return words


def _sec(v):
    """Whisper writes seconds as a float or 'HH:MM:SS,mmm'."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.match(r"(\d+):(\d+):(\d+)[.,](\d+)", str(v))
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000.0
    try:
        return float(v)
    except ValueError:
        return None


def root(html):
    """{'duration', 'width', 'height', 'portrait'} of the composition root."""
    m = re.search(r'id="root"[^>]*', html)
    tag = m.group(0) if m else ""
    def attr(n, default):
        mm = re.search(n + r'="([\d.]+)"', tag)
        return float(mm.group(1)) if mm else default
    w = attr("data-width", 1080.0)
    h = attr("data-height", 1920.0)
    return {"duration": attr("data-duration", 0.0), "width": w, "height": h,
            "portrait": h >= w}


def beats(html):
    """Every graphic beat, in document order.

    Returns dicts with id, start, duration, end, the device name from the
    preceding HTML comment, and the beat's own inner markup.

    Every container that matches the profile's beat id counts, whether or not a
    device comment sits in front of it — a project that comments some beats and
    not others used to lose the uncommented ones without a word.
    """
    out = []
    cont = re.compile(r'<div[^>]*\bid="(' + beat_id_re() + r')"[^>]*'
                      r'data-start="([\d.]+)"[^>]*data-duration="([\d.]+)"', re.S)
    for m in cont.finditer(html):
        before = html[max(0, m.start() - 4000):m.start()]
        cm = re.search(r"<!--((?:(?!-->).)*)-->\s*$", before, re.S)
        comment = cm.group(1) if cm else ""
        start, dur = float(m.group(2)), float(m.group(3))
        out.append({"id": m.group(1), "start": start, "duration": dur,
                    "end": start + dur, "device": _device(comment),
                    "comment": comment, "html": _inner(html, m.start())})
    vis = visible_windows(html)
    for b in out:
        w = vis.get(b["id"], {})
        b["visible_start"] = w.get("visible_start", b["start"])
        b["visible_end"] = w.get("visible_end", b["end"])
    return out


def _vis_re():
    """A visibility event on a beat container: set/to/from of opacity or autoAlpha."""
    return re.compile(
        r"tl\.(set|to|from)\(\s*[\"'`]#(" + beat_id_re() + r")[\"'`]\s*,\s*"
        r"(\{[^}]*(?:opacity|autoAlpha):\s*([01])(?:\.0+)?(?![\d.])[^}]*\})\s*,\s*([^)]+)\)")


def _vis_fromto_re():
    """tl.fromTo on a beat container: both the from and the to object are captured.

    CLD's segments enter with `tl.fromTo("#seg1", {autoAlpha: 0}, {autoAlpha: 1,
    duration: 0.32}, T1)` and declare data-start=0 over the whole video, so a
    reader that only knew set/to/from placed the segment on screen from 0.
    """
    return re.compile(
        r"tl\.fromTo\(\s*[\"'`]#(" + beat_id_re() + r")[\"'`]\s*,\s*"
        r"(\{[^}]*\})\s*,\s*(\{[^}]*\})\s*,\s*([^)]+)\)")


# The declaration keyword is optional on purpose: `const B1S = X, B1E = Y;`
# declares two times and only the first carries `const`. Requiring the keyword
# made the second one invisible, and the gate then measured the wrong frame.
_CONST_RE = re.compile(
    r"(?:const|let|var)?\s*\b([A-Za-z_]\w*)\s*=\s*(-?\d+(?:\.\d+)?)\s*(?=[,;])")


def strip_comments(src):
    """JS with its comments removed, string literals intact.

    Comments are not inert: `// B1_EXIT + B1_OUT_DUR = B1E` reads as a second
    assignment of B1_OUT_DUR, so `const_table` dropped the symbol as ambiguous
    and every duration that referenced it resolved to nothing.
    """
    out, i, n, quote = [], 0, len(src), None
    while i < n:
        ch = src[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def script_text(html):
    """Every <script> body, comments stripped — the one place gates parse from.

    Chained timelines (`tl.from(...)\n  .to(...)\n  .set(...)`) are written out as
    one `tl.<method>(...)` call per line, so every gate reads them the same way
    it reads unchained ones. Positions in these projects are absolute, so the
    rewrite does not change a single time.
    """
    return unchain(strip_comments("\n".join(
        re.findall(r"<script[^>]*>(.*?)</script>", html, re.S))))


_CHAIN_HEAD_RE = re.compile(r"\btl\s*\.\s*(set|to|from|fromTo)\s*\(")
_CHAIN_LINK_RE = re.compile(r"\)\s*\n\s*\.\s*(set|to|from|fromTo)\s*\(")


def unchain(src):
    src = _CHAIN_HEAD_RE.sub(lambda m: "tl.%s(" % m.group(1), src)
    prev = None
    while prev != src:
        prev = src
        src = _CHAIN_LINK_RE.sub(lambda m: ");\ntl.%s(" % m.group(1), src)
    return src


def visible_windows(html):
    """When each beat actually becomes visible, from the timeline itself.

    `data-start` declares the clip's track window; the opacity set is what the
    viewer sees. They can disagree — and when they do, the timeline wins.
    """
    script = script_text(html)
    consts = _const_table(_CONST_RE, script)
    out = {}
    for m in _vis_re().finditer(script):
        kind, bid, obj, val, expr = (m.group(1), m.group(2), m.group(3),
                                     m.group(4), m.group(5).strip())
        t = _expr(expr, consts)
        if t is None:
            continue
        if kind == "from":
            # `from` animates from the value given toward the element's own:
            # from 0 is an entrance (visible from t), from 1 an exit.
            val = "1" if val == "0" else "0"
            if val == "0":
                dm = re.search(r"duration:\s*([A-Za-z_]\w*|[\d.]+)", obj)
                if dm:
                    dur = _expr(dm.group(1), consts)
                    if dur:
                        t += dur
        if kind == "to" and val == "0":
            # a fade-out is still visible until it finishes
            dm = re.search(r"duration:\s*([A-Za-z_]\w*|[\d.]+)", obj)
            if dm:
                dur = _expr(dm.group(1), consts)
                if dur:
                    t += dur
        w = out.setdefault(bid, {})
        key = "visible_start" if val == "1" else "visible_end"
        if key not in w or (key == "visible_start" and t < w[key]) or \
                (key == "visible_end" and t > w[key]):
            w[key] = t
    # fromTo: from 0 to 1 is an entrance at t; from 1 to 0 an exit, visible until
    # the tween ends. A fromTo that leaves the opacity alone says nothing here.
    for m in _vis_fromto_re().finditer(script):
        bid, frm, to, expr = m.group(1), m.group(2), m.group(3), m.group(4).strip()
        # 0 or 1 exactly (0.0, 1.00 too) — "0.5" is a dim, not an entrance or an exit
        a = re.search(r"(?:opacity|autoAlpha):\s*([01])(?:\.0+)?(?![\d.])", frm)
        b = re.search(r"(?:opacity|autoAlpha):\s*([01])(?:\.0+)?(?![\d.])", to)
        if not a or not b or a.group(1) == b.group(1):
            continue
        t = _expr(expr, consts)
        if t is None:
            continue
        if b.group(1) == "1":
            key = "visible_start"
        else:
            key = "visible_end"
            dm = re.search(r"duration:\s*([A-Za-z_]\w*|[\d.]+)", to)
            if dm:
                dur = _expr(dm.group(1), consts)
                if dur:
                    t += dur
        w = out.setdefault(bid, {})
        if key not in w or (key == "visible_start" and t < w[key]) or \
                (key == "visible_end" and t > w[key]):
            w[key] = t
    return out


def const_table(rx, script):
    """name -> value, but only when the file declares it once.

    Several projects redeclare EXIT_START per beat inside separate blocks. A
    symbol with two different values is unresolvable, and guessing produces
    confident wrong answers — so it is dropped.
    """
    seen = {}
    for m in rx.finditer(script):
        seen.setdefault(m.group(1), set()).add(float(m.group(2)))
    decls = {}
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*=[^=]", script):
        decls[m.group(1)] = decls.get(m.group(1), 0) + 1
    return {k: list(v)[0] for k, v in seen.items()
            if len(v) == 1 and decls.get(k, 0) <= 1}


_const_table = const_table


def _expr(text, consts):
    """A time written in the timeline: a number, a constant, or arithmetic on them.

    `E1 + D1 - 0.55` and `(D1 - 1.6) / 2` are ordinary in hand-written timelines;
    a reader that only took `a ± b` dropped every event written that way, and the
    exit and dead-air gates then measured a beat with half its events missing.
    Only + - * / and parentheses over numbers and known constants are accepted.
    """
    import ast
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except (SyntaxError, ValueError):
        return None

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.Num):                       # Python < 3.8
            return float(n.n)
        if isinstance(n, ast.Name):
            v = consts.get(n.id)
            if v is None:
                raise ValueError(n.id)
            return float(v)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            return a / b if b else None
        raise ValueError("unsupported")

    try:
        out = ev(tree)
    except (ValueError, TypeError, ZeroDivisionError):
        return None
    return out


def _device(comment):
    """Device name from a beat's leading comment, or ''.

    An explicit `device: <name>` wins. Without that, the documented shape
    `Beat 1 — device: …` used to hand back the word "device" itself (the first
    em dash matched first), which then read as unnamed.
    """
    dev = ""
    em = re.search(r"\bdevice\s*:\s*([A-Za-z][A-Za-z /\-]{1,40})", comment or "", re.I)
    if em:
        dev = em.group(1).strip().rstrip(":,.").lower()
        if dev:
            return dev
    # the em-dash shape ("Beat 3 — Chart annotation", CLB ep2's "==== SEG 3 — RED FLAG #3 —")
    # only right after the beat's own label: a comment that merely contains a dash
    # ("Single graphic segment (CLD ep1 — one animation per snippet)") is not a device name
    dm = re.search(r"(?:device:?\s*|(?i:^[\s=\-#*]*(?:beat|seg(?:ment)?)\s*#?\d+\s*)[—–]\s*)([A-Za-z][A-Za-z /\-]{2,40})",
                   comment or "")
    if dm:
        dev = dm.group(1).strip().rstrip(":,.").lower()
        if dev in ("device", "beat", "silhouette", "the"):
            dev = ""      # the literal keyword, not a device name
    return dev


def _inner(html, from_index):
    """Markup of one beat — from its opening div to the matching close."""
    m = re.compile(r'\bid="(?:' + beat_id_re() + r')"').search(html, from_index)
    if not m:
        return ""
    open_tag = html.rfind("<div", 0, m.start())
    depth, j = 0, open_tag
    while j < len(html):
        nxt_open = html.find("<div", j + 1)
        nxt_close = html.find("</div>", j + 1)
        if nxt_close < 0:
            break
        if 0 <= nxt_open < nxt_close:
            depth += 1
            j = nxt_open
        else:
            if depth == 0:
                return html[open_tag:nxt_close + 6]
            depth -= 1
            j = nxt_close
    return html[open_tag:]


CAP_RE = re.compile(
    r"\{\s*start:\s*(-?[\d.]+)\s*,\s*end:\s*(-?[\d.]+)\s*,(.*?)\]\s*\}",
    re.S,
)
WORD_RE = re.compile(r'(?:^|[,\[{\s])[tw]\s*:\s*"((?:[^"\\]|\\.)*)"')
# the same key written with single quotes — one client's arrays mix both
WORD_RE_SQ = re.compile(r"(?:^|[,\[{\s])[tw]\s*:\s*'((?:[^'\\]|\\.)*)'")
EMPH_RE = re.compile(r'\be\s*:\s*true')


def _words(body):
    """Caption words from one group's `words: [...]` body, either quote style."""
    found = [(m.start(), m.group(1).replace('\\"', '"')) for m in WORD_RE.finditer(body)]
    found += [(m.start(), m.group(1).replace("\\'", "'")) for m in WORD_RE_SQ.finditer(body)]
    return [w for _, w in sorted(found)]


def js_block(src, start_index):
    """Substring of the balanced {...} body that follows start_index."""
    i = src.find("{", start_index)
    if i < 0:
        return ""
    depth, j = 0, i
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1
    return src[i:]


def js_call_args(src, paren_index):
    """Top-level arguments of the call whose "(" sits at paren_index."""
    if paren_index >= len(src) or src[paren_index] != "(":
        return []
    depth, i, start, args = 0, paren_index, paren_index + 1, []
    quote = None
    while i < len(src):
        ch = src[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                args.append(src[start:i])
                return args
        elif ch == "," and depth == 1:
            args.append(src[start:i])
            start = i + 1
        i += 1
    return args


def caption_bind_blocks(html):
    """The forEach bodies that put caption groups on the timeline.

    Identified by content, not by variable name — several projects call their
    loop variable `sel`, and so do the beat-exit loops.
    """
    out = []
    for m in re.finditer(r"\.forEach\s*\(", html):
        body = js_block(html, m.end())
        if not body:
            continue
        if ("autoAlpha" in body or "visibility" in body) and (
                "cap" in body.lower() or "cg" in body or "group" in body.lower()):
            out.append(body)
    return out


PLAIN_CAP_RE = re.compile(
    r'\{\s*text:\s*"((?:[^"\\]|\\.)*)"\s*,\s*start:\s*(-?[\d.]+)\s*,\s*end:\s*(-?[\d.]+)',
    re.S,
)


def captions(html):
    """[{'start','end','words':[str],'emph':int,'text':str}] in order.

    Three array shapes exist across CLA projects — per-word objects, per-word
    objects with extra keys, and a plain {text,start,end}. All three parse here;
    new builds should use the first.
    """
    out = []
    for m in CAP_RE.finditer(html):
        body = m.group(3)
        words = _words(body)
        if not words and re.search(r"\bwords\s*:\s*\[", body):
            # words as plain strings — `words:["IF","YOU'RE"]`, CLC ep1's delivered arrays (2026-08-31)
            words = [a.replace('\\"', '"') or b.replace("\\'", "'") for a, b in
                     re.findall(r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'', body.split("[", 1)[-1])]
            words = [w for w in words if w]
        if not words:
            continue
        out.append({
            "start": float(m.group(1)), "end": float(m.group(2)),
            "words": words, "emph": len(EMPH_RE.findall(body)),
            "text": " ".join(words),
        })
    expr = _expr_captions(html)
    if len(expr) > len(out):
        out = expr
    if out:
        return out
    out = _id_captions(html)
    if out:
        return out
    for m in PLAIN_CAP_RE.finditer(html):
        text = m.group(1).replace('\\"', '"')
        out.append({
            "start": float(m.group(2)), "end": float(m.group(3)),
            "words": text.split(), "emph": 0, "text": text,
        })
    return out


_CAP_HEAD_RE = re.compile(r"\{\s*start\s*:\s*([^,{}\n]+?)\s*,\s*end\s*:\s*([^,{}\n]+?)\s*,")
_WORDS_KEY_RE = re.compile(r"\bwords\s*:\s*\[")


def _expr_captions(html):
    """Caption groups whose times are written as expressions.

    One client writes `start: 0.070 - ONSET` — the Whisper time minus a
    calibrated onset — and the literal-number parser above reads zero groups
    from those files, which turns every caption rule into a silent pass. The
    expression is resolved against the file's own constants; a group whose time
    cannot be resolved is left out rather than guessed.
    """
    script = script_text(html)
    consts = const_table(_CONST_RE, script)
    out = []
    for m in _CAP_HEAD_RE.finditer(script):
        s0, e0 = _expr(m.group(1), consts), _expr(m.group(2), consts)
        if s0 is None or e0 is None:
            continue
        wm = _WORDS_KEY_RE.search(script, m.end(), m.end() + 600)
        if not wm:
            continue
        i = wm.end() - 1
        depth, j = 0, i
        while j < len(script):
            if script[j] == "[":
                depth += 1
            elif script[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = script[i + 1:j]
        words = _words(body)
        if not words:
            continue
        out.append({"start": s0, "end": e0, "words": words,
                    "emph": len(EMPH_RE.findall(body)), "text": " ".join(words)})
    if out:
        return out
    return _ts_captions(script, consts)


_HELPER_RE = re.compile(
    r"(?:const|let|var)\s+(\w+)\s*=\s*\(?\s*(\w+)\s*\)?\s*=>\s*"
    r"(?:Math\.max\(\s*0\s*,\s*\2\s*-\s*(\w+|[\d.]+)\s*\)|\2\s*-\s*(\w+|[\d.]+))")
_TS_GROUP_RE = re.compile(r"\{[^{}]*?\bend\s*:\s*([\w.]+(?:\s*[+\-]\s*[\w.]+)?)\s*,[^{}]*?\bwords\s*:\s*\[")
_TS_KEY_RE = re.compile(r"\bts\s*:\s*\[\s*([^,\]]+)")


def _ts_captions(script, consts):
    """Groups whose start is derived at runtime from their first word's time.

    Shape: `{ end: 0.96, words: [...], ts: [os(0.08), ...] }` plus a one-line
    helper `const os = (t) => Math.max(0, t - ONSET)`. Only that helper form is
    resolved; anything else is left out rather than guessed. A runtime clamp of
    `end` (some files trim each end to the next start in JS) is not visible here.
    """
    helpers = {}
    for m in _HELPER_RE.finditer(script):
        off = _expr(m.group(3) or m.group(4), consts)
        if off is not None:
            helpers[m.group(1)] = (off, bool(m.group(3)))
    out = []
    for m in _TS_GROUP_RE.finditer(script):
        e0 = _expr(m.group(1), consts)
        if e0 is None:
            continue
        i = m.end() - 1
        depth, j = 0, i
        while j < len(script):
            if script[j] == "[":
                depth += 1
            elif script[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        words = _words(script[i + 1:j])
        tm = _TS_KEY_RE.search(script, j, j + 200)
        if not words or not tm:
            continue
        first = tm.group(1).strip()
        hm = re.match(r"(\w+)\(\s*([\d.]+)\s*\)$", first)
        if hm and hm.group(1) in helpers:
            off, clamp = helpers[hm.group(1)]
            s0 = float(hm.group(2)) - off
            s0 = max(0.0, s0) if clamp else s0
        else:
            s0 = _expr(first, consts)
        if s0 is None:
            continue
        out.append({"start": s0, "end": e0, "words": words, "emph": 0,
                    "text": " ".join(words)})
    return out


# `emphasis:` and `mode:` may sit between `end` and `words` (CLD's teaser writes
# `{id, start, end, emphasis: false, mode: "line", words: [...]}`)
ID_CAP_RE = re.compile(
    r"\{\s*id:\s*[\"'`]([\w-]+)[\"'`]\s*,\s*start:\s*(-?[\d.]+)\s*,\s*end:\s*(-?[\d.]+)\s*,"
    r"(?:\s*(?:emphasis|mode)\s*:\s*[^,\[\]{}]+,)*"
    r"\s*words:\s*\[(.*?)\]\s*\}",
    re.S,
)
ID_WORD_RE = re.compile(r"id:\s*[\"'`]([\w-]+)[\"'`]")


def _id_captions(html):
    """The shape where the array holds ids and the words live in the markup.

    CLD ships this: `{id:"cap-g0", start, end, words:[{id:"cap-g0-w0", start}]}`
    with the text inside pre-rendered spans. Without resolving the ids the gate
    reports `no-captions` and every caption rule silently does nothing.
    """
    # `\sid="` and not just `id="`: every element also carries `data-hf-id`,
    # and a greedy match binds the span's text to that one instead.
    texts = dict(re.findall(r'\sid="([\w-]+)"\s*>([^<]*)<', html))
    out = []
    for m in ID_CAP_RE.finditer(html):
        words = [texts.get(w, "").strip() for w in ID_WORD_RE.findall(m.group(4))]
        words = [w for w in words if w]
        if not words:
            continue
        out.append({
            "start": float(m.group(2)), "end": float(m.group(3)),
            "words": words, "emph": 0, "text": " ".join(words),
        })
    return out


# `font: 900 124px/0.98 Family` — the size is the first length of the shorthand
# (the weight is a bare number, the line height follows a slash)
_FONT_SHORT_RE = re.compile(r"(?<![-\w])font\s*:\s*[^;{}\"']*?(?<![\w.])(\d+(?:\.\d+)?)px\b")


def _font_shorthand(decls):
    return _FONT_SHORT_RE.search(decls)


def css_sizes(html):
    """{'.class': font_size_px} from the <style> block."""
    sizes = {}
    style = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", style):
        fs = re.search(r"font-size:\s*(\d+(?:\.\d+)?)px", m.group(2)) or _font_shorthand(m.group(2))
        if not fs:
            continue
        for sel in m.group(1).split(","):
            sel = sel.strip()
            if sel:
                sizes[sel] = float(fs.group(1))
    return sizes


TAG_RE = re.compile(r"<(/?)([a-zA-Z][\w-]*)([^>]*?)(/?)>", re.S)
VOID = {"br", "img", "input", "hr", "meta", "link", "use", "circle", "rect",
        "path", "line", "polyline", "polygon", "ellipse", "stop", "source"}


def _declared_size(attrs, sizes):
    """font-size for one open tag: inline first, then any matching CSS rule."""
    inline = re.search(r"font-size:\s*(\d+(?:\.\d+)?)px", attrs) or _font_shorthand(attrs)
    if inline:
        return float(inline.group(1))
    keys = []
    cm = re.search(r'class="([^"]*)"', attrs)
    if cm:
        keys += ["." + c for c in cm.group(1).split()]
    im = re.search(r'id="([^"]*)"', attrs)
    if im:
        keys.append("#" + im.group(1))
    best = None
    for sel, px in sizes.items():
        last = sel.strip().split()[-1] if sel.strip() else ""
        for k in keys:
            # ".row-label" matches ".row-label" and "#beat-1 .row-label"
            if last == k or last.startswith(k + ".") or last.endswith(k):
                best = px if best is None else max(best, px)
    return best


def text_elements(fragment, sizes):
    """Leaf text nodes with an inherited, resolved font-size.

    Walks the fragment with a tag stack so a <span> inside a sized .headline
    reports the headline's size instead of nothing.
    """
    out = []
    fragment = re.sub(r"<!--.*?-->", "", fragment, flags=re.S)
    stack = []          # [(tag, size_or_None, classes, id)]
    pos = 0
    for m in TAG_RE.finditer(fragment):
        text = fragment[pos:m.start()]
        pos = m.end()
        clean = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean and stack:
            size = None
            for entry in reversed(stack):
                sz = entry[1]
                if sz is not None:
                    size = sz
                    break
            out.append({"text": clean, "size": size,
                        "classes": stack[-1][2], "id": stack[-1][3],
                        "chain": [c for entry in stack for c in entry[2]]})
        closing, name, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if name in ("script", "style"):
            end = fragment.find("</" + name, m.end())
            pos = end if end > 0 else len(fragment)
            continue
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == name:
                    del stack[i:]
                    break
        elif not selfclose and name not in VOID:
            cm = re.search(r'class="([^"]*)"', attrs)
            im = re.search(r'id="([^"]*)"', attrs)
            stack.append((name, _declared_size(attrs, sizes),
                          cm.group(1).split() if cm else [],
                          im.group(1) if im else ""))
    return out


def outro_start(html):
    """Where the brand's fixed end card starts (seconds), or None.

    The profile's `outro.id_re` names the card's element ids ("outro" matches
    <video id="outro"> and <audio id="outro-audio"> with `outro(?:-audio)?`). The
    card is appended after the speech, so every check that asks "how long until
    the video ends" has to ask about the speech, not about the card.
    """
    spec = PROFILE.get("outro") or {}
    rx = spec.get("id_re")
    if not rx:
        return None
    starts = []
    for m in re.finditer(r"<[a-zA-Z][^>]*>", html):
        tag = m.group(0)
        if not re.search(r'(?<![\w-])id="(?:%s)"' % rx, tag):
            continue
        sm = re.search(r'(?<![\w-])data-start="([\d.]+)"', tag)
        if sm:
            starts.append(float(sm.group(1)))
    return min(starts) if starts else None


def speech_end(html, duration):
    """The end of the speech: where the outro card starts, else the composition's end."""
    o = outro_start(html)
    if o is not None and 0 < o < (duration or 1e9) + 0.01:
        return o
    return duration


VIDEO_SRC_RE = re.compile(r"<video[^>]*src=\"([^\"]+)\"")


def video_path(d, html=None):
    """Absolute path of the a-roll the composition plays, or None.

    The `src` is relative to index.html and often URL-encoded (`CLA%20067…`).
    """
    if html is None:
        html = read_html(d)
    m = re.search(r'id="a-roll"[^>]*src="([^"]+)"', html) or VIDEO_SRC_RE.search(html)
    if not m:
        return None
    src = m.group(1)
    if src.startswith(("http:", "https:", "data:")):
        return None
    try:
        from urllib.parse import unquote
        src = unquote(src)
    except Exception:
        pass
    p = src if os.path.isabs(src) else os.path.join(d, src)
    return p if os.path.isfile(p) else None


# The arrays that hold caption cards. Named, not guessed: a broader pattern would
# also swallow a beat's own data array and hide a layout change from the hash.
_CAP_ARRAY_RE = re.compile(
    r"\b(?:const|let|var)\s+(?:CAPTIONS|CAPTION_GROUPS|CAP_GROUPS|CAPS|GROUPS)\s*=\s*\[")


def layout_hash(html):
    """A fingerprint of everything that can move pixels on a beat's resting frame.

    Left out: the caption arrays (a caption edit cannot change a beat's balance)
    and the `data-hf-id` attributes the Studio stamps on its own. `run_gates.py
    --fast` compares it with the last balance measurement and re-measures when it
    changed — taking one element out of a beat is a balance change too.
    """
    import hashlib
    src = re.sub(r'\sdata-hf-id="[^"]*"', "", html)
    parts, i = [], 0
    for m in _CAP_ARRAY_RE.finditer(src):
        if m.start() < i:
            continue
        parts.append(src[i:m.end() - 1])
        depth, j = 0, m.end() - 1
        while j < len(src):
            if src[j] == "[":
                depth += 1
            elif src[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1
    parts.append(src[i:])
    return hashlib.sha1("".join(parts).encode("utf-8", "replace")).hexdigest()[:16]


BALANCE_STATE = os.path.join(".gates-cache", "balance-state.json")


def balance_state(d):
    """The last balance measurement of a project: {layout, status, when, frames}, or None."""
    try:
        with open(os.path.join(d, BALANCE_STATE), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


CUT_SCENE_THRESHOLD = 0.35     # the default; calibrated on CLA ep4: every hit was a speaker change
CUT_MERGE_TOL = 0.05           # a listed cut and a detected one this close are the same cut


def read_cut_list(d):
    """The project's own cuts.txt: (times, unreadable_lines), or (None, 0) without one.

    One time per line, in seconds (`podcast-beat-plan` step 2b writes it) or as
    HH:MM:SS.mmm; `#` starts a comment. A line that is not a time is counted,
    never silently skipped.
    """
    p = os.path.join(d, "cuts.txt")
    if not os.path.isfile(p):
        return None, 0
    times, bad = [], 0
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None, 0
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        v = _sec(line.replace("pts_time:", "").split()[0])
        if v is None:
            bad += 1
        else:
            times.append(v)
    return sorted(times), bad


def detect_cuts(d, html=None, threshold=None):
    """Scene-detected cuts of the a-roll in seconds, or None when it cannot be read.

    Cached per threshold and per video (size + mtime), because `scene-detect` over
    a 130 MB clip costs ~2s and the gates run after every edit. The cache of the
    old shape (`cuts.json`, a bare list with no threshold or video) is ignored: it
    could not tell a re-rendered video or another threshold apart.
    """
    if threshold is None:
        threshold = float((PROFILE.get("cuts") or {}).get("scene_threshold", CUT_SCENE_THRESHOLD))
    video = video_path(d, html)
    if not video:
        return None
    st = os.stat(video)
    key = {"video": os.path.basename(video), "size": st.st_size,
           "mtime": round(st.st_mtime, 3), "threshold": threshold}
    cache = os.path.join(d, ".gates-cache", "cuts-scene-%s.json" % ("%g" % threshold))
    if os.path.isfile(cache):
        try:
            with open(cache, encoding="utf-8") as fh:
                data = json.load(fh)
            if all(data.get(k) == v for k, v in key.items()):
                return data["cuts"]
        except Exception:
            pass
    import subprocess
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video,
             "-vf", "select='gt(scene,%s)',metadata=print:file=-" % threshold,
             "-an", "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    cuts = sorted(float(t) for t in re.findall(r"pts_time:([\d.]+)", out))
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(dict(key, cuts=cuts), fh)
    except OSError:
        pass
    return cuts


def cut_info(d, html=None):
    """Camera cuts from both sources, merged, and where each one came from.

    A cut is where the picture changes — a person on a multi-speaker show, a jump
    in one take on a single-speaker one. Scene detection sees the first and not
    the second (CLB jump cuts score 0.07–0.11 against CLA's 0.35), so the project's
    own cuts.txt is read too. Merged, not replaced: a stale or incomplete list
    never hides a cut the detector does see. Returns
    {"cuts", "listed", "listed_bad", "detected", "threshold", "require_list", "summary"};
    "cuts" is None only when neither source could be read.
    """
    cfg = PROFILE.get("cuts") or {}
    thr = float(cfg.get("scene_threshold", CUT_SCENE_THRESHOLD))
    listed, bad = read_cut_list(d)
    detected = detect_cuts(d, html, thr)
    merged = None
    if listed is not None or detected is not None:
        merged = list(listed or [])
        for t in detected or []:
            if not any(abs(t - x) <= CUT_MERGE_TOL for x in merged):
                merged.append(t)
        merged.sort()
    parts = ["cuts.txt: %d" % len(listed) if listed is not None else T("sin cuts.txt", "no cuts.txt")]
    if bad:
        parts[0] += T(" (+%d línea(s) ilegibles)", " (+%d unreadable line(s))") % bad
    parts.append("scene>%g: %s" % (thr, len(detected) if detected is not None else T("sin video", "no video")))
    return {"cuts": merged, "listed": listed, "listed_bad": bad, "detected": detected,
            "threshold": thr, "require_list": bool(cfg.get("require_list")),
            "summary": " · ".join(parts)}


def camera_cuts(d, html=None):
    """Camera cuts in seconds — cuts.txt and scene detection merged — or None
    when neither can be read. See cut_info() for where each one came from."""
    return cut_info(d, html)["cuts"]


# ── Is a cut the same shot? ───────────────────────────────────────────────────
#
# The editor, 2026-10-03 ("sí, para todos"): a caption card may cross a JUMP CUT of the
# same shot when splitting it there would leave a single dangling word or a flash;
# it never crosses a camera change or a change of speaker. "Same shot" has to be
# measured, because cuts.txt lists a jump cut inside one take and a speaker change
# alike. The picture decides: decode the frames on the two sides of the cut
# (96x96, gray, area-averaged) and ask how much of the frame did not change. A jump
# cut keeps the room, the camera and the person where they were — most pixels stay —
# and a camera or speaker change replaces the lot. Measured 2026-10-03:
#
#   jump cuts of one take (59: CLB ep2/ep3, CLE ep2 S1-S3)   static 0.38-0.95
#                                                           edge   0.47-1.00   mean 0.007-0.131
#   camera / speaker changes (11: CLA ep4, CLD ep1)         static 0.04-0.08
#                                                           edge   0.03-0.10   mean 0.248-0.455
#   the same clip with no cut (12 points, CLB ep3 S2)        static 0.80-0.97
#                                                           edge   0.90-0.99   mean 0.006-0.023
#
# static = share of pixels that changed by SHOT_LEVELS or less over the whole frame;
# edge = the same over the outer ring (left/right 18 %, top 12 % — the background,
# not the person); mean = mean absolute change / 255. The limits live in the client's
# profile (captions.cross_cut) and sit well inside that gap.

SHOT_SIZE = 96          # frames are compared as SHOT_SIZE x SHOT_SIZE gray
SHOT_HALF = 0.14        # seconds decoded on each side of a cut
SHOT_LEVELS = 8         # a pixel is "static" when it changed by this many levels of 255, or fewer
SHOT_VERSION = 1        # bump when the measure changes: old cache files are ignored


def _shot_ring():
    """Indices of the outer ring of the frame: left/right 18 % and the top 12 %."""
    n = SHOT_SIZE
    return [r * n + c for r in range(n) for c in range(n)
            if c < n * 0.18 or c >= n * (1 - 0.18) or r < n * 0.12]


def _balanced_sum(terms):
    """a+b+c+… as a balanced tree of parentheses: ffmpeg's expression parser gives up on a
    flat chain of a hundred terms (it nests one level per `+`)."""
    if len(terms) == 1:
        return terms[0]
    mid = len(terms) // 2
    return "(%s)+(%s)" % (_balanced_sum(terms[:mid]), _balanced_sum(terms[mid:]))


SHOT_BATCH = 300        # cut times per ffmpeg pass: a longer command line is not worth the risk on Windows


def _shot_frames(video, times):
    """[(pts, gray bytes)] of the frames within SHOT_HALF of each time, from one pass
    over the clip (a pass per SHOT_BATCH times) — or None when ffmpeg cannot read it."""
    if len(times) > SHOT_BATCH:
        out = []
        seen = set()
        for k in range(0, len(times), SHOT_BATCH):
            part = _shot_frames(video, times[k:k + SHOT_BATCH])
            if part is None:
                return None
            for f in part:
                if f[0] not in seen:        # the windows of two batches can share a frame
                    seen.add(f[0])
                    out.append(f)
        return sorted(out, key=lambda f: f[0])
    import subprocess
    expr = _balanced_sum(["between(t,%.4f,%.4f)" % (max(0.0, t - SHOT_HALF), t + SHOT_HALF) for t in times])
    base = ["ffmpeg", "-hide_banner", "-loglevel", "info", "-i", video,
            "-vf", "select='%s',showinfo,scale=%d:%d:flags=area,format=gray" % (expr, SHOT_SIZE, SHOT_SIZE)]
    tail = ["-an", "-f", "rawvideo", "-"]
    out = None
    # frames the select dropped must not be re-created to keep a constant rate: passthrough
    # (`-fps_mode` since ffmpeg 5.1, `-vsync 0` before)
    for opt in (["-fps_mode", "passthrough"], ["-vsync", "0"]):
        try:
            out = subprocess.run(base + opt + tail, capture_output=True, timeout=900)
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode == 0:
            break
    if out is None or out.returncode != 0:
        return None
    pts = [float(m) for m in re.findall(rb"showinfo[^\n]*?pts_time:\s*(-?[\d.]+)", out.stderr)]
    size = SHOT_SIZE * SHOT_SIZE
    n = len(out.stdout) // size
    if n == 0 or n != len(pts):
        return None
    return [(pts[i], out.stdout[i * size:(i + 1) * size]) for i in range(n)]


def _shot_metrics(a, b, ring):
    """static / edge_static / mean_diff between two gray frames of SHOT_SIZE x SHOT_SIZE."""
    diff = [abs(x - y) for x, y in zip(a, b)]
    tot = float(len(diff))
    rd = [diff[i] for i in ring]
    return {"static": sum(1 for v in diff if v <= SHOT_LEVELS) / tot,
            "edge_static": sum(1 for v in rd if v <= SHOT_LEVELS) / float(len(rd)),
            "mean_diff": sum(diff) / tot / 255.0}


def cut_shots(d, html, cuts):
    """How much of the picture survives each cut: {time: {static, edge_static, mean_diff, frames}}.

    The 2nd frame before the cut is compared with the 1st frame after it, so a cut
    time one frame off still straddles the edit. A cut with no frames on one side
    (the clip's first or last instant) maps to None. Returns None when there is no
    video to read or ffmpeg fails. Cached per video (name, size, mtime) in
    .gates-cache/cut-shots.json, one entry per cut time — only new times are decoded.
    """
    if not cuts:
        return {}
    video = video_path(d, html)
    if not video:
        return None
    st = os.stat(video)
    key = {"video": os.path.basename(video), "size": st.st_size, "mtime": round(st.st_mtime, 3),
           "n": SHOT_SIZE, "levels": SHOT_LEVELS, "half": SHOT_HALF, "v": SHOT_VERSION}
    cache = os.path.join(d, ".gates-cache", "cut-shots.json")
    store = {}
    try:
        with open(cache, encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("key") == key:
            store = data.get("cuts") or {}
    except (OSError, ValueError):
        pass
    todo = sorted(set(round(c, 3) for c in cuts if ("%.3f" % c) not in store))
    if todo:
        frames = _shot_frames(video, todo)
        if frames is None:
            return None
        ring = _shot_ring()
        for c in todo:
            before = [f for f in frames if c - SHOT_HALF <= f[0] < c - 0.004]
            after = [f for f in frames if c - 0.004 <= f[0] <= c + SHOT_HALF]
            if not before or not after:
                store["%.3f" % c] = None
                continue
            fb = before[-2] if len(before) >= 2 else before[-1]
            fa = after[1] if len(after) >= 2 else after[0]
            m = _shot_metrics(fb[1], fa[1], ring)
            m = {k: round(v, 4) for k, v in m.items()}
            m["frames"] = [round(fb[0], 3), round(fa[0], 3)]
            store["%.3f" % c] = m
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump({"key": key, "cuts": store}, fh)
        except OSError:
            pass
    return {c: store.get("%.3f" % round(c, 3)) for c in cuts}


def shot_selftest():
    """Does the same-shot measure work with this ffmpeg? Builds a 2.4 s clip of three 0.8 s shots —
    a grey room with a lighter block, the same room with the block somewhere else (a jump cut), and
    a colour test pattern (a camera change) — and measures the two cuts with the code the gates use.
    Returns (ok, text); a computer whose ffmpeg cannot do it keeps every cut a boundary."""
    import subprocess
    import tempfile
    cfg = (PROFILE.get("captions") or {}).get("cross_cut") or {}
    room = "color=c=0x383838:s=160x284:r=25:d=0.8,drawbox=x=%d:y=%d:w=50:h=120:c=0x909090:t=fill"
    with tempfile.TemporaryDirectory() as tmp:
        clip = os.path.join(tmp, "shots.mp4")
        try:
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", room % (30, 60), "-f", "lavfi", "-i", room % (80, 90),
                 "-f", "lavfi", "-i", "testsrc2=s=160x284:r=25:d=0.8",
                 "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
                 "-c:v", "mpeg4", "-q:v", "3", "-pix_fmt", "yuv420p", clip],
                capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as e:
            return False, T("ffmpeg no corre: %s", "ffmpeg does not run: %s") % e
        if r.returncode != 0 or not os.path.isfile(clip):
            return False, T("ffmpeg no armó el clip de prueba: %s", "ffmpeg did not build the test clip: %s") % (r.stderr or b"").decode("utf-8", "replace")[:160]
        frames = _shot_frames(clip, [0.8, 1.6])
        if not frames:
            return False, T("ffmpeg no devolvió los cuadros de los cortes (select/showinfo)", "ffmpeg did not return the frames around the cuts (select/showinfo)")
        ring = _shot_ring()
        got = []
        for c in (0.8, 1.6):
            before = [f for f in frames if c - SHOT_HALF <= f[0] < c - 0.004]
            after = [f for f in frames if c - 0.004 <= f[0] <= c + SHOT_HALF]
            if not before or not after:
                return False, T("faltan cuadros a un lado del corte de %.1f s", "frames missing on one side of the cut at %.1f s") % c
            got.append(_shot_metrics((before[-2] if len(before) > 1 else before[-1])[1],
                                     (after[1] if len(after) > 1 else after[0])[1], ring))

    def same(m):
        return (m["static"] >= float(cfg.get("static_min", 0.30)) and m["edge_static"] >= float(cfg.get("edge_static_min", 0.40))
                and m["mean_diff"] <= float(cfg.get("mean_diff_max", 0.20)))
    ok = same(got[0]) and not same(got[1])
    return ok, T("corte de salto: %s · cambio de cámara: %s%s", "jump cut: %s · camera change: %s%s") % (
        shot_evidence_text(got[0]), shot_evidence_text(got[1]), "" if ok else T(" — la lectura no es la esperada", " — not the expected reading"))


def shot_evidence_text(m):
    """The numbers of one cut, as the gates and the grouping print them."""
    return T("estático %.2f · borde %.2f · cambio medio %.3f", "static %.2f · edge %.2f · mean change %.3f") % (m["static"], m["edge_static"], m["mean_diff"])


def shot_limits_text(cfg):
    """The profile's three limits for "same shot", as the gates print them."""
    return T("estático ≥ %g, borde ≥ %g y cambio ≤ %g", "static ≥ %g, edge ≥ %g and change ≤ %g") % (
        float(cfg["static_min"]), float(cfg["edge_static_min"]), float(cfg["mean_diff_max"]))


def cut_kinds(d, html, cuts, ci=None):
    """Which cuts are a jump cut of the same shot: {time: {"same": bool, "why": str}}.

    Every cut is a boundary for a caption card; only a cut measured as the same shot
    (profile `captions.cross_cut`) is one a card may cross, and only for the reasons
    `check_captions.split_reasons` gives. A cut the scene detection lists at the profile's
    threshold is a camera change; `same_shot: false` in the profile makes every cut one.
    Returns None when the picture could not be read (then no card may cross anything).
    """
    cfg = (PROFILE.get("captions") or {}).get("cross_cut") or {}
    if not cuts:
        return {}
    if not cfg.get("same_shot"):
        return {c: {"same": False, "why": T("el perfil no deja cruzar cortes (captions.cross_cut.same_shot)", "the profile does not allow crossing cuts (captions.cross_cut.same_shot)")}
                for c in cuts}
    detected = (ci or {}).get("detected") or []
    thr = (ci or {}).get("threshold", CUT_SCENE_THRESHOLD)
    todo = [c for c in cuts if not any(abs(c - t) <= CUT_MERGE_TOL for t in detected)]
    meas = cut_shots(d, html, todo) if todo else {}
    if meas is None:
        return None
    out = {}
    for c in cuts:
        if any(abs(c - t) <= CUT_MERGE_TOL for t in detected):
            out[c] = {"same": False, "why": T("la detección de escena lo lista (cambio de cámara, > %g)", "scene detection lists it (camera change, > %g)") % thr}
            continue
        m = meas.get(c)
        if not m:
            out[c] = {"same": False, "why": T("sin cuadros a los dos lados del corte", "no frames on both sides of the cut")}
            continue
        ok = (m["static"] >= float(cfg["static_min"]) and m["edge_static"] >= float(cfg["edge_static_min"])
              and m["mean_diff"] <= float(cfg["mean_diff_max"]))
        out[c] = {"same": ok, "m": m, "ev": shot_evidence_text(m),
                  "why": T("%s: %s (mismo plano si %s)", "%s: %s (same shot if %s)") % (
                      T("mismo plano", "same shot") if ok else T("otro plano", "different shot"), shot_evidence_text(m), shot_limits_text(cfg))}
    return out


# ── Pauses in the voice ───────────────────────────────────────────────────────
#
# The editor, CLB ep3 (2026-10-01), for every video: what is said after a pause goes on
# the next card, and a card after a pause opens where the voice comes back. That
# needs the pauses, measured on the clip's own audio:
#
# * silencedetect needs every sample under its threshold for the whole pause;
#   under CLA's room tone and bed (RMS about −33 dB, peaks higher) it lists 0–2
#   pauses per snippet, and none at −25 dB either.
# * the word gaps in transcript.json do not work: whisper.cpp stretches the word
#   before a pause over it. CLB ep3 Snippet 2 has 9 pauses of 0.40 s or more
#   (silencedetect, clean voice) and not one word gap of 0.40 s.
# * what works is the RMS level in 10 ms windows under a floor set from the clip
#   itself: halfway between its quiet tenth (p10) and its median, never above
#   18 dB under its loud tenth (p90). On CLB ep3 it finds the same pauses as
#   silencedetect (3 of 3 and 8 of 9 at 0.40 s); on CLA ep4 Snippet 4 it finds
#   9 where silencedetect finds none — flat at −36 to −41 dB, 3–5 dB over the
#   clip's quietest tenth.

PAUSE_FRAME = 160              # samples per RMS window at 16 kHz = 10 ms
PAUSE_MIN_RUN = 0.18           # shortest run listed; the gate and the grouping pick their own minimum
# A music bed (or a constant noise) under the voice fills the pauses: the clip's quietest tenth
# then sits just under the pause floor, and most pauses never get below it. Measured 2026-10-03
# (floor minus the quietest tenth of the whole clip): CLA ep4's Premiere bases, whose audio carries
# the bed, 0.5-2.2 dB (S1: 1 pause found; the same edit's clean voice: 4 pauses, at 12.1 dB), CLD
# ep1's teaser 0.4 (0 pauses); every other clip of the regression set 4.1-27.3 (clean voices of
# CLB ep2/ep3, CLE ep2 and the CLA ep4 rebuild 6.2-27.3; CLD ep1 S1/S2 4.1/5.9; CLA ep4 S4, whose
# bed sits 24.5 LU down, 7.9 and 9 pauses found). Under this margin the measure is reported as
# limited (caption gate: WARN pauses-limited) — it can only find fewer pauses than there are. A
# bed far enough down to leave the quiet tenth 4 dB or more under the floor can still break pauses
# up unflagged: the cure is the clean voice of the cut in the project folder (clean_voice_file).
PAUSE_BED_MARGIN = 3.0
AUDIO_EXT = (".wav", ".m4a", ".mp3", ".aac", ".flac", ".aif", ".aiff")


def _pcm16(path):
    """Mono 16 kHz signed 16-bit samples of a media file's audio, or None."""
    import subprocess
    from array import array
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path,
                              "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                             capture_output=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or len(out.stdout) < 32000:
        return None
    a = array("h")
    a.frombytes(out.stdout[:len(out.stdout) // 2 * 2])
    if sys.byteorder == "big":
        a.byteswap()
    return a


def clean_voice_file(d):
    """A clean voice track kept in the project folder, or None: `voice.wav` (music-bed's input,
    the export's own audio — cla-brand finish.md), or a file whose name says VOICE and not MIX
    (`CLA ep4 Snippet 1 VOICE.wav`). It wins over the a-roll for the pauses: a base whose audio
    already carries a bed (an old Premiere render) hides most of them."""
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return None
    audio = [n for n in names if n.lower().endswith(AUDIO_EXT) and not n.startswith("._")]
    exact = [n for n in audio if os.path.splitext(n)[0].lower() == "voice"]
    named = [n for n in audio if re.search(r"(?<![a-z])voice(?![a-z])", n.lower()) and "mix" not in n.lower()]
    for n in exact + named:
        p = os.path.join(d, n)
        if os.path.isfile(p):
            return p
    return None


def _audio_sources(d, html):
    """Where the clip's own voice is: a clean voice track in the project folder first
    (clean_voice_file), then the a-roll video, then the <audio> element's file.

    The video comes before the <audio> on purpose: a client that mixes a music bed
    into the <audio> (CLB: `… MIX.wav`) keeps the clean voice in the a-roll.
    """
    out = []
    cv = clean_voice_file(d)
    if cv:
        out.append(cv)
    v = video_path(d, html)
    if v and v not in out:
        out.append(v)
    m = re.search(r"<audio[^>]*src=\"([^\"]+)\"", html or "")
    if m:
        try:
            from urllib.parse import unquote
            src = unquote(m.group(1))
        except Exception:
            src = m.group(1)
        p = src if os.path.isabs(src) else os.path.join(d, src)
        if os.path.isfile(p) and p not in out:
            out.append(p)
    return out


def voice_pauses(d, html=None):
    """Pauses in the clip's voice, measured on its own audio — or None when it cannot be read.

    {"pauses": [[start, end], …] (every run of at least PAUSE_MIN_RUN s),
     "floor", "p10", "p50", "p90" (dB), "source", "duration", "margin" (dB between the
     floor and the quietest tenth), "limited" (margin under PAUSE_BED_MARGIN: a bed or a
     constant noise under the voice — fewer pauses than there are), "skipped" (sources
     passed over, and why)}. Cached per file (size + mtime) in .gates-cache/pauses.json —
     decoding a clip costs ~1 s.
    """
    import math
    import operator
    if html is None:
        html = read_html(d)
    sources = _audio_sources(d, html)
    if not sources:
        return None
    # the voice belongs to the speech: the composition up to a fixed outro card, when it has one
    comp = speech_end(html, root(html)["duration"])
    voice = clean_voice_file(d)
    cache = os.path.join(d, ".gates-cache", "pauses.json")
    a = src = key = None
    skipped = []
    for cand in sources:
        st = os.stat(cand)
        key = {"source": os.path.basename(cand), "size": st.st_size,
               "mtime": round(st.st_mtime, 3), "frame": PAUSE_FRAME, "run": PAUSE_MIN_RUN, "v": 2,
               "comp": round(comp or 0.0, 2)}
        if os.path.isfile(cache):
            try:
                with open(cache, encoding="utf-8") as fh:
                    data = json.load(fh)
                if data.get("key") == key:
                    return data
            except Exception:
                pass
        a = _pcm16(cand)
        if a is None and cand == voice:
            skipped.append(T("%s no se pudo leer (ffmpeg)", "%s could not be read (ffmpeg)") % os.path.basename(cand))
            continue
        if a is not None and cand == voice and comp and abs(len(a) / 16000.0 - comp) > 1.0:
            # a voice file of another cut (or the uncut take) would place every pause wrong
            skipped.append(T("%s dura %.2fs y el habla del video %.2fs: no es de este corte", "%s lasts %.2fs and the video's speech %.2fs: it is not from this cut") % (
                os.path.basename(cand), len(a) / 16000.0, comp))
            a = None
            continue
        if a is not None:
            src = cand
            break
    if a is None:
        return None
    n = len(a) // PAUSE_FRAME
    levels = []
    for i in range(n):
        seg = a[i * PAUSE_FRAME:(i + 1) * PAUSE_FRAME]
        r = math.sqrt(sum(map(operator.mul, seg, seg)) / float(PAUSE_FRAME)) / 32768.0
        levels.append(20.0 * math.log10(r + 1e-9))
    spoken = sorted(x for x in levels if x > -70.0) or [-90.0]

    def pct(q):
        return spoken[int(round(q * (len(spoken) - 1)))]
    p10, p50, p90 = pct(0.10), pct(0.50), pct(0.90)
    floor = min(p10 + 0.5 * (p50 - p10), p90 - 18.0)
    step = PAUSE_FRAME / 16000.0
    pauses, i = [], 0
    while i < n:
        if levels[i] < floor:
            j = i
            while j < n and levels[j] < floor:
                j += 1
            if (j - i) * step >= PAUSE_MIN_RUN:
                pauses.append([round(i * step, 3), round(j * step, 3)])
            i = j
        else:
            i += 1
    # the quietest tenth of the WHOLE clip, digital silence included (a gated clean voice drops to
    # -90 dB between words, and those windows are not in `spoken`): a bed keeps it at the bed's level
    allq = sorted(levels) or [-90.0]
    margin = floor - allq[int(round(0.10 * (len(allq) - 1)))]
    data = {"key": key, "pauses": pauses, "floor": round(floor, 1), "p10": round(p10, 1),
            "p50": round(p50, 1), "p90": round(p90, 1), "source": os.path.basename(src),
            "duration": round(n * step, 3), "margin": round(margin, 1),
            "limited": margin < PAUSE_BED_MARGIN, "skipped": skipped}
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError:
        pass
    return data
