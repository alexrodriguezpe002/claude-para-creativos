#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
descarga.py · Copia una tarjeta de cámara (o un SSD) a 2 o más discos con verificación real.

Qué hace, en simple:
  1. Lee cada archivo de la tarjeta UNA vez, le saca su huella (MD5) y lo escribe en todos los discos a la vez.
  2. Vuelve a leer cada copia desde el disco (no desde la memoria de la compu) y compara la huella.
     Recién cuando coincide, la copia recibe su nombre final.
  3. Al terminar deja en cada disco un manifiesto .mhl (la lista de huellas, el formato que leen Hedge,
     OffShoot, ShotPut y Silverstack) y un informe: HTML (para ver o imprimir a PDF) y CSV (para Excel).

Nunca escribe, borra ni formatea la tarjeta. Nunca pisa un archivo que ya existe.
Si se corta (tarjeta afuera, disco lleno, compu apagada), el mismo comando sigue desde donde quedó.

Uso (Mac: python3 · Windows: py):
  descarga.py detectar [--json]
  descarga.py plan    --origen RUTA [--destino D1 --destino D2] [--proyecto P] [--tarjeta T] [--plantilla ...]
  descarga.py copiar  (los mismos datos que plan)
  descarga.py verificar CARPETA [CARPETA2 ...] [--rapido] [--json]
  descarga.py manifiesto CARPETA          (crea el manifiesto de una carpeta que no tiene)
  descarga.py informe CARPETA             (rehace el informe de una copia)
  descarga.py config mostrar | config guardar [--proyecto ...] [--destino ...] ...
  descarga.py historial
  descarga.py autoprueba

Solo biblioteca estándar de Python 3.8 o más nuevo. Mac y Windows (y Linux).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import getpass
import hashlib
import html
import json
import os
import plistlib
import queue
import re
import shutil
import signal
import socket
import stat
import string
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as cf_wait
from pathlib import Path

VERSION = "1.0.0"
HERRAMIENTA = "descargar-tarjeta (kit creativos)"
BLOQUE = 8 * 1024 * 1024          # 8 MiB: múltiplo de cualquier sector, rápido con archivos grandes
ES_MAC = sys.platform == "darwin"
ES_WIN = os.name == "nt"
SUFIJO_PARCIAL = ".parcial-descarga"
CARPETA_META = "_DESCARGA"
PLANTILLA_DEFECTO = "{proyecto}/{fecha}/{tarjeta}"
ALGORITMOS = ("md5", "sha1")      # los dos que leen todos los programas de DIT (MHL 1.1 y ASC MHL)

IGNORAR = {
    ".ds_store", ".spotlight-v100", ".fseventsd", ".trashes", ".temporaryitems", ".documentrevisions-v100",
    ".apdisk", ".metadata_never_index", ".com.apple.timemachine.donotpresent", "system volume information",
    "$recycle.bin", "thumbs.db", "desktop.ini",
}
EXT_VIDEO = {".mp4", ".mov", ".mxf", ".mts", ".m2ts", ".avi", ".mkv", ".m4v", ".braw", ".r3d", ".crm",
             ".ari", ".insv", ".360", ".lrv", ".3gp", ".mpg", ".mpeg", ".wmv", ".dng_seq"}
EXT_AUDIO = {".wav", ".bwf", ".mp3", ".aac", ".m4a", ".aif", ".aiff", ".flac"}
EXT_FOTO = {".jpg", ".jpeg", ".heic", ".heif", ".png", ".tif", ".tiff", ".dng", ".arw", ".cr2", ".cr3",
            ".nef", ".raf", ".orf", ".rw2", ".srw", ".pef", ".gpr"}
NOMBRES_GENERICOS = {"untitled", "sin título", "sin titulo", "no name", "no_name", "noname", "eos_digital",
                     "canon", "nikon", "sony", "sd", "sdcard", "sd card", "card", "disk", "usb", "camera",
                     "gopro", "dji", "lumix", "fujifilm", "om system", "olympus", "removable disk",
                     "disco extraíble", "nuevo vol", "new volume", "untitled 1", "untitled 2"}
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

EXIT_OK, EXIT_USO, EXIT_NO_EMPIEZA, EXIT_ORIGEN, EXIT_DESTINO, EXIT_VERIFICACION, EXIT_CORTADO = 0, 1, 2, 3, 4, 5, 130

_PARAR = threading.Event()        # Ctrl+C o señal de apagado


# ───────────────────────────── utilidades ─────────────────────────────

def _consola_utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def decir(*partes):
    print(*partes, flush=True)


def ahora():
    return dt.datetime.now().astimezone()


def fecha_legible(d: dt.datetime, hora=True):
    return f"{DIAS[d.weekday()]} {d:%d-%m-%Y}" + (f" {d:%H:%M}" if hora else "")


def iso_utc(ts=None):
    d = dt.datetime.fromtimestamp(ts, dt.timezone.utc) if ts is not None else dt.datetime.now(dt.timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def marca_tiempo():
    return ahora().strftime("%Y-%m-%d_%H%M%S")


def tam(n):
    if n is None:
        return "—"
    for u, f in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if n >= f:
            return f"{n / f:.1f} {u}".replace(".", ",")
    return f"{n} B"


def duracion(s):
    if s is None:
        return "—"
    s = int(round(s))
    h, r = divmod(s, 3600)
    m, s2 = divmod(r, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s2:02d} s"
    return f"{s2} s"


def codigo_tiempo(s):
    if s is None:
        return ""
    s = float(s)
    h, r = divmod(int(s), 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def clave_natural(texto):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", texto)]


def limpiar_nombre(texto: str) -> str:
    """Nombre válido para carpetas en Mac y Windows."""
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(texto)).strip().strip(".")
    t = re.sub(r"\s+", "_", t)
    return t[:80]


def dir_sistema() -> Path:
    d = os.environ.get("RESPALDO_MATERIAL_DIR")
    return Path(d).expanduser() if d else Path.home() / "MI-SISTEMA-CLAUDE" / "respaldo-material"


def guardar_json(p: Path, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def leer_config() -> dict:
    p = dir_sistema() / "config.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:
        raise SystemExit(f"❌ No se puede leer {p} ({e}). Revisa el archivo o bórralo para empezar de cero.")


def _mantener_despierta():
    """Que la compu no se duerma mientras copia (se suelta sola al terminar)."""
    try:
        if ES_MAC and shutil.which("caffeinate"):
            subprocess.Popen(["caffeinate", "-ims", "-w", str(os.getpid())],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif ES_WIN:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    except Exception:
        pass


# ───────────────────────────── discos y tarjetas ─────────────────────────────

def punto_de_montaje(ruta: str) -> str:
    p = os.path.abspath(ruta)
    if ES_WIN:
        return os.path.splitdrive(p)[0] + "\\"
    while not os.path.ismount(p):
        padre = os.path.dirname(p)
        if padre == p:
            break
        p = padre
    return p


def _diskutil(ruta: str) -> dict:
    if not ES_MAC:
        return {}
    try:
        r = subprocess.run(["diskutil", "info", "-plist", ruta], capture_output=True, timeout=20)
        return plistlib.loads(r.stdout) if r.returncode == 0 and r.stdout else {}
    except Exception:
        return {}


def _info_win(raiz: str) -> dict:
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        nombre = ctypes.create_unicode_buffer(261)
        fs = ctypes.create_unicode_buffer(261)
        serie = ctypes.c_uint32()
        k32.GetVolumeInformationW(ctypes.c_wchar_p(raiz), nombre, 261, ctypes.byref(serie), None, None, fs, 261)
        tipo = k32.GetDriveTypeW(ctypes.c_wchar_p(raiz))
        return {"nombre": nombre.value or None, "uuid": f"{serie.value:08X}" if serie.value else None,
                "fs": fs.value or None, "extraible": tipo == 2, "interno": tipo == 3 and raiz.upper().startswith(
                    os.environ.get("SystemDrive", "C:").upper()), "disco_fisico": raiz[:2].upper(),
                "tipo_win": tipo}
    except Exception:
        return {}


def info_volumen(ruta: str) -> dict:
    """«nombre» = el de la tarjeta o carpeta; «disco» = el del disco que la contiene."""
    ruta = os.path.abspath(ruta)
    mp = punto_de_montaje(ruta)
    es_raiz = os.path.normcase(ruta.rstrip("/\\") or "/") == os.path.normcase(mp.rstrip("/\\") or "/")
    base_mp = os.path.basename(mp.rstrip("/\\")) or mp
    info = {"ruta": ruta, "montaje": mp, "es_raiz": es_raiz,
            "nombre": base_mp if es_raiz else os.path.basename(ruta.rstrip("/\\")),
            "disco": base_mp if mp not in ("/", "\\") else "disco interno",
            "uuid": None, "fs": None, "extraible": None, "interno": None, "disco_fisico": None, "protocolo": None}
    try:
        u = shutil.disk_usage(ruta if os.path.exists(ruta) else mp)
        info.update(total=u.total, libre=u.free, usado=u.used)
    except OSError:
        info.update(total=None, libre=None, usado=None)
    if ES_MAC:
        d = _diskutil(mp)
        if d:
            if d.get("VolumeName"):
                info["disco"] = d["VolumeName"]
                if es_raiz:
                    info["nombre"] = d["VolumeName"]
            info["uuid"] = (d.get("VolumeUUID") or d.get("DiskUUID")) if es_raiz else None
            info["fs"] = d.get("FilesystemName") or d.get("FilesystemType")
            info["extraible"] = bool(d.get("RemovableMedia") or d.get("Removable") or d.get("Ejectable"))
            info["interno"] = bool(d.get("Internal"))
            info["protocolo"] = d.get("BusProtocol")
            fisico = None
            for s in d.get("APFSPhysicalStores") or []:
                m = re.match(r"(disk\d+)", str(s.get("APFSPhysicalStore", "")))
                if m:
                    fisico = m.group(1)
                    break
            info["disco_fisico"] = fisico or d.get("ParentWholeDisk")
    elif ES_WIN:
        w = _info_win(mp)
        for k in ("fs", "extraible", "interno", "disco_fisico"):
            if w.get(k) is not None:
                info[k] = w[k]
        if w.get("nombre"):
            info["disco"] = f"{w['nombre']} ({mp[:2]})"
            if es_raiz:
                info["nombre"] = w["nombre"]
        if es_raiz:
            info["uuid"] = w.get("uuid")
    if not info["disco_fisico"]:
        try:
            info["disco_fisico"] = f"dev{os.stat(mp).st_dev}"
        except OSError:
            pass
    return info


def tamano_cluster(ruta: str) -> int:
    try:
        if hasattr(os, "statvfs"):
            v = os.statvfs(ruta)
            return max(int(v.f_frsize or v.f_bsize or 4096), 512)
        if ES_WIN:
            import ctypes
            spc, bps, a, b = (ctypes.c_ulong() for _ in range(4))
            ctypes.windll.kernel32.GetDiskFreeSpaceW(ctypes.c_wchar_p(punto_de_montaje(ruta)),
                                                     ctypes.byref(spc), ctypes.byref(bps),
                                                     ctypes.byref(a), ctypes.byref(b))
            return max(spc.value * bps.value, 512)
    except Exception:
        pass
    return 1024 * 1024


def _hijos(p):
    try:
        return {e.name.lower(): e.path for e in os.scandir(p)}
    except OSError:
        return {}


def _existe(raiz, *partes):
    p = raiz
    for parte in partes:
        h = _hijos(p)
        if parte.lower() not in h:
            return False
        p = h[parte.lower()]
    return True


def _busca_ext(raiz, exts, prof=2, tope=4000):
    vistos, pila = 0, [(raiz, 0)]
    while pila:
        p, d = pila.pop()
        try:
            entradas = list(os.scandir(p))
        except OSError:
            continue
        for e in entradas:
            vistos += 1
            if vistos > tope:
                return False
            n = e.name.lower()
            if os.path.splitext(n)[1] in exts:
                return True
            try:
                es_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                es_dir = False
            if es_dir and d < prof and n not in IGNORAR and not n.startswith("."):
                pila.append((e.path, d + 1))
    return False


# (id, nombre legible, prefijo para nombrar tarjetas, comprobación). Lo específico va primero.
FIRMAS_CAMARA = [
    ("sony-xavc", "Sony (XAVC S/HS · PRIVATE/M4ROOT)", "SONY", lambda r: _existe(r, "PRIVATE", "M4ROOT")),
    ("sony-xdcam", "Sony XDCAM/XAVC (XDROOT · FX6, FX9, Venice)", "SONY", lambda r: _existe(r, "XDROOT")),
    ("canon-xf", "Canon Cinema EOS (XF-AVC · CONTENTS/CLIPS001)", "CANON",
     lambda r: _existe(r, "CONTENTS", "CLIPS001")),
    ("p2", "Panasonic P2 (CONTENTS/CLIP)", "P2", lambda r: _existe(r, "CONTENTS", "CLIP")),
    ("avchd", "AVCHD (PRIVATE/AVCHD)", "AVCHD", lambda r: _existe(r, "PRIVATE", "AVCHD")),
    ("clip", "Clips de cámara (carpeta CLIP)", "CLIP", lambda r: _existe(r, "CLIP")),
    ("red", "RED (R3D)", "RED", lambda r: _busca_ext(r, {".rdm", ".rdc", ".r3d"}, prof=2)),
    ("blackmagic", "Blackmagic (BRAW)", "BMD", lambda r: _busca_ext(r, {".braw"}, prof=2)),
    ("dcim", "Cámara, celular, dron o GoPro (DCIM)", "CAMARA", lambda r: _existe(r, "DCIM")),
    ("audio", "Grabadora de audio (WAV)", "AUDIO", lambda r: _busca_ext(r, {".wav", ".bwf"}, prof=2)),
]


def tipo_de_camara(raiz: str):
    encontradas = []
    for cid, nombre, corto, prueba in FIRMAS_CAMARA:
        try:
            if prueba(raiz):
                encontradas.append({"id": cid, "nombre": nombre, "corto": corto})
        except Exception:
            pass
    if not encontradas:
        return None
    principal = dict(encontradas[0])
    principal["tambien"] = [e["id"] for e in encontradas[1:]]
    return principal


def volumenes_montados():
    """Rutas de los volúmenes conectados, sin el disco del sistema."""
    override = os.environ.get("DESCARGA_VOLUMENES")
    if override:
        try:
            return sorted(e.path for e in os.scandir(override) if e.is_dir())
        except OSError:
            return []
    if ES_MAC:
        rutas = []
        try:
            for e in os.scandir("/Volumes"):
                try:
                    if os.path.realpath(e.path) == "/" or not e.is_dir():
                        continue
                except OSError:
                    continue
                rutas.append(e.path)
        except OSError:
            pass
        return sorted(rutas)
    if ES_WIN:
        import ctypes
        k32 = ctypes.windll.kernel32
        mascara = k32.GetLogicalDrives()
        sistema = os.environ.get("SystemDrive", "C:").upper()
        rutas = []
        for i, letra in enumerate(string.ascii_uppercase):
            if mascara & (1 << i):
                raiz = f"{letra}:\\"
                if raiz[:2].upper() == sistema:
                    continue
                if k32.GetDriveTypeW(ctypes.c_wchar_p(raiz)) in (2, 3) and os.path.isdir(raiz):
                    rutas.append(raiz)
        return rutas
    usuario = getpass.getuser()
    rutas = []
    for base in (f"/media/{usuario}", f"/run/media/{usuario}", "/mnt"):
        try:
            rutas += [e.path for e in os.scandir(base) if e.is_dir()]
        except OSError:
            pass
    return sorted(rutas)


def detectar(contar=True):
    cfg = leer_config()
    destinos_cfg = [os.path.abspath(d) for d in cfg.get("destinos", [])]
    salida = []
    for ruta in volumenes_montados():
        info = info_volumen(ruta)
        info["camara"] = tipo_de_camara(ruta)
        base = info["ruta"].rstrip("/\\")
        info["es_destino_guardado"] = any(d == base or d.startswith(base + os.sep) for d in destinos_cfg)
        if info["camara"] and contar:
            archivos, _ = listar_origen(ruta)
            info["archivos"] = len(archivos)
            info["clips"] = sum(1 for a in archivos if a.tipo == "video")
            info["bytes"] = sum(a.tam for a in archivos)
        salida.append(info)
    salida.sort(key=lambda v: (v["camara"] is None, v["nombre"].lower()))
    return salida


# ───────────────────────────── archivos de origen ─────────────────────────────

class Arch:
    __slots__ = ("rel", "ruta", "tam", "mtime", "atime", "tipo")

    def __init__(self, rel, ruta, st):
        self.rel, self.ruta, self.tam = rel, ruta, st.st_size
        self.mtime, self.atime = st.st_mtime, st.st_atime
        ext = os.path.splitext(rel)[1].lower()
        self.tipo = ("video" if ext in EXT_VIDEO else "audio" if ext in EXT_AUDIO
                     else "foto" if ext in EXT_FOTO else "otro")


def listar_origen(origen):
    """Todos los archivos de la tarjeta (sin la basura del sistema). Devuelve (archivos, ignorados)."""
    origen = os.path.abspath(origen)
    archivos, ignorados = [], 0
    for raiz, dirs, files in os.walk(origen, topdown=True, followlinks=False):
        rel_raiz = os.path.relpath(raiz, origen)
        quedan = []
        for d in dirs:
            dl = d.lower()
            if dl in IGNORAR or (rel_raiz == "." and d == CARPETA_META):
                ignorados += 1
                continue
            quedan.append(d)
        dirs[:] = sorted(quedan, key=clave_natural)
        for f in files:
            fl = f.lower()
            if fl in IGNORAR or f.startswith("._") or f.endswith(SUFIJO_PARCIAL) or \
                    (rel_raiz == "." and fl.endswith(".mhl")):
                ignorados += 1
                continue
            p = os.path.join(raiz, f)
            try:
                st = os.stat(p, follow_symlinks=False)
            except OSError:
                ignorados += 1
                continue
            if not stat.S_ISREG(st.st_mode):
                ignorados += 1
                continue
            rel = f if rel_raiz == "." else rel_raiz.replace(os.sep, "/") + "/" + f
            archivos.append(Arch(rel, p, st))
    archivos.sort(key=lambda a: clave_natural(a.rel))
    return archivos, ignorados


def firma_de(archivos):
    h = hashlib.sha1()
    for a in archivos:
        h.update(f"{a.rel}|{a.tam}|{int(a.mtime)}\n".encode("utf-8"))
    return h.hexdigest()


def fecha_de_grabacion(archivos):
    """El día en que se grabó la mayoría de los clips (o de los archivos)."""
    base = [a for a in archivos if a.tipo == "video"] or archivos
    if not base:
        return ahora().strftime("%Y-%m-%d")
    dias = Counter(dt.datetime.fromtimestamp(a.mtime).strftime("%Y-%m-%d") for a in base)
    return dias.most_common(1)[0][0]


# ───────────────────────────── lectura, huellas y escritura ─────────────────────────────

class _NoDisponible(Exception):
    pass


def _sin_cache(fd):
    """Que la lectura venga del disco y no de la memoria de la compu."""
    if ES_MAC:
        try:
            import fcntl
            fcntl.fcntl(fd, getattr(fcntl, "F_NOCACHE", 48), 1)
            return True
        except Exception:
            return False
    if hasattr(os, "posix_fadvise"):
        try:
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
            return True
        except Exception:
            return False
    return False


def _forzar_a_disco(fd, completo=False):
    """fsync de cada archivo. completo=True además vacía la memoria interna del disco (Mac: F_FULLFSYNC);
    eso se hace una vez por disco al terminar, antes de decir que se puede formatear la tarjeta."""
    if completo and ES_MAC:
        try:
            import fcntl
            fcntl.fcntl(fd, getattr(fcntl, "F_FULLFSYNC", 51))
            return
        except Exception:
            pass
    os.fsync(fd)


def _bloques_win_sin_cache(ruta):
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crear = k32.CreateFileW
    crear.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                      wintypes.DWORD, wintypes.HANDLE]
    crear.restype = wintypes.HANDLE
    leer = k32.ReadFile
    leer.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                     wintypes.LPVOID]
    leer.restype = wintypes.BOOL
    reservar = k32.VirtualAlloc
    reservar.argtypes = [wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
    reservar.restype = wintypes.LPVOID
    liberar = k32.VirtualFree
    liberar.argtypes = [wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD]
    cerrar = k32.CloseHandle
    ruta_larga = ruta if ruta.startswith("\\\\?\\") else "\\\\?\\" + os.path.abspath(ruta)
    h = crear(ruta_larga, 0x80000000, 0x1 | 0x2, None, 3, 0x20000000 | 0x08000000, None)
    if h is None or h == ctypes.c_void_p(-1).value:
        raise _NoDisponible()
    buf = reservar(None, BLOQUE, 0x3000, 0x04)
    if not buf:
        cerrar(h)
        raise _NoDisponible()
    try:
        n = wintypes.DWORD(0)
        while True:
            if not leer(h, buf, BLOQUE, ctypes.byref(n), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if n.value == 0:
                break
            yield ctypes.string_at(buf, n.value)
    finally:
        liberar(buf, 0, 0x8000)
        cerrar(h)


MODO_RELECTURA = {"valor": "sin caché" if (ES_MAC or hasattr(os, "posix_fadvise")) else "con caché"}


def _bloques(ruta, sin_cache=True):
    if ES_WIN and sin_cache:
        gen = _bloques_win_sin_cache(ruta)
        try:
            primero = next(gen)
            MODO_RELECTURA["valor"] = "sin caché"
        except _NoDisponible:
            MODO_RELECTURA["valor"] = "con caché"
            gen = None
        except StopIteration:
            return
        if gen is not None:
            yield primero
            yield from gen
            return
    with open(ruta, "rb", buffering=0) as f:
        if sin_cache:
            _sin_cache(f.fileno())
        while True:
            b = f.read(BLOQUE)
            if not b:
                break
            yield b


def _poner(q, item, parar):
    while True:
        try:
            q.put(item, timeout=0.2)
            return True
        except queue.Full:
            if parar.is_set():
                return False


def _sacar(q, parar):
    while True:
        try:
            return q.get(timeout=0.2)
        except queue.Empty:
            if parar.is_set():
                return None


class Avance:
    """Lleva la cuenta (copia + relectura de cada archivo) y escribe una línea cada pocos segundos."""

    def __init__(self, total_bytes, total_archivos, cada=5.0, silencioso=False, pasadas=2):
        self.total, self.n_total = total_bytes, total_archivos
        self.hechos_bytes, self.n_hechos = 0, 0
        self.leidos, self.releidos = 0, 0
        self.inicio = time.time()
        self.cada, self.silencioso, self.pasadas = cada, silencioso, pasadas
        self._ult, self._ult_cuenta, self._ult_t = 0.0, 0, time.time()
        self.archivo_actual, self.etapa, self.idx = "", "", 0
        self.actual_tam, self.actual_leido, self.actual_releido, self.n_copias = 0, 0, 0, 1
        self.lock = threading.Lock()

    def empezar_archivo(self, idx, nombre, tamano, n_copias):
        self.idx, self.archivo_actual = idx, nombre
        self.actual_tam, self.actual_leido, self.actual_releido = tamano, 0, 0
        self.n_copias = max(1, n_copias)

    def sumar(self, n):
        with self.lock:
            self.leidos += n
            self.actual_leido += n

    def sumar_relectura(self, n):
        with self.lock:
            self.releidos += n
            self.actual_releido += n

    def archivo_listo(self, n):
        self.hechos_bytes += n
        self.n_hechos += 1
        self.actual_tam = 0

    def hecho(self):
        if not self.actual_tam:
            return self.hechos_bytes
        f_copia = min(self.actual_leido / self.actual_tam, 1.0)
        if self.pasadas == 1:
            return self.hechos_bytes + f_copia * self.actual_tam
        f_verif = min(self.actual_releido / (self.actual_tam * self.n_copias), 1.0)
        return self.hechos_bytes + (0.5 * f_copia + 0.5 * f_verif) * self.actual_tam

    def tal_vez(self, forzar=False):
        if self.silencioso:
            return
        t = time.time()
        if not forzar and t - self._ult < self.cada:
            return
        cuenta = self.releidos if self.etapa == "verificando" else self.leidos
        vel = (cuenta - self._ult_cuenta) / max(t - self._ult_t, 1e-6) if self._ult else 0
        self._ult, self._ult_cuenta, self._ult_t = t, cuenta, t
        hecho = self.hecho()
        pct = 100 * hecho / self.total if self.total else 100
        trans = t - self.inicio
        falta = ""
        if hecho > 0 and self.total > hecho and (trans > 8 or pct > 2):
            falta = f" · faltan ~{duracion(trans / hecho * (self.total - hecho))}"
        vel_txt = f" · {vel / 1e6:.0f} MB/s" if vel > 0 else ""
        decir(f"[{self.idx}/{self.n_total}] {self.archivo_actual} · {self.etapa}{vel_txt} · "
              f"total {tam(hecho)} de {tam(self.total)} ({pct:.0f} %){falta}")


def huella_de(ruta, alg, sin_cache=True, contar=None):
    """Huella de un archivo leyendo y calculando a la vez (hilo lector + este hilo).
    contar: función que recibe los bytes leídos (para el avance)."""
    h = hashlib.new(alg)
    parar = threading.Event()
    q = queue.Queue(maxsize=4)
    error = []

    def lector():
        try:
            for b in _bloques(ruta, sin_cache):
                if parar.is_set() or _PARAR.is_set():
                    break
                if not _poner(q, b, parar):
                    return
        except BaseException as e:      # noqa: BLE001
            error.append(e)
        finally:
            _poner(q, None, parar)

    t = threading.Thread(target=lector, daemon=True)
    t.start()
    try:
        while True:
            b = _sacar(q, parar)
            if b is None:
                break
            h.update(b)
            if contar:
                contar(len(b))
    finally:
        parar.set()
        t.join()
    if error:
        raise error[0]
    if _PARAR.is_set():
        raise Corte()
    return h.hexdigest()


class Corte(Exception):
    pass


class ErrorOrigen(Exception):
    pass


class ErrorDestino(Exception):
    def __init__(self, destino, error):
        super().__init__(str(error))
        self.destino, self.error = destino, error


class ErrorVerificacion(Exception):
    def __init__(self, destino, rel):
        super().__init__(rel)
        self.destino, self.rel = destino, rel


def copiar_a_temporales(a: Arch, temporales, alg, avance, destinos):
    """Lee el archivo una vez: calcula su huella y lo escribe en todos los temporales a la vez."""
    parar = threading.Event()
    colas = [queue.Queue(maxsize=3) for _ in range(len(temporales) + 1)]
    errores = {}
    h = hashlib.new(alg)

    def calculador():
        try:
            while True:
                b = _sacar(colas[0], parar)
                if b is None:
                    return
                h.update(b)
        except BaseException as e:      # noqa: BLE001
            errores["huella"] = e
            parar.set()

    def escritor(i, ruta):
        try:
            with open(ruta, "xb", buffering=0) as f:      # "x": si existe, falla. Nunca pisa.
                _sin_cache(f.fileno())
                while True:
                    b = _sacar(colas[i + 1], parar)
                    if b is None:
                        break
                    mv = memoryview(b)
                    while mv:
                        n = f.write(mv)
                        mv = mv[n:]
                if not parar.is_set():
                    _forzar_a_disco(f.fileno())
        except BaseException as e:      # noqa: BLE001
            errores[i] = e
            parar.set()

    def lector():
        try:
            for b in _bloques(a.ruta, sin_cache=True):
                if parar.is_set() or _PARAR.is_set():
                    break
                for q in colas:
                    if not _poner(q, b, parar):
                        break
                avance.sumar(len(b))
        except BaseException as e:      # noqa: BLE001
            errores["origen"] = e
            parar.set()
        finally:
            if _PARAR.is_set():
                parar.set()
            for q in colas:
                _poner(q, None, parar)

    hilos = [threading.Thread(target=calculador, daemon=True)]
    hilos += [threading.Thread(target=escritor, args=(i, r), daemon=True) for i, r in enumerate(temporales)]
    hilos.append(threading.Thread(target=lector, daemon=True))
    for t in hilos:
        t.start()
    while any(t.is_alive() for t in hilos):
        for t in hilos:
            t.join(0.25)
        avance.tal_vez()
        if _PARAR.is_set():
            parar.set()
    if errores or _PARAR.is_set():
        for r in temporales:
            try:
                os.unlink(r)
            except OSError:
                pass
        if "origen" in errores:
            raise ErrorOrigen(errores["origen"])
        for i in range(len(temporales)):
            if i in errores:
                raise ErrorDestino(destinos[i], errores[i])
        if "huella" in errores:
            raise errores["huella"]
        raise Corte()
    return h.hexdigest()


# ───────────────────────────── estado de cada copia (para seguir si se corta) ─────────────────────────────

class Estado:
    def __init__(self, carpeta: Path):
        self.carpeta = carpeta
        self.meta = carpeta / CARPETA_META
        self.ruta = self.meta / "estado.jsonl"
        self.inicio = None
        self.archivos = {}
        self.conflictos = {}
        self._f = None
        self._ult_sync = 0.0

    def cargar(self):
        if not self.ruta.exists():
            return False
        for linea in self.ruta.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(linea)
            except ValueError:
                continue                     # una línea a medias de un corte
            t = r.get("tipo")
            if t == "inicio" and self.inicio is None:
                self.inicio = r
            elif t == "archivo":
                self.archivos[r["ruta"]] = r
                self.conflictos.pop(r["ruta"], None)
            elif t == "conflicto":
                self.conflictos[r["ruta"]] = r
        return True

    def abrir(self):
        self.meta.mkdir(parents=True, exist_ok=True)
        self._f = open(self.ruta, "a", encoding="utf-8")

    def anotar(self, rec, forzar=False):
        self._f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._f.flush()
        if rec.get("tipo") == "archivo":
            self.archivos[rec["ruta"]] = rec
            self.conflictos.pop(rec["ruta"], None)
        elif rec.get("tipo") == "conflicto":
            self.conflictos[rec["ruta"]] = rec
        t = time.time()
        if forzar or t - self._ult_sync > 2:
            os.fsync(self._f.fileno())
            self._ult_sync = t

    def cerrar(self):
        if self._f:
            self._f.flush()
            _forzar_a_disco(self._f.fileno(), completo=True)   # todo lo escrito en ese disco queda grabado
            self._f.close()
            self._f = None

    def verificado(self, a: Arch):
        r = self.archivos.get(a.rel)
        if r is None or r.get("tam") != a.tam or abs(r.get("mtime", 0) - a.mtime) > 2:
            return False
        try:                                   # si alguien lo borró del disco, se vuelve a copiar
            return os.path.getsize(self.carpeta / a.rel) == a.tam
        except OSError:
            return False

    def continuable_para(self, archivos, firma, uuid):
        """¿Esta carpeta es de la misma tarjeta (aunque ahora tenga clips nuevos)?"""
        actual = {a.rel: a for a in archivos}
        if not self.archivos:
            ini = self.inicio or {}
            return bool(ini.get("firma") == firma or (uuid and ini.get("origen_uuid") == uuid))
        for rel, r in self.archivos.items():
            a = actual.get(rel)
            if a is None or a.tam != r.get("tam") or abs(a.mtime - r.get("mtime", 0)) > 2:
                return False
        return True


def _limpiar_parciales(carpeta: Path):
    """Borra solo los temporales nuestros que quedaron de un corte (terminan en .parcial-descarga)."""
    n = 0
    for raiz, _dirs, files in os.walk(carpeta):
        for f in files:
            if f.endswith(SUFIJO_PARCIAL):
                try:
                    os.unlink(os.path.join(raiz, f))
                    n += 1
                except OSError:
                    pass
    return n


# ───────────────────────────── plan ─────────────────────────────

class Destino:
    def __init__(self, raiz):
        self.raiz = Path(os.path.abspath(os.path.expanduser(raiz)))
        self.carpeta = None
        self.estado = None
        self.modo = "nueva"
        self.info = {}
        self.necesita = 0
        self.ok = True
        self.verificados_ahora = 0
        self.adoptados = 0

    @property
    def nombre(self):
        return self.info.get("disco") or self.raiz.name


def disco_conectado(ruta: str):
    """En Mac, escribir en /Volumes/X cuando X no está conectado crea una carpeta en el disco interno.
    Esto lo evita: devuelve el nombre del disco que falta, o None si está conectado."""
    ruta = os.path.abspath(ruta)
    if ES_MAC and ruta.startswith("/Volumes/"):
        vol = "/".join(ruta.split("/")[:3])
        if not os.path.ismount(vol):
            return os.path.basename(vol)
    if ES_WIN:
        unidad = os.path.splitdrive(ruta)[0]
        if unidad and not os.path.isdir(unidad + "\\"):
            return unidad
    return None


class Plan:
    pass


def _render_plantilla(plantilla, proyecto, fecha, tarjeta, dia):
    vals = {"proyecto": limpiar_nombre(proyecto or ""), "fecha": fecha, "tarjeta": limpiar_nombre(tarjeta),
            "dia": limpiar_nombre(dia or "")}
    try:
        texto = plantilla.format(**vals)
    except (KeyError, IndexError, ValueError) as e:
        raise SystemExit(f"❌ La plantilla de carpetas tiene un dato que no existe ({e}). "
                         f"Se puede usar: {{proyecto}}, {{fecha}}, {{dia}}, {{tarjeta}}.")
    partes = [p for p in re.split(r"[\\/]+", texto) if p.strip() and p not in (".", "..")]
    return Path(*partes)


def _leer_estado(carpeta: Path):
    e = Estado(carpeta)
    return e if e.cargar() else None


def _nombre_auto(destinos, base_padre: Path, corto, archivos, firma, uuid):
    """Para tarjetas sin nombre propio: reusa la carpeta de esta misma tarjeta o da el siguiente número."""
    usados = set()
    for d in destinos:
        padre = d.raiz / base_padre
        try:
            hermanos = [e for e in os.scandir(padre) if e.is_dir()]
        except OSError:
            continue
        for e in hermanos:
            m = re.match(rf"^{re.escape(corto)}_(\d+)$", e.name)
            if m:
                usados.add(int(m.group(1)))
                est = _leer_estado(Path(e.path))
                if est and est.continuable_para(archivos, firma, uuid):
                    return e.name
    n = 1
    while n in usados:
        n += 1
    return f"{corto}_{n:02d}"


def elegir_carpeta(destinos, rel_base: Path, archivos, firma, uuid):
    """Mismo nombre de carpeta en todos los discos; si ya hay otra tarjeta con ese nombre, _2, _3…"""
    k = 1
    while k < 1000:
        rel = rel_base if k == 1 else rel_base.with_name(f"{rel_base.name}_{k}")
        modos, sirve = {}, True
        for d in destinos:
            c = d.raiz / rel
            if not c.exists():
                modos[d] = "nueva"
                continue
            est = _leer_estado(c)
            if est is None:
                visibles = [x for x in os.listdir(c) if not x.startswith(".")]
                if not visibles:
                    modos[d] = "nueva"
                    continue
                sirve = False
                break
            if est.continuable_para(archivos, firma, uuid):
                modos[d] = "continuar"
                continue
            sirve = False
            break
        if sirve:
            return rel, modos
        k += 1
    raise SystemExit("❌ No encontré un nombre libre para la carpeta de la tarjeta.")


def armar_plan(args, cfg):
    origen = os.path.abspath(os.path.expanduser(args.origen))
    if not os.path.isdir(origen):
        raise SystemExit(f"❌ No encuentro la tarjeta o carpeta de origen: {origen}")
    destinos_txt = args.destino or cfg.get("destinos") or []
    if not destinos_txt:
        raise SystemExit("❌ Faltan los discos de destino (--destino, uno por disco).")
    plantilla = args.plantilla or cfg.get("plantilla") or PLANTILLA_DEFECTO
    if "{tarjeta}" not in plantilla:
        raise SystemExit("❌ La plantilla tiene que llevar {tarjeta}: así dos tarjetas nunca se mezclan "
                         "ni se pisan archivos con el mismo nombre.")
    proyecto = args.proyecto if args.proyecto is not None else cfg.get("proyecto")
    if "{proyecto}" in plantilla and not proyecto:
        raise SystemExit("❌ Falta el nombre del proyecto (--proyecto).")
    alg = (args.algoritmo or cfg.get("algoritmo") or "md5").lower()
    if alg not in ALGORITMOS:
        raise SystemExit(f"❌ Huella no soportada: {alg}. Usa md5 o sha1.")

    p = Plan()
    p.origen, p.alg, p.plantilla, p.proyecto = origen, alg, plantilla, proyecto or ""
    p.avisos, p.errores = [], []
    p.info_origen = info_volumen(origen)
    p.camara = tipo_de_camara(origen)
    p.archivos, p.ignorados = listar_origen(origen)
    if not p.archivos:
        raise SystemExit("❌ La tarjeta no tiene archivos para copiar.")
    p.firma = firma_de(p.archivos)
    p.total = sum(a.tam for a in p.archivos)
    p.fecha = args.fecha or fecha_de_grabacion(p.archivos)
    p.dia = args.dia or cfg.get("dia") or ""
    p.destinos = [Destino(d) for d in destinos_txt]
    if len(p.destinos) < 2:
        p.avisos.append("Solo hay UN destino: si ese disco falla, el material existe en un solo lugar. "
                        "Lo recomendado son 2 discos distintos.")

    # que nada se copie dentro de sí mismo, ni a un disco desconectado
    falta_origen = disco_conectado(origen)
    if falta_origen:
        raise SystemExit(f"❌ La tarjeta {falta_origen} no está conectada.")
    permitir = args.permitir_mismo_disco or bool(os.environ.get("DESCARGA_PERMITIR_MISMO_DISCO"))
    for d in p.destinos:
        r = str(d.raiz)
        if r == origen or r.startswith(origen + os.sep) or origen.startswith(r + os.sep):
            p.errores.append(f"El destino {d.raiz} está dentro de la tarjeta (o al revés). Elige otro disco.")
        falta = disco_conectado(r)
        if falta:
            p.errores.append(f"El disco {falta} no está conectado (destino {d.raiz}). Conéctalo y vuelve a "
                             "intentar: si no, la copia caería en el disco de la computadora.")
            d.info = {"disco": falta}
            continue
        d.info = info_volumen(r)
        if d.info.get("montaje") in ("/", "\\") or d.info.get("interno"):
            p.avisos.append(f"El destino {d.raiz} está en el disco de la computadora, no en un disco externo.")
    if len({str(d.raiz) for d in p.destinos}) != len(p.destinos):
        p.errores.append("Pusiste el mismo destino dos veces.")
    if p.errores:
        return p
    fisicos = [d.info.get("disco_fisico") for d in p.destinos]
    if len(set(fisicos)) < len(fisicos) and not permitir:
        p.errores.append("Dos copias quedarían en el MISMO disco físico: si ese disco falla, se pierden las dos. "
                         "Usa discos distintos (o confirma con --permitir-mismo-disco).")
    if p.info_origen.get("disco_fisico") in fisicos and not permitir:
        p.errores.append("Un destino está en el mismo disco que el origen. Usa otro disco "
                         "(o confirma con --permitir-mismo-disco).")
    if p.errores:
        return p

    # nombre de la tarjeta y carpeta
    etiqueta = args.tarjeta or p.info_origen.get("nombre") or os.path.basename(origen)
    corto = (p.camara or {}).get("corto", "TARJETA")
    base_padre = _render_plantilla(plantilla, p.proyecto, p.fecha, "X", p.dia).parent
    if not args.tarjeta and (not etiqueta or etiqueta.strip().lower() in NOMBRES_GENERICOS):
        etiqueta = _nombre_auto(p.destinos, base_padre, corto, p.archivos, p.firma, p.info_origen.get("uuid"))
    p.tarjeta = limpiar_nombre(etiqueta) or "TARJETA"
    rel_base = _render_plantilla(plantilla, p.proyecto, p.fecha, p.tarjeta, p.dia)
    p.rel, modos = elegir_carpeta(p.destinos, rel_base, p.archivos, p.firma, p.info_origen.get("uuid"))
    if p.rel != rel_base:
        p.avisos.append(f"Ya había otra tarjeta en «{rel_base.name}»: esta va a «{p.rel.name}» (no se pisa nada).")
    p.tarjeta_carpeta = p.rel.name

    # espacio y estado de cada destino
    for d in p.destinos:
        d.carpeta = d.raiz / p.rel
        d.modo = modos[d]
        d.estado = _leer_estado(d.carpeta) or Estado(d.carpeta)
        faltan = [a for a in p.archivos if not d.estado.verificado(a)]
        cluster = tamano_cluster(d.info["montaje"])
        d.necesita = sum(a.tam for a in faltan) + len(faltan) * cluster + 64 * 1024 * 1024
        d.faltan = len(faltan)
        libre = d.info.get("libre")
        if faltan and libre is not None and libre < d.necesita and not os.environ.get(
                "DESCARGA_PRUEBA_SALTAR_ESPACIO"):
            p.errores.append(f"No entra en {d.nombre}: necesita {tam(d.necesita)} y tiene {tam(libre)} libres "
                             f"(faltan {tam(d.necesita - libre)}).")
    return p


def mostrar_plan(p, json_out=False):
    if json_out:
        decir(json.dumps({
            "origen": p.origen, "tarjeta": getattr(p, "tarjeta_carpeta", None), "camara": p.camara,
            "archivos": len(p.archivos), "bytes": p.total, "clips": sum(1 for a in p.archivos if a.tipo == "video"),
            "fecha": p.fecha, "algoritmo": p.alg,
            "destinos": [{"raiz": str(d.raiz), "carpeta": str(d.carpeta) if d.carpeta else None,
                          "modo": d.modo, "faltan": getattr(d, "faltan", None), "necesita": d.necesita,
                          "libre": d.info.get("libre"), "disco": d.nombre} for d in p.destinos],
            "avisos": p.avisos, "errores": p.errores}, ensure_ascii=False, indent=2))
        return
    clips = sum(1 for a in p.archivos if a.tipo == "video")
    fotos = sum(1 for a in p.archivos if a.tipo == "foto")
    cam = p.camara["nombre"] if p.camara else "sin estructura de cámara conocida"
    decir("📋 Plan de copia")
    decir(f"Origen: {p.info_origen.get('nombre') or p.origen} ({p.origen}) · {cam}")
    detalle = f"{len(p.archivos)} archivos · {tam(p.total)}"
    if clips:
        detalle += f" · {clips} clips"
    if fotos:
        detalle += f" · {fotos} fotos"
    decir(f"        {detalle}" + (f" · {p.ignorados} archivos del sistema se ignoran" if p.ignorados else ""))
    try:
        d_ = dt.datetime.strptime(p.fecha, "%Y-%m-%d")
        decir(f"Grabado el {fecha_legible(d_, hora=False)} (según la fecha de los archivos).")
    except ValueError:
        pass
    if p.errores:
        for e in p.errores:
            decir(f"❌ {e}")
        return
    decir("Destinos (cada uno es una copia completa):")
    for i, d in enumerate(p.destinos, 1):
        libre = d.info.get("libre")
        estado = ("nueva" if d.modo == "nueva" else
                  f"sigue la copia anterior: faltan {d.faltan} de {len(p.archivos)}" if d.faltan else
                  "ya estaba todo copiado y verificado")
        decir(f"  {i}. {d.nombre} → {d.carpeta}  ({estado}; libres {tam(libre)})")
    falta_bytes = max(d.necesita for d in p.destinos) if p.destinos else 0
    if falta_bytes > 64 * 1024 * 1024:
        decir(f"Tiempo aproximado: ~{duracion(2 * (falta_bytes / 150e6))} con un lector USB común "
              f"(copia + relectura de verificación).")
    decir(f"Huella: {p.alg.upper()} · la tarjeta solo se lee, nunca se escribe ni se formatea.")
    for a in p.avisos:
        decir(f"⚠️  {a}")


# ───────────────────────────── metadatos (ffprobe) ─────────────────────────────

def _ffprobe():
    for c in (shutil.which("ffprobe"), "/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe",
              os.path.expanduser("~/.claude/bin/ffprobe")):
        if c and os.path.exists(c):
            return c
    return None


def _fps(txt):
    try:
        n, d = txt.split("/")
        v = float(n) / float(d)
        return round(v, 3) if v else None
    except Exception:
        return None


def metadatos_de(ruta, ffprobe):
    try:
        r = subprocess.run([ffprobe, "-v", "error", "-print_format", "json", "-show_entries",
                            "format=duration:stream=codec_type,codec_name,profile,width,height,avg_frame_rate,"
                            "r_frame_rate,sample_rate,channels", ruta],
                           capture_output=True, text=True, timeout=30)
        d = json.loads(r.stdout or "{}")
    except Exception:
        return {}
    m = {}
    try:
        m["duracion"] = float(d.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        pass
    for s in d.get("streams", []):
        if s.get("codec_type") == "video" and "video_codec" not in m:
            m["video_codec"] = (s.get("codec_name") or "") + (f" ({s['profile']})" if s.get("profile") else "")
            if s.get("width"):
                m["resolucion"] = f"{s.get('width')}×{s.get('height')}"
            m["fps"] = _fps(s.get("avg_frame_rate") or "") or _fps(s.get("r_frame_rate") or "")
        elif s.get("codec_type") == "audio" and "audio_codec" not in m:
            m["audio_codec"] = s.get("codec_name")
            m["audio"] = f"{s.get('codec_name')} {s.get('channels', '')}c {s.get('sample_rate', '')} Hz".strip()
    return m


def leer_metadatos(carpeta: Path, archivos_rel, base_cache=None):
    """Duración y códec de cada clip (si hay ffprobe). Guarda un caché en _DESCARGA/metadatos.json."""
    ffprobe = _ffprobe()
    cache_p = carpeta / CARPETA_META / "metadatos.json"
    try:
        cache = json.loads(cache_p.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    if base_cache:
        cache.update(base_cache)
    if not ffprobe:
        return cache, False
    pend = [r for r in archivos_rel
            if r not in cache and os.path.splitext(r)[1].lower() in (EXT_VIDEO | EXT_AUDIO)]
    if pend:
        with ThreadPoolExecutor(max_workers=4) as ex:
            for rel, m in zip(pend, ex.map(lambda r: metadatos_de(str(carpeta / r), ffprobe), pend)):
                cache[rel] = m
        try:
            guardar_json(cache_p, cache)
        except OSError:
            pass
    return cache, True


# ───────────────────────────── manifiesto MHL ─────────────────────────────

def escribir_mhl(carpeta: Path, nombre_tarjeta, registros, inicio_ts, fin_ts):
    """MHL 1.1 (hashlist), el formato que leen ShotPut, Silverstack, Hedge/OffShoot y DaVinci."""
    raiz = ET.Element("hashlist", version="1.1")
    ci = ET.SubElement(raiz, "creatorinfo")
    try:
        ET.SubElement(ci, "username").text = getpass.getuser()
    except Exception:
        pass
    ET.SubElement(ci, "hostname").text = socket.gethostname()
    ET.SubElement(ci, "tool").text = f"{HERRAMIENTA} {VERSION}"
    ET.SubElement(ci, "startdate").text = iso_utc(inicio_ts)
    ET.SubElement(ci, "finishdate").text = iso_utc(fin_ts)
    for r in sorted(registros, key=lambda x: clave_natural(x["ruta"])):
        h = ET.SubElement(raiz, "hash")
        ET.SubElement(h, "file").text = r["ruta"]
        ET.SubElement(h, "size").text = str(r["tam"])
        ET.SubElement(h, "lastmodificationdate").text = iso_utc(r["mtime"])
        ET.SubElement(h, r.get("alg", "md5")).text = r["huella"]
        ET.SubElement(h, "hashdate").text = r.get("fecha_utc") or iso_utc(fin_ts)
    try:
        ET.indent(raiz)                     # Python 3.9+
    except AttributeError:
        pass
    destino = carpeta / f"{limpiar_nombre(nombre_tarjeta)}_{marca_tiempo()}.mhl"
    datos = ET.tostring(raiz, encoding="utf-8", xml_declaration=True)
    tmp = destino.with_name(destino.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(datos)
        f.flush()
        _forzar_a_disco(f.fileno(), completo=True)
    os.replace(tmp, destino)
    return destino


def _c4(digest: bytes) -> str:
    alfabeto = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n, s = int.from_bytes(digest, "big"), ""
    while n:
        n, r = divmod(n, 58)
        s = alfabeto[r] + s
    return "c4" + s.rjust(88, "1")


def _tag(e):
    return e.tag.split("}", 1)[-1].lower()


def leer_manifiesto(carpeta: Path):
    """Busca el manifiesto más nuevo de la carpeta: MHL 1.1 en la raíz o ASC MHL (carpeta ascmhl/).
    Devuelve (descripcion, {ruta_rel: {"tam": n, "huellas": {alg: valor}}}) o (None, {})."""
    carpeta = Path(carpeta)
    entradas = {}
    asc = carpeta / "ascmhl"
    if asc.is_dir():
        gens = sorted(asc.glob("*.mhl"))
        for g in gens:
            try:
                arbol = ET.parse(g).getroot()
            except ET.ParseError:
                continue
            for h in arbol.iter():
                if _tag(h) != "hash":
                    continue
                ruta, tam_ = None, None
                huellas = {}
                for c in h:
                    t = _tag(c)
                    if t == "path":
                        ruta = (c.text or "").strip()
                        tam_ = c.get("size")
                    elif t in ("md5", "sha1", "c4", "xxh64", "xxh3", "xxh128"):
                        huellas[t] = (c.text or "").strip()
                if ruta:
                    e = entradas.setdefault(ruta, {"tam": None, "huellas": {}})
                    if tam_ is not None:
                        e["tam"] = int(tam_)
                    e["huellas"].update(huellas)
        if entradas:
            return f"ASC MHL ({len(gens)} generaciones, ascmhl/)", entradas
    mhls = sorted(carpeta.glob("*.mhl"), key=lambda p: p.stat().st_mtime)
    if not mhls:
        return None, {}
    ultimo = mhls[-1]
    arbol = ET.parse(ultimo).getroot()
    for h in arbol.iter():
        if _tag(h) != "hash":
            continue
        ruta, tam_, huellas = None, None, {}
        for c in h:
            t = _tag(c)
            if t == "file":
                ruta = (c.text or "").strip()
            elif t == "size":
                tam_ = int((c.text or "0").strip() or 0)
            elif t in ("md5", "sha1", "xxhash64be"):
                huellas["xxh64" if t == "xxhash64be" else t] = (c.text or "").strip().lower()
        if ruta:
            entradas[ruta.replace("\\", "/")] = {"tam": tam_, "huellas": huellas}
    return f"MHL 1.1 ({ultimo.name})", entradas


def _calcular(ruta, alg, sin_cache=True):
    if alg in ("md5", "sha1"):
        return huella_de(ruta, alg, sin_cache)
    if alg == "c4":
        return _c4(bytes.fromhex(huella_de(ruta, "sha512", sin_cache)))
    try:
        import xxhash                       # opcional: no viene con Python
    except ImportError:
        raise _NoDisponible(alg)
    f = {"xxh64": xxhash.xxh64, "xxh3": xxhash.xxh3_64, "xxh128": xxhash.xxh3_128}[alg]()
    for b in _bloques(ruta, sin_cache):
        f.update(b)
    return f.hexdigest()


# ───────────────────────────── informe ─────────────────────────────

def _fila_csv(w, fila):
    w.writerow(["" if v is None else v for v in fila])


def escribir_informe(p_like, destinos, registros_por_rel, metas, inicio, fin, resultado, carpeta_salida: Path):
    """Informe HTML (para ver o imprimir a PDF) y CSV (para Excel) dentro de _DESCARGA/."""
    meta_dir = carpeta_salida / CARPETA_META
    meta_dir.mkdir(parents=True, exist_ok=True)
    ts = marca_tiempo()
    filas = []
    total_dur = 0.0
    for rel in sorted(registros_por_rel, key=clave_natural):
        r = registros_por_rel[rel]
        m = metas.get(rel, {}) or {}
        if m.get("duracion") and os.path.splitext(rel)[1].lower() in EXT_VIDEO:
            total_dur += m["duracion"]
        filas.append((rel, r, m))
    clips = [f for f in filas if os.path.splitext(f[0])[1].lower() in EXT_VIDEO]

    csv_p = meta_dir / f"informe_{ts}.csv"
    with open(csv_p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["archivo", "carpeta", "tipo", "bytes", "tamaño", "duración", "códec de video", "resolución",
                    "fps", "audio", f"huella ({p_like['alg']})", "fecha del archivo"] +
                   [f"copia {i + 1}: {d['nombre']}" for i, d in enumerate(destinos)])
        for rel, r, m in filas:
            carpeta, nombre = (rel.rsplit("/", 1) if "/" in rel else ("", rel))
            ext = os.path.splitext(rel)[1].lower()
            tipo = "video" if ext in EXT_VIDEO else "audio" if ext in EXT_AUDIO else "foto" if ext in EXT_FOTO \
                else "otro"
            _fila_csv(w, [nombre, carpeta, tipo, r["tam"], tam(r["tam"]), codigo_tiempo(m.get("duracion")),
                          m.get("video_codec"), m.get("resolucion"),
                          str(m.get("fps") or "").replace(".", ","), m.get("audio"), r["huella"],
                          dt.datetime.fromtimestamp(r["mtime"]).strftime("%Y-%m-%d %H:%M:%S")] +
                      ["verificada" if rel in d["verificados"] else "FALTA" for d in destinos])

    ok = resultado["ok"]
    estado_txt = ("✅ Copias verificadas: ya se puede formatear la tarjeta EN LA CÁMARA." if ok else
                  "❌ NO formatees la tarjeta: " + resultado.get("motivo", "la copia no terminó bien."))
    e = html.escape
    filas_dest = "".join(
        f"<tr><td>{i + 1}</td><td>{e(d['nombre'])}</td><td class=mono>{e(d['carpeta'])}</td>"
        f"<td>{len(d['verificados'])} de {len(registros_por_rel)}</td>"
        f"<td>{'✅ verificada' if d['ok'] else '❌ incompleta'}</td></tr>" for i, d in enumerate(destinos))
    filas_clips = "".join(
        f"<tr><td class=mono>{e(rel.rsplit('/', 1)[-1])}</td><td>{e(codigo_tiempo(m.get('duracion')))}</td>"
        f"<td>{e(tam(r['tam']))}</td><td>{e(m.get('video_codec') or '—')}</td><td>{e(m.get('resolucion') or '—')}</td>"
        f"<td>{e(str(m.get('fps') or '—').replace('.', ','))}</td><td>{e(m.get('audio') or '—')}</td>"
        f"<td class='mono chico'>{e(r['huella'])}</td></tr>" for rel, r, m in filas
        if os.path.splitext(rel)[1].lower() in (EXT_VIDEO | EXT_AUDIO))
    otros = len(filas) - len([f for f in filas if os.path.splitext(f[0])[1].lower() in (EXT_VIDEO | EXT_AUDIO)])
    velocidad = resultado.get("bytes_leidos", 0) / max((fin - inicio).total_seconds(), 1)
    html_txt = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Informe de descarga · {e(p_like['tarjeta'])}</title>
<style>
body{{font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;color:#16181b;margin:32px;max-width:1100px}}
h1{{font-size:26px;margin:0 0 4px}} .sub{{color:#5b5f66;margin:0 0 18px}}
.estado{{padding:14px 18px;border-radius:10px;font-size:18px;font-weight:600;margin:0 0 20px}}
.ok{{background:#e3f6e8;color:#11612b}} .mal{{background:#fde4e1;color:#9b1c10}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:0 0 22px}}
.caja{{border:1px solid #e1e3e6;border-radius:10px;padding:10px 14px}} .caja b{{display:block;font-size:22px}}
.caja span{{color:#5b5f66;font-size:13px}}
table{{border-collapse:collapse;width:100%;margin:0 0 22px;font-size:13px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #eceef0;vertical-align:top}}
th{{background:#f5f6f7;font-weight:600}} .mono{{font-family:ui-monospace,Menlo,Consolas,monospace}}
.chico{{font-size:11px;color:#5b5f66}} h2{{font-size:17px;margin:26px 0 8px}}
.nota{{color:#5b5f66;font-size:12px}} @media print{{body{{margin:12mm}} .caja,.estado{{break-inside:avoid}}}}
</style></head><body>
<h1>Informe de descarga · {e(p_like['tarjeta'])}</h1>
<p class=sub>{e(p_like.get('proyecto') or '')} · grabado el {e(p_like.get('fecha_txt') or p_like.get('fecha') or '')} ·
copiado el {e(fecha_legible(fin))} · {e(p_like.get('camara_txt') or '')}</p>
<div class="estado {'ok' if ok else 'mal'}">{e(estado_txt)}</div>
<div class=grid>
<div class=caja><b>{len(filas)}</b><span>archivos</span></div>
<div class=caja><b>{e(tam(sum(r['tam'] for r in registros_por_rel.values())))}</b><span>en total</span></div>
<div class=caja><b>{len(clips)}</b><span>clips de video</span></div>
<div class=caja><b>{e(duracion(total_dur) if total_dur else '—')}</b><span>de material</span></div>
</div>
<h2>Copias</h2>
<table><tr><th>#</th><th>Disco</th><th>Carpeta</th><th>Archivos verificados</th><th>Estado</th></tr>{filas_dest}</table>
<h2>Clips y audio</h2>
<table><tr><th>Archivo</th><th>Duración</th><th>Tamaño</th><th>Video</th><th>Resolución</th><th>fps</th><th>Audio</th>
<th>Huella {e(p_like['alg'].upper())}</th></tr>{filas_clips or '<tr><td colspan=8>No hay clips de video ni audio.</td></tr>'}</table>
<p class=nota>Además: {otros} archivos de la cámara (miniaturas, XML, fotos y otros) copiados y verificados igual.
{('Duración y códec: ' + ('leídos con ffprobe.' if p_like.get('ffprobe') else 'no disponibles (falta ffprobe).'))}
Tiempo: {e(duracion((fin - inicio).total_seconds()))} · velocidad media de lectura {e(tam(velocidad))}/s ·
relectura {e(MODO_RELECTURA['valor'])} · inicio {e(fecha_legible(inicio))}.</p>
<p class=nota>Cómo se verificó: cada archivo se leyó una vez de la tarjeta (huella {e(p_like['alg'].upper())}),
se escribió en todos los discos a la vez y después cada copia se volvió a leer desde su disco y se comparó.
La lista de huellas queda en el manifiesto .mhl de cada copia; con la skill verificar-material se puede volver
a comprobar en cualquier momento. Para guardarlo como PDF: Archivo › Imprimir › Guardar como PDF.</p>
<p class=nota>{e(HERRAMIENTA)} {VERSION}</p>
</body></html>"""
    html_p = meta_dir / f"informe_{ts}.html"
    html_p.write_text(html_txt, encoding="utf-8")
    return html_p, csv_p


# ───────────────────────────── copiar ─────────────────────────────

def _registro(a: Arch, huella, alg, adoptado=False):
    return {"tipo": "archivo", "ruta": a.rel, "tam": a.tam, "mtime": a.mtime, "huella": huella, "alg": alg,
            "fecha_utc": iso_utc(), **({"ya_estaba": True} if adoptado else {})}


def _instalar_senales():
    def manejar(_s, _f):
        _PARAR.set()
    for s in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None),
              getattr(signal, "SIGHUP", None)):
        if s is not None:
            try:
                signal.signal(s, manejar)
            except (ValueError, OSError):
                pass


def _historial_anotar(rec):
    try:
        d = dir_sistema()
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "historial.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def historial():
    p = dir_sistema() / "historial.jsonl"
    try:
        lineas = p.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    out = []
    for l in lineas:
        try:
            out.append(json.loads(l))
        except ValueError:
            pass
    return out


def cmd_copiar(args):
    cfg = leer_config()
    p = armar_plan(args, cfg)
    mostrar_plan(p)
    if p.errores:
        if args.json_final:
            decir("RESULTADO=" + json.dumps({"ok": False, "motivo": " ".join(p.errores), "codigo": EXIT_NO_EMPIEZA},
                                            ensure_ascii=False))
        return EXIT_NO_EMPIEZA
    _instalar_senales()
    _mantener_despierta()
    inicio = ahora()
    t0 = time.time()
    pendientes = [a for a in p.archivos if any(not d.estado.verificado(a) for d in p.destinos)]
    for d in p.destinos:
        try:
            d.carpeta.mkdir(parents=True, exist_ok=True)
            borrados = _limpiar_parciales(d.carpeta)
            if borrados:
                decir(f"🧹 {d.nombre}: borré {borrados} temporales de un corte anterior (eran copias a medias).")
            d.estado.abrir()
            if pendientes:
                d.estado.anotar({"tipo": "inicio", "fecha_utc": iso_utc(), "tarjeta": p.tarjeta_carpeta,
                                 "firma": p.firma, "origen": p.origen,
                                 "origen_nombre": p.info_origen.get("nombre"),
                                 "origen_uuid": p.info_origen.get("uuid"), "algoritmo": p.alg, "version": VERSION,
                                 "destinos": [str(x.carpeta) for x in p.destinos]}, forzar=True)
        except OSError as e:
            decir(f"❌ No se puede escribir en {d.nombre} ({e}). ¿Está protegido contra escritura o lleno?")
            for x in p.destinos:
                x.estado.cerrar()
            return EXIT_DESTINO
    total_pend = sum(a.tam for a in pendientes)
    av = Avance(total_pend, len(pendientes), cada=args.cada, silencioso=args.silencioso)
    if not pendientes:
        decir("✔️  Todo ya estaba copiado y verificado en los destinos.")
    decir(f"▶️  Copiando {len(pendientes)} archivos ({tam(total_pend)})…")
    motivo, codigo = None, EXIT_OK
    conflictos = []
    try:
        for i, a in enumerate(pendientes, 1):
            if _PARAR.is_set():
                raise Corte()
            faltan = [d for d in p.destinos if not d.estado.verificado(a)]
            existentes = [d for d in faltan if (d.carpeta / a.rel).exists()]
            a_copiar = [d for d in faltan if d not in existentes]
            av.empezar_archivo(i, a.rel.rsplit("/", 1)[-1], a.tam, len(a_copiar))
            temporales = []
            for d in a_copiar:
                final = d.carpeta / a.rel
                tmp = final.with_name("." + final.name + SUFIJO_PARCIAL)
                try:
                    final.parent.mkdir(parents=True, exist_ok=True)
                    if tmp.exists():
                        tmp.unlink()
                except OSError as e:
                    raise ErrorDestino(d, e)
                temporales.append(tmp)
            av.etapa = "copiando"
            if a_copiar:
                h_origen = copiar_a_temporales(a, temporales, p.alg, av, a_copiar)
            else:
                av.etapa = "leyendo"
                try:
                    h_origen = huella_de(a.ruta, p.alg, True, av.sumar)
                except OSError as e:
                    raise ErrorOrigen(e)
            # archivos que ya estaban en el destino sin registro: se adoptan si son iguales; si no, no se tocan
            for d in existentes:
                final = d.carpeta / a.rel
                try:
                    h = huella_de(str(final), p.alg, True)
                except OSError as e:
                    raise ErrorDestino(d, e)
                try:
                    if h == h_origen:
                        d.estado.anotar(_registro(a, h, p.alg, adoptado=True))
                        d.adoptados += 1
                    elif args.apartar_conflictos:
                        # con el OK de la persona: el distinto se aparta (no se borra) y se copia el de la tarjeta
                        aparte = final.with_name(f"{final.name}.DISTINTO_{marca_tiempo()}")
                        os.rename(final, aparte)
                        decir(f"↪️  {d.nombre}: {a.rel} era distinto; quedó aparte como {aparte.name}")
                        tmp = final.with_name("." + final.name + SUFIJO_PARCIAL)
                        if copiar_a_temporales(a, [tmp], p.alg, av, [d]) != h_origen or \
                                huella_de(str(tmp), p.alg, True) != h_origen:
                            try:
                                os.unlink(tmp)
                            except OSError:
                                pass
                            raise ErrorVerificacion(d, a.rel)
                        os.utime(tmp, (a.atime, a.mtime))
                        os.rename(tmp, final)
                        d.estado.anotar(_registro(a, h_origen, p.alg))
                    else:
                        d.estado.anotar({"tipo": "conflicto", "ruta": a.rel, "fecha_utc": iso_utc(),
                                         "motivo": "ya existe en el destino y es distinto: no se pisa"})
                        conflictos.append((d, a.rel))
                        d.ok = False
                except OSError as e:
                    raise ErrorDestino(d, e)
            # verificar cada copia releyéndola desde su disco (en paralelo, un hilo por disco)
            av.etapa = "verificando"

            def verificar_uno(par):
                d, tmp = par
                try:
                    return huella_de(str(tmp), p.alg, True, av.sumar_relectura)
                except OSError as e:
                    return e
            with ThreadPoolExecutor(max_workers=max(1, len(a_copiar))) as ex:
                futuros = [ex.submit(verificar_uno, par) for par in zip(a_copiar, temporales)]
                while not cf_wait(futuros, timeout=0.5).not_done == set():
                    av.tal_vez()
                    if _PARAR.is_set():
                        break
                huellas = [f.result() for f in futuros]
            for (d, tmp), h in zip(zip(a_copiar, temporales), huellas):
                if isinstance(h, BaseException):
                    raise ErrorDestino(d, h)
                if h != h_origen:
                    decir(f"⚠️  {d.nombre}: la copia de {a.rel} no coincide. La vuelvo a copiar una vez…")
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                    h2 = copiar_a_temporales(a, [tmp], p.alg, av, [d])
                    if h2 != h_origen:
                        raise ErrorOrigen(OSError(f"La tarjeta dio dos lecturas distintas de {a.rel}: "
                                                  "posible falla de la tarjeta o del lector."))
                    if huella_de(str(tmp), p.alg, True) != h_origen:
                        try:
                            os.unlink(tmp)
                        except OSError:
                            pass
                        raise ErrorVerificacion(d, a.rel)
                final = d.carpeta / a.rel
                try:
                    os.utime(tmp, (a.atime, a.mtime))
                    if final.exists():
                        os.unlink(tmp)
                        d.estado.anotar({"tipo": "conflicto", "ruta": a.rel, "fecha_utc": iso_utc(),
                                         "motivo": "apareció un archivo con ese nombre durante la copia"})
                        conflictos.append((d, a.rel))
                        d.ok = False
                        continue
                    os.rename(tmp, final)
                    d.estado.anotar(_registro(a, h_origen, p.alg))
                except OSError as e:
                    raise ErrorDestino(d, e)
                d.verificados_ahora += 1
            av.archivo_listo(a.tam)
            av.tal_vez()
    except Corte:
        motivo, codigo = "se detuvo a pedido (Ctrl+C o se apagó la compu).", EXIT_CORTADO
    except ErrorOrigen as e:
        motivo, codigo = (f"se cortó la lectura de la tarjeta ({e}). ¿La sacaron o se desconectó el lector? "
                          "Lo copiado y verificado queda; al volver a conectarla, el mismo comando sigue "
                          "desde donde quedó."), EXIT_ORIGEN
    except ErrorDestino as e:
        lleno = getattr(e.error, "errno", None) == 28 or "No space" in str(e.error)
        motivo = (f"se llenó el disco {e.destino.nombre}. Libera espacio o usa otro disco y vuelve a correr "
                  "el mismo comando: sigue desde donde quedó." if lleno else
                  f"falló la escritura en {e.destino.nombre} ({e.error}). Revisa el cable o el disco y vuelve "
                  "a correr el mismo comando.")
        e.destino.ok = False
        codigo = EXIT_DESTINO
    except ErrorVerificacion as e:
        motivo = (f"la copia de {e.rel} en {e.destino.nombre} no coincide con la tarjeta ni después de "
                  "copiarla dos veces: ese disco o su cable pueden estar fallando. Prueba otro disco.")
        e.destino.ok = False
        codigo = EXIT_VERIFICACION
    finally:
        for d in p.destinos:
            try:
                d.estado.cerrar()
            except Exception:
                pass
    if conflictos and codigo == EXIT_OK:
        codigo = EXIT_VERIFICACION
        motivo = (f"{len(conflictos)} archivo(s) ya existían en el destino con otro contenido y no se pisaron: "
                  + ", ".join(f"{r} en {d.nombre}" for d, r in conflictos[:5]))
    fin = ahora()

    # manifiestos e informes (también si se cortó: dejan constancia de lo verificado)
    resultado = {"ok": codigo == EXIT_OK, "motivo": motivo or "", "bytes_leidos": av.leidos}
    rels_origen = {a.rel for a in p.archivos}
    regs_por_rel = {}
    for d in p.destinos:
        for rel, r in d.estado.archivos.items():
            if rel in rels_origen:
                regs_por_rel.setdefault(rel, r)
    dests_info = []
    for d in p.destinos:
        verificados = {a.rel for a in p.archivos if d.estado.verificado(a)}
        d.ok = d.ok and len(verificados) == len(p.archivos)
        dests_info.append({"nombre": d.nombre, "carpeta": str(d.carpeta), "verificados": verificados, "ok": d.ok})
    # si no había nada nuevo y el manifiesto ya cubre todo, no se repiten manifiesto ni informe
    nada_nuevo = not pendientes and not conflictos and all(
        set(leer_manifiesto(d.carpeta)[1]) >= rels_origen for d in p.destinos if d.ok)
    metas, con_ffprobe = ({}, False)
    if regs_por_rel and not args.sin_informe and resultado["ok"] and not nada_nuevo:
        base = next((d for d in p.destinos if d.ok), p.destinos[0])
        metas, con_ffprobe = leer_metadatos(base.carpeta, [r for r in regs_por_rel if (base.carpeta / r).exists()])
    p_like = {"tarjeta": p.tarjeta_carpeta, "proyecto": p.proyecto, "fecha": p.fecha, "alg": p.alg,
              "camara_txt": (p.camara or {}).get("nombre", ""), "ffprobe": con_ffprobe}
    try:
        p_like["fecha_txt"] = fecha_legible(dt.datetime.strptime(p.fecha, "%Y-%m-%d"), hora=False)
    except ValueError:
        pass
    informes = []
    for d in p.destinos:
        regs = [r for rel, r in d.estado.archivos.items() if rel in rels_origen]
        if not regs:
            continue
        if nada_nuevo:
            viejos = sorted((d.carpeta / CARPETA_META).glob("informe_*.html"))
            if viejos:
                informes.append(viejos[-1])
            continue
        try:
            if d.ok:
                escribir_mhl(d.carpeta, p.tarjeta_carpeta, regs, t0, time.time())
            if not args.sin_informe:
                h_p, c_p = escribir_informe(p_like, dests_info, regs_por_rel, metas, inicio, fin, resultado,
                                            d.carpeta)
                informes.append(h_p)
        except OSError as e:
            decir(f"⚠️  No pude escribir el manifiesto o el informe en {d.nombre}: {e}")
    if not nada_nuevo:
        _historial_anotar({"fecha_utc": iso_utc(), "tarjeta": p.tarjeta_carpeta, "firma": p.firma,
                       "origen_nombre": p.info_origen.get("nombre"), "origen_uuid": p.info_origen.get("uuid"),
                       "archivos": len(p.archivos), "bytes": p.total, "ok": resultado["ok"],
                       "destinos": [str(d.carpeta) for d in p.destinos], "codigo": codigo,
                       "rutas": [[a.rel, a.tam, a.mtime] for a in p.archivos] if len(p.archivos) <= 20000 else None})
    seg = max(time.time() - t0, 0.001)
    decir("")
    if resultado["ok"]:
        decir(f"✅ {p.tarjeta_carpeta}: {len(p.archivos)} archivos ({tam(p.total)}) en {len(p.destinos)} discos, "
              f"cada copia releída y verificada ({duracion(seg)}).")
        decir("   Ya se puede formatear la tarjeta EN LA CÁMARA (nunca desde la computadora).")
    else:
        decir(f"❌ NO formatees la tarjeta: {motivo}")
    for d in dests_info:
        decir(f"   {'✅' if d['ok'] else '❌'} {d['nombre']}: {len(d['verificados'])} de {len(p.archivos)} "
              f"verificados → {d['carpeta']}")
    if informes:
        decir(f"📄 Informe: {informes[0]}")
    if args.json_final:
        decir("RESULTADO=" + json.dumps({"ok": resultado["ok"], "motivo": motivo or "", "codigo": codigo,
                                         "tarjeta": p.tarjeta_carpeta, "archivos": len(p.archivos), "bytes": p.total,
                                         "informe": str(informes[0]) if informes else None,
                                         "destinos": [{"nombre": d["nombre"], "carpeta": d["carpeta"], "ok": d["ok"]}
                                                      for d in dests_info]}, ensure_ascii=False))
    return codigo


def cmd_plan(args):
    p = armar_plan(args, leer_config())
    mostrar_plan(p, json_out=args.json)
    return EXIT_NO_EMPIEZA if p.errores else EXIT_OK


# ───────────────────────────── verificar / manifiesto / informe ─────────────────────────────

def _archivos_en(carpeta: Path):
    out = {}
    for raiz, dirs, files in os.walk(carpeta):
        rel_raiz = os.path.relpath(raiz, carpeta)
        dirs[:] = [d for d in dirs if d.lower() not in IGNORAR and not (rel_raiz == "." and d in (CARPETA_META,
                                                                                                   "ascmhl"))]
        for f in files:
            if f.lower() in IGNORAR or f.startswith("._") or f.endswith(SUFIJO_PARCIAL):
                continue
            if rel_raiz == "." and f.lower().endswith(".mhl"):
                continue
            rel = f if rel_raiz == "." else rel_raiz.replace(os.sep, "/") + "/" + f
            out[rel] = os.path.join(raiz, f)
    return out


def verificar_carpeta(carpeta: Path, rapido=False, avance=True):
    desc, entradas = leer_manifiesto(carpeta)
    res = {"carpeta": str(carpeta), "manifiesto": desc, "ok": [], "distintos": [], "faltan": [], "nuevos": [],
           "sin_poder": [], "tam_distinto": []}
    if not desc:
        return res
    presentes = _archivos_en(carpeta)
    total = sum((e.get("tam") or 0) for e in entradas.values())
    hecho, t0, ult = 0, time.time(), time.time()
    for i, (rel, e) in enumerate(sorted(entradas.items(), key=lambda x: clave_natural(x[0])), 1):
        ruta = presentes.get(rel) or str(carpeta / rel)
        if not os.path.exists(ruta):
            res["faltan"].append(rel)
            continue
        tam_real = os.path.getsize(ruta)
        if e.get("tam") is not None and e["tam"] != tam_real:
            res["tam_distinto"].append(rel)
            continue
        if rapido:
            res["ok"].append(rel)
            continue
        alg = next((x for x in ("md5", "sha1", "c4", "xxh64", "xxh3", "xxh128") if e["huellas"].get(x)), None)
        if not alg:
            res["sin_poder"].append((rel, "el manifiesto no trae huella"))
            continue
        try:
            h = _calcular(ruta, alg)
        except _NoDisponible:
            res["sin_poder"].append((rel, f"huella {alg}: hace falta el módulo xxhash (pip install xxhash) "
                                          "u OffShoot/Hedge"))
            continue
        except OSError as ex:
            res["sin_poder"].append((rel, f"no se pudo leer ({ex})"))
            continue
        (res["ok"] if h.lower() == e["huellas"][alg].lower() else res["distintos"]).append(rel)
        hecho += tam_real
        if avance and time.time() - ult > 5:
            ult = time.time()
            vel = hecho / max(ult - t0, 1e-6)
            decir(f"   … {i}/{len(entradas)} · {tam(hecho)} de {tam(total)} · {vel / 1e6:.0f} MB/s")
    listados = set(entradas)
    res["nuevos"] = sorted((r for r in presentes if r not in listados), key=clave_natural)
    return res


def cmd_verificar(args):
    _instalar_senales()
    resultados = []
    codigo = EXIT_OK
    for c in args.carpetas:
        carpeta = Path(os.path.abspath(os.path.expanduser(c)))
        if not carpeta.is_dir():
            decir(f"❌ No existe la carpeta {carpeta}")
            codigo = EXIT_USO
            continue
        decir(f"🔎 Verificando {carpeta} …")
        try:
            r = verificar_carpeta(carpeta, rapido=args.rapido, avance=not args.json)
        except Corte:
            decir("⏹️  Detenido.")
            return EXIT_CORTADO
        resultados.append(r)
        if not r["manifiesto"]:
            decir("   ⚠️  No tiene manifiesto (.mhl). Se puede crear uno ahora con «manifiesto»: certifica cómo "
                  "está HOY (no puede saber si algo cambió antes).")
            codigo = max(codigo, EXIT_NO_EMPIEZA)
            continue
        malos = r["distintos"] + r["faltan"] + r["tam_distinto"]
        decir(f"   Manifiesto: {r['manifiesto']}")
        if r["ok"]:
            decir(f"   ✅ {len(r['ok'])} archivos {'presentes con su tamaño' if args.rapido else 'idénticos a cuando se copiaron'}.")
        for rel in r["distintos"]:
            decir(f"   ❌ CAMBIÓ (huella distinta): {rel}")
        for rel in r["tam_distinto"]:
            decir(f"   ❌ Tamaño distinto: {rel}")
        for rel in r["faltan"]:
            decir(f"   ❌ Falta: {rel}")
        for rel, por_que in r["sin_poder"][:20]:
            decir(f"   ⚠️  No se pudo comprobar {rel}: {por_que}")
        if r["nuevos"]:
            decir(f"   ℹ️  {len(r['nuevos'])} archivo(s) que no estaban en el manifiesto (agregados después): "
                  + ", ".join(r["nuevos"][:5]) + ("…" if len(r["nuevos"]) > 5 else ""))
        if malos:
            codigo = EXIT_VERIFICACION
        elif r["sin_poder"]:
            codigo = max(codigo, EXIT_NO_EMPIEZA)
        try:
            meta = carpeta / CARPETA_META
            meta.mkdir(exist_ok=True)
            with open(meta / f"verificacion_{marca_tiempo()}.csv", "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["archivo", "resultado"])
                for k, etiqueta in (("ok", "ok"), ("distintos", "CAMBIÓ"), ("tam_distinto", "TAMAÑO DISTINTO"),
                                    ("faltan", "FALTA"), ("nuevos", "nuevo (no estaba en el manifiesto)")):
                    for rel in r[k]:
                        w.writerow([rel, etiqueta])
                for rel, por_que in r["sin_poder"]:
                    w.writerow([rel, "sin comprobar: " + por_que])
        except OSError:
            pass
    mismo_nombre = len(resultados) == 2 and Path(resultados[0]["carpeta"]).name == Path(resultados[1]["carpeta"]).name
    if len(resultados) == 2 and (args.comparar or mismo_nombre) and all(r["manifiesto"] for r in resultados):
        a, b = (leer_manifiesto(Path(r["carpeta"]))[1] for r in resultados[:2])
        dif = []
        for rel in set(a) | set(b):
            if rel not in a or rel not in b:
                dif.append(rel)
                continue
            ha, hb = a[rel]["huellas"], b[rel]["huellas"]
            comunes = set(ha) & set(hb)
            if comunes and any(ha[x].lower() != hb[x].lower() for x in comunes):
                dif.append(rel)
        if dif:
            decir(f"⚠️  Las dos copias no tienen la misma lista: {len(dif)} archivo(s) distintos entre manifiestos "
                  f"(ej.: {', '.join(sorted(dif)[:3])}).")
            codigo = max(codigo, EXIT_VERIFICACION)
        else:
            decir("✅ Las dos copias tienen exactamente los mismos archivos y huellas.")
    if args.json:
        decir(json.dumps(resultados, ensure_ascii=False, indent=2, default=list))
    return codigo


def cmd_reparar(args):
    """Cambia los archivos dañados o faltantes de una copia por los buenos de otra copia (o de la tarjeta).
    Antes comprueba que el bueno coincide con el manifiesto. El dañado no se borra: queda como .DANADO_<fecha>."""
    _instalar_senales()
    mala = Path(os.path.abspath(os.path.expanduser(args.carpeta)))
    buena = Path(os.path.abspath(os.path.expanduser(args.desde)))
    desc, entradas = leer_manifiesto(mala)
    if not desc:
        decir("❌ La copia a reparar no tiene manifiesto: no hay contra qué comparar.")
        return EXIT_NO_EMPIEZA
    decir(f"🔎 Buscando qué está mal en {mala} …")
    r = verificar_carpeta(mala, avance=True)
    malos = r["distintos"] + r["tam_distinto"] + r["faltan"]
    if not malos:
        decir("✅ Esa copia está bien: no hay nada que reparar.")
        return EXIT_OK
    decir(f"Hay {len(malos)} archivo(s) para reparar desde {buena}.")
    ts = marca_tiempo()
    reparados, sin_poder = [], []
    for rel in malos:
        e = entradas[rel]
        alg = next((x for x in ("md5", "sha1", "c4") if e["huellas"].get(x)), None)
        bueno = buena / rel
        if not alg or not bueno.exists():
            sin_poder.append((rel, "no está en la copia buena" if alg else "huella no soportada"))
            continue
        try:
            if _calcular(str(bueno), alg).lower() != e["huellas"][alg].lower():
                sin_poder.append((rel, "en la otra copia tampoco coincide con el manifiesto"))
                continue
            final = mala / rel
            final.parent.mkdir(parents=True, exist_ok=True)
            tmp = final.with_name("." + final.name + SUFIJO_PARCIAL)
            if tmp.exists():
                tmp.unlink()
            a = Arch(rel, str(bueno), bueno.stat())
            av = Avance(a.tam, 1, silencioso=True)
            h = copiar_a_temporales(a, [tmp], alg if alg != "c4" else "sha512", av, [Destino(str(mala))])
            if alg == "c4":
                h = _c4(bytes.fromhex(h))
            if h.lower() != e["huellas"][alg].lower() or _calcular(str(tmp), alg).lower() != h.lower():
                tmp.unlink()
                sin_poder.append((rel, "la copia nueva no verificó: revisa el disco"))
                continue
            os.utime(tmp, (a.atime, a.mtime))
            if final.exists():
                os.rename(final, final.with_name(f"{final.name}.DANADO_{ts}"))
            os.rename(tmp, final)
            reparados.append(rel)
            decir(f"   🔧 {rel}: reparado (el dañado quedó como {final.name}.DANADO_{ts})")
        except (OSError, ErrorDestino, ErrorOrigen) as ex:
            sin_poder.append((rel, str(ex)))
    for rel, por_que in sin_poder:
        decir(f"   ❌ {rel}: {por_que}")
    if reparados and not sin_poder:
        decir(f"✅ {len(reparados)} archivo(s) reparados y verificados. Los dañados no se borraron: se pueden "
              "borrar a mano cuando quieras.")
        return EXIT_OK
    return EXIT_VERIFICACION


def cmd_manifiesto(args):
    _instalar_senales()
    carpeta = Path(os.path.abspath(os.path.expanduser(args.carpeta)))
    if not carpeta.is_dir():
        decir(f"❌ No existe {carpeta}")
        return EXIT_USO
    archivos, _ = listar_origen(str(carpeta))
    archivos = [a for a in archivos if not a.rel.startswith("ascmhl/")]
    if not archivos:
        decir("❌ La carpeta está vacía.")
        return EXIT_USO
    alg = args.algoritmo or "md5"
    total = sum(a.tam for a in archivos)
    decir(f"🧾 Huella de {len(archivos)} archivos ({tam(total)}) en {carpeta} …")
    av = Avance(total, len(archivos), pasadas=1)
    av.etapa = "leyendo"
    regs, t0 = [], time.time()
    try:
        for i, a in enumerate(archivos, 1):
            av.empezar_archivo(i, a.rel.rsplit("/", 1)[-1], a.tam, 1)
            h = huella_de(a.ruta, alg, True, av.sumar)
            regs.append(_registro(a, h, alg))
            av.archivo_listo(a.tam)
            av.tal_vez()
    except Corte:
        decir("⏹️  Detenido: no se escribió el manifiesto.")
        return EXIT_CORTADO
    mhl = escribir_mhl(carpeta, carpeta.name, regs, t0, time.time())
    decir(f"✅ Manifiesto creado: {mhl}")
    decir("   Ojo: certifica cómo están los archivos HOY. Desde ahora «verificar» avisa si algo cambia.")
    return EXIT_OK


def cmd_informe(args):
    carpeta = Path(os.path.abspath(os.path.expanduser(args.carpeta)))
    est = _leer_estado(carpeta)
    if not est or not est.archivos:
        desc, entradas = leer_manifiesto(carpeta)
        if not desc:
            decir("❌ Esa carpeta no tiene una copia hecha con esta skill ni un manifiesto.")
            return EXIT_USO
        regs = {}
        for rel, e in entradas.items():
            ruta = carpeta / rel
            if ruta.exists():
                st = ruta.stat()
                alg = next(iter(e["huellas"]), "md5")
                regs[rel] = {"ruta": rel, "tam": st.st_size, "mtime": st.st_mtime,
                             "huella": e["huellas"].get(alg, ""), "alg": alg}
        alg = next(iter(regs.values()))["alg"] if regs else "md5"
        tarjeta, proyecto, fecha = carpeta.name, "", ""
    else:
        regs = dict(est.archivos)
        alg = (est.inicio or {}).get("algoritmo", "md5")
        tarjeta = (est.inicio or {}).get("tarjeta", carpeta.name)
        proyecto, fecha = "", ""
    metas, con_ff = leer_metadatos(carpeta, list(regs))
    destinos = [{"nombre": info_volumen(str(carpeta)).get("nombre"), "carpeta": str(carpeta),
                 "verificados": set(regs), "ok": True}]
    ahora_ = ahora()
    h, c = escribir_informe({"tarjeta": tarjeta, "proyecto": proyecto, "fecha": fecha, "alg": alg,
                             "ffprobe": con_ff, "camara_txt": ""}, destinos, regs, metas, ahora_, ahora_,
                            {"ok": True, "bytes_leidos": 0}, carpeta)
    decir(f"📄 Informe: {h}\n📊 CSV: {c}")
    return EXIT_OK


# ───────────────────────────── detectar / config / historial ─────────────────────────────

def cmd_detectar(args):
    vols = detectar(contar=not args.rapido)
    if args.json:
        decir(json.dumps(vols, ensure_ascii=False, indent=2))
        return EXIT_OK
    if not vols:
        decir("No hay tarjetas ni discos conectados (aparte del disco de la computadora).")
        return EXIT_OK
    decir("Conectado ahora:")
    for v in vols:
        if v["camara"]:
            extra = (f" · {v.get('clips', 0)} clips · {v.get('archivos', 0)} archivos · {tam(v.get('bytes'))}"
                     if "archivos" in v else "")
            decir(f"🎞️  {v['nombre']} ({v['ruta']}) · {v['camara']['nombre']}{extra}")
        else:
            marca = " · guardado como destino" if v.get("es_destino_guardado") else ""
            decir(f"💽 {v['nombre']} ({v['ruta']}) · {tam(v.get('libre'))} libres de {tam(v.get('total'))}"
                  f"{' · ' + v['fs'] if v.get('fs') else ''}{marca}")
    return EXIT_OK


def cmd_config(args):
    p = dir_sistema() / "config.json"
    cfg = leer_config()
    if args.accion == "mostrar":
        if not cfg:
            decir(f"Todavía no hay configuración ({p}).")
        else:
            decir(json.dumps(cfg, ensure_ascii=False, indent=2))
        return EXIT_OK
    if args.proyecto is not None:
        cfg["proyecto"] = args.proyecto
    if args.destino:
        cfg["destinos"] = [os.path.abspath(os.path.expanduser(d)) for d in args.destino]
    if args.plantilla:
        if "{tarjeta}" not in args.plantilla:
            raise SystemExit("❌ La plantilla tiene que llevar {tarjeta}.")
        cfg["plantilla"] = args.plantilla
    if args.algoritmo:
        cfg["algoritmo"] = args.algoritmo
    if args.dia is not None:
        cfg["dia"] = args.dia
    vig = cfg.setdefault("vigilante", {"modo": "preguntar", "vigilar": "todas", "ignorar": []})
    if args.modo_vigilante:
        vig["modo"] = args.modo_vigilante
    if args.vigilar:
        vig["vigilar"] = "todas" if args.vigilar == ["todas"] else args.vigilar
    if args.ignorar is not None:
        vig["ignorar"] = args.ignorar
    cfg["version"] = 1
    cfg["actualizado"] = iso_utc()
    guardar_json(p, cfg)
    decir(f"✅ Guardado en {p}")
    decir(json.dumps(cfg, ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_historial(args):
    h = historial()[-args.ultimos:]
    if not h:
        decir("Todavía no hay descargas anotadas.")
        return EXIT_OK
    for r in h:
        try:
            f = dt.datetime.strptime(r["fecha_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=dt.timezone.utc).astimezone()
            ftxt = fecha_legible(f)
        except Exception:
            ftxt = r.get("fecha_utc", "")
        decir(f"{'✅' if r.get('ok') else '❌'} {ftxt} · {r.get('tarjeta')} · {r.get('archivos')} archivos · "
              f"{tam(r.get('bytes'))} → {', '.join(r.get('destinos') or [])}")
    return EXIT_OK


def estado_en_historial(archivos, firma):
    """'respaldada' si ya hay una copia completa verificada de exactamente esto; 'parcial' si hay una copia
    verificada de una parte (la tarjeta tiene clips nuevos); None si nunca se copió."""
    actual = {a.rel: (a.tam, int(a.mtime)) for a in archivos}
    estado = None
    for r in reversed(historial()):
        if not r.get("ok"):
            continue
        if r.get("firma") == firma and all(os.path.isdir(d) for d in r.get("destinos", [])):
            return "respaldada", r
        rutas = r.get("rutas") or []
        if rutas and all(actual.get(rel) == (t, int(m)) for rel, t, m in rutas):
            estado = estado or ("parcial", r)
    return estado if estado else (None, None)


# ───────────────────────────── autoprueba ─────────────────────────────

def cmd_autoprueba(_args):
    """Prueba corta en carpetas temporales: copia, verifica y detecta un byte cambiado. No toca nada tuyo."""
    script = os.path.abspath(__file__)
    py = sys.executable
    ok_total = True
    with tempfile.TemporaryDirectory(prefix="autoprueba-descarga-") as tmp:
        tmp = Path(tmp)
        tarjeta = tmp / "TARJETA"
        for rel, n in (("DCIM/100MSDCF/DSC00001.JPG", 2_000_000), ("PRIVATE/M4ROOT/CLIP/C0001.MP4", 6_000_000),
                       ("PRIVATE/M4ROOT/CLIP/C0001M01.XML", 3_000), ("PRIVATE/M4ROOT/CLIP/C0002.MP4", 9_000_001)):
            f = tarjeta / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(os.urandom(n))
        d1, d2 = tmp / "DISCO1", tmp / "DISCO2"
        d1.mkdir()
        d2.mkdir()
        env = dict(os.environ, RESPALDO_MATERIAL_DIR=str(tmp / "sistema"))

        def correr(*a):
            r = subprocess.run([py, script, *a], capture_output=True, text=True, env=env, encoding="utf-8",
                               errors="replace")
            return r.returncode, r.stdout + r.stderr

        def chequear(nombre, cond, salida=""):
            nonlocal ok_total
            ok_total &= bool(cond)
            decir(f"{'✅' if cond else '❌'} {nombre}")
            if not cond and salida:
                decir("   " + salida.strip().replace("\n", "\n   ")[-1500:])

        c, s = correr("copiar", "--origen", str(tarjeta), "--destino", str(d1), "--destino", str(d2),
                      "--proyecto", "PRUEBA", "--tarjeta", "A001", "--fecha", "2026-01-01", "--permitir-mismo-disco",
                      "--silencioso")
        chequear("copia a 2 destinos con verificación", c == 0, s)
        carpeta1 = d1 / "PRUEBA" / "2026-01-01" / "A001"
        carpeta2 = d2 / "PRUEBA" / "2026-01-01" / "A001"
        iguales = all((carpeta1 / r).read_bytes() == (tarjeta / r).read_bytes() ==
                      (carpeta2 / r).read_bytes() for r in ("PRIVATE/M4ROOT/CLIP/C0002.MP4",))
        chequear("las copias son idénticas a la tarjeta", iguales)
        chequear("hay manifiesto .mhl en cada copia", list(carpeta1.glob("*.mhl")) and list(carpeta2.glob("*.mhl")))
        c, s = correr("verificar", str(carpeta1), str(carpeta2))
        chequear("verificar: todo bien", c == 0, s)
        f = carpeta2 / "PRIVATE/M4ROOT/CLIP/C0001.MP4"
        b = bytearray(f.read_bytes())
        b[len(b) // 2] ^= 0xFF
        f.write_bytes(bytes(b))
        c, s = correr("verificar", str(carpeta2))
        chequear("verificar detecta un byte cambiado", c == EXIT_VERIFICACION and "C0001.MP4" in s, s)
        c, s = correr("copiar", "--origen", str(tarjeta), "--destino", str(d1), "--destino", str(d2),
                      "--proyecto", "PRUEBA", "--tarjeta", "A001", "--fecha", "2026-01-01", "--permitir-mismo-disco",
                      "--silencioso")
        chequear("repetir la copia no duplica ni pisa nada", c == 0 and not (d1 / "PRUEBA/2026-01-01/A001_2").exists(), s)
        tarj_txt = (tarjeta / "PRIVATE/M4ROOT/CLIP/C0001M01.XML").stat().st_size == 3_000
        chequear("la tarjeta no se tocó", tarj_txt)
        decir(f"Relectura {MODO_RELECTURA['valor']} en esta computadora · Python {sys.version.split()[0]} · "
              f"ffprobe {'sí' if _ffprobe() else 'no'}")
    decir("✅ Autoprueba completa." if ok_total else "❌ La autoprueba encontró problemas (arriba).")
    return EXIT_OK if ok_total else EXIT_VERIFICACION


# ───────────────────────────── principal ─────────────────────────────

def main(argv=None):
    _consola_utf8()
    ap = argparse.ArgumentParser(prog="descarga.py",
                                 description="Copia tarjetas de cámara a 2+ discos con verificación real.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def datos_copia(sp):
        sp.add_argument("--origen", required=True, help="tarjeta o carpeta a copiar")
        sp.add_argument("--destino", action="append", help="carpeta raíz en cada disco (repetir por disco)")
        sp.add_argument("--proyecto")
        sp.add_argument("--tarjeta", help="nombre de la tarjeta (si no, el del volumen o SONY_01…)")
        sp.add_argument("--fecha", help="AAAA-MM-DD (si no, el día de grabación de los clips)")
        sp.add_argument("--dia", help="etiqueta de jornada para {dia}, ej. DIA_01")
        sp.add_argument("--plantilla", help=f"carpetas, por defecto {PLANTILLA_DEFECTO}")
        sp.add_argument("--algoritmo", choices=ALGORITMOS)
        sp.add_argument("--permitir-mismo-disco", action="store_true")

    sp = sub.add_parser("detectar")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--rapido", action="store_true", help="sin contar archivos")
    sp.set_defaults(fn=cmd_detectar)

    sp = sub.add_parser("plan")
    datos_copia(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_plan)

    sp = sub.add_parser("copiar")
    datos_copia(sp)
    sp.add_argument("--cada", type=float, default=5.0, help="segundos entre líneas de avance")
    sp.add_argument("--silencioso", action="store_true")
    sp.add_argument("--sin-informe", action="store_true")
    sp.add_argument("--json-final", action="store_true")
    sp.add_argument("--apartar-conflictos", action="store_true",
                    help="(solo con el OK de la persona) si un archivo del destino es distinto al de la tarjeta, "
                         "renombrarlo a .DISTINTO_<fecha> y copiar el de la tarjeta")
    sp.set_defaults(fn=cmd_copiar)

    sp = sub.add_parser("verificar")
    sp.add_argument("carpetas", nargs="+")
    sp.add_argument("--rapido", action="store_true", help="solo presencia y tamaño, sin releer")
    sp.add_argument("--comparar", action="store_true",
                    help="son dos copias del mismo material: además compararlas entre sí "
                         "(se hace solo si las dos carpetas se llaman igual)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_verificar)

    sp = sub.add_parser("reparar")
    sp.add_argument("carpeta", help="la copia con archivos dañados o faltantes")
    sp.add_argument("--desde", required=True, help="la otra copia (o la tarjeta) de donde sacar los buenos")
    sp.set_defaults(fn=cmd_reparar)

    sp = sub.add_parser("manifiesto")
    sp.add_argument("carpeta")
    sp.add_argument("--algoritmo", choices=ALGORITMOS)
    sp.set_defaults(fn=cmd_manifiesto)

    sp = sub.add_parser("informe")
    sp.add_argument("carpeta")
    sp.set_defaults(fn=cmd_informe)

    sp = sub.add_parser("config")
    sp.add_argument("accion", choices=["mostrar", "guardar"])
    sp.add_argument("--proyecto")
    sp.add_argument("--destino", action="append")
    sp.add_argument("--plantilla")
    sp.add_argument("--algoritmo", choices=ALGORITMOS)
    sp.add_argument("--dia")
    sp.add_argument("--modo-vigilante", choices=["preguntar", "automatico"])
    sp.add_argument("--vigilar", nargs="+", help="todas, o ids: " + ", ".join(f[0] for f in FIRMAS_CAMARA))
    sp.add_argument("--ignorar", nargs="*", help="nombres de discos que el vigilante no toca")
    sp.set_defaults(fn=cmd_config)

    sp = sub.add_parser("historial")
    sp.add_argument("--ultimos", type=int, default=20)
    sp.set_defaults(fn=cmd_historial)

    sp = sub.add_parser("autoprueba")
    sp.set_defaults(fn=cmd_autoprueba)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except SystemExit as e:
        if isinstance(e.code, str):
            decir(e.code)
            return EXIT_USO
        raise
    except KeyboardInterrupt:
        decir("⏹️  Detenido.")
        return EXIT_CORTADO


if __name__ == "__main__":
    sys.exit(main())
