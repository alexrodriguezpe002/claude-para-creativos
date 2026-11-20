#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MD FILES — el registro de cada proyecto del usuario (skill `mdfilesummary`).

Cada proyecto guarda su historia en `<carpeta del proyecto>/MD FILES/`, al lado de
AFTER, RENDERS, PREMIERE...:

  <NOMBRE> — Resumen.md    resumen global del proyecto (la puerta de entrada)
  <NOMBRE> — <Video>.md    uno por video de HyperFrames (teaser, snippet, clip)
  + anexos                 auditorías, specs, propuestas, archivos viejos

Uso (los tres primeros los llaman solos los hooks del plugin creativos-base):

  md_files.py post-tool             hook PostToolUse: crea el registro y anota la sesión
  md_files.py prompt                hook UserPromptSubmit: "El usuario nombró CAMPAÑA VERANO" -> ruta
  md_files.py stop                  hook Stop: pide actualizar en los hitos y regenera el índice
  md_files.py indice                regenera ~/.claude/registro-proyectos/INDICE.md
  md_files.py buscar TEXTO          qué registros coinciden con TEXTO
  md_files.py ensure RUTA...        crea a mano el registro de un proyecto o video
  md_files.py donde RUTA [--cwd C]  dice qué carpeta tomaría como proyecto (o por qué ninguna)
  md_files.py backfill [--aplicar]  vincula las sesiones guardadas a cada proyecto

Dónde actúa (kit v2): en la carpeta de proyecto que la persona abra, esté donde esté. La carpeta
del proyecto es, en este orden: la que ya tiene `MD FILES/`; la que tiene al menos dos carpetas de
la plantilla (MATERIAL, RENDERS, PREMIERE...); `<raíz>/<CLIENTE>/<PROYECTO>` debajo de una carpeta
de proyectos declarada en ~/.claude/registro-proyectos/carpetas.json; o la carpeta abierta en la
sesión. Nunca la carpeta de usuario, el Escritorio, Descargas, Documentos, la raíz de un disco,
una nube (iCloud, Drive, OneDrive, Dropbox), ~/.claude ni carpetas del sistema.

Los hooks nunca frenan nada: ante cualquier error salen con código 0 y lo anotan
en ~/.claude/registro-proyectos/errores.log. Funciona en Mac, Windows y Linux (Python 3.7+).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

try:                                   # Mac y Linux
    import fcntl
except ImportError:                    # Windows: no hay fcntl
    fcntl = None
try:
    import msvcrt                      # Windows
except ImportError:
    msvcrt = None

IS_WIN = os.name == "nt"
HOME = Path(os.path.expanduser("~"))
# Las variables MDFILES_* existen solo para probar el script con carpetas de prueba.
REG_DIR = Path(os.environ.get("MDFILES_REG_DIR", str(HOME / ".claude" / "registro-proyectos")))
STATE_DIR = Path(os.environ.get("MDFILES_STATE_DIR",
                                os.path.join(tempfile.gettempdir(), "claude-md-files")))
# Las sesiones guardadas: una carpeta por carpeta abierta, todas dentro de ~/.claude/projects/.
PROJECTS_DIR = Path(os.environ.get("MDFILES_TRANSCRIPTS", str(HOME / ".claude" / "projects")))
INDEX_MD = REG_DIR / "INDICE.md"
INDEX_JSON = REG_DIR / "indice.json"
ERROR_LOG = REG_DIR / "errores.log"
# Opcional: las carpetas donde la persona guarda sus proyectos (`raices`) y las que nunca son un
# proyecto (`ignorar`). Lo escribe Claude cuando la persona lo pide; sin el archivo vale ~/PROYECTOS.
CARPETAS_JSON = REG_DIR / "carpetas.json"
# Carpetas de proyecto que ya tienen registro, aunque estén fuera de las raíces: así el índice las
# encuentra sin recorrer todo el disco.
PROYECTOS_JSON = REG_DIR / "proyectos.json"

MD_DIR = "MD FILES"
SEP = " — "
THROTTLE_S = 20 * 60          # entre recordatorios de "actualiza el registro" por edición

# Una carpeta es la raíz del proyecto si tiene al menos dos de estas (la plantilla del usuario).
TEMPLATE_DIRS = {"AFTER", "PREMIERE", "RENDERS", "MEDIA", "AUDIO RENDERS", "AUDIO PARA IA",
                 "EXTRA", "GRAFICA", "MUSIC", "PARA HYPERFRAMES", "MATERIAL", "AUDIO", "HYPERFRAMES"}
SKIP_PARTS = {"node_modules", ".git", "ASSETS", ".thumbnails", ".gates-cache", "$RECYCLE.BIN",
              ".Trashes", ".Spotlight-V100", ".fseventsd", "System Volume Information"}
# Lo que dejan los gates y `hyperframes snapshot` al medir un video (además de las carpetas
# ocultas, como .gates-cache/): no cuenta como trabajo en el video.
QA_DIRS = {"snapshots"}
# MD que leen las herramientas: se quedan donde están, nunca van a MD FILES.
FUNCTIONAL_MD = {"agents.md", "claude.md", "design.md", "brief.md", "storyboard.md",
                 "script.md", "beats.md", "readme.md", "skill.md", "index.md"}

SESS_HEADER = "## Sesiones"
SESS_COMMENT = ("<!-- La mantiene el hook de MD FILES: una línea por sesión de Claude que "
                "trabajó acá. No borrar ni reescribir. -->")
SESS_RE = re.compile(r"^## Sesiones[ \t]*$", re.M)
FM_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n", re.S)
TITLE_RE = re.compile(r'"customTitle":"((?:[^"\\]|\\.)*)"')
HF_RE = re.compile(r"hyperframes", re.I)          # CLI o carpeta HYPERFRAMES/
HFCLI_RE = re.compile(r"\bhyperframes\s+(init|preview|render|check|lint|snapshot|inspect|"
                      r"validate|compare|transcribe|play|present|capture|keyframes|beats)\b",
                      re.I)
INIT_RE = re.compile(r"\bhyperframes\s+init\b", re.I)
PREVIEW_RE = re.compile(r"\bhyperframes\s+preview\b", re.I)
RENDER_RE = re.compile(r"\bhyperframes\s+render\b|render_beat|prores", re.I)
WRITE_RE = re.compile(r"(?:^|[\s;&|(])(?:cp|mv|rsync|ditto|tee|touch|mkdir)\s|sed\s+-i|"
                      r"perl\s+-p?i|(?<![0-9&>])>(?![&>])(?!\s*/dev/null)")
# "CLA 12", "cla-012", "EP 12": código + número de un proyecto nombrado en un pedido.
CODE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2,4})[ _-]?0*(\d{1,4})(?![0-9])")
# Rutas absolutas dentro de un comando: /..., ~/..., C:\... o C:/... (entre comillas o sueltas).
_ABS = r"""(?:~(?=/)|/|[A-Za-z]:[\\/])"""
QPATH_RE = re.compile(r"""(['"])(""" + _ABS + r""".+?)\1""")
UPATH_RE = re.compile(r"""(?:^|(?<=[\s=(]))(""" + _ABS + r"""(?:\\.|[^\s'"\\;|&<>()])+)""")
# Entregables que cuentan en la carpeta abierta cuando no tiene plantilla ni registro: solo video,
# audio, subtítulos y líneas de tiempo (una imagen, un PDF o un .txt sueltos no arman un proyecto).
MEDIA_EXT = {".srt", ".vtt", ".ass", ".scc", ".mp4", ".mov", ".m4v", ".mxf", ".wav", ".mp3",
             ".aac", ".m4a", ".fcpxml", ".edl", ".aaf", ".prproj", ".drp", ".aep"}
# Una carpeta abierta que es un repositorio de código no es un proyecto de video.
CODE_MARKERS = {"package.json", "pyproject.toml", "setup.py", "Cargo.toml", "go.mod", "pom.xml",
                "Gemfile", "composer.json", "CMakeLists.txt", ".claude-plugin"}


# --------------------------------------------------------------------------- util

def now():
    return datetime.now()


def today():
    return datetime.now().strftime("%Y-%m-%d")


def local_date(iso):
    try:
        dt = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d")
    except Exception:
        return today()


def log_error(where, exc):
    try:
        REG_DIR.mkdir(parents=True, exist_ok=True)
        if ERROR_LOG.exists() and ERROR_LOG.stat().st_size > 200_000:
            ERROR_LOG.write_text("", encoding="utf-8")
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{now().isoformat(timespec='seconds')} [{where}] "
                    f"{type(exc).__name__}: {exc}\n")
    except Exception:
        pass


def fold(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def clean_line(s, limit=90):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = s.replace("`", "'").replace("|", "/")
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + "…"
    return s


def q(p):
    return f"«{p}»"


class Lock:
    """Candado entre hooks que corren en paralelo (subagentes, varias sesiones)."""

    def __init__(self, name="md-files"):
        self.path = STATE_DIR / f"{name}.lock"
        self.f = None

    def _try(self):
        if fcntl is not None:
            fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif msvcrt is not None:
            self.f.seek(0)
            msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)

    def __enter__(self):
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            self.f = open(self.path, "a+")
            deadline = time.time() + 5
            while True:
                try:
                    self._try()
                    break
                except OSError:
                    if time.time() > deadline:
                        break
                    time.sleep(0.05)
        except Exception:
            pass
        return self

    def __exit__(self, *exc):
        try:
            if self.f:
                if fcntl is not None:
                    fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
                elif msvcrt is not None:
                    try:
                        self.f.seek(0)
                        msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                self.f.close()
        except Exception:
            pass
        return False


# ------------------------------------------------------------------ estado por sesión

def _state_file(sid):
    safe = re.sub(r"[^A-Za-z0-9_-]", "", sid or "") or "sin-sesion"
    return STATE_DIR / f"sesion-{safe}.json"


def load_state(sid):
    st = {"registrados": [], "dirty": {}, "anunciados": [], "md_escrito": {},
          "pendientes": [], "indice_sucio": False, "md_visto": {}}
    try:
        st.update(json.loads(_state_file(sid).read_text(encoding="utf-8")))
    except Exception:
        pass
    return st


def save_state(sid, st):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        p = _state_file(sid)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
    except Exception as e:
        log_error("save_state", e)


# ------------------------------------------------------------------------- rutas

def _norm(p):
    """Ruta absoluta para comparar: sin ~ y, en Windows, sin mayúsculas ni barras mezcladas."""
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(p))))


def _within(child, parent):
    c, p = _norm(child), _norm(parent)
    return c == p or c.startswith(p.rstrip("\\/") + os.sep)


def _msys(p):
    """Git Bash en Windows escribe /c/Users/...: se pasa a C:/Users/..."""
    if IS_WIN:
        m = re.match(r"^/([A-Za-z])(/.*)?$", p or "")
        if m:
            return m.group(1).upper() + ":" + (m.group(2) or "/")
    return p


def _abs(p):
    return Path(os.path.abspath(os.path.expanduser(_msys(str(p)))))


@lru_cache(maxsize=1)
def carpetas_config():
    """(raíces de proyectos, carpetas a ignorar) de carpetas.json. Sin archivo: ~/PROYECTOS."""
    raices, ignorar = None, []
    try:
        data = json.loads(CARPETAS_JSON.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            if isinstance(data.get("raices"), list):
                raices = [x for x in data["raices"] if isinstance(x, str) and x.strip()]
            if isinstance(data.get("ignorar"), list):
                ignorar = [x for x in data["ignorar"] if isinstance(x, str) and x.strip()]
    except Exception:
        pass
    if raices is None:
        raices = ["~/PROYECTOS"]
    return tuple(_abs(x) for x in raices), tuple(_abs(x) for x in ignorar)


# Carpetas que agrupan cosas y nunca son un proyecto, cuando cuelgan de la carpeta de usuario,
# de una nube o de la raíz de un disco (en inglés en el disco aunque el Finder diga "Escritorio").
CONTAINER_NAMES = {
    "desktop", "escritorio", "downloads", "descargas", "documents", "documentos", "movies",
    "películas", "peliculas", "music", "música", "musica", "pictures", "imágenes", "imagenes",
    "fotos", "videos", "vídeos", "public", "público", "publico", "applications", "aplicaciones",
    "dropbox", "google drive", "icloud drive", "box", "creative cloud files", "my drive",
    "mi unidad", "shared drives", "unidades compartidas", "other computers", "otros ordenadores",
    "otras computadoras", "users", "usuarios"}


def _system_dirs():
    if IS_WIN:
        out = [os.environ.get("SystemRoot") or r"C:\Windows"]
        out += [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
                                            "ProgramData")]
        return [Path(x) for x in out if x]
    return [Path(x) for x in ("/System", "/Library", "/Applications", "/usr", "/bin", "/sbin",
                              "/etc", "/opt", "/private/etc", "/private/var", "/var", "/dev",
                              "/proc", "/sys", "/cores", "/Network", "/snap", "/boot")]


def no_es_proyecto_nunca(p):
    """True si `p` está donde nunca se crea un registro: el sistema, ~/.claude y las demás carpetas
    ocultas de la carpeta de usuario, ~/Library (salvo las nubes), AppData o una carpeta ignorada."""
    n = _norm(p)
    home = _norm(HOME)
    if n != home and _within(n, home):
        rel = Path(n[len(home):].lstrip("\\/")).parts
        first = rel[0].lower() if rel else ""
        if first.startswith("."):
            return True
        if first == "appdata":
            return True
        if first == "library":
            nube = len(rel) >= 2 and rel[1].lower() in ("cloudstorage", "mobile documents")
            if not nube:
                return True
    if any(_within(n, s) for s in _system_dirs()):
        return True
    return any(_within(n, x) for x in carpetas_config()[1])


def _es_nube(d):
    """Raíz de una nube sincronizada: ~/OneDrive*, ~/Dropbox, ~/Library/CloudStorage/<x>/My Drive..."""
    n, home = _norm(d), _norm(HOME)
    if n == home or not _within(n, home):
        return False
    low = [x.lower() for x in Path(n[len(home):].lstrip("\\/")).parts]
    if len(low) == 1:
        return low[0].startswith("onedrive") or low[0] in CONTAINER_NAMES
    if low[:2] in (["library", "cloudstorage"], ["library", "mobile documents"]):
        return len(low) <= 3 or (len(low) == 4 and low[3] in CONTAINER_NAMES)
    return False


def es_contenedor(d):
    """Carpetas que nunca son un proyecto en sí mismas (sí lo que está adentro): la raíz del disco,
    la carpeta de usuario, Escritorio, Descargas, Documentos, Películas, Imágenes, Música, una nube,
    la raíz de un disco externo, las carpetas temporales y las raíces de proyectos declaradas."""
    dp = _abs(d)
    n = _norm(dp)
    if dp.parent == dp or n in (_norm(HOME), _norm(HOME.parent)):
        return True
    if n in {_norm(t) for t in ("/tmp", "/private/tmp", "/var/tmp", tempfile.gettempdir())}:
        return True
    if not IS_WIN:
        if str(dp) in ("/Volumes", "/mnt", "/media") or str(dp.parent) in ("/Volumes", "/mnt"):
            return True
        if str(dp.parent.parent) == "/media":              # /media/<usuario>/<disco> (Linux)
            return True
    try:
        if os.path.ismount(str(dp)):
            return True
    except Exception:
        pass
    if any(n == _norm(r) for r in carpetas_config()[0]):
        return True
    if _es_nube(dp):
        return True
    name = dp.name.lower()
    if name in CONTAINER_NAMES or name.startswith("onedrive"):
        par = dp.parent
        if _norm(par) == _norm(HOME) or _es_nube(par) or par.parent == par:
            return True
    return False


def raiz_de(p):
    """La carpeta de proyectos declarada (o ~/PROYECTOS) que contiene `p`, o None."""
    best = None
    for r in carpetas_config()[0]:
        if _within(p, r) and _norm(p) != _norm(r):
            if best is None or len(_norm(r)) > len(_norm(best)):
                best = r
    return best


def es_repo_de_codigo(d):
    """Una carpeta abierta que es un programa (repo con package.json, un plugin...) no es un
    proyecto de video: ahí no se crea el registro solo."""
    names = _listdir(str(d))
    return ".claude-plugin" in names or (".git" in names and bool(CODE_MARKERS & names))


def find_root_modo(path, cwd=None):
    """(carpeta del proyecto, modo) o (None, por qué no).

    Modos: "registro" (ya tiene MD FILES), "plantilla" (dos o más carpetas de la plantilla),
    "raiz" (<raíz>/<CLIENTE>/<PROYECTO>, debajo de una carpeta de proyectos declarada),
    "abierta" (la carpeta que la persona abrió en la sesión)."""
    if not path:
        return None, "sin ruta"
    p = _abs(path)
    if no_es_proyecto_nunca(p):
        return None, "carpeta del sistema, oculta (como ~/.claude) o ignorada en carpetas.json"
    parts = p.parts
    if MD_DIR in parts:
        root = Path(*parts[:parts.index(MD_DIR)])
        if root.parts and not es_contenedor(root):
            return root, "registro"
        return None, "MD FILES suelto en una carpeta contenedora"
    if any(x in SKIP_PARTS for x in parts):
        return None, "carpeta interna (node_modules, .git, ASSETS...)"
    d = p
    while not d.is_dir():
        if d.parent == d:
            return None, "la ruta no existe"
        d = d.parent
    cur = d
    while not es_contenedor(cur) and not no_es_proyecto_nunca(cur):
        if (cur / MD_DIR).is_dir():
            return cur, "registro"
        if count_markers(cur) >= 2:
            return cur, "plantilla"
        if cur.parent == cur:
            break
        cur = cur.parent
    raiz = raiz_de(p)
    if raiz is not None:
        rel = p.parts[len(raiz.parts):]
        if len(rel) >= 2:
            cand = raiz.joinpath(rel[0], rel[1])
            if cand.is_dir() and not es_contenedor(cand):
                return cand, "raiz"
        return None, "en la carpeta de proyectos, pero no dentro de <CLIENTE>/<PROYECTO>"
    if cwd:
        c = _abs(cwd)
        if _within(p, c) and c.is_dir():
            if es_contenedor(c):
                return None, ("la carpeta abierta es una carpeta general (usuario, Escritorio, "
                              "Descargas, Documentos, una nube o la raíz de un disco)")
            if no_es_proyecto_nunca(c):
                return None, "la carpeta abierta es del sistema u oculta"
            if es_repo_de_codigo(c) and not is_video_dir(c):
                return None, "la carpeta abierta es un repositorio de código"
            return c, "abierta"
    return None, "fuera de la carpeta abierta y sin plantilla ni registro"


def find_root(path, cwd=None):
    """Carpeta raíz del proyecto o None (ver find_root_modo)."""
    return find_root_modo(path, cwd)[0]


def volumen_de(path):
    """Nombre del disco externo donde está `path` ("" si es el disco de la computadora)."""
    p = _abs(path)
    if IS_WIN:
        drive = (p.drive or "").upper()
        sysdrive = (os.environ.get("SystemDrive") or "C:").upper()
        return drive if drive and drive != sysdrive else ""
    parts = p.parts
    if len(parts) >= 3 and parts[1] in ("Volumes", "mnt"):
        return parts[2]
    if len(parts) >= 4 and parts[1] == "media":
        return parts[3]
    return ""


def conectado(path):
    """¿Está conectado el disco de `path`? (el interno siempre)."""
    v = volumen_de(path)
    if not v:
        return True
    p = _abs(path)
    if IS_WIN:
        return Path(p.drive + "\\").exists()
    parts = p.parts
    base = Path(*parts[:3]) if parts[1] in ("Volumes", "mnt") else Path(*parts[:4])
    return base.is_dir()


@lru_cache(maxsize=8192)
def _listdir(d):
    try:
        return frozenset(os.listdir(d))
    except Exception:
        return frozenset()


def count_markers(d):
    return len(TEMPLATE_DIRS & _listdir(str(d)))


def is_video_dir(d):
    names = _listdir(str(d))
    if "index.html" not in names:
        return False
    if "hyperframes.json" in names or "meta.json" in names:
        return True
    parent = Path(d).parent.name.upper()
    return parent == "HYPERFRAMES" or parent.endswith("ANIMATIONS")


def find_video_dir(path, root):
    """Carpeta del proyecto de HyperFrames (un video) que contiene `path`, o None."""
    path, root = Path(path), Path(root)
    try:
        rel = path.relative_to(root).parts
    except ValueError:
        return None
    if not rel or rel[0] == MD_DIR:
        return None
    for part in rel:
        low = part.lower()
        if part in SKIP_PARTS or "handoff" in low or low == "reference":
            return None
    d = path
    while not d.is_dir():
        if d == d.parent or d == root:
            return None
        d = d.parent
    while d != root and root in d.parents:
        if is_video_dir(d):
            return d
        d = d.parent
    return None


def extract_paths(cmd):
    """Rutas absolutas nombradas en un comando (las relativas se cubren con la carpeta abierta)."""
    cmd = cmd or ""
    out = [m.group(2) for m in QPATH_RE.finditer(cmd)]
    for m in UPATH_RE.finditer(cmd):
        raw = m.group(1)
        # una ruta de Windows lleva barras invertidas de verdad; en Mac, "\ " es un espacio
        out.append(raw if re.match(r"^[A-Za-z]:", raw) else re.sub(r"\\(.)", r"\1", raw))
    clean = []
    for p in out:
        p = re.split(r"[*?\[]", p)[0]
        if len(p) > 3:
            p = p.rstrip("/\\")
        p = os.path.expanduser(_msys(p))
        if not p or p == "/" or p.startswith(("/dev/", "/proc/")) or p == "/dev":
            continue
        if p not in clean:
            clean.append(p)
    return clean


# ------------------------------------------------------------------------ nombres

def nombre_de(root):
    """El nombre de la carpeta del proyecto: `CLA 012`, `09-18 CAMPAÑA`, `Video boda Ana`."""
    return Path(root).name.replace("/", "-").replace(":", "-") or "Proyecto"


def cliente_de(root):
    """El cliente: la carpeta del primer nivel debajo de la carpeta de proyectos declarada, o la
    carpeta madre del proyecto cuando no es una carpeta general (Escritorio, Documentos...)."""
    root = _abs(root)
    raiz = raiz_de(root)
    if raiz is not None:
        rel = root.parts[len(raiz.parts):]
        if len(rel) >= 2:
            return rel[0]
        return ""
    par = root.parent
    if par == root or es_contenedor(par) or no_es_proyecto_nunca(par):
        return ""
    return par.name


def codigo_ep(nombre):
    m = re.match(r"^([A-Z]{2,4}) (\d{1,4})$", nombre or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def video_de(vdir, nombre):
    """`CLA 012 Snippet 4` -> `Snippet 4`, `CLA011-Snippet1` -> `Snippet 1`, `teaser` -> `Teaser`."""
    s = Path(vdir).name
    code, ep = codigo_ep(nombre)
    if code:
        s = re.sub(r"(?i)^\s*" + code + r"\s*[-_ ]?\s*0*" + str(int(ep)) + r"(?!\d)\s*[-_–— ]*",
                   "", s)
    s = s.replace("_", " ")
    s = re.sub(r"(?<=[A-Za-z])-|-(?=[A-Za-z])", " ", s)
    s = re.sub(r"(?i)\b(snippet|teaser|clip|seg|segment|reel|short|part|parte)(\d)", r"\1 \2", s)
    s = re.sub(r"\s+", " ", s).strip(" -–—")
    if s[:1].islower():
        s = s[0].upper() + s[1:]
    return (s or Path(vdir).name).replace("/", "-").replace(":", "-")


def global_path(root, nombre=None):
    nombre = nombre or nombre_de(root)
    return Path(root) / MD_DIR / f"{nombre}{SEP}Resumen.md"


def video_path(root, video, nombre=None):
    nombre = nombre or nombre_de(root)
    return Path(root) / MD_DIR / f"{nombre}{SEP}{video}.md"


# --------------------------------------------------------------------- esqueletos

def skeleton_global(root, nombre, fecha, origen="hook", resumen=None):
    if origen == "historial":
        nota = ("Registro creado el " + fecha + " a partir del historial de sesiones: todavía no "
                "tiene resumen escrito. El contexto está en las sesiones de abajo (transcripts en "
                "`~/.claude/projects/<carpeta>/<id>.jsonl`).")
        estado = "sin resumen"
    else:
        nota = ("Registro creado por el hook de MD FILES al empezar a trabajar en el proyecto. "
                "Lo mantiene Claude con la skill `mdfilesummary`.")
        estado = "en curso"
    resumen = resumen or "(completar — una línea que sirva sola: qué es y en qué estado está)"
    return f"""---
proyecto: {nombre}
cliente: {cliente_de(root)}
carpeta: {root}
creado: {fecha}
actualizado: {fecha}
estado: {estado}
resumen: {resumen}
alias: []
---

# {nombre} — Resumen

> {nota} Acá va el estado de cada video, lo que se decidió para todo el proyecto, lo pendiente y el historial. El detalle de cada video está en su propio archivo, en esta misma carpeta.

(2–4 líneas: qué es el proyecto, qué se entrega y para quién.)

## Videos

| Video | Estado | Archivo |
|---|---|---|

## Decisiones que aplican a todo el proyecto

## Pendiente

## Archivos y fuentes

## Historial

{SESS_HEADER}
{SESS_COMMENT}
"""


def skeleton_video(vdir, nombre, video, fecha):
    return f"""---
proyecto: {nombre}
video: {video}
carpeta: {vdir}
creado: {fecha}
actualizado: {fecha}
estado: en curso
resumen: (completar — una línea: qué es este video y en qué estado está)
---

# {nombre} — {video}

> Archivo de este video. El resumen global del proyecto está en `{nombre}{SEP}Resumen.md`, en esta misma carpeta.

## Qué es
(video fuente, duración y formato, skill con la que se arma, tema o cita central)

## Estado actual

## Beats / contenido
(breve: el detalle vive en `BEATS.md` del proyecto, si existe)

## Correcciones del usuario

## Decisiones y por qué

## Pendiente

{SESS_HEADER}
{SESS_COMMENT}
"""


def write_new(path, content):
    try:
        with open(path, "x", encoding="utf-8") as f:
            f.write(content)
        return True
    except FileExistsError:
        return False


def add_video_row(gpath, video, vfile):
    try:
        text = Path(gpath).read_text(encoding="utf-8")
    except Exception:
        return
    if vfile in text:
        return
    lines = text.split("\n")
    idx = [k for k, ln in enumerate(lines) if ln.strip() == "## Videos"]
    if not idx:
        return
    i = idx[0]
    j, last = i + 1, None
    while j < len(lines) and not lines[j].startswith("## "):
        if lines[j].lstrip().startswith("|"):
            last = j
        elif last is not None and lines[j].strip() == "":
            break
        j += 1
    row = f"| {video} | en curso | `{vfile}` |"
    if last is None:
        lines[i + 1:i + 1] = ["", "| Video | Estado | Archivo |", "|---|---|---|", row]
    else:
        lines.insert(last + 1, row)
    Path(gpath).write_text("\n".join(lines), encoding="utf-8")


def ensure_registry(root, vdir=None, origen="hook", resumen=None):
    """Crea MD FILES/, el Resumen y (si hay video) su archivo. Devuelve (g, v, video, creados)."""
    root = Path(root)
    nombre = nombre_de(root)
    (root / MD_DIR).mkdir(exist_ok=True)
    recordar_proyecto(root)
    fecha = today()
    created = []
    g = global_path(root, nombre)
    if not g.exists() and write_new(g, skeleton_global(root, nombre, fecha, origen, resumen)):
        created.append(g)
    v = video = None
    if vdir is not None:
        video = video_de(vdir, nombre)
        v = video_path(root, video, nombre)
        if not v.exists() and write_new(v, skeleton_video(vdir, nombre, video, fecha)):
            created.append(v)
            add_video_row(g, video, v.name)
    return g, v, video, created


def _proyectos_conocidos():
    try:
        data = json.loads(PROYECTOS_JSON.read_text(encoding="utf-8"))
        return [x for x in data if isinstance(x, str)] if isinstance(data, list) else []
    except Exception:
        return []


def recordar_proyecto(root):
    """Anota la carpeta del proyecto en proyectos.json: el índice la revisa siempre."""
    try:
        lista = _proyectos_conocidos()
        r = str(root)
        if r in lista:
            return
        lista.append(r)
        REG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PROYECTOS_JSON.with_name(PROYECTOS_JSON.name + ".tmp")
        tmp.write_text(json.dumps(sorted(set(lista)), ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, PROYECTOS_JSON)
    except Exception as e:
        log_error("recordar_proyecto", e)


def transcript_de(sid):
    """El archivo de la sesión `sid`, en cualquier carpeta de ~/.claude/projects/."""
    if not sid:
        return None
    try:
        for d in PROJECTS_DIR.iterdir():
            f = d / f"{sid}.jsonl"
            if f.is_file():
                return f
    except OSError:
        pass
    return None


# ----------------------------------------------------------------------- sesiones

def register_session(md_path, sid, fecha, titulo, videos=()):
    """Agrega (o completa) la línea de esta sesión en `## Sesiones`. True si escribió."""
    md_path = Path(md_path)
    if not sid:
        return False
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        return False
    videos = [v for v in (videos or []) if v]
    if sid in text:
        if not videos:
            return False
        lines = text.split("\n")
        for k, ln in enumerate(lines):
            if sid in ln and ln.lstrip().startswith("- "):
                missing = [v for v in videos if v not in ln]
                if not missing:
                    return False
                if " · videos: " in ln:
                    lines[k] = ln.rstrip() + ", " + ", ".join(missing)
                else:
                    lines[k] = ln.rstrip() + " · videos: " + ", ".join(missing)
                md_path.write_text("\n".join(lines), encoding="utf-8")
                return True
        return False
    line = f"- {fecha} · {clean_line(titulo) or '(sin título)'} · `{sid}`"
    if videos:
        line += " · videos: " + ", ".join(videos)
    m = SESS_RE.search(text)
    if not m:
        text = text.rstrip("\n") + f"\n\n{SESS_HEADER}\n{SESS_COMMENT}\n{line}\n"
    else:
        nxt = re.search(r"^## ", text[m.end():], re.M)
        end = m.end() + nxt.start() if nxt else len(text)
        body = text[m.end():end].rstrip("\n")
        new = (body if body else "") + "\n" + line + "\n"
        if nxt:
            new += "\n"
        text = text[:m.end()] + new + text[end:]
    md_path.write_text(sort_sessions(text), encoding="utf-8")
    return True


def sort_sessions(text):
    """Deja las líneas de `## Sesiones` en orden de fecha (el comentario, arriba)."""
    m = SESS_RE.search(text)
    if not m:
        return text
    nxt = re.search(r"^## ", text[m.end():], re.M)
    end = m.end() + nxt.start() if nxt else len(text)
    lines = [ln for ln in text[m.end():end].split("\n") if ln.strip()]
    dated = [ln for ln in lines if re.match(r"^- \d{4}-\d{2}-\d{2}", ln)]
    other = [ln for ln in lines if ln not in dated]
    dated.sort(key=lambda ln: ln[2:12])          # sort estable: mismo día, mismo orden
    new = "\n" + "\n".join(other + dated) + "\n" + ("\n" if nxt else "")
    return text[:m.end()] + new + text[end:]


def _user_text(d):
    c = (d.get("message") or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                return b["text"]
    return ""


def _prompt_text(d):
    t = _user_text(d)
    t = re.sub(r"<([A-Za-z_-]+)[^>]*>.*?</\1>", " ", t, flags=re.S)
    return clean_line(t, 80)


def session_title(transcript_path):
    """Título que la app le puso a la sesión, o el comienzo del primer mensaje del usuario."""
    try:
        p = Path(transcript_path) if transcript_path else None
        if not p or not p.is_file():
            return ""
        size = p.stat().st_size
        with p.open("rb") as f:
            f.seek(max(0, size - 400_000))
            tail = f.read().decode("utf-8", "ignore")
        found = TITLE_RE.findall(tail)
        if found:
            return clean_line(json.loads('"' + found[-1] + '"'))
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            for k, line in enumerate(f):
                if k > 500:
                    break
                if '"type":"user"' not in line or '"tool_result"' in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("isMeta") or d.get("isSidechain"):
                    continue
                t = _prompt_text(d)
                if t:
                    return t
    except Exception as e:
        log_error("session_title", e)
    return ""


# -------------------------------------------------------------------- hook: tools

def touch_message(nombre, g, v, video, created, global_seen):
    if g in created:
        files = [q(g)] + ([q(v)] if v else [])
        return ("📁 MD FILES — Proyecto nuevo: se creó su registro: " + " y ".join(files) + ". "
                "Complétalo ahora con la skill `mdfilesummary` (qué es, qué se entrega, con qué "
                "skill o herramienta, plan) y actualízalo en cada hito: build terminado, cada "
                "ronda de correcciones, render o entrega.")
    if v is not None and v in created:
        s = (f"📁 MD FILES — Video nuevo en {nombre}: se creó {q(v)}. Complétalo con la skill "
             "`mdfilesummary`.")
        if not global_seen:
            s += f" El proyecto ya tenía registro: lee {q(g)} antes de seguir."
        return s
    if not global_seen:
        s = f"📁 MD FILES — {nombre} ya tiene registro: {q(g)}"
        if v is not None:
            s += f" y, para {video}, {q(v)}"
        return s + (". Si todavía no lo leíste en esta sesión, léelo antes de seguir: tiene el "
                    "estado, las decisiones y lo pendiente. Actualizalo en cada hito (skill "
                    "`mdfilesummary`).")
    if v is not None:
        return (f"📁 MD FILES — {video} ({nombre}) tiene su archivo: {q(v)}. Léelo si vas a "
                "trabajar en ese video.")
    return ""


def stray_md_message(path, root):
    return (f"📁 MD FILES — {q(path)} quedó fuera de MD FILES. Los MD de sesión (resúmenes, "
            f"progreso, auditorías, propuestas, specs) van en {q(Path(root) / MD_DIR)}. Si "
            "ninguna herramienta necesita leerlo desde ahí, muévelo (mv) y actualiza las "
            "referencias que apunten a la ruta vieja.")


def md_snapshot(root):
    """{nombre del .md: fecha de modificación} de MD FILES/ del proyecto."""
    d = Path(root) / MD_DIR
    out = {}
    try:
        for n in os.listdir(d):
            if n.endswith(".md") and not n.startswith("."):
                try:
                    out[n] = (d / n).stat().st_mtime
                except OSError:
                    pass
    except OSError:
        pass
    return out


def external_change_message(st, root, since=None):
    """Aviso si el registro del proyecto cambió desde la última vez que ESTA sesión lo vio: casi
    siempre lo escribió otra sesión (CLB 007, 2026-10-01: otra sesión anotó a las 22:27 que el Snippet 2
    se cortó del video 3, y esta, que había leído el Resumen a las 18:40, le preguntó al usuario lo mismo).
    Lo que escribió la herramienta actual (fecha >= since) no cuenta. Actualiza la foto."""
    rk = str(root)
    snap = md_snapshot(root)
    visto = st.setdefault("md_visto", {})
    prev = visto.get(rk)
    visto[rk] = snap
    if prev is None or not snap:
        return ""
    # lo que escribió un comando de esta misma sesión (un script, un heredoc) no es de otra sesión
    propias = st.get("bash_propias") or []
    cambiados = [n for n, m in sorted(snap.items(), key=lambda x: -x[1])
                 if m > prev.get(n, 0) + 1 and (since is None or m < since)
                 and not any(a <= m <= b for a, b in propias)]
    if not cambiados:
        return ""
    hora = datetime.fromtimestamp(max(snap[n] for n in cambiados)).strftime("%H:%M")
    archivos = ", ".join(q(Path(root) / MD_DIR / n) for n in cambiados[:4])
    return (f"📁 MD FILES — El registro de {nombre_de(root)} cambió desde que esta sesión lo vio "
            f"(último cambio {hora}): {archivos}. Si no lo escribiste tú, fue otra sesión: reléelo "
            "antes de seguir, de escribir en él o de preguntarle algo al usuario sobre el proyecto "
            "(puede que ya esté explicado ahí).")


# Un MD de estado escrito suelto («anota dónde quedamos» sin la skill): su lugar es MD FILES/. En el
# usuario de prueba (jue 19-11-2026) 3 de 3 sesiones escribieron un DONDE-QUEDAMOS.md a mano y no se creó el registro.
ESTADO_MD_RE = re.compile(
    r"(?:^|[\s_-])(?:donde[\s_-]*(?:nos[\s_-]*)?quedamos|estado|progreso|avances?|pendientes?|resumen|"
    r"bitacora|notas|apuntes|seguimiento|status|progress|notes|todo|handoff)(?:[\s_-]|$)")
# Pedidos que crean un proyecto o piden anotar su estado (sobre el texto sin tildes): el hook le recuerda a
# Claude dónde van, una vez por hora y sesión.
PISTA_REGISTRO_RE = re.compile(
    r"donde (?:nos )?quedamos|(?:crea|crear|arma|armar|empieza|empezar|haz)(?:me)? (?:un |una |el |la |mi )?"
    r"(?:proyecto|carpeta (?:del?|para el|de mi) proyecto)|proyecto nuevo|nuevo proyecto|"
    r"(?:anota|anotar|guarda|guardar|registra|registrar) (?:el |lo |en que |por donde )?"
    r"(?:estado|progreso|avance|lo que hicimos|donde|como vamos)")
PISTA_CADA_S = 3600


def pista_registro_texto():
    raices = " o ".join(str(r) for r in carpetas_config()[0]) or str(HOME / "PROYECTOS")
    cmd = f'"{sys.executable}" "{Path(__file__).resolve()}" ensure "<carpeta del proyecto>"'
    return ("📁 MD FILES — Los proyectos van en " + raices + "/<CLIENTE>/<PROYECTO>/ (si esa carpeta no existe, "
            "créala ahí: no inventes otra). El estado de un proyecto («dónde quedamos», qué se hizo, decisiones, "
            "pendientes) va en su MD FILES/ con la skill mdfilesummary: nunca en un DONDE-QUEDAMOS.md ni en otro MD "
            "suelto. Si este pedido crea la carpeta del proyecto, crea también su registro (" + cmd + ") y "
            "complétalo.")


# Archivos de prueba que arma Claude: no son entregables y no se anotan en el registro.
# Convención (2026-10-01): empiezan con "ZZ" o terminan en "-PRUEBA" / "_PRUEBA" antes de la
# extensión. "PRUEBA DE COLOR.mp4" de un cliente sí cuenta.
TEST_FILE_RE = re.compile(r"(?:^|[\s_-])ZZ[\s_-]|[-_]PRUEBA(?=\.[^.]+$)")


def is_functional_md(path):
    p = Path(path)
    low = p.name.lower()
    if low in FUNCTIONAL_MD:
        return True
    # los escribe y los lee el pipeline del shelf (process-ds-episode / process-episode)
    if "social captions" in low or "transcript cleanup" in low:
        return True
    return any("transcript" in part.lower() or part.startswith(".") for part in p.parts[:-1])


def _bash_propio(st, since):
    """Un comando de Bash puede escribir el registro sin que el hook vea la ruta (un script de Python, un
    heredoc). Se guarda la ventana del comando: un cambio del registro dentro de ella no es «de otra sesión», y si
    el proyecto tenía el registro pendiente, cuenta como actualizado (prueba del jue 19-11-2026: completar el
    Resumen con Python dio una falsa alarma y un recordatorio de más al terminar)."""
    ahora = time.time()
    ventanas = st.setdefault("bash_propias", [])
    ventanas.append([since, ahora + 1])
    del ventanas[:-40]
    for rk in list(st["dirty"]):
        snap = md_snapshot(rk)
        if any(m >= since for m in snap.values()):
            st["md_escrito"][rk] = ahora
            st["dirty"].pop(rk, None)
            if rk not in st["pendientes"]:
                st["pendientes"].append(rk)
            st["indice_sucio"] = True
            st.setdefault("md_visto", {})[rk] = snap
    return True


def handle_post_tool(data):
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    sid = data.get("session_id") or ""
    # la carpeta abierta en la sesión (la manda la app en cada hook)
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or ""
    paths, kind, cmd = [], None, ""
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        fp = ti.get("file_path") or ti.get("notebook_path") or ""
        if fp:
            paths, kind = [fp], "edit"
    elif tool == "Bash":
        cmd = ti.get("command") or ""
        paths = extract_paths(cmd)
        if cwd:
            paths.append(cwd)                            # las rutas relativas caen acá
        if INIT_RE.search(cmd):
            kind = "init"
        elif RENDER_RE.search(cmd):
            kind = "render"
        elif PREVIEW_RE.search(cmd):
            kind = "preview"
        elif WRITE_RE.search(cmd):
            kind = "bash-write"
        else:
            kind = "bash"
    paths = [p for p in dict.fromkeys(paths) if isinstance(p, str) and p.strip()]
    if not paths:
        return None

    msgs = []
    since = tool_start(data.get("duration_ms"))
    with Lock():
        st = load_state(sid)
        changed = False
        if tool == "Bash":
            changed = _bash_propio(st, since)
        vistos = set()
        for p in paths:
            path = _abs(p)
            r0, modo = find_root_modo(path, cwd)
            if not r0:
                continue
            if str(r0) not in vistos:
                vistos.add(str(r0))
                ext = external_change_message(st, r0, since)
                changed = True
                if ext:
                    msgs.append(ext)
                conocidos = st.setdefault("conocidos", [])
                if modo == "registro" and str(r0) not in conocidos:
                    conocidos.append(str(r0))
                    recordar_proyecto(r0)
            if MD_DIR in path.parts:                         # escribieron en el registro
                root = r0
                # WRITE_RE se equivoca (el `>` de un grep cuenta como redirección): se confirma
                # mirando si el archivo cambió de verdad
                if root and (kind == "edit" or (kind == "bash-write" and wrote_md(path, since))):
                    rk = str(root)
                    st["md_escrito"][rk] = time.time()
                    st["dirty"].pop(rk, None)
                    if rk not in st["pendientes"]:
                        st["pendientes"].append(rk)
                    st["indice_sucio"] = changed = True
                continue
            root = r0
            if (tool in ("Write", "Edit", "MultiEdit") and path.suffix.lower() == ".md"
                    and not is_functional_md(path)):
                if (root / MD_DIR).is_dir():
                    msgs.append(stray_md_message(path, root))
                elif modo != "abierta" and ESTADO_MD_RE.search(fold(path.stem)):
                    # «anota dónde quedamos» escrito a mano en la carpeta de un proyecto: se crea su registro
                    changed = _touch_project(st, data, sid, root, [path], msgs,
                                             "estado del proyecto") or changed
                    msgs.append(stray_md_message(path, root))
            vdirs, copiados = [], False
            vdir = find_video_dir(path, root)
            if vdir is not None:
                vdirs = [vdir]
            elif kind in ("init", "bash-write") and path.is_dir() and (
                    path.name.upper() == "HYPERFRAMES" or path.name.upper().endswith("ANIMATIONS")):
                # proyecto armado en el disco interno y copiado a la carpeta contenedora: solo
                # los videos que este comando escribió (rsync -a deja nueva la fecha de creación)
                copiados = True
                for child in sorted(_listdir(str(path))):
                    c = path / child
                    if is_video_dir(c) and wrote_in_video(c, since):
                        vdirs.append(c)
            for vdir in vdirs:
                k = kind
                if kind in ("bash", "bash-write") and not copiados:
                    # Bash cuenta como trabajo solo si dejó cambios en el video: un grep, un
                    # ffprobe o un gate que mide no crea ni anota nada (auditoría del 2026-10-01)
                    k = "bash-write" if wrote_in_video(vdir, since) else None
                if k:
                    changed = _touch_video(st, data, sid, k, root, vdir, msgs) or changed
                else:
                    changed = _peek_video(st, root, vdir, msgs) or changed
            if not vdirs and is_video_dir(root):
                # la carpeta del proyecto es el propio video de HyperFrames (index.html al lado)
                k = kind
                if kind in ("bash", "bash-write"):
                    k = "bash-write" if wrote_in_video(root, since) else None
                motivo = {"init": "creación", "render": "render", "edit": "edición",
                          "bash-write": "edición"}.get(k)
                if k == "preview" and str(root) in st["dirty"]:
                    motivo = "build terminado (Studio abierto)"
                if motivo:
                    changed = _touch_project(st, data, sid, root, [path], msgs,
                                             motivo) or changed
            elif not vdirs:
                # proyecto sin HyperFrames (Premiere, Resolve, entrega...): se activa cuando se
                # escribe un entregable en la carpeta del proyecto. En una carpeta abierta sin
                # plantilla ni registro cuentan solo video, audio, subtítulos y líneas de tiempo.
                files = recent_deliverables(tool, path, root, since,
                                            solo_media=(modo == "abierta"))
                if files:
                    changed = _touch_project(st, data, sid, root, files, msgs) or changed
            if modo == "registro":
                changed = _peek_project(st, root, msgs) or changed
        if changed:
            save_state(sid, st)
    msgs = [m for m in dict.fromkeys(msgs) if m]
    if not msgs:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "additionalContext": "\n\n".join(msgs)}}


# Lo que se considera un entregable escrito en la carpeta de un proyecto.
DELIVERABLE_EXT = {".srt", ".vtt", ".ass", ".scc", ".txt", ".mp4", ".mov", ".m4v", ".mxf",
                   ".wav", ".mp3", ".aac", ".m4a", ".png", ".jpg", ".jpeg", ".gif", ".xml",
                   ".fcpxml", ".edl", ".aaf", ".prproj", ".pdf"}
DELIVERABLE_SUBDIRS = ("RENDERS", "GRAFICA", "AUDIO RENDERS", "EXTRA", "PREMIERE")


def _is_deliverable(p):
    p = Path(p)
    return (p.suffix.lower() in DELIVERABLE_EXT and not p.name.startswith(".")
            and not TEST_FILE_RE.search(p.name)
            and MD_DIR not in p.parts and not any("auto-save" in x.lower() for x in p.parts))


def tool_start(duration_ms):
    """Cuándo empezó la herramienta (sin el dato, hace un minuto). El margen de 2 s cubre la
    demora hasta que corre el hook; exFAT guarda las fechas al centésimo de segundo. Más margen
    haría pasar por escritura de este comando lo que se escribió justo antes."""
    try:
        dur = float(duration_ms) / 1000 if duration_ms else 60
    except (TypeError, ValueError):
        dur = 60
    return time.time() - dur - 2


def _changed_since(p, since):
    """Modificación, cambio o creación desde `since`. Leer no toca ninguna de las tres, y una
    copia que conserva la fecha vieja (cp -p, rsync -a, ditto) igual deja nueva la de creación
    (medido en exFAT, el formato de DISCO y DISCO2)."""
    st = Path(p).stat()
    return max(st.st_mtime, st.st_ctime, getattr(st, "st_birthtime", 0)) >= since


def wrote_in_video(vdir, since):
    """¿El comando dejó cambios en el video? Mira los archivos y subcarpetas de nivel 1 y 2,
    salvo lo que dejan los gates y el Studio (carpetas ocultas, snapshots/)."""
    vdir = Path(vdir)
    try:
        names = os.listdir(vdir)
    except OSError:
        return False
    for name in names:
        if name.startswith(".") or name in SKIP_PARTS or name in QA_DIRS:
            continue
        p = vdir / name
        try:
            if _changed_since(p, since):
                return True
            kids = os.listdir(p) if p.is_dir() else []
        except OSError:
            continue
        for k in kids[:400]:
            try:
                if not k.startswith(".") and _changed_since(p / k, since):
                    return True
            except OSError:
                pass
    return False


def wrote_md(path, since):
    """¿El comando escribió en MD FILES? El archivo nombrado o su carpeta (un mv deja el
    archivo con sus fechas viejas, pero cambia la de la carpeta)."""
    p = Path(path)
    try:
        if p.is_file() and _changed_since(p, since):
            return True
        return _changed_since(p if p.is_dir() else p.parent, since)
    except OSError:
        return False


def recent_deliverables(tool, path, root, since, solo_media=False):
    """Entregables que esta herramienta acaba de escribir en la carpeta del proyecto."""
    path = Path(path)
    if solo_media:
        def ok(c):
            return _is_deliverable(c) and c.suffix.lower() in MEDIA_EXT
    else:
        ok = _is_deliverable
    if tool in ("Write", "Edit", "MultiEdit"):
        return [path] if ok(path) else []
    candidates = []
    if path.is_file():
        candidates = [path]
    elif path.is_dir():
        dirs = [path] + ([path / s for s in DELIVERABLE_SUBDIRS if (path / s).is_dir()]
                         if path == root else [])
        for d in dirs:
            names = sorted(_listdir(str(d)))[:400]
            candidates += [d / n for n in names]
    out = []
    for c in candidates:
        try:
            if ok(c) and c.is_file() and c.stat().st_mtime >= since:
                out.append(c)
        except OSError:
            pass
    return out


def _touch_project(st, data, sid, root, files, msgs, motivo=None):
    """Proyecto sin videos de HyperFrames adentro: crea el Resumen si falta, anota la sesión y
    marca el hito."""
    g, _, _, created = ensure_registry(root, None)
    rk, gk = str(root), str(g)
    if gk not in st["registrados"]:
        title = session_title(data.get("transcript_path"))
        register_session(g, sid, today(), title)
        msg = touch_message(nombre_de(root), g, None, None, created, False)
        if msg:
            msgs.append(msg)
        st["registrados"].append(gk)
        if rk not in st["anunciados"]:
            st["anunciados"].append(rk)
        st["indice_sucio"] = True
    names = ", ".join(sorted({Path(f).name for f in files})[:3])
    if created:
        motivo = "creación"
    elif not motivo:
        motivo = clean_line(f"entregable: {names}", 120)
    d = st["dirty"].setdefault(rk, {"videos": [], "motivos": [], "archivos": []})
    for lst, val in ((d["motivos"], motivo), (d["archivos"], gk)):
        if val not in lst:
            lst.append(val)
    return True


def _touch_video(st, data, sid, kind, root, vdir, msgs):
    """Registra un video tocado: crea lo que falte, anota la sesión y marca el hito."""
    g, v, video, created = ensure_registry(root, vdir)
    rk, gk, vk = str(root), str(g), str(v)
    global_seen = gk in st["registrados"]
    if vk not in st["registrados"]:
        title = session_title(data.get("transcript_path"))
        register_session(g, sid, today(), title, [video])
        register_session(v, sid, today(), title)
        msg = touch_message(nombre_de(root), g, v, video, created, global_seen)
        if msg:
            msgs.append(msg)
        st["registrados"] += [x for x in (gk, vk) if x not in st["registrados"]]
        if rk not in st["anunciados"]:
            st["anunciados"].append(rk)
        st["indice_sucio"] = True
    motivo = None
    if kind == "init" or created:
        motivo = "creación"
    elif kind == "render":
        motivo = "render"
    elif kind in ("edit", "bash-write"):
        motivo = "edición"
    elif kind == "preview" and rk in st["dirty"]:
        motivo = "build terminado (Studio abierto)"
    if motivo:
        d = st["dirty"].setdefault(rk, {"videos": [], "motivos": [], "archivos": []})
        for lst, val in ((d["videos"], video), (d["motivos"], motivo),
                         (d["archivos"], gk), (d["archivos"], vk)):
            if val and val not in lst:
                lst.append(val)
    return True


def _peek_project(st, root, msgs):
    """La sesión trabaja en un proyecto que ya tiene registro: lo avisa una vez por sesión, para
    que se lea antes de seguir (sin crear ni anotar nada)."""
    rk = str(root)
    if rk in st["anunciados"]:
        return False
    nombre = nombre_de(root)
    g = global_path(root, nombre)
    if not g.is_file():
        return False
    msgs.append(touch_message(nombre, g, None, None, [], False))
    st["anunciados"].append(rk)
    return True


def _peek_video(st, root, vdir, msgs):
    """Bash que solo leyó un video: no crea ni anota nada. Si el proyecto ya tiene registro,
    lo avisa una vez por sesión, para que se lea antes de trabajar."""
    rk = str(root)
    if rk in st["anunciados"]:
        return False
    nombre = nombre_de(root)
    g = global_path(root, nombre)
    if not g.is_file():
        return False
    video = video_de(vdir, nombre)
    v = video_path(root, video, nombre)
    msgs.append(touch_message(nombre, g, v if v.is_file() else None, video, [], False))
    st["anunciados"].append(rk)
    return True


# --------------------------------------------------------------------- hook: stop

def build_reminder(st):
    dirty = st.get("dirty") or {}
    if not dirty:
        return ""
    now_ts = time.time()
    due = []
    for rk in list(dirty.keys()):
        info = dirty[rk]
        motivos = info.get("motivos") or []
        milestone = any(m == "creación" or m == "render" or m.startswith("build")
                        for m in motivos)
        last = (st.get("md_escrito") or {}).get(rk, 0)
        if not milestone and last and now_ts - last < THROTTLE_S:
            continue                      # se actualizó hace poco: se recuerda más adelante
        due.append((rk, info))
        del dirty[rk]
    if not due:
        return ""
    lines = ["📁 MD FILES — Hito: hubo cambios en un proyecto y su registro todavía no los tiene."]
    for rk, info in due:
        nombre = nombre_de(Path(rk))
        vids = ", ".join(info.get("videos") or []) or "archivos del proyecto"
        mot = ", ".join(info.get("motivos") or []) or "edición"
        lines.append(f"- {nombre} · {vids} · {mot}")
        for a in info.get("archivos") or [str(global_path(Path(rk), nombre))]:
            lines.append(f"  actualizar: {q(a)}")
    lines.append(
        "Antes de terminar, actualízalos con la skill `mdfilesummary`: qué pidió el usuario, qué se "
        "hizo y qué queda pendiente. Si fue un ajuste chico, basta una línea en «Correcciones "
        "del usuario» del video y otra en «Historial» del Resumen; si el proyecto recién se creó, "
        "completa el esqueleto. Después cierra con una sola línea (\"Registro actualizado.\"), "
        "sin repetirle al usuario lo que ya le dijiste.")
    return "\n".join(lines)


def handle_stop(data):
    sid = data.get("session_id") or ""
    out = None
    with Lock():
        st = load_state(sid)
        if not data.get("stop_hook_active") and not data.get("background_tasks"):
            msg = build_reminder(st)
            if msg:
                out = {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": msg}}
        if out is None and st.get("pendientes"):
            title = session_title(data.get("transcript_path"))
            for rk in st["pendientes"]:
                g = global_path(Path(rk))
                if g.exists():
                    register_session(g, sid, today(), title)
            st["pendientes"] = []
            st["indice_sucio"] = True
        if st.get("indice_sucio"):
            try:
                build_index()
                st["indice_sucio"] = False
            except Exception as e:
                log_error("build_index", e)
        save_state(sid, st)
    return out


def run_stop(data):
    # El sonido de fin de turno NO vive acá: es otro comando del hook Stop (hooks.json del
    # plugin), para que suene siempre, pase lo que pase con este script.
    try:
        out = handle_stop(data)
        if out:
            emit(out)
    except Exception as e:
        log_error("stop", e)
    return 0


# ------------------------------------------------------------------------- índice

def parse_frontmatter(text):
    m = FM_RE.match(text or "")
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([^:\s][^:]*):\s*(.*)$", line)
        if mm:
            out[mm.group(1).strip()] = mm.group(2).strip()
    al = out.get("alias", "")
    if al.startswith("["):
        out["alias"] = [a.strip().strip("\"'") for a in al.strip("[]").split(",") if a.strip()]
    else:
        out["alias"] = [al] if al else []
    return out


def first_heading(text):
    for line in (text or "").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def count_sessions(text):
    m = SESS_RE.search(text or "")
    if not m:
        return 0, ""
    sec = text[m.end():]
    nxt = re.search(r"^## ", sec, re.M)
    if nxt:
        sec = sec[:nxt.start()]
    dates = re.findall(r"^- (\d{4}-\d{2}-\d{2})", sec, re.M)
    return len(dates), (max(dates) if dates else "")


# Carpetas que no se recorren buscando MD FILES (pesadas o del sistema).
PRUNE_DIRS = SKIP_PARTS | {"Library", "AppData", "Applications", "Backups.backupdb",
                           "venv", ".venv", "__pycache__", "dist", "build", "Pods",
                           "DerivedData", "Caches", "cache"}


def find_md_dirs(base, max_depth=4, deadline=None):
    """Carpetas MD FILES debajo de `base`, hasta `max_depth` niveles. (lista, completo)."""
    base = Path(base)
    out = []
    if not base.is_dir():
        return out, False
    stack = [(str(base), 0)]
    while stack:
        if deadline and time.time() > deadline:
            return out, False
        d, depth = stack.pop()
        try:
            with os.scandir(d) as it:
                kids = list(it)
        except OSError:
            continue
        for k in kids:
            try:
                if not k.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if k.name == MD_DIR:
                out.append(Path(k.path))
            elif (not k.name.startswith(".") and k.name not in PRUNE_DIRS
                  and depth + 1 < max_depth):
                stack.append((k.path, depth + 1))
    return out, True


def scan_project(md_dir):
    md_dir = Path(md_dir)
    root = md_dir.parent
    nombre = nombre_de(root)
    gname = f"{nombre}{SEP}Resumen.md"
    files, videos, fm, g = [], [], {}, None
    sess_n, sess_last = 0, ""
    try:
        names = sorted(n for n in os.listdir(md_dir)
                       if n.lower().endswith(".md") and not n.startswith("."))
    except Exception:
        names = []
    for n in names:
        p = md_dir / n
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")
        except Exception:
            continue
        files.append({"nombre": n, "titulo": clean_line(first_heading(text) or n[:-3], 110),
                      "modificado": mtime})
        if n == gname:
            g, fm = p, parse_frontmatter(text)
            sess_n, sess_last = count_sessions(text)
        elif n.startswith(nombre + SEP):
            videos.append(n[len(nombre + SEP):-3])
    resumen = fm.get("resumen", "")
    if resumen.startswith("(completar"):
        resumen = "(el Resumen todavía no está completado)"
    if not resumen and files:
        latest = max(files, key=lambda f: f["modificado"])
        resumen = f"(sin Resumen — el archivo más reciente es: {latest['titulo']})"
    code, ep = codigo_ep(nombre)
    return {
        "nombre": nombre, "cliente": fm.get("cliente") or cliente_de(root),
        "codigo": code, "episodio": ep, "raiz": str(root), "md_dir": str(md_dir),
        "volumen": volumen_de(root), "global": str(g) if g else None, "resumen": resumen,
        "estado": fm.get("estado") or "—",
        "actualizado": fm.get("actualizado") or max((f["modificado"] for f in files), default=""),
        "alias": fm.get("alias") or [], "videos": videos, "archivos": files,
        "sesiones": {"n": sess_n, "ultima": sess_last},
    }


def render_index_md(entries):
    out = ["# Índice de MD FILES", "",
           f"_Lo regenera solo el hook de MD FILES (skill `mdfilesummary`). Última "
           f"actualización: {now():%Y-%m-%d %H:%M}._", "",
           "Cada proyecto guarda su historia en su carpeta `MD FILES/`. Para retomar uno: abrir su "
           "**Resumen** y después el archivo del video. *Desconectado* = está en un disco que no "
           "estaba enchufado la última vez que se armó el índice.", ""]
    cliente = None
    sin = [e for e in entries if e.get("sin_registro")]
    entries = [e for e in entries if not e.get("sin_registro")]
    for e in entries:
        if e.get("cliente") != cliente:
            cliente = e.get("cliente")
            out += [f"## {cliente or 'Sin cliente'}", ""]
        head = f"### {e['nombre']} · {e.get('estado') or '—'} · actualizado {e.get('actualizado') or '—'}"
        if e.get("desconectado"):
            head += " · *desconectado*"
        out.append(head)
        if e.get("resumen"):
            out.append(e["resumen"])
        if e.get("alias"):
            out.append("Alias: " + ", ".join(e["alias"]))
        out.append(f"`{e['md_dir']}`")
        gname = Path(e["global"]).name if e.get("global") else None
        for f in e.get("archivos") or []:
            mark = " **(Resumen)**" if f["nombre"] == gname else ""
            out.append(f"- {f['nombre']}{mark} — {f['titulo']} ({f['modificado']})")
        s = e.get("sesiones") or {}
        if s.get("n"):
            out.append(f"- Sesiones registradas: {s['n']} (última {s.get('ultima') or '—'})")
        out.append("")
    if sin:
        out += ["## Sesiones de proyectos sin registro", "",
                "Proyectos que alguna sesión tocó pero que no tienen `MD FILES/`. No se creó "
                "nada en sus carpetas: el contexto está en el transcript de cada sesión "
                "(`~/.claude/projects/<carpeta>/<id>.jsonl`).", ""]
        for e in sin:
            out.append(f"### {e['nombre']} · {e.get('cliente') or '—'}")
            out.append(f"`{e['raiz']}`")
            for ses in e.get("sesiones_detalle") or []:
                out.append(f"- {ses.get('fecha')} · {ses.get('titulo')} · `{ses.get('sid')}`")
            out.append("")
    return "\n".join(out)


def build_index():
    """Arma INDICE.md con: lo que hay en las carpetas de proyectos declaradas (o ~/PROYECTOS),
    los proyectos que ya tienen registro (proyectos.json) y lo que estaba en el índice anterior.
    Un proyecto de un disco desconectado se conserva marcado; uno borrado sale del índice."""
    prev = load_index_entries()
    prev_md = {e.get("md_dir"): e for e in prev if e.get("md_dir")}
    deadline = time.time() + 12
    candidatos = []
    for r in carpetas_config()[0]:
        candidatos += find_md_dirs(r, 4, deadline)[0]
    candidatos += [Path(r) / MD_DIR for r in _proyectos_conocidos()]
    candidatos += [Path(k) for k in prev_md]
    entries, vistos = [], set()
    for d in candidatos:
        key = _norm(d)
        if key in vistos:
            continue
        vistos.add(key)
        try:
            if d.is_dir():
                if no_es_proyecto_nunca(d) or es_contenedor(d.parent):
                    continue
                entries.append(scan_project(d))
            elif not conectado(d) and str(d) in prev_md:
                e = dict(prev_md[str(d)])
                e["desconectado"] = True
                entries.append(e)
            # disco conectado y sin la carpeta: el proyecto se borró o se movió
        except Exception as e:
            log_error("scan_project", e)
    con_registro = {e.get("raiz") for e in entries}
    try:
        extra = json.loads(SIN_REGISTRO_JSON.read_text(encoding="utf-8"))
    except Exception:
        extra = []
    for x in extra:                              # sesiones viejas de proyectos sin MD FILES
        if x.get("raiz") in con_registro:
            continue
        ses = x.get("sesiones") or []
        temas = "; ".join(dict.fromkeys(s.get("titulo", "") for s in ses))
        entries.append({
            "nombre": x.get("nombre"), "cliente": x.get("cliente"), "raiz": x.get("raiz"),
            "md_dir": None, "volumen": x.get("volumen"), "global": None, "sin_registro": True,
            "codigo": codigo_ep(x.get("nombre"))[0], "episodio": codigo_ep(x.get("nombre"))[1],
            "resumen": clean_line("Sin MD FILES. Sesiones: " + temas, 240), "estado": "sin registro",
            "actualizado": max((s.get("fecha", "") for s in ses), default=""), "alias": [],
            "videos": [], "archivos": [], "sesiones": {"n": len(ses), "ultima": max(
                (s.get("fecha", "") for s in ses), default="")}, "sesiones_detalle": ses})
    entries.sort(key=lambda e: (bool(e.get("sin_registro")), fold(e.get("cliente") or ""),
                                fold(e.get("nombre") or "")))
    REG_DIR.mkdir(parents=True, exist_ok=True)
    data = {"generado": now().isoformat(timespec="seconds"), "proyectos": entries}
    for target, content in ((INDEX_JSON, json.dumps(data, ensure_ascii=False, indent=1)),
                            (INDEX_MD, render_index_md(entries))):
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)
    return entries


def load_index_entries():
    try:
        return json.loads(INDEX_JSON.read_text(encoding="utf-8")).get("proyectos", [])
    except Exception:
        return []


# ------------------------------------------------------------------ hook: prompt

def auto_alias(e):
    if e.get("codigo"):
        return []
    n = re.sub(r"^\d{1,2}-\d{1,2}\s+", "", e.get("nombre") or "")   # "09-18 CAMPAÑA..." -> "CAMPAÑA..."
    return [n] if len(n) >= 4 else []


def match_entries(text, entries):
    t = fold(text)
    keys = {(m.group(1).upper(), int(m.group(2))) for m in CODE_RE.finditer(text or "")}
    hits = []
    for e in entries:
        score = 0
        code, ep = codigo_ep(e.get("nombre"))
        if code and (code, int(ep)) in keys:
            score = 3
        else:
            for a in list(e.get("alias") or []) + auto_alias(e):
                fa = fold(a).strip()
                if len(fa) >= 4 and re.search(r"(?<![a-z0-9])" + re.escape(fa) + r"(?![a-z0-9])", t):
                    score = 2
                    break
        if score:
            hits.append((score, e.get("actualizado") or "", e))
    hits.sort(key=lambda h: (h[0], h[1]), reverse=True)
    return [h[2] for h in hits[:4]]


def describe_entry(e):
    if e.get("sin_registro"):
        lines = [f"- {e['nombre']}: no tiene MD FILES, pero estas sesiones lo tocaron "
                 f"(transcripts en `~/.claude/projects/<carpeta>/<id>.jsonl`):"]
        for ses in (e.get("sesiones_detalle") or [])[-6:]:
            lines.append(f"  {ses.get('fecha')} · {ses.get('titulo')} · `{ses.get('sid')}`")
        return lines
    lines = [f"- {e['nombre']} ({e.get('estado') or '—'} · actualizado "
             f"{e.get('actualizado') or '—'}): {e.get('resumen') or '(sin resumen)'}"]
    if e.get("global"):
        lines.append(f"  Resumen: {q(e['global'])}")
    else:
        lines.append(f"  Todavía sin Resumen; archivos en {q(e['md_dir'])}")
    if e.get("videos"):
        lines.append("  Videos con archivo propio: " + ", ".join(e["videos"]))
    gname = Path(e["global"]).name if e.get("global") else None
    vnames = {f"{e['nombre']}{SEP}{v}.md" for v in e.get("videos") or []}
    otros = [f["nombre"] for f in e.get("archivos") or [] if f["nombre"] not in vnames | {gname}]
    if otros:
        s = ", ".join(otros)
        lines.append("  Anexos: " + (s[:400] + "…" if len(s) > 400 else s))
    if e.get("desconectado") or not conectado(e.get("raiz") or ""):
        lines.append(f"  ⚠️ El disco «{e.get('volumen') or volumen_de(e.get('raiz') or '')}» no "
                     "está conectado: hasta que se conecte solo está disponible esta línea.")
    return lines


# Pedidos que trabajan con el material del proyecto: para estos no basta con hojear el Resumen.
TAREA_CON_MATERIAL_RE = re.compile(
    r"deliver|entreg|sub[iíe]|upload|drive|render|export|caption|subtit|srt|qc\b|auditor"
    r"|thumbnail|miniatura|handoff|publica|youtube|transcri|guia|guide")


def handle_prompt(data):
    prompt = (data.get("prompt") or "")[:6000]
    sid = data.get("session_id") or ""
    if not prompt.strip():
        return None
    # avisos internos de la app (agentes en segundo plano, recordatorios): no los escribió el usuario
    if re.search(r"<task-notification>|\[SYSTEM NOTIFICATION|<system-reminder>", prompt[:600]):
        return None
    pista = PISTA_REGISTRO_RE.search(fold(prompt)) is not None
    entries = load_index_entries()
    hits = match_entries(prompt, entries) if entries else []
    if not hits and not pista:
        return None
    with Lock():
        st = load_state(sid)
        dar_pista = pista and time.time() - st.get("pista_registro", 0) > PISTA_CADA_S
        if dar_pista:
            st["pista_registro"] = time.time()
        new = [e for e in hits if e.get("raiz") not in st["anunciados"]]
        ext = []
        for e in hits:
            if e.get("raiz") and Path(e["raiz"]).is_dir():
                m = external_change_message(st, Path(e["raiz"]))
                if m:
                    ext.append(m)
        st["anunciados"] += [e["raiz"] for e in new]
        save_state(sid, st)
    extra = [pista_registro_texto()] if dar_pista else []
    if not new:
        if not ext and not extra:
            return None
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                       "additionalContext": "\n\n".join(ext + extra)}}
    lines = ext + ["📁 MD FILES — el usuario nombró proyecto(s) con historial:"]
    for e in new:
        lines += describe_entry(e)
    lines.append("Si pregunta por trabajo ya hecho o pide seguir alguno de estos proyectos, lee "
                 "primero su Resumen (y el archivo del video que nombre) antes de responder o "
                 "tocar nada; si no tiene Resumen, busca en esas sesiones. Si solo lo menciona "
                 "de pasada, no hace falta.")
    if TAREA_CON_MATERIAL_RE.search(fold(prompt)):
        lines.append("⚠️ Este pedido usa los videos o documentos del proyecto (entrega, delivery "
                     "page, subida, render, captions, QC, thumbnails, handoff…): lee COMPLETOS el "
                     "Resumen, el archivo de CADA video y los anexos antes de empezar. La tabla y "
                     "el «Pendiente» pueden estar viejos: si algo no cierra (cuántos videos van, "
                     "qué toma se usó, un video \"sin editar\", un doc que falta), resuélvelo con "
                     "el registro y las sesiones de su lista «Sesiones» (search_session_transcripts) "
                     "antes de preguntarle al usuario; pregunta solo lo que no esté en ningún lado, y "
                     "corrige el registro con lo que encuentres.")
    if extra:
        lines += [""] + extra
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                   "additionalContext": "\n".join(lines)}}


# ----------------------------------------------------------------------- backfill

def iter_tool_uses(path):
    meta = {"inicio": None, "titulo": "", "primer_prompt": "", "cwd": ""}
    uses = []
    try:
        with Path(path).open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if meta["inicio"] is None:
                    m = re.search(r'"timestamp":"([^"]+)"', line)
                    if m:
                        meta["inicio"] = m.group(1)
                if not meta["cwd"]:
                    m = re.search(r'"cwd":"((?:[^"\\]|\\.)*)"', line)
                    if m:
                        try:
                            meta["cwd"] = json.loads('"' + m.group(1) + '"')
                        except Exception:
                            pass
                if '"customTitle"' in line:
                    m = TITLE_RE.search(line)
                    if m:
                        try:
                            meta["titulo"] = json.loads('"' + m.group(1) + '"')
                        except Exception:
                            pass
                    continue
                if (not meta["primer_prompt"] and '"type":"user"' in line
                        and '"tool_result"' not in line):
                    try:
                        d = json.loads(line)
                        if not d.get("isMeta") and not d.get("isSidechain"):
                            meta["primer_prompt"] = _prompt_text(d)
                    except Exception:
                        pass
                if '"tool_use"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                for b in (d.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        uses.append((b.get("name") or "", b.get("input") or {}))
    except Exception as e:
        log_error("iter_tool_uses", e)
    return meta, uses


def classify(name, inp):
    if not isinstance(inp, dict):
        return []
    if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        p = inp.get("file_path") or inp.get("notebook_path")
        return [(p, "fuerte")] if p else []
    if name == "Read":
        p = inp.get("file_path")
        return [(p, "debil")] if p else []
    if name == "Bash":
        cmd = inp.get("command") or ""
        strong = bool(HFCLI_RE.search(cmd) or WRITE_RE.search(cmd))
        return [(p, "fuerte" if strong else "debil") for p in extract_paths(cmd)]
    return []


SIN_REGISTRO_JSON = REG_DIR / "sesiones-sin-registro.json"


def backfill(apply=False, excluir=()):
    """Vincula cada sesión guardada con los proyectos que tocó.

    Solo escribe en proyectos que YA tienen MD FILES. Los demás (con estructura de proyecto)
    quedan listados en el índice, en "Sesiones de proyectos sin registro", sin crear carpetas.
    """
    plan, modos = {}, {}
    files = []
    try:
        for d in sorted(PROJECTS_DIR.iterdir()):
            if d.is_dir():
                files += sorted(d.glob("*.jsonl"))
    except OSError:
        pass
    for f in files:
        sid = f.stem
        if sid in excluir:
            continue
        meta, uses = iter_tool_uses(f)
        sub = f.parent / sid / "subagents"
        if sub.is_dir():
            for sf in sorted(sub.glob("*.jsonl")):
                uses += iter_tool_uses(sf)[1]
        per_root = {}
        for name, inp in uses:
            for p, strength in classify(name, inp):
                if not isinstance(p, str) or not p.strip():
                    continue
                root, modo = find_root_modo(p, meta.get("cwd") or None)
                if not root:
                    continue
                modos[str(root)] = modo
                r = per_root.setdefault(str(root), {"fuerte": 0, "debil": 0, "videos": set()})
                r[strength] += 1
                vd = find_video_dir(Path(p), root)
                if vd is not None and strength == "fuerte":
                    r["videos"].add(video_de(vd, nombre_de(root)))
        fecha = local_date(meta["inicio"])
        titulo = clean_line(meta["titulo"] or meta["primer_prompt"] or "(sin título)")
        for rk, r in per_root.items():
            if r["fuerte"] >= 1 or r["debil"] >= 3:
                plan.setdefault(rk, []).append({
                    "sid": sid, "fecha": fecha,
                    "titulo": titulo + ("" if r["fuerte"] else " (solo consulta)"),
                    "videos": sorted(r["videos"]), "fuerte": r["fuerte"], "debil": r["debil"]})
    for rk in plan:
        plan[rk].sort(key=lambda s: (s["fecha"], s["sid"]))
    if apply:
        sin_registro = []
        for rk, sessions in sorted(plan.items()):
            root = Path(rk)
            if not (root / MD_DIR).is_dir():
                if modos.get(rk) in ("plantilla", "raiz"):
                    sin_registro.append({"nombre": nombre_de(root), "raiz": rk,
                                         "cliente": cliente_de(root),
                                         "volumen": volumen_de(root),
                                         "sesiones": sessions})
                continue
            g, _, _, _ = ensure_registry(root, None)
            for s in sessions:
                register_session(g, s["sid"], s["fecha"], s["titulo"], s["videos"])
        REG_DIR.mkdir(parents=True, exist_ok=True)
        SIN_REGISTRO_JSON.write_text(json.dumps(sin_registro, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
        build_index()
    return plan


# --------------------------------------------------------------------------- main

def emit(obj):
    """Respuesta del hook por stdout, siempre en UTF-8 (en Windows la consola no lo es)."""
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    except AttributeError:
        sys.stdout.write(data.decode("utf-8"))


def main(argv):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd in ("post-tool", "prompt", "stop"):
        try:
            raw = sys.stdin.buffer.read().decode("utf-8", "replace")
            data = json.loads(raw) if raw.strip() else {}
        except Exception as e:
            log_error(cmd + ":stdin", e)
            data = {}
        if cmd == "stop":
            return run_stop(data)
        try:
            out = handle_post_tool(data) if cmd == "post-tool" else handle_prompt(data)
            if out:
                emit(out)
        except Exception as e:
            log_error(cmd, e)
        return 0
    if cmd == "indice":
        entries = build_index()
        print(f"Índice regenerado: {len(entries)} proyectos → {INDEX_MD}")
        return 0
    if cmd == "buscar":
        text = " ".join(argv[2:])
        entries = load_index_entries() or build_index()
        hits = match_entries(text, entries)
        if not hits:
            print(f"Nada en el índice coincide con: {text}")
        for e in hits:
            print("\n".join(describe_entry(e)))
        return 0
    if cmd == "donde":
        args = argv[2:]
        cwd = None
        if "--cwd" in args:
            i = args.index("--cwd")
            cwd = args[i + 1] if i + 1 < len(args) else None
            args = args[:i] + args[i + 2:]
        for p in args:
            root, modo = find_root_modo(p, cwd)
            if root:
                print(f"{p}\n  proyecto: {root}\n  cómo se eligió: {modo}")
            else:
                print(f"{p}\n  ningún proyecto: {modo}")
        return 0
    if cmd == "ensure":
        sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
        for p in argv[2:]:
            path = _abs(p)
            # la ruta que se nombra a mano vale como carpeta abierta
            root, modo = find_root_modo(path, path if path.is_dir() else path.parent)
            if not root:
                print(f"No creé nada para {p}: {modo}.")
                continue
            vdir = find_video_dir(path, root)
            g, v, video, created = ensure_registry(root, vdir)
            if sid:
                title = session_title(transcript_de(sid))
                register_session(g, sid, today(), title, [video] if video else [])
                if v is not None:
                    register_session(v, sid, today(), title)
            for f in (g, v):
                if f is not None:
                    print(("creado:    " if f in created else "ya estaba: ") + str(f))
        build_index()
        return 0
    if cmd == "backfill":
        apply = "--aplicar" in argv
        # la sesión actual la registra el hook (o `ensure`), no el backfill
        plan = backfill(apply=apply, excluir={os.environ.get("CLAUDE_CODE_SESSION_ID", "")})
        for rk, sessions in sorted(plan.items()):
            print(f"\n{nombre_de(Path(rk))}  ({rk})")
            for s in sessions:
                vids = (" · videos: " + ", ".join(s["videos"])) if s["videos"] else ""
                print(f"  {s['fecha']} · {s['titulo']} · {s['sid'][:8]} "
                      f"[{s['fuerte']}f/{s['debil']}d]{vids}")
        total = sum(len(s) for s in plan.values())
        print(f"\n{len(plan)} proyectos, {total} vínculos sesión→proyecto"
              + (" — APLICADO" if apply else " — simulación (agregar --aplicar para escribir)"))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except SystemExit:
        raise
    except Exception as exc:
        log_error("main", exc)
        sys.exit(0)
