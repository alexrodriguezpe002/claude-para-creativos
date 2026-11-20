#!/usr/bin/env python3
"""Gate: ningún caption cruza un corte de la edición (caption-across-cut).

  python cruce_cortes.py --srt "<archivo>.srt" --cortes cortes.json

Regla del editor (2026-10-28): una palabra se lee cuando se dice. Un caption que arranca antes de un corte y sigue
después tiene palabras de los dos lados, y la de después del corte aparece en pantalla antes de que se diga
("porque la" | corte | "poesía"; "Otras" antes del corte y se dice después). En una clase grabada, 38 de 634.

--cortes  los clips de V1 de premiere_bridge.py (con o sin el sobre {"result": "..."}). Solo cuentan los cortes
          reales: donde se sacó material (un clip partido sin quitar nada no es un corte).
Tolerancia: 0,04 s de cada lado (un cuadro a 25 fps). Única excepción: un caption que con lo que tiene antes del
corte no llega a 0,5 s en pantalla puede seguir hasta 0,5 s; eso se lista como aviso, no falla.
No ve el caso del caption que cierra justo EN el corte con una palabra que se dice después: ese lo oye
verificar_timing.py de premiere-captions (escucha cada caption solo hasta su corte).
Salida: 0 pasa · 1 algún caption cruza un corte · 2 no se pudo medir (sin cortes o SRT vacío).
"""
import argparse
import json
import re
import sys

CLE = 0.04
MIN_DURO = 0.50


def leer_cortes(path):
    r = json.load(open(path)); r = r.get("result", r) if isinstance(r, dict) else r
    r = json.loads(r) if isinstance(r, str) else r
    return sorted(r["clips"] if isinstance(r, dict) else r, key=lambda c: c["s"])


def cortes_reales(clips):
    """tiempos de timeline donde se sacó material entre un clip y el siguiente"""
    return [a["e"] for a, b in zip(clips, clips[1:]) if abs(b["inP"] - (a["inP"] + a["e"] - a["s"])) > 0.02]


def leer_srt(path):
    t = open(path, encoding="utf-8-sig").read().replace("\r\n", "\n").strip()
    f = lambda s: int(s[:2]) * 3600 + int(s[3:5]) * 60 + float(s[6:].replace(",", "."))
    caps = []
    for b in re.split(r"\n\s*\n", t):
        l = b.split("\n")
        if len(l) < 3 or "-->" not in l[1]: continue
        a, z = l[1].split(" --> ")
        caps.append({"n": int(l[0]), "a": f(a.strip()), "z": f(z.strip()), "txt": " ".join(l[2:]).strip()})
    return caps


def cruces(caps, cortes):
    """→ (fallas, avisos): [(caption, corte, s antes, s después)]"""
    fallas, avisos = [], []
    for cp in caps:
        for t in cortes:
            antes, despues = t - cp["a"], cp["z"] - t
            if antes > CLE and despues > CLE:
                fila = (cp, t, antes, despues)
                (avisos if antes < MIN_DURO and cp["z"] - cp["a"] <= MIN_DURO + CLE else fallas).append(fila)
    return fallas, avisos


def tc(t): return "%d:%05.2f" % (t // 60, t % 60)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--srt", required=True); ap.add_argument("--cortes", required=True)
    a = ap.parse_args()
    clips = leer_cortes(a.cortes); caps = leer_srt(a.srt)
    cortes = cortes_reales(clips)
    print("leído: %d captions · %d clips · %d cortes reales" % (len(caps), len(clips), len(cortes)))
    if not caps or not clips:
        print("NO SE PUDO MEDIR: sin captions o sin clips"); sys.exit(2)
    fallas, avisos = cruces(caps, cortes)
    for cp, t, an, de in fallas:
        print("  CRUZA %s «%s» · corte %s · %.2f s antes y %.2f s después" % (tc(cp["a"]), cp["txt"], tc(t), an, de))
    for cp, t, an, de in avisos:
        print("  aviso %s «%s» · sigue %.2f s después del corte %s solo para llegar a 0,5 s" % (tc(cp["a"]), cp["txt"], de, tc(t)))
    print("PASA" if not fallas else "NO PASA (%d captions cruzan un corte)" % len(fallas))
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
