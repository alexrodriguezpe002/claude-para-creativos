#!/usr/bin/env python3
"""Tiempo de cada palabra en un tramo del audio del corte (faster-whisper, modelo medium, español).

  python3 words.py "<proyecto>/AUDIO PARA IA/<corte>.wav" 40 11     # desde 40 s, 11 s de largo
  python3 words.py audio.wav 40 11 --desde-seccion 41.9            # además, tiempos relativos al inicio de la sección

Sirve para sincronizar cada momento de la gráfica con lo que dice la persona en cámara. El audio de AUDIO PARA IA
es el del corte que exportó el editor: si siguió editando después, los tiempos pueden haberse corrido.
"""
import subprocess, sys, tempfile
a = sys.argv[1:]
if len(a) < 3:
    print(__doc__); sys.exit(2)
src, t0, dur = a[0], float(a[1]), float(a[2])
rel = float(a[a.index("--desde-seccion") + 1]) if "--desde-seccion" in a else None
tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t0), "-t", str(dur), "-i", src, "-ac", "1", "-ar", "16000", tmp], check=True)
from faster_whisper import WhisperModel
m = WhisperModel("medium", device="cpu", compute_type="int8")
segs, _ = m.transcribe(tmp, language="es", word_timestamps=True, vad_filter=False)
n = 0
for s in segs:
    for w in s.words:
        st, en = w.start + t0, w.end + t0
        extra = f"   (sección {st - rel:5.2f}–{en - rel:5.2f})" if rel is not None else ""
        print(f"{st:7.2f}-{en:7.2f} {w.word.strip():18s} p={w.probability:.2f}{extra}"); n += 1
print(f"— {n} palabras")
sys.exit(0 if n else 2)
