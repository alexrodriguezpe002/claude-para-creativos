#!/usr/bin/env python3
"""Passes 2 and 3: adjudicate the spots that pass 1 flagged.

Pass 2  re-transcribes each spot as an ISOLATED clip, so the surrounding
        sentence cannot bias the model into "fixing" the word.
Pass 3  repeats it on SLOWED audio. This is the pass that actually resolves
        final consonants (-s), unstressed syllables (nos/los/las) and short
        function words. A word that flips between tempos is unresolved by ASR
        and must be decided by grammar, not by the model.

  python verify_spots.py --audio out/audio.wav \
      --spots "0.0-3.0:conoces_vs_conocen,51.4-55.6:va_a_haber" \
      --tempos 1.0,0.6,0.5

With --pitch it also prints an F0 contour per spot, for question marks.
Pass --ref-question / --ref-statement (timestamps of a CONFIRMED question and a
CONFIRMED statement in the same video) so the contours are read against this
speaker, not against an absolute.

⚠️ Spanish: pronominal questions (qué / por qué / cuál / cómo) FALL at the end
exactly like statements. Falling does NOT mean "not a question". Only yes/no
questions reliably rise. Never remove a question mark on a falling contour alone.
"""
import argparse, os, re, subprocess, sys, tempfile, wave
import numpy as np


def cut(src, a, b, dst, tempo=1.0):
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", str(a), "-to", str(b), "-i", src]
    if abs(tempo - 1.0) < 1e-6:
        cmd += ["-c", "copy"]
    else:
        # atempo is valid in [0.5, 2.0]; chain for anything outside.
        chain, t = [], tempo
        while t < 0.5:
            chain.append("atempo=0.5")
            t /= 0.5
        chain.append(f"atempo={t:.4f}")
        cmd += ["-filter:a", ",".join(chain), "-ar", "16000", "-ac", "1"]
    cmd.append(dst)
    subprocess.run(cmd, check=True)


def f0(seg, sr, fmin=70, fmax=400):
    n, hop = int(0.04 * sr), int(0.01 * sr)
    out = []
    for i in range(0, max(0, len(seg) - n), hop):
        fr = seg[i:i + n] - seg[i:i + n].mean()
        if np.sqrt((fr ** 2).mean()) < 0.006:
            out.append(np.nan)
            continue
        c = np.correlate(fr, fr, "full")[n - 1:]
        lo, hi = int(sr / fmax), int(sr / fmin)
        if hi >= len(c):
            out.append(np.nan)
            continue
        k = lo + int(np.argmax(c[lo:hi]))
        out.append(sr / k if c[k] > 0.3 * c[0] else np.nan)
    return np.array(out)


def contour(wav_path, label, a, b, pad=0.06):
    w = wave.open(wav_path)
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    seg = x[int(max(0, a - pad) * sr):int((b + pad) * sr)]
    p = f0(seg, sr)
    v = p[~np.isnan(p)]
    if len(v) < 4:
        print(f"  {label:38s} not enough voiced frames")
        return
    h = len(v) // 2
    first, last = np.median(v[:h]), np.median(v[h:])
    tail = v[-max(3, len(v) // 3):]
    slope = np.polyfit(np.arange(len(tail)), tail, 1)[0]
    d = 100 * (last - first) / first
    mark = "RISES" if (d > 8 or slope > 1.5) else ("FALLS" if d < -8 else "flat")
    print(f"  {label:38s} {first:5.0f}Hz → {last:5.0f}Hz ({d:+5.1f}%) slope {slope:+5.1f}  {mark}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True, help="out/audio.wav from pass 1")
    ap.add_argument("--spots", required=True,
                    help='comma list of "start-end[:label]" in seconds')
    ap.add_argument("--tempos", default="1.0,0.6,0.5")
    ap.add_argument("--lang", default="es")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--pitch", action="store_true")
    ap.add_argument("--ref-question", default=None, help='"start-end" of a CONFIRMED question')
    ap.add_argument("--ref-statement", default=None, help='"start-end" of a CONFIRMED statement')
    args = ap.parse_args()

    spots = []
    for raw in args.spots.split(","):
        raw = raw.strip()
        if not raw:
            continue
        rng, _, label = raw.partition(":")
        a, b = [float(x) for x in rng.split("-")]
        spots.append((label or f"{a}-{b}", a, b))
    tempos = [float(t) for t in args.tempos.split(",")]

    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    tmp = tempfile.mkdtemp()

    for label, a, b in spots:
        print(f"\n=== {label}  [{a}–{b}s] ===")
        readings = {}
        for tempo in tempos:
            dst = os.path.join(tmp, "clip.wav")
            cut(args.audio, a, b, dst, tempo)
            segs, _ = model.transcribe(dst, language=args.lang, beam_size=8,
                                       vad_filter=False, condition_on_previous_text=False,
                                       word_timestamps=True)
            # faster-whisper returns a GENERATOR — materialise it, or a second pass
            # over it yields nothing and every tempo silently "agrees" on empty text.
            segs = list(segs)
            ws = [w for s in segs for w in (s.words or [])]
            words = [f"{w.word.strip()}({w.probability:.2f})" for w in ws]
            # Compare on normalised words only: punctuation and ellipses differ between
            # tempos for reasons that have nothing to do with which word was said.
            readings[tempo] = " ".join(
                re.sub(r"[^\w áéíóúñü]", "", w.word.strip().lower()) for w in ws).strip()
            print(f"  @{tempo:>4}x  {' '.join(words)}")
        uniq = set(readings.values())
        if len(uniq) > 1:
            print("  ⚠️ readings DISAGREE across tempos → ASR cannot resolve this. "
                  "Decide by grammar and flag it to the user as a listen-check.")
        else:
            print("  ✓ all tempos agree")

    if args.pitch:
        print("\n=== F0 contours ===")
        if args.ref_question:
            a, b = [float(x) for x in args.ref_question.split("-")]
            contour(args.audio, "REF confirmed QUESTION", a, b)
        if args.ref_statement:
            a, b = [float(x) for x in args.ref_statement.split("-")]
            contour(args.audio, "REF confirmed STATEMENT", a, b)
        for label, a, b in spots:
            contour(args.audio, label, a, b)
        print("\n  Reminder: in Spanish, qué/por qué/cuál/cómo questions FALL. "
              "Only yes/no questions rise. A fall is not evidence against a question mark.")


if __name__ == "__main__":
    sys.exit(main())
