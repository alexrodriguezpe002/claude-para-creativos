#!/usr/bin/env python3
"""Second ASR pass on the doubtful words of a clip — it reports, it never edits.

    python3 second_pass.py <project-dir> [--below 0.5] [--at 23.4,51.2] [--model large-v3]

The doubtful spots: every word of transcript.json under --below (Whisper's own
probability), every word the voice pass (video-quality-gates word_timing.py) heard
under the profile's captions.timing.missing_p — the words the grouping script and the
gate list as DUDOSAS / caption-doubtful-word — and the times given with --at. For each,
it cuts the clip's audio from 3 s before to 3 s after, runs faster-whisper on that piece
alone (no initial_prompt: a prompt is what it hallucinates back on silence) and prints
what it hears there. The model is the strongest one this computer already has —
large-v3, else medium, else small (never downloaded here: --model asks for one).

How to read it — the rules are in podcast-captions SKILL.md, "Text":
* what is SAID decides which words appear; the cleaned text decides spelling and
  punctuation. A word both passes hear goes on the cards (put it in the text); a text
  word neither hears comes out;
* the second pass decides the WORD, never the time: in CLB ep3 S1 it put "and" 0.75 s
  early. Times are the voice pass's (word_timing.py);
* when it hears nothing, noise or a prompt-like phrase where the first pass had words,
  those words were a hallucination (a speaker restarting a sentence) and are not
  captioned;
* CLC ep1 S3 (2026-10-03): "who" (p 0.55 with small, 0.91 with large-v3 — the approved
  text had it) is said; "this weekend" after "extra money" is heard three different ways
  ("this weekend", "as we get", "planets we get") — doubtful, left out, said so.
"""

import argparse
import os
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

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from group_captions import whisper_words, C, WT  # noqa: E402

CONTEXT = 3.0
STRONGEST = ("large-v3", "medium", "small")


def load_model(name=None):
    from faster_whisper import WhisperModel
    if name:
        return name, WhisperModel(name, device="cpu", compute_type="int8")
    for cand in STRONGEST:
        try:
            return cand, WhisperModel(cand, device="cpu", compute_type="int8", local_files_only=True)
        except Exception:
            continue
    return "small", WhisperModel("small", device="cpu", compute_type="int8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project")
    ap.add_argument("--below", type=float, default=0.5)
    ap.add_argument("--at", default="", help="times in seconds, comma-separated")
    ap.add_argument("--model", default=None, help="faster-whisper model (default: the strongest one already here)")
    ap.add_argument("--no-voice-pass", action="store_true", help="only transcript.json and --at")
    args = ap.parse_args()
    d = C.project_dir(["x", args.project])
    html = C.read_html(d)
    src = C.video_path(d, html)
    voice = C.clean_voice_file(d)
    if voice:
        src = voice
    if not src:
        sys.exit(T("no encontré el video del proyecto", "could not find the project's video"))
    ww, how = whisper_words(d)
    spots = [(w["s"], w["t"], w["p"], "transcript.json") for w in ww if w["p"] < args.below]
    if not args.no_voice_pass:
        wt = WT.measure(d, html)
        if wt["status"] == "measured":
            cut = float(WT.timing_cfg().get("missing_p", 0.70))
            spots += [(w["s"], w["t"], w.get("p", 1.0), T("voz (%s)", "voice (%s)") % wt["model"])
                      for w in wt["words"] if w.get("p", 1.0) < cut]
    for t in [x for x in args.at.split(",") if x.strip()]:
        spots.append((float(t), "(--at)", None, T("pedido", "requested")))
    if not spots:
        print(T("nada dudoso: ninguna palabra bajo p=%.2f", "nothing doubtful: no word under p=%.2f") % args.below)
        return 0
    try:
        name, model = load_model(args.model)
    except ImportError:
        sys.exit(T("faster-whisper no está instalado (pip install faster-whisper) — sin él no hay segundo pase", "faster-whisper is not installed (pip install faster-whisper) — without it there is no second pass"))
    print(T("segundo pase con faster-whisper %s, ±%.0f s alrededor de cada palabra dudosa, sin prompt", "second pass with faster-whisper %s, ±%.0f s around each doubtful word, no prompt") % (name, CONTEXT))
    spots.sort()
    done = []
    for t, word, p, origin in spots:
        if any(abs(t - x) < 1.0 for x in done):
            continue
        done.append(t)
        a = max(0.0, t - CONTEXT)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
            wav = fh.name
        try:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "%.3f" % a,
                            "-t", "%.3f" % (2 * CONTEXT), "-i", src, "-vn", "-ac", "1", "-ar", "16000",
                            "-y", wav], check=True)
            segs, _ = model.transcribe(wav, beam_size=5, word_timestamps=True,
                                       condition_on_previous_text=False)
            heard = []
            for sg in segs:
                for w in sg.words or []:
                    heard.append("%s(%.2f, p%.2f)" % (w.word.strip(), a + w.start, w.probability))
        finally:
            os.unlink(wav)
        first = [w["t"] for w in ww if a <= (w["s"] or 0) <= a + 2 * CONTEXT]
        print("@%.2f  %s%s  [%s]" % (t, word, (" (p=%.2f)" % p) if p is not None else "", origin))
        print("   transcript.json: %s" % " ".join(first))
        print(T("   segundo pase:    %s", "   second pass:     %s") % (" ".join(heard) or T("(nada)", "(nothing)")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
