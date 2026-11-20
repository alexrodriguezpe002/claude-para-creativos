#!/usr/bin/env python3
"""Cut points measured on the audio, not on the transcript.

Whisper's word times are good enough to FIND a sentence, not to CUT it: it
starts many words 0.1-0.35 s late, starts the word after a pause up to 0.9 s
early, and stretches the last word over the silence that follows. On the Prospect P
master, 25 of 50 cut points placed on Whisper times fell on voice and
several ate or split a whole word ("Ev-|-erybody's", "-tal technology").

Module (used by the video engines) and command line:

    python3 audiocuts.py energy   --src M.mp4 --at 403.6 --win 0.4 [--step 0.01]
    python3 audiocuts.py gap      --src M.mp4 --between 403.5 403.8
    python3 audiocuts.py check    --src M.mp4 403.30 406.40 408.04 ...   # silence / valley / ON VOICE
    python3 audiocuts.py silences --src M.mp4 --range 416.0 423.25 [--th 0.6]
    python3 audiocuts.py ab       --src M.mp4 --old 403.30-406.40 --new 403.64-406.40

`ab` transcribes the old and the new version of a cut with Whisper large-v3 so
you can hear-by-reading that no word was eaten. Do it for every cut you move.
"""
import argparse
import math
import re
import struct
import subprocess
import sys
import tempfile

# Silence trimming defaults chosen by the editor (2026-09-17) among three options:
# silences of 0.6 s or more are cut down to 0.2 s of breath. Only where the
# speaker is NOT on screen: on camera the jump would show.
SIL_TH = 0.60
SIL_KEEP = 0.20
SIL_DB = -34
FADE = 0.04          # micro fade on every splice, in and out


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("FAILED %s\n%s" % (" ".join(map(str, args))[:160], r.stderr[-1500:]))
    return r.stdout


# --------------------------------------------------------------- measuring
def energy(src, t0, dur, step=0.01, rate=16000):
    """[(t, dBFS)] RMS energy of the mono mix, one value per `step` seconds."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % t0, "-t", "%.3f" % dur,
                          "-i", str(src), "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
                         capture_output=True).stdout
    s = struct.unpack("<%dh" % (len(raw) // 2), raw)
    n = max(1, int(rate * step))
    out = []
    for k in range(len(s) // n):
        blk = s[k * n:(k + 1) * n]
        rms = (sum(x * x for x in blk) / len(blk)) ** .5
        out.append((round(t0 + k * step, 3), 20 * math.log10(max(1, rms) / 32768)))
    return out


def quietest(src, a, b, step=0.01):
    """(t, dB) of the quietest instant between a and b: where a cut belongs."""
    e = energy(src, a, b - a, step)
    return min(e, key=lambda x: x[1]) if e else (a, 0.0)


def classify_point(src, t, near=0.15):
    """What a cut point sits on: 'silence' (the 30 ms around it under -45 dB),
    'valley' (at least 12 dB under the loudest voice within +-near s: the dip
    between two words, a clean splice with the 40 ms fades), or 'ON VOICE'.
    Returns (verdict, level_at_point_dB, local_peak_dB)."""
    e = energy(src, max(0, t - near), 2 * near, 0.01)
    if not e:
        return "silence", -90.0, -90.0
    at = [db for tt, db in e if abs(tt - t) <= 0.015] or [min(e, key=lambda x: abs(x[0] - t))[1]]
    lvl = sum(at) / len(at)
    peak = max(db for _, db in e)
    if lvl < -45:
        return "silence", lvl, peak
    if peak - lvl >= 12:
        return "valley", lvl, peak
    return "ON VOICE", lvl, peak


def silences(src, a, b, th=SIL_TH, db=SIL_DB):
    """Silences >= th inside [a, b] of the source, in source time. Measured on
    the audio with silencedetect (never with -v error: it prints at info level)."""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-ss", "%.3f" % a, "-t", "%.3f" % (b - a),
         "-i", str(src), "-af", "silencedetect=noise=%ddB:d=%.2f" % (db, th),
         "-f", "null", "-"], capture_output=True, text=True).stderr
    st = [a + float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    en = [a + float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    while len(en) < len(st):
        en.append(b)                       # a silence that runs to the end of the range
    return [(x, y) for x, y in zip(st, en) if y - x >= th]


def trim_cut(src, i0, i1, th=SIL_TH, keep=SIL_KEEP, db=SIL_DB, cache=None):
    """Split [i0, i1] into sub-cuts that skip the excess of every long silence."""
    key = (round(i0, 3), round(i1, 3))
    if cache is not None and key in cache:
        sil = cache[key]
    else:
        sil = silences(src, i0, i1, th, db)
        if cache is not None:
            cache[key] = sil
    subs, cur = [], i0
    for (s, e) in sil:
        k = min(e, max(s, cur) + keep)
        if k - cur > 0.05:
            subs.append((cur, k))
        cur = max(cur, e)
    if i1 - cur > 0.05:
        subs.append((cur, i1))
    return subs or [(i0, i1)]


def remap(t, old, new):
    """Second t of the old cut list -> the same instant in the new cut list."""
    acc, master = 0.0, None
    for (a, z) in old:
        if t <= acc + (z - a):
            master = a + (t - acc)
            break
        acc += z - a
    if master is None:
        master = old[-1][1]
    acc = 0.0
    for (a, z) in new:
        if master < a:
            return round(acc, 3)            # fell into a removed silence
        if master <= z:
            return round(acc + (master - a), 3)
        acc += z - a
    return round(acc, 3)


def trim_silence(video, src, th=SIL_TH, keep=SIL_KEEP, db=SIL_DB, cache=None):
    """Copy of a video spec with long silences cut out of every NON-camera beat,
    anchors moved to the same point of the audio, and `cont` listing the splices
    that only removed a silence (a caption line may run across them). Camera
    beats are left untouched. Returns (video, seconds_removed)."""
    beats, removed = [], 0.0
    for b in video["beats"]:
        if b["kind"] == "cam" or not b["cuts"]:
            beats.append(dict(b))
            continue
        old, new_cuts, cont = b["cuts"], [], []
        for (i0, i1) in old:
            subs = trim_cut(src, i0, i1, th, keep, db, cache)
            cont.extend(a for a, _ in subs[1:])
            new_cuts.extend(subs)
        removed += sum(z - a for a, z in old) - sum(z - a for a, z in new_cuts)
        nb = dict(b, cuts=new_cuts, cont=cont)
        if b.get("anchors"):
            nb["anchors"] = [(dt, remap(bt, old, new_cuts)) for dt, bt in b["anchors"]]
        beats.append(nb)
    return dict(video, beats=beats), removed


# ---------------------------------------------------------------- writing
def concat_audio(src, segs, out, fade=FADE, bitrate="192k"):
    """One continuous audio file with every segment, in ONE ffmpeg pass (concat
    filter). Cutting each piece to AAC and gluing the files looks equivalent but
    is not: the codec adds ~25 ms of padding per file and with ten pieces the
    audio ends up 0.25 s behind the picture."""
    args, chains, labels = [], [], []
    for k, (i0, i1) in enumerate(segs):
        d = i1 - i0
        args += ["-ss", "%.3f" % i0, "-t", "%.3f" % d, "-i", str(src)]
        chains.append("[%d:a]afade=t=in:st=0:d=%.3f,afade=t=out:st=%.3f:d=%.3f,aresample=48000[a%d]"
                      % (k, fade, max(0.0, d - fade), fade, k))
        labels.append("[a%d]" % k)
    fc = ";".join(chains) + ";" + "".join(labels) + "concat=n=%d:v=0:a=1[out]" % len(segs)
    sh(["ffmpeg", "-v", "error", "-y"] + args +
       ["-filter_complex", fc, "-map", "[out]", "-c:a", "aac", "-b:a", bitrate,
        "-ar", "48000", "-ac", "2", str(out)])


def whisper_text(src, segs, model=None, prompt=None):
    """What Whisper large-v3 hears in the concatenation of `segs`."""
    from faster_whisper import WhisperModel
    m = model or WhisperModel("large-v3", device="cpu", compute_type="int8")
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        args, labels = [], []
        for k, (i0, i1) in enumerate(segs):
            args += ["-ss", "%.3f" % i0, "-t", "%.3f" % (i1 - i0), "-i", str(src)]
            labels.append("[%d:a]" % k)
        sh(["ffmpeg", "-v", "error", "-y"] + args + ["-filter_complex",
            "".join(labels) + "concat=n=%d:v=0:a=1[o]" % len(segs), "-map", "[o]",
            "-ac", "1", "-ar", "16000", tmp.name])
        segs_, _ = m.transcribe(tmp.name, language="en", word_timestamps=True, beam_size=5,
                                vad_filter=False, condition_on_previous_text=False,
                                initial_prompt=prompt)
        return " ".join("%s(%.2f)" % (w.word.strip(), w.probability) for s in segs_ for w in s.words)


# --------------------------------------------------------------------- cli
def _pair(s):
    a, b = s.split("-")
    return (float(a), float(b))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("energy"); e.add_argument("--src", required=True)
    e.add_argument("--at", type=float, required=True); e.add_argument("--win", type=float, default=0.4)
    e.add_argument("--step", type=float, default=0.01)
    g = sub.add_parser("gap"); g.add_argument("--src", required=True)
    g.add_argument("--between", type=float, nargs=2, required=True)
    c = sub.add_parser("check"); c.add_argument("--src", required=True)
    c.add_argument("points", type=float, nargs="+")
    s = sub.add_parser("silences"); s.add_argument("--src", required=True)
    s.add_argument("--range", type=float, nargs=2, required=True)
    s.add_argument("--th", type=float, default=SIL_TH); s.add_argument("--db", type=float, default=SIL_DB)
    b = sub.add_parser("ab"); b.add_argument("--src", required=True)
    b.add_argument("--old", nargs="+", type=_pair, required=True)
    b.add_argument("--new", nargs="+", type=_pair, required=True)
    b.add_argument("--prompt", default="Um, uh, hmm, I mean, yeah.",
                   help="initial prompt that makes Whisper write fillers instead of hiding them")
    a = ap.parse_args()

    if a.cmd == "energy":
        for t, db in energy(a.src, a.at - a.win / 2, a.win, a.step):
            print("%.3f  %6.1f dB  %s" % (t, db, "#" * max(0, int((db + 70) / 2))))
    elif a.cmd == "gap":
        t, db = quietest(a.src, *a.between)
        print("quietest point %.3f s (%.1f dB)" % (t, db))
    elif a.cmd == "check":
        for p in a.points:
            v, lvl, peak = classify_point(a.src, p)
            print("%.3f  %-8s  level %.1f dB · loudest voice nearby %.1f dB" % (p, v, lvl, peak))
    elif a.cmd == "silences":
        for x, y in silences(a.src, a.range[0], a.range[1], a.th, a.db):
            print("%.3f – %.3f  (%.2f s)" % (x, y, y - x))
    elif a.cmd == "ab":
        from faster_whisper import WhisperModel
        m = WhisperModel("large-v3", device="cpu", compute_type="int8")
        print("OLD:", whisper_text(a.src, a.old, m, a.prompt))
        print("NEW:", whisper_text(a.src, a.new, m, a.prompt))


if __name__ == "__main__":
    main()
