#!/usr/bin/env python3
"""Gate de un clip generado por IA (Kling, Seedance, Veo…): imprime números, no opiniones.

  python3 qc_clip.py clip.mp4 --modo fija|orbita|acercamiento|bajada|libre [--min-dur 3] [--fps 24]
                     [--res 1076x1928] [--sin-cara] [--out carpeta_revision] [--solo-medir]

Mide:
  duración/fps/tamaño contra lo pedido
  saltos      cuadro a cuadro que cambian >3× la mediana (cortes, glitches)
  deriva      desplazamiento global primer→último cuadro (en `fija` tiene que ser ~0)
  movimiento  cambio medio por cuadro (en órbita/acercamiento/bajada tiene que haberlo; en fija/libre, si la
              mediana por medio segundo baja de 0,30 el clip parece una foto y FALLA)
  destello    el punto más brillante (luminancia suavizada), máximo contra el inicio: una zona
              que se "quema" hasta casi blanco
  sin cara    (con --sin-cara) piel que entra por el borde de arriba o por la mitad alta de los
              costados y que en los primeros cuadros no estaba: una cabeza que se mete en cuadro.
              Solo ve lo que ENTRA; una cara que ya está en la imagen de partida se ve al revisarla.
Deja una tira de 12 cuadros y los cuadros del medio y del final en --out para mirar a ojo.
NO mide (revisar siempre en la tira): órganos que se hinchan o deforman, y si el movimiento es el
pedido (un "crane down" que salió acercamiento pasa todos los números).

Salida: 0 = PASA · 1 = FALLA (algún umbral) · 2 = no se pudo leer el clip (nunca pasa en silencio).
Umbrales calibrados el 2026-09-28 con clips de un cliente médico (ver el SKILL.md de higgsfield-imagen-video).
"""
import json
import pathlib
import subprocess
import sys

import numpy as np

a = sys.argv[1:]
if not a:
    print(__doc__); sys.exit(2)
path = a[0]
opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
modo = opt("--modo", "libre")
min_dur = float(opt("--min-dur", 0))
fps_req = opt("--fps")
res_req = opt("--res")
out = pathlib.Path(opt("--out", str(pathlib.Path(path).with_suffix("")) + "_qc"))
solo_medir = "--solo-medir" in a
sin_cara = "--sin-cara" in a

TH = dict(salto=3.0, deriva_px=3.0, mov_min=0.35, quieto=0.30, destello_ratio=1.10, destello_abs=245, piel_borde=0.01)

pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                     "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", path],
                    capture_output=True, text=True)
try:
    info = json.loads(pr.stdout); st = info["streams"][0]
    W, H = int(st["width"]), int(st["height"]); dur = float(info["format"]["duration"])
    num, den = st["r_frame_rate"].split("/"); fps = float(num) / float(den)
except Exception:
    print("NO SE PUDO LEER", path, pr.stderr.strip()[:200]); sys.exit(2)

w = 320; h = int(round(H * w / W / 2) * 2)
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                      "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8)
if fr.size == 0 or fr.size % (w * h * 3):
    print("NO SE PUDO LEER los cuadros de", path); sys.exit(2)
fr = fr.reshape(-1, h, w, 3).astype(np.float32)
n = len(fr)
gray = fr.mean(axis=3)
fails, notes = [], []

# formato
if min_dur and dur + 0.5 / fps < min_dur:
    fails.append(f"dura {dur:.2f}s, se pidieron {min_dur:g}s")
if fps_req:
    fr_req = eval(fps_req) if "/" in fps_req else float(fps_req)
    if abs(fps - fr_req) > 0.01:
        fails.append(f"fps {fps:.3f}, se pidió {fr_req:.3f}")
if res_req and f"{W}x{H}" != res_req:
    fails.append(f"tamaño {W}x{H}, se pidió {res_req}")

# saltos y movimiento
d = np.abs(np.diff(gray, axis=0)).mean(axis=(1, 2))
med = float(np.median(d)) if len(d) else 0.0
saltos = [(i + 1, round(float(x), 2)) for i, x in enumerate(d) if x > TH["salto"] * max(med, 0.3) and x > 1.0]
if saltos:
    fails.append(f"{len(saltos)} saltos (cuadro, cambio): {saltos[:6]}")
perfil = [round(float(d[i:i + int(fps / 2)].mean()), 2) for i in range(0, len(d), max(1, int(fps / 2)))]

# deriva global primer→último cuadro (correlación de fase)
def shift(a0, b0):
    A = np.fft.fft2(a0 - a0.mean()); B = np.fft.fft2(b0 - b0.mean())
    c = np.fft.ifft2(A * np.conj(B) / (np.abs(A * np.conj(B)) + 1e-9)).real
    y, x = np.unravel_index(c.argmax(), c.shape)
    return (x if x <= w // 2 else x - w) * W / w, (y if y <= h // 2 else y - h) * H / h
dx, dy = shift(gray[0], gray[-1])
deriva = float(np.hypot(dx, dy))
if modo == "fija" and deriva > TH["deriva_px"]:
    fails.append(f"cámara fija pero se corrió {deriva:.1f}px")
if modo in ("orbita", "acercamiento", "bajada") and med < TH["mov_min"]:
    fails.append(f"se pidió movimiento ({modo}) y el cambio medio es {med:.2f} (umbral {TH['mov_min']})")
# casi quieto: "no quiero videos que parezcan fotos de lo quietos que están" (el editor, 2026-10-07). Calibrado:
# la caída con la misma imagen al inicio y al final (proyecto B) dio mediana 0,13 → rechazada; la más quieta de las
# aprobadas, la quemadura, 0,67; la gráfica del 75 % (HyperFrames, aprobada) 0,35.
mediana_perfil = float(np.median(perfil)) if perfil else 0.0
if modo in ("fija", "libre") and mediana_perfil < TH["quieto"]:
    fails.append(f"casi quieto, parece una foto: movimiento mediano por medio segundo {mediana_perfil:.2f} "
                 f"(umbral {TH['quieto']}); pedir algo natural que se mueva (luz, viento, agua, un gesto)")

# destello: punto más brillante (luminancia con desenfoque de caja de 9 px a 320 px de ancho)
def boxmax(img, k=9):
    c = np.cumsum(np.cumsum(np.pad(img, ((1, 0), (1, 0))), 0), 1)
    return float(((c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)).max())
lum = 0.299 * fr[..., 0] + 0.587 * fr[..., 1] + 0.114 * fr[..., 2]
picos = np.array([boxmax(L) for L in lum])
p0, pmax = float(picos[:3].mean()), float(picos.max())
destello_ratio = pmax / max(p0, 1.0)
if destello_ratio > TH["destello_ratio"] and pmax > TH["destello_abs"]:
    t_max = float(picos.argmax()) / fps
    fails.append(f"destello: el punto más brillante sube de {p0:.0f} a {pmax:.0f} (×{destello_ratio:.2f}) a los {t_max:.1f}s")

# sin cara: piel nueva por los bordes altos (calibrado 2026-10-01 con las tomas de Parkinson de proyecto A)
borde_txt, borde_peor = "", None
if sin_cara:
    R_, G_, B_ = fr[..., 0], fr[..., 1], fr[..., 2]
    Yc = 0.299 * R_ + 0.587 * G_ + 0.114 * B_
    Cb = 128 - 0.168736 * R_ - 0.331264 * G_ + 0.5 * B_
    Cr = 128 + 0.5 * R_ - 0.418688 * G_ - 0.081312 * B_
    piel = (Cr >= 135) & (Cr <= 180) & (Cb >= 80) & (Cb <= 130) & (Yc > 45)
    # lo que ya había al principio, agrandado ~6 % del ancho: así no cuenta lo que solo se corre
    # con el movimiento de cámara (la pared beige que entra con un acercamiento)
    base = piel[:3].any(0)
    for _ in range(max(4, round(w * 0.0625))):
        b2 = base.copy()
        b2[1:] |= base[:-1]; b2[:-1] |= base[1:]; b2[:, 1:] |= base[:, :-1]; b2[:, :-1] |= base[:, 1:]
        base = b2
    zonas = {"arriba": (slice(0, int(h * .12)), slice(0, w)),
             "izquierda alta": (slice(0, int(h * .5)), slice(0, int(w * .08))),
             "derecha alta": (slice(0, int(h * .5)), slice(int(w * .92), w))}
    min_cuadros = max(3, round(fps * 0.25))
    partes = []
    for nombre_z, (ys, xs) in zonas.items():
        area = (ys.stop - ys.start) * (xs.stop - xs.start)
        frac = (piel[:, ys, xs] & ~base[ys, xs]).sum(axis=(1, 2)) / area
        cuadros = int((frac > TH["piel_borde"]).sum())
        partes.append(f"{nombre_z} {frac.max() * 100:.1f}% ({cuadros} cuadros)")
        if cuadros >= min_cuadros:
            i_max = int(frac.argmax()); t0 = float(np.argmax(frac > TH["piel_borde"])) / fps
            fails.append(f"sin cara: entra piel por el borde {nombre_z} durante {cuadros} cuadros desde los "
                         f"{t0:.1f}s (máx {frac.max() * 100:.1f}% del borde a los {i_max / fps:.1f}s): posible cabeza en cuadro")
            if borde_peor is None or frac.max() > borde_peor[1]:
                borde_peor = (i_max / fps, float(frac.max()))
    borde_txt = "  sin cara (piel nueva en bordes altos): " + " · ".join(partes)

# material para mirar
out.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vf",
                f"fps={12 / dur:.4f},scale=270:-1,tile=6x2", "-frames:v", "1", str(out / "tira.jpg")])
for nombre, t in (("medio", dur / 2), ("final", max(0, dur - 0.05))):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
                    "-vf", "scale=540:-1", str(out / f"{nombre}.png")])

print(f"{pathlib.Path(path).name}: {W}x{H} {fps:.3f}fps {dur:.2f}s {n} cuadros leídos · modo {modo}")
print(f"  movimiento por medio segundo: {perfil}")
print(f"  saltos {len(saltos)} · deriva {deriva:.1f}px · destello ×{destello_ratio:.2f} ({p0:.0f}→{pmax:.0f})")
if borde_peor:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{borde_peor[0]:.3f}", "-i", path, "-frames:v", "1",
                    "-vf", "scale=540:-1", str(out / "borde.png")])
if borde_txt:
    print(borde_txt)
print(f"  para mirar: {out}/tira.jpg, medio.png, final.png" + (", borde.png" if borde_peor else ""))
if solo_medir:
    sys.exit(0)
if fails:
    print("FALLA:"); [print("  -", f) for f in fails]; sys.exit(1)
print("PASA los números. Falta mirar la tira: forma de la anatomía y que el movimiento sea el pedido.")
sys.exit(0)
