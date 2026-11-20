#!/usr/bin/env python3
"""Baja UN video de un link (YouTube, Vimeo, Instagram, Dropbox, Google Drive o link directo) a una carpeta.

Uso:  python bajar_video.py "<link o ruta>" "<carpeta destino>" [--nombre NOMBRE] [--desde 1:20 --hasta 1:45]

Imprime al final una línea  ARCHIVO=<ruta>  con el archivo listo.
Necesita el entorno ~/.claude/venv-video (yt-dlp, imageio-ffmpeg, gdown); ver SKILL.md.
"""
import argparse
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request

EXT_VIDEO = (".mp4", ".mov", ".mxf", ".mkv", ".m4v", ".avi", ".webm", ".mts")


def limpio(nombre):
    nombre = re.sub(r'[\\/:*?"<>|]+', " ", nombre).strip()
    return re.sub(r"\s+", " ", nombre)[:80] or "video"


def ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return shutil.which("ffmpeg")


def bajar_http(url, destino, nombre):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r:
        disp = r.headers.get("Content-Disposition", "")
        m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", disp)
        original = urllib.parse.unquote(m.group(1)) if m else os.path.basename(urllib.parse.urlparse(url).path)
        ext = os.path.splitext(original)[1].lower() or ".mp4"
        final = os.path.join(destino, (nombre or limpio(os.path.splitext(original)[0])) + ext)
        total = int(r.headers.get("Content-Length") or 0)
        hecho = 0
        with open(final + ".part", "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
                hecho += len(b)
                if total:
                    print("\r  %d de %d MB" % (hecho >> 20, total >> 20), end="", flush=True)
    print()
    if total and hecho != total:
        os.remove(final + ".part")
        sys.exit("La descarga quedó incompleta (%d de %d bytes). Probar de nuevo." % (hecho, total))
    os.replace(final + ".part", final)
    return final


def dropbox(url):
    p = urllib.parse.urlparse(url)
    q = dict(urllib.parse.parse_qsl(p.query))
    q["dl"] = "1"
    return urllib.parse.urlunparse(p._replace(query=urllib.parse.urlencode(q)))


def drive(url, destino, nombre):
    import gdown
    m = re.search(r"/d/([\w-]+)", url) or re.search(r"[?&]id=([\w-]+)", url)
    if not m:
        sys.exit("No encontré el id del archivo en el link de Drive. ¿Es un archivo (no una carpeta)?")
    tmp = gdown.download(id=m.group(1), output=destino + os.sep, quiet=False)
    if not tmp:
        sys.exit("Drive no dejó bajar el archivo: tiene que estar compartido como 'cualquiera con el link'.")
    if nombre:
        final = os.path.join(destino, nombre + os.path.splitext(tmp)[1])
        os.replace(tmp, final)
        return final
    return tmp


def binario_ytdlp():
    """El programa yt-dlp actualizado (el paquete de pip con el Python de la Mac queda viejo para YouTube)."""
    propio = os.path.join(os.path.expanduser("~"), ".claude", "bin", "yt-dlp" + (".exe" if os.name == "nt" else ""))
    return propio if os.path.exists(propio) else shutil.which("yt-dlp")


def ytdlp(url, destino, nombre, desde, hasta):
    import subprocess
    exe = binario_ytdlp()
    if not exe:
        sys.exit("Falta yt-dlp: instalarlo como dice la sección 'Preparar' de SKILL.md.")
    cmd = [exe, "--no-playlist", "--newline", "--windows-filenames",
           "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b",
           "--merge-output-format", "mp4",
           "-o", os.path.join(destino, (nombre or "%(title).70s") + ".%(ext)s"),
           "--print", "after_move:ARCHIVO_YTDLP=%(filepath)s"]
    ff = ffmpeg()
    if ff:
        cmd += ["--ffmpeg-location", ff]
    deno = os.path.join(os.path.expanduser("~"), ".deno", "bin", "deno" + (".exe" if os.name == "nt" else ""))
    if not shutil.which("deno") and os.path.exists(deno):   # YouTube necesita deno; el instalador no siempre lo deja en el PATH
        cmd += ["--js-runtimes", "deno:" + deno]
    if desde or hasta:
        cmd += ["--download-sections", "*%s-%s" % (desde or "0", hasta or "inf"), "--force-keyframes-at-cuts"]
    r = subprocess.run(cmd + [url], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"ARCHIVO_YTDLP=(.+)", r.stdout)
    if r.returncode or not m:
        sys.exit("yt-dlp no pudo bajar el video:\n" + (r.stderr or r.stdout)[-1500:]
                 + "\nSi dice que falta un 'JavaScript runtime', instalar deno (ver SKILL.md). "
                   "Si es otra cosa, actualizar yt-dlp: '<yt-dlp> -U' o 'brew upgrade yt-dlp'.")
    return m.group(1).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("link")
    ap.add_argument("destino")
    ap.add_argument("--nombre")
    ap.add_argument("--desde")
    ap.add_argument("--hasta")
    a = ap.parse_args()
    os.makedirs(a.destino, exist_ok=True)
    nombre = limpio(a.nombre) if a.nombre else None
    link = a.link.strip()

    if os.path.exists(os.path.expanduser(link)):                       # archivo que ya está en la compu
        src = os.path.expanduser(link)
        final = os.path.join(a.destino, (nombre or limpio(os.path.splitext(os.path.basename(src))[0]))
                             + os.path.splitext(src)[1])
        if os.path.abspath(src) != os.path.abspath(final):
            shutil.copy2(src, final)                                     # copia: el original no se toca
    elif "dropbox.com" in link:
        final = bajar_http(dropbox(link), a.destino, nombre)
    elif "drive.google.com" in link:
        final = drive(link, a.destino, nombre)
    elif "wetransfer.com" in link or "we.tl" in link:
        sys.exit("WeTransfer no deja bajar por código. Bájalo desde el navegador y pásame la ruta del archivo.")
    elif urllib.parse.urlparse(link).path.lower().endswith(EXT_VIDEO):
        final = bajar_http(link, a.destino, nombre)
    else:                                                                # YouTube, Vimeo, Instagram, TikTok…
        final = ytdlp(link, a.destino, nombre, a.desde, a.hasta)

    if not os.path.exists(final) or os.path.getsize(final) == 0:
        sys.exit("No quedó ningún archivo. Revisar el link.")
    print("ARCHIVO=%s" % os.path.abspath(final))


if __name__ == "__main__":
    main()
