#!/usr/bin/env python3
"""transcript.json with faster-whisper — the way around HyperFrames' own transcription
when it cannot run here (whisper.cpp missing, or failing to build on Windows), and the
speech self-test of `run_gates.py --doctor`.

    python3 transcribe_fw.py <video or audio> [-d <project>] [--model small] [--language en] [--force]
    python3 transcribe_fw.py --selftest [--json]      speak a test sentence, transcribe it, time it

Windows: `py -3` (or `python`) where this says python3.

It writes <project>/transcript.json in the shape `npx hyperframes transcribe` writes — a flat
list of words [{"text", "start", "end", "id"}] — which the gates, the caption grouping and the
beat plan read like any other. The model is the one caption timing already uses
(word_timing.py): faster-whisper `small`, int8 on the CPU, downloaded once (~490 MB, into the
Hugging Face cache of this user).

When `npx hyperframes init <dir> --video <file>` stops at the transcription step, create the
project with `--skip-transcribe` and run this on the project's video. An existing
transcript.json stays unless --force (then the old one is kept as transcript.json.bak).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _platform as P  # noqa: E402 — UTF-8 console and the Windows PATH
from _lang import T  # noqa: E402

DEFAULT_MODEL = "small"          # = word_timing.DEFAULT_MODEL: one download serves both
SELFTEST_TEXT = ("Testing the caption timing for the studio videos. "
                 "The quick brown fox jumps over the lazy dog. One, two, three, four, five.")
SELFTEST_WORDS = ("testing", "caption", "timing", "videos", "quick", "brown", "fox", "jumps",
                  "lazy", "dog", "one|1", "two|2", "three|3", "four|4", "five|5")   # a|b: either counts


def _norm(w):
    return "".join(c for c in w.lower() if c.isalnum() or c == "'")


def speak(text, wav):
    """Write `text` spoken by this computer's own voice to `wav`. (ok, how or why not)."""
    if sys.platform == "darwin" and shutil.which("say"):
        r = P.run_text(["say", "-o", wav, "--data-format=LEI16@16000", text], timeout=120)
        return (r.returncode == 0 and os.path.isfile(wav)), "macOS say"
    if P.IS_WIN:
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if not ps:
            return False, T("no hay PowerShell", "no PowerShell")
        q = wav.replace("'", "''")
        t = text.replace("'", "''")
        script = ("Add-Type -AssemblyName System.Speech; "
                  "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  "$s.SetOutputToWaveFile('%s'); $s.Speak('%s'); $s.Dispose()" % (q, t))
        r = P.run_text([ps, "-NoProfile", "-NonInteractive", "-Command", script], timeout=120)
        ok = r.returncode == 0 and os.path.isfile(wav) and os.path.getsize(wav) > 1000
        return ok, ("Windows SAPI" if ok else (r.stderr or r.stdout or "").strip()[-200:] or "SAPI")
    for tool in ("espeak-ng", "espeak"):
        if shutil.which(tool):
            r = P.run_text([tool, "-w", wav, text], timeout=120)
            return (r.returncode == 0 and os.path.isfile(wav)), tool
    return False, T("este sistema no tiene una voz sintética (say, SAPI, espeak)",
                    "this system has no speech synthesizer (say, SAPI, espeak)")


def load_model(name=DEFAULT_MODEL):
    from faster_whisper import WhisperModel
    return WhisperModel(name, device="cpu", compute_type="int8")


def words_of(model, media, language="en"):
    """[{"text", "start", "end"}] — every word with its own time, and the audio length."""
    segs, info = model.transcribe(media, language=language, word_timestamps=True, beam_size=5,
                                  vad_filter=False, condition_on_previous_text=False)
    out = []
    for s in segs:
        for w in (s.words or []):
            t = w.word.strip()
            if t:
                out.append({"text": t, "start": round(float(w.start), 3), "end": round(float(w.end), 3)})
    return out, float(getattr(info, "duration", 0.0) or 0.0)


def selftest(model_name=DEFAULT_MODEL):
    """Speak SELFTEST_TEXT, transcribe it, time it. A dict the doctor prints."""
    res = {"ok": False, "model": model_name, "voice": None, "heard": "", "matched": 0,
           "expected": len(SELFTEST_WORDS), "load_s": None, "transcribe_s": None, "audio_s": None,
           "error": None}
    tmp = tempfile.mkdtemp(prefix="dcv-asr-")
    try:
        wav = os.path.join(tmp, "selftest.wav")
        ok, how = speak(SELFTEST_TEXT, wav)
        res["voice"] = how
        if not ok:
            res["error"] = T("no pude generar el audio de prueba (%s)", "could not make the test audio (%s)") % how
            return res
        try:
            import faster_whisper  # noqa: F401
        except ImportError as e:
            res["error"] = T("faster-whisper no está instalado (%s)", "faster-whisper is not installed (%s)") % e
            return res
        t0 = time.time()
        try:
            model = load_model(model_name)
        except Exception as e:                      # no internet the first time, a broken cache…
            res["error"] = T("no pude cargar el modelo %s (%s)", "could not load the %s model (%s)") % (model_name, e)
            return res
        t1 = time.time()
        words, dur = words_of(model, wav)
        t2 = time.time()
        heard = [_norm(w["text"]) for w in words]
        res.update(load_s=round(t1 - t0, 2), transcribe_s=round(t2 - t1, 2), audio_s=round(dur, 2),
                   heard=" ".join(w["text"] for w in words),
                   matched=sum(1 for w in SELFTEST_WORDS if any(x in heard for x in w.split("|"))))
        res["ok"] = res["matched"] >= len(SELFTEST_WORDS) // 2
        if not res["ok"]:
            res["error"] = T("oyó otra cosa", "heard something else")
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def write_transcript(media, project, model_name=DEFAULT_MODEL, language="en", force=False):
    dest = os.path.join(project, "transcript.json")
    if os.path.isfile(dest) and not force:
        print(T("ya hay un transcript.json en %s — no lo toco (--force lo reemplaza y guarda el viejo como "
                "transcript.json.bak)", "%s already has a transcript.json — left as it is (--force replaces it and "
                "keeps the old one as transcript.json.bak)") % project)
        return 2
    print(T("· transcribiendo %s con faster-whisper %s (CPU)…", "· transcribing %s with faster-whisper %s (CPU)…")
          % (os.path.basename(media), model_name), flush=True)
    t0 = time.time()
    model = load_model(model_name)
    words, dur = words_of(model, media, language)
    if os.path.isfile(dest):
        shutil.copy2(dest, dest + ".bak")
    out = [dict(w, id="w%d" % i) for i, w in enumerate(words)]
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(T("escrito %s — %d palabras de %.1f s de audio en %.0f s",
            "wrote %s — %d words from %.1f s of audio in %.0f s") % (dest, len(out), dur, time.time() - t0))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("media", nargs="?", help="the project's video (or its audio)")
    ap.add_argument("-d", "--dir", help="the project folder (default: the media's folder)")
    ap.add_argument("--model", default=os.environ.get("CAPTIONS_TIMING_MODEL") or DEFAULT_MODEL)
    ap.add_argument("--language", default="en")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true", help="--selftest: one JSON line")
    a = ap.parse_args(argv)
    if a.selftest:
        res = selftest(a.model)
        if a.json:
            print(json.dumps(res, ensure_ascii=False))
        else:
            print(json.dumps(res, indent=1, ensure_ascii=False))
        return 0 if res["ok"] else 1
    if not a.media:
        ap.print_help()
        return 2
    media = os.path.abspath(a.media)
    if not os.path.isfile(media):
        print(T("no existe: %s", "not found: %s") % media)
        return 2
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        if P.ensure_modules(["faster_whisper", "numpy"], T("faster-whisper hace falta para transcribir",
                                                          "faster-whisper is needed to transcribe")):
            print(T("faster-whisper no está instalado: run_gates.py --doctor lo instala",
                    "faster-whisper is not installed: run_gates.py --doctor installs it"))
            return 2
    return write_transcript(media, os.path.abspath(a.dir or os.path.dirname(media)), a.model, a.language, a.force)


if __name__ == "__main__":
    sys.exit(main())
