#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""¿De qué repo de GitHub viene el kit instalado? Solo lee: no cambia nada.

Busca el plugin base del kit (el de esta skill) entre los instalados, su marketplace y la fuente de
ese marketplace. Imprime líneas CLAVE=valor:

  MARKETPLACE=creativos
  PLUGINS=creativos-base creativos-video
  REPO=dueño/repo          (vacío si no se pudo saber)
  ORIGEN=github | git | carpeta | app | desconocido
  CARPETA=<ruta local del marketplace, si es una carpeta>
  CLI=<ruta del comando claude, vacío si no hay>   (sirve para actualizar con `claude plugin …`)
  V1=<cuántas skills de la versión 1 hay sueltas en ~/.claude/skills> HOOKS_V1=<sí|no>
  NOTA=<por qué falta el repo, si falta>

ORIGEN=app: el kit vino de la app (Cowork, "sincronizado"); se actualiza desde la app, no con el CLI.

Uso: python3 repo_del_kit.py   (en Windows: py -3 repo_del_kit.py)
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

C = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
RAIZ = Path(__file__).resolve().parents[3]          # la carpeta del plugin base


def leer(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def repo_de_url(url):
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url or "")
    return f"{m.group(1)}/{m.group(2)}" if m else ""


def repo_de_fuente(src):
    """(repo, origen) de una fuente de marketplace: {"source": "github", "repo": ...} o git/url."""
    tipo = (src or {}).get("source")
    if tipo == "github":
        return src.get("repo") or "", "github"
    if tipo in ("git", "url"):
        return repo_de_url(src.get("url")), "git"
    return "", ""


def _version(ruta):
    m = re.search(r"claude-code[\\/](\d+)\.(\d+)\.(\d+)", ruta)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def buscar_cli():
    """El comando claude: el del PATH o, si no hay, el que trae la app de escritorio (el más nuevo)."""
    en_path = shutil.which("claude")
    if en_path:
        return en_path
    h = Path.home()
    cands = []
    if sys.platform == "darwin":
        base = h / "Library" / "Application Support" / "Claude" / "claude-code"
        for patron in ("*/claude.app/Contents/MacOS/claude", "*/*/claude.app/Contents/MacOS/claude"):
            cands += glob.glob(str(base / patron))
    elif os.name == "nt":
        # sin probar en Windows: dónde suele dejarlo la app
        for raiz in (os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")):
            if raiz:
                for patron in ("*/claude.exe", "*/*/claude.exe", "*/*/*/claude.exe"):
                    cands += glob.glob(str(Path(raiz) / "Claude" / "claude-code" / patron))
    for fijo in (h / ".local" / "bin" / "claude", h / ".local" / "bin" / "claude.exe",
                 h / ".claude" / "local" / "claude"):
        if fijo.exists():
            cands.append(str(fijo))
    cands = [c for c in cands if os.access(c, os.X_OK) or c.endswith(".exe")]
    cands.sort(key=_version, reverse=True)
    return cands[0] if cands else ""


def restos_v1():
    """Cuántas skills de la versión 1 del kit hay sueltas en ~/.claude/skills y si quedan sus hooks."""
    lista = RAIZ / "skills" / "chequeo" / "references" / "skills-v1.txt"
    n = 0
    try:
        for linea in lista.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and (C / "skills" / linea.split()[0]).is_dir():
                n += 1
    except OSError:
        pass
    try:
        texto = (C / "settings.json").read_text(encoding="utf-8")
    except OSError:
        texto = ""
    hooks = bool(re.search(r"skills[\\/]+mdfilesummary[\\/]+scripts[\\/]+md_files\.py", texto))
    return n, hooks


def desde_la_app():
    """Si este plugin vino sincronizado desde la app: (True, repo). El repo, de la lista de marketplaces
    que guarda la app (.marketplaces.json); vacío si no se puede saber."""
    synced = C / "plugins" / "synced"
    try:
        rel = RAIZ.relative_to(synced.resolve())
    except ValueError:
        try:
            rel = RAIZ.relative_to(synced)
        except ValueError:
            return False, ""
    partes = set(rel.parts)
    balde = synced / rel.parts[0] if rel.parts else synced
    filas = (leer(balde / ".marketplaces.json").get("rows") or [])
    con_repo = []
    for f in filas:
        repo, _ = repo_de_fuente(f.get("source"))
        if repo:
            con_repo.append((f.get("name") or "", repo))
    for nombre, repo in con_repo:
        if nombre and nombre in partes:
            return True, repo
    return True, (con_repo[0][1] if len(con_repo) == 1 else "")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    base = leer(RAIZ / ".claude-plugin" / "plugin.json").get("name") or "creativos-base"
    prefijo = base[:-4] if base.endswith("-base") else "creativos-"
    inst = (leer(C / "plugins" / "installed_plugins.json").get("plugins") or {})
    mkts = sorted({k.split("@", 1)[1] for k in inst if k.startswith(base + "@") and "@" in k})
    out = {"MARKETPLACE": "", "PLUGINS": "", "REPO": "", "ORIGEN": "desconocido", "CARPETA": "",
           "CLI": buscar_cli(), "V1": "", "HOOKS_V1": "", "NOTA": ""}
    n1, h1 = restos_v1()
    out["V1"], out["HOOKS_V1"] = str(n1), ("sí" if h1 else "no")
    app, repo_app = desde_la_app()
    if not mkts:
        out["ORIGEN"] = "app"
        out["REPO"] = repo_app
        if app and not repo_app:
            out["NOTA"] = "Vino sincronizado desde la app, pero no se pudo saber de qué repo. Preguntárselo."
        elif not app:
            out["NOTA"] = (f"{base} no figura entre los plugins instalados por Claude Code: puede venir de la "
                           "app (Cowork, sincronizado) o no estar instalado. Preguntar el repo a la persona.")
    else:
        mkt = mkts[0]
        out["MARKETPLACE"] = mkt
        out["PLUGINS"] = " ".join(sorted(k.split("@")[0] for k in inst
                                         if k.endswith("@" + mkt) and k.startswith(prefijo)))
        src = (leer(C / "plugins" / "known_marketplaces.json").get(mkt) or {}).get("source") or {}
        tipo = src.get("source")
        if tipo in ("github", "git", "url"):
            out["REPO"], out["ORIGEN"] = repo_de_fuente(src)
        elif tipo in ("directory", "file"):
            carpeta = src.get("path") or ""
            out["ORIGEN"], out["CARPETA"] = "carpeta", carpeta
            try:
                url = subprocess.run(["git", "-C", carpeta, "remote", "get-url", "origin"],
                                     capture_output=True, text=True, timeout=10).stdout.strip()
                out["REPO"] = repo_de_url(url)
            except Exception:
                pass
            if not out["REPO"]:
                out["NOTA"] = "El marketplace es una carpeta local sin repo de GitHub."
        else:
            out["NOTA"] = f"No reconozco la fuente del marketplace {mkt}."
    for k, v in out.items():
        print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
