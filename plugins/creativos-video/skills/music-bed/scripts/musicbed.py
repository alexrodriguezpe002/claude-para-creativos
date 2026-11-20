#!/usr/bin/env python3
"""Background music under a voice: find it on Epidemic Sound, mix it by loudness,
prove the voice is still understood.

    python3 musicbed.py search "reflective cinematic piano" [--bpm 70-100] [--vocals] [--limit 15]
    python3 musicbed.py preview <publicSlug-or-track-url> --out preview.mp3
    python3 musicbed.py mix   --voice voice.m4a --song song.wav --out mix.m4a --total 74.4 --speech-end 72.2 [--start 8]
    python3 musicbed.py check --voice voice.m4a --mix mix.m4a          # Whisper on both, diff
            [--model small]   (default small: the caption-timing model, ~490 MB once, fast on a CPU;
                               large-v3 is the strongest — 3 GB, several times slower on a laptop CPU)

    # Client B: a steady bed 18-24 dB under the voice, no ducking, the song's own
    # swings levelled, -16 LUFS / -1.5 dBTP
    python3 musicbed.py mix --voice v.wav --song CLB-...wav --out mix.wav --total 36.16 --speech-end 35.9 \
        --start 18.4 --voice-lufs -16 --gap 20 --steady --level --tp -1.5

Why loudness and not peaks: a mastered song has far less peak-to-loudness range
than a voice, so "voice -6 / music -18 peak" says little about what you hear.
Instagram, TikTok and YouTube normalize by LUFS, so the mix is set in LUFS:
voice at -15 LUFS, music 10 LU under the voice WHILE THE SPEAKER TALKS, gently
ducked by the voice (so it rises in pauses and in the tail), a -3 dB dip at
2.5 kHz where consonants live, limiter at -1 dBTP. The editor (2026-09-24) wants the
music present, never "casi inexistente", and never on top of the voice.

The search endpoint is the one the public Epidemic Sound site uses; it answers
without a login. The preview MP3 is for listening and comparing only: the file
that goes in the video is the WAV the user downloads from the team's account.
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")   # Windows consoles default to cp1252
    except (AttributeError, ValueError):
        pass

VOICE_LUFS = -15.0
BED_GAP = 10.0        # LU the music sits under the voice while the speaker talks
DUCK_DB = 3.5         # roughly how much the voice pushes the music down

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit("FAILED %s\n%s" % (" ".join(map(str, args))[:160], r.stderr[-1500:]))
    return r.stdout


# ------------------------------------------------------------------ search
def search(term, limit=20, bpm=None, vocals=False):
    """Tracks from Epidemic Sound's public search. Results keep the site's
    ranking. BPM is normalized: salsa, mambo and guaracha are often tagged at
    double tempo (198 for a 99 BPM track), so anything over 140 is halved."""
    q = {"term": term, "limit": min(100, limit)}
    if bpm:
        q["bpm"] = bpm
    url = "https://www.epidemicsound.com/json/search/tracks/?" + urllib.parse.urlencode(q)
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())
    ents = d.get("entities", {}).get("tracks", {})
    out = []
    for h in d.get("meta", {}).get("hits", []):
        t = ents.get(str(h["trackId"]))
        if not t or t.get("isSfx"):
            continue
        if t.get("hasVocals") and not vocals:
            continue
        arts = ", ".join(a["name"] for a in (t.get("creatives") or {}).get("mainArtists", []))
        b = t.get("bpm") or 0
        out.append(dict(
            title=t["title"], artist=arts, bpm=b, bpm_real=b / 2 if b > 140 else b,
            energy=t.get("energyLevel"), length=t.get("length"),
            moods=[m["displayTag"] for m in t.get("moods", [])],
            genres=[g["displayTag"] for g in t.get("genres", []) if g.get("fatherTag") != "Production Genre"],
            vocals=t.get("hasVocals"), slug=t.get("publicSlug"),
            link="https://www.epidemicsound.com/track/%s/" % t.get("publicSlug"),
            preview=((t.get("stems") or {}).get("full") or {}).get("lqMp3Url")))
    return out


def preview(slug_or_url, out):
    """Download the low-quality full-length preview of one track (listening only)."""
    slug = slug_or_url.rstrip("/").split("/")[-1]
    for t in search(slug, limit=100, vocals=True):
        if t["slug"] == slug:
            break
    else:
        raise SystemExit("track %s not found by search; search by artist name instead" % slug)
    urllib.request.urlretrieve(t["preview"], out)
    print("%s — %s -> %s" % (t["title"], t["artist"], out))


# --------------------------------------------------------------------- mix
def loudness(path, extra=None):
    """(integrated LUFS, true peak dBTP) of a file, or of `extra` filter applied to it."""
    af = "ebur128=peak=true" if not extra else extra + ",ebur128=peak=true"
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
                          "-af", af, "-f", "null", "-"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stderr
    i = float(re.findall(r"I:\s*(-?[\d.]+) LUFS", err)[-1])
    tp = float(re.findall(r"Peak:\s*(-?[\d.inf]+)", err)[-1])
    return i, tp


def level_song(song, start, total, out, window=3.0, smooth=2.0, lo=-6.0, hi=8.0):
    """Flatten the song's own loudness swings over [start, start+total] (a steady bed: one
    that swells is ridden back down, one that thins out partway is brought back up).
    RMS over `window` s, gain towards the segment's median, clamped to [lo, hi] dB and
    smoothed over `smooth` s so it never pumps. Writes a float WAV and returns the gain
    range applied, in dB."""
    import numpy as np
    sr = 48000
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % start, "-t", "%.3f" % total,
                          "-i", str(song), "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)
    hop = int(0.1 * sr)
    mono = x.mean(1)
    n = len(mono) // hop
    p = (mono[:n * hop].reshape(n, hop) ** 2).mean(1)
    w = max(1, int(window / 0.1))
    db = 10 * np.log10(np.convolve(p, np.ones(w) / w, mode="same") + 1e-12)
    g = np.clip(np.median(db) - db, lo, hi)
    s = max(1, int(smooth / 0.1))
    g = np.convolve(np.pad(g, (s, s), mode="edge"), np.ones(s) / s, mode="same")[s:-s]
    gs = np.interp(np.arange(len(x)), np.arange(n) * hop + hop / 2, g)
    y = (x * (10 ** (gs / 20))[:, None]).astype(np.float32)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "-",
                    "-c:a", "pcm_f32le", str(out)], input=y.tobytes(), check=True)
    return float(g.min()), float(g.max())


def mix(voice, song, out, total, speech_end, voice_lufs=VOICE_LUFS, gap=BED_GAP,
        duck=DUCK_DB, bed_tmp=None, label=None, start=0.0, steady=False, level=False, tp=-1.0,
        fade_out=None, sfx=None, fade_curve="tri"):
    """out = voice + song, `total` seconds long (speech plus the tail).

    The ducking depends on how much the speaker talks in each video, so the bed
    level is measured under the voice and corrected once instead of guessed: in
    the first Prospect P pass the ducking pushed the music 2.5 dB lower than planned.
    `start` skips the first seconds of the song (a long or empty intro).
    `steady` drops the sidechain (a constant bed); `level` flattens the
    song's own swings first (level_song); `tp` is the true-peak ceiling in dBTP.
    `fade_out` sets the length of the closing fade, which always ends at `total`
    (default: 1.2-2 s, from the tail after the speech); `fade_curve` is its shape
    (ffmpeg afade: "tri" linear, the default; "qsin" equal power, Premiere's
    Constant Power, measured on CLA ep4). `sfx` is a list of
    (file, seconds): each effect plays at its own level from that time, summed
    before the limiter and left out of the bed measurement (CLA's teaser CTA).
    Returns a dict with the measurements."""
    import pathlib
    voice, song, out = pathlib.Path(voice), pathlib.Path(song), pathlib.Path(out)
    label = label or song.stem
    bed_tmp = pathlib.Path(bed_tmp) if bed_tmp else out.with_name("_bed.wav")
    levelled = None
    if level:
        levelled = out.with_name("_levelled.wav")
        lg = level_song(song, start, total, levelled)
        print("   levelled %s: gain %.1f to %+.1f dB" % (label, lg[0], lg[1]))
        song, start = levelled, 0.0
    if steady:
        duck = 0.0
    # alimiter works on samples: 0.4 dB of margin for the true peak; the default stays the old 0.89
    limit = "0.89" if tp == -1.0 else "%.4f" % (10 ** ((tp - 0.4) / 20))
    vi, _ = loudness(voice)
    trim = "atrim=0:%.3f" % total if not start else "atrim=%.3f:%.3f" % (start, start + total)
    mi, _ = loudness(song, trim)
    gv = voice_lufs - vi
    gm = (voice_lufs - gap + duck) - mi          # un-ducked music sits `duck` over its level under the voice
    fo = float(fade_out) if fade_out else min(2.0, max(1.2, total - speech_end))
    sfx = [(pathlib.Path(f), float(t)) for f, t in (sfx or [])]
    sfx_in = [a for f, _ in sfx for a in ("-i", str(f))]
    sfx_graph = "".join("[%d:a]aresample=48000,aformat=channel_layouts=stereo,adelay=delays=%d:all=1[s%d];"
                        % (2 + i, round(t * 1000), i) for i, (_, t) in enumerate(sfx))
    sfx_pads = "".join("[s%d]" % i for i in range(len(sfx)))

    def run(gm):
        graph = ((
            "[0:a]aresample=48000,highpass=f=70,volume=%.2fdB,apad=whole_dur=%.3f,"
            "asplit=2[v][key];"
            "[1:a]aresample=48000,%s,asetpts=PTS-STARTPTS,volume=%.2fdB,"
            "equalizer=f=2500:t=o:w=1.4:g=-3,"
            "afade=t=in:st=0:d=0.35,afade=t=out:%sst=%.3f:d=%.3f[m];"
            + ("[key]anullsink;[m]anull[md];" if steady else
               "[m][key]sidechaincompress=threshold=0.06:ratio=2:attack=40:release=650:"
               "knee=6:detection=rms[md];")
            + sfx_graph
            + "[v][md]%samix=inputs=%d:duration=first:normalize=0,"
            "alimiter=limit=%s:level=false:attack=5:release=60[out]")
            % (gv, total, trim, gm, "" if fade_curve == "tri" else "curve=%s:" % fade_curve,
               total - fo, fo, sfx_pads, 2 + len(sfx), limit))
        # check: the music alone, exactly as it sits in the mix, while the speaker talks
        bed = graph.replace("[v][md]%samix=inputs=%d:duration=first:normalize=0," % (sfx_pads, 2 + len(sfx)),
                            "[v]anullsink;" + "".join("[s%d]anullsink;" % i for i in range(len(sfx))) + "[md]")
        sh(["ffmpeg", "-v", "error", "-y", "-i", str(voice), "-i", str(song), *sfx_in,
            "-filter_complex", bed, "-map", "[out]", "-t", "%.3f" % speech_end,
            "-c:a", "pcm_s16le", str(bed_tmp)])
        bi, _ = loudness(bed_tmp)
        bed_tmp.unlink()
        return graph, bi

    graph, bi = run(gm)
    target = voice_lufs - gap
    if abs(bi - target) > 0.4:
        gm += target - bi
        graph, bi = run(gm)
    codec = (["-c:a", "pcm_s24le"] if out.suffix.lower() == ".wav" else ["-c:a", "aac", "-b:a", "256k"])
    sh(["ffmpeg", "-v", "error", "-y", "-i", str(voice), "-i", str(song), *sfx_in,
        "-filter_complex", graph, "-map", "[out]", "-t", "%.3f" % total,
        *codec, "-ar", "48000", "-ac", "2", str(out)])
    if levelled:
        levelled.unlink()
    fi, ftp = loudness(out)
    print("   music %s · voice %.1f LUFS · music under the voice %.1f LUFS (%.1f LU below) · "
          "mix %.1f LUFS, peak %.1f dBTP%s%s" % (label, voice_lufs, bi, voice_lufs - bi, fi, ftp,
                                                " · steady bed, no ducking" if steady else "",
                                                "".join(" · %s at %.2fs" % (f.name, t) for f, t in sfx)))
    return dict(voice_lufs=voice_lufs, bed_lufs=bi, mix_lufs=fi, mix_peak=ftp)


# ------------------------------------------------------------------- check
CHECK_MODEL = "small"   # 2026-10-03: was large-v3 (3 GB, slow on a laptop CPU); small = caption timing's model


def check(voice, mixed, model=CHECK_MODEL):
    """Whisper on the voice alone and on the mix; every word the mix loses is
    listed. Expected losses: 'uh'/'um' (they sink under the music, harmless).
    Anything else gets a second pass on the short clip before blaming the music
    (with --model large-v3 when it is on this computer: a smaller model mishears more
    under music, so a "lost" word from small is a question, not a verdict)."""
    from faster_whisper import WhisperModel
    print("faster-whisper %s on the voice and on the mix (CPU)…" % model, flush=True)
    m = WhisperModel(model, device="cpu", compute_type="int8")
    norm = lambda s: re.sub(r"[^a-z0-9']", "", s.lower())

    def words(f):
        segs, _ = m.transcribe(str(f), language="en", word_timestamps=True, beam_size=5,
                               vad_filter=False, condition_on_previous_text=False)
        return [(norm(w.word), w.start, w.word.strip()) for s in segs for w in s.words if norm(w.word)]
    a, b = words(voice), words(mixed)
    ops = [o for o in difflib.SequenceMatcher(a=[x[0] for x in a], b=[x[0] for x in b], autojunk=False).get_opcodes()
           if o[0] != "equal"]
    print("voice alone %d words · mix %d · %d difference(s)" % (len(a), len(b), len(ops)))
    for t, i1, i2, j1, j2 in ops:
        print("   %6.2fs %-7s voice [%s]  mix [%s]" % (a[min(i1, len(a) - 1)][1], t,
              " ".join(x[2] for x in a[i1:i2]), " ".join(x[2] for x in b[j1:j2])))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("term")
    s.add_argument("--bpm", help="e.g. 70-100"); s.add_argument("--vocals", action="store_true")
    s.add_argument("--limit", type=int, default=15); s.add_argument("--min-length", type=int, default=0)
    s.add_argument("--json", action="store_true")
    p = sub.add_parser("preview"); p.add_argument("track"); p.add_argument("--out", required=True)
    m = sub.add_parser("mix"); m.add_argument("--voice", required=True); m.add_argument("--song", required=True)
    m.add_argument("--out", required=True); m.add_argument("--total", type=float, required=True)
    m.add_argument("--speech-end", type=float, required=True)
    m.add_argument("--voice-lufs", type=float, default=VOICE_LUFS); m.add_argument("--gap", type=float, default=BED_GAP)
    m.add_argument("--start", type=float, default=0.0, help="start the song this many seconds in")
    m.add_argument("--steady", action="store_true", help="no ducking: a constant bed")
    m.add_argument("--level", action="store_true", help="flatten the song's own swings first")
    m.add_argument("--tp", type=float, default=-1.0, help="true-peak ceiling, dBTP (CLB: -1.5)")
    m.add_argument("--fade-out", type=float, default=None,
                   help="length of the closing fade in seconds, ending at --total (default 1.2-2 s)")
    m.add_argument("--fade-curve", choices=["tri", "qsin"], default="tri",
                   help="shape of the closing fade: tri = linear (default), qsin = equal power (CLA)")
    m.add_argument("--sfx", action="append", default=[], metavar="FILE@SECONDS",
                   help="a sound effect at its own level from that time (repeatable; CLA teaser CTA)")
    c = sub.add_parser("check"); c.add_argument("--voice", required=True); c.add_argument("--mix", required=True)
    c.add_argument("--model", default=CHECK_MODEL,
                   help="faster-whisper model (default small; large-v3 = strongest, 3 GB, slow on a CPU)")
    a = ap.parse_args()

    if a.cmd == "search":
        res = [t for t in search(a.term, a.limit * 3, a.bpm, a.vocals) if (t["length"] or 0) >= a.min_length][:a.limit]
        if a.json:
            print(json.dumps(res, indent=1))
            return
        for i, t in enumerate(res, 1):
            print("%2d. %s — %s · %s BPM%s · %s · %d:%02d · %s\n    %s\n    genres: %s" % (
                i, t["title"], t["artist"], t["bpm"], " (or %g half-time)" % t["bpm_real"] if t["bpm_real"] != t["bpm"] else "",
                t["energy"], (t["length"] or 0) // 60, (t["length"] or 0) % 60, ", ".join(t["moods"][:4]),
                t["link"], ", ".join(t["genres"][:4])))
    elif a.cmd == "preview":
        preview(a.track, a.out)
    elif a.cmd == "mix":
        sfx = []
        for spec in a.sfx:
            f, sep, t = spec.rpartition("@")
            if not sep:
                raise SystemExit("--sfx wants FILE@SECONDS, got %r" % spec)
            sfx.append((f, float(t)))
        mix(a.voice, a.song, a.out, a.total, a.speech_end, a.voice_lufs, a.gap, start=a.start,
            steady=a.steady, level=a.level, tp=a.tp, fade_out=a.fade_out, sfx=sfx,
            fade_curve=a.fade_curve)
    elif a.cmd == "check":
        check(a.voice, a.mix, a.model)


if __name__ == "__main__":
    main()
