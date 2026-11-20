#!/usr/bin/env python3
"""Cruza verify.log (pases 2-3) con candidates.md (pase 1) en una tabla legible.

  python adjudicar.py --log <workdir>/verify.log --candidates <workdir>/candidates.md \
      [--out <workdir>/adjudicados.json]

Por cada divergencia: cue, palabra del SRT, palabra del ASR, la lectura a cada tempo, si
los tempos coinciden, y si la palabra del SRT / del ASR aparece en cada lectura. El script
NO decide: ordena la evidencia para que la decisión sea rápida y quede trazable.

Las etiquetas de los spots deben ser "c<cue>_<palabra>" como las genera este flujo:
    python adjudicar.py --candidates candidates.md --spots-out spots.txt   # genera el --spots
"""
import argparse, json, re, sys, unicodedata


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return re.sub(r"[^a-z0-9 ]", "", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()


def parse_candidates(path):
    txt = open(path, encoding="utf-8").read()
    out = []
    for b in re.split(r"\n## ", txt)[1:]:
        m = re.match(r"(\d+)\. cue #(\d+) · ([\d:.]+) · audio ([\d.]+)s · (\w+)", b)
        if not m: continue
        g = lambda k: (re.search(r"- %s: «(.*?)»" % k, b) or [None, ""])[1]
        conf = re.search(r"- ASR confidence: (.*)", b)
        out.append({"n": int(m.group(1)), "cue": int(m.group(2)), "tc": m.group(3), "t": float(m.group(4)),
                    "op": m.group(5), "srt": g("SRT"), "asr": g("ASR"), "conf": conf.group(1).strip() if conf else ""})
    return out


def etiqueta(c):
    return "c%d_%s" % (c["cue"], re.sub(r"[^a-z0-9]", "", (c["srt"] or c["asr"]).lower())[:10] or c["op"])


def parse_log(path):
    spots = {}
    for b in re.split(r"\n(?==== )", open(path, encoding="utf-8").read()):
        m = re.match(r"=== (\S+)\s+\[([\d.]+)–([\d.]+)s\] ===", b)
        if not m: continue
        lect = {t: re.sub(r"\(\d\.\d\d\)", "", x).strip() for t, x in re.findall(r"@ ([\d.]+)x\s+(.*)", b)}
        spots[m.group(1)] = {"lecturas": lect, "acuerdo": "all tempos agree" in b}
    return spots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True); ap.add_argument("--log")
    ap.add_argument("--out"); ap.add_argument("--spots-out", help="escribe la lista --spots para verify_spots.py y sale")
    ap.add_argument("--margen", type=float, default=1.0, help="segundos de contexto a cada lado (mínimo recomendado 1,0)")
    a = ap.parse_args()
    C = parse_candidates(a.candidates)

    if a.spots_out:
        seen, spots = set(), []
        for c in C:
            lab = etiqueta(c)
            if lab in seen: lab += "_%d" % c["n"]
            seen.add(lab); spots.append("%.2f-%.2f:%s" % (max(0, c["t"] - a.margen), c["t"] + a.margen + 0.7, lab))
        open(a.spots_out, "w").write(",".join(spots))
        print("%d spots → %s  (pasar con --spots \"$(cat %s)\")" % (len(spots), a.spots_out, a.spots_out)); return 0

    if not a.log: sys.exit("falta --log (o usar --spots-out para generar los spots)")
    S = parse_log(a.log)
    out = []
    for c in C:
        s = S.get(etiqueta(c)) or S.get(etiqueta(c) + "_%d" % c["n"])
        if not s: continue
        sn, an = norm(c["srt"]), norm(c["asr"])
        lecturas = s["lecturas"]
        en_srt = {t: (sn in norm(l)) if sn else None for t, l in lecturas.items()}
        en_asr = {t: (an in norm(l)) if an else None for t, l in lecturas.items()}
        ruido = all(("gracias" == norm(l).strip() or not l.strip()) for l in lecturas.values())
        out.append({**c, "lecturas": lecturas, "acuerdo": s["acuerdo"], "srt_en_lecturas": en_srt,
                    "asr_en_lecturas": en_asr, "sin_senal": ruido})
    if a.out: json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)

    def tag(d):
        v = [x for x in d.values() if x is not None]
        return "✓" if v and all(v) else ("✗" if v and not any(v) else "~")
    print("cruzados %d de %d divergencias" % (len(out), len(C)))
    print("leyenda: SRT✓ = la palabra del archivo aparece en TODAS las lecturas · ASR✓ = la del pase 1 también · "
          "agree/DIS = tempos coinciden · SIN SEÑAL = el modelo devolvió 'Gracias.'/nada (voz lejana)\n")
    for o in out:
        flag = "SIN SEÑAL" if o["sin_senal"] else ("agree" if o["acuerdo"] else "DIS")
        print("cue%3d %6.1fs %-7s SRT%s ASR%s %-9s SRT«%s» ASR«%s»" % (
            o["cue"], o["t"], o["op"], tag(o["srt_en_lecturas"]), tag(o["asr_en_lecturas"]), flag, o["srt"][:22], o["asr"][:22]))
        for t, l in o["lecturas"].items(): print("        @%sx  %s" % (t, l[:100]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
