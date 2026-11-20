#!/usr/bin/env python3
"""Clean the voice of a podcast clip on this computer (CPU only) — the step the user did with
Adobe Podcast's Enhance Speech — and say honestly whether the result reaches the bar or whether
Descript's Studio Sound is the better tool for this recording.

  audio_clean.py doctor [--fix]
  audio_clean.py clean INPUT [--out OUT.wav] [--json OUT.json] [--mux OUT.mp4] [options]
  audio_clean.py check RAW CLEANED [--json OUT.json]

INPUT is the edited clip (video or audio). The chain: DeepFilterNet3 (official standalone
build) -> 70 Hz high-pass + the voice EQ measured on the user's Adobe Podcast versions ->
one gain to -16 LUFS (true peak <= -1.5 dBTP) -> the quality check. Same length as the input,
sample-aligned. Exit codes: 0 good enough, 3 use Studio Sound (files still written),
2 nothing to clean (no audio / no voice), 1 could not run."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

from aclib import dsp, engines, qc  # noqa: E402
from aclib.util import Stop, T, exe, ffmpeg, run, say, tempdir, tilde  # noqa: E402

VERSION = "1.0"
# The voice EQ: what Adobe Podcast's Enhance Speech did to the user's voices on top of the
# noise removal, in the band where it does the same thing on every client (315 Hz - 6.3 kHz;
# below and above it differs per recording, so it is left alone). Fitted on 13 snippets
# (references/measured.md). dB at 1/3-octave centres; flat outside.
EQ_CENTERS = [200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000]
EQ_GAINS = [0.0, -0.2, -0.5, -0.5, -0.4, 0.1, 1.4, 2.9, 2.8, 0.8, -1.6, -2.9, -3.8, -4.9, -4.8, -2.8, -0.7]
DEFAULTS = dict(engine="dfn", atten="auto", hp=70.0, lufs=-16.0, tp=-1.5)


def _outputs(inp, a):
    stem = inp.with_suffix("")
    wav = Path(a.out) if a.out else Path(str(stem) + " clean.wav")
    js = Path(a.json) if a.json else wav.with_suffix(".json")
    return wav, js


def _print_verdict(res, check=False):
    met = res["metrics"]
    keys = [("noise_floor", T("ruido en las pausas", "noise in the pauses"), "dBFS"),
            ("input_noise_floor", T("  (entrada)", "  (input)"), "dBFS"),
            ("floor_unsteadiness", T("vaivén del fondo", "background unsteadiness"), "dB"),
            ("echo_tail", T("cola de eco", "echo tail"), "dB"),
            ("dropouts_per_min", T("caídas de voz por minuto", "voice dropouts per minute"), ""),
            ("input_snr", T("voz sobre el fondo en la entrada", "voice over background in the input"), "dB"),
            ("input_bandwidth_khz", T("ancho de banda de la entrada", "input bandwidth"), "kHz"),
            ("output_lufs", T("sonoridad", "loudness"), "LUFS"),
            ("output_true_peak", T("pico real", "true peak"), "dBTP")]
    for k, label, unit in keys:
        if met.get(k) is not None:
            say("  %-34s %7s %s" % (label, met[k], unit))
    if res["verdict"] == "ok" and check:
        say(T("✓ OK — el archivo limpio no muestra problemas (fondo, voz, eco).",
              "✓ OK — the cleaned file shows no problem (background, voice, echo)."))
    elif res["verdict"] == "ok":
        say(T("✓ ALCANZA — el fondo queda al nivel de Adobe Podcast y no se rompió nada en la voz "
              "(Studio Sound igual la dejaría más «de estudio»).",
              "✓ GOOD ENOUGH — the background is at Adobe Podcast's level and nothing in the voice broke "
              "(Studio Sound would still make it sound more like a studio mic)."))
    elif res["verdict"] == "review":
        say(T("! REVISAR — el resultado tiene esto:", "! REVIEW — the result shows:"))
        for r in res["reasons"]:
            say("   - " + qc.explain(r, T))
    elif res["verdict"] == "studio-sound":
        say(T("✗ NO ALCANZA → usá Descript Studio Sound para este clip:",
              "✗ NOT ENOUGH → use Descript's Studio Sound for this clip:"))
        for r in res["reasons"]:
            say("   - " + qc.explain(r, T))
    else:
        say("· " + qc.explain(res["verdict"], T))
    notes = {"input-noisy": T("la entrada era ruidosa", "the input was noisy"),
             "noisy-stretch": T("la entrada tenía un tramo muy ruidoso", "the input had a very noisy stretch"),
             "band-limited": T("la entrada no tenía agudos", "the input had no highs"),
             "input-clipped": T("la entrada estaba saturada", "the input was clipped")}
    for w in res.get("warnings", []):
        say(("  · " + notes[w]) if (check and w in notes) else ("  ! " + qc.explain(w, T)))


def cmd_clean(a):
    inp = Path(a.input)
    if not inp.is_file():
        raise Stop(T("No existe %s" % inp, "No such file: %s" % inp), code=2)
    wav, js = _outputs(inp, a)
    t0 = time.time()
    x, info = dsp.decode(inp)
    if a.start or a.duration:
        s = int(round((a.start or 0) * dsp.SR))
        e = s + int(round(a.duration * dsp.SR)) if a.duration else len(x)
        x = x[s:e]
    raw, how = dsp.to_mono(x)
    n = len(raw)
    if n < dsp.SR:
        raise Stop(T("El audio dura menos de 1 s.", "The audio is shorter than 1 s."), code=2)
    if n > 30 * 60 * dsp.SR:
        say(T("! más de 30 min: está pensado para el clip ya cortado; va a usar mucha memoria.",
              "! longer than 30 min: this is meant for the edited clip; it will use a lot of memory."))
    engine = a.engine
    with tempdir() as td:
        td = Path(td)
        src = td / "in.wav"
        dsp.write_float_mono(src, raw)
        if engine == "dfn":
            binary = engines.deep_filter_path()
            if not binary:
                say(T("! DeepFilterNet no tiene versión para este sistema; uso RNNoise.",
                      "! DeepFilterNet has no build for this system; using RNNoise."))
                engine = "rnnoise"
        if engine == "dfn":
            out = engines.run_deep_filter(binary, src, td / "o", None)       # full suppression, once
        else:
            out = engines.run_rnnoise(engines.rnnoise_path(), src.resolve(), (td / "rn.wav").resolve())
        pre = dsp.read_wav_mono(out)
    pre, shift = dsp.align(raw, pre)        # same clock and length as the input (DFN drops the last 30 ms)
    atten, curve = None, {}
    if engine == "dfn":
        if a.atten == "auto":
            atten, curve = dsp.choose_atten(raw, pre)
        else:
            atten = float(a.atten)
        if atten < 100:
            pre = dsp.mix_background(raw, pre, atten)
    y = pre if a.no_eq else dsp.apply_eq(pre, EQ_CENTERS, EQ_GAINS, hp_hz=a.hp)
    level = {}
    if a.lufs is not None:
        y, level = dsp.normalize(y, a.lufs, a.tp)
    wav.parent.mkdir(parents=True, exist_ok=True)
    dsp.write_wav(wav, y, stereo=not a.mono)
    res = qc.analyze(raw, y, pre)
    took = time.time() - t0
    doc = dict(tool="podcast-audio-clean", version=VERSION, input=str(inp), output=str(wav),
               input_audio=dict(info, downmix=how), seconds=round(n / dsp.SR, 3),
               settings=dict(engine=engine, atten_db=atten, atten_mode=a.atten if engine == "dfn" else None,
                             atten_curve={str(k): v for k, v in curve.items()}, eq=not a.no_eq,
                             highpass_hz=None if a.no_eq else a.hp, lufs=a.lufs, true_peak_max=a.tp,
                             stereo=not a.mono, start=a.start, duration=a.duration),
               level=level, engine_shift_samples=shift, processing_seconds=round(took, 1), **res)
    doc["reasons_text"] = [qc.explain(r, lambda es, en: en) for r in res["reasons"]]
    if a.mux:
        if not info["has_video"]:
            raise Stop(T("--mux necesita un video de entrada.", "--mux needs a video input."), code=1)
        if a.start or a.duration:
            raise Stop(T("--mux no se combina con --start/--duration.", "--mux cannot be combined with --start/--duration."))
        ffmpeg("-y", "-i", str(inp), "-i", str(wav), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
               "-c:a", "aac", "-b:a", "320k", "-ac", "2", "-movflags", "+faststart", str(a.mux))
        doc["mux"] = str(a.mux)
    js.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    say(T("Limpio: %s  (%.0f s de audio en %.0f s)" % (tilde(wav), n / dsp.SR, took),
          "Cleaned: %s  (%.0f s of audio in %.0f s)" % (tilde(wav), n / dsp.SR, took)))
    _print_verdict(res)
    say("##JSON## " + json.dumps(dict(verdict=res["verdict"], reasons=res["reasons"], wav=str(wav), json=str(js),
                                      mux=doc.get("mux"))))
    return {"ok": 0, "studio-sound": 3}.get(res["verdict"], 2)


def cmd_check(a):
    r, _ = dsp.decode(Path(a.raw))
    c, _ = dsp.decode(Path(a.cleaned))
    raw, _ = dsp.to_mono(r)
    cl, _ = dsp.to_mono(c)
    cl, k = dsp.align(raw, cl, max_shift=dsp.SR)
    res = qc.analyze(raw, cl, judge_input=False)
    res["metrics"]["aligned_by_samples"] = int(k)
    doc = dict(tool="podcast-audio-clean", version=VERSION, raw=a.raw, cleaned=a.cleaned, **res)
    if a.json:
        Path(a.json).write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    _print_verdict(res, check=True)
    say("##JSON## " + json.dumps(dict(verdict=res["verdict"], reasons=res["reasons"], json=a.json)))
    return {"ok": 0, "review": 3}.get(res["verdict"], 2)


def cmd_doctor(a):
    import importlib
    import subprocess
    ok = True

    def line(good, what, detail=""):
        say("%s %s%s" % ("✓" if good else "✗", what, ("  — " + detail) if detail else ""))

    line(sys.version_info >= (3, 8), "Python %d.%d" % sys.version_info[:2],
         "" if sys.version_info >= (3, 8) else T("necesita 3.8+", "needs 3.8+"))
    for prog in ("ffmpeg", "ffprobe"):
        p = exe(prog)
        line(bool(p), prog, p or T("instalá ffmpeg (Windows: winget install Gyan.FFmpeg; Mac: brew install ffmpeg)",
                                   "install ffmpeg (Windows: winget install Gyan.FFmpeg; Mac: brew install ffmpeg)"))
        ok &= bool(p)
    if exe("ffmpeg"):
        f = run([exe("ffmpeg"), "-hide_banner", "-filters"], check=False).stdout or ""
        line("arnndn" in f, T("filtro arnndn de ffmpeg (RNNoise, el plan B)", "ffmpeg arnndn filter (RNNoise, the fallback)"),
             "" if "arnndn" in f else T("este ffmpeg no lo trae; DeepFilterNet igual funciona",
                                        "this ffmpeg lacks it; DeepFilterNet still works"))
    try:
        np_ = importlib.import_module("numpy")
    except ImportError:
        np_ = None
    if a.fix and not np_:
        in_venv = getattr(sys, "base_prefix", sys.prefix) != sys.prefix     # a venv refuses --user
        say(T("· instalando numpy…", "· installing numpy…"))
        subprocess.run([sys.executable, "-m", "pip", "install", *([] if in_venv else ["--user"]), "numpy"])
        importlib.invalidate_caches()
        try:
            np_ = importlib.import_module("numpy")
        except ImportError:
            np_ = None
    line(bool(np_), "numpy", getattr(np_, "__version__", "") if np_ else T("corré doctor --fix", "run doctor --fix"))
    ok &= bool(np_)
    spec = engines.deep_filter_spec()
    if not spec:
        line(False, "DeepFilterNet", T("no hay versión para %s/%s: se usará RNNoise" % engines.platform_key(),
                                       "no build for %s/%s: RNNoise will be used" % engines.platform_key()))
    else:
        b = engines.deep_filter_path(download=bool(a.fix))
        works = False
        if b:
            r = run([b, "--version"], check=False)
            works = r.returncode == 0
        line(bool(b) and works, "DeepFilterNet (deep-filter 0.5.6)",
             (tilde(b) if works else T("está pero no arranca (¿antivirus?): %s" % tilde(b),
                                        "present but does not start (antivirus?): %s" % tilde(b)))
             if b else T("falta — doctor --fix lo baja (27 MB, SHA-256)", "missing — doctor --fix downloads it (27 MB, SHA-256)"))
        ok &= bool(b) and works
    m = engines.rnnoise_path(download=bool(a.fix))
    line(bool(m), "RNNoise std.rnnn", tilde(m) if m else T("falta — doctor --fix lo baja", "missing — doctor --fix downloads it"))
    say("")
    say(T("Todo listo.", "All set.") if ok else T("Falta algo (arriba).", "Something is missing (above)."))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="audio_clean.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("doctor", help="check (and --fix) what this needs")
    d.add_argument("--fix", action="store_true")
    c = sub.add_parser("clean", help="clean the voice of a clip and check it")
    c.add_argument("input", help="the edited clip: video (MP4/MOV) or audio (WAV/M4A/MP3)")
    c.add_argument("--out", help="the cleaned WAV (default: '<input name> clean.wav' next to the input)")
    c.add_argument("--json", help="the check's JSON (default: next to the WAV, same name)")
    c.add_argument("--mux", help="also write a copy of the video with the cleaned audio (video stream untouched)")
    c.add_argument("--engine", choices=["dfn", "rnnoise"], default=DEFAULTS["engine"])
    c.add_argument("--atten", default=DEFAULTS["atten"], type=lambda v: v if v == "auto" else float(v),
                   help="how far the background goes down, in dB: 'auto' (default: the mildest of 12-40 dB that "
                        "reaches the clean floor) or a number (100 = remove everything)")
    c.add_argument("--no-eq", action="store_true", help="denoise only: no high-pass, no voice EQ")
    c.add_argument("--hp", type=float, default=DEFAULTS["hp"], help="high-pass in Hz (default 70)")
    c.add_argument("--lufs", type=lambda s: None if s.lower() in ("keep", "none") else float(s),
                   default=DEFAULTS["lufs"], help="integrated loudness of the output (default -16; 'keep' = no gain)")
    c.add_argument("--tp", type=float, default=DEFAULTS["tp"], help="true-peak ceiling in dBTP (default -1.5)")
    c.add_argument("--mono", action="store_true", help="write a mono WAV (default: stereo, both channels the same)")
    c.add_argument("--start", type=float, help="only from this second (for a test excerpt)")
    c.add_argument("--duration", type=float, help="only this many seconds (for a test excerpt)")
    k = sub.add_parser("check", help="only the quality check, on any original + cleaned pair (e.g. a Studio Sound export)")
    k.add_argument("raw")
    k.add_argument("cleaned")
    k.add_argument("--json")
    a = ap.parse_args(argv)
    return {"doctor": cmd_doctor, "clean": cmd_clean, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
