#!/usr/bin/env python3
"""Saca de un render maestro las versiones para cada red: 9:16, 1:1, 4:5 y 16:9, y una liviana para WhatsApp.

Uso:
  python versiones.py "<maestro>" [--salida <carpeta>] [--formatos 9x16,1x1,4x5,16x9] [--modo fondo|recorte]
         [--foco 0.5] [--foco-v 0.5] [--sin-whatsapp] [--whatsapp-mb 16] [--srt <archivo.srt>] [--caja]
         [--fuente <archivo.ttf>] [--logo <logo.png>] [--logo-pos arriba-derecha] [--logo-ancho 0.14]
         [--logo-opacidad 0.9] [--simular] [--ignorar-hdr]
  python versiones.py autoprueba

--modo fondo   el cuadro entero, con el mismo video desenfocado y oscurecido detrás (no se pierde nada).
--modo recorte llena el formato recortando; --foco elige qué parte queda (0 = izquierda, 0.5 = centro, 1 = derecha;
               --foco-v lo mismo de arriba a abajo).
--srt          subtítulos quemados (con Pillow: no hace falta un ffmpeg con libass). --caja: sobre caja negra.
Nunca toca el maestro y nunca pisa archivos: todo va a una carpeta nueva (<maestro>_VERSIONES por defecto).

Códigos: 0 listo · 2 faltan datos o el maestro no sirve · 3 falta ffmpeg · 4 falta Pillow (solo con --srt) ·
5 la autoprueba falló.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

FORMATOS = {
    "9x16": (1080, 1920, "reels-tiktok-shorts"),
    "1x1": (1080, 1080, "feed"),
    "4x5": (1080, 1350, "feed-instagram"),
    "16x9": (1920, 1080, "youtube"),
}
# Dónde termina el bloque de subtítulos (fracción de la altura): en vertical, arriba de los botones de la app.
BASE_SUBS = {"9x16": 0.76, "1x1": 0.90, "4x5": 0.86, "16x9": 0.92, "whatsapp": 0.90}
POSICIONES = ("arriba-derecha", "arriba-izquierda", "abajo-derecha", "abajo-izquierda")


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


def medir(ruta):
    """Duración, tamaño (ya rotado), fps, si tiene audio y si es HDR."""
    if FFPROBE:
        r = correr([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", ruta])
        if r.returncode == 0:
            try:
                j = json.loads(r.stdout)
                info = {"dur": float((j.get("format") or {}).get("duration") or 0), "w": 0, "h": 0, "fps": 0.0,
                        "audio": False, "transfer": None, "size": int((j.get("format") or {}).get("size") or 0)}
                for s in j.get("streams") or []:
                    if s.get("codec_type") == "video" and not info["w"] and \
                            not (s.get("disposition") or {}).get("attached_pic"):
                        w, h = int(s.get("width") or 0), int(s.get("height") or 0)
                        rot = 0
                        for sd in s.get("side_data_list") or []:
                            if "rotation" in sd:
                                rot = int(float(sd["rotation"]))
                        if "rotate" in (s.get("tags") or {}):
                            rot = int(float(s["tags"]["rotate"]))
                        if abs(abs(rot) - 90) < 1:
                            w, h = h, w
                        fps = _frac(s.get("avg_frame_rate")) or _frac(s.get("r_frame_rate"))
                        info.update(w=w, h=h, fps=fps, transfer=s.get("color_transfer"))
                    elif s.get("codec_type") == "audio":
                        info["audio"] = True
                return info
            except Exception:
                pass
    t = correr([FFMPEG, "-hide_banner", "-nostdin", "-i", ruta]).stderr
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", t)
    info = {"dur": (int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))) if d else 0.0,
            "w": 0, "h": 0, "fps": 0.0, "audio": "Audio:" in t, "transfer": None,
            "size": os.path.getsize(ruta) if os.path.exists(ruta) else 0}
    m = re.search(r"Stream #.*?Video:.*", t)
    if m:
        linea = m.group(0)
        v = re.search(r", (\d{2,5})x(\d{2,5})", linea)
        f = re.search(r"([\d.]+) fps", linea) or re.search(r"([\d.]+) tbr", linea)
        if v:
            info["w"], info["h"] = int(v.group(1)), int(v.group(2))
        rot = re.search(r"rotation of (-?[\d.]+)", t)
        if rot and abs(abs(float(rot.group(1))) - 90) < 1:
            info["w"], info["h"] = info["h"], info["w"]
        info["fps"] = float(f.group(1)) if f else 25.0
        tr = re.search(r"(arib-std-b67|smpte2084)", linea)
        info["transfer"] = tr.group(1) if tr else None
    return info


# ----------------------------------------------------------------------------------------------- subtítulos
def leer_srt(ruta):
    with open(ruta, encoding="utf-8-sig", errors="replace") as f:
        texto = f.read().replace("\r\n", "\n").replace("\r", "\n")
    subs = []
    for bloque in re.split(r"\n\s*\n", texto.strip()):
        lineas = [x for x in bloque.split("\n") if x.strip() != ""]
        for i, linea in enumerate(lineas):
            m = re.match(r"\s*(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", linea)
            if m:
                g = [int(x) for x in m.groups()]
                ini = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 10 ** len(m.group(4))
                fin = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 10 ** len(m.group(8))
                cuerpo = " ".join(re.sub(r"<[^>]+>|\{[^}]+\}", "", x).strip() for x in lineas[i + 1:])
                if cuerpo and fin > ini:
                    subs.append((ini, fin, cuerpo))
                break
    return sorted(subs)


def buscar_fuente(pedida=None):
    if pedida:
        if not os.path.exists(pedida):
            salir("No existe la fuente: %s" % pedida)
        return pedida
    win = os.environ.get("WINDIR", r"C:\Windows")
    for f in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
              os.path.join(win, "Fonts", "arialbd.ttf"), os.path.join(win, "Fonts", "segoeuib.ttf"),
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        if os.path.exists(f):
            return f
    return None


def _envolver(draw, texto, fuente, ancho_max, borde):
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if draw.textlength(prueba, font=fuente) + 2 * borde <= ancho_max or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def dibujar_subs(subs, W, H, clave, carpeta, ruta_fuente, caja):
    """Un PNG transparente por subtítulo y una lista ffconcat con los tiempos. Devuelve la ruta de la lista."""
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(carpeta, exist_ok=True)
    vertical = H > W * 1.2
    base_px = round(min(W, H) * (0.066 if vertical else 0.054))     # en vertical se mira en el celular: más grande
    ancho_max = int(W * 0.84)
    vacio = os.path.join(carpeta, "vacio.png")
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(vacio)
    nombres = []
    for n, (ini, fin, texto) in enumerate(subs, 1):
        px = base_px
        while True:
            fuente = ImageFont.truetype(ruta_fuente, px) if ruta_fuente else ImageFont.load_default()
            borde = max(2, px // 12)
            img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            lineas = _envolver(d, texto, fuente, ancho_max, borde)
            if len(lineas) <= 2 or px <= base_px * 0.8:
                break
            px = int(px * 0.92)                      # texto largo: un poco más chico antes de pasar a 3 líneas
        alto_linea = int(px * 1.22)
        y = int(H * BASE_SUBS.get(clave, 0.9)) - alto_linea * len(lineas)
        if caja:
            anchos = [d.textlength(x, font=fuente) for x in lineas]
            pad = int(px * 0.35)
            x0 = int((W - max(anchos)) / 2) - pad
            d.rounded_rectangle([x0, y - pad, W - x0, y + alto_linea * len(lineas) + pad // 2],
                                radius=pad, fill=(0, 0, 0, 175))
        for linea in lineas:
            ancho = d.textlength(linea, font=fuente)
            x = (W - ancho) / 2
            if caja:
                d.text((x, y), linea, font=fuente, fill=(255, 255, 255, 255))
            else:
                d.text((x, y), linea, font=fuente, fill=(255, 255, 255, 255), stroke_width=borde,
                       stroke_fill=(0, 0, 0, 255))
            y += alto_linea
        nombre = "s%04d.png" % n
        img.save(os.path.join(carpeta, nombre))
        nombres.append((ini, fin, nombre))
    lista = os.path.join(carpeta, "subs.ffconcat")
    with open(lista, "w", encoding="utf-8") as f:
        f.write("ffconcat version 1.0\n")
        t = 0.0
        for ini, fin, nombre in nombres:
            if ini > t:
                f.write("file 'vacio.png'\nduration %.3f\n" % (ini - t))
            ini = max(ini, t)
            f.write("file '%s'\nduration %.3f\n" % (nombre, max(0.04, fin - ini)))
            t = max(t, fin)
        f.write("file 'vacio.png'\nduration 1.000\nfile 'vacio.png'\n")
    return lista


# ----------------------------------------------------------------------------------------------- versiones
def _par(x):
    return max(2, int(x) // 2 * 2)


def filtro_video(info, W, H, modo, fx, fy):
    """Cadena de filtros para llevar el maestro a W×H. Termina en [v0]."""
    a_src, a_dst = info["w"] / float(info["h"]), W / float(H)
    if abs(a_src - a_dst) / a_dst < 0.01:
        return "[0:v]scale=%d:%d:flags=lanczos,setsar=1[v0]" % (W, H)
    if modo == "recorte":
        return ("[0:v]scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,"
                "crop=%d:%d:(iw-%d)*%.3f:(ih-%d)*%.3f,setsar=1[v0]" % (W, H, W, H, W, fx, H, fy))
    w8, h8 = _par(W / 8), _par(H / 8)
    return ("[0:v]split=2[fondo][frente];"
            "[fondo]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,gblur=sigma=6,"
            "scale=%d:%d,eq=brightness=-0.07:saturation=0.85[f2];"
            "[frente]scale=%d:%d:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos[f3];"
            "[f2][f3]overlay=(W-w)/2:(H-h)/2,setsar=1[v0]" % (w8, h8, w8, h8, W, H, W, H))


def _encoder():
    enc = correr([FFMPEG, "-hide_banner", "-encoders"]).stdout
    if "libx264" in enc:
        return "libx264"
    if "h264_videotoolbox" in enc:
        return "h264_videotoolbox"
    if "h264_mf" in enc:
        return "h264_mf"
    return "mpeg4"


def codificar(maestro, info, salida, W, H, clave, modo, a, subs_lista, calidad):
    """calidad: ('crf', n) o ('kbps', n)."""
    filtro = filtro_video(info, W, H, modo, a.foco, a.foco_v)
    entradas = ["-i", maestro]
    ultimo, n_in = "v0", 1
    if subs_lista:
        entradas += ["-f", "concat", "-safe", "0", "-i", subs_lista]
        filtro += ";[v0][%d:v]overlay=0:0:eof_action=pass[v1]" % n_in
        ultimo, n_in = "v1", n_in + 1
    if a.logo:
        entradas += ["-i", a.logo]
        lw = _par(W * a.logo_ancho)
        m = int(min(W, H) * 0.045)
        x = ("W-w-%d" % m) if a.logo_pos.endswith("derecha") else str(m)
        y = str(m) if a.logo_pos.startswith("arriba") else ("H-h-%d" % m)
        filtro += (";[%d:v]scale=%d:-1,format=rgba,colorchannelmixer=aa=%.2f[lg];[%s][lg]overlay=%s:%s[v2]"
                   % (n_in, lw, a.logo_opacidad, ultimo, x, y))
        ultimo = "v2"
    filtro += ";[%s]format=yuv420p[vout]" % ultimo
    enc = _encoder()
    cmd = [FFMPEG, "-nostdin", "-v", "error", "-y"] + entradas + ["-filter_complex", filtro, "-map", "[vout]"]
    if info["audio"]:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "192k" if calidad[0] == "crf" else "96k", "-ar", "48000",
                "-ac", "2"]
    cmd += ["-c:v", enc]
    if enc == "libx264":
        cmd += ["-preset", "medium", "-profile:v", "high"]
        cmd += ["-crf", str(calidad[1])] if calidad[0] == "crf" else ["-b:v", "%dk" % calidad[1], "-maxrate",
                                                                       "%dk" % int(calidad[1] * 1.4), "-bufsize",
                                                                       "%dk" % int(calidad[1] * 2)]
    else:
        bitrate = calidad[1] if calidad[0] == "kbps" else int(W * H * 0.0058)    # ~12 Mb/s en 1080×1920
        cmd += ["-b:v", "%dk" % bitrate]
    cmd += ["-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-movflags", "+faststart", salida]
    r = correr(cmd)
    if r.returncode != 0 or not os.path.exists(salida):
        if os.path.exists(salida):
            os.remove(salida)                         # lo creó este comando y quedó a medias
        return (r.stderr.strip().splitlines() or ["error de ffmpeg"])[-1]
    return None


def nombre_libre(ruta):
    if not os.path.exists(ruta):
        return ruta
    base, ext = os.path.splitext(ruta)
    i = 2
    while os.path.exists("%s_%d%s" % (base, i, ext)):
        i += 1
    return "%s_%d%s" % (base, i, ext)


def hoja_revision(salidas, carpeta, momento):
    """Un cuadro de cada versión, uno al lado del otro, con su nombre. Devuelve la ruta del JPG o None."""
    tmp = tempfile.mkdtemp(prefix="revision_")
    try:
        cuadros = []
        for etiqueta, ruta in salidas:
            png = os.path.join(tmp, "%02d.png" % len(cuadros))
            correr([FFMPEG, "-nostdin", "-v", "error", "-ss", "%.2f" % momento, "-i", ruta, "-frames:v", "1",
                    "-vf", "scale=-2:540", "-y", png])
            if os.path.exists(png):
                cuadros.append((etiqueta, png))
        if not cuadros:
            return None
        destino = nombre_libre(os.path.join(carpeta, "revision.jpg"))
        try:
            from PIL import Image, ImageDraw, ImageFont
            imgs = [(e, Image.open(p).convert("RGB")) for e, p in cuadros]
            pad, alto_txt = 16, 44
            ancho = sum(i.width for _, i in imgs) + pad * (len(imgs) + 1)
            hoja = Image.new("RGB", (ancho, 540 + alto_txt + 2 * pad), (28, 28, 30))
            d = ImageDraw.Draw(hoja)
            ruta_f = buscar_fuente()
            f = ImageFont.truetype(ruta_f, 22) if ruta_f else ImageFont.load_default()
            x = pad
            for e, i in imgs:
                hoja.paste(i, (x, pad))
                d.text((x, 540 + pad + 10), e, font=f, fill=(235, 235, 235))
                x += i.width + pad
            hoja.save(destino, quality=88)
        except ImportError:
            entradas = []
            for _, p in cuadros:
                entradas += ["-i", p]
            correr([FFMPEG, "-nostdin", "-v", "error"] + entradas + ["-filter_complex",
                   "hstack=inputs=%d" % len(cuadros) if len(cuadros) > 1 else "null", "-y", destino])
        return destino if os.path.exists(destino) else None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def generar(a):
    if not FFMPEG:
        salir("Falta ffmpeg (instalarlo, o imageio-ffmpeg en el entorno propio: ver SKILL.md).", 3)
    maestro = os.path.abspath(os.path.expanduser(a.maestro))
    if not os.path.isfile(maestro):
        salir("No existe el maestro: %s" % maestro)
    info = medir(maestro)
    if not info["w"] or not info["dur"]:
        salir("No pude leer el video (¿está completo?).")
    if info["transfer"] in ("arib-std-b67", "smpte2084") and not a.ignorar_hdr:
        salir("El maestro es HDR (%s): las versiones saldrían con colores lavados. Exportar el maestro en SDR "
              "(Rec. 709) y volver a correr; --ignorar-hdr solo si se sabe lo que pasa." % info["transfer"])
    claves = [c.strip().lower() for c in a.formatos.split(",") if c.strip()]
    for c in claves:
        if c not in FORMATOS:
            salir("Formato desconocido: %s (sirven: %s)" % (c, ", ".join(FORMATOS)))
    if a.logo and not os.path.isfile(a.logo):
        salir("No existe el logo: %s" % a.logo)
    if a.logo_pos not in POSICIONES:
        salir("--logo-pos tiene que ser una de: %s" % ", ".join(POSICIONES))
    subs = []
    if a.srt:
        if not os.path.isfile(a.srt):
            salir("No existe el SRT: %s" % a.srt)
        subs = leer_srt(a.srt)
        if not subs:
            salir("El SRT no tiene subtítulos legibles.")
        try:
            import PIL  # noqa: F401
        except ImportError:
            salir("Para quemar subtítulos falta Pillow: correr con el Python del entorno propio (ver SKILL.md).", 4)
    base = os.path.splitext(os.path.basename(maestro))[0]
    carpeta = os.path.abspath(os.path.expanduser(a.salida)) if a.salida else \
        os.path.join(os.path.dirname(maestro), base + "_VERSIONES")
    if os.path.abspath(carpeta) == os.path.dirname(maestro):
        salir("La carpeta de salida no puede ser la misma del maestro: elegir otra (o dejar la de por defecto).")
    plan = []
    for c in claves:
        W, H, uso = FORMATOS[c]
        plan.append((c, W, H, "%s_%s_%s.mp4" % (base, c, uso), a.modo, ("crf", 18)))
    if not a.sin_whatsapp:
        corto = 720
        if info["w"] >= info["h"]:
            W, H = _par(min(info["w"], corto * info["w"] / float(info["h"]))), min(info["h"], corto)
        else:
            W, H = min(info["w"], corto), _par(min(info["h"], corto * info["h"] / float(info["w"])))
        plan.append(("whatsapp", _par(W), _par(H), "%s_whatsapp.mp4" % base, "fondo", ("crf", 26)))
    print("Maestro: %s · %dx%d · %.2f fps · %.1f s · audio: %s" % (os.path.basename(maestro), info["w"], info["h"],
                                                                     info["fps"], info["dur"],
                                                                     "sí" if info["audio"] else "no"))
    print("Salida: %s" % carpeta)
    for c, W, H, nombre, modo, _ in plan:
        cambia = abs(info["w"] / float(info["h"]) - W / float(H)) / (W / float(H)) >= 0.01
        print("  %-9s %4dx%-4d %s%s" % (c, W, H, nombre, (" · " + modo) if cambia else ""))
    if subs:
        print("  + %d subtítulos quemados (%s)" % (len(subs), "en caja" if a.caja else "letra blanca con borde"))
    if a.logo:
        print("  + logo %s (%s)" % (os.path.basename(a.logo), a.logo_pos))
    if a.simular:
        print("\n(Simulación: no se generó nada.)")
        return None
    os.makedirs(carpeta, exist_ok=True)
    trabajo = tempfile.mkdtemp(prefix="versiones_")
    hechas, errores = [], []
    fuente = buscar_fuente(a.fuente) if subs else None
    try:
        for c, W, H, nombre, modo, calidad in plan:
            salida = nombre_libre(os.path.join(carpeta, nombre))
            lista = dibujar_subs(subs, W, H, c, os.path.join(trabajo, c), fuente, a.caja) if subs else None
            err = codificar(maestro, info, salida, W, H, c, modo, a, lista, calidad)
            if not err and c == "whatsapp":
                tope = a.whatsapp_mb * 1024 * 1024
                intento = 0
                while os.path.getsize(salida) > tope and intento < 3:
                    intento += 1
                    kbps = int((tope * 8 / 1024.0 * (0.92 - 0.08 * intento)) / max(info["dur"], 1) - 96)
                    os.remove(salida)                  # lo creó este mismo paso
                    if kbps < 250:
                        err = "el video es demasiado largo para %d MB" % a.whatsapp_mb
                        break
                    err = codificar(maestro, info, salida, W, H, c, modo, a, lista, ("kbps", kbps))
                    if err:
                        break
            if err:
                errores.append((nombre, err))
                print("❌ %s: %s" % (nombre, err))
                continue
            m = medir(salida)
            hechas.append((c, salida, m))
            print("✅ %s · %dx%d · %.1f s · %.1f MB" % (os.path.basename(salida), m["w"], m["h"], m["dur"],
                                                       os.path.getsize(salida) / 1048576.0))
    finally:
        shutil.rmtree(trabajo, ignore_errors=True)
    if not hechas:
        salir("No se pudo generar ninguna versión.")
    momento = info["dur"] * 0.4
    if subs:
        ini, fin, _ = subs[min(len(subs) - 1, len(subs) // 2)]
        momento = min(info["dur"] - 0.1, (ini + fin) / 2)
    hoja = hoja_revision([(c, s) for c, s, _ in hechas], carpeta, momento)
    informe = os.path.join(carpeta, "informe_versiones.html")
    filas = "".join("<tr><td>%s</td><td>%s</td><td>%dx%d</td><td>%.1f s</td><td>%.1f MB</td></tr>"
                    % (html.escape(c), html.escape(os.path.basename(s)), m["w"], m["h"], m["dur"],
                       os.path.getsize(s) / 1048576.0) for c, s, m in hechas)
    with open(nombre_libre(informe) if os.path.exists(informe) else informe, "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset='utf-8'><title>Versiones</title><style>body{font:15px/1.4 "
                "-apple-system,Segoe UI,Arial,sans-serif;margin:24px}td,th{padding:6px 10px;border-bottom:1px solid "
                "#ddd;text-align:left}img{max-width:100%%;margin-top:16px}</style><h1>Versiones de %s</h1>"
                "<p>%s · modo %s%s%s</p><table><tr><th>Formato</th><th>Archivo</th><th>Tamaño</th><th>Dura</th>"
                "<th>Peso</th></tr>%s</table>%s%s"
                % (html.escape(os.path.basename(maestro)), dt.datetime.now().strftime("%Y-%m-%d %H:%M"), a.modo,
                   " · subtítulos quemados" if subs else "", " · logo" if a.logo else "", filas,
                   ("<img src='%s'>" % os.path.basename(hoja)) if hoja else "",
                   "".join("<p>❌ %s: %s</p>" % (html.escape(n), html.escape(e)) for n, e in errores)))
    print("")
    print("CARPETA=%s" % carpeta)
    if hoja:
        print("REVISION=%s" % hoja)
    print("INFORME=%s" % informe)
    return hechas, errores, hoja


# ----------------------------------------------------------------------------------------------- autoprueba
def autoprueba(_a=None):
    if not FFMPEG:
        salir("Falta ffmpeg.", 3)
    try:
        from PIL import Image
    except ImportError:
        salir("Falta Pillow (la autoprueba prueba los subtítulos): ver SKILL.md «Preparar».", 4)
    base = tempfile.mkdtemp(prefix="versiones_prueba_")
    ok = True
    try:
        maestro = os.path.join(base, "MAESTRO.mov")
        r = correr([FFMPEG, "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "8", "-c:v", "libx264"
                    if "libx264" in correr([FFMPEG, "-hide_banner", "-encoders"]).stdout else "mpeg4",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", maestro])
        if r.returncode != 0:
            salir("No pude armar el video de prueba: " + r.stderr[-200:], 5)
        srt = os.path.join(base, "subs.srt")
        with open(srt, "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:03,000\nHola, esto es una prueba\n\n"
                    "2\n00:00:04,000 --> 00:00:06,500\nUn subtítulo bastante más largo, que tiene que partirse en "
                    "dos líneas sin salirse del cuadro\n\n")
        logo = os.path.join(base, "logo.png")
        Image.new("RGBA", (400, 160), (230, 40, 40, 255)).save(logo)
        args = argparse.Namespace(maestro=maestro, salida=os.path.join(base, "SALIDA"), formatos="9x16,1x1,4x5,16x9",
                                  modo="fondo", foco=0.5, foco_v=0.5, sin_whatsapp=False, whatsapp_mb=16, srt=srt,
                                  caja=False, fuente=None, logo=logo, logo_pos="arriba-derecha", logo_ancho=0.14,
                                  logo_opacidad=0.9, simular=False, ignorar_hdr=False)
        hechas, errores, hoja = generar(args)
        print("")
        esperado = {"9x16": (1080, 1920), "1x1": (1080, 1080), "4x5": (1080, 1350), "16x9": (1920, 1080),
                    "whatsapp": (1280, 720)}
        for c, s, m in hechas:
            bien = (m["w"], m["h"]) == esperado[c] and abs(m["dur"] - 8.0) < 0.2 and m["audio"]
            print("%s %s: %dx%d, %.2f s, audio %s" % ("✅" if bien else "❌", c, m["w"], m["h"], m["dur"],
                                                       "sí" if m["audio"] else "no"))
            ok &= bien
        ok &= len(hechas) == 5 and not errores
        # Subtítulo: a los 5 s (subtítulo 2) tiene que haber texto blanco en la zona de subtítulos; a los 3,5 s, no.
        nueve = [s for c, s, _ in hechas if c == "9x16"][0]

        def blancos(t):
            png = os.path.join(base, "f.png")
            correr([FFMPEG, "-nostdin", "-v", "error", "-ss", str(t), "-i", nueve, "-frames:v", "1", "-y", png])
            img = Image.open(png).convert("RGB").crop((60, int(1920 * 0.60), 1020, int(1920 * 0.77)))
            return sum(1 for p in img.getdata() if min(p) > 235)

        con, sin = blancos(5.0), blancos(3.5)
        bien = con > 2000 and sin < con / 10
        print("%s Subtítulos: %d píxeles blancos con subtítulo, %d sin subtítulo" % ("✅" if bien else "❌", con, sin))
        ok &= bien
        wa = [m for c, s, m in hechas if c == "whatsapp"][0]
        bien = wa["size"] <= 16 * 1024 * 1024
        print("%s WhatsApp: %.2f MB (tope 16 MB)" % ("✅" if bien else "❌", wa["size"] / 1048576.0))
        ok &= bien
        print("%s Hoja de revisión: %s" % ("✅" if hoja else "❌", "sí" if hoja else "no"))
        ok &= bool(hoja)
        # Recorte de un maestro vertical a 16:9 (lo contrario)
        vert = os.path.join(base, "VERTICAL.mp4")
        correr([FFMPEG, "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30", "-t", "3",
                "-pix_fmt", "yuv420p", "-y", vert])
        args2 = argparse.Namespace(**dict(vars(args), maestro=vert, salida=os.path.join(base, "SALIDA2"),
                                          formatos="16x9", modo="recorte", srt=None, logo=None, sin_whatsapp=True))
        h2, e2, _ = generar(args2)
        bien = len(h2) == 1 and (h2[0][2]["w"], h2[0][2]["h"]) == (1920, 1080) and not h2[0][2]["audio"]
        print("%s Vertical sin audio → 16:9 recortado: %s" % ("✅" if bien else "❌", "ok" if bien else h2))
        ok &= bien
        if hoja and os.environ.get("VERSIONES_GUARDAR_REVISION"):
            shutil.copy(hoja, os.environ["VERSIONES_GUARDAR_REVISION"])
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("✅ Autoprueba OK" if ok else "❌ La autoprueba falló")
    sys.exit(0 if ok else 5)


def main():
    _consola_utf8()
    if len(sys.argv) > 1 and sys.argv[1] == "autoprueba":
        autoprueba()
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("maestro")
    ap.add_argument("--salida")
    ap.add_argument("--formatos", default="9x16,1x1,4x5,16x9")
    ap.add_argument("--modo", choices=["fondo", "recorte"], default="fondo")
    ap.add_argument("--foco", type=float, default=0.5)
    ap.add_argument("--foco-v", type=float, default=0.5)
    ap.add_argument("--sin-whatsapp", action="store_true")
    ap.add_argument("--whatsapp-mb", type=int, default=16)
    ap.add_argument("--srt")
    ap.add_argument("--caja", action="store_true")
    ap.add_argument("--fuente")
    ap.add_argument("--logo")
    ap.add_argument("--logo-pos", default="arriba-derecha")
    ap.add_argument("--logo-ancho", type=float, default=0.14)
    ap.add_argument("--logo-opacidad", type=float, default=0.9)
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--ignorar-hdr", action="store_true")
    a = ap.parse_args()
    a.foco, a.foco_v = min(1.0, max(0.0, a.foco)), min(1.0, max(0.0, a.foco_v))
    generar(a)


if __name__ == "__main__":
    main()
