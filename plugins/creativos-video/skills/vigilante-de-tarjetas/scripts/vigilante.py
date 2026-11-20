#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vigilante.py · Al conectar una tarjeta de cámara, avisa y ofrece copiarla a los discos guardados
(o la copia sola, si la persona lo dejó así). Usa el motor de la skill descargar-tarjeta (descarga.py).

Modos:
  --una-vez   revisa las tarjetas conectadas y termina. En Mac lo lanza launchd cada vez que se conecta un disco.
  --bucle     revisa cada 5 s mientras la sesión está abierta. En Windows lo lanza el Programador de tareas.
  --simular   dice qué haría con cada tarjeta, sin avisos ni copias.
  --estado    configuración, tarjetas conectadas y qué haría con cada una.

Nunca borra ni formatea nada. Si no contestan la pregunta en 10 minutos, no copia.
Registro: ~/MI-SISTEMA-CLAUDE/respaldo-material/vigilante.log
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
for _cand in (AQUI, AQUI.parent.parent / "descargar-tarjeta" / "scripts"):
    if (_cand / "descarga.py").exists():
        sys.path.insert(0, str(_cand))
        MOTOR = _cand / "descarga.py"
        break
else:
    sys.exit("No encuentro descarga.py (el motor de descargar-tarjeta).")
import descarga as D  # noqa: E402

ES_MAC, ES_WIN = D.ES_MAC, D.ES_WIN
ESPERA_RESPUESTA = 600            # segundos para contestar; si no contestan, no se copia
POSPONER_HORAS = 12               # «Ahora no» = no vuelve a preguntar por esa misma tarjeta en 12 h
AVISO_YA_COPIADA_HORAS = 6


def carpeta() -> Path:
    d = D.dir_sistema() / "vigilante"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log(msg):
    p = D.dir_sistema() / "vigilante.log"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > 1_000_000:
            os.replace(p, p.with_name("vigilante.log.1"))
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{D.ahora():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


def _leer(nombre):
    try:
        return json.loads((carpeta() / nombre).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _guardar(nombre, data):
    D.guardar_json(carpeta() / nombre, data)


# ───────────────────────────── avisos y preguntas ─────────────────────────────

def _sin_avisos():
    return bool(os.environ.get("VIGILANTE_SIN_AVISOS")) or SIMULAR


def _as(texto):      # cadena para AppleScript
    return '"' + str(texto).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ps(texto):      # cadena para PowerShell
    return "'" + str(texto).replace("'", "''") + "'"


def _powershell(script, esperar=True, timeout=None):
    args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-Command", script]
    flags = 0x08000000 if ES_WIN else 0      # CREATE_NO_WINDOW
    if esperar:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=flags)
    return subprocess.Popen(args, creationflags=flags)


def avisar(titulo, texto):
    log(f"AVISO {titulo}: {texto}")
    if _sin_avisos():
        print(f"[aviso] {titulo}: {texto}")
        return
    try:
        if ES_MAC:
            subprocess.run(["osascript", "-e", f'display notification {_as(texto)} with title {_as(titulo)} '
                                               f'sound name "Glass"'], timeout=20)
        elif ES_WIN:
            _powershell("Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
                        "$n=New-Object System.Windows.Forms.NotifyIcon; "
                        "$n.Icon=[System.Drawing.SystemIcons]::Information; $n.Visible=$true; "
                        f"$n.ShowBalloonTip(10000,{_ps(titulo)},{_ps(texto)},'Info'); Start-Sleep 8; $n.Dispose()",
                        esperar=False)
    except Exception as e:
        log(f"no se pudo mostrar el aviso: {e}")


def preguntar(titulo, texto, si="Copiar", no="Ahora no"):
    """True = sí · False = no · None = no contestaron a tiempo."""
    log(f"PREGUNTA {titulo}: {texto}")
    if _sin_avisos():
        r = os.environ.get("VIGILANTE_RESPUESTA", "no").lower()
        print(f"[pregunta] {titulo}: {texto} → respuesta de prueba: {r}")
        return True if r in ("si", "sí", "s") else (None if r == "nada" else False)
    try:
        if ES_MAC:
            r = subprocess.run(["osascript", "-e",
                                f"display dialog {_as(texto)} with title {_as(titulo)} buttons {{{_as(no)}, {_as(si)}}} "
                                f"default button {_as(si)} with icon note giving up after {ESPERA_RESPUESTA}"],
                               capture_output=True, text=True, timeout=ESPERA_RESPUESTA + 60)
            if "gave up:true" in r.stdout:
                return None
            m = re.search(r"button returned:([^,\n]+)", r.stdout)
            return bool(m and m.group(1).strip() == si)
        if ES_WIN:
            r = _powershell(f"$s=New-Object -ComObject WScript.Shell; "
                            f"$r=$s.Popup({_ps(texto + chr(10) + chr(10) + 'Sí = ' + si + ' · No = ' + no)},"
                            f"{ESPERA_RESPUESTA},{_ps(titulo)},4+32+4096); Write-Output $r",
                            timeout=ESPERA_RESPUESTA + 60)
            v = (r.stdout or "").strip()
            return None if v == "-1" else v == "6"
    except Exception as e:
        log(f"no se pudo preguntar: {e}")
    return None


def abrir(ruta):
    if _sin_avisos():
        return
    try:
        if ES_MAC:
            subprocess.run(["open", str(ruta)], timeout=20)
        elif ES_WIN:
            os.startfile(str(ruta))   # noqa: S606
    except Exception:
        pass


# ───────────────────────────── lógica ─────────────────────────────

def _ignorada(v, vig):
    nombres = {str(x).strip().lower() for x in vig.get("ignorar") or []}
    return (v.get("nombre") or "").lower() in nombres or (v.get("uuid") or "").lower() in nombres


def _vigilada(v, vig):
    lista = vig.get("vigilar", "todas")
    if lista in ("todas", None, []):
        return True
    cam = v.get("camara") or {}
    return cam.get("id") in lista or any(t in lista for t in cam.get("tambien", []))


def revisar(cfg):
    """Lista de (volumen, archivos, firma, situacion, motivo) de cada tarjeta conectada."""
    vig = cfg.get("vigilante") or {}
    salida = []
    for v in D.detectar(contar=False):
        if not v.get("camara"):
            continue
        if v.get("es_destino_guardado"):
            salida.append((v, [], None, "omitir", "es uno de los discos de destino"))
            continue
        if _ignorada(v, vig):
            salida.append((v, [], None, "omitir", "está en la lista de discos a ignorar"))
            continue
        if not _vigilada(v, vig):
            salida.append((v, [], None, "omitir", "ese tipo de tarjeta no está en la lista a vigilar"))
            continue
        archivos, _ = D.listar_origen(v["ruta"])
        if not archivos:
            salida.append((v, [], None, "omitir", "está vacía"))
            continue
        firma = D.firma_de(archivos)
        estado, rec = D.estado_en_historial(archivos, firma)
        if estado == "respaldada":
            salida.append((v, archivos, firma, "ya_copiada", rec))
            continue
        pos = _leer("pospuestas.json").get(firma)
        if pos and time.time() < pos:
            salida.append((v, archivos, firma, "pospuesta", "dijeron «Ahora no» hace poco"))
            continue
        salida.append((v, archivos, firma, "nueva" if estado is None else "con_clips_nuevos", rec))
    return salida


def _faltan_destinos(cfg):
    faltan = []
    for d in cfg.get("destinos", []):
        nombre = D.disco_conectado(d)
        if nombre:
            faltan.append(nombre)
        elif not os.path.isdir(D.punto_de_montaje(d)):
            faltan.append(os.path.basename(d.rstrip("/\\")) or d)
    return faltan


def _bloqueo(firma):
    p = carpeta() / f"copiando-{firma[:12]}.lock"
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return p
    except FileExistsError:
        try:
            pid = int(p.read_text() or 0)
            os.kill(pid, 0)          # sigue vivo: otra copia en curso
            return None
        except (ValueError, OSError):
            try:
                p.unlink()           # quedó de una copia que se cortó
            except OSError:
                return None
            return _bloqueo(firma)


def describir(v, archivos):
    clips = sum(1 for a in archivos if a.tipo == "video")
    fotos = sum(1 for a in archivos if a.tipo == "foto")
    partes = [v["camara"]["nombre"].split(" (")[0]]
    if clips:
        partes.append(f"{clips} clips")
    if fotos:
        partes.append(f"{fotos} fotos")
    partes.append(D.tam(sum(a.tam for a in archivos)))
    return ", ".join(partes)


def copiar(v, archivos, firma, cfg, situacion):
    modo = (cfg.get("vigilante") or {}).get("modo", "preguntar")
    nombre = v.get("nombre") or os.path.basename(v["ruta"])
    destinos_txt = " y ".join(os.path.basename(D.punto_de_montaje(d).rstrip("/\\")) or d
                              for d in cfg.get("destinos", []))
    faltan = _faltan_destinos(cfg)
    if faltan:
        avisar("Vigilante de tarjetas", f"Llegó la tarjeta {nombre}, pero falta conectar {', '.join(faltan)}. "
                                        "Conéctalo y la copio.")
        return "faltan_discos"
    nuevos = ""
    if situacion == "con_clips_nuevos":
        nuevos = " Tiene material nuevo desde la última copia: se copia solo lo que falta."
    texto = (f"Se conectó la tarjeta {nombre} ({describir(v, archivos)}).{nuevos}\n\n"
             f"¿La copio a {destinos_txt} (proyecto {cfg.get('proyecto') or '—'}) y verifico las copias?")
    if modo != "automatico":
        r = preguntar("Vigilante de tarjetas", texto)
        if r is not True:
            pos = _leer("pospuestas.json")
            pos[firma] = time.time() + POSPONER_HORAS * 3600
            _guardar("pospuestas.json", pos)
            log(f"{nombre}: no se copia ({'no contestaron' if r is None else 'Ahora no'})")
            return "no"
    else:
        avisar("Vigilante de tarjetas", f"Copiando la tarjeta {nombre} a {destinos_txt}…")
    if SIMULAR:
        print(f"[simular] copiaría {v['ruta']} a {', '.join(cfg.get('destinos', []))}")
        return "simulado"
    candado = _bloqueo(firma)
    if not candado:
        log(f"{nombre}: ya hay una copia en curso")
        return "en_curso"
    try:
        log(f"{nombre}: empieza la copia")
        r = subprocess.run([sys.executable, str(MOTOR), "copiar", "--origen", v["ruta"], "--json-final",
                            "--cada", "30"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        for linea in (r.stdout + r.stderr).splitlines():
            log(f"   {linea}")
        res = {}
        for linea in r.stdout.splitlines():
            if linea.startswith("RESULTADO="):
                res = json.loads(linea[len("RESULTADO="):])
        if res.get("ok"):
            msg = (f"✅ {res.get('tarjeta')}: {res.get('archivos')} archivos ({D.tam(res.get('bytes'))}) copiados "
                   f"y verificados en {len(res.get('destinos', []))} discos. Ya se puede formatear la tarjeta "
                   "en la cámara.")
            avisar("Tarjeta copiada", msg)
            if modo != "automatico" and res.get("informe"):
                if preguntar("Tarjeta copiada", msg, si="Abrir informe", no="Listo"):
                    abrir(res["informe"])
            return "ok"
        avisar("❌ No formatees la tarjeta", f"{nombre}: {res.get('motivo') or 'la copia no terminó bien'} "
                                           "(detalle en vigilante.log)")
        return "error"
    finally:
        try:
            candado.unlink()
        except OSError:
            pass


def una_vez(max_vueltas=20):
    cfg = D.leer_config()
    if not cfg.get("destinos"):
        log("sin configuración: faltan los discos de destino")
        if any(v.get("camara") for v in D.detectar(contar=False)):
            avisar("Vigilante de tarjetas", "Hay una tarjeta conectada, pero todavía no elegiste los discos de "
                                            "destino. Pídele a Claude: «configura el vigilante».")
        return
    hechas = set()
    for _ in range(max_vueltas):
        filas = revisar(cfg)
        pendientes = [x for x in filas if x[3] in ("nueva", "con_clips_nuevos") and x[2] not in hechas]
        for v, _arch, firma, situacion, rec in filas:
            if situacion == "ya_copiada" and firma not in hechas:
                avisadas = _leer("avisadas.json")
                if time.time() - avisadas.get(firma, 0) > AVISO_YA_COPIADA_HORAS * 3600:
                    cuando = ""
                    try:
                        f = D.dt.datetime.strptime((rec or {}).get("fecha_utc", ""), "%Y-%m-%dT%H:%M:%SZ")
                        cuando = " el " + D.fecha_legible(f.replace(tzinfo=D.dt.timezone.utc).astimezone())
                    except ValueError:
                        pass
                    avisar("Tarjeta ya copiada", f"{v.get('nombre')} ya está copiada y verificada{cuando}. "
                                                 "Se puede formatear en la cámara.")
                    avisadas[firma] = time.time()
                    _guardar("avisadas.json", avisadas)
                hechas.add(firma)
        if not pendientes:
            return
        v, archivos, firma, situacion, _rec = pendientes[0]
        hechas.add(firma)
        copiar(v, archivos, firma, cfg, situacion)
        cfg = D.leer_config()         # por si cambió el proyecto mientras copiaba


def bucle(cada=5.0):
    pid_p = carpeta() / "bucle.pid"
    try:
        viejo = int(pid_p.read_text() or 0)
        if viejo and viejo != os.getpid():
            os.kill(viejo, 0)
            log("ya hay un vigilante en bucle corriendo; salgo")
            return
    except (ValueError, OSError):
        pass
    pid_p.write_text(str(os.getpid()))
    parar = carpeta() / "PARAR"
    if parar.exists():
        parar.unlink()
    log(f"bucle iniciado (pid {os.getpid()})")
    vistos = None
    try:
        while not parar.exists():
            actuales = set(D.volumenes_montados())
            if actuales != vistos:
                vistos = actuales
                try:
                    una_vez()
                except Exception as e:      # el vigilante no se cae por una tarjeta rara
                    log(f"error revisando: {e!r}")
            time.sleep(cada)
    finally:
        log("bucle detenido")
        try:
            pid_p.unlink()
        except OSError:
            pass


def estado():
    cfg = D.leer_config()
    vig = cfg.get("vigilante") or {}
    print(f"Configuración: {D.dir_sistema() / 'config.json'}")
    print(f"  proyecto: {cfg.get('proyecto') or '—'} · destinos: {', '.join(cfg.get('destinos', [])) or '—'}")
    print(f"  modo: {vig.get('modo', 'preguntar')} · vigilar: {vig.get('vigilar', 'todas')} · "
          f"ignorar: {', '.join(vig.get('ignorar') or []) or '—'}")
    faltan = _faltan_destinos(cfg)
    if faltan:
        print(f"  ⚠️  destinos sin conectar: {', '.join(faltan)}")
    filas = revisar(cfg)
    if not filas:
        print("No hay tarjetas de cámara conectadas.")
    for v, archivos, _firma, situacion, motivo in filas:
        txt = {"nueva": "la ofrecería para copiar", "con_clips_nuevos": "ofrecería copiar lo nuevo",
               "ya_copiada": "ya está copiada y verificada (solo avisa)", "pospuesta": "pospuesta (dijeron Ahora no)",
               "omitir": f"no la toca: {motivo}"}[situacion]
        print(f"🎞️  {v.get('nombre')} ({v['ruta']}) · {v['camara']['nombre']} → {txt}")


SIMULAR = False


def main():
    global SIMULAR
    D._consola_utf8()
    ap = argparse.ArgumentParser(description="Vigilante de tarjetas de cámara")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--una-vez", action="store_true")
    g.add_argument("--bucle", action="store_true")
    g.add_argument("--estado", action="store_true")
    ap.add_argument("--simular", action="store_true")
    a = ap.parse_args()
    SIMULAR = a.simular
    if a.estado:
        estado()
    elif a.bucle:
        bucle()
    else:
        try:
            una_vez()
        except Exception as e:
            log(f"error: {e!r}")
            raise


if __name__ == "__main__":
    main()
