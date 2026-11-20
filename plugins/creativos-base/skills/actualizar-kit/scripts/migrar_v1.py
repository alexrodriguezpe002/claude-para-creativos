#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pasa una instalación vieja del kit (versión 1) a la versión 2 (plugins). Sin --aplicar solo
SIMULA: dice qué haría y no cambia nada.

Qué hace con --aplicar (nada se borra):
  1. Mueve las skills de la versión 1 que ya vienen en un plugin instalado a
     ~/.claude/skills-anteriores/<aaaa-mm-dd>-v1/. Las de un plugin que no está instalado se quedan
     donde están (para no perderlas), salvo que se pida con --tambien <plugin>.
  2. Quita de ~/.claude/settings.json los hooks que agregó la versión 1 (registro MD FILES y sonido),
     solo si el plugin base está instalado: el plugin trae los mismos. Antes, copia de respaldo.
  3. Con --memoria: si no hay "autoMemoryDirectory", lo apunta a la memoria que ya tenía (la de la
     carpeta de usuario), para que todas las sesiones usen esa sola memoria.
  4. Con --quitar-bloque-memoria: saca del ~/.claude/CLAUDE.md el bloque "MEMORIA-UNICA" de la
     versión 1, solo si autoMemoryDirectory ya apunta a esa misma memoria (si no, el bloque hace
     falta). Antes, copia de respaldo.
Nunca toca: el resto del CLAUDE.md, el perfil, la memoria, las skills propias, ~/.claude/remote-control
ni la carpeta del kit.

  python3 migrar_v1.py                         # simulación
  python3 migrar_v1.py --aplicar [--memoria] [--quitar-bloque-memoria] [--tambien creativos-oficina]
(en Windows: py -3)
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys
from pathlib import Path

C = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]                                   # la carpeta del plugin base
LISTA = RAIZ / "skills" / "chequeo" / "references" / "skills-v1.txt"
SONIDO_V1 = "afplay /System/Library/Sounds/Glass.aiff 2>/dev/null || true"
MARCA_BLOQUE = "<!-- MEMORIA-UNICA"


def leer_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def prefijo():
    base = (leer_json(RAIZ / ".claude-plugin" / "plugin.json") or {}).get("name") or "creativos-base"
    return base[:-4] if base.endswith("-base") else "creativos-"


def plugins_instalados(pref):
    """Nombres de los plugins del kit instalados por Claude Code o sincronizados desde la app."""
    nombres = set()
    inst = (leer_json(C / "plugins" / "installed_plugins.json") or {}).get("plugins") or {}
    for k in inst:
        n = k.split("@", 1)[0]
        if n.startswith(pref):
            nombres.add(n)
    synced = C / "plugins" / "synced"
    if synced.is_dir():
        for pj in list(synced.glob("*/*/.claude-plugin/plugin.json")) + \
                  list(synced.glob("*/*/*/.claude-plugin/plugin.json")):
            n = (leer_json(pj) or {}).get("name") or ""
            if n.startswith(pref):
                nombres.add(n)
    # el plugin de esta skill está instalado aunque no figure (por ejemplo, cargado con --plugin-dir)
    nombres.add(pref + "base")
    return nombres


def skills_v1():
    """[(skill, plugin)] de la lista de la versión 1."""
    out = []
    for linea in LISTA.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        partes = linea.split()
        out.append((partes[0], partes[1] if len(partes) > 1 else ""))
    return out


def es_hook_v1(cmd):
    c = (cmd or "").replace("\\", "/")
    return "/.claude/skills/mdfilesummary/scripts/md_files.py" in c or c.strip() == SONIDO_V1


def sin_hooks_v1(settings):
    """(settings nuevo, cuántos hooks se quitan). No cambia el original."""
    s = json.loads(json.dumps(settings))
    hooks = s.get("hooks")
    if not isinstance(hooks, dict):
        return s, 0
    quitados = 0
    for evento in list(hooks):
        grupos = hooks[evento]
        if not isinstance(grupos, list):
            continue
        nuevos = []
        for g in grupos:
            if not isinstance(g, dict) or not isinstance(g.get("hooks"), list):
                nuevos.append(g)
                continue
            quedan = [h for h in g["hooks"] if not (isinstance(h, dict) and es_hook_v1(h.get("command")))]
            quitados += len(g["hooks"]) - len(quedan)
            if quedan:
                g["hooks"] = quedan
                nuevos.append(g)
        if nuevos:
            hooks[evento] = nuevos
        else:
            del hooks[evento]
    if not hooks:
        del s["hooks"]
    return s, quitados


def memoria_v1():
    esc = re.sub(r"[^A-Za-z0-9]", "-", str(Path.home()))
    m = C / "projects" / esc / "memory"
    return m if (m / "MEMORY.md").is_file() else None


def misma_carpeta(a, b):
    try:
        return Path(os.path.expanduser(str(a))).resolve() == Path(os.path.expanduser(str(b))).resolve()
    except Exception:
        return False


def quitar_bloque(texto):
    """Saca el bloque MEMORIA-UNICA tal como lo escribía la versión 1: su comentario, su título
    '## Memoria…' y todo hasta el próximo título '## ' (o el final). Si no tiene esa forma (alguien lo
    cambió), no se reconoce y no se saca. Devuelve (texto nuevo, carpeta que importaba el bloque o None)."""
    i = texto.find(MARCA_BLOQUE)
    if i < 0:
        return texto, None
    resto = texto[i:]
    lineas = resto.splitlines(keepends=True)
    siguiente = next((l for l in lineas[1:] if l.strip()), "")
    if not siguiente.startswith("## Memoria"):
        return texto, None
    titulos = [m.start() for m in re.finditer(r"(?m)^## ", resto)]
    fin = titulos[1] if len(titulos) > 1 else len(resto)
    bloque = resto[:fin]
    m = re.search(r"(?m)^@(.+)/MEMORY\.md\s*$", bloque)
    if not m:
        return texto, None
    nuevo = texto[:i].rstrip() + "\n" + (("\n" + resto[fin:]) if fin < len(resto) else "")
    return nuevo, m.group(1)


def escribir_json(p, data):
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Pasa el kit de la versión 1 a la 2 (sin --aplicar, simula).")
    ap.add_argument("--aplicar", action="store_true", help="hacer los cambios (sin esto, solo simula)")
    ap.add_argument("--memoria", action="store_true", help="apuntar autoMemoryDirectory a la memoria v1")
    ap.add_argument("--quitar-bloque-memoria", action="store_true",
                    help="sacar el bloque MEMORIA-UNICA del CLAUDE.md (solo si ya no hace falta)")
    ap.add_argument("--tambien", action="append", default=[], metavar="PLUGIN",
                    help="mover también las skills v1 de un plugin que la persona no quiere instalar")
    a = ap.parse_args()

    hoy = datetime.date.today().isoformat()
    modo = "APLICADO" if a.aplicar else "SIMULACIÓN (no se cambió nada)"
    print(f"Migración del kit a la versión 2 · {modo}")
    pref = prefijo()
    instalados = plugins_instalados(pref)
    print(f"Plugins del kit instalados: {' '.join(sorted(instalados))}")

    # 1. skills
    destino = C / "skills-anteriores" / f"{hoy}-v1"
    mover, quedan = [], []
    for skill, plugin in skills_v1():
        ruta = C / "skills" / skill
        if not (ruta.is_dir() or ruta.is_symlink()):
            continue
        if plugin in instalados or plugin in a.tambien:
            mover.append(skill)
        else:
            quedan.append((skill, plugin))
    print()
    if mover:
        print(f"Skills viejas que se mueven a {destino} ({len(mover)}): {' '.join(mover)}")
    else:
        print("No hay skills viejas para mover.")
    if quedan:
        por_plugin = {}
        for s, p in quedan:
            por_plugin.setdefault(p or "?", []).append(s)
        for p, ss in sorted(por_plugin.items()):
            print(f"Se quedan donde están (falta el plugin {p}): {' '.join(ss)}")
    if a.aplicar and mover:
        destino.mkdir(parents=True, exist_ok=True)
        for s in mover:
            d = destino / s
            n = 2
            while d.exists() or d.is_symlink():
                d = destino / f"{s}-{n}"
                n += 1
            shutil.move(str(C / "skills" / s), str(d))

    # 2. hooks
    print()
    ruta_set = C / "settings.json"
    settings = leer_json(ruta_set) if ruta_set.exists() else {}
    copia_set = None
    if settings is None:
        print("settings.json no es JSON válido: no se toca (hay que revisarlo a mano).")
        settings = {}
    else:
        nuevo, quitados = sin_hooks_v1(settings)
        if not quitados:
            print("No hay hooks de la versión 1 en settings.json.")
        elif (pref + "base") not in instalados:
            print(f"Hay {quitados} hooks de la versión 1, pero sin el plugin base no se quitan.")
        else:
            print(f"Hooks de la versión 1 que se quitan de settings.json: {quitados} "
                  "(el plugin base trae los mismos).")
            if a.aplicar:
                copia_set = ruta_set.with_name(f"settings.json.antes-de-v2-{hoy}")
                shutil.copy2(ruta_set, copia_set)
                escribir_json(ruta_set, nuevo)
                settings = nuevo
                print(f"  copia de antes: {copia_set}")

    # 3. memoria
    print()
    mem_v1 = memoria_v1()
    actual = settings.get("autoMemoryDirectory") if isinstance(settings, dict) else None
    if actual:
        print(f"Memoria: ya es una sola ({actual}).")
    elif mem_v1:
        print(f"Memoria: la de la versión 1 está en {mem_v1}.", end=" ")
        if a.memoria:
            print("Se apunta autoMemoryDirectory ahí.")
            if a.aplicar:
                if copia_set is None and ruta_set.exists():
                    copia_set = ruta_set.with_name(f"settings.json.antes-de-v2-{hoy}")
                    shutil.copy2(ruta_set, copia_set)
                    print(f"  copia de antes: {copia_set}")
                settings["autoMemoryDirectory"] = str(mem_v1)
                escribir_json(ruta_set, settings)
                actual = str(mem_v1)
        else:
            print("Para que todas las sesiones la usen: --memoria.")
    else:
        print("Memoria: no hay memoria de la versión 1 (la arma el chequeo, código memoria-unica).")

    # 4. bloque MEMORIA-UNICA del CLAUDE.md
    cmd = C / "CLAUDE.md"
    try:
        texto = cmd.read_text(encoding="utf-8")
    except OSError:
        texto = ""
    if MARCA_BLOQUE in texto:
        nuevo, carpeta = quitar_bloque(texto)
        if not a.quitar_bloque_memoria:
            print("El CLAUDE.md tiene el bloque MEMORIA-UNICA de la versión 1 "
                  "(con autoMemoryDirectory ya no hace falta; se saca con --quitar-bloque-memoria).")
        elif carpeta is None:
            print("El bloque MEMORIA-UNICA del CLAUDE.md no tiene la forma de la versión 1 (¿lo cambiaron a "
                  "mano?): no se toca.")
        elif not (actual and misma_carpeta(actual, carpeta)):
            print("El bloque MEMORIA-UNICA se deja: autoMemoryDirectory no apunta a la misma memoria "
                  "(sin el bloque, las sesiones dejarían de verla).")
        else:
            print("Se saca del CLAUDE.md el bloque MEMORIA-UNICA (autoMemoryDirectory ya carga esa memoria).")
            if a.aplicar:
                copia = cmd.with_name(f"CLAUDE.md.antes-de-v2-{hoy}")
                shutil.copy2(cmd, copia)
                cmd.write_text(nuevo, encoding="utf-8")
                print(f"  copia de antes: {copia}")

    print()
    print("No se tocó: el resto del CLAUDE.md, el perfil, la memoria, las skills propias, "
          "~/.claude/remote-control ni la carpeta del kit.")
    if not a.aplicar:
        print("Para hacerlo: el mismo comando con --aplicar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
