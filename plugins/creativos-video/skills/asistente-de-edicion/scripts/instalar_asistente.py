#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
instalar_asistente.py · Instala, actualiza, revisa o quita el asistente de edición. Solo se corre con el OK de la persona.

  estado        ¿está instalado? ¿qué versión? ¿qué vigila?
  instalar      copia el asistente y el motor de sincronizar-audio a ~/MI-SISTEMA-CLAUDE/asistente-edicion/bin y lo
                deja corriendo:
                  Mac: un agente de launchd que revisa cada 2 minutos y cada vez que cambia la carpeta vigilada.
                  Windows: una tarea del Programador de tareas al iniciar sesión (o, si Windows no deja, un acceso en
                           la carpeta Inicio) que revisa cada minuto.
  actualizar    vuelve a copiarlo (después de actualizar el kit o de cambiar la carpeta vigilada) y lo recarga.
  desinstalar   lo apaga y lo quita. La configuración, el registro y los timelines quedan.
  --python      el Python con numpy que lo va a correr (por defecto, el del entorno propio ~/.claude/venv-video)
  --simular     muestra lo que haría, sin instalar nada.

Por qué se copia afuera del plugin: el plugin vive en una carpeta que cambia con cada actualización del kit; el
sistema necesita una ruta fija para lanzar el asistente.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ASISTENTE = AQUI / "asistente.py"
MOTOR = next((c / "sincronizar.py" for c in (AQUI, AQUI.parent.parent / "sincronizar-audio" / "scripts")
              if (c / "sincronizar.py").exists()), None)
ES_MAC = sys.platform == "darwin"
ES_WIN = os.name == "nt"
ETIQUETA = "com.creativos.asistente-edicion"
TAREA_WIN = "Asistente de edicion"


def _consola_utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def version_kit():
    m = re.search(r'^VERSION = "([^"]+)"', ASISTENTE.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "?"


def dir_sistema() -> Path:
    d = os.environ.get("ASISTENTE_DIR")
    return Path(d).expanduser() if d else Path.home() / "MI-SISTEMA-CLAUDE" / "asistente-edicion"


def rutas():
    base = dir_sistema()
    agentes = Path(os.environ.get("LAUNCH_AGENTS_DIR") or (Path.home() / "Library" / "LaunchAgents"))
    inicio_win = Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / \
        "Programs" / "Startup" / "asistente-de-edicion.vbs"
    return {"base": base, "bin": base / "bin", "plist": agentes / f"{ETIQUETA}.plist", "vbs": inicio_win,
            "log_launchd": base / "asistente-launchd.log"}


def leer_config():
    import json
    try:
        return json.loads((dir_sistema() / "config.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def version_instalada():
    try:
        return (rutas()["bin"] / "VERSION").read_text().strip()
    except OSError:
        return None


def python_con_numpy(pedido=None):
    """El Python que corre el asistente: el pedido, el del entorno propio o este. Tiene que tener numpy."""
    cand = [pedido] if pedido else []
    venv = Path.home() / ".claude" / "venv-video"
    cand += [str(venv / "Scripts" / "python.exe")] if ES_WIN else [str(venv / "bin" / "python")]
    cand.append(sys.executable)
    for c in cand:
        if c and Path(c).exists():
            try:
                if subprocess.run([c, "-c", "import numpy"], capture_output=True, timeout=60).returncode == 0:
                    return c
            except Exception:
                pass
    return None


def copiar_bin(simular):
    r = rutas()
    if simular:
        print(f"[simular] copiaría asistente.py y sincronizar.py a {r['bin']}")
        return
    r["bin"].mkdir(parents=True, exist_ok=True)
    shutil.copy2(ASISTENTE, r["bin"] / "asistente.py")
    shutil.copy2(MOTOR, r["bin"] / "sincronizar.py")
    (r["bin"] / "VERSION").write_text(version_kit())


def _launchctl(*args):
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=30)


def instalar_mac(py, cfg, simular):
    r = rutas()
    entorno = {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", "PYTHONIOENCODING": "utf-8"}
    if os.environ.get("ASISTENTE_DIR"):
        entorno["ASISTENTE_DIR"] = os.environ["ASISTENTE_DIR"]
    plist = {"Label": ETIQUETA,
             "ProgramArguments": [py, str(r["bin"] / "asistente.py"), "--una-vez"],
             "StartInterval": 120, "RunAtLoad": True, "WatchPaths": [cfg["carpeta"]],
             "StandardOutPath": str(r["log_launchd"]), "StandardErrorPath": str(r["log_launchd"]),
             "EnvironmentVariables": entorno}
    datos = plistlib.dumps(plist)
    uid = os.getuid()
    if simular:
        print(f"[simular] escribiría el agente en {r['plist']} y lo cargaría con: launchctl bootstrap gui/{uid} "
              f"{r['plist']}")
        print(f"[simular] corre «{py} asistente.py --una-vez» cada 2 min y cuando cambia {cfg['carpeta']}")
        return True
    r["plist"].parent.mkdir(parents=True, exist_ok=True)
    _launchctl("bootout", f"gui/{uid}/{ETIQUETA}")            # por si había uno viejo
    r["plist"].write_bytes(datos)
    res = _launchctl("bootstrap", f"gui/{uid}", str(r["plist"]))
    if res.returncode != 0:
        res = _launchctl("load", "-w", str(r["plist"]))
    if res.returncode != 0:
        print(f"❌ launchd no aceptó el agente: {res.stderr.strip() or res.stdout.strip()}")
        return False
    print(f"✅ Asistente instalado: revisa {cfg['carpeta']} cada 2 minutos y cada vez que cambia (python: {py}).")
    print("   La primera vez que lee un disco externo, macOS puede pedir permiso para que python acceda a "
          "«volúmenes extraíbles» (o a Documentos o Escritorio): hay que tocar «Permitir».")
    return True


def _pythonw(py):
    w = Path(py).with_name("pythonw.exe")
    return str(w if w.exists() else Path(py))


def instalar_win(py, simular):
    r = rutas()
    py = _pythonw(py)
    script = str(r["bin"] / "asistente.py")
    ps = (f"$a=New-ScheduledTaskAction -Execute '{py}' -Argument '\"{script}\" --bucle'; "
          "$t=New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME; "
          "$s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
          "-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew; "
          f"Register-ScheduledTask -TaskName '{TAREA_WIN}' -Action $a -Trigger $t -Settings $s "
          "-Description 'Arma el timeline cuando termina la copia del material (kit creativos)' -Force | Out-Null; "
          f"Start-ScheduledTask -TaskName '{TAREA_WIN}'")
    if simular:
        print(f"[simular] registraría la tarea «{TAREA_WIN}» con PowerShell:\n  {ps}")
        return True
    res = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                         capture_output=True, text=True, timeout=60)
    if res.returncode == 0:
        print("✅ Asistente instalado en el Programador de tareas: corre al iniciar sesión y ya está corriendo.")
        return True
    r["vbs"].parent.mkdir(parents=True, exist_ok=True)
    r["vbs"].write_text(f'CreateObject("Wscript.Shell").Run """{py}"" ""{script}"" --bucle", 0, False\r\n',
                        encoding="utf-8")
    subprocess.Popen(["wscript", str(r["vbs"])])
    print("✅ Asistente instalado en la carpeta Inicio (Windows no dejó crear la tarea): corre al iniciar sesión y "
          "ya está corriendo.")
    return True


def _parar_bucle_win(espera=90):
    """Windows: el bucle lee el archivo PARAR cada minuto y se cierra solo; se espera a que suelte su pid."""
    import time
    r = rutas()
    r["base"].mkdir(parents=True, exist_ok=True)
    (r["base"] / "PARAR").write_text("1")
    pid = r["base"] / "bucle.pid"
    t0 = time.time()
    while pid.exists() and time.time() - t0 < espera:
        time.sleep(2)


def desinstalar(simular):
    r = rutas()
    if simular:
        print(f"[simular] quitaría {r['plist'] if ES_MAC else TAREA_WIN} y la carpeta {r['bin']}")
        return
    if ES_MAC:
        _launchctl("bootout", f"gui/{os.getuid()}/{ETIQUETA}")
        try:
            r["plist"].unlink()
        except OSError:
            pass
    elif ES_WIN:
        _parar_bucle_win()
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Unregister-ScheduledTask -TaskName '{TAREA_WIN}' -Confirm:$false"],
                       capture_output=True, timeout=60)
        try:
            r["vbs"].unlink()
        except OSError:
            pass
    shutil.rmtree(r["bin"], ignore_errors=True)
    print(f"✅ Asistente quitado. La configuración, el registro y los timelines quedan (en {r['base']} y en la "
          "carpeta de salida): no se borró nada más.")


def estado():
    r = rutas()
    v = version_instalada()
    cfg = leer_config()
    if ES_MAC:
        cargado = _launchctl("print", f"gui/{os.getuid()}/{ETIQUETA}").returncode == 0
        instalado = r["plist"].exists()
    elif ES_WIN:
        q = subprocess.run(["schtasks", "/Query", "/TN", TAREA_WIN], capture_output=True, text=True)
        instalado = q.returncode == 0 or r["vbs"].exists()
        cargado = instalado
    else:
        instalado = cargado = False
    print(f"Asistente de edición: {'✅ instalado' if instalado else '❌ no instalado'}{' y activo' if cargado else ''}"
          f" · versión instalada {v or '—'} · versión del kit {version_kit()}")
    if v and v != version_kit():
        print("   ⚠️  El kit tiene una versión más nueva: correr «actualizar».")
    if ES_MAC and instalado:
        try:
            vigila = plistlib.loads(r["plist"].read_bytes()).get("WatchPaths", [None])[0]
        except Exception:
            vigila = None
        if cfg.get("carpeta") and vigila and vigila != cfg["carpeta"]:
            print(f"   ⚠️  El agente vigila {vigila} pero la configuración dice {cfg['carpeta']}: correr «actualizar».")
    print(f"   Vigila: {cfg.get('carpeta') or '—'} · timeline en: {cfg.get('salida') or '—'}")
    print(f"   Registro: {r['base'] / 'asistente.log'}")


def main():
    _consola_utf8()
    ap = argparse.ArgumentParser(description="Instala o quita el asistente de edición")
    ap.add_argument("accion", choices=["estado", "instalar", "actualizar", "desinstalar"])
    ap.add_argument("--python")
    ap.add_argument("--simular", action="store_true")
    a = ap.parse_args()
    if MOTOR is None:
        print("❌ No encuentro sincronizar.py (la skill sincronizar-audio del mismo plugin).")
        return 2
    if a.accion == "estado":
        estado()
        return 0
    if a.accion == "desinstalar":
        desinstalar(a.simular)
        return 0
    cfg = leer_config()
    if not cfg.get("carpeta") or not cfg.get("salida"):
        print("❌ Primero hay que configurar qué carpeta vigilar y dónde dejar el timeline "
              "(asistente.py config guardar --carpeta … --salida …).")
        return 2
    py = python_con_numpy(a.python)
    if not py:
        print("❌ No encuentro un Python con numpy. Preparar el entorno propio (skill sincronizar-audio, «Preparar») "
              "y volver a correr esto.")
        return 2
    copiar_bin(a.simular)
    if ES_MAC:
        ok = instalar_mac(py, cfg, a.simular)
    elif ES_WIN:
        if a.accion == "actualizar" and not a.simular:
            _parar_bucle_win()                                 # el bucle viejo tiene el código anterior en memoria
        ok = instalar_win(py, a.simular)
    else:
        print("Este sistema no está soportado (solo Mac y Windows).")
        return 1
    if ok and a.accion == "actualizar":
        print(f"✅ Asistente actualizado a la versión {version_kit()}.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
