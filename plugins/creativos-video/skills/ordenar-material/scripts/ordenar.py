#!/usr/bin/env python3
"""Ordena archivos sueltos de una carpeta en subcarpetas por tipo y les pone la fecha adelante.
Por defecto solo simula. --aplicar mueve. --deshacer revierte usando _ordenar-log.csv. Nunca borra."""
import argparse, csv, datetime as dt, sys
from collections import Counter
from pathlib import Path

TIPOS = {
    "VIDEO": "mp4 mov mxf avi mkv m4v mts r3d braw insv 3gp webm",
    "AUDIO": "wav mp3 aac m4a aif aiff flac ogg opus",
    "FOTOS": "jpg jpeg png heic tif tiff raw cr2 cr3 nef arw dng webp",
    "GRAFICOS": "psd ai svg eps pdf mogrt",
    "PROYECTOS": "prproj aep drp fcpxml xml edl otio",
    "DOCUMENTOS": "doc docx txt md srt vtt xlsx csv pptx key pages",
}
EXT = {e: t for t, es in TIPOS.items() for e in es.split()}
LOG = "_ordenar-log.csv"
# Carpetas que las cámaras crean en la tarjeta: lo que está ahí (o al lado, como el lastclip.txt de P2) no se mueve
TARJETA = {"private", "m4root", "xdroot", "contents", "avchd", "bdmv", "dcim", "clip", "canonmsc", "clips001"}


def copia_verificada(root: Path):
    """Si la carpeta es (o está dentro de) una copia verificada o una tarjeta copiada tal cual, dice por qué.

    Señales: ASC MHL (carpeta ascmhl/), un .mhl adentro o al lado con su nombre (ShotPut, Hedge, OffShoot,
    Silverstack), las sumas de ShotPut (*ChecksumFileSPP.*), la carpeta _DESCARGA de descargar-tarjeta, o la
    estructura de una tarjeta de cámara (PRIVATE, XDROOT, CONTENTS, DCIM…)."""
    partes = [p.lower() for p in root.parts]
    for k, p in enumerate(partes):
        # «private» solo cuenta como tarjeta con M4ROOT/AVCHD/XDROOT abajo (/private es también una carpeta de macOS)
        if (p in TARJETA and p != "private") or (p == "private" and k + 1 < len(partes)
                                                 and partes[k + 1] in ("m4root", "avchd", "xdroot")):
            return f"está dentro de la estructura de una tarjeta de cámara («{root.parts[k]}»)"
    hijo = None
    for d in [root, *root.parents]:
        try:
            hijos = list(d.iterdir())
        except OSError:
            hijo = d
            continue
        carpetas = [h.name.lower() for h in hijos if h.is_dir()]
        for h in hijos:
            n = h.name.lower()
            if n == "ascmhl" and h.is_dir():
                return f"«{d.name}» tiene un sello de verificación ASC MHL (carpeta ascmhl)"
            if n == "_descarga" and h.is_dir():
                return f"«{d.name}» es una copia hecha con descargar-tarjeta (_DESCARGA)"
            if "checksumfilespp" in n:
                return f"«{d.name}» tiene las sumas de verificación de ShotPut ({h.name})"
            if n.endswith(".mhl"):
                de = max((c for c in carpetas if n.startswith(c)), key=len, default=None)
                if d == root or de is None or (hijo is not None and de == hijo.name.lower()):
                    return f"hay un sello de verificación MHL ({h.name}) en «{d.name}»"
        if d == root and any(c in TARJETA and (c != "private" or any((d / h.name / x).is_dir()
                                                                     for h in hijos if h.name.lower() == "private"
                                                                     for x in ("M4ROOT", "AVCHD", "XDROOT")))
                             for c in carpetas):
            return "tiene adentro la estructura de una tarjeta de cámara"
        hijo = d
    return None

def libre(p: Path) -> Path:
    if not p.exists(): return p
    i = 2
    while (q := p.with_name(f"{p.stem}_{i}{p.suffix}")).exists(): i += 1
    return q

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta"); ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--deshacer", action="store_true"); ap.add_argument("--sin-fecha", action="store_true")
    ap.add_argument("--por-dia", action="store_true")
    a = ap.parse_args()
    root = Path(a.carpeta).expanduser()
    if not root.is_dir(): sys.exit(f"No es una carpeta: {root}")
    log = root / LOG

    if a.deshacer:
        if not log.exists(): sys.exit("No hay nada para deshacer (falta _ordenar-log.csv)")
        filas = list(csv.reader(log.open(encoding="utf-8")))[1:]
        for orig, nuevo in reversed(filas):
            o, n = root / orig, root / nuevo
            if n.exists() and not o.exists(): o.parent.mkdir(parents=True, exist_ok=True); n.rename(o)
        log.rename(root / f"_ordenar-log-deshecho-{dt.datetime.now():%Y%m%d-%H%M%S}.csv")
        for d in sorted(root.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()): d.rmdir()
        print(f"Deshecho: {len(filas)} archivos volvieron a su lugar"); return

    motivo = copia_verificada(root.resolve())
    if motivo:
        print(f"🛑 No ordeno {root}: {motivo}.\n"
              "   Mover o renombrar algo ahí rompe la verificación de la copia (el MHL o las sumas de ShotPut) y la "
              "estructura de la tarjeta, que Premiere necesita.\n"
              "   El orden se arma en Premiere: sincronizar-audio y asistente-de-edicion dejan un XML con una carpeta "
              "por día, por cámara y de audio, sin tocar las copias.")
        sys.exit(3)
    archivos = [p for p in root.iterdir() if p.is_file() and not p.name.startswith((".", "_ordenar"))]
    plan, cuenta = [], Counter()
    for p in sorted(archivos):
        tipo = EXT.get(p.suffix.lower().lstrip("."), "OTROS")
        fecha = dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")
        nombre = p.name if a.sin_fecha or p.name[:10] == fecha else f"{fecha}_{p.name}"
        dest = root / tipo / (fecha if a.por_dia and tipo in ("VIDEO", "AUDIO", "FOTOS") else "") / nombre
        plan.append((p, dest)); cuenta[tipo] += 1
    if not plan: print("No hay archivos sueltos para ordenar."); return
    print(f"{len(plan)} archivos en {root}")
    for t, c in cuenta.most_common(): print(f"  {t:<11} {c}")
    for p, d in plan[:6]: print(f"  {p.name}  →  {d.relative_to(root)}")
    if len(plan) > 6: print(f"  … y {len(plan) - 6} más")
    if any(p.suffix.lower() == ".prproj" for p in archivos) or list(root.rglob("*.prproj")):
        print("⚠️  Hay un proyecto de Premiere acá: al mover el material habrá que relinkearlo.")
    if not a.aplicar: print("\n(Simulación: no se movió nada. Agrega --aplicar para hacerlo.)"); return
    nuevo_log = not log.exists()
    with log.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo_log: w.writerow(["original", "nuevo"])
        for p, d in plan:
            d.parent.mkdir(parents=True, exist_ok=True); d = libre(d)
            p.rename(d); w.writerow([p.relative_to(root).as_posix(), d.relative_to(root).as_posix()])
    print(f"Listo. Para deshacer: --deshacer (registro en {LOG})")

if __name__ == "__main__":
    main()
