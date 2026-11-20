#!/usr/bin/env python3
"""Respaldo de lo de Claude -> GitHub (repo PRIVADO `claude-respaldo` en la cuenta de quien lo usa).
Skill `respaldar` del plugin creativos-base. Mac y Windows (Windows: pendiente de prueba).

Qué guarda (en ~/respaldo-claude/claude-respaldo, y de ahí a GitHub):
  claude/      espejo de ~/.claude: CLAUDE.md, ajustes (sin claves), skills propias, hooks, comandos, agentes,
               registro de proyectos. Sin lo que se regenera solo (cachés, logs, sesiones, entornos de Python,
               plugins: se reinstalan desde su marketplace) ni las skills viejas de la versión 1.
  config/      conexiones (MCP) de Claude Code y de la app de escritorio, con las claves tapadas.
  proyectos/   de cada proyecto en ~/PROYECTOS: MD FILES/, HYPERFRAMES/ (sin videos ni audios) y los CLAUDE.md.
  sistema/     ~/MI-SISTEMA-CLAUDE (perfil, memoria, notas) SOLO si la persona dijo que sí (--personal si).
  sesiones/    (solo con --completo y con ese sí) el historial de conversaciones.
La memoria de Claude en ~/.claude/projects/*/memory también va solo con el sí.
NUNCA, ni con el sí: auditorías, procesos e informes de la empresa (~/MI-SISTEMA-CLAUDE/auditoria/, procesos/, y
las conversaciones que pasaron por una auditoría); videos, audios, renders, MATERIAL ni archivos de más de 20 MB.
Toda clave, token o contraseña se reemplaza por <REDACTADO> en la copia. Si el repo no es privado, no sube nada.

Uso (lo corre Claude, no la persona; en Windows `py -3` en lugar de `python3`):
  python3 respaldar.py                     respaldar ahora
  python3 respaldar.py --completo          también las conversaciones (antes de cambiar de computadora)
  python3 respaldar.py --estado            último respaldo, si falló y qué respondió sobre perfil y memoria
  python3 respaldar.py --personal si|no    guarda la respuesta a «¿respaldo tu perfil y tu memoria?»
  python3 respaldar.py --restaurar         en la computadora nueva: baja el respaldo y lo pone en su lugar
  python3 respaldar.py --restaurar --desde CARPETA   lo mismo, desde una copia local (un disco), sin GitHub
  python3 respaldar.py --si-toca           (hook) una vez por día, en segundo plano; no demora nada
  python3 respaldar.py --no-push           arma la copia y el commit, sin subir
"""
import json, os, re, shutil, subprocess, sys, time
from datetime import datetime
from pathlib import Path

ES_WINDOWS = os.name == "nt"
HOME = Path.home()
CLAUDE = HOME / ".claude"
SISTEMA = HOME / "MI-SISTEMA-CLAUDE"
PROYECTOS = HOME / "PROYECTOS"
REPO_NAME = "claude-respaldo"
DEST = HOME / "respaldo-claude" / REPO_NAME
STATE_DIR = CLAUDE / "respaldo"
STATE = STATE_DIR / "estado.json"
AJUSTES = STATE_DIR / "ajustes.json"  # la respuesta a «¿respaldo tu perfil y tu memoria?»
LOG = STATE_DIR / "respaldo.log"
LOCK = STATE_DIR / "en-curso.lock"
if ES_WINDOWS:
    DESKTOP_CFG = Path(os.environ.get("APPDATA") or str(HOME / "AppData" / "Roaming")) / "Claude" / "claude_desktop_config.json"
elif sys.platform == "darwin":
    DESKTOP_CFG = HOME / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
else:
    DESKTOP_CFG = HOME / ".config" / "Claude" / "claude_desktop_config.json"

CADA_HORAS = 20                      # uno por día, sea a la hora que sea que abra la computadora
REINTENTO = 3600                     # si falló, reintenta a la hora
AVISO_ERROR_CADA = 24 * 3600         # el mismo error se le cuenta a Claude una vez por día como máximo
AVISO_PREGUNTA_CADA = 20 * 3600     # «¿perfil y memoria?» sin responder: se le recuerda a Claude una vez por día
LOCK_VIEJO = 3600                    # un candado de respaldo en curso más viejo que esto quedó colgado

MEDIA = {".mp4", ".mov", ".wav", ".mp3", ".m4a", ".webm", ".aac", ".mxf", ".aiff", ".aif", ".mkv", ".avi",
         ".m4v", ".flac", ".ogg", ".prproj", ".aep", ".psd", ".zip", ".dmg", ".pkg", ".exe", ".msi"}
JUNK_DIRS = {"node_modules", "__pycache__", ".venv", "venv", ".git", ".hyperframes", "renders", "RENDERS",
             "MATERIAL", ".cache", "cache", ".next", "dist", "site-packages"}
JUNK_FILES = {".DS_Store", ".credentials.json", "Thumbs.db", "desktop.ini"}
MAX_FILE = 20 * 1024 * 1024
MAX_SESION = 45 * 1024 * 1024  # GitHub rechaza desde 100 MB

# De ~/.claude NO se copia: lo que se regenera solo o es de la máquina (projects/ va aparte; plugins/ se
# reinstala desde su marketplace y pisarlo en otra computadora rompería la instalación).
CLAUDE_FUERA = {"projects", "skills-anteriores", "plugins", "shell-snapshots", "todos", "statsig", "ide", "debug",
                "logs", "file-history", "session-env", "sessions", "telemetry", "respaldo", "paste-cache", "local",
                "downloads", "history.jsonl", "plans", "restaurar-anteriores", "backups", "cache",
                "mcp-needs-auth-cache.json", ".last-cleanup"}
# Copias que dejan el kit, la migración o la persona (settings.json.antes-del-chequeo-…, .bak, …): pueden tener
# claves que no se reconocen por su forma, así que no se copian nunca.
COPIA_VIEJA = re.compile(r"\.antes-|^settings(\.local)?\.json.+|^\.claude\.json|signature-iat\.json$|\.bak$", re.I)

# Datos de la empresa: NUNCA salen de la computadora, ni con el sí de la persona.
EMPRESA = re.compile(r"auditor|informe", re.I)
EMPRESA_CARPETAS = {"procesos"}
MARCAS_AUDITORIA = (b"auditoria-procesos", b"MI-SISTEMA-CLAUDE/auditoria", b"MI-SISTEMA-CLAUDE/procesos",
                    b"MI-SISTEMA-CLAUDE\\\\auditoria", b"MI-SISTEMA-CLAUDE\\\\procesos")

SECRET_KEYS = re.compile(r"(TOKEN|KEY|SECRET|PASSWORD|PASS|AUTH|AUTHORIZATION|COOKIE|CREDENTIALS?)$", re.I)
# Lo que parece una clave: se tapa en la copia (el original no se toca).
SECRETOS = [
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    re.compile(r"\bsk-(ant-)?[A-Za-z0-9_\-]{30,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\bya29\.[0-9A-Za-z_\-]{30,}"),
    re.compile(r"\b1//0[0-9A-Za-z_\-]{30,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}"),  # tokens JWT
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]
# clave = "valor": se tapa solo el valor
SECRETO_ASIGNADO = re.compile(
    r"""(?i)(\b(?:api[_-]?key|secret|token|password|passwd|contraseña|clave|bearer)\b["']?\s*[:=]?\s*["']?)([A-Za-z0-9_\-+/=.]{24,})""")


def log(*a):
    print(*a, flush=True)


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def clave_carpeta(p):
    """Cómo nombra Claude la carpeta de memoria/sesiones de una ruta (/Users/ana -> -Users-ana)."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(p))


def es_de_empresa(nombre):
    return bool(EMPRESA.search(nombre)) or nombre.lower() in EMPRESA_CARPETAS


def es_de_auditoria(nombre):
    return "auditor" in nombre.lower()


def es_venv(d):
    return (d / "pyvenv.cfg").exists()


def dentro(p, base):
    try:
        Path(p).resolve().relative_to(Path(base).resolve())
        return True
    except (ValueError, OSError):
        return False


def borrar_carpeta(p):
    def quitar_solo_lectura(func, ruta, _):  # en Windows rmtree no borra archivos de solo lectura
        try:
            os.chmod(ruta, 0o700)
            func(ruta)
        except Exception:
            pass
    shutil.rmtree(str(p), onerror=quitar_solo_lectura)


# ------------------------------------------------------------------ estado y respuesta de la persona
def leer_json(p):
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def escribir_json(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp-" + str(os.getpid()))
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(p))


def leer_estado():
    return leer_json(STATE)


def guardar_estado(**kw):
    st = leer_estado()
    st.update(kw)
    escribir_json(STATE, st)


def respuesta_personal():
    """True (dijo que sí), False (dijo que no) o None (todavía no se le preguntó)."""
    v = leer_json(AJUSTES).get("perfil_y_memoria")
    return v if isinstance(v, bool) else None


def guardar_personal(si, origen="la persona"):
    aj = leer_json(AJUSTES)
    aj.update({"perfil_y_memoria": bool(si), "respondido": ahora(), "origen": origen})
    escribir_json(AJUSTES, aj)


# ------------------------------------------------------------------ claves
TAPADAS = []


def tapar_texto(t):
    n = 0
    for rx in SECRETOS:
        t, k = rx.subn("<REDACTADO>", t)
        n += k
    t, k = SECRETO_ASIGNADO.subn(lambda m: m.group(1) + "<REDACTADO>", t)
    return t, n + k


def tapar_archivo(p, rel):
    try:
        if p.stat().st_size > MAX_SESION:
            return
        b = p.read_bytes()
    except OSError:
        return
    if b"\0" in b[:8192]:
        return  # binario (imagen, fuente)
    t = b.decode("utf-8", errors="ignore")
    t2, n = tapar_texto(t)
    if n:
        p.write_text(t2, encoding="utf-8")
        TAPADAS.append(f"{rel} ({n})")


def redact(obj):
    if isinstance(obj, dict):
        return {k: ("<REDACTADO>" if SECRET_KEYS.search(k) and isinstance(v, str) and v else redact(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


# ------------------------------------------------------------------ copiar
def copiar_archivo(p, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(p), str(out))
    tapar_archivo(out, out.relative_to(DEST))


def copy_tree(src, dst, max_file=MAX_FILE, borrar=True, solo_ext=None, seguir_link=False, filtro=None, fuera=None):
    """Copia src en dst sin carpetas técnicas, sin video/audio, sin copias viejas de ajustes y tapando claves.
    `filtro(nombre)` True = carpeta o archivo que no se copia (se anota en `fuera`). Devuelve cuántos archivos."""
    if not src.exists():
        return 0
    if seguir_link and src.is_symlink():
        src = src.resolve()
    if borrar and dst.exists():
        borrar_carpeta(dst)
    if src.is_file():
        copiar_archivo(src, dst)
        return 1
    n = 0
    for root, dirs, files in os.walk(str(src), followlinks=False):
        r = Path(root)
        rel = r.relative_to(src)
        quedan = []
        for d in dirs:
            if d in JUNK_DIRS or (r / d).is_symlink() or es_venv(r / d):
                continue
            if filtro and filtro(d):
                if fuera is not None:
                    fuera.append(str(rel / d) + "/")
                continue
            quedan.append(d)
        dirs[:] = quedan
        for f in files:
            p = r / f
            if f in JUNK_FILES or f.startswith("._") or p.is_symlink() or COPIA_VIEJA.search(f):
                continue
            if p.suffix.lower() in MEDIA or (solo_ext and p.suffix.lower() not in solo_ext):
                continue
            if filtro and filtro(f):
                if fuera is not None:
                    fuera.append(str(rel / f))
                continue
            try:
                if p.stat().st_size > max_file:
                    log(f"  queda afuera por pesado: {p}")
                    continue
            except OSError:
                continue
            copiar_archivo(p, dst / rel / f)
            n += 1
    return n


def armar_claude(personal):
    """Espejo de ~/.claude (menos lo regenerable). De projects/ solo la memoria, y solo con el sí."""
    dst = DEST / "claude"
    if dst.exists():
        borrar_carpeta(dst)
    dst.mkdir(parents=True)
    n_skills = n_mem = 0
    for p in sorted(CLAUDE.iterdir()) if CLAUDE.exists() else []:
        n = p.name
        if (n in CLAUDE_FUERA or n in JUNK_FILES or n in JUNK_DIRS or n.startswith("._") or COPIA_VIEJA.search(n)
                or (p.is_symlink() and n not in ("skills", "settings.json", "settings.local.json"))
                or (p.is_dir() and es_venv(p))):
            continue
        if n in ("settings.json", "settings.local.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                (dst / n).write_text(json.dumps(redact(d), indent=2, ensure_ascii=False), encoding="utf-8")
                tapar_archivo(dst / n, Path("claude") / n)
            except Exception:
                copy_tree(p, dst / n)
        elif n == "skills":
            for s in sorted(p.iterdir()):
                if s.is_dir():  # también las skills instaladas como enlace: se copia lo que apuntan
                    copy_tree(s, dst / "skills" / s.name, seguir_link=True)
                    n_skills += 1
        else:
            copy_tree(p, dst / n)
    if personal:
        for m in sorted((CLAUDE / "projects").glob("*/memory")):
            n_mem += copy_tree(m, dst / "projects" / m.parent.name / "memory")
    return n_skills, n_mem


def armar_config():
    """Conexiones (MCP) de Claude Code y de la app de escritorio, con las claves tapadas, y qué plugins había."""
    dst = DEST / "config"
    if dst.exists():
        borrar_carpeta(dst)
    nombres = []
    cj = HOME / ".claude.json"
    if cj.exists():
        try:
            d = json.loads(cj.read_text(encoding="utf-8"))
            out = {"mcpServers": d.get("mcpServers", {}),
                   "proyectos": {k: {"mcpServers": v.get("mcpServers")} for k, v in d.get("projects", {}).items()
                                 if isinstance(v, dict) and v.get("mcpServers")}}
            nombres += list(out["mcpServers"])
            for v in out["proyectos"].values():
                nombres += list(v["mcpServers"])
            dst.mkdir(parents=True, exist_ok=True)
            (dst / "claude-code-mcp.json").write_text(json.dumps(redact(out), indent=2, ensure_ascii=False),
                                                      encoding="utf-8")
            tapar_archivo(dst / "claude-code-mcp.json", Path("config/claude-code-mcp.json"))
        except Exception as e:
            log(f"  no se pudo leer ~/.claude.json: {e}")
    if DESKTOP_CFG.exists():
        try:
            d = json.loads(DESKTOP_CFG.read_text(encoding="utf-8"))
            # Solo las conexiones: el resto son preferencias de esta computadora (su nombre, ids de la cuenta,
            # ajustes de Cowork) que no sirven en otra y no hace falta subir (prueba del jue 19-11-2026).
            mcp = d.get("mcpServers") if isinstance(d, dict) else None
            if isinstance(mcp, dict) and mcp:
                nombres += list(mcp)
                dst.mkdir(parents=True, exist_ok=True)
                (dst / "claude-desktop-config.json").write_text(
                    json.dumps(redact({"mcpServers": mcp}), indent=2, ensure_ascii=False), encoding="utf-8")
                tapar_archivo(dst / "claude-desktop-config.json", Path("config/claude-desktop-config.json"))
        except Exception as e:
            log(f"  no se pudo leer la config de la app de escritorio: {e}")
    # Plugins: solo los nombres y de dónde vienen; en la computadora nueva se instalan desde la app.
    plugins, mercados = [], {}
    d = leer_json(CLAUDE / "plugins" / "installed_plugins.json")
    if isinstance(d.get("plugins"), dict):
        plugins = sorted(d["plugins"])
    for k, v in leer_json(CLAUDE / "plugins" / "known_marketplaces.json").items():
        src = v.get("source") if isinstance(v, dict) else None
        src = src if isinstance(src, dict) else {}
        origen = src.get("repo") or src.get("url") or src.get("path") or ""
        mercados[k] = tapar_texto(str(origen))[0]
    return sorted(set(nombres)), plugins, mercados


def armar_proyectos():
    """De cada proyecto: MD FILES/, HYPERFRAMES/ (sin videos ni audios) y los CLAUDE.md / .claude/."""
    dst = DEST / "proyectos"
    if dst.exists():
        borrar_carpeta(dst)
    fuera = []
    if not PROYECTOS.exists():
        return 0, 0, fuera
    n_md = n_hf = 0
    for root, dirs, files in os.walk(str(PROYECTOS), followlinks=False):
        r = Path(root)
        rel = r.relative_to(PROYECTOS)
        for d in list(dirs):
            if d in ("MD FILES", "HYPERFRAMES", ".claude"):
                copy_tree(r / d, dst / rel / d, filtro=es_de_auditoria, fuera=fuera)
                n_md += d == "MD FILES"
                n_hf += d == "HYPERFRAMES"
        if "CLAUDE.md" in files:
            copy_tree(r / "CLAUDE.md", dst / rel / "CLAUDE.md", borrar=False)
        dirs[:] = [d for d in dirs if d not in JUNK_DIRS and d not in ("MD FILES", "HYPERFRAMES", ".claude")
                   and not d.startswith(".") and not es_de_auditoria(d)] if len(rel.parts) < 5 else []
    return n_md, n_hf, fuera


def armar_sistema(personal):
    """~/MI-SISTEMA-CLAUDE (perfil, memoria, notas): solo con el sí, y nunca auditorías, procesos ni informes."""
    dst = DEST / "sistema"
    if dst.exists():
        borrar_carpeta(dst)
    fuera = []
    if not personal or not SISTEMA.exists():
        return 0, fuera
    return copy_tree(SISTEMA, dst, filtro=es_de_empresa, fuera=fuera), fuera


def toco_auditoria(p):
    try:
        data = p.read_bytes()
    except OSError:
        return True
    return any(m in data for m in MARCAS_AUDITORIA)


def armar_sesiones():
    """Conversaciones (solo --completo y con el sí), sin las que pasaron por una auditoría (ni sus subagentes).
    Las rutas quedan con la carpeta vieja; --restaurar las corrige. El historial de pedidos (history.jsonl) no va:
    mezcla todo, auditorías incluidas."""
    dst = DEST / "sesiones"
    if dst.exists():
        borrar_carpeta(dst)
    n = n_aud = 0
    for d in sorted((CLAUDE / "projects").glob("*")):
        if not d.is_dir():
            continue
        marcadas = set()
        for p in d.glob("*.jsonl"):
            if toco_auditoria(p):
                marcadas.add(p.stem)
                n_aud += 1
        for root, dirs, files in os.walk(str(d)):
            r = Path(root)
            rel = r.relative_to(d)
            if rel.parts and (rel.parts[0] in marcadas or rel.parts[0] == "memory"):
                dirs[:] = []
                continue
            for f in files:
                p = r / f
                if not f.endswith(".jsonl") or (not rel.parts and p.stem in marcadas) or toco_auditoria(p):
                    continue
                try:
                    if p.stat().st_size > MAX_SESION:
                        log(f"  conversación demasiado grande, queda afuera: {p}")
                        continue
                except OSError:
                    continue
                copiar_archivo(p, dst / d.name / rel / f)
                n += 1
    return n, n_aud


def memoria_auto():
    """Dónde guarda Claude la memoria (autoMemoryDirectory), para avisar si queda fuera del respaldo."""
    ruta = leer_json(CLAUDE / "settings.json").get("autoMemoryDirectory")
    return str(Path(os.path.expanduser(str(ruta)))) if ruta else None


def armar(completo=False):
    TAPADAS.clear()
    resp = respuesta_personal()
    personal = resp is True
    DEST.mkdir(parents=True, exist_ok=True)
    n_skills, n_mem = armar_claude(personal)
    mcps, plugins, mercados = armar_config()
    n_md, n_hf, fuera_proy = armar_proyectos()
    n_sis, fuera_sis = armar_sistema(personal)
    if personal:
        resumen = [f"perfil y memoria: sí ({n_sis} archivos de MI-SISTEMA-CLAUDE, {n_mem} recuerdos)"]
    else:
        resumen = ["perfil y memoria: no (" + ("dijo que no" if resp is False else "todavía no se le preguntó") + ")"]
    resumen += [f"{n_skills} skills propias", f"{n_md} proyectos (MD FILES)", f"{n_hf} carpetas HYPERFRAMES",
                f"{len(mcps)} conexiones"]
    ses = DEST / "sesiones"
    if completo and personal:
        n_ses, n_aud = armar_sesiones()
        resumen.append(f"{n_ses} conversaciones" +
                       (f" ({n_aud} que pasaron por una auditoría quedaron afuera)" if n_aud else ""))
    elif completo:
        resumen.append("conversaciones: no (van solo con el sí al perfil y la memoria)")
    if not personal and ses.exists():
        borrar_carpeta(ses)
    empresa = fuera_sis + fuera_proy
    if empresa:
        resumen.append(f"{len(empresa)} de auditorías o procesos de la empresa quedaron afuera (nunca se respaldan)")
    mem = memoria_auto()
    if personal and mem and not (dentro(mem, SISTEMA) or dentro(mem, CLAUDE / "projects")):
        log(f"  ⚠️ la memoria está en {mem}, fuera de lo que cubre este respaldo: no se respaldó")
    meta = {"home": str(HOME), "clave_home": clave_carpeta(HOME), "fecha": ahora(),
            "sistema_operativo": "windows" if ES_WINDOWS else sys.platform, "conexiones": mcps,
            "plugins": plugins, "marketplaces": mercados, "sesiones": ses.exists(),
            "perfil_y_memoria": personal, "memoria_auto": mem}
    escribir_json(DEST / "respaldo.json", meta)
    escribir_readme()
    return resumen


def escribir_readme():
    (DEST / "README.md").write_text(f"""# Respaldo de Claude

Copia privada de lo de Claude en tu computadora. Se sube sola una vez por día (la primera vez que le escribes a
Claude) o cuando le dices "respalda mis cosas". Antes de cambiar de computadora: "respalda todo, que cambio de
computadora".

| Carpeta | Qué es |
|---|---|
| `claude/` | Tu `~/.claude`: CLAUDE.md, ajustes (sin claves), tus skills, hooks, registro de proyectos |
| `config/` | Conexiones de Claude (Google, etc.), con las claves tapadas: en la computadora nueva se vuelven a conectar |
| `proyectos/` | De cada proyecto en `~/PROYECTOS`: `MD FILES/`, `HYPERFRAMES/` (sin videos ni audios) y sus `CLAUDE.md` |
| `sistema/` | Tu `~/MI-SISTEMA-CLAUDE` (perfil, memoria, notas), solo si dijiste que sí |
| `sesiones/` | Tus conversaciones con Claude (solo en un respaldo completo y si dijiste que sí) |

No están: videos, audios, renders, `MATERIAL`, las auditorías ni los procesos de la empresa (esos nunca salen de tu
computadora), ni ninguna clave o contraseña (dicen `<REDACTADO>`). Tus chats de claude.ai no hacen falta: viven en tu
cuenta y aparecen al iniciar sesión.

## En la computadora nueva

Instala la app de Claude y los plugins del kit como la primera vez y dile a Claude:

> Restaura mi respaldo de Claude (skill respaldar).

Después, que haga el chequeo.

Última actualización: {ahora()}
""", encoding="utf-8")


# ------------------------------------------------------------------ git / GitHub
def sh(cmd, cwd=None, check=True, env=None):
    return subprocess.run(cmd, cwd=None if cwd is None else str(cwd), check=check, capture_output=True,
                          encoding="utf-8", errors="replace", env=env)


def gh_usuario():
    try:
        r = sh(["gh", "api", "user", "--jq", ".login"], check=False)
    except FileNotFoundError:
        raise RuntimeError("falta el programa gh y conectar tu cuenta de GitHub (la skill chequeo lo arregla)")
    if r.returncode or not r.stdout.strip():
        raise RuntimeError("GitHub no tiene la sesión iniciada en esta computadora (la skill chequeo lo arregla: gh-login)")
    return r.stdout.strip()


def gh_con_sesion():
    """¿Hay gh con una cuenta conectada? Solo mira esta computadora (sin internet). Recién instalado el kit,
    antes del chequeo, no hay: el aviso del respaldo espera (sin cuenta no hay dónde respaldar, y la pregunta
    salía antes del chequeo y del perfil; prueba en un usuario nuevo, jue 19-11-2026)."""
    for gh in (shutil.which("gh"), "/opt/homebrew/bin/gh", "/usr/local/bin/gh"):
        if gh and os.path.exists(gh):
            try:
                r = subprocess.run([gh, "auth", "token", "--hostname", "github.com"], capture_output=True,
                                   timeout=5)
            except Exception:
                return False
            return r.returncode == 0 and bool(r.stdout.strip())
    return False


def gh_listo(st):
    """gh_con_sesion() a lo sumo cada 5 minutos mientras dé que no (corre en cada mensaje)."""
    if time.time() < st.get("gh_no_hasta", 0):
        return False
    if gh_con_sesion():
        return True
    guardar_estado(gh_no_hasta=time.time() + 300)
    return False


def es_privado(user):
    r = sh(["gh", "api", f"repos/{user}/{REPO_NAME}", "--jq", ".private"], check=False)
    return None if r.returncode else r.stdout.strip() == "true"


def asegurar_repo(user):
    """El repo tiene que existir y ser PRIVADO. Si no existe, se crea privado."""
    priv = es_privado(user)
    if priv is None:
        c = sh(["gh", "repo", "create", f"{user}/{REPO_NAME}", "--private",
                "--description", "Respaldo privado de Claude (configuración, proyectos, skills)"], check=False)
        if c.returncode:
            raise RuntimeError(f"no se pudo crear el repo {user}/{REPO_NAME}: {c.stderr.strip()[-300:]}")
        log(f"  repo nuevo y privado: github.com/{user}/{REPO_NAME}")
        priv = es_privado(user)
    if priv is not True:
        raise RuntimeError(f"el repo {user}/{REPO_NAME} NO es privado: no se sube nada (hacerlo privado en GitHub)")


def git_auth():
    token = sh(["gh", "auth", "token"]).stdout.strip()
    helper = f"!f() {{ echo username=x-access-token; echo password={token}; }}; f"
    return ["-c", "credential.helper=", "-c", f"credential.helper={helper}"]


def commit(user):
    if not (DEST / ".git").exists():
        sh(["git", "init", "-q", "-b", "main"], cwd=DEST)
    sh(["git", "add", "-A"], cwd=DEST)
    if sh(["git", "diff", "--cached", "--quiet"], cwd=DEST, check=False).returncode == 0:
        return False
    sh(["git", "-c", f"user.name={user}", "-c", f"user.email={user}@users.noreply.github.com",
        "commit", "-q", "-m", f"Respaldo {ahora()}"], cwd=DEST)
    return True


def subir(user):
    url = f"https://github.com/{user}/{REPO_NAME}.git"
    if "origin" not in sh(["git", "remote"], cwd=DEST).stdout.split():
        sh(["git", "remote", "add", "origin", url], cwd=DEST)
    else:
        sh(["git", "remote", "set-url", "origin", url], cwd=DEST)
    r = sh(["git", *git_auth(), "push", "-q", "-u", "origin", "main"], cwd=DEST, check=False)
    if r.returncode and ("rejected" in r.stderr or "fetch first" in r.stderr):
        raise RuntimeError("GitHub tiene un respaldo más nuevo hecho desde OTRA computadora; no se pisa. Si ya se usa la "
                           "computadora nueva, dejar de usar Claude en la vieja (o restaurar acá con --restaurar)")
    if r.returncode:
        raise RuntimeError(f"falló la subida: {r.stderr.strip()[-500:]}")


# ------------------------------------------------------------------ respaldar
def respaldar(push=True, completo=False):
    log(f"→ Respaldo {ahora()}" + (" (completo, con conversaciones)" if completo else ""))
    user = gh_usuario() if push else "yo"
    if push and not (DEST / ".git").exists() and es_privado(user) is not None:
        raise RuntimeError(f"en GitHub ya hay un respaldo (github.com/{user}/{REPO_NAME}) y esta computadora todavía "
                           "no lo restauró; no se sube nada para no taparlo. Ofrecer restaurarlo (skill respaldar → "
                           "Cambiar de computadora → En la nueva)")
    resumen = armar(completo)
    log("  copiado: " + ", ".join(resumen))
    if TAPADAS:
        log(f"  claves tapadas con <REDACTADO> en {len(TAPADAS)} archivo(s) de la copia (los originales no se tocan):")
        for t in TAPADAS[:15]:
            log(f"    {t}")
    else:
        log("  claves: ninguna")
    hubo = commit(user)
    if not push:
        log("  listo sin subir (--no-push)")
        return
    # Siempre se sube (si GitHub ya lo tiene, git no manda nada): así un commit que quedó sin subir sale ahora.
    asegurar_repo(user)
    subir(user)
    log(f"  ✅ subido a github.com/{user}/{REPO_NAME} (privado)" if hubo else
        f"  ✅ sin cambios nuevos; github.com/{user}/{REPO_NAME} al día")
    guardar_estado(ultimo_ok=time.time(), ultimo_ok_texto=ahora(), error=None, error_visto=False,
                   **({"ultimo_completo": ahora()} if completo else {}))


# ------------------------------------------------------------------ restaurar
CAMBIOS_RUTA = []  # [(texto viejo, texto nuevo)] cuando la computadora nueva tiene otro usuario


def poner(src, dst, pisar, anteriores, base):
    """Copia un archivo (con las rutas de la computadora vieja cambiadas a las de esta); si ya existe distinto y
    `pisar`, guarda el viejo en `anteriores`. Devuelve 1 si copió."""
    data = src.read_bytes()
    if CAMBIOS_RUTA and b"\0" not in data[:8192]:
        for a, b in CAMBIOS_RUTA:
            data = data.replace(a.encode("utf-8"), b.encode("utf-8"))
    if dst.exists():
        if not pisar:
            return 0
        try:
            if dst.read_bytes() == data:
                return 0
        except OSError:
            pass
        guard = anteriores / dst.relative_to(base)
        guard.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(dst), str(guard))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    shutil.copystat(str(src), str(dst))
    return 1


def cambios_de_ruta(meta):
    vieja_home, nueva_home = meta.get("home", ""), str(HOME)
    vieja, nueva = meta.get("clave_home", ""), clave_carpeta(HOME)
    pares = []
    if vieja and vieja != nueva and vieja_home:
        pares.append((vieja_home + "/", nueva_home + "/"))
        if "\\" in vieja_home or "\\" in nueva_home:  # Windows: C:\Users\ana, C:\\Users\\ana (JSON) y C:/Users/ana
            pares += [(vieja_home + "\\", nueva_home + "\\"),
                      (vieja_home.replace("\\", "\\\\") + "\\\\", nueva_home.replace("\\", "\\\\") + "\\\\"),
                      (vieja_home.replace("\\", "/") + "/", nueva_home.replace("\\", "/") + "/")]
        pares += [(vieja + "-", nueva + "-"), (vieja + "/", nueva + "/")]
    return pares


def restaurar(desde=None):
    if desde:
        src = Path(os.path.expanduser(desde)).resolve()
        if not (src / "respaldo.json").exists():
            raise RuntimeError(f"{src} no parece un respaldo de Claude (falta respaldo.json)")
        log(f"→ Restaurar desde la copia local {src}")
        if not DEST.exists() and (src / ".git").exists():
            DEST.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(src), str(DEST), symlinks=True)
            log(f"  la copia quedó también en {DEST}: desde acá se sigue respaldando")
            base = DEST
        else:
            base = src
    else:
        user = gh_usuario()
        log(f"→ Restaurar desde github.com/{user}/{REPO_NAME}")
        if es_privado(user) is None:
            raise RuntimeError(f"no existe el repo {user}/{REPO_NAME} (¿otra cuenta de GitHub?)")
        if (DEST / ".git").exists():
            r = sh(["git", *git_auth(), "pull", "-q", "--ff-only", "origin", "main"], cwd=DEST, check=False)
            if r.returncode:
                raise RuntimeError(f"la copia local {DEST} no coincide con GitHub: {r.stderr.strip()[-300:]}")
        else:
            DEST.parent.mkdir(parents=True, exist_ok=True)
            r = sh(["git", *git_auth(), "clone", "-q", "-b", "main", f"https://github.com/{user}/{REPO_NAME}.git",
                    str(DEST)], check=False)
            if r.returncode:
                raise RuntimeError(f"no se pudo bajar el respaldo: {r.stderr.strip()[-300:]}")
        base = DEST
    meta = leer_json(base / "respaldo.json")
    vieja, nueva = meta.get("clave_home", ""), clave_carpeta(HOME)
    CAMBIOS_RUTA.clear()
    CAMBIOS_RUTA.extend(cambios_de_ruta(meta))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    anteriores = CLAUDE / "restaurar-anteriores" / stamp

    def carpeta_nueva(nombre):  # -Users-ana-PROYECTOS-X  ->  -Users-maria-PROYECTOS-X
        return nueva + nombre[len(vieja):] if vieja and nombre.startswith(vieja) else nombre

    def tapado(p):
        return b"<REDACTADO>" in p.read_bytes()[:2000000]

    n_claude = n_omit = 0
    src = base / "claude"
    for p in sorted(src.rglob("*")) if src.exists() else []:
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        parts = list(rel.parts)
        if parts[0] == "projects" and len(parts) > 1:
            parts[1] = carpeta_nueva(parts[1])
        dst = CLAUDE.joinpath(*parts)
        if rel.name in ("settings.json", "settings.local.json") and dst.exists():
            n_omit += 1  # los ajustes de esta computadora no se tocan; los tuyos quedan en el respaldo para comparar
            continue
        n_claude += poner(p, dst, pisar=not tapado(p), anteriores=anteriores, base=CLAUDE)
    n_sis = 0
    src = base / "sistema"
    for p in sorted(src.rglob("*")) if src.exists() else []:
        if p.is_file():
            n_sis += poner(p, SISTEMA / p.relative_to(src), pisar=not tapado(p), anteriores=anteriores, base=HOME)
    n_proy = 0
    src = base / "proyectos"
    for p in sorted(src.rglob("*")) if src.exists() else []:
        if p.is_file():
            n_proy += poner(p, PROYECTOS / p.relative_to(src), pisar=False, anteriores=anteriores, base=HOME)
    n_ses = 0
    src = base / "sesiones"
    for p in sorted(src.rglob("*")) if src.exists() else []:
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        if len(rel.parts) == 1:  # history.jsonl de un respaldo hecho con la versión del kit de video
            if rel.name == "history.jsonl":
                n_ses += poner(p, CLAUDE / "history.jsonl", pisar=False, anteriores=anteriores, base=CLAUDE)
            continue
        n_ses += poner(p, CLAUDE / "projects" / carpeta_nueva(rel.parts[0]) / Path(*rel.parts[1:]),
                       pisar=False, anteriores=anteriores, base=CLAUDE)
    log(f"  ~/.claude: {n_claude} archivos puestos ({n_omit} ajustes no se tocaron: son los de esta computadora)")
    log(f"  ~/MI-SISTEMA-CLAUDE: {n_sis} archivos puestos" +
        ("" if meta.get("perfil_y_memoria") else " (el respaldo no traía perfil ni memoria)"))
    log(f"  ~/PROYECTOS: {n_proy} archivos nuevos (lo que ya estaba no se pisa)")
    log(f"  conversaciones: {n_ses}" + ("" if meta.get("sesiones") else " (el respaldo no era completo)"))
    if anteriores.exists():
        log(f"  lo que había antes y se reemplazó quedó en {anteriores}")
    if meta.get("perfil_y_memoria") is True and respuesta_personal() is None:
        guardar_personal(True, origen="respaldo de la computadora anterior")
        log("  perfil y memoria: en la computadora anterior dijiste que sí; se siguen respaldando")
    if meta.get("conexiones"):
        log("  conexiones para volver a conectar (sus claves no viajan): " + ", ".join(meta["conexiones"]))
    if meta.get("plugins"):
        log("  plugins que tenías (instala desde la app los que falten): " + ", ".join(meta["plugins"]))
    if meta.get("home") and meta["home"] != str(HOME):
        log(f"  la computadora vieja usaba {meta['home']}; las carpetas se adaptaron a {HOME}")
    log("  ahora haz el chequeo: conecta la memoria que volvió y revisa lo demás")
    guardar_estado(restaurado=ahora(), ultimo_intento=time.time())


# ------------------------------------------------------------------ modos
def aviso_sistema(texto):
    """Notificación de la computadora (solo cuando falla un respaldo automático)."""
    try:
        if sys.platform == "darwin":
            t = texto.replace('"', "'")
            sh(["osascript", "-e", f'display notification "{t}" with title "Respaldo de Claude"'], check=False)
        elif ES_WINDOWS:  # globo de Windows con PowerShell (pendiente de prueba)
            t = texto.replace("'", "''")
            ps = ("Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
                  "$n = New-Object System.Windows.Forms.NotifyIcon; $n.Icon = [System.Drawing.SystemIcons]::Warning; "
                  f"$n.Visible = $true; $n.ShowBalloonTip(10000, 'Respaldo de Claude', '{t}', "
                  "[System.Windows.Forms.ToolTipIcon]::Warning); Start-Sleep -Seconds 11; $n.Dispose()")
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=0x08000000)  # CREATE_NO_WINDOW
        elif shutil.which("notify-send"):
            sh(["notify-send", "Respaldo de Claude", texto], check=False)
    except Exception:
        pass


def tomar_lock():
    """Un solo respaldo o restauración a la vez (dos sesiones de Claude pueden abrirse juntas)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                colgado = time.time() - LOCK.stat().st_mtime > LOCK_VIEJO
            except OSError:
                continue  # se soltó mientras tanto: probar de nuevo
            if not colgado:
                return False
            soltar_lock()
            continue
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    return False


def soltar_lock():
    try:
        LOCK.unlink()
    except OSError:
        pass


def correr(fn, automatico=False, con_lock=False, **kw):
    if not con_lock and not tomar_lock():
        log("  ⏳ ya hay un respaldo en curso; esperar unos minutos y mirar --estado")
        return 1
    try:
        fn(**kw)
        return 0
    except Exception as e:
        msg = str(e)
        log(f"  ❌ {msg}")
        st = leer_estado()
        ya_avisado = (st.get("error") == msg and time.time() - st.get("error_avisado", 0) < AVISO_ERROR_CADA)
        # Si lo corrió Claude a mano, ya vio el error: el hook no lo vuelve a contar.
        guardar_estado(error=msg, error_cuando=ahora(), error_visto=bool(ya_avisado or not automatico))
        if automatico and not ya_avisado:
            aviso_sistema("El respaldo de Claude falló. Pregúntale a Claude.")
        return 1
    finally:
        soltar_lock()


def recortar_log():
    try:
        if LOG.stat().st_size > 1000000:
            LOG.write_bytes(LOG.read_bytes()[-200000:])
    except OSError:
        pass


def lanzar_en_segundo_plano():
    kw = {"stdin": subprocess.DEVNULL}
    if ES_WINDOWS:
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    recortar_log()
    with open(str(LOG), "a", encoding="utf-8") as out:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--automatico", "--con-lock"],
                         stdout=out, stderr=out, **kw)


def si_toca():
    """Hook UserPromptSubmit: nunca demora ni corta la conversación. Lo que imprime lo lee Claude."""
    st = leer_estado()
    if st.get("error") and not st.get("error_visto"):
        guardar_estado(error_visto=True, error_avisado=time.time())  # una vez: Claude lo cuenta y lo arregla
        print(f"⚠️ RESPALDO: el último respaldo a GitHub falló ({st.get('error_cuando')}): "
              f"{st['error'][:300]}. Contárselo en una línea y ofrecer arreglarlo (skill respaldar).")
    elif (respuesta_personal() is None and time.time() - st.get("aviso_pregunta", 0) > AVISO_PREGUNTA_CADA
          and gh_listo(st)):
        guardar_estado(aviso_pregunta=time.time())
        print("📦 RESPALDO: el respaldo diario a su GitHub privado espera una respuesta: si quiere respaldar también su "
              "perfil y su memoria. Cuando termines lo que está pidiendo, pregúntaselo una vez (skill respaldar → "
              "«La primera vez»); el respaldo automático empieza con su respuesta, sea sí o no.")
    if respuesta_personal() is None:
        return  # nada se sube (ni se crea el repo en su cuenta) antes de que la persona sepa del respaldo
    espera = REINTENTO if st.get("error") else CADA_HORAS * 3600
    if time.time() - st.get("ultimo_intento", 0) < espera:
        return
    if not tomar_lock():
        return
    try:
        guardar_estado(ultimo_intento=time.time())
        lanzar_en_segundo_plano()
    except Exception:
        soltar_lock()
        raise


def estado():
    st = leer_estado()
    aj = leer_json(AJUSTES)
    r = respuesta_personal()
    log(f"Último respaldo bueno: {st.get('ultimo_ok_texto') or 'nunca'}")
    log(f"Último respaldo completo (con conversaciones): {st.get('ultimo_completo') or 'nunca'}")
    if r is None:
        log("Perfil y memoria: sin responder (todavía no se respaldan)")
    else:
        log(f"Perfil y memoria: {'sí' if r else 'no'} (respondido {aj.get('respondido')}, {aj.get('origen')})")
    if st.get("error"):
        log(f"Último error ({st.get('error_cuando')}): {st['error']}")
    if LOCK.exists():
        log("Hay un respaldo en curso ahora.")
    if st.get("restaurado"):
        log(f"Restaurado en esta computadora: {st['restaurado']}")
    log(f"Copia local: {DEST}")
    log(f"Registro: {LOG}")


def main():
    for s in (sys.stdout, sys.stderr):  # Windows: los emojis no rompen la salida
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    a = sys.argv[1:]
    if "--si-toca" in a:
        try:
            si_toca()
        except Exception:
            pass
        return 0
    if "--estado" in a:
        estado()
        return 0
    if "--personal" in a:
        i = a.index("--personal")
        v = a[i + 1].strip().lower() if i + 1 < len(a) else ""
        if v not in ("si", "sí", "no"):
            log("Uso: --personal si  o  --personal no")
            return 2
        antes = respuesta_personal()
        guardar_personal(v != "no")
        if v != "no":
            msg = "sí, se respaldan desde el próximo respaldo"
        elif antes is True:
            msg = ("no; desde el próximo respaldo ya no se suben (las copias anteriores siguen en el historial del "
                   "repo privado)")
        else:
            msg = "no; se respalda solo la configuración (tu perfil y tu memoria quedan solo en esta computadora)"
        log("Perfil y memoria: " + msg)
        return 0
    if "--restaurar" in a:
        desde = None
        if "--desde" in a:
            i = a.index("--desde")
            if i + 1 >= len(a):
                log("Uso: --restaurar --desde <carpeta del respaldo>")
                return 2
            desde = a[i + 1]
        return correr(restaurar, desde=desde)
    return correr(respaldar, automatico="--automatico" in a, con_lock="--con-lock" in a,
                  push="--no-push" not in a, completo="--completo" in a)


if __name__ == "__main__":
    sys.exit(main())
