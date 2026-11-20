#!/usr/bin/env python3
"""Elimina cues cuyo texto repite EXACTAMENTE el del cue anterior, extendiendo el anterior
hasta el fin del duplicado para no dejar un hueco. Renumera. Preserva BOM y CRLF.

Es el ÚNICO paso de esta skill que mueve timecodes (los del cue fusionado). Correrlo
DESPUÉS de apply_fixes.py, sobre su salida, y reportar aparte cuántos cues se fusionaron.

  python quitar_duplicados.py --srt "<archivo CORREGIDO>.srt" [--cortes cortes.json] [--out "<salida>.srt"] [--dry-run]

Un tartamudeo se escribe una vez: si el audio confirma que la frase se dice una sola vez
(verify_spots), el cue repetido sobra. Si la hablante REALMENTE la repite, no usar esto.

--cortes (video editado en Premiere): si entre los dos cues hay un corte, NO se fusionan: queda el de DESPUÉS
del corte con su tiempo y se borra el de antes. Fusionar estiraría el de antes por encima del corte y el texto
se leería antes de que se diga (regla del editor, 2026-10-28; gate cruce_cortes.py).
"""
import argparse, re, sys

from cruce_cortes import cortes_reales, leer_cortes

ap = argparse.ArgumentParser()
ap.add_argument("--srt", required=True); ap.add_argument("--out"); ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--cortes")
a = ap.parse_args()
cortes = cortes_reales(leer_cortes(a.cortes)) if a.cortes else []
seg = lambda s: int(s[:2]) * 3600 + int(s[3:5]) * 60 + float(s[6:].strip().replace(",", "."))

raw = open(a.srt, "rb").read()
bom = raw.startswith(b"\xef\xbb\xbf")
txt = raw.decode("utf-8-sig"); crlf = "\r\n" in txt; txt = txt.replace("\r\n", "\n")

cues = []
for b in re.split(r"\n\s*\n", txt.strip()):
    ls = b.split("\n")
    if len(ls) < 3 or "-->" not in ls[1]: continue
    cues.append({"tc": ls[1].strip(), "txt": "\n".join(ls[2:]).strip()})

out, quitados, del_otro_lado = [], [], []
for c in cues:
    if out and c["txt"] == out[-1]["txt"]:
        a0 = seg(out[-1]["tc"].split(" --> ")[0]); c0 = seg(c["tc"].split(" --> ")[0])
        if any(a0 + 0.04 < t <= c0 + 0.04 for t in cortes):     # corte en el medio: queda el de después
            del_otro_lado.append(out.pop()); out.append(dict(c)); continue
        out[-1]["tc"] = "%s --> %s" % (out[-1]["tc"].split(" --> ")[0], c["tc"].split(" --> ")[1])
        quitados.append(c); continue
    out.append(dict(c))

print("cues: %d → %d | duplicados fusionados con el anterior: %d | con un corte en el medio (queda el de después): %d"
      % (len(cues), len(out), len(quitados), len(del_otro_lado)))
for q in quitados: print("   %s  %r" % (q["tc"], q["txt"][:60]))
for q in del_otro_lado: print("   borrado el de antes del corte: %s  %r" % (q["tc"], q["txt"][:60]))
if a.dry_run: print("(dry run — nada escrito)"); sys.exit(0)

dest = a.out or a.srt.replace(".srt", " SIN DUPLICADOS.srt")
if dest == a.srt: sys.exit("REFUSED: no piso el archivo de entrada")
nl = "\r\n" if crlf else "\n"
body = nl.join("%d%s%s%s%s%s" % (i, nl, c["tc"], nl, c["txt"].replace("\n", nl), nl) for i, c in enumerate(out, 1)) + nl
with open(dest, "wb") as f:
    if bom: f.write(b"\xef\xbb\xbf")
    f.write(body.encode("utf-8"))
print("→", dest)
