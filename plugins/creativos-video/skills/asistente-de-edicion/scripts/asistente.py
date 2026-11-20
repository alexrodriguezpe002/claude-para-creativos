#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asistente.py · Asistente de edición. Cuando ShotPut Pro (u OffShoot, Hedge, Silverstack o descargar-tarjeta) termina
de copiar material a la carpeta vigilada, sincroniza el audio de la grabadora con los clips y deja el proyecto listo
para Premiere o DaVinci: un XML con una carpeta por día, una por cámara y una de audio, y la secuencia del día con los
clips en orden de grabación (motor: sincronizar.py, de la skill sincronizar-audio).

  config guardar --carpeta <destino de las copias> --salida <carpeta del timeline> [--nombre "SINCRO BODA"]
                 [--espera 5] [--sin-senal 15] [--copias | --sin-copias]
  config ver
  --una-vez      revisa una vez y, si una copia terminó, arma el timeline (en Mac lo lanza launchd cada 2 minutos y
                 cada vez que cambia la carpeta)
  --bucle        revisa cada 60 s mientras la sesión está abierta (en Windows lo lanza el Programador de tareas)
  --ahora        arma el timeline ya, sin esperar la señal del programa de copia (si la carpeta no está cambiando)
  --estado       qué vigila, qué vio y el último timeline (para contestar «¿ya está el timeline?»)
  --simular      junto con --una-vez: dice qué haría, sin armar nada ni avisar
  autoprueba     prueba todo con un rodaje inventado, en una carpeta temporal (menos de un minuto)

Cuándo terminó una copia: ShotPut escribe al final el sello de verificación (ASC MHL: una carpeta ascmhl/; MHL: un
archivo .mhl al lado de la carpeta copiada o adentro; o un archivo de sumas *ChecksumFileSPP.*) y los reportes (PDF,
TXT o CSV) en su carpeta de reportes. Hedge, OffShoot y Silverstack dejan ASC MHL; descargar-tarjeta deja _DESCARGA/
y un .mhl. Además la carpeta tiene que quedar quieta (sin archivos nuevos ni que crezcan) --espera minutos. Si el
programa no deja ninguna señal, arma igual después de --sin-senal minutos sin cambios.

Nunca mueve, renombra ni borra nada de las copias (se rompería su verificación): solo las lee. Todo lo nuevo va a la
carpeta de salida, que no puede estar dentro de una copia sellada.
Registro: ~/MI-SISTEMA-CLAUDE/asistente-edicion/asistente.log
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VERSION = "1.0.0"
ES_MAC = sys.platform == "darwin"
ES_WIN = os.name == "nt"
AQUI = Path(__file__).resolve().parent
for _cand in (AQUI, AQUI.parent.parent / "sincronizar-audio" / "scripts"):
    if (_cand / "sincronizar.py").exists():
        MOTOR = _cand / "sincronizar.py"
        sys.path.insert(0, str(_cand))
        break
else:
    sys.exit("No encuentro sincronizar.py (el motor de la skill sincronizar-audio).")
import sincronizar as S  # noqa: E402  extensiones, carpetas que no se miran y el material de prueba

EXT_MEDIA = S.EXT_VIDEO | S.EXT_AUDIO
SUMAS_SHOTPUT = re.compile(r"checksumfilespp", re.I)          # md5ChecksumFileSPP.md5, xxhash64ChecksumFileSPP…
REPORTES = (".pdf", ".txt", ".csv", ".html")
REVISAR_CADA = 60                                             # segundos, en el modo --bucle (Windows)
SIMULAR = False
AVISOS = []                                                   # lo que se avisó (para la autoprueba)


# ───────────────────────────── archivos del sistema ─────────────────────────────

def dir_sistema() -> Path:
    d = os.environ.get("ASISTENTE_DIR")
    return Path(d).expanduser() if d else Path.home() / "MI-SISTEMA-CLAUDE" / "asistente-edicion"


def _leer(nombre):
    try:
        return json.loads((dir_sistema() / nombre).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _guardar(nombre, data):
    p = dir_sistema() / nombre
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def log(msg):
    p = dir_sistema() / "asistente.log"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > 1_000_000:
            os.replace(p, p.with_name("asistente.log.1"))
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def cuando(ts):
    """«sáb 28-11 14:32» (con el día de la semana, para saber de un vistazo si cae en día de trabajo)."""
    d = dt.datetime.fromtimestamp(ts)
    return f"{DIAS[d.weekday()]} {d:%d-%m %H:%M}"


def hace(segundos):
    m = int(segundos // 60)
    return "menos de un minuto" if m < 1 else ("1 minuto" if m == 1 else f"{m} minutos")


# ───────────────────────────── avisos ─────────────────────────────

def _sin_avisos():
    return bool(os.environ.get("ASISTENTE_SIN_AVISOS")) or SIMULAR


def _as(texto):
    return '"' + str(texto).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ps(texto):
    return "'" + str(texto).replace("'", "''") + "'"


def avisar(titulo, texto):
    AVISOS.append((titulo, texto))
    log(f"AVISO {titulo}: {texto}")
    if _sin_avisos():
        print(f"[aviso] {titulo}: {texto}")
        return
    try:
        if ES_MAC:
            subprocess.run(["osascript", "-e", f"display notification {_as(texto)} with title {_as(titulo)} "
                                               'sound name "Glass"'], timeout=20)
        elif ES_WIN:
            script = ("Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
                      "$n=New-Object System.Windows.Forms.NotifyIcon; "
                      "$n.Icon=[System.Drawing.SystemIcons]::Information; $n.Visible=$true; "
                      f"$n.ShowBalloonTip(10000,{_ps(titulo)},{_ps(texto)},'Info'); Start-Sleep 8; $n.Dispose()")
            subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                              "-Command", script], creationflags=0x08000000)
    except Exception as e:
        log(f"no se pudo mostrar el aviso: {e}")


def _despierta():
    """Que la compu no se duerma mientras sincroniza (se suelta sola al terminar)."""
    try:
        if ES_MAC and shutil.which("caffeinate"):
            subprocess.Popen(["caffeinate", "-ims", "-w", str(os.getpid())],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif ES_WIN:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    except Exception:
        pass


# ───────────────────────────── mirar la carpeta ─────────────────────────────

def _rel(carpeta_rel, nombre):
    return f"{carpeta_rel}/{nombre}" if carpeta_rel else nombre


def escanear(raiz, salida=None):
    """El material de la carpeta vigilada y las señales de que una copia terminó.

    Devuelve (media {ruta relativa: [tamaño, fecha]}, carpetas selladas {ruta relativa}, reportes [(ruta, fecha)])."""
    media, selladas, reportes = {}, set(), []
    sal = os.path.normcase(os.path.abspath(salida)) if salida else None
    for actual, dirs, archivos in os.walk(raiz):
        rel = os.path.relpath(actual, raiz)
        rel = "" if rel == "." else rel.replace("\\", "/")
        nombres = {d.lower() for d in dirs}
        if "ascmhl" in nombres or "_descarga" in nombres:
            selladas.add(rel)                       # ASC MHL (o descargar-tarjeta): sella la carpeta que lo tiene
        carpeta = os.path.basename(actual).lower()
        de_reportes = bool(rel) and ("report" in carpeta or "shotput" in carpeta)
        for a in archivos:
            if a.startswith("."):
                continue
            al = a.lower()
            ruta = os.path.join(actual, a)
            if al.endswith(".mhl"):
                # MHL: al lado de la carpeta copiada (lleva su nombre adelante) o adentro de la carpeta sellada
                vecina = max((d for d in dirs if al.startswith(d.lower())), key=len, default=None)
                selladas.add(_rel(rel, vecina) if vecina else rel)
            elif SUMAS_SHOTPUT.search(a):
                selladas.add(rel)
            elif de_reportes and al.endswith(REPORTES):
                try:
                    reportes.append((_rel(rel, a), os.path.getmtime(ruta)))
                except OSError:
                    pass
            if os.path.splitext(al)[1].lstrip(".") in EXT_MEDIA:
                try:
                    st = os.stat(ruta)
                except OSError:
                    continue
                media[_rel(rel, a)] = [st.st_size, int(st.st_mtime)]
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d.lower() not in S.NO_ENTRAR
                         and not (sal and os.path.normcase(os.path.join(actual, d)) == sal))
    return media, selladas, reportes


def cubierto(rel_archivo, selladas):
    partes = rel_archivo.split("/")[:-1]
    return any("/".join(partes[:k]) in selladas for k in range(len(partes), -1, -1))


def huella(media):
    return hashlib.sha1(json.dumps(sorted(media.items())).encode("utf-8")).hexdigest()


def sellada_la_salida(cfg):
    """¿La carpeta de salida cae dentro de una copia sellada? (escribir ahí rompería su verificación)"""
    raiz, salida = os.path.abspath(cfg["carpeta"]), os.path.abspath(cfg["salida"])
    try:
        rel = os.path.relpath(salida, raiz)
    except ValueError:                              # otro disco (Windows)
        return None
    if rel.startswith(".."):
        return None
    _, selladas, _ = escanear(raiz, salida)
    rel = rel.replace("\\", "/")
    partes = rel.split("/")
    for k in range(len(partes), -1, -1):
        p = "/".join(partes[:k])
        if p in selladas:
            return p or os.path.basename(raiz)
    return None


# ───────────────────────────── decidir y armar ─────────────────────────────

def decidir(cfg, est, t, forzar=False):
    """Qué hacer ahora. Actualiza est (lo que vio y desde cuándo) y devuelve un dict con la situación."""
    raiz = cfg["carpeta"]
    if not os.path.isdir(raiz):
        return {"situacion": "desconectada", "texto": f"no encuentro {raiz} (¿el disco está desconectado?)"}
    media, selladas, reportes = escanear(raiz, cfg.get("salida"))
    h = huella(media)
    if not media:
        return {"situacion": "vacia", "texto": "la carpeta todavía no tiene material"}
    if h == est.get("huella_base") and not forzar:
        return {"situacion": "al_dia", "texto": "no llegó nada nuevo desde el último timeline"}
    base = est.get("base") or {}
    nuevos = [r for r, v in media.items() if base.get(r) != v]
    if h != est.get("huella_vista"):
        est["huella_vista"], est["desde"] = h, t
        return {"situacion": "copiando", "nuevos": len(nuevos), "media": media, "huella": h,
                "texto": f"llegaron {len(nuevos)} archivos nuevos o cambiados: espero a que termine la copia"}
    quieta = t - est.get("desde", t)
    if est.get("error", {}).get("huella") == h and not forzar:
        return {"situacion": "error", "texto": "la última vez no pude armar el timeline con este material: "
                                               + est["error"].get("texto", "")}
    if forzar:
        return {"situacion": "lista", "media": media, "huella": h, "con_senal": None, "nuevos": len(nuevos),
                "texto": "armado a pedido"}
    espera = float(cfg.get("espera", 5)) * 60
    if quieta < espera:
        return {"situacion": "esperando_quieta", "nuevos": len(nuevos),
                "texto": f"{len(nuevos)} archivos nuevos; la carpeta está quieta hace {hace(quieta)}: "
                         f"espero {hace(espera)} sin cambios"}
    sin_cubrir = [r for r in nuevos if not cubierto(r, selladas)]
    ultimo = (est.get("ultimo") or {}).get("ts", 0)
    if sin_cubrir and any(m > ultimo for _, m in reportes):
        sin_cubrir = []                             # hay un reporte del programa de copia escrito después
    sin_senal = float(cfg.get("sin_senal", 15)) * 60
    if sin_cubrir and quieta < sin_senal:
        return {"situacion": "esperando_senal", "nuevos": len(nuevos),
                "texto": f"{len(sin_cubrir)} archivos sin sello ni reporte del programa de copia: espero la señal "
                         f"o {hace(sin_senal)} sin cambios (van {hace(quieta)})"}
    return {"situacion": "lista", "media": media, "huella": h, "con_senal": not sin_cubrir, "nuevos": len(nuevos),
            "texto": "la copia terminó" + ("" if not sin_cubrir else " (sin sello ni reporte: esperé sin cambios)")}


def _bloqueo():
    p = dir_sistema() / "armando.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return p
    except FileExistsError:
        try:
            pid = int(p.read_text() or 0)
            os.kill(pid, 0)                         # sigue vivo: hay otro armando
            return None
        except (ValueError, OSError):
            try:
                p.unlink()                          # quedó de una vez que se cortó
            except OSError:
                return None
            return _bloqueo()


def _cuentas(resumen):
    def n(patron):
        m = re.search(patron, resumen)
        return int(m.group(1)) if m else 0
    m = re.search(r"Sincronizados: (\d+) de (\d+)", resumen)
    return {"sinc": int(m.group(1)) if m else 0, "total": int(m.group(2)) if m else 0,
            "media": n(r"media (\d+)"), "sin": n(r"sin coincidencia (\d+)"), "mudos": n(r"sin audio (\d+)"),
            "sin_grabadora": n(r"sin grabadora (\d+)")}


def armar(cfg, est, d, t, motivo):
    salida = cfg["salida"]
    os.makedirs(salida, exist_ok=True)
    cmd = [sys.executable, str(MOTOR), "analizar", "--clips", cfg["carpeta"], "--audio", cfg["carpeta"],
           "--salida", salida, "--nombre", cfg.get("nombre") or "SINCRO",
           "--cache", os.path.join(salida, ".asistente-cache.json"), "--excluir", salida]
    if cfg.get("copias"):
        cmd.append("--copias")
    if SIMULAR:
        print("[simular] armaría el timeline: " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
        return "simulado"
    candado = _bloqueo()
    if not candado:
        log("ya hay otro armando el timeline; salgo")
        return "en_curso"
    try:
        _despierta()
        log(f"armando el timeline ({motivo}): {d.get('nuevos', 0)} archivos nuevos")
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        salida_txt = (r.stdout or "") + (r.stderr or "")
        for linea in salida_txt.splitlines():
            log(f"   {linea}")
        xmls = [x[4:] for x in r.stdout.splitlines() if x.startswith("XML=")]
        resumen = next((x for x in r.stdout.splitlines() if x.startswith("Sincronizados:")), "")
        informe = next((x[8:] for x in r.stdout.splitlines() if x.startswith("INFORME=")), None)
        if r.returncode == 0 and xmls:
            c = _cuentas(resumen)
            est["base"], est["huella_base"] = d["media"], d["huella"]
            est["ultimo"] = {"ts": t, "xml": xmls[-1], "informe": informe, "resumen": resumen, "motivo": motivo,
                             "con_senal": d.get("con_senal"), **c}
            est.pop("error", None)
            nombre = os.path.basename(xmls[-1])
            if c["sin_grabadora"] and not c["sinc"]:
                texto = (f"Timeline listo con el audio de la cámara ({c['total']} clips; no encontré audio de "
                         f"grabadora). En Premiere: Archivo › Importar › «{nombre}».")
            else:
                revisar = f" (🟡 {c['media']} para escuchar)" if c["media"] else ""
                texto = (f"{c['sinc']} de {c['total']} clips sincronizados{revisar}. En Premiere: Archivo › "
                         f"Importar › «{nombre}».")
            avisar("✅ Timeline listo", texto)
            return "ok"
        error = next((x for x in reversed(salida_txt.splitlines()) if x.startswith("❌")), None) or \
            (salida_txt.strip().splitlines() or ["terminó sin XML"])[-1]
        est["error"] = {"ts": t, "huella": d["huella"], "texto": error.lstrip("❌ ").strip()}
        avisar("❌ No pude armar el timeline", f"{est['error']['texto']}. Pídele a Claude: «revisa el asistente "
                                               "de edición».")
        return "error"
    finally:
        try:
            candado.unlink()
        except OSError:
            pass


def una_vez(t=None, forzar=False):
    cfg = _leer("config.json")
    if not cfg.get("carpeta") or not cfg.get("salida"):
        log("sin configuración: falta la carpeta a vigilar o la de salida")
        return {"situacion": "sin_config", "texto": "falta configurar (config guardar)"}
    est = _leer("estado.json")
    t = time.time() if t is None else t
    d = decidir(cfg, est, t, forzar=forzar)
    est["revisado"] = t
    est["situacion"] = {k: v for k, v in d.items() if k in ("situacion", "texto", "nuevos")}
    if SIMULAR:
        print(f"[simular] {d['situacion']}: {d['texto']}")
    if d["situacion"] == "lista":
        motivo = "a pedido" if forzar else ("señal del programa de copia" if d.get("con_senal")
                                            else "sin señal, carpeta quieta")
        d["resultado"] = armar(cfg, est, d, t, motivo)
    elif d["situacion"] == "copiando":
        log(f"{d['texto']}")
    if not SIMULAR:
        _guardar("estado.json", est)
    return d


def ahora_ya():
    """--ahora: arma ya si la carpeta no está cambiando (la mira dos veces, con 20 s de diferencia)."""
    cfg = _leer("config.json")
    if not cfg.get("carpeta"):
        print("❌ Falta configurar el asistente (config guardar).")
        return 2
    m1 = huella(escanear(cfg["carpeta"], cfg.get("salida"))[0]) if os.path.isdir(cfg["carpeta"]) else None
    if m1 is None:
        print(f"❌ No encuentro {cfg['carpeta']} (¿el disco está desconectado?).")
        return 2
    time.sleep(float(os.environ.get("ASISTENTE_ESPERA_AHORA", 20)))
    m2 = huella(escanear(cfg["carpeta"], cfg.get("salida"))[0])
    if m1 != m2:
        print("⏳ La carpeta está cambiando ahora mismo (se está copiando algo): el timeline se arma solo cuando "
              "termine.")
        return 1
    est = _leer("estado.json")
    est["huella_vista"], est["desde"] = m2, time.time()
    _guardar("estado.json", est)
    d = una_vez(forzar=True)
    ultimo = _leer("estado.json").get("ultimo") or {}
    if d.get("resultado") == "ok":
        print(f"✅ Timeline listo: {ultimo.get('xml', '')}\n   {ultimo.get('resumen', '')}")
    else:
        print(f"❌ {d['situacion']}: {d['texto']}" + (f" ({d.get('resultado')})" if d.get("resultado") else ""))
    return 0 if d.get("resultado") == "ok" else 1


def bucle():
    pid_p = dir_sistema() / "bucle.pid"
    pid_p.parent.mkdir(parents=True, exist_ok=True)
    try:
        viejo = int(pid_p.read_text() or 0)
        if viejo and viejo != os.getpid():
            os.kill(viejo, 0)
            log("ya hay un asistente en bucle corriendo; salgo")
            return
    except (ValueError, OSError):
        pass
    pid_p.write_text(str(os.getpid()))
    parar = dir_sistema() / "PARAR"
    if parar.exists():
        parar.unlink()
    log(f"bucle iniciado (pid {os.getpid()})")
    try:
        while not parar.exists():
            try:
                una_vez()
            except Exception as e:                  # el asistente no se cae por una carpeta rara
                log(f"error revisando: {e!r}")
            time.sleep(REVISAR_CADA)
    finally:
        log("bucle detenido")
        try:
            pid_p.unlink()
        except OSError:
            pass


# ───────────────────────────── configuración y estado ─────────────────────────────

def config_guardar(a):
    cfg = _leer("config.json")
    if a.carpeta:
        cfg["carpeta"] = os.path.abspath(os.path.expanduser(a.carpeta))
    if a.salida:
        cfg["salida"] = os.path.abspath(os.path.expanduser(a.salida))
    if a.nombre:
        cfg["nombre"] = a.nombre
    if a.espera is not None:
        cfg["espera"] = a.espera
    if a.sin_senal is not None:
        cfg["sin_senal"] = a.sin_senal
    if a.copias is not None:
        cfg["copias"] = a.copias
    cfg.setdefault("nombre", "SINCRO")
    cfg.setdefault("espera", 5)
    cfg.setdefault("sin_senal", 15)
    cfg.setdefault("copias", False)
    if not cfg.get("carpeta") or not cfg.get("salida"):
        print("❌ Faltan --carpeta (el destino de las copias) y --salida (dónde dejar el timeline).")
        return 2
    if os.path.normcase(cfg["carpeta"]) == os.path.normcase(cfg["salida"]):
        print("❌ La salida no puede ser la misma carpeta que se vigila: elegir otra (por ejemplo una carpeta "
              "SINCRO al lado).")
        return 2
    if os.path.isdir(cfg["carpeta"]):
        sellada = sellada_la_salida(cfg)
        if sellada:
            print(f"❌ La salida cae dentro de «{sellada}», que es una copia sellada (tiene su MHL o sus sumas): "
                  "escribir ahí rompería la verificación. Elegir una carpeta fuera de las copias.")
            return 2
    else:
        print(f"⚠️  Todavía no existe {cfg['carpeta']} (¿disco desconectado?). Se guarda igual.")
    _guardar("config.json", cfg)
    est = _leer("estado.json")
    if est.get("carpeta") != cfg["carpeta"]:        # carpeta nueva: empieza de cero
        est = {"carpeta": cfg["carpeta"]}
        _guardar("estado.json", est)
    print(f"✅ Guardado: vigila {cfg['carpeta']} · timeline en {cfg['salida']} · nombre «{cfg['nombre']}» · "
          f"espera {cfg['espera']} min (sin señal: {cfg['sin_senal']} min){' · con copias' if cfg['copias'] else ''}")
    return 0


ETIQUETA = "com.creativos.asistente-edicion"   # el agente que deja instalar_asistente.py en Mac
TAREA_WIN = "Asistente de edicion"             # la tarea programada en Windows


def vigilando():
    """(activo, texto): ¿el vigilante está instalado y cargado? Sin él no se arma ningún timeline nuevo, aunque la
    configuración y el último timeline sigan ahí (repaso del vie 20-11-2026: estaba desinstalado y se culpó al disco)."""
    try:
        if sys.platform == "darwin":
            plist = Path.home() / "Library" / "LaunchAgents" / f"{ETIQUETA}.plist"
            if not plist.exists():
                return False, "no: el asistente no está instalado en esta computadora"
            r = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{ETIQUETA}"],
                               capture_output=True, text=True, timeout=10)
            return (True, "sí") if r.returncode == 0 else (False, "no: está instalado pero apagado")
        if os.name == "nt":
            r = subprocess.run(["schtasks", "/Query", "/TN", TAREA_WIN], capture_output=True, text=True, timeout=10)
            return (True, "sí") if r.returncode == 0 else (False, "no: el asistente no está instalado en esta computadora")
    except Exception as e:  # noqa: BLE001
        return False, f"no lo pude saber ({e})"
    return False, "no: en este sistema no hay vigilante"


def estado():
    cfg = _leer("config.json")
    est = _leer("estado.json")
    print(f"Asistente de edición (versión {VERSION}) · configuración: {dir_sistema() / 'config.json'}")
    activo, texto = vigilando()
    print(f"  Vigilando ahora: {'✅' if activo else '❌'} {texto}")
    if not cfg.get("carpeta"):
        print("  ❌ Sin configurar: falta elegir la carpeta a vigilar y dónde dejar el timeline.")
        return
    conectada = os.path.isdir(cfg["carpeta"])
    print(f"  Vigila: {cfg['carpeta']} ({'✅ conectada' if conectada else '❌ no la encuentro: ¿disco desconectado?'})")
    print(f"  Timeline en: {cfg['salida']} · nombre «{cfg.get('nombre', 'SINCRO')}» · espera "
          f"{cfg.get('espera', 5)} min sin cambios (sin señal: {cfg.get('sin_senal', 15)} min)")
    u = est.get("ultimo")
    if u:
        sigue = os.path.exists(u["xml"])
        print(f"  Último timeline: {cuando(u['ts'])} → {u['xml']}"
              + ("" if sigue else "  (⚠️ ese archivo ya no está ahí: no dar el link)"))
        print(f"     {u.get('resumen', '')}")
    else:
        print("  Último timeline: todavía ninguno.")
    if est.get("error"):
        print(f"  ❌ Último error ({cuando(est['error']['ts'])}): {est['error']['texto']}")
    if conectada:
        copia = json.loads(json.dumps(est))
        d = decidir(cfg, copia, time.time())
        if d["situacion"] == "copiando" and est.get("huella_vista"):
            d["texto"] = "está llegando material (la carpeta cambió desde la última revisión)"
        print(f"  Ahora: {d['texto']}")
    if est.get("revisado"):
        print(f"  Última revisión: {cuando(est['revisado'])}")
    print(f"  Registro: {dir_sistema() / 'asistente.log'}")
    if not activo:
        print("  ⚠️ Mientras no vigile, no arma timelines nuevos. Para prenderlo: instalar_asistente.py instalar "
              "(o «actualizar» si ya estaba).")


# ───────────────────────────── autoprueba ─────────────────────────────

def _mhl_asc(carpeta, nombre):
    asc = Path(carpeta) / "ascmhl"
    asc.mkdir(parents=True, exist_ok=True)
    (asc / f"0001_{nombre}_2026-11-28_120500Z.mhl").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                                                '<hashlist version="2.0"/>\n', encoding="utf-8")
    (asc / "ascmhl_chain.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<ascmhldirectory/>\n',
                                          encoding="utf-8")


def autoprueba():
    global AVISOS
    np = S.numpy_o_salir()
    if not S.FFMPEG:
        S.salir("Falta ffmpeg.", 3)
    base = Path(tempfile.mkdtemp(prefix="asistente_prueba_"))
    viejo_dir, viejo_av = os.environ.get("ASISTENTE_DIR"), os.environ.get("ASISTENTE_SIN_AVISOS")
    os.environ["ASISTENTE_DIR"] = str(base / "SISTEMA")
    os.environ["ASISTENTE_SIN_AVISOS"] = "1"
    ok = True

    def check(bien, texto):
        nonlocal ok
        print(f"{'✅' if bien else '❌'} {texto}")
        ok &= bool(bien)

    try:
        rng = np.random.default_rng(11)
        sr = 48000
        tarjetas = base / "TARJETAS"                                  # lo que traería cada tarjeta
        destino = base / "SSD" / "BODA PRUEBA"                        # el destino de ShotPut
        salida = base / "SSD" / "BODA PRUEBA - SINCRO"
        print("Armando un rodaje de prueba: grabadora, cámara A (Sony), cámara B y B-roll…")
        voz = S._habla(np, 100, sr, rng)
        zoom = tarjetas / "ZOOM"
        zoom.mkdir(parents=True)
        S._wav(np, str(zoom / "ZOOM0001.WAV"), [voz, voz * 0.5], sr)
        clips = [("A001", "C0001.MP4", 10.0, 20.0, "2026-11-28T12:01:00"),
                 ("B001", "MVI_0001.MP4", 30.0, 30.0, "2026-11-28T12:01:20"),
                 ("A001", "C0002.MP4", 50.0, 25.0, "2026-11-28T12:02:00"),
                 ("A002", "C0004.MP4", 70.0, 15.0, "2026-11-28T12:04:00")]
        for tarjeta, nombre, off, dur, hora in clips:
            if tarjeta.startswith("A"):
                carpeta = tarjetas / tarjeta / "PRIVATE" / "M4ROOT" / "CLIP"
            else:
                carpeta = tarjetas / tarjeta / "DCIM" / "100CANON"
            carpeta.mkdir(parents=True, exist_ok=True)
            seg = voz[int(off * sr): int((off + dur) * sr)]
            w = base / f"{nombre}.wav"
            S._wav(np, str(w), [S._camara(np, seg, sr, rng)], sr, bits=16)
            S._clip(str(carpeta / nombre), str(w), dur, creado=hora + "Z")
            if tarjeta.startswith("A"):
                S._xml_sony(str(carpeta / nombre), "ILME-FX3", hora + "+00:00")
        broll = tarjetas / "A001" / "PRIVATE" / "M4ROOT" / "CLIP"
        S._clip(str(broll / "C0003.MP4"), None, 6.0, creado="2026-11-28T12:03:00Z")
        S._xml_sony(str(broll / "C0003.MP4"), "ILME-FX3", "2026-11-28T12:03:00+00:00")

        cfg_args = argparse.Namespace(carpeta=str(destino), salida=str(salida), nombre="SINCRO BODA", espera=5,
                                      sin_senal=15, copias=False)
        destino.mkdir(parents=True)
        check(config_guardar(cfg_args) == 0, "configuración guardada (vigila el destino de ShotPut)")
        t = 1_800_000_000.0
        dia = destino / "2026-11-28"

        # 1) Llega la cámara A a medias: espera
        a001 = dia / "A001" / "PRIVATE" / "M4ROOT" / "CLIP"
        a001.mkdir(parents=True)
        shutil.copy2(tarjetas / "A001/PRIVATE/M4ROOT/CLIP/C0001.MP4", a001)
        check(una_vez(t)["situacion"] == "copiando", "llega el primer clip: espera a que termine la copia")
        for f in ("C0001M01.XML", "C0002.MP4", "C0002M01.XML", "C0003.MP4", "C0003M01.XML"):
            shutil.copy2(tarjetas / "A001/PRIVATE/M4ROOT/CLIP" / f, a001)
        check(una_vez(t + 30)["situacion"] == "copiando", "siguen llegando clips: sigue esperando")
        check(una_vez(t + 90)["situacion"] == "esperando_quieta", "1 minuto sin cambios: todavía no (espera 5)")
        check(una_vez(t + 30 + 6 * 60)["situacion"] == "esperando_senal",
              "quieta pero sin sello ni reporte de ShotPut: espera la señal (o 15 minutos)")

        # 2) ShotPut termina: sello ASC MHL en A001, la grabadora con MHL al lado y la cámara B con sumas + reporte
        _mhl_asc(dia / "A001", "A001")
        shutil.copytree(zoom, dia / "ZOOM")
        (dia / "ZOOM_2026-11-28_120500.mhl").write_text("<hashlist/>\n", encoding="utf-8")
        shutil.copytree(tarjetas / "B001", dia / "B001")
        (dia / "B001" / "md5ChecksumFileSPP.md5").write_text("x  DCIM/100CANON/MVI_0001.MP4\n", encoding="utf-8")
        (destino / "Reports").mkdir()
        (destino / "Reports" / "BODA - Offload 1.txt").write_text("ShotPut Pro report\n", encoding="utf-8")
        antes = sorted((str(p.relative_to(destino)), p.stat().st_size, int(p.stat().st_mtime))
                       for p in destino.rglob("*") if p.is_file())
        t2 = t + 8 * 60
        check(una_vez(t2)["situacion"] == "copiando", "llegan la grabadora y la cámara B: espera otra vez")
        AVISOS = []
        d = una_vez(t2 + 6 * 60)
        est = _leer("estado.json")
        u = est.get("ultimo") or {}
        check(d["situacion"] == "lista" and d.get("resultado") == "ok" and os.path.exists(u.get("xml", "")),
              f"todo sellado y quieto 5 minutos: arma el timeline → {os.path.basename(u.get('xml', '—'))}")
        check(u.get("sinc") == 3 and u.get("total") == 4 and u.get("mudos") == 1,
              f"3 de 4 clips sincronizados (las dos cámaras) y el B-roll adentro: {u.get('resumen', '—')}")
        check(any("Timeline listo" in t_ for t_, _ in AVISOS), "avisa «✅ Timeline listo» con el nombre del XML")
        x = S.revisar_proyecto_xml(u["xml"]) if u.get("xml") else {"secuencias": {}, "carpetas": {}, "problemas": [1]}
        orden = next(iter(x["secuencias"].values()), [])
        check(orden == ["C0001.MP4", "MVI_0001.MP4", "C0002.MP4", "SIN AUDIO - C0003.MP4"],
              f"la secuencia del día va en orden de grabación, mezclando las dos cámaras: {orden}")
        check({"CAMARA - ILME-FX3", "CAMARA - B001", "AUDIO"} <= set(x["carpetas"]) and not x["problemas"],
              "carpetas por cámara (modelo o carpeta de la tarjeta) y de audio")
        despues = sorted((str(p.relative_to(destino)), p.stat().st_size, int(p.stat().st_mtime))
                         for p in destino.rglob("*") if p.is_file())
        check(antes == despues, "las copias quedaron intactas: nada nuevo, movido ni cambiado adentro")
        check(una_vez(t2 + 7 * 60)["situacion"] == "al_dia", "sin material nuevo: no hace nada")

        # 3) Otra tarjeta de la cámara A (sellada): nueva versión, sin volver a analizar lo de antes
        shutil.copytree(tarjetas / "A002", dia / "A002")
        _mhl_asc(dia / "A002", "A002")
        t3 = t2 + 20 * 60
        una_vez(t3)
        d = una_vez(t3 + 6 * 60)
        u2 = _leer("estado.json").get("ultimo") or {}
        log_txt = (dir_sistema() / "asistente.log").read_text(encoding="utf-8")
        check(d.get("resultado") == "ok" and u2.get("xml") != u.get("xml") and u2.get("total") == 5,
              f"llega otra tarjeta: versión nueva con todo el día → {os.path.basename(u2.get('xml', '—'))}")
        check("Reutilizados del análisis anterior: 3 de 5" in log_txt,
              "solo analiza el clip nuevo (los otros 3 con audio salen del análisis guardado)")

        # 4) Una carpeta sin ninguna señal (programa que no sella): arma después de 15 minutos quieta
        c001 = dia / "C001"
        c001.mkdir()
        shutil.copy2(tarjetas / "B001/DCIM/100CANON/MVI_0001.MP4", c001 / "CLIP0001.MP4")
        t4 = t3 + 30 * 60
        una_vez(t4)
        check(una_vez(t4 + 6 * 60)["situacion"] == "esperando_senal", "carpeta sin sello: a los 6 minutos espera")
        d = una_vez(t4 + 16 * 60)
        check(d.get("resultado") == "ok", "a los 15 minutos quieta, arma igual (sin señal)")
        print("")
        estado()
    finally:
        for k, v in (("ASISTENTE_DIR", viejo_dir), ("ASISTENTE_SIN_AVISOS", viejo_av)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(base, ignore_errors=True)
    print("✅ Autoprueba OK" if ok else "❌ La autoprueba falló")
    return 0 if ok else 5


# ───────────────────────────── main ─────────────────────────────

def main():
    global SIMULAR
    S._consola_utf8()
    ap = argparse.ArgumentParser(description="Asistente de edición: timeline listo cuando termina la copia",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("accion", nargs="?", choices=["config", "autoprueba"])
    ap.add_argument("sub", nargs="?", choices=["guardar", "ver"])
    ap.add_argument("--una-vez", action="store_true")
    ap.add_argument("--bucle", action="store_true")
    ap.add_argument("--ahora", action="store_true")
    ap.add_argument("--estado", action="store_true")
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--carpeta")
    ap.add_argument("--salida")
    ap.add_argument("--nombre")
    ap.add_argument("--espera", type=float)
    ap.add_argument("--sin-senal", dest="sin_senal", type=float)
    ap.add_argument("--copias", dest="copias", action="store_true", default=None)
    ap.add_argument("--sin-copias", dest="copias", action="store_false")
    a = ap.parse_args()
    SIMULAR = a.simular
    if a.accion == "autoprueba":
        return autoprueba()
    if a.accion == "config":
        if a.sub == "guardar":
            return config_guardar(a)
        print(json.dumps(_leer("config.json"), ensure_ascii=False, indent=1) or "{}")
        return 0
    if a.estado:
        estado()
        return 0
    if a.ahora:
        return ahora_ya()
    if a.bucle:
        bucle()
        return 0
    if a.una_vez:
        try:
            d = una_vez()
        except Exception as e:
            log(f"error: {e!r}")
            raise
        if not SIMULAR and sys.stdout.isatty():
            print(f"{d['situacion']}: {d['texto']}")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
