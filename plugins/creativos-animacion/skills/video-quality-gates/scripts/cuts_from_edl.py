#!/usr/bin/env python3
"""The camera cuts of a clip, read from a timeline export — a CMX3600 EDL or an FCPXML.

    python3 cuts_from_edl.py <timeline.edl | timeline.fcpxml> [--video <clip.mp4>]
                             [--fps 29.97] [--track V] [--sequence "<name>"]
                             [--tolerance 0.1] [--write <project-dir>]

The route for a cut made outside Premiere. Descript exports the timeline of a
composition as an EDL or as FCPXML (Export → Timeline); that is where a cut list
comes from when nobody opens Premiere — the other editor's route. A single-take video (one
person, jump cuts where pauses and retakes were removed) changes picture too
little for scene detection to list its cuts (CLB ep2 and CLB ep3: real cuts scored
0.034–0.17, frames with no cut up to 0.079, and a hand-made cuts.txt held 3 of 8
and 11 of 17), and a caption card that crosses a jump cut is the most visible
caption bug there is. The edit itself knows every cut.

It reads the picture events in record order and prints each edit point: a cut
when the source jumps, the media changes or the timeline has a hole, a
through-edit (skipped) when the source runs on without a break, a dissolve when
a transition joins two clips.

--video      the clip exported from that timeline. When the timeline and the clip
             differ in length by more than --tolerance (0.1 s) they are not the
             same cut — a range was exported, or it is another version — and
             nothing is written (exit 2), as cuts_from_prproj.py does. It also
             gives the frame rate an EDL needs.
--fps        the timeline's frame rate; an EDL stores timecode and no rate.
             29.97, 23.976 and 59.94 mean the NTSC rates (30000/1001…). Without
             --video or --fps the script assumes 30 and says so.
--track      EDL only: which video track to read when the file has several
             (default: the first one found, V before V2…).
--sequence   FCPXML only: the project/sequence to read when the file holds more
             than one (default: the only one; otherwise the script lists them).
--write DIR  write DIR/cuts.txt, one time in seconds per line — the file the
             caption gate, the variety gate and the grouping script read.

Times are measured from the first frame of the timeline (a 01:00:00:00 start is
taken away). Reads only; never writes next to the export. Exit 2 when the file
cannot be read or the timeline is not the clip.
"""

import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")   # Windows consoles default to cp1252
    except (AttributeError, ValueError):
        pass

NTSC = {23.976: (24000, 1001), 29.97: (30000, 1001), 47.952: (48000, 1001),
        59.94: (60000, 1001), 119.88: (120000, 1001)}


class InputError(Exception):
    """The file cannot be read as the timeline of one clip."""


# ── frame rate and timecode ──────────────────────────────────────────────────

def rate(fps):
    """(real fps as a Fraction, nominal integer fps) for a number like 29.97 or 30."""
    f = float(fps)
    for k, (n, d) in NTSC.items():
        if abs(f - k) < 0.011 or abs(f - n / float(d)) < 0.0005:
            return Fraction(n, d), int(round(n / float(d)))
    frac = Fraction(f).limit_denominator(1001)
    return frac, int(round(f))


TC = r"\d+[:;]\d+[:;]\d+[:;.]\d+"


def timecode_seconds(tc, fps_real, nominal, hour_base=0, drop=False):
    """HH:MM:SS:FF (non-drop) or HH:MM:SS;FF (drop-frame) → seconds.

    Drop-frame is a `;` anywhere in the timecode (`01:00:00;00`, `01;00;00;00`) or
    `drop=True` — the EDL's own `FCM: DROP FRAME` line, which some exporters write
    with plain colons. Read as non-drop, a drop-frame label runs 2 frames ahead per
    minute (a 3-minute teaser: 0.2 s off at the end).

    hour_base is taken off the hour field before anything is counted: a sequence
    whose timecode starts at 01:00:00:00 is 3600 timecode seconds long at 30 fps
    and 3603.6 real seconds at 29.97, and only counting in timecode makes the
    clip's first frame come out as 0.
    """
    m = re.match(r"^(\d+)[:;](\d+)[:;](\d+)([:;.])(\d+)$", tc.strip())
    if not m:
        raise InputError(T("timecode ilegible: %r", "unreadable timecode: %r") % tc)
    h, mi, s, f = int(m.group(1)) - hour_base, int(m.group(2)), int(m.group(3)), int(m.group(5))
    if f >= nominal:
        raise InputError(T("el cuadro %d no existe a %g fps (%r): ¿es otro frame rate? usá --fps", "frame %d does not exist at %g fps (%r): is it another frame rate? use --fps") % (f, float(fps_real), tc))
    frames = ((h * 60 + mi) * 60 + s) * nominal + f
    if (";" in tc or drop) and nominal in (30, 60):
        skipped = 2 if nominal == 30 else 4          # labels skipped at each minute but every tenth
        total_min = h * 60 + mi
        frames -= skipped * (total_min - total_min // 10)
    return float(Fraction(frames) / fps_real)


# ── CMX3600 EDL ──────────────────────────────────────────────────────────────

EVENT_RE = re.compile(
    r"^\s*(\d{1,6})\s+(.+?)\s+(AA/V|A/V|V/A|AA|NONE|A\d*|V\d*|B)\s+(C|D|W\d*|K\w*)\s*(\d{1,4})?\s+"
    r"(" + TC + r")\s+(" + TC + r")\s+(" + TC + r")\s+(" + TC + r")\s*$")


def _picture_track(track):
    """The picture track an event sits on: 'V' for V, V1, AA/V, A/V, V/A and B (all the one
    picture track of CMX3600), 'V2'… for the others, None for an audio-only event."""
    comps = track.upper().split("/")
    v = next((c for c in comps if c.startswith("V")), None)
    if v is None:
        return "V" if "B" in comps else None
    return "V" if v in ("V", "V1") else v


def read_edl(path, fps, wanted_track=None):
    """[{start, end, src_in, src_out, reel, name, kind}] of the picture events, in record order.

    CMX3600 has one picture track: an event tagged V, V1, AA/V, A/V, V/A or B is on it
    (the tag says which channels the event carries, not another track); V2, V3… are
    the extra tracks some exporters add (B-roll), read only with --track. Audio-only
    events (A, AA, A2…) are left out. The clip name comes from `* FROM CLIP NAME` —
    for a dissolve or wipe from `* TO CLIP NAME`, the clip coming in — and the
    zero-length "from" line of a two-line dissolve is skipped.
    """
    real, nominal = rate(fps)
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    events, last, drop = [], None, False
    for line in lines:
        fcm = re.match(r"^\s*FCM\s*:\s*(.+?)\s*$", line, re.I)
        if fcm:
            drop = "DROP" in fcm.group(1).upper() and "NON" not in fcm.group(1).upper()
            continue
        m = EVENT_RE.match(line)
        if m:
            num, reel, track, trans, tdur, si, so, ri, ro = m.groups()
            last = {"num": int(num), "reel": reel.strip(), "track": track, "trans": trans[:1],
                    "tc": (si, so, ri, ro), "drop": drop,
                    "start": timecode_seconds(ri, real, nominal, drop=drop),
                    "end": timecode_seconds(ro, real, nominal, drop=drop),
                    "src_in": timecode_seconds(si, real, nominal, drop=drop),
                    "src_out": timecode_seconds(so, real, nominal, drop=drop),
                    "from": None, "to": None}
            events.append(last)
        elif last is not None and line.strip().startswith("*"):
            cm = re.match(r"^\s*\*\s*(FROM|TO)\s+CLIP\s+NAME\s*:\s*(.+?)\s*$", line, re.I)
            if cm and last[cm.group(1).lower()] is None:
                last[cm.group(1).lower()] = cm.group(2)
    if not events:
        raise InputError(T("no encontré eventos CMX3600 en %s (¿es un EDL? Descript: Export → Timeline → EDL)", "no CMX3600 events found in %s (is it an EDL? Descript: Export → Timeline → EDL)") % path)

    for e in events:
        e["vtrack"] = _picture_track(e["track"])
    video = [e for e in events if e["vtrack"] and e["end"] > e["start"]]
    if not video:
        raise InputError(T("el EDL no tiene eventos de video (pistas: %s)", "the EDL has no video events (tracks: %s)") % ", ".join(sorted({e['track'] for e in events})))
    tracks = sorted({e["vtrack"] for e in video}, key=lambda t: (t != "V", t))
    if wanted_track:
        want = _picture_track(wanted_track) or wanted_track.upper()
        video = [e for e in video if e["vtrack"] == want]
        if not video:
            raise InputError(T("el EDL no tiene la pista de video %s. Hay: %s", "the EDL has no video track %s. Available: %s") % (wanted_track, ", ".join(tracks)))
    elif len(tracks) > 1:
        keep = tracks[0]
        sys.stderr.write(T("el EDL tiene varias pistas de imagen (%s): leo %s; --track elige otra\n", "the EDL has several picture tracks (%s): reading %s; --track picks another\n")
                         % (", ".join(tracks), keep))
        video = [e for e in video if e["vtrack"] == keep]
    video.sort(key=lambda e: (e["start"], e["num"]))
    # the timecode of a sequence often starts at 01:00:00:00: that hour is not part of the clip
    base = int(re.split(r"[:;]", video[0]["tc"][2])[0])
    origin = base * 3600
    out = []
    for e in video:
        moving = e["trans"] != "C"
        name = (e["to"] or e["from"]) if moving else (e["from"] or e["to"])
        out.append({"start": timecode_seconds(e["tc"][2], real, nominal, base, e["drop"]),
                    "end": timecode_seconds(e["tc"][3], real, nominal, base, e["drop"]),
                    "src_in": e["src_in"], "src_out": e["src_out"],
                    "reel": e["reel"], "name": name or "",
                    "media": "%s|%s" % (e["reel"], name or ""), "kind": "dissolve" if moving else "cut",
                    "transition": moving})
    return out, {"format": "CMX3600 EDL", "fps": float(real), "origin": origin, "tracks": tracks,
                 "drop": any(e["drop"] or ";" in "".join(e["tc"]) for e in video)}


# ── FCPXML ───────────────────────────────────────────────────────────────────

def _fcp_time(txt):
    """'3003/30000s', '10s', '0s' → seconds as a Fraction; None when absent."""
    if txt is None:
        return None
    m = re.match(r"^\s*(-?\d+)(?:/(\d+))?s\s*$", txt)
    if not m:
        raise InputError(T("tiempo FCPXML ilegible: %r", "unreadable FCPXML time: %r") % txt)
    return Fraction(int(m.group(1)), int(m.group(2) or 1))


def read_fcpxml(path, sequence=None):
    p = path
    if os.path.isdir(p):
        p = os.path.join(p, "Info.fcpxml")
    try:
        root = ET.parse(p).getroot()
    except (OSError, ET.ParseError) as e:
        raise InputError(T("no pude leer %s como FCPXML: %s", "could not read %s as FCPXML: %s") % (path, e))
    if root.tag != "fcpxml":
        hint = T(" (es XML de Premiere/xmeml: exportá FCPXML o EDL desde Descript)", " (it is Premiere XML/xmeml: export FCPXML or EDL from Descript)") if root.tag == "xmeml" else ""
        raise InputError(T("%s no es un FCPXML (raíz <%s>)%s", "%s is not an FCPXML (root <%s>)%s") % (path, root.tag, hint))
    seqs = [(proj.get("name") or "", seq) for proj in root.iter("project") for seq in proj.findall("sequence")]
    if not seqs:
        seqs = [("", seq) for seq in root.iter("sequence")]
    if not seqs:
        raise InputError(T("el FCPXML no tiene ninguna secuencia/proyecto", "the FCPXML has no sequence/project"))
    if sequence:
        pick = [s for s in seqs if s[0] == sequence]
        if not pick:
            raise InputError(T("no hay un proyecto «%s». Hay: %s", "no project “%s” found. Available: %s") % (sequence, " · ".join(n or T("(sin nombre)", "(unnamed)") for n, _ in seqs)))
    elif len(seqs) > 1:
        raise InputError(T("el FCPXML tiene %d proyectos; elegí uno con --sequence: %s", "the FCPXML has %d projects; pick one with --sequence: %s")
                         % (len(seqs), " · ".join(n or T("(sin nombre)", "(unnamed)") for n, _ in seqs)))
    else:
        pick = seqs
    name, seq = pick[0]
    spine = seq.find("spine")
    if spine is None:
        raise InputError(T("la secuencia «%s» no tiene spine", "sequence “%s” has no spine") % name)
    tc0 = _fcp_time(seq.get("tcStart")) or Fraction(0)
    fps = None
    fmt = seq.get("format")
    for f in root.iter("format"):
        if f.get("id") == fmt and f.get("frameDuration"):
            fd = _fcp_time(f.get("frameDuration"))
            fps = float(1 / fd) if fd else None
    assets = {a.get("id"): a for a in root.iter("asset") if a.get("id")}
    items, pending_transitions = [], []

    def primary(el):
        """The element's own media reference: its `ref`, else the first nested video/clip that is
        on the primary storyline — a connected clip (`lane`, B-roll, a title, music) never is."""
        if el.get("ref"):
            return el.get("ref"), el
        stack = list(el)
        while stack:
            sub = stack.pop(0)
            if sub.get("lane") not in (None, "", "0"):
                continue
            if sub.get("ref") and sub.tag in ("video", "asset-clip", "ref-clip", "audio"):
                return sub.get("ref"), sub
            stack[:0] = list(sub)
        return None, None

    for el in spine:
        if el.get("lane") not in (None, "", "0"):
            continue                     # a connected clip (B-roll, music): not the primary storyline
        off, dur = _fcp_time(el.get("offset")), _fcp_time(el.get("duration"))
        if el.tag == "transition":
            if off is not None and dur is not None:
                pending_transitions.append((off + dur / 2, dur))
            continue
        if off is None or dur is None:
            continue
        ref, holder = primary(el)
        start = _fcp_time(el.get("start"))
        if start is None and el.tag != "gap":
            # no `start`: the clip begins at its media's own start (FCPXML leaves it out then)
            src = holder if holder is not None and holder is not el else None
            start = (_fcp_time(src.get("start")) if src is not None and src.get("start") else None)
            if start is None:
                a = assets.get(ref)
                start = _fcp_time(a.get("start")) if a is not None and a.get("start") else Fraction(0)
        items.append({"start": off - tc0, "end": off - tc0 + dur,
                      "src_in": start if el.tag != "gap" else None,
                      "src_out": (start + dur) if (start is not None and el.tag != "gap") else None,
                      "media": ("gap" if el.tag == "gap" else (ref or el.get("name") or el.tag)),
                      "kind": "gap" if el.tag == "gap" else "clip"})
    if not items:
        raise InputError(T("la secuencia «%s» está vacía", "sequence “%s” is empty") % name)
    items.sort(key=lambda x: x["start"])
    seq_dur = _fcp_time(seq.get("duration"))
    out = [{"start": float(i["start"]), "end": float(i["end"]),
            "src_in": None if i["src_in"] is None else float(i["src_in"]),
            "src_out": None if i["src_out"] is None else float(i["src_out"]),
            "media": i["media"], "kind": i["kind"], "transition": False} for i in items]
    return out, {"format": "FCPXML", "fps": fps, "origin": float(tc0), "name": name,
                 "transitions": [(float(t - tc0), float(d)) for t, d in pending_transitions],
                 "duration": float(seq_dur) if seq_dur is not None else None}


# ── edit points ──────────────────────────────────────────────────────────────

def _same_media(a, b):
    """Two events show the same media: the same reel and, when both carry a clip name, the same
    name (an EDL writes the name on some events and not on others — then the reel decides)."""
    if "reel" in a and "reel" in b:
        return a["reel"] == b["reel"] and (not a["name"] or not b["name"] or a["name"] == b["name"])
    return a["media"] == b["media"]


def classify(items, fps, extra_transitions=()):
    """[(time, 'cut' | 'through' | 'dissolve', why)] for each boundary between two picture events.

    A hole in the timeline (black between two events) is two edit points: where the
    picture goes to black and where it comes back. `extra_transitions` are FCPXML's
    transitions, (middle, duration) or a bare time: each is one edit point, at its
    middle, and the clip boundary under it is not listed again.
    """
    frame = 1.0 / (fps or 30.0)
    out = []
    for a, b in zip(items, items[1:]):
        t = b["start"]
        gap = b["start"] - a["end"]
        if a["kind"] == "gap" or b["kind"] == "gap":
            out.append((t, "cut", T("hueco en la pista (la imagen entra o sale de un vacío)", "gap in the track (the picture goes into or comes out of an empty space)")))
            continue
        if gap > frame / 2:
            out.append((a["end"], "cut", T("la imagen sale a negro (hueco de %.3fs en la pista)", "the picture goes to black (a %.3fs gap in the track)") % gap))
            out.append((t, "cut", T("la imagen vuelve del negro", "the picture comes back from black")))
            continue
        if b.get("transition"):
            out.append((t, "dissolve", T("transición entre dos clips (cuenta como corte)", "transition between two clips (counts as a cut)")))
            continue
        same = _same_media(a, b)
        if not same or None in (a["src_in"], a["src_out"], b["src_in"]):
            out.append((t, "cut", T("otro clip", "different clip") if not same else T("sin punto de entrada", "no in point")))
            continue
        jump = b["src_in"] - a["src_out"]
        if abs(gap) > frame / 2:
            out.append((t, "cut", T("superposición de %.3fs en la pista", "overlap of %.3fs in the track") % -gap))
        elif abs(jump) < frame / 2:
            out.append((t, "through", T("la fuente sigue (%+.3fs)", "the source runs on (%+.3fs)") % jump))
        else:
            out.append((t, "cut", T("salto de fuente %+.3fs", "source jump %+.3fs") % jump))
    for tr in extra_transitions:
        mid, dur = tr if isinstance(tr, (tuple, list)) else (tr, 0.0)
        out = [p for p in out if abs(p[0] - mid) > dur / 2 + frame]
        out.append((mid, "dissolve", T("transición (FCPXML)", "transition (FCPXML)")))
    return sorted(out)


def _looks_xml(path):
    try:
        with open(path, "rb") as fh:
            return fh.read(512).lstrip().startswith(b"<?xml")
    except OSError:
        return False


def _probe(video):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                              "-show_entries", "stream=r_frame_rate,avg_frame_rate:format=duration", "-of", "json", video],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60).stdout
        data = json.loads(out)
        st = data["streams"][0]
        fps = None
        for key in ("r_frame_rate", "avg_frame_rate"):
            num, den = (st.get(key) or "0/0").split("/")
            v = float(num) / float(den) if float(den) else 0.0
            if 1.0 <= v <= 121.0:            # a variable-rate clip reports 90000/1 as r_frame_rate
                fps = v
                break
        return float(data["format"]["duration"]), fps
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError):
        return None, None


def selftest():
    """Write an EDL and an FCPXML from a known cut list, read them back, compare.

    The edit: 20 s at 30 fps — a source jump at 3.5 s, a through-edit at 7.2 s (the
    source runs on), a source jump at 12.0 s. Expected cuts: 3.5 and 12.0. Also run
    at 29.97 (non-drop and drop-frame timecode) and with an FCPXML that has a
    connected clip and a tcStart. No ffmpeg, no files kept.
    """
    import tempfile
    segs = [(10.0, 13.5), (20.0, 23.7), (23.7, 28.5), (40.0, 48.0)]      # source in/out
    want = [3.5, 12.0]
    fails = []

    def tc(frames, nominal, drop=False, sep=None):
        if drop:
            d = 2
            tens, rest = divmod(frames, 17982)
            frames += 18 * tens + (d * ((rest - d) // 1798) if rest > d else 0)
        s, f = divmod(frames, nominal)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return "%02d:%02d:%02d%s%02d" % (h, m, s, sep or (";" if drop else ":"), f)

    def edl(fps, nominal, drop, offset_frames, sep=None, tracks=("V",)):
        lines = ["TITLE: SELFTEST", "FCM: %s" % ("DROP FRAME" if drop else "NON-DROP FRAME"), ""]
        rec = 0
        for n, (a, b) in enumerate(segs, 1):
            fa, fb = int(round(a * fps)), int(round(b * fps))
            lines.append("%03d  AX       %-5s C        %s %s %s %s"
                         % (n, tracks[n % len(tracks)], tc(fa, nominal, drop, sep), tc(fb, nominal, drop, sep),
                            tc(offset_frames + rec, nominal, drop, sep), tc(offset_frames + rec + fb - fa, nominal, drop, sep)))
            lines.append("* FROM CLIP NAME: clip.mp4")
            rec += fb - fa
        return "\n".join(lines) + "\n"

    def fcpxml(num, den, tc_start, lane):
        # a frame is num/den s; clip times are written as N*num/den s
        def t(frames):
            return "%d/%ds" % (frames * num, den)
        rec, clips = 0, []
        for a, b in segs:
            fa, fb = int(round(a * den / num)), int(round(b * den / num))
            clips.append('<asset-clip ref="r2" offset="%s" name="clip" start="%s" duration="%s"/>'
                         % (t(tc_start + rec), t(fa), t(fb - fa)))
            rec += fb - fa
        extra = '<asset-clip ref="r2" lane="1" offset="%s" name="music" start="0s" duration="%s"/>' % (t(tc_start), t(30)) if lane else ""
        return ('<?xml version="1.0" encoding="UTF-8"?><fcpxml version="1.9"><resources>'
                '<format id="r1" frameDuration="%d/%ds"/><asset id="r2" name="clip" start="0s" duration="3600s" format="r1"/>'
                '</resources><library><event name="e"><project name="Snippet"><sequence format="r1" duration="%s" tcStart="%s">'
                '<spine>%s%s</spine></sequence></project></event></library></fcpxml>'
                % (num, den, t(rec), t(tc_start), "".join(clips), extra))

    cases = []
    with tempfile.TemporaryDirectory() as d:
        for name, text, kw in [
            ("EDL 30 fps", edl(30, 30, False, 0), dict(fps=30)),
            ("EDL 30 fps, 01:00:00:00 start", edl(30, 30, False, 108000), dict(fps=30)),
            ("EDL 29.97 non-drop, 01:00:00:00 start", edl(30000 / 1001.0, 30, False, 108000), dict(fps=29.97)),
            ("EDL 29.97 drop-frame, 01:00:00;00 start", edl(30000 / 1001.0, 30, True, 107892), dict(fps=29.97)),
            ("EDL 25 fps", edl(25, 25, False, 90000), dict(fps=25)),
            # FCM: DROP FRAME written with plain colons, and V / AA/V / B on the one picture track
            ("EDL 29.97 drop-frame with ':' (FCM), V/AA/V/B", edl(30000 / 1001.0, 30, True, 107892, ":", ("V", "AA/V", "B")),
             dict(fps=29.97)),
        ]:
            path = os.path.join(d, "t.edl")
            with open(path, "w") as fh:
                fh.write(text)
            items, info = read_edl(path, kw["fps"])
            cases.append((name, [t for t, k, _ in classify(items, kw["fps"]) if k == "cut"],
                          max(x["end"] for x in items)))
        for name, xml in [("FCPXML 30 fps", fcpxml(1, 30, 0, False)),
                          ("FCPXML 29.97, tcStart 3600 s, a connected clip", fcpxml(1001, 30000, 107892, True))]:
            path = os.path.join(d, "t.fcpxml")
            with open(path, "w") as fh:
                fh.write(xml)
            items, info = read_fcpxml(path)
            cases.append((name, [t for t, k, _ in classify(items, info["fps"]) if k == "cut"],
                          max(x["end"] for x in items)))
    total = sum(b - a for a, b in segs)
    for name, got, end in cases:
        # the 29.97 timelines are 0.1 % longer than their frame counts at 30: compare in frames
        tol = 0.05
        ok = len(got) == len(want) and all(abs(g - w) <= tol for g, w in zip(got, want)) and abs(end - total) <= 0.05
        print(T("%-52s %s  cortes %s · termina en %.3fs", "%-52s %s  cuts %s · ends at %.3fs") % (name, "OK  " if ok else "FAIL", ", ".join("%.3f" % g for g in got), end))
        if not ok:
            fails.append(name)
    print("selftest: %s" % (T("todo bien", "all good") if not fails else T("FALLÓ: ", "FAILED: ") + ", ".join(fails)))
    return 1 if fails else 0


def main(argv):
    if len(argv) >= 2 and argv[1] == "--selftest":
        return selftest()
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        sys.stderr.write(__doc__)
        return 2
    path = argv[1]
    opt = {}
    i = 2
    while i < len(argv):
        if argv[i] in ("--video", "--fps", "--track", "--sequence", "--tolerance", "--write") and i + 1 < len(argv):
            opt[argv[i]] = argv[i + 1]
            i += 2
        else:
            sys.stderr.write(T("opción desconocida: %s\n", "unknown option: %s\n") % argv[i])
            return 2
    clip_dur = clip_fps = None
    if "--video" in opt:
        clip_dur, clip_fps = _probe(opt["--video"])
        if clip_dur is None:
            sys.stderr.write(T("ERROR DE ENTRADA: no pude leer la duración de %s\n", "INPUT ERROR: could not read the duration of %s\n") % opt["--video"])
            return 2
    ext = os.path.splitext(path.rstrip("/\\"))[1].lower()
    try:
        if ext in (".fcpxml", ".fcpxmld", ".xml") or _looks_xml(path):
            items, info = read_fcpxml(path, opt.get("--sequence"))
            fps = info.get("fps") or clip_fps or float(opt.get("--fps", 30))
        else:
            fps_given = float(opt["--fps"]) if "--fps" in opt else None
            fps = fps_given or clip_fps
            if fps is None:
                fps = 30.0
                sys.stderr.write(T("OJO: un EDL no dice su frame rate y no di --fps ni --video: asumí 30. "
                                 "Con otro rate los tiempos salen corridos.\n",
                                   "WARNING: an EDL does not state its frame rate and neither --fps nor --video was given: assumed 30. "
"At another rate the times come out shifted.\n"))
            elif fps_given and clip_fps and abs(fps_given - clip_fps) > 0.02:
                sys.stderr.write(T("OJO: --fps %g y el video va a %g fps\n", "WARNING: --fps %g but the video runs at %g fps\n") % (fps_given, clip_fps))
            items, info = read_edl(path, fps, opt.get("--track"))
    except (InputError, OSError, ValueError) as e:
        sys.stderr.write(T("ERROR DE ENTRADA: %s\n", "INPUT ERROR: %s\n") % e)
        return 2
    seq_end = max(x["end"] for x in items)
    print(T("Leído: %s · %s · %d evento(s) de imagen · %.3f fps%s · termina en %.3fs%s", "Read: %s · %s · %d picture event(s) · %.3f fps%s · ends at %.3fs%s")
          % (os.path.basename(path), info["format"], len(items), fps,
             " drop-frame" if info.get("drop") else "", seq_end,
             (T(" · origen -%.0fs", " · origin -%.0fs") % info["origin"]) if info.get("origin") else ""))
    points = classify(items, fps, info.get("transitions") or ())
    for t, kind, why in points:
        print("  %8.3f  %-8s %s" % (t, {"cut": T("corte", "cut"), "through": T("seguido", "through"), "dissolve": T("disolv.", "dissolve")}[kind], why))
    cuts = [t for t, kind, _ in points if kind in ("cut", "dissolve")]
    print(T("%d corte(s), %d edición(es) sin salto", "%d cut(s), %d edit(s) with no jump") % (len(cuts), len(points) - len(cuts)))
    if clip_dur is not None:
        tol = float(opt.get("--tolerance", 0.1))
        print(T("clip %.3fs vs línea de tiempo %.3fs (dif %.3fs)", "clip %.3fs vs timeline %.3fs (diff %.3fs)") % (clip_dur, seq_end, clip_dur - seq_end))
        if abs(clip_dur - seq_end) > tol:
            sys.stderr.write(T("ERROR: el clip y la línea de tiempo no tienen el mismo largo — no es el mismo "
                             "corte, se exportó un rango, o el frame rate no es el del EDL (--fps). "
                             "No escribí nada.\n",
                               "ERROR: the clip and the timeline are not the same length — it is not the same "
"cut, a range was exported, or the frame rate is not the EDL's (--fps). "
"Nothing was written.\n"))
            return 2
    else:
        sys.stderr.write(T("OJO: sin --video no pude comprobar que esta línea de tiempo sea el clip.\n", "WARNING: without --video, could not check that this timeline is the clip.\n"))
    if not cuts:
        print(T("la línea de tiempo no tiene cortes de salto (un solo tramo)", "the timeline has no jump cuts (a single stretch)"))
    if "--write" in opt:
        dest = os.path.join(opt["--write"], "cuts.txt")
        if not os.path.isdir(opt["--write"]):
            sys.stderr.write(T("ERROR: %s no es una carpeta (la del proyecto de HyperFrames). No escribí nada.\n", "ERROR: %s is not a folder (it should be the HyperFrames project folder). Nothing was written.\n")
                             % opt["--write"])
            return 2
        try:
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write("".join("%.6f\n" % t for t in cuts))
        except OSError as e:
            sys.stderr.write(T("ERROR: no pude escribir %s: %s\n", "ERROR: could not write %s: %s\n") % (dest, e))
            return 2
        print(T("escrito: %s", "written: %s") % dest)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
