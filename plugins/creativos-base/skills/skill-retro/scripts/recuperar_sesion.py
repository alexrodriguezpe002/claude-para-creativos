#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recupera una sesión completa de Claude Code para el retro (skill `skill-retro`).

Lee el archivo guardado de la sesión (~/.claude/projects/<carpeta>/<id>.jsonl), con sus
subagentes, y escribe una versión legible en un archivo LOCAL (carpeta temporal del sistema):
lo que dijo la persona, lo que respondió Claude, cada herramienta usada y los errores. Marca
dónde hubo compactación (desde ahí Claude trabajó con un resumen) y lo que se recortó.

Privacidad: no sube nada a ningún lado. Tapa claves, contraseñas, tokens, correos y teléfonos
antes de escribir. El archivo de salida queda en la carpeta temporal; bórralo al terminar.

Uso:
  recuperar_sesion.py --buscar "frase que dijo la persona"   elige la sesión por esa frase
  recuperar_sesion.py --id <id de la sesión>                   una sesión concreta
  recuperar_sesion.py --actual                                 la sesión en la que corre
Opciones:
  --salida ARCHIVO     dónde escribir (por defecto, la carpeta temporal del sistema)
  --max N              caracteres máximos por resultado de herramienta (por defecto 600)

Códigos de salida: 0 listo · 2 no encontré ninguna sesión · 3 hay varias: elige una con --id.
En Windows: `py -3 recuperar_sesion.py …`.
"""
import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECTS = Path(os.environ.get("RETRO_PROJECTS_DIR",
                               str(Path(os.path.expanduser("~")) / ".claude" / "projects")))

# --------------------------------------------------------------------- tapar datos
SECRETOS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "<clave privada>"),
    (re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{16,}"), "<clave>"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"), "<token>"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "<token>"),
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"), "<token>"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<clave>"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "<clave>"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"), "Bearer <token>"),
    (re.compile(r"(?i)\b(password|passwd|pwd|contraseña|clave|token|secret|api[_-]?key)"
                r"(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|\S+)"), r"\1\2<tapado>"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "<correo>"),
    (re.compile(r"(?<![\w/.-])\+?\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}(?![\w/.-])"),
     "<teléfono>"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "<número>"),
]


def tapar(texto, cuenta):
    for rx, rep in SECRETOS:
        texto, n = rx.subn(rep, texto)
        cuenta[0] += n
    return texto


# ----------------------------------------------------------------------- sesiones
def sesiones():
    out = []
    try:
        for d in PROJECTS.iterdir():
            if d.is_dir():
                out += [f for f in d.glob("*.jsonl")]
    except OSError:
        pass
    return out


def datos_de(f):
    """(fecha de inicio, carpeta abierta, título) leyendo el comienzo y el final del archivo."""
    inicio, cwd, titulo = "", "", ""
    try:
        with f.open("r", encoding="utf-8", errors="ignore") as fh:
            for k, line in enumerate(fh):
                if k > 200:
                    break
                if not inicio:
                    m = re.search(r'"timestamp":"([^"]+)"', line)
                    inicio = m.group(1) if m else ""
                if not cwd:
                    m = re.search(r'"cwd":"((?:[^"\\]|\\.)*)"', line)
                    if m:
                        cwd = json.loads('"' + m.group(1) + '"')
        size = f.stat().st_size
        with f.open("rb") as fh:
            fh.seek(max(0, size - 300_000))
            tail = fh.read().decode("utf-8", "ignore")
        t = re.findall(r'"customTitle":"((?:[^"\\]|\\.)*)"', tail)
        if t:
            titulo = json.loads('"' + t[-1] + '"')
    except Exception:
        pass
    return inicio, cwd, titulo


def hora(ts):
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "?"


def buscar(frase):
    """Sesiones cuyo texto de la persona contiene la frase (sin mayúsculas ni tildes)."""
    import unicodedata

    def fold(s):
        s = unicodedata.normalize("NFKD", s or "")
        return "".join(c for c in s if not unicodedata.combining(c)).lower()

    objetivo = fold(frase)
    hits = []
    for f in sesiones():
        n = 0
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if '"type":"user"' not in line:
                        continue
                    if objetivo in fold(line):
                        try:
                            d = json.loads(line)
                        except Exception:
                            continue
                        if objetivo in fold(texto_de(d.get("message"))):
                            n += 1
        except OSError:
            continue
        if n:
            hits.append((f, n))
    return hits


# ------------------------------------------------------------------------ lectura
def texto_de(msg):
    if not isinstance(msg, dict):
        return ""
    c = msg.get("content")
    if isinstance(c, str):
        return c
    partes = []
    if isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and b.get("type") == "text":
                partes.append(b.get("text") or "")
    return "\n".join(partes)


def corto(s, n):
    s = s or ""
    if len(s) <= n:
        return s, 0
    return s[:n] + f" [… recortado: {len(s) - n} caracteres]", 1


def entrada_herramienta(nombre, inp):
    if not isinstance(inp, dict):
        return str(inp)
    if nombre == "Bash":
        return inp.get("command") or ""
    for k in ("file_path", "notebook_path", "pattern", "url", "query", "description", "prompt",
              "skill"):
        if inp.get(k):
            return f"{k}: {inp[k]}"
    return json.dumps(inp, ensure_ascii=False)[:300]


def volcar(f, maxres, cuenta, stats):
    """Líneas legibles de un archivo de sesión (o de subagente)."""
    out = []
    try:
        fh = f.open("r", encoding="utf-8", errors="ignore")
    except OSError as e:
        return [f"(no pude leer {f.name}: {e})"]
    with fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = d.get("type")
            h = hora(d.get("timestamp") or "")
            if t == "system" and d.get("subtype") == "compact_boundary":
                stats["compactaciones"] += 1
                out.append(f"\n--- [{h}] COMPACTACIÓN: desde acá Claude trabajó con un resumen de lo "
                           "anterior; lo de arriba está completo en este archivo ---\n")
                continue
            if t == "user":
                msg = d.get("message") or {}
                c = msg.get("content")
                if d.get("isCompactSummary"):
                    txt, r = corto(texto_de(msg), 1500)
                    stats["recortes"] += r
                    out.append(f"[{h}] (RESUMEN AUTOMÁTICO DE LA COMPACTACIÓN)\n{tapar(txt, cuenta)}")
                    continue
                if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result"
                                               for b in c):
                    for b in c:
                        if not (isinstance(b, dict) and b.get("type") == "tool_result"):
                            continue
                        res = b.get("content")
                        if isinstance(res, list):
                            res = "\n".join(x.get("text", "") for x in res if isinstance(x, dict))
                        res = str(res or "")
                        err = bool(b.get("is_error"))
                        txt, r = corto(res, maxres if not err else maxres * 2)
                        stats["recortes"] += r
                        etiqueta = "RESULTADO (ERROR)" if err else "resultado"
                        if err:
                            stats["errores"] += 1
                        out.append(f"    {etiqueta}: {tapar(txt, cuenta)}")
                    continue
                if d.get("isMeta"):
                    continue
                txt = texto_de(msg)
                if txt.strip():
                    stats["persona"] += 1
                    out.append(f"\n[{h}] PERSONA: {tapar(txt, cuenta)}")
            elif t == "assistant":
                msg = d.get("message") or {}
                for b in msg.get("content") or []:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text" and (b.get("text") or "").strip():
                        txt, r = corto(b["text"], 4000)
                        stats["recortes"] += r
                        out.append(f"[{h}] CLAUDE: {tapar(txt, cuenta)}")
                    elif b.get("type") == "tool_use":
                        stats["herramientas"] += 1
                        nombre = b.get("name") or "?"
                        txt, r = corto(entrada_herramienta(nombre, b.get("input")), 800)
                        stats["recortes"] += r
                        out.append(f"[{h}] HERRAMIENTA {nombre}: {tapar(txt, cuenta)}")
    return out


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Recupera una sesión de Claude Code para el retro.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--buscar")
    g.add_argument("--id")
    g.add_argument("--actual", action="store_true")
    ap.add_argument("--salida")
    ap.add_argument("--max", type=int, default=600)
    a = ap.parse_args()

    if a.buscar:
        hits = buscar(a.buscar)
        if not hits:
            print(f"No encontré ninguna sesión donde la persona haya escrito: «{a.buscar}».")
            print("Prueba con otra frase, o usa --actual para la sesión de ahora.")
            return 2
        if len(hits) > 1:
            print(f"Hay {len(hits)} sesiones con esa frase. No elijo a ciegas: dime cuál (--id).")
            for f, n in sorted(hits, key=lambda x: datos_de(x[0])[0], reverse=True)[:15]:
                ini, cwd, tit = datos_de(f)
                print(f"- {f.stem} · {hora(ini)} · {tit or '(sin título)'} · carpeta: {cwd or '?'}"
                      f" · {n} coincidencia(s)")
            return 3
        archivo = hits[0][0]
    else:
        sid = a.id or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
        if not sid:
            print("No sé cuál es la sesión actual (falta CLAUDE_CODE_SESSION_ID). Usa --buscar.")
            return 2
        archivo = next((f for f in sesiones() if f.stem == sid), None)
        if archivo is None:
            print(f"No encontré el archivo de la sesión {sid} en {PROJECTS}.")
            print("Puede ser una sesión de Cowork o de la web (no se guardan acá): el retro será "
                  "parcial, con lo que hay en esta conversación.")
            return 2

    sid = archivo.stem
    ini, cwd, tit = datos_de(archivo)
    cuenta = [0]
    stats = {"persona": 0, "herramientas": 0, "errores": 0, "compactaciones": 0, "recortes": 0}
    cuerpo = volcar(archivo, a.max, cuenta, stats)
    subdir = archivo.parent / sid / "subagents"
    subs = sorted(subdir.glob("*.jsonl")) if subdir.is_dir() else []
    for sf in subs:
        cuerpo.append(f"\n\n## Subagente {sf.stem}\n")
        cuerpo += volcar(sf, a.max, cuenta, stats)

    cab = [f"# Sesión {sid}",
           f"- Título: {tit or '(sin título)'}",
           f"- Empezó: {hora(ini)} · carpeta abierta: {cwd or '?'}",
           f"- Mensajes de la persona: {stats['persona']} · herramientas: {stats['herramientas']} · "
           f"errores: {stats['errores']} · subagentes: {len(subs)}",
           f"- Compactaciones: {stats['compactaciones']} · textos recortados: {stats['recortes']} · "
           f"datos tapados (claves, correos, teléfonos): {cuenta[0]}",
           "- Archivo local y temporal: bórralo al terminar el retro.", ""]
    salida = Path(a.salida) if a.salida else Path(tempfile.gettempdir()) / f"retro-{sid[:8]}.md"
    salida.write_text("\n".join(cab + cuerpo) + "\n", encoding="utf-8")
    print("\n".join(cab[:-2]))
    print(f"Escrito en: {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
