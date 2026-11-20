#!/usr/bin/env python3
"""Arma una secuencia de Premiere con UN video y la abre en Premiere Pro.

Uso:  python armar_premiere.py "<video>" "<carpeta PREMIERE>" --nombre "NOMBRE" [--no-abrir]

Mide el video (tamaño, cuadros por segundo, duración, audio), escribe <NOMBRE>.xml (Final Cut Pro XML,
que Premiere abre en cualquier versión) con una secuencia del mismo formato que el video y el video
entero en V1/A1, y lo abre con Premiere. Al guardar (Cmd+S / Ctrl+S) queda el .prproj al lado.
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from xml.sax.saxutils import escape


def ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return shutil.which("ffmpeg") or sys.exit("Falta ffmpeg: instalar imageio-ffmpeg en el venv (ver SKILL.md).")


def medir(video):
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", video], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    t = r.stderr
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", t)
    v = re.search(r"Stream #.*?Video:.*?(\d{2,5})x(\d{2,5})", t)
    if not d or not v:
        sys.exit("No pude leer el video (¿está completo?).\n" + t[-800:])
    seg = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))
    w, h = int(v.group(1)), int(v.group(2))
    linea = re.search(r"Stream #.*?Video:.*", t).group(0)
    f = re.search(r"([\d.]+) fps", linea) or re.search(r"([\d.]+) tbr", linea)
    fps = float(f.group(1)) if f else 30.0
    rot = re.search(r"rotation of (-?[\d.]+)", t)
    if rot and abs(abs(float(rot.group(1))) - 90) < 1:               # video vertical de celular
        w, h = h, w
    a = re.search(r"Stream #.*?Audio:.*?(\d+) Hz, (mono|stereo|[\d.]+)", t)
    audio = None
    if a:
        canales = {"mono": 1, "stereo": 2}.get(a.group(2), 2)
        audio = (int(a.group(1)), canales)
    return seg, w, h, fps, audio


def base_tiempo(fps):
    for ntsc, nominal in ((23.976, 24), (29.97, 30), (59.94, 60), (47.952, 48), (119.88, 120)):
        if abs(fps - ntsc) < 0.01:
            return nominal, True
    return int(round(fps)), False


def rate(tb, ntsc):
    return "<rate><timebase>%d</timebase><ntsc>%s</ntsc></rate>" % (tb, "TRUE" if ntsc else "FALSE")


def xml(video, nombre, seg, w, h, fps, audio):
    tb, ntsc = base_tiempo(fps)
    real = tb * (1000 / 1001 if ntsc else 1)
    n = int(round(seg * real))
    url = "file://localhost" + urllib.parse.quote(os.path.abspath(video).replace("\\", "/")
                                                  if os.sep == "/" else "/" + os.path.abspath(video).replace("\\", "/"))
    archivo = os.path.basename(video)
    R = rate(tb, ntsc)
    fmt_video = ("<samplecharacteristics>%s<width>%d</width><height>%d</height><anamorphic>FALSE</anamorphic>"
                 "<pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance>"
                 "</samplecharacteristics>" % (R, w, h))
    media_audio = ""
    if audio:
        media_audio = ("<audio><samplecharacteristics><depth>16</depth><samplerate>%d</samplerate>"
                       "</samplecharacteristics><channelcount>%d</channelcount></audio>" % audio)
    file_full = ("<file id=\"file-1\"><name>%s</name><pathurl>%s</pathurl>%s<duration>%d</duration>"
                 "<media><video>%s</video>%s</media></file>" % (escape(archivo), url, R, n, fmt_video, media_audio))

    def clip(cid, contenido, extra=""):
        return ("<clipitem id=\"%s\"><name>%s</name><enabled>TRUE</enabled><duration>%d</duration>%s"
                "<start>0</start><end>%d</end><in>0</in><out>%d</out>%s%s</clipitem>"
                % (cid, escape(archivo), n, R, n, n, contenido, extra))

    links = ""
    pistas_audio = ""
    if audio:
        canales = audio[1]
        ids = ["clipitem-v"] + ["clipitem-a%d" % i for i in range(1, canales + 1)]
        links = "".join("<link><linkclipref>%s</linkclipref><mediatype>%s</mediatype><trackindex>%d</trackindex>"
                        "<clipindex>1</clipindex></link>" % (c, "video" if i == 0 else "audio", max(i, 1))
                        for i, c in enumerate(ids))
        # Un canal por pista (A1 izquierdo, A2 derecho). Probado 13-11-2026 en Premiere 26.3: con una sola pista
        # marcada premiereTrackType="Stereo" Premiere importa la secuencia SIN audio.
        for i in range(1, canales + 1):
            pistas_audio += ("<track>%s</track>" % clip(
                "clipitem-a%d" % i, "<file id=\"file-1\"/><sourcetrack><mediatype>audio</mediatype>"
                "<trackindex>%d</trackindex></sourcetrack>" % i, links))
        pistas_audio = ("<audio><numOutputChannels>2</numOutputChannels><format><samplecharacteristics>"
                        "<depth>16</depth><samplerate>%d</samplerate></samplecharacteristics></format>%s</audio>"
                        % (audio[0], pistas_audio))
    pista_video = "<track>%s</track>" % clip("clipitem-v", file_full, links)
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE xmeml>\n<xmeml version=\"4\">"
            "<sequence id=\"sequence-1\"><name>%s</name><duration>%d</duration>%s"
            "<media><video><format>%s</format>%s</video>%s</media>"
            "<timecode>%s<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode>"
            "</sequence></xmeml>\n" % (escape(nombre), n, R, fmt_video, pista_video, pistas_audio, R))


def premiere():
    if sys.platform == "darwin":
        apps = sorted(glob.glob("/Applications/Adobe Premiere Pro*/Adobe Premiere Pro*.app"))
        return apps[-1] if apps else None
    if os.name == "nt":
        base = os.environ.get("ProgramFiles", r"C:\Program Files")
        exes = sorted(glob.glob(os.path.join(base, "Adobe", "Adobe Premiere Pro*", "Adobe Premiere Pro.exe")))
        return exes[-1] if exes else None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("carpeta")
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--no-abrir", action="store_true")
    a = ap.parse_args()
    seg, w, h, fps, audio = medir(a.video)
    os.makedirs(a.carpeta, exist_ok=True)
    salida = os.path.join(a.carpeta, a.nombre + ".xml")
    with open(salida, "w", encoding="utf-8") as f:
        f.write(xml(a.video, a.nombre, seg, w, h, fps, audio))
    print("Video: %dx%d, %.3f fps, %.1f s, audio: %s" % (w, h, fps, seg,
          "%d Hz, %d canal(es)" % audio if audio else "sin audio"))
    print("XML=%s" % os.path.abspath(salida))
    if a.no_abrir:
        return
    app = premiere()
    if not app:
        print("No encontré Premiere Pro instalado: abrir el XML a mano (Archivo > Abrir proyecto).")
        return
    if sys.platform == "darwin":
        subprocess.run(["open", "-a", app, salida], check=True)
    else:
        subprocess.Popen([app, salida])
    print("Abriendo en %s" % os.path.basename(app))


if __name__ == "__main__":
    main()
