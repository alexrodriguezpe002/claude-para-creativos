#!/usr/bin/env python3
"""Transcribe un audio o video con faster-whisper y escribe .txt (con tiempos) y .srt al lado del archivo."""
import argparse, sys, textwrap
from pathlib import Path

def ts(t, sep=","):
    h, r = divmod(int(t), 3600); m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{int((t - int(t)) * 1000):03d}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archivo")
    ap.add_argument("--idioma", default="es")
    ap.add_argument("--modelo", default="large-v3")
    ap.add_argument("--max-caracteres", type=int, default=42)
    a = ap.parse_args()
    src = Path(a.archivo).expanduser()
    if not src.exists():
        sys.exit(f"No existe: {src}")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("Falta faster-whisper: ver 'Preparar' en el SKILL.md")
    print(f"Cargando modelo {a.modelo}…", flush=True)
    model = WhisperModel(a.modelo, device="cpu", compute_type="int8")
    # La configuración probada en captions de trabajos reales: beam 5, tiempos por palabra, VAD con pausas de 400 ms
    segs, info = model.transcribe(str(src), language=a.idioma, beam_size=5, word_timestamps=True,
                                  vad_filter=True, vad_parameters={"min_silence_duration_ms": 400})
    txt, srt, n = [], [], 0
    for s in segs:
        txt.append(f"[{ts(s.start, '.')[:8]}] {s.text.strip()}")
        # partir en tarjetas de máx. 2 líneas usando los tiempos de cada palabra
        words = list(s.words or [])
        card, start = [], None
        def flush(end):
            nonlocal n, card, start
            if not card: return
            n += 1
            lines = textwrap.wrap(" ".join(w.word.strip() for w in card), a.max_caracteres)
            srt.append(f"{n}\n{ts(start)} --> {ts(end)}\n" + "\n".join(lines) + "\n")
            card, start = [], None
        for w in words:
            prueba = " ".join(x.word.strip() for x in card + [w])
            if card and len(textwrap.wrap(prueba, a.max_caracteres)) > 2:
                flush(card[-1].end)
            if start is None: start = w.start
            card.append(w)
            if w.word.strip().endswith((".", "?", "!")):
                flush(w.end)
        flush(words[-1].end if words else s.end)
        print(f"  {ts(s.end, '.')[:8]}", end="\r", flush=True)
    src.with_suffix(src.suffix + ".txt").write_text("\n".join(txt) + "\n", encoding="utf-8")
    src.with_suffix(src.suffix + ".srt").write_text("\n".join(srt), encoding="utf-8")
    print(f"\nListo: {len(txt)} frases, {n} subtítulos ({info.duration/60:.1f} min de audio)")
    print(src.with_suffix(src.suffix + ".txt")); print(src.with_suffix(src.suffix + ".srt"))

if __name__ == "__main__":
    main()
