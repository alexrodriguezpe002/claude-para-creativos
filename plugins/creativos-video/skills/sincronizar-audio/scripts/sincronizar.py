#!/usr/bin/env python3
"""Sincroniza el audio de una grabadora (o de otra cámara) con los clips de video por la forma de onda.

Uso:
  python sincronizar.py analizar --clips <carpeta|archivo> [...] [--audio <carpeta|archivo> [...]] --salida <carpeta>
         [--nombre "SINCRO PROYECTO"] [--copias] [--audio-camara apagado|encendido] [--sin-xml] [--xml-simple]
         [--cache <archivo.json>] [--excluir <carpeta> [...]]
  python sincronizar.py autoprueba

Busca dónde cae el audio de cada clip dentro de las grabaciones (correlación GCC-PHAT, sin timecode), dice el
desfase y la confianza de cada uno y deja en --salida:
  - <nombre> - <día>.xml  proyecto (Final Cut Pro 7 XML) que abren Premiere y DaVinci: una carpeta (bin) por día de
                       rodaje, y en cada una una carpeta por cámara, una de audio y la secuencia del día con los clips
                       en orden de grabación, cada uno con su audio bueno alineado debajo (el de la cámara queda en sus
                       pistas, apagado). Los clips a revisar llevan un marcador y color. Con --xml-simple, en cambio,
                       una secuencia suelta por día y formato (sin carpetas, marcadores ni colores).
  - informe_sincronizacion.html / .csv / .json
  - CLIPS_CON_AUDIO/   (solo con --copias) cada clip con el audio bueno ya pegado, sin recomprimir el video.
Sin --audio (o sin grabaciones), arma igual el proyecto con el audio de la cámara, sin sincronizar.
--cache guarda el análisis de cada clip: la próxima vez solo se analiza lo nuevo (lo usa asistente-de-edicion).
Nunca toca los originales: solo lee los clips y las grabaciones. Necesita numpy (entorno propio, ver SKILL.md) y ffmpeg.

Códigos de salida: 0 terminó (mirar el informe: puede haber clips sin coincidencia) · 2 faltan datos o archivos ·
3 falta ffmpeg · 4 falta numpy · 5 la autoprueba falló.
"""
import argparse
import csv
import datetime as dt
import gc
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from xml.sax.saxutils import escape

SR = 8000                      # frecuencia de análisis: 0,125 ms por muestra, de sobra para el cuadro
TRAMO = 30.0                   # segundos del tramo más activo del clip que se busca en las grabaciones
TRAMO_VERIF = 8.0              # tramos de verificación (uno por mitad del clip)
VENTANA_VERIF = 0.5            # ± segundos alrededor de la posición esperada
NFFT_MAX = 1 << 22             # bloques de unos 8 minutos de grabación por pasada (memoria acotada)
BANDA = (80.0, 3800.0)         # Hz que se comparan (voz)
BETA = 0.8                     # PHAT-beta: blanqueo parcial, aguanta micrófonos y salas distintas
EXCLUIR = 0.5                  # s alrededor del pico que no cuentan como «segundo pico» (ecos de la sala)
Z_ALTA, Z_MEDIA = 20.0, 12.0   # pico contra el ruido de la correlación (en desvíos); calibrado el 19-11-2026
R_ALTA, R_MEDIA = 0.55, 0.75   # segundo pico / primero (más bajo = más inequívoco)
Z_VERIF = 10.0                 # z mínimo de cada tramo de verificación (búsqueda de ±0,5 s)
SOLAPE_MIN = 0.5               # fracción del tramo que tiene que caer dentro de la grabación en los bordes

EXT_VIDEO = set("mp4 mov mxf m4v mts m2ts avi mkv webm 3gp insv".split())
EXT_AUDIO = set("wav bwf aif aiff mp3 m4a flac aac ogg opus caf".split())
NO_LEE_FFMPEG = set("braw r3d crm ari arx".split())
NO_ENTRAR = {"sub", "proxy", "proxies", "proxymedia", "thmbnl", "_descarga", "ascmhl", "__macosx",
             "clips_con_audio", "$recycle.bin", "system volume information"}
# Carpetas que las cámaras crean dentro de la tarjeta: la carpeta de la copia (la «tarjeta») es la de arriba de estas
CARPETAS_TARJETA = {"private", "m4root", "clip", "dcim", "xdroot", "contents", "avchd", "bdmv", "stream",
                    "canonmsc", "clips001"}
DIAS_SEMANA = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
ETIQUETA_COLOR = {"media": "Yellow", "sin coincidencia": "Rose"}     # colores de etiqueta de Premiere


def _consola_utf8():
    """En Windows la consola puede ser cp1252: sin esto, un ✅ corta el programa."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def salir(msg, codigo=2):
    print("❌ " + msg)
    sys.exit(codigo)


# ----------------------------------------------------------------------------------------------- herramientas
def _herramientas():
    ff = shutil.which("ffmpeg")
    if not ff:
        try:
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ff = None
    return ff, shutil.which("ffprobe")


FFMPEG, FFPROBE = _herramientas()


def numpy_o_salir():
    try:
        import numpy
        return numpy
    except ImportError:
        salir("Falta numpy. Correr este script con el Python del entorno propio "
              "(~/.claude/venv-video, ver SKILL.md «Preparar»).", 4)


def correr(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


# ----------------------------------------------------------------------------------------------- medir
def _frac(txt):
    try:
        a, b = str(txt).split("/")
        return float(a) / float(b) if float(b) else 0.0
    except Exception:
        try:
            return float(txt)
        except Exception:
            return 0.0


def _bits(codec, sample_fmt, raw):
    m = re.search(r"pcm_[suf](\d+)", codec or "")
    if m:
        return int(m.group(1))
    if raw:
        return int(raw)
    return {"s16": 16, "s16p": 16, "s32": 24, "s32p": 24}.get(sample_fmt or "", 16)


def medir(ruta):
    """Duración, video (w, h, fps) y pistas de audio (sr, canales, bits) de un archivo."""
    if FFPROBE:
        r = correr([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", ruta])
        if r.returncode == 0:
            try:
                return _medir_json(json.loads(r.stdout))
            except Exception:
                pass
    return _medir_texto(ruta)


def _medir_json(j):
    fmt = j.get("format") or {}
    ftags = {str(k).lower(): str(v) for k, v in (fmt.get("tags") or {}).items()}
    info = {"dur": float(fmt.get("duration") or 0), "video": None, "audio": [],
            "tc": ftags.get("timecode"), "creado": ftags.get("creation_time"), "tags": ftags}
    for s in j.get("streams") or []:
        tipo, tags = s.get("codec_type"), s.get("tags") or {}
        if tags.get("creation_time") and not info["creado"]:
            info["creado"] = tags.get("creation_time")
        if tipo == "video" and tags.get("handler_name") and "handler_name" not in info["tags"]:
            info["tags"]["handler_name"] = str(tags.get("handler_name"))
        if tipo == "video" and info["video"] is None and not (s.get("disposition") or {}).get("attached_pic"):
            w, h = int(s.get("width") or 0), int(s.get("height") or 0)
            rot = 0
            for sd in s.get("side_data_list") or []:
                if "rotation" in sd:
                    rot = int(float(sd["rotation"]))
            if "rotate" in tags:
                rot = int(float(tags["rotate"]))
            if abs(abs(rot) - 90) < 1:
                w, h = h, w
            fps, avg = _frac(s.get("r_frame_rate")), _frac(s.get("avg_frame_rate"))
            if (fps <= 0 or fps > 240) and avg:
                fps = avg
            info["video"] = {"w": w, "h": h, "fps": fps or 25.0, "codec": s.get("codec_name"),
                             "transfer": s.get("color_transfer")}
            info["tc"] = info["tc"] or tags.get("timecode")
            if not info["dur"]:
                info["dur"] = float(s.get("duration") or 0)
        elif tipo == "audio":
            info["audio"].append({"sr": int(s.get("sample_rate") or 48000), "ch": int(s.get("channels") or 1),
                                  "bits": _bits(s.get("codec_name"), s.get("sample_fmt"),
                                                s.get("bits_per_raw_sample")),
                                  "codec": s.get("codec_name")})
            if not info["dur"]:
                info["dur"] = float(s.get("duration") or 0)
        elif tags.get("timecode"):
            info["tc"] = info["tc"] or tags.get("timecode")
    return info


def _medir_texto(ruta):
    t = correr([FFMPEG, "-hide_banner", "-nostdin", "-i", ruta]).stderr
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", t)
    info = {"dur": (int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))) if d else 0.0,
            "video": None, "audio": [], "tc": None, "creado": None, "tags": {}}
    m = re.search(r"timecode\s*:\s*(\d\d[:;]\d\d[:;]\d\d[:;.]\d\d)", t)
    if m:
        info["tc"] = m.group(1)
    m = re.search(r"creation_time\s*:\s*(\S+)", t)
    if m:
        info["creado"] = m.group(1)
    for clave in ("com.apple.quicktime.make", "com.apple.quicktime.model", "make", "model",
                  "com.android.manufacturer", "com.android.model", "handler_name"):
        m = re.search(r"^\s*%s\s*:\s*(.+)$" % re.escape(clave), t, re.M)
        if m:
            info["tags"][clave] = m.group(1).strip()
    for linea in re.findall(r"Stream #\d+:\d+.*", t):
        if "Video:" in linea and info["video"] is None and "attached pic" not in linea:
            v = re.search(r", (\d{2,5})x(\d{2,5})", linea)
            f = re.search(r"([\d.]+) fps", linea) or re.search(r"([\d.]+) tbr", linea)
            w, h = (int(v.group(1)), int(v.group(2))) if v else (0, 0)
            rot = re.search(r"rotation of (-?[\d.]+)", t)
            if rot and abs(abs(float(rot.group(1))) - 90) < 1:
                w, h = h, w
            tr = re.search(r"(arib-std-b67|smpte2084)", linea)
            info["video"] = {"w": w, "h": h, "fps": float(f.group(1)) if f else 25.0,
                             "codec": linea.split("Video:")[1].split()[0].strip(","),
                             "transfer": tr.group(1) if tr else None}
        elif "Audio:" in linea:
            a = re.search(r"(\d+) Hz, ([^,]+)", linea)
            lay = a.group(2).strip() if a else "stereo"
            ch = {"mono": 1, "stereo": 2, "2.1": 3, "quad": 4, "5.0": 5, "5.1": 6, "6.1": 7, "7.1": 8}.get(lay)
            if ch is None:
                m2 = re.match(r"(\d+) channels", lay)
                ch = int(m2.group(1)) if m2 else 2
            codec = linea.split("Audio:")[1].split()[0].strip(",")
            info["audio"].append({"sr": int(a.group(1)) if a else 48000, "ch": ch,
                                  "bits": _bits(codec, "s32" if "s32" in linea else "", None), "codec": codec})
    return info


# ----------------------------------------------------------------------------------------------- archivos
def listar(entradas, exts, avisos, excluir=(), raiz_de=None):
    """Archivos de esas extensiones. excluir: carpetas donde no entrar. raiz_de: anota de qué entrada salió cada uno."""
    vistos, out = set(), []
    excluir = {os.path.normcase(os.path.abspath(x)) for x in excluir}
    for e in entradas:
        e = os.path.abspath(os.path.expanduser(e))
        if os.path.isfile(e):
            cand = [e]
            base = os.path.dirname(e)
        elif os.path.isdir(e):
            cand = []
            base = e
            for raiz, dirs, archivos in os.walk(e):
                dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d.lower() not in NO_ENTRAR
                                 and not d.lower().startswith("_sincro")
                                 and os.path.normcase(os.path.join(raiz, d)) not in excluir)
                cand += [os.path.join(raiz, a) for a in sorted(archivos) if not a.startswith(".")]
        else:
            salir("No existe: %s" % e)
        for c in cand:
            ext = os.path.splitext(c)[1].lower().lstrip(".")
            if ext in NO_LEE_FFMPEG:
                avisos.append("%s: ffmpeg no lee %s (usar el proxy o un audio exportado)" % (os.path.basename(c),
                                                                                             ext.upper()))
            elif ext in exts and c not in vistos:
                vistos.add(c)
                out.append(c)
                if raiz_de is not None:
                    raiz_de[c] = base
    return out


# ----------------------------------------------------------------------------------------------- cuándo y con qué cámara
def clave_natural(texto):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", texto)]


def _fecha_iso(txt):
    """'2026-11-28T12:05:00.000000Z' u '2026-11-28T12:05:00+01:00' → fecha y hora local, o None si no sirve."""
    if not txt:
        return None
    s = str(txt).strip().replace(" ", "T", 1)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)                    # más de 6 decimales: Python no los lee
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.year < 2001:                                         # cámara sin hora puesta (1904, 1970, 2000)
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)                 # en los metadatos de video la hora va en UTC
    return d.astimezone().replace(tzinfo=None)


def _xml_de_camara(ruta):
    """Lo que algunas cámaras dejan en un XML al lado del clip (Sony: C0001M01.XML): modelo, serie y hora."""
    base, _ = os.path.splitext(ruta)
    for cand in (base + "M01.XML", base + "M01.xml", base + ".XML", base + ".xml"):
        if os.path.isfile(cand):
            try:
                with open(cand, "r", encoding="utf-8", errors="replace") as f:
                    t = f.read(65536)
            except OSError:
                continue
            m = re.search(r'modelName="([^"]+)"', t)
            s = re.search(r'serialNo="([^"]+)"', t)
            c = re.search(r'<CreationDate\s+value="([^"]+)"', t)
            return {"modelo": m.group(1).strip() if m else None, "serie": s.group(1).strip() if s else None,
                    "fecha": _fecha_iso(c.group(1)) if c else None}
    return {}


def _modelo_de_tags(tags):
    t = tags or {}
    marca = t.get("com.apple.quicktime.make") or t.get("make") or t.get("com.android.manufacturer") or ""
    modelo = t.get("com.apple.quicktime.model") or t.get("model") or t.get("com.android.model") or ""
    if modelo:
        return modelo if not marca or modelo.lower().startswith(marca.lower()) else "%s %s" % (marca, modelo)
    if "gopro" in (t.get("handler_name") or "").lower():
        return "GoPro"
    return None


def _carpeta_origen(ruta, raiz):
    """La carpeta de la copia de la tarjeta: la que está arriba de PRIVATE, DCIM, CONTENTS… o la que tiene el clip."""
    raiz = raiz or os.path.dirname(ruta)
    rel = os.path.relpath(os.path.dirname(ruta), raiz)
    partes = [] if rel in (".", "") else rel.replace("\\", "/").split("/")
    for k, p in enumerate(partes):
        if p.lower() in CARPETAS_TARJETA or re.match(r"^\d{3}[a-z0-9_]{0,8}$", p.lower()):
            return partes[k - 1] if k > 0 else os.path.basename(os.path.normpath(raiz))
    return partes[-1] if partes else os.path.basename(os.path.normpath(raiz))


def datos_de_grabacion(ruta, info, raiz=None):
    """Cuándo empezó la grabación (hora local) y qué cámara o carpeta la grabó.

    Orden: el XML de la cámara (trae la zona horaria) · los metadatos del archivo · la fecha del archivo."""
    x = _xml_de_camara(ruta) if info.get("video") else {}
    momento, origen = x.get("fecha"), "XML de la cámara"
    if momento is None:
        momento, origen = _fecha_iso(info.get("creado")), "metadatos"
    if momento is None:
        try:
            momento, origen = dt.datetime.fromtimestamp(os.path.getmtime(ruta)), "fecha del archivo"
        except OSError:
            momento, origen = dt.datetime(2000, 1, 1), "sin fecha"
    modelo = x.get("modelo") or _modelo_de_tags(info.get("tags"))
    return {"momento": momento, "origen_fecha": origen, "modelo": modelo, "serie": x.get("serie"),
            "carpeta": _carpeta_origen(ruta, raiz)}


def etiqueta_dia(d, anio=True):
    return "%s %s" % (DIAS_SEMANA[d.weekday()], d.strftime("%d-%m-%Y" if anio else "%d-%m"))


def libre(ruta):
    if not os.path.exists(ruta):
        return ruta
    base, ext = os.path.splitext(ruta)
    i = 2
    while os.path.exists("%s_%d%s" % (base, i, ext)):
        i += 1
    return "%s_%d%s" % (base, i, ext)


def decodificar(ruta, destino):
    """Audio de la primera pista, a mono y 8 kHz, en float32 crudo. Devuelve None si no hay audio."""
    r = correr([FFMPEG, "-nostdin", "-v", "error", "-i", ruta, "-map", "0:a:0", "-vn", "-ac", "1",
                "-ar", str(SR), "-c:a", "pcm_f32le", "-f", "f32le", "-y", destino])
    if r.returncode != 0 or not os.path.exists(destino) or os.path.getsize(destino) < 4 * SR // 2:
        return None
    return destino


# ----------------------------------------------------------------------------------------------- correlación
def _nfft(n):
    return 1 << int(math.ceil(math.log2(max(n, 2))))


def correlacion(np, x, y, nfft):
    """GCC-PHAT-beta entre x (tramo del clip) e y (bloque de la grabación). r[k]: x empieza en y[k]."""
    X = np.fft.rfft(np.asarray(x, dtype=np.float64), nfft)
    Y = np.fft.rfft(np.asarray(y, dtype=np.float64), nfft)
    G = Y * np.conj(X)
    f = np.fft.rfftfreq(nfft, 1.0 / SR)
    G[(f < BANDA[0]) | (f > BANDA[1])] = 0
    mag = np.abs(G)
    G = G / np.maximum(mag, 1e-30) ** BETA
    return np.fft.irfft(G, nfft)


def _pico(np, r, lags_validos):
    """Mejor pico dentro de los desfases válidos: (desfase con fracción, z, segundo/primero).

    z = cuántos desvíos sobresale el pico del resto de la correlación. El «segundo pico» se busca a más de
    EXCLUIR segundos del primero: más cerca están los ecos de la sala y el tono de la voz, que son del mismo lugar.
    """
    idx = np.asarray(lags_validos) % len(r)
    v = r[idx]
    i = int(np.argmax(v))
    pico = float(v[i])
    muestra = v[:: max(1, len(v) // 200000)]
    med = float(np.median(muestra))
    mad = float(np.median(np.abs(muestra - med))) * 1.4826 or 1e-12
    z = (pico - med) / mad
    excl = int(EXCLUIR * SR)
    resto = np.concatenate([v[: max(0, i - excl)], v[i + excl + 1:]])
    segundo = float(np.max(resto)) if len(resto) else med
    ratio = (segundo - med) / (pico - med) if pico > med else 1.0
    k = int(lags_validos[i])
    a, b, c = r[(k - 1) % len(r)], r[k % len(r)], r[(k + 1) % len(r)]
    d = a - 2 * b + c
    frac = 0.5 * (a - c) / d if d != 0 else 0.0
    return k + max(-0.5, min(0.5, frac)), z, max(0.0, ratio)


def tramo_activo(np, x, largo, desde=0, hasta=None):
    """El tramo de `largo` muestras con más modulación (habla) entre desde y hasta."""
    hasta = len(x) if hasta is None else hasta
    if hasta - desde <= largo:
        return desde, hasta
    hop = SR // 20
    seg = x[desde:hasta]
    n = len(seg) // hop
    e = np.log10(np.add.reduceat(seg[: n * hop] ** 2, np.arange(0, n * hop, hop)) / hop + 1e-10)
    w = max(1, largo // hop)
    if n <= w:
        return desde, desde + largo
    c1, c2 = np.cumsum(np.r_[0.0, e]), np.cumsum(np.r_[0.0, e * e])
    s, s2 = c1[w:] - c1[:-w], c2[w:] - c2[:-w]
    var = s2 / w - (s / w) ** 2
    i = int(np.argmax(var))
    return desde + i * hop, desde + i * hop + largo


def buscar_en(np, tramo, rec):
    """Busca el tramo en toda la grabación, por bloques. Devuelve (posición en muestras, z, ratio) del mejor."""
    lx, total = len(tramo), len(rec)
    minimo = int(lx * SOLAPE_MIN)
    nfft = min(NFFT_MAX, _nfft(total + lx))
    if nfft < 2 * lx:
        nfft = _nfft(2 * lx + 1)
    by = nfft - lx + 1                          # muestras de grabación por bloque
    paso = max(1, by - lx + 1)
    mejor = None
    inicio = 0
    while True:
        bloque = np.asarray(rec[inicio: inicio + by], dtype=np.float32)
        nb = len(bloque)
        if nb < minimo:
            break
        primero, ultimo = inicio == 0, inicio + by >= total
        lo = -(lx - minimo) if primero else 0
        hi = (nb - minimo) if ultimo else (nb - lx)
        if hi >= lo:
            r = correlacion(np, tramo, bloque, nfft)
            k, z, ratio = _pico(np, r, np.arange(lo, hi + 1))
            if mejor is None or z > mejor[1]:
                mejor = (inicio + k, z, ratio)
        if ultimo:
            break
        inicio += paso
    return mejor


def verificar_cerca(np, tramo, rec, esperado):
    """Busca el tramo solo cerca de donde debería estar. Devuelve (posición, z) o None si cae fuera."""
    w = int(VENTANA_VERIF * SR)
    a, b = int(esperado) - w, int(esperado) + len(tramo) + w
    if a < 0 or b > len(rec):
        return None
    bloque = np.asarray(rec[a:b], dtype=np.float32)
    nfft = _nfft(len(bloque) + len(tramo))
    r = correlacion(np, tramo, bloque, nfft)
    k, z, _ = _pico(np, r, np.arange(0, len(bloque) - len(tramo) + 1))
    return a + k, z


def verificar(np, x, rec, pos):
    """Un tramo de cada mitad del clip, buscado solo cerca de donde debería estar.

    Devuelve [(inicio del tramo en el clip, dónde dice ese tramo que empieza el clip, z)]. En un clip que de verdad
    está en esa grabación, los dos tramos aparecen ahí; en uno que no está, cada uno cae en cualquier lado.
    """
    largo = min(int(TRAMO_VERIF * SR), len(x) // 2 - SR // 10)
    if largo < int(1.0 * SR):
        return []
    out = []
    n = len(x)
    zonas = ((0, n // 2), (n // 2, n)) if n < 60 * SR else ((0, n // 4), (3 * n // 4, n))   # lejos, para medir deriva
    for desde, hasta in zonas:
        va, vb = tramo_activo(np, x, largo, desde, hasta)
        res = verificar_cerca(np, x[va:vb], rec, pos + va)
        if res:
            out.append((va, res[0] - va, res[1]))
    return out


def clasificar(z, ratio, verif):
    """verif: «todas» (los dos tramos lo confirman), «una», «ninguna» o None (clip demasiado corto)."""
    if z >= Z_ALTA and ratio <= R_ALTA and verif in ("todas", None):
        return "alta" if verif == "todas" else "media"
    # Con un solo tramo que lo confirma, el pico principal tiene que ser claro en algo (z o segundo pico): en un clip
    # corto los tramos son parte del mismo audio y no prueban mucho. Sin esto, una frase ajena con la misma voz pasó
    # como 🟡 con todo justo en el límite (z 12,2 · 0,74 · un tramo a 10,6). La calibración con voz real no cambia.
    if z >= Z_MEDIA and ratio <= R_MEDIA and (verif == "todas" or (verif == "una" and (z >= Z_ALTA or ratio <= R_ALTA))):
        return "media"
    return "sin coincidencia"


def sincronizar_clip(np, clip_raw, recs):
    """recs: lista de (ruta, memmap). Devuelve dict con el resultado del clip."""
    x = np.fromfile(clip_raw, dtype=np.float32)
    if len(x) < SR:
        return {"estado": "sin audio", "nota": "el clip dura menos de 1 s o no tiene audio"}
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    if rms < 10 ** (-60 / 20):
        return {"estado": "sin audio", "nota": "el audio del clip es silencio (¿cámara sin micrófono?)"}
    largo = int(TRAMO * SR)
    tramos = [tramo_activo(np, x, largo)]
    if len(x) > largo:                       # si el más activo no aparece: el principio y el final del clip
        tramos += [(0, largo), (len(x) - largo, len(x))]
    candidatos, a, b = [], 0, 0
    for a, b in tramos:
        candidatos = []
        for ruta, rec in recs:
            m = buscar_en(np, x[a:b], rec)
            if m:
                candidatos.append((m[1], m[2], m[0] - a, ruta, rec))
        candidatos.sort(key=lambda c: -c[0])
        if candidatos and candidatos[0][0] >= Z_MEDIA and candidatos[0][1] <= R_MEDIA:
            break
    if not candidatos:
        return {"estado": "sin coincidencia", "nota": "ninguna grabación se superpone con el clip"}
    z, ratio, pos, ruta, rec = candidatos[0]
    verifs = verificar(np, x, rec, pos)
    tol = 0.040 * SR + 1e-4 * len(x)         # 40 ms + deriva de reloj de hasta 100 ppm
    fuertes = [v for v in verifs if v[2] >= Z_VERIF and abs(v[1] - pos) <= tol]
    verif = None if not verifs else ("todas" if len(fuertes) == len(verifs) else ("una" if fuertes else "ninguna"))
    deriva_ms = 0.0
    if len(fuertes) == 2 and len(x) >= 60 * SR:
        # Deriva de relojes (cámara y grabadora no cuentan el tiempo igual): solo se mide en tomas largas; en las
        # cortas la diferencia entre tramos es ruido de la medición, no deriva.
        (va1, p1, _), (va2, p2, _) = fuertes
        e = (p2 - p1) / float(va2 - va1)     # muestras de deriva por muestra de clip
        if abs(e * len(x)) > SR / 30.0:      # más de un cuadro: el primer cuadro sale del primer tramo
            deriva_ms = e * len(x) / SR * 1000.0
            pos = p1 - e * va1
    estado = clasificar(z, ratio, verif)
    otros = []                                # otra grabación con el mismo audio (pista de respaldo, -12 dB…)
    for zc, rc, pc, rutac, recc in candidatos[1:]:
        if zc >= Z_MEDIA and rc <= R_MEDIA:
            vc = verificar(np, x, recc, pc)
            if vc and all(v[2] >= Z_VERIF and abs(v[1] - pc) <= tol for v in vc):
                otros.append(os.path.basename(rutac))
    return {"estado": estado, "audio": ruta, "offset": pos / SR, "z": round(z, 1), "ratio": round(ratio, 2),
            "verificado": verif, "z_verif": [round(v[2], 1) for v in verifs], "deriva_ms": round(deriva_ms, 1),
            "tambien": otros, "tramo": [round(a / SR, 2), round(b / SR, 2)]}


# ----------------------------------------------------------------------------------------------- XML (FCP7)
def base_tiempo(fps):
    for ntsc, nominal in ((23.976, 24), (29.97, 30), (59.94, 60), (47.952, 48), (119.88, 120)):
        if abs(fps - ntsc) < 0.01:
            return nominal, True
    return int(round(fps)), False


def rate(tb, ntsc):
    return "<rate><timebase>%d</timebase><ntsc>%s</ntsc></rate>" % (tb, "TRUE" if ntsc else "FALSE")


def url_archivo(ruta):
    p = os.path.abspath(ruta).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return "file://localhost" + urllib.parse.quote(p)


class _Doc:
    """Un documento XML: cada archivo se define completo una sola vez y después se nombra por su id."""

    def __init__(self, maestros=False):
        self.files, self.definidos, self.maestros, self.n_seq = {}, set(), {}, 0
        self.usar_maestros = maestros

    def fid(self, ruta):
        if ruta not in self.files:
            self.files[ruta] = "file-%d" % (len(self.files) + 1)
        return self.files[ruta]

    def mid(self, ruta):
        if ruta not in self.maestros:
            self.maestros[ruta] = "masterclip-%d" % (len(self.maestros) + 1)
        return self.maestros[ruta]

    def file_xml(self, ruta, info, es_video, R, real):
        i = self.fid(ruta)
        if i in self.definidos:
            return '<file id="%s"/>' % i
        self.definidos.add(i)
        n = int(round(info["dur"] * real))
        media = ""
        if es_video and info.get("video"):
            v = info["video"]
            media += ("<video><samplecharacteristics>%s<width>%d</width><height>%d</height>"
                      "<anamorphic>FALSE</anamorphic><pixelaspectratio>square</pixelaspectratio>"
                      "<fielddominance>none</fielddominance></samplecharacteristics></video>" % (R, v["w"], v["h"]))
        if info.get("audio"):
            a = info["audio"][0]
            media += ("<audio><samplecharacteristics><depth>%d</depth><samplerate>%d</samplerate>"
                      "</samplecharacteristics><channelcount>%d</channelcount></audio>"
                      % (a["bits"], a["sr"], a["ch"]))
        return ('<file id="%s"><name>%s</name><pathurl>%s</pathurl>%s<duration>%d</duration><media>%s</media>'
                "</file>" % (i, escape(os.path.basename(ruta)), url_archivo(ruta), R, n, media))


def _tiempos(fps):
    tb, ntsc = base_tiempo(fps)
    return tb * (1000.0 / 1001.0 if ntsc else 1.0), rate(tb, ntsc)


def nombre_en_secuencia(it):
    """Nombre del clip en la línea de tiempo: el del archivo, con un aviso adelante si no quedó sincronizado."""
    nombre = os.path.basename(it["clip"])
    if it.get("rinfo"):
        return nombre
    if not it["info"].get("audio") or it.get("estado") == "sin audio":
        return "SIN AUDIO - " + nombre
    if it.get("estado") == "sin grabadora":
        return nombre
    return "SIN SINCRO - " + nombre


def secuencia_xml(doc, nombre, items, fps, w, h, camara_encendida, adornos=True):
    """Una secuencia: items en orden, cada uno {clip, info, estado, res y rinfo si quedó sincronizado}.

    adornos: marcadores y colores en los clips a revisar, y el vínculo con su clip maestro (solo en el proyecto)."""
    real, R = _tiempos(fps)
    doc.n_seq += 1
    s = doc.n_seq
    fmt_v = ("<samplecharacteristics>%s<width>%d</width><height>%d</height><anamorphic>FALSE</anamorphic>"
             "<pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance>"
             "</samplecharacteristics>" % (R, w, h))

    # 1) Posiciones en la secuencia y piezas de cada par
    cam_ch = max([len(it["info"]["audio"]) and it["info"]["audio"][0]["ch"] or 0 for it in items] + [0])
    rec_ch = max([it["rinfo"]["audio"][0]["ch"] for it in items if it.get("rinfo")] + [0])
    piezas, marcas = [], []          # piezas: por clip, lista de (pista ("v", n) o ("a", n), dict de clipitem)
    pos = 0
    for it in items:
        info = it["info"]
        n = max(1, int(round(info["dur"] * real)))
        grupo = []
        nombre_clip = nombre_en_secuencia(it)
        color = ETIQUETA_COLOR.get(it.get("estado")) if adornos else None
        grupo.append((("v", 1), {"ruta": it["clip"], "info": info, "video": True, "nombre": nombre_clip,
                                 "start": pos, "end": pos + n, "in": 0, "out": n, "ch": None, "on": True,
                                 "color": color}))
        if info.get("audio"):
            for c in range(1, info["audio"][0]["ch"] + 1):
                grupo.append((("a", c), {"ruta": it["clip"], "info": info, "video": False, "nombre": nombre_clip,
                                         "start": pos, "end": pos + n, "in": 0, "out": n, "ch": c,
                                         "on": camara_encendida or not it.get("rinfo"), "color": color}))
        if it.get("rinfo"):
            rinfo = it["rinfo"]
            off = int(round(it["res"]["offset"] * real))       # cuadro de la grabación donde empieza el clip
            rec_n = max(1, int(round(rinfo["dur"] * real)))
            start = pos + max(0, -off)
            a_in = max(0, off)
            a_out = min(rec_n, a_in + (pos + n - start))
            if a_out > a_in:
                for c in range(1, rinfo["audio"][0]["ch"] + 1):
                    grupo.append((("a", cam_ch + c), {"ruta": it["res"]["audio"], "info": rinfo, "video": False,
                                                      "nombre": os.path.basename(it["res"]["audio"]),
                                                      "start": start, "end": start + (a_out - a_in), "in": a_in,
                                                      "out": a_out, "ch": c, "on": True, "color": color}))
        if adornos and it.get("estado") == "media":
            marcas.append((pos, "REVISAR SINCRO", "Confianza media: escuchar antes de usar (%s)"
                           % os.path.basename(it["clip"])))
        elif adornos and it.get("estado") == "sin coincidencia":
            marcas.append((pos, "SIN SINCRO", "No está en las grabaciones: queda con el audio de la cámara (%s)"
                           % os.path.basename(it["clip"])))
        piezas.append(grupo)
        pos += n
    total = pos

    # 2) Índices dentro de cada pista (para los <link>)
    cuenta = {}
    for grupo in piezas:
        for pista, d in grupo:
            cuenta[pista] = cuenta.get(pista, 0) + 1
            d["clipindex"] = cuenta[pista]
            d["id"] = "clipitem-%d-%s%d-%d" % (s, pista[0], pista[1], d["clipindex"])

    def clipitem(pista, d, grupo):
        links = "".join(
            "<link><linkclipref>%s</linkclipref><mediatype>%s</mediatype><trackindex>%d</trackindex>"
            "<clipindex>%d</clipindex></link>" % (g["id"], "video" if p[0] == "v" else "audio", p[1], g["clipindex"])
            for p, g in grupo)
        fuente = doc.file_xml(d["ruta"], d["info"], d["video"], R, real)
        if not d["video"]:
            fuente += ("<sourcetrack><mediatype>audio</mediatype><trackindex>%d</trackindex></sourcetrack>"
                       % d["ch"])
        dur_src = max(1, int(round(d["info"]["dur"] * real)))
        maestro = "<masterclipid>%s</masterclipid>" % doc.mid(d["ruta"]) if doc.usar_maestros else ""
        color = "<labels><label2>%s</label2></labels>" % d["color"] if d.get("color") else ""
        return ('<clipitem id="%s">%s<name>%s</name><enabled>%s</enabled><duration>%d</duration>%s<start>%d</start>'
                "<end>%d</end><in>%d</in><out>%d</out>%s%s%s</clipitem>"
                % (d["id"], maestro, escape(d["nombre"]), "TRUE" if d["on"] else "FALSE", dur_src, R, d["start"],
                   d["end"], d["in"], d["out"], fuente, links, color))

    pistas = {}
    for grupo in piezas:
        for pista, d in grupo:
            pistas.setdefault(pista, []).append(clipitem(pista, d, grupo))
    v = "<track>%s</track>" % "".join(pistas.get(("v", 1), []))
    a = "".join("<track>%s</track>" % "".join(pistas.get(("a", i), [])) for i in range(1, cam_ch + rec_ch + 1))
    marcadores = "".join("<marker><comment>%s</comment><name>%s</name><in>%d</in><out>-1</out></marker>"
                         % (escape(c), escape(n), p) for p, n, c in marcas)
    return ('<sequence id="sequence-%d"><name>%s</name><duration>%d</duration>%s'
            "<media><video><format>%s</format>%s</video><audio><numOutputChannels>2</numOutputChannels>"
            "<format><samplecharacteristics><depth>24</depth><samplerate>48000</samplerate></samplecharacteristics>"
            "</format>%s</audio></media>"
            "<timecode>%s<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode>"
            "%s</sequence>" % (s, escape(nombre), total, R, fmt_v, v, a, R, marcadores))


def armar_xml(nombre, items, fps, w, h, camara_encendida):
    """Una secuencia suelta (sin carpetas, marcadores ni colores): la forma más simple, la de --xml-simple."""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">%s</xmeml>\n'
            % secuencia_xml(_Doc(), nombre, items, fps, w, h, camara_encendida, adornos=False))


def clip_maestro(doc, ruta, info, fps):
    """El clip tal como aparece en una carpeta del proyecto (un clip maestro, como los que exporta Premiere)."""
    real, R = _tiempos(fps)
    m = doc.mid(ruta)
    n = max(1, int(round(info["dur"] * real)))
    nombre = escape(os.path.basename(ruta))
    es_video = bool(info.get("video"))
    pistas_v = ""
    if es_video:
        pistas_v = ('<track><clipitem id="%s-v"><masterclipid>%s</masterclipid><name>%s</name>%s'
                    "<alphatype>none</alphatype><pixelaspectratio>square</pixelaspectratio>"
                    "<anamorphic>FALSE</anamorphic>%s</clipitem></track>"
                    % (m, m, nombre, R, doc.file_xml(ruta, info, True, R, real)))
    pistas_a = ""
    for c in range(1, (info["audio"][0]["ch"] if info.get("audio") else 0) + 1):
        pistas_a += ('<track><clipitem id="%s-a%d"><masterclipid>%s</masterclipid><name>%s</name>%s%s'
                     "<sourcetrack><mediatype>audio</mediatype><trackindex>%d</trackindex></sourcetrack>"
                     "</clipitem></track>" % (m, c, m, nombre, R, doc.file_xml(ruta, info, es_video, R, real), c))
    media = ("<video>%s</video>" % pistas_v if pistas_v else "") + ("<audio>%s</audio>" % pistas_a if pistas_a else "")
    return ('<clip id="%s" explodedTracks="true"><masterclipid>%s</masterclipid><ismasterclip>TRUE</ismasterclip>'
            "<duration>%d</duration>%s<name>%s</name><media>%s</media></clip>" % (m, m, n, R, nombre, media))


def carpeta_xml(nombre, hijos):
    return "<bin><name>%s</name><children>%s</children></bin>" % (escape(nombre), hijos)


def armar_proyecto_xml(titulo, dias, audio_suelto, camara_encendida):
    """El proyecto: dias = [{etiqueta, secuencias [(nombre, fps, w, h, items)], camaras [(carpeta, [(ruta, info)])],
    audios [(ruta, info)]}]. Un solo día: todo suelto en el proyecto; varios días: una carpeta por día.
    audio_suelto: grabaciones que no coincidieron con ningún clip ni son de un día con clips."""
    doc = _Doc(maestros=True)
    partes, fps_general = [], None
    for d in dias:
        hijos = []
        fps_dia = d["secuencias"][0][1] if d["secuencias"] else 25.0
        fps_general = fps_general or fps_dia
        # Primero las secuencias: cada archivo se define completo la primera vez que aparece en una secuencia y las
        # carpetas lo nombran por su id. Así lo leen también los programas que solo miran las secuencias y guardan
        # la primera aparición de cada id (OpenTimelineIO, por ejemplo).
        for nombre, fps, w, h, items in d["secuencias"]:
            hijos.append(secuencia_xml(doc, nombre, items, fps, w, h, camara_encendida))
        for nombre_carpeta, clips in d["camaras"]:
            hijos.append(carpeta_xml(nombre_carpeta, "".join(clip_maestro(doc, r, i, i["video"]["fps"])
                                                             for r, i in clips)))
        if d["audios"]:
            hijos.append(carpeta_xml("AUDIO", "".join(clip_maestro(doc, r, i, fps_dia) for r, i in d["audios"])))
        if len(dias) > 1:
            partes.append(carpeta_xml(d["etiqueta"], "".join(hijos)))
        else:
            partes.extend(hijos)
    if audio_suelto:
        partes.append(carpeta_xml("AUDIO SIN COINCIDENCIA", "".join(clip_maestro(doc, r, i, fps_general or 25.0)
                                                                    for r, i in audio_suelto)))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4"><project><name>%s</name>'
            "<children>%s</children></project></xmeml>\n" % (escape(titulo), "".join(partes)))


# ----------------------------------------------------------------------------------------------- copias con audio
def copiar_con_audio(clip, info, res, rinfo, carpeta, con_camara):
    """Clip con el audio bueno pegado (video sin recomprimir). Devuelve la ruta o un error."""
    os.makedirs(carpeta, exist_ok=True)
    salida = libre(os.path.join(carpeta, os.path.splitext(os.path.basename(clip))[0] + "_SYNC.mov"))
    sr = rinfo["audio"][0]["sr"]
    off = res["offset"]
    dur = info["dur"]
    filtro = "[1:a:0]"
    if off >= 0:
        filtro += "atrim=start_sample=%d,asetpts=PTS-STARTPTS," % int(round(off * sr))
    else:
        filtro += "adelay=delays=%dS:all=1," % int(round(-off * sr))
    filtro += "apad,atrim=end_sample=%d[bueno]" % int(round(dur * sr))
    bits = rinfo["audio"][0]["bits"]
    if str(rinfo["audio"][0].get("codec") or "").startswith("pcm_f"):
        codec = "pcm_f32le"                          # grabadoras de 32 bits flotante: se conserva el margen
    else:
        codec = "pcm_s24le" if bits > 16 else "pcm_s16le"
    cmd = [FFMPEG, "-nostdin", "-v", "error", "-i", clip, "-i", res["audio"], "-filter_complex", filtro,
           "-map", "0:v:0", "-map", "[bueno]"]
    if con_camara and info.get("audio"):
        cmd += ["-map", "0:a:0"]
    cmd += ["-c:v", "copy", "-c:a", codec, "-map_metadata", "0", "-metadata:s:a:0", "title=Audio sincronizado"]
    if con_camara and info.get("audio"):
        cmd += ["-metadata:s:a:1", "title=Audio de camara"]
    if info.get("tc") and re.match(r"^\d\d[:;]\d\d[:;]\d\d[:;.]\d\d$", info["tc"]):
        cmd += ["-timecode", info["tc"]]
    cmd += [salida]
    r = correr(cmd)
    if r.returncode != 0 or not os.path.exists(salida):
        if os.path.exists(salida):
            os.remove(salida)                       # lo creó este mismo comando y quedó a medias
        return None, (r.stderr.strip().splitlines() or ["error de ffmpeg"])[-1]
    return salida, None


# ----------------------------------------------------------------------------------------------- informe
def hms(seg):
    signo = "-" if seg < 0 else ""
    seg = abs(seg)
    return "%s%02d:%02d:%06.3f" % (signo, int(seg // 3600), int(seg % 3600 // 60), seg % 60)


ICONO = {"alta": "✅", "media": "🟡", "sin coincidencia": "❌", "sin audio": "🔇", "sin grabadora": "🎬",
         "error": "⚠️"}


def escribir_informe(carpeta, filas, extra):
    os.makedirs(carpeta, exist_ok=True)
    js = os.path.join(carpeta, "informe_sincronizacion.json")
    with open(js, "w", encoding="utf-8") as f:
        json.dump({"filas": filas, **extra}, f, ensure_ascii=False, indent=1)
    cs = os.path.join(carpeta, "informe_sincronizacion.csv")
    with open(cs, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["clip", "camara", "grabado", "duracion_s", "fps", "confianza", "audio", "empieza_en_la_grabacion",
                    "desfase_s", "desfase_cuadros", "z", "segundo_pico", "deriva_ms", "nota"])
        for r in filas:
            w.writerow([r["clip"], r.get("camara", ""), r.get("grabado", ""), "%.2f" % r["dur"], "%.3f" % r["fps"],
                        r["estado"], r.get("audio_nombre", ""),
                        hms(r["offset"]) if "offset" in r else "", ("%.4f" % r["offset"]) if "offset" in r else "",
                        r.get("cuadros", ""), r.get("z", ""), r.get("ratio", ""), r.get("deriva_ms", ""),
                        r.get("nota", "")])
    def celdas(r):
        bueno = r["estado"] in ("alta", "media")
        return (ICONO.get(r["estado"], ""), html.escape(r["estado"]), html.escape(r["clip"]),
                html.escape(r.get("camara", "")), html.escape(r.get("grabado", "").replace("T", " ")),
                html.escape(r.get("audio_nombre", "—")) if bueno else "—", hms(r["offset"]) if bueno else "—",
                r.get("cuadros", "—") if bueno else "—", r.get("z", "—"), html.escape(r.get("nota", "")))
    filas_html = "".join("<tr><td>%s %s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                         "<td>%s</td><td>%s</td></tr>" % celdas(r) for r in filas)
    hh = os.path.join(carpeta, "informe_sincronizacion.html")
    with open(hh, "w", encoding="utf-8") as f:
        f.write("""<!doctype html><meta charset="utf-8"><title>Sincronización</title>
<style>body{font:15px/1.4 -apple-system,Segoe UI,Arial,sans-serif;margin:24px;color:#222}
table{border-collapse:collapse;width:100%%}td,th{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left}
th{background:#f3f3f3}small{color:#666}</style>
<h1>Sincronización de audio</h1><p><small>%s · %d clips · %d con audio bueno · grabaciones: %s</small></p>
<table><tr><th>Confianza</th><th>Clip</th><th>Cámara</th><th>Grabado</th><th>Grabación</th>
<th>El clip empieza en</th><th>Cuadros</th><th>z</th><th>Nota</th></tr>%s</table>
<p><small>✅ alta: el audio del clip aparece clarísimo en la grabación y dos tramos más del clip caen en el mismo
lugar. 🟡 media: aparece, pero con menos certeza (clip muy corto, mucho ruido o solo un tramo lo confirma):
escucharlo antes de usarlo. ❌ sin coincidencia: no está en estas grabaciones (o no se puede asegurar); en la
secuencia queda con su audio de cámara. 🔇 sin audio: el clip no tiene sonido (B-roll). 🎬 sin grabadora: no había
audio aparte, el clip va con el de la cámara. z = qué tan claro es el pico de coincidencia. «El clip empieza en» = el
momento de la grabación donde cae el primer cuadro del clip (negativo: la cámara arrancó antes que la
grabadora).</small></p>""" % (html.escape(extra["fecha"]), len(filas),
                                                    sum(1 for r in filas if r["estado"] in ("alta", "media")),
                                                    html.escape(", ".join(extra["grabaciones"])), filas_html))
    return hh, cs, js


# ----------------------------------------------------------------------------------------------- caché
CLAVES_RES = ("estado", "audio", "offset", "z", "ratio", "verificado", "z_verif", "deriva_ms", "tambien", "tramo",
              "nota")


def _clave_archivo(ruta):
    try:
        st = os.stat(ruta)
        return [st.st_size, int(st.st_mtime)]
    except OSError:
        return None


def _leer_cache(ruta):
    vacio = {"version": 1, "clips": {}, "grabaciones": {}}
    if not ruta or not os.path.exists(ruta):
        return vacio
    try:
        with open(ruta, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("version") == 1:
            c.setdefault("clips", {})
            c.setdefault("grabaciones", {})
            return c
    except Exception:
        pass
    return vacio


def _guardar_cache(ruta, cache):
    if not ruta:
        return
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, ruta)


def _reusable(ent, clave, firma_recs, claves_recs):
    """El análisis guardado de un clip sirve si el clip no cambió y lo que encontró sigue valiendo."""
    if not ent or ent.get("clave") != clave or not ent.get("res"):
        return None
    res = ent["res"]
    estado = res.get("estado")
    if estado in ("alta", "media"):
        return res if claves_recs.get(res.get("audio")) == ent.get("clave_audio") else None
    if estado == "sin audio":
        return res
    if estado in ("sin coincidencia", "sin grabadora"):
        return res if ent.get("firma_recs") == firma_recs else None
    return None


# ----------------------------------------------------------------------------------------------- analizar
def _nombre_archivo(txt):
    return re.sub(r'[\\/:*?"<>|]', "-", txt).strip()


def armar_dias(filas, infos, base):
    """Agrupa los clips por día de grabación y, dentro de cada día, por formato y por cámara (en orden de grabación).

    Devuelve (dias, audio_suelto) para armar_proyecto_xml."""
    con_video = [f for f in filas if f["info"].get("video")]
    series = {}
    for f in con_video:
        m = f["_meta"]
        if m["modelo"] and m["serie"]:
            series.setdefault(m["modelo"], set()).add(m["serie"])
    for f in con_video:
        m = f["_meta"]
        if m["modelo"]:
            f["camara"] = ("%s (%s)" % (m["modelo"], m["serie"][-4:]) if len(series.get(m["modelo"], ())) > 1
                           else m["modelo"])
        else:
            f["camara"] = m["carpeta"] or "CAMARA"
    por_dia = {}
    for f in con_video:
        por_dia.setdefault(f["_meta"]["momento"].date(), []).append(f)
    ancho = 2 if len(por_dia) > 9 else 1
    dias, usadas = [], set()
    for k, d in enumerate(sorted(por_dia), 1):
        fs = sorted(por_dia[d], key=lambda f: (f["_meta"]["momento"], clave_natural(f["clip"])))
        etq = etiqueta_dia(d)
        formatos = {}
        for f in fs:
            v = f["info"]["video"]
            formatos.setdefault((round(v["fps"], 3), v["w"], v["h"]), []).append(f)
        secuencias = []
        for (fps, w, h), gs in sorted(formatos.items(), key=lambda g: -len(g[1])):
            items = []
            for f in gs:
                it = {"clip": f["ruta"], "info": f["info"], "estado": f["estado"]}
                if f["estado"] in ("alta", "media"):
                    it["res"], it["rinfo"] = f, infos[f["audio"]]
                items.append(it)
            nombre = "%s - %s" % (base, etq)
            if len(formatos) > 1:
                nombre += " - %dx%d %s" % (w, h, ("%.3f" % fps).rstrip("0").rstrip("."))
            secuencias.append((nombre, fps, w, h, items))
        camaras = []
        for f in fs:
            c = "CAMARA - " + f["camara"]
            lista = next((l for n, l in camaras if n == c), None)
            if lista is None:
                lista = []
                camaras.append((c, lista))
            lista.append((f["ruta"], f["info"]))
        del_dia = sorted({f["audio"] for f in fs if f["estado"] in ("alta", "media")},
                         key=lambda r: clave_natural(os.path.basename(r)))
        usadas.update(del_dia)
        dias.append({"fecha": d, "etiqueta": "DIA %s - %s" % (str(k).zfill(ancho), etq), "secuencias": secuencias,
                     "camaras": camaras, "audios": [(r, infos[r]) for r in del_dia]})
    # Grabaciones que no coincidieron con ningún clip: a su día si ese día hay clips; si no, a una carpeta aparte
    suelto = []
    for r in sorted(infos, key=lambda r: clave_natural(os.path.basename(r))):
        if r in usadas:
            continue
        dr = datos_de_grabacion(r, infos[r])["momento"].date()
        destino = next((x for x in dias if x["fecha"] == dr), None)
        (destino["audios"] if destino else suelto).append((r, infos[r]))
    return dias, suelto


def analizar(a):
    if not FFMPEG:
        salir("Falta ffmpeg (instalarlo, o imageio-ffmpeg en el entorno propio: ver SKILL.md).", 3)
    avisos = []
    salida = os.path.abspath(os.path.expanduser(a.salida))
    excluir = [salida] + [os.path.abspath(os.path.expanduser(x)) for x in (getattr(a, "excluir", None) or [])]
    raiz_de = {}
    clips = listar(a.clips, EXT_VIDEO, avisos, excluir, raiz_de)
    audios = [x for x in listar(a.audio or [], EXT_VIDEO | EXT_AUDIO, avisos, excluir) if x not in set(clips)]
    for av in avisos:
        print("⚠️  " + av)
    if not clips:
        salir("No encontré clips de video en --clips.")
    for x in clips + audios:
        if os.path.dirname(x) == salida:
            salir("La carpeta de salida no puede ser la misma que la del material: elegir otra.")
    print("Clips: %d · grabaciones: %d · salida: %s" % (len(clips), len(audios), salida))
    if not audios:
        print("⚠️  No hay grabaciones aparte: armo el proyecto con el audio de la cámara, sin sincronizar.")
    cache = _leer_cache(getattr(a, "cache", None))
    nuevo_cache = {"version": 1, "clips": {}, "grabaciones": {}}
    trabajo = tempfile.mkdtemp(prefix="sincro_")
    recs, filas, infos, reusados = [], [], {}, 0
    np = None
    try:
        claves_recs = {}
        for ruta in audios:
            clave = _clave_archivo(ruta)
            ent = cache["grabaciones"].get(ruta)
            info = ent["info"] if ent and ent.get("clave") == clave and ent.get("info") else medir(ruta)
            nuevo_cache["grabaciones"][ruta] = {"clave": clave, "info": info}
            if not info["audio"]:
                print("⚠️  %s no tiene audio: se ignora" % os.path.basename(ruta))
                continue
            infos[ruta] = info
            claves_recs[ruta] = clave
        firma_recs = sorted([r, c] for r, c in claves_recs.items())
        pendientes = []
        for clip in clips:
            clave = _clave_archivo(clip)
            ent = cache["clips"].get(clip)
            info = ent["info"] if ent and ent.get("clave") == clave and ent.get("info") else medir(clip)
            meta = datos_de_grabacion(clip, info, raiz_de.get(clip))
            fila = {"clip": os.path.basename(clip), "ruta": clip, "dur": info["dur"],
                    "fps": (info["video"] or {}).get("fps", 0.0),
                    "grabado": meta["momento"].isoformat(timespec="seconds"), "_meta": meta, "_clave": clave,
                    "info": info}
            if not info.get("video"):
                fila.update(estado="error", nota="no tiene video")
            elif not info["audio"]:
                fila.update(estado="sin audio", nota="el clip no tiene audio (B-roll)")
            elif not infos:
                fila.update(estado="sin grabadora", nota="no hay audio de grabadora: va con el de la cámara")
            else:
                res = _reusable(ent, clave, firma_recs, claves_recs)
                if res is not None:
                    fila.update(res)
                    fila["_reusado"] = True
                    reusados += 1
                else:
                    pendientes.append(fila)
            filas.append(fila)
        if pendientes:
            np = numpy_o_salir()
            for i, ruta in enumerate(r for r in audios if r in infos):
                raw = decodificar(ruta, os.path.join(trabajo, "rec%d.f32" % i))
                if not raw:
                    print("⚠️  No pude leer el audio de %s: se ignora" % os.path.basename(ruta))
                    continue
                recs.append((ruta, np.memmap(raw, dtype=np.float32, mode="r")))
                print("  grabación %s · %s · %d canal(es)" % (os.path.basename(ruta), hms(infos[ruta]["dur"]),
                                                              infos[ruta]["audio"][0]["ch"]))
            if not recs:
                salir("Ninguna grabación tiene audio legible.")
        for i, fila in enumerate(pendientes):
            print("  analizando %d de %d: %s" % (i + 1, len(pendientes), fila["clip"]), flush=True)
            raw = decodificar(fila["ruta"], os.path.join(trabajo, "clip%d.f32" % i))
            res = sincronizar_clip(np, raw, recs) if raw else {"estado": "sin audio",
                                                               "nota": "no pude leer el audio del clip"}
            fila.update(res)
            if raw and os.path.exists(raw):
                os.remove(raw)
        for fila in filas:
            if fila["info"].get("video"):
                nuevo_cache["clips"][fila["ruta"]] = {
                    "clave": fila["_clave"], "info": fila["info"],
                    "res": {k: fila[k] for k in CLAVES_RES if k in fila},
                    "clave_audio": claves_recs.get(fila.get("audio")), "firma_recs": firma_recs}
            if "offset" in fila:
                fila["audio_nombre"] = os.path.basename(fila["audio"])
                fila["cuadros"] = int(round(fila["offset"] * fila["fps"]))
                notas = []
                if fila.get("tambien"):
                    notas.append("también coincide con " + ", ".join(fila["tambien"]))
                if abs(fila.get("deriva_ms", 0)) > 1000.0 / max(fila["fps"], 1):
                    notas.append("el audio se corre %.0f ms al final (relojes distintos)" % fila["deriva_ms"])
                if fila["estado"] == "sin coincidencia":
                    notas.insert(0, "mejor candidato %s, pero no es claro" % fila["audio_nombre"])
                fila["nota"] = "; ".join(notas)
            print("%s %s → %s%s" % (ICONO.get(fila["estado"], ""), fila["clip"],
                                    ("%s a %s (%s, z %s)" % (fila["audio_nombre"], hms(fila["offset"]),
                                                             fila["estado"], fila["z"]))
                                    if fila["estado"] in ("alta", "media")
                                    else fila["estado"] + (": " + fila.get("nota", "") if fila.get("nota") else ""),
                                    " (análisis guardado)" if fila.get("_reusado") else ""))
        # Salidas
        os.makedirs(salida, exist_ok=True)
        buenas = [f for f in filas if f["estado"] in ("alta", "media")]
        xmls = []
        base = a.nombre or "SINCRO"
        dias, suelto = armar_dias(filas, infos, base)
        if not a.sin_xml and dias:
            cam = a.audio_camara == "encendido"
            if getattr(a, "xml_simple", False):
                for d in dias:
                    for nombre, fps, w, h, items in d["secuencias"]:
                        ruta_xml = libre(os.path.join(salida, _nombre_archivo(nombre) + ".xml"))
                        with open(ruta_xml, "w", encoding="utf-8") as fh:
                            fh.write(armar_xml(nombre, items, fps, w, h, cam))
                        xmls.append(ruta_xml)
            else:
                if len(dias) == 1:
                    titulo = "%s - %s" % (base, etiqueta_dia(dias[0]["fecha"]))
                else:
                    titulo = "%s - %s a %s" % (base, etiqueta_dia(dias[0]["fecha"], anio=False),
                                               etiqueta_dia(dias[-1]["fecha"]))
                ruta_xml = libre(os.path.join(salida, _nombre_archivo(titulo) + ".xml"))
                with open(ruta_xml, "w", encoding="utf-8") as fh:
                    fh.write(armar_proyecto_xml(titulo, dias, suelto, cam))
                xmls.append(ruta_xml)
        copias = []
        if a.copias:
            carpeta = os.path.join(salida, "CLIPS_CON_AUDIO")
            for f in buenas:
                ruta, err = copiar_con_audio(f["ruta"], f["info"], f, infos[f["audio"]], carpeta, a.audio_camara_copias)
                if ruta:
                    copias.append(ruta)
                else:
                    f["nota"] = (f.get("nota", "") + "; " if f.get("nota") else "") + "copia: " + err
                    print("⚠️  %s: no se pudo armar la copia (%s)" % (f["clip"], err))
        limpias = [{k: v for k, v in f.items() if k != "info" and not k.startswith("_")} for f in filas]
        hh, cs, js = escribir_informe(salida, limpias, {"fecha": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                                       "grabaciones": [os.path.basename(r) for r in infos],
                                                       "xml": xmls, "copias": copias})
        _guardar_cache(getattr(a, "cache", None), nuevo_cache)
    finally:
        recs.clear()
        gc.collect()
        shutil.rmtree(trabajo, ignore_errors=True)
    print("")
    cuenta = {e: sum(f["estado"] == e for f in filas) for e in ICONO}
    print("Sincronizados: %d de %d clips (✅ alta %d · 🟡 media %d · ❌ sin coincidencia %d · 🔇 sin audio %d%s)"
          % (len(buenas), len(filas), cuenta["alta"], cuenta["media"], cuenta["sin coincidencia"],
             cuenta["sin audio"], " · 🎬 sin grabadora %d" % cuenta["sin grabadora"] if cuenta["sin grabadora"]
             else ""))
    if getattr(a, "cache", None):
        print("Reutilizados del análisis anterior: %d de %d clips" % (reusados, len(filas)))
    for x in xmls:
        print("XML=%s" % x)
    print("INFORME=%s" % hh)
    if copias:
        print("COPIAS=%s (%d)" % (os.path.join(salida, "CLIPS_CON_AUDIO"), len(copias)))
    return filas, xmls, copias


# ----------------------------------------------------------------------------------------------- autoprueba
def _habla(np, seg, sr, rng):
    """Habla sintética: sílabas con tono, formantes y pausas (para probar sin material real)."""
    n = int(seg * sr)
    out = np.zeros(n, np.float32)
    t = 0
    while t < n:
        if rng.random() < 0.22:
            t += int(rng.uniform(0.12, 0.7) * sr)
            continue
        m = min(int(rng.uniform(0.1, 0.42) * sr), n - t)
        if m < 64:
            break
        tt = np.arange(m) / sr
        f0 = rng.uniform(95, 220) * (1 + 0.06 * np.sin(2 * np.pi * rng.uniform(2, 6) * tt))
        fase = 2 * np.pi * np.cumsum(f0) / sr
        sig = sum(np.sin(k * fase) / k for k in range(1, 14)) * 0.8 + rng.standard_normal(m) * 0.35
        S = np.fft.rfft(sig)
        f = np.fft.rfftfreq(m, 1.0 / sr)
        f1, f2 = rng.uniform(300, 900), rng.uniform(1000, 2600)
        S *= np.exp(-((f - f1) / 200) ** 2) + 0.6 * np.exp(-((f - f2) / 350) ** 2) + 0.04
        sig = np.fft.irfft(S, m)
        sig *= np.hanning(m) ** 0.6 * rng.uniform(0.25, 0.9) / (np.abs(sig).max() + 1e-9)
        out[t:t + m] += sig.astype(np.float32)
        t += m
    return out


def _camara(np, x, sr, rng, ganancia=0.2):
    """Lo que oye una cámara: otro micrófono (ecualización), sala (ecos), ruido y otra ganancia."""
    X = np.fft.rfft(x.astype(np.float64))
    f = np.fft.rfftfreq(len(x), 1.0 / sr)
    X *= (f / (f + 250.0)) * (1.0 / (1.0 + (f / 5000.0) ** 4)) * (1 + 0.5 * np.exp(-((f - 3000) / 600) ** 2))
    y = np.fft.irfft(X, len(x))
    for ms, g in ((17, 0.4), (43, 0.25), (97, 0.15)):
        d = int(ms * sr / 1000)
        y[d:] += g * y[:-d]
    y = y / (np.abs(y).max() + 1e-9) * 0.7 + rng.standard_normal(len(y)) * 0.03
    return (y * ganancia).astype(np.float32)


def _wav(np, ruta, canales, sr, bits=24):
    """Escribe un WAV con ffmpeg desde float32 (canales: lista de arrays del mismo largo)."""
    datos = np.stack(canales, axis=1).astype(np.float32).tobytes()
    codec = "pcm_s24le" if bits == 24 else "pcm_s16le"
    r = subprocess.run([FFMPEG, "-nostdin", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", str(len(canales)),
                        "-i", "pipe:0", "-c:a", codec, "-y", ruta], input=datos, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-300:])


def _clip(ruta, wav, dur, fps="24000/1001", creado=None):
    cmd = [FFMPEG, "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=%s" % fps]
    if wav:
        mp4 = ruta.lower().endswith(".mp4")             # MP4 de celular o cámara: AAC (con su retardo inicial)
        cmd += ["-i", wav, "-map", "0:v", "-map", "1:a"] + (["-c:a", "aac", "-b:a", "192k"] if mp4
                                                            else ["-c:a", "pcm_s16le"])
    if creado:
        cmd += ["-metadata", "creation_time=%s" % creado]
    cmd += ["-t", "%.3f" % dur, "-c:v", "libx264" if "libx264" in _encoders() else "mpeg4", "-pix_fmt", "yuv420p",
            "-g", "24", "-y", ruta]
    r = correr(cmd)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-300:])


_ENC = None


def _encoders():
    global _ENC
    if _ENC is None:
        _ENC = correr([FFMPEG, "-hide_banner", "-encoders"]).stdout
    return _ENC


def _xml_sony(ruta_clip, modelo, fecha_iso):
    """El XML que deja una cámara Sony al lado de cada clip (C0001.MP4 → C0001M01.XML), en chiquito."""
    base, _ = os.path.splitext(ruta_clip)
    with open(base + "M01.XML", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<NonRealTimeMeta xmlns="urn:schemas-professionalDisc:'
                'nonRealTimeMeta:ver.2.20">\n<CreationDate value="%s"/>\n<Device manufacturer="Sony" '
                'modelName="%s" serialNo="0012345"/>\n</NonRealTimeMeta>\n' % (fecha_iso, modelo))


def revisar_proyecto_xml(ruta):
    """Lee un XML de proyecto y devuelve {carpetas: {nombre: hijos}, secuencias: {nombre: [nombres en V1]},
    marcadores: {secuencia: [(nombre, in)]}, maestros: [nombres], audio_in: {(secuencia, archivo): [in]}} y
    los problemas de ids (archivos definidos dos veces o nombrados sin definir)."""
    import xml.etree.ElementTree as ET
    raiz = ET.parse(ruta).getroot()
    out = {"carpetas": {}, "secuencias": {}, "marcadores": {}, "maestros": [], "audio_in": {}, "problemas": []}
    for b in raiz.iter("bin"):
        hijos = b.find("children")
        out["carpetas"][b.find("name").text] = [(h.tag, h.findtext("name")) for h in (hijos if hijos is not None
                                                                                       else [])]
    for s in raiz.iter("sequence"):
        nombre = s.findtext("name")
        pistas = s.find("media/video").findall("track")
        out["secuencias"][nombre] = [c.findtext("name") for c in pistas[0].findall("clipitem")] if pistas else []
        out["marcadores"][nombre] = [(m.findtext("name"), int(m.findtext("in"))) for m in s.findall("marker")]
        for c in s.iter("clipitem"):
            out["audio_in"].setdefault((nombre, c.findtext("name")), []).append(int(c.findtext("in")))
    out["maestros"] = [c.findtext("name") for c in raiz.iter("clip") if c.findtext("ismasterclip") == "TRUE"]
    definidos, nombrados = {}, set()
    for f in raiz.iter("file"):
        if len(f):
            definidos[f.get("id")] = definidos.get(f.get("id"), 0) + 1
        nombrados.add(f.get("id"))
    out["problemas"] += ["%s definido %d veces" % (i, n) for i, n in definidos.items() if n > 1]
    out["problemas"] += ["%s sin definir" % i for i in nombrados if i not in definidos]
    en_secuencias = set()
    for s in raiz.iter("sequence"):
        for f in s.iter("file"):
            if len(f):
                en_secuencias.add(f.get("id"))
            elif f.get("id") not in en_secuencias:
                out["problemas"].append("%s se nombra en «%s» antes de definirse en una secuencia"
                                        % (f.get("id"), s.findtext("name")))
    return out


def autoprueba(_a=None):
    np = numpy_o_salir()
    if not FFMPEG:
        salir("Falta ffmpeg.", 3)
    rng = np.random.default_rng(7)
    sr = 48000
    base = tempfile.mkdtemp(prefix="sincro_prueba_")
    ok = True

    def check(bien, texto):
        nonlocal ok
        print("%s %s" % ("✅" if bien else "❌", texto))
        ok &= bool(bien)

    try:
        mat = os.path.join(base, "MATERIAL")
        tarjeta_a = os.path.join(mat, "A001", "PRIVATE", "M4ROOT", "CLIP")     # tarjeta Sony copiada tal cual
        tarjeta_b = os.path.join(mat, "CAM B")                                  # otra cámara, sin metadatos
        for d in (tarjeta_a, tarjeta_b, os.path.join(mat, "AUDIO")):
            os.makedirs(d)
        print("Armando material de prueba (habla sintética, 1 grabación de 4 min + otra que no tiene que ver;"
              " 2 cámaras, 2 días)…")
        voz = _habla(np, 240, sr, rng)
        sala = rng.standard_normal(len(voz)).astype(np.float32) * 0.004
        _wav(np, os.path.join(mat, "AUDIO", "ZOOM0001.WAV"), [voz + sala, voz * 0.5 + sala * 1.3], sr)
        otra = _habla(np, 120, sr, np.random.default_rng(99))
        _wav(np, os.path.join(mat, "AUDIO", "ZOOM0002.WAV"), [otra], sr)
        fps = 24000 / 1001.0
        # (nombre, desfase en la grabación, duración, hora de grabación): C0002 se grabó primero
        casos = [("C0001.MOV", 37.250, 20.0, "2026-11-28T12:03:00"), ("C0002.MP4", 151.533, 45.0, "2026-11-28T12:00:00"),
                 ("C0003.MOV", -3.0, 15.0, "2026-11-28T12:06:00")]
        for nombre, off, dur, cuando in casos:
            n0 = int(round(off * sr))
            n = int(round(dur * sr))
            seg = np.zeros(n, np.float32)
            a0, b0 = max(0, n0), min(len(voz), n0 + n)
            seg[a0 - n0: b0 - n0] = voz[a0:b0]
            seg[: max(0, -n0)] += rng.standard_normal(max(0, -n0)).astype(np.float32) * 0.05
            w = os.path.join(base, nombre + ".wav")
            _wav(np, w, [_camara(np, seg, sr, rng)], sr, bits=16)
            _clip(os.path.join(tarjeta_a, nombre), w, dur, creado=cuando + "Z")
            _xml_sony(os.path.join(tarjeta_a, nombre), "ILME-FX3", cuando + "+00:00")
        ajena = _camara(np, _habla(np, 18, sr, np.random.default_rng(3)), sr, rng)
        w = os.path.join(base, "ajena.wav")
        _wav(np, w, [ajena], sr, bits=16)
        _clip(os.path.join(tarjeta_b, "C0004.MOV"), w, 18.0, creado="2026-11-29T12:00:00Z")
        _clip(os.path.join(tarjeta_b, "C0005.MOV"), None, 6.0, creado="2026-11-29T12:01:00Z")
        cache = os.path.join(base, "cache.json")
        args = argparse.Namespace(clips=[mat], audio=[mat], salida=os.path.join(base, "SINCRO"),
                                  nombre="SINCRO PRUEBA", copias=True, audio_camara="apagado",
                                  audio_camara_copias=True, sin_xml=False, xml_simple=False, cache=cache, excluir=[])
        print("")
        filas, xmls, copias = analizar(args)
        print("")
        por = {f["clip"]: f for f in filas}
        cuadro_ms = 1000.0 / fps
        peor = 0.0
        for nombre, off, _, _ in casos:
            f = por[nombre]
            if f["estado"] not in ("alta", "media") or f.get("audio_nombre") != "ZOOM0001.WAV":
                check(False, "%s: esperaba ZOOM0001.WAV, salió %s (%s)" % (nombre, f.get("audio_nombre"), f["estado"]))
                continue
            err = abs(f["offset"] - off) * 1000
            peor = max(peor, err)
            check(err <= cuadro_ms, "%s: desfase %.4f s (real %.3f) · error %.2f ms · %s · z %s" % (
                nombre, f["offset"], off, err, f["estado"], f["z"]))
        for nombre, esperado in (("C0004.MOV", "sin coincidencia"), ("C0005.MOV", "sin audio")):
            check(por[nombre]["estado"] == esperado, "%s: %s (esperado: %s, z %s)" % (
                nombre, por[nombre]["estado"], esperado, por[nombre].get("z", "—")))

        # El proyecto XML: días, cámaras, audio, orden de grabación, marcadores, ids
        x = revisar_proyecto_xml(xmls[0])
        d1 = etiqueta_dia(_fecha_iso("2026-11-28T12:00:00Z").date())
        d2 = etiqueta_dia(_fecha_iso("2026-11-29T12:00:00Z").date())
        dia1, dia2 = "DIA 1 - " + d1, "DIA 2 - " + d2
        check(len(xmls) == 1 and dia1 in x["carpetas"] and dia2 in x["carpetas"],
              "XML: un proyecto con una carpeta por día (%s · %s)" % (dia1, dia2))
        hijos1 = x["carpetas"].get(dia1, [])
        check(("bin", "CAMARA - ILME-FX3") in hijos1 and ("bin", "AUDIO") in hijos1
              and ("sequence", "SINCRO PRUEBA - " + d1) in hijos1,
              "día 1: carpeta de la cámara (modelo leído del XML de la Sony), de audio y la secuencia del día")
        check(len(x["carpetas"].get("CAMARA - ILME-FX3", [])) == 3 and
              ("clip", "ZOOM0001.WAV") in x["carpetas"].get("AUDIO", []),
              "día 1: los 3 clips de la cámara y la grabación usada, como clips maestros")
        orden = x["secuencias"].get("SINCRO PRUEBA - " + d1)
        check(orden == ["C0002.MP4", "C0001.MOV", "C0003.MOV"],
              "día 1: la secuencia va en orden de grabación (C0002, C0001, C0003): %s" % orden)
        check(("bin", "CAMARA - CAM B") in x["carpetas"].get(dia2, []),
              "día 2: la cámara sin metadatos toma el nombre de su carpeta (CAM B)")
        orden2 = x["secuencias"].get("SINCRO PRUEBA - " + d2)
        check(orden2 == ["SIN SINCRO - C0004.MOV", "SIN AUDIO - C0005.MOV"],
              "día 2: el clip sin coincidencia y el B-roll entran, con su aviso en el nombre: %s" % orden2)
        check(x["marcadores"].get("SINCRO PRUEBA - " + d2) == [("SIN SINCRO", 0)],
              "día 2: marcador «SIN SINCRO» al principio del clip a revisar")
        check(any(n == "ZOOM0002.WAV" for n in x["maestros"]),
              "la grabación que no coincidió con nada queda en el proyecto (no se pierde)")
        esperado_in = int(round(37.250 * 24 * 1000 / 1001))
        ins = x["audio_in"].get(("SINCRO PRUEBA - " + d1, "ZOOM0001.WAV"), [])
        check(esperado_in in ins, "la grabación de C0001 entra en el cuadro %d" % esperado_in)
        check(not x["problemas"], "cada archivo definido una sola vez, adentro de la secuencia que lo usa primero%s" % (
            "" if not x["problemas"] else ": " + ", ".join(x["problemas"][:3])))

        # Copias: el audio pegado tiene que coincidir con el de la cámara sin desfase
        c1 = [c for c in copias if os.path.basename(c).startswith("C0001")]
        if not c1:
            check(False, "no se armó la copia de C0001")
        else:
            ra = os.path.join(base, "pegado.f32")
            rb = os.path.join(base, "cam.f32")
            correr([FFMPEG, "-nostdin", "-v", "error", "-i", c1[0], "-map", "0:a:0", "-ac", "1", "-ar", str(SR),
                    "-f", "f32le", "-y", ra])
            correr([FFMPEG, "-nostdin", "-v", "error", "-i", c1[0], "-map", "0:a:1", "-ac", "1", "-ar", str(SR),
                    "-f", "f32le", "-y", rb])
            xa, xb = np.fromfile(ra, np.float32), np.fromfile(rb, np.float32)
            r = correlacion(np, xb, xa, _nfft(len(xa) + len(xb)))
            k, z, _ = _pico(np, r, np.arange(-SR // 2, SR // 2))
            dur_ok = abs(medir(c1[0])["dur"] - 20.0) < 0.1
            check(abs(k) / SR * 1000 <= 1.0 and dur_ok,
                  "copia de C0001: audio pegado a %.2f ms del de la cámara, dura %.2f s, video sin recomprimir"
                  % (k / SR * 1000, medir(c1[0])["dur"]))

        # Segunda vez con el caché: no se vuelve a analizar nada y el resultado es el mismo
        print("")
        args2 = argparse.Namespace(**dict(vars(args), copias=False, salida=os.path.join(base, "SINCRO2")))
        filas2, xmls2, _ = analizar(args2)
        mismos = all(abs(f.get("offset", 0) - por[f["clip"]].get("offset", 0)) < 1e-9 and
                     f["estado"] == por[f["clip"]]["estado"] for f in filas2)
        check(all(f.get("_reusado") for f in filas2 if f["info"].get("audio")) and mismos,
              "segunda pasada con caché: los 4 clips con audio salen del análisis guardado, con el mismo resultado")
        # --xml-simple: secuencias sueltas (la forma más simple), una por día
        args3 = argparse.Namespace(**dict(vars(args), copias=False, xml_simple=True,
                                          salida=os.path.join(base, "SINCRO3")))
        _, xmls3, _ = analizar(args3)
        import xml.etree.ElementTree as ET
        simples = [ET.parse(p).getroot() for p in xmls3]
        check(len(xmls3) == 2 and all(r.find("sequence") is not None and r.find("project") is None
                                      for r in simples), "--xml-simple: una secuencia suelta por día (2 archivos)")
        # Los originales no se tocaron
        check(sorted(os.listdir(tarjeta_a)) == ["C0001.MOV", "C0001M01.XML", "C0002.MP4", "C0002M01.XML",
                                                 "C0003.MOV", "C0003M01.XML"],
              "la carpeta de la tarjeta quedó igual (nada nuevo, nada movido)")
        print("")
        print("Peor error: %.2f ms (un cuadro a 23,976 son %.1f ms)" % (peor, cuadro_ms))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("✅ Autoprueba OK" if ok else "❌ La autoprueba falló")
    sys.exit(0 if ok else 5)


def main():
    _consola_utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("analizar", help="sincronizar clips con grabaciones")
    p.add_argument("--clips", nargs="+", required=True, help="carpetas o archivos de video")
    p.add_argument("--audio", nargs="*", default=[],
                   help="grabaciones (o clips de otra cámara); sin esto, el proyecto va con el audio de la cámara")
    p.add_argument("--salida", required=True, help="carpeta nueva para el XML, el informe y las copias")
    p.add_argument("--nombre", help="nombre del proyecto y de las secuencias (por defecto SINCRO; se suma el día)")
    p.add_argument("--xml-simple", action="store_true",
                   help="una secuencia suelta por día y formato, sin carpetas, marcadores ni colores")
    p.add_argument("--cache", help="archivo .json donde guardar el análisis para reusarlo la próxima vez")
    p.add_argument("--excluir", nargs="*", default=[], help="carpetas donde no buscar material")
    p.add_argument("--copias", action="store_true", help="armar copias de cada clip con el audio bueno pegado")
    p.add_argument("--audio-camara", choices=["apagado", "encendido"], default="apagado",
                   help="audio de la cámara en el XML (queda en sus pistas; apagado por defecto)")
    p.add_argument("--sin-audio-camara-en-copias", dest="audio_camara_copias", action="store_false",
                   help="en las copias, no guardar el audio de la cámara como segunda pista")
    p.add_argument("--sin-xml", action="store_true")
    sub.add_parser("autoprueba", help="probar todo con material sintético (unos 30 s)")
    a = ap.parse_args()
    if a.cmd == "analizar":
        analizar(a)
    elif a.cmd == "autoprueba":
        autoprueba(a)
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
