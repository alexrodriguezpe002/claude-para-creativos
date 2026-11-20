#!/usr/bin/env python3
"""Mide las capas de ajuste de la secuencia activa de Premiere: cada una marca el hueco de una toma generada.

Uso:
  python3 listar_capas.py [--pista 2] [--secuencia NOMBRE] [--srt transcripcion.srt] [--json capas.json]

Para cada capa de ajuste (en todas las pistas de video, o solo en --pista) imprime: número, pista, inicio,
fin, duración exacta, la duración a PEDIR en Higgsfield (el segundo entero siguiente, nunca justo, y como
mínimo 3 s porque Kling no acepta menos) y el nombre de la capa (si quien edita la renombró con la idea de la
toma, aparece acá). Con --srt agrega lo que se dice en ese tramo. Con --json guarda todo para el plan.
También dice el tamaño y los fps de la secuencia, y el formato que hay que pedir (9:16, 16:9, 1:1).

Una capa se reconoce porque Premiere la marca como capa de ajuste o porque su nombre empieza con
"Adjustment Layer" / "Capa de ajuste". No cambia nada en el proyecto.
Salida: 0 = midió · 1 = no hay capas · 2 = no se pudo hablar con Premiere.
"""
import argparse, json, math, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import puente  # noqa: E402

JS = r"""(function(){
var s=app.project.activeSequence; if(!s) return 'ERROR no hay secuencia activa';
var esperada=%s; if(esperada && s.name!=esperada) return 'ERROR la secuencia activa es '+s.name;
var solo=%d, out=[];
function esCapa(c){
  try { if(c.projectItem && c.projectItem.isAdjustmentLayer && c.projectItem.isAdjustmentLayer()) return true; } catch(e){}
  var n=(c.projectItem ? c.projectItem.name : '') + '|' + c.name;
  return n.indexOf('Adjustment Layer')>=0 || n.indexOf('Capa de ajuste')>=0;
}
for(var t=0;t<s.videoTracks.numTracks;t++){ if(solo && t!=solo-1) continue;
  var tr=s.videoTracks[t];
  for(var i=0;i<tr.clips.numItems;i++){ var c=tr.clips[i]; if(!esCapa(c)) continue;
    out.push((t+1)+'\t'+c.start.seconds+'\t'+c.end.seconds+'\t'+c.name); } }
var st=s.getSettings();
return 'SEQ\t'+s.name+'\t'+s.frameSizeHorizontal+'\t'+s.frameSizeVertical+'\t'+(254016000000/Number(st.videoFrameRate.ticks))
  +'\t'+app.project.name+'\n'+out.join('\n');})()"""


def leer_srt(ruta):
    subs = []
    for bloque in re.split(r"\n\s*\n", open(ruta, encoding="utf-8-sig").read().strip()):
        lineas = bloque.strip().splitlines()
        for k, l in enumerate(lineas):
            m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", l)
            if m:
                g = [int(x) for x in m.groups()]
                ini = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
                fin = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
                subs.append((ini, fin, " ".join(lineas[k + 1:])))
                break
    return subs


def tc(s):
    return "%d:%06.3f" % (int(s // 60), s % 60)


def formato(w, h):
    r = w / h
    if r < 0.8:
        return "9:16"
    if r > 1.25:
        return "16:9"
    return "1:1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pista", type=int, default=0, help="solo esta pista de video (V2 = 2); por defecto todas")
    ap.add_argument("--secuencia", help="nombre esperado de la secuencia activa (se verifica)")
    ap.add_argument("--srt", help="transcripción con tiempos de la secuencia, para ver qué se dice en cada hueco")
    ap.add_argument("--json", help="guardar las capas medidas en este archivo")
    a = ap.parse_args()
    try:
        r = puente.extendscript(JS % (json.dumps(a.secuencia or ""), a.pista), 60)
    except Exception as e:
        print("ERROR", e)
        sys.exit(2)
    if r.startswith("ERROR"):
        print(r)
        sys.exit(2)
    lineas = r.splitlines()
    _, seq, w, h, fps, proyecto = lineas[0].split("\t")
    w, h, fps = int(float(w)), int(float(h)), float(fps)
    print("Proyecto %s · secuencia %s · %dx%d · %.3f fps · pedir formato %s" % (proyecto, seq, w, h, fps, formato(w, h)))
    subs = leer_srt(a.srt) if a.srt else []
    capas = []
    for l in lineas[1:]:
        p, ini, fin, nombre = l.split("\t", 3)
        ini, fin = float(ini), float(fin)
        dur = fin - ini
        pedir = max(3, math.floor(dur + 1e-6) + 1)
        dicho = " ".join(t for (i, f, t) in subs if f > ini + 0.05 and i < fin - 0.05)
        capas.append({"pista": int(p), "inicio": round(ini, 3), "fin": round(fin, 3), "duracion": round(dur, 3),
                      "pedir_s": pedir, "nombre": nombre, "dicho": dicho})
    capas.sort(key=lambda c: (c["inicio"], c["pista"]))
    if not capas:
        print("No hay capas de ajuste en la secuencia" + (" (pista V%d)" % a.pista if a.pista else "") + ".")
        sys.exit(1)
    print("%-3s %-4s %-10s %-10s %-8s %-6s %s" % ("#", "pista", "inicio", "fin", "dura", "pedir", "nombre"))
    for n, c in enumerate(capas, 1):
        print("%-3d V%-3d %-10s %-10s %-8.3f %-6s %s" % (n, c["pista"], tc(c["inicio"]), tc(c["fin"]),
                                                    c["duracion"], "%d s" % c["pedir_s"], c["nombre"]))
        if c["dicho"]:
            print("      dice: %s" % c["dicho"])
    total = sum(c["pedir_s"] for c in capas)
    print("%d capas · %d s de video a pedir · Kling 3.0 pro ≈ %.1f créditos (1,5 por segundo) + 2 por imagen"
          % (len(capas), total, total * 1.5))
    if a.json:
        json.dump({"proyecto": proyecto, "secuencia": seq, "ancho": w, "alto": h, "fps": fps,
                   "formato": formato(w, h), "capas": capas}, open(a.json, "w"), ensure_ascii=False, indent=1)
        print("guardado en", a.json)


if __name__ == "__main__":
    main()
