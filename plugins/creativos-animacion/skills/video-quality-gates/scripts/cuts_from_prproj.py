#!/usr/bin/env python3
"""The camera cuts of a clip, read from the Premiere sequence it was rendered from.

    python3 cuts_from_prproj.py <file.prproj> "<sequence name>" [--video <clip.mp4>]
                                [--track 1] [--write <project-dir>]

A single-take video (one person, jump cuts where pauses and retakes were
removed) changes picture too little for scene detection to list its cuts
reliably: CLB ep3's cuts.txt, built from a hand-picked scene threshold, held 3 of
the 8 edits of Snippet 1 and 11 of the 17 of Snippet 2, and three caption cards
crossed the missing ones. The edit itself knows every cut. This reads the clip
items on one video track of the sequence and prints each edit point: a cut when
the source jumps or the media changes, a through-edit (skipped) when the source
runs on.

--video   the clip rendered from the sequence; when the sequence and the clip
          differ in length by more than 0.1 s they are not the same cut and
          nothing is written (exit 2)
--write   write <project-dir>/cuts.txt (one time in seconds per line), the
          file the caption and variety gates read

Reads the .prproj only (gzip XML); never writes next to it. Exit 2 when the
sequence or its track cannot be read. Times are sequence times, which are the
clip's times when the whole sequence was rendered from its start.
"""

import gzip
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)

TICKS = 254016000000          # Premiere ticks per second


def _load(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return ET.fromstring(raw)


def _index(root):
    byid = {}
    for el in root.iter():
        for k in ("ObjectID", "ObjectUID"):
            if el.get(k):
                byid[el.get(k)] = el
    return byid


def _deref(byid, el):
    if el is None:
        return None
    ref = el.get("ObjectRef") or el.get("ObjectURef")
    return byid.get(ref) if ref else el


def _int(el, default=None):
    return int(el.text) if el is not None and el.text else default


def edit_points(prproj, sequence, track=1):
    root = _load(prproj)
    byid = _index(root)
    seqs = [s for s in root.iter("Sequence")
            if s.find("Name") is not None and s.find("Name").text == sequence]
    if not seqs:
        names = sorted({s.find("Name").text for s in root.iter("Sequence")
                        if s.find("Name") is not None and s.find("Name").text})
        raise ValueError(T("no hay una secuencia «%s». Hay: %s", "no sequence “%s” found. Available: %s") % (sequence, " · ".join(names)))
    seq = seqs[0]
    fps = None
    for item in seq.find("TrackGroups") or []:
        group = _deref(byid, item.find("Second"))
        if group is None or group.tag != "VideoTrackGroup":
            continue
        tg = group.find("TrackGroup")
        per_frame = _int(tg.find("FrameRate"))
        fps = TICKS / per_frame if per_frame else None
        tracks = list(tg.find("Tracks"))
        if track > len(tracks):
            raise ValueError(T("la secuencia tiene %d pista(s) de video, no V%d", "the sequence has %d video track(s), there is no V%d") % (len(tracks), track))
        tr = _deref(byid, tracks[track - 1])
        tis = tr.find("ClipTrack").find("ClipItems").find("TrackItems")
        items = []
        for ti in (tis if tis is not None else []):
            ti = _deref(byid, ti)
            cti = ti.find("ClipTrackItem")
            t = cti.find("TrackItem")
            start = _int(t.find("Start"), 0) / TICKS
            end = _int(t.find("End"), 0) / TICKS
            sub = _deref(byid, cti.find("SubClip"))
            media = src_in = None
            if sub is not None:
                mc = sub.find("MasterClip")
                media = mc.get("ObjectURef") if mc is not None else None
                clip = _deref(byid, sub.find("Clip"))
                inner = clip.find("Clip") if clip is not None else None
                src_in = _int(inner.find("InPoint"), 0) / TICKS if inner is not None else None
            items.append({"start": start, "end": end, "media": media, "src_in": src_in})
        items.sort(key=lambda x: x["start"])
        return items, fps
    raise ValueError(T("la secuencia «%s» no tiene pistas de video legibles", "sequence “%s” has no readable video tracks") % sequence)


def classify(items, fps):
    frame = 1.0 / (fps or 30.0)
    out = []
    for a, b in zip(items, items[1:]):
        t = b["start"]
        gap = b["start"] - a["end"]
        if a["media"] != b["media"] or a["src_in"] is None or b["src_in"] is None:
            out.append((t, "cut", T("otro clip", "different clip") if a["media"] != b["media"] else T("sin punto de entrada", "no in point")))
            continue
        jump = b["src_in"] - (a["src_in"] + (a["end"] - a["start"]))
        if abs(gap) > frame / 2:
            out.append((t, "cut", T("hueco de %.3fs en la pista", "gap of %.3fs in the track") % gap))
        elif abs(jump) < frame / 2:
            out.append((t, "through", T("la fuente sigue (%.3fs)", "the source runs on (%.3fs)") % jump))
        else:
            out.append((t, "cut", T("salto de fuente %+.3fs", "source jump %+.3fs") % jump))
    return out


def _duration(video):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "json", video], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=60).stdout
        return float(json.loads(out)["format"]["duration"])
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return None


def main(argv):
    if len(argv) < 3:
        sys.stderr.write(__doc__)
        return 2
    prproj, sequence = argv[1], argv[2]
    opt = {}
    i = 3
    while i < len(argv):
        if argv[i] in ("--video", "--track", "--write") and i + 1 < len(argv):
            opt[argv[i]] = argv[i + 1]
            i += 2
        else:
            sys.stderr.write(T("opción desconocida: %s\n", "unknown option: %s\n") % argv[i])
            return 2
    try:
        items, fps = edit_points(prproj, sequence, int(opt.get("--track", 1)))
    except (OSError, ValueError, ET.ParseError, AttributeError) as e:
        sys.stderr.write(T("ERROR DE ENTRADA: %s\n", "INPUT ERROR: %s\n") % e)
        return 2
    if not items:
        sys.stderr.write(T("ERROR DE ENTRADA: la pista V%s de «%s» está vacía\n", "INPUT ERROR: track V%s of “%s” is empty\n")
                         % (opt.get("--track", 1), sequence))
        return 2
    seq_end = items[-1]["end"]
    print(T("Leído: «%s» V%s · %d clip(s) · %.3f fps · termina en %.3fs", "Read: “%s” V%s · %d clip(s) · %.3f fps · ends at %.3fs")
          % (sequence, opt.get("--track", 1), len(items), fps or 0, seq_end))
    points = classify(items, fps)
    for t, kind, why in points:
        print("  %8.3f  %-7s %s" % (t, T("corte", "cut") if kind == "cut" else T("seguido", "through"), why))
    cuts = [t for t, kind, _ in points if kind == "cut"]
    print(T("%d corte(s), %d edición(es) sin salto", "%d cut(s), %d edit(s) with no jump") % (len(cuts), len(points) - len(cuts)))
    if "--video" in opt:
        dur = _duration(opt["--video"])
        if dur is None:
            sys.stderr.write(T("ERROR DE ENTRADA: no pude leer la duración de %s\n", "INPUT ERROR: could not read the duration of %s\n") % opt["--video"])
            return 2
        print(T("clip %.3fs vs secuencia %.3fs (dif %.3fs)", "clip %.3fs vs sequence %.3fs (diff %.3fs)") % (dur, seq_end, dur - seq_end))
        if abs(dur - seq_end) > 0.1:
            sys.stderr.write(T("ERROR: el clip y la secuencia no tienen el mismo largo — no es el "
                             "mismo corte, o se renderizó un rango. No escribí nada.\n",
                               "ERROR: the clip and the sequence are not the same length — it is not the "
"same cut, or a range was rendered. Nothing was written.\n"))
            return 2
    if "--write" in opt:
        dest = os.path.join(opt["--write"], "cuts.txt")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write("".join("%.6f\n" % t for t in cuts))
        print(T("escrito: %s", "written: %s") % dest)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
