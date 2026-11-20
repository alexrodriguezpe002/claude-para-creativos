#!/usr/bin/env python3
"""Habla con Premiere Pro a través del panel MCP Bridge (Window > Extensions > MCP Bridge).

El panel revisa una carpeta cada 250 ms: se deja ahí `command-<id>.json` con {id, script} (ExtendScript)
y el panel contesta en `response-<id>.json`. No hace falta el servidor MCP: alcanza con Python.
Carpeta: /tmp/premiere-mcp-bridge en Mac (se puede cambiar con la variable PREMIERE_BRIDGE_DIR).
El panel rechaza scripts que contengan eval(, new Function(, require(, process., __dirname, child_process.
"""
import json, os, time

PUENTE = os.environ.get("PREMIERE_BRIDGE_DIR", "/tmp/premiere-mcp-bridge")


def extendscript(script, espera=120):
    """Manda ExtendScript a Premiere y devuelve su resultado como texto."""
    if not os.path.isdir(PUENTE):
        raise RuntimeError("no existe %s: Premiere no está abierto o el panel MCP Bridge no está andando" % PUENTE)
    cid = "hfp-%d-%d" % (os.getpid(), int(time.time() * 1000))
    cmd = os.path.join(PUENTE, "command-%s.json" % cid)
    resp = os.path.join(PUENTE, "response-%s.json" % cid)
    with open(cmd + ".tmp", "w") as f:   # el panel solo lee *.json: se escribe y después se renombra
        json.dump({"id": cid, "script": script}, f)
    os.replace(cmd + ".tmp", cmd)
    t0 = time.time()
    while time.time() - t0 < espera:
        if os.path.exists(resp):
            try:
                r = json.load(open(resp))
            except ValueError:   # todavía escribiéndose
                time.sleep(0.3)
                continue
            os.remove(resp)
            if r.get("success"):
                return str(r.get("result")).strip()
            raise RuntimeError("Premiere respondió con error: %s" % r.get("error"))
        time.sleep(0.25)
    if os.path.exists(cmd):
        os.remove(cmd)
    raise TimeoutError("Premiere no respondió en %d s (¿está abierto, con un proyecto, y el panel "
                       "Window > Extensions > MCP Bridge conectado?)" % espera)
