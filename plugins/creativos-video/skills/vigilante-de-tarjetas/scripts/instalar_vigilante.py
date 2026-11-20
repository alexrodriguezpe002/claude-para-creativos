#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
instalar_vigilante.py · Instala, actualiza, revisa o quita el vigilante de tarjetas. Solo se corre con el OK de la persona.

  estado        ¿está instalado? ¿qué versión? ¿qué configuración usa?
  instalar      copia el vigilante a ~/MI-SISTEMA-CLAUDE/respaldo-material/bin y lo deja corriendo:
                  Mac: un agente de launchd que se activa cada vez que se conecta un disco (StartOnMount).
                  Windows: una tarea del Programador de tareas al iniciar sesión (o, si Windows no deja,
                           un acceso en la carpeta Inicio) que revisa cada 5 s.
  actualizar    vuelve a copiar el vigilante (después de actualizar el kit).
  desinstalar   lo apaga y lo quita. La configuración y el historial quedan.
  --simular     muestra lo que haría, sin instalar nada.

Por qué se copia afuera del plugin: el plugin vive en una carpeta que cambia con cada actualización del kit;
el sistema necesita una ruta fija para lanzar el vigilante.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
for _cand in (AQUI, AQUI.parent.parent / "descargar-tarjeta" / "scripts"):
    if (_cand / "descarga.py").exists():
        MOTOR = _cand / "descarga.py"
        sys.path.insert(0, str(_cand))
        break
else:
    sys.exit("No encuentro descarga.py (el motor de descargar-tarjeta).")
import descarga as D  # noqa: E402

ETIQUETA = "com.creativos.vigilante-tarjetas"
TAREA_WIN = "Vigilante de tarjetas"


def rutas():
    base = D.dir_sistema()
    agentes = Path(os.environ.get("LAUNCH_AGENTS_DIR") or (Path.home() / "Library" / "LaunchAgents"))
    inicio_win = Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / \
        "Programs" / "Startup" / "vigilante-de-tarjetas.vbs"
    return {"base": base, "bin": base / "bin", "plist": agentes / f"{ETIQUETA}.plist", "vbs": inicio_win,
            "log_launchd": base / "vigilante-launchd.log"}


def version_instalada():
    try:
        return (rutas()["bin"] / "VERSION").read_text().strip()
    except OSError:
        return None


def python_para_mac():
    """/usr/bin/python3 si las herramientas de Apple están instaladas (no dispara ventanas); si no, este python."""
    try:
        if subprocess.run(["xcode-select", "-p"], capture_output=True, timeout=10).returncode == 0 and \
                subprocess.run(["/usr/bin/python3", "-c", "import ssl"], capture_output=True,
                               timeout=30).returncode == 0:
            return "/usr/bin/python3"
    except Exception:
        pass
    return sys.executable


def copiar_bin(simular):
    r = rutas()
    if simular:
        print(f"[simular] copiaría descarga.py y vigilante.py a {r['bin']}")
        return
    r["bin"].mkdir(parents=True, exist_ok=True)
    shutil.copy2(MOTOR, r["bin"] / "descarga.py")
    shutil.copy2(AQUI / "vigilante.py", r["bin"] / "vigilante.py")
    (r["bin"] / "VERSION").write_text(D.VERSION)


def _launchctl(*args):
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=30)


def instalar_mac(simular):
    r = rutas()
    py = python_para_mac()
    entorno = {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
               "PYTHONIOENCODING": "utf-8"}
    if os.environ.get("RESPALDO_MATERIAL_DIR"):
        entorno["RESPALDO_MATERIAL_DIR"] = os.environ["RESPALDO_MATERIAL_DIR"]
    plist = {"Label": ETIQUETA,
             "ProgramArguments": [py, str(r["bin"] / "vigilante.py"), "--una-vez"],
             "StartOnMount": True, "RunAtLoad": False, "ProcessType": "Interactive",
             "StandardOutPath": str(r["log_launchd"]), "StandardErrorPath": str(r["log_launchd"]),
             "EnvironmentVariables": entorno}
    datos = plistlib.dumps(plist)
    uid = os.getuid()
    if simular:
        destino = r["plist"]
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(datos)
        print(f"[simular] escribí el agente en {destino} (no lo cargué)")
        print(f"[simular] cargaría con: launchctl bootstrap gui/{uid} {destino}")
        return True
    r["plist"].parent.mkdir(parents=True, exist_ok=True)
    _launchctl("bootout", f"gui/{uid}/{ETIQUETA}")          # por si había uno viejo
    r["plist"].write_bytes(datos)
    res = _launchctl("bootstrap", f"gui/{uid}", str(r["plist"]))
    if res.returncode != 0:
        res = _launchctl("load", "-w", str(r["plist"]))
    if res.returncode != 0:
        print(f"❌ launchd no aceptó el agente: {res.stderr.strip() or res.stdout.strip()}")
        return False
    print(f"✅ Vigilante instalado: se activa cada vez que se conecta una tarjeta (python: {py}).")
    print("   La primera vez, macOS puede pedir permiso para que python3 lea «volúmenes extraíbles»: "
          "hay que tocar «Permitir».")
    return True


def _python_win():
    w = Path(sys.executable).with_name("pythonw.exe")
    return str(w if w.exists() else Path(sys.executable))


def instalar_win(simular):
    r = rutas()
    py = _python_win()
    script = str(r["bin"] / "vigilante.py")
    ps = (f"$a=New-ScheduledTaskAction -Execute '{py}' -Argument '\"{script}\" --bucle'; "
          "$t=New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME; "
          "$s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
          "-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew; "
          f"Register-ScheduledTask -TaskName '{TAREA_WIN}' -Action $a -Trigger $t -Settings $s "
          "-Description 'Avisa y copia las tarjetas de cámara (kit creativos)' -Force | Out-Null; "
          f"Start-ScheduledTask -TaskName '{TAREA_WIN}'")
    if simular:
        print(f"[simular] registraría la tarea «{TAREA_WIN}» con PowerShell:\n  {ps}")
        return True
    res = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                         capture_output=True, text=True, timeout=60)
    if res.returncode == 0:
        print("✅ Vigilante instalado en el Programador de tareas: corre al iniciar sesión y ya está corriendo.")
        return True
    # sin permiso para tareas: acceso oculto en la carpeta Inicio
    r["vbs"].parent.mkdir(parents=True, exist_ok=True)
    r["vbs"].write_text(f'CreateObject("Wscript.Shell").Run """{py}"" ""{script}"" --bucle", 0, False\r\n',
                        encoding="utf-8")
    subprocess.Popen(["wscript", str(r["vbs"])])
    print("✅ Vigilante instalado en la carpeta Inicio (Windows no dejó crear la tarea): corre al iniciar sesión "
          "y ya está corriendo.")
    return True


def desinstalar(simular):
    r = rutas()
    if simular:
        print(f"[simular] quitaría {r['plist'] if D.ES_MAC else TAREA_WIN} y la carpeta {r['bin']}")
        return
    if D.ES_MAC:
        _launchctl("bootout", f"gui/{os.getuid()}/{ETIQUETA}")
        try:
            r["plist"].unlink()
        except OSError:
            pass
    elif D.ES_WIN:
        (D.dir_sistema() / "vigilante").mkdir(parents=True, exist_ok=True)
        (D.dir_sistema() / "vigilante" / "PARAR").write_text("1")      # el bucle se detiene solo
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Unregister-ScheduledTask -TaskName '{TAREA_WIN}' -Confirm:$false"],
                       capture_output=True, timeout=60)
        try:
            r["vbs"].unlink()
        except OSError:
            pass
    shutil.rmtree(r["bin"], ignore_errors=True)
    print("✅ Vigilante quitado. La configuración, el historial y el registro quedan en "
          f"{D.dir_sistema()} (no se borró nada más).")


def estado():
    r = rutas()
    v = version_instalada()
    cfg = D.leer_config()
    if D.ES_MAC:
        cargado = _launchctl("print", f"gui/{os.getuid()}/{ETIQUETA}").returncode == 0
        instalado = r["plist"].exists()
    elif D.ES_WIN:
        q = subprocess.run(["schtasks", "/Query", "/TN", TAREA_WIN], capture_output=True, text=True)
        instalado = q.returncode == 0 or r["vbs"].exists()
        cargado = instalado
    else:
        instalado = cargado = False
    print(f"Vigilante: {'✅ instalado' if instalado else '❌ no instalado'}"
          f"{' y activo' if cargado else ''} · versión instalada {v or '—'} · versión del kit {D.VERSION}")
    if v and v != D.VERSION:
        print("   ⚠️  El kit tiene una versión más nueva: correr «actualizar».")
    print(f"   Proyecto: {cfg.get('proyecto') or '—'} · destinos: {', '.join(cfg.get('destinos', [])) or '—'} · "
          f"modo: {(cfg.get('vigilante') or {}).get('modo', 'preguntar')}")
    print(f"   Registro: {D.dir_sistema() / 'vigilante.log'}")


def main():
    D._consola_utf8()
    ap = argparse.ArgumentParser(description="Instala o quita el vigilante de tarjetas")
    ap.add_argument("accion", choices=["estado", "instalar", "actualizar", "desinstalar"])
    ap.add_argument("--simular", action="store_true")
    a = ap.parse_args()
    if a.accion == "estado":
        estado()
        return 0
    if a.accion == "desinstalar":
        desinstalar(a.simular)
        return 0
    cfg = D.leer_config()
    if a.accion == "instalar" and len(cfg.get("destinos", [])) < 1:
        print("❌ Primero hay que guardar los discos de destino y el proyecto "
              "(descarga.py config guardar --proyecto … --destino … --destino …).")
        return 2
    copiar_bin(a.simular)
    if a.accion == "actualizar":
        print(f"✅ Vigilante actualizado a la versión {D.VERSION}." if not a.simular else "")
        return 0
    if D.ES_MAC:
        return 0 if instalar_mac(a.simular) else 1
    if D.ES_WIN:
        return 0 if instalar_win(a.simular) else 1
    print("Este sistema no está soportado por el vigilante (solo Mac y Windows).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
