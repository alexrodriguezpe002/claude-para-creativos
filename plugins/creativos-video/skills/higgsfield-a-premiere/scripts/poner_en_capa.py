#!/usr/bin/env python3
"""Pone una toma aprobada en lugar de su capa de ajuste en la timeline de Premiere.

Uso:
  python3 poner_en_capa.py "<ruta del archivo en EXTRA/>" <inicio aprox de la capa, en s>
                           [--pista N] [--secuencia NOMBRE] [--desde S] [--escala 101] [--bin EXTRA] [--prueba]

Qué hace (por el panel MCP Bridge, sobre el proyecto y la secuencia ACTIVOS):
  1. Busca el archivo en el proyecto. Si no está, lo importa al bin EXTRA (lo crea si falta).
  2. Busca la capa de ajuste MÁS CERCANA a ese inicio (hasta 1 s), en --pista o en todas las pistas de video.
     El inicio es aproximado a propósito: quien edita mueve la timeline mientras se trabaja.
  3. Borra la capa, pone in/out en el clip con la duración exacta de la capa (desde --desde si el arranque de
     la toma no sirve), overwriteClip en la misma pista y tramo, limpia in/out.
  4. Corrige el cuadro de menos (Kling sale a 24 fps y la secuencia suele ir a 23,976): fin = fin exacto de la capa.
  5. Motion > Scale = 101 % (al 100 % se ve un borde de lo que está detrás: Kling sale 1076x1928).
  6. Verifica que los clips siguientes de la pista no se movieron y guarda el proyecto.

Con --prueba solo busca el archivo y la capa y dice qué haría, sin tocar nada.
Salida OK: "puesto 3.921-7.257 capa 3.921-7.257 exacto=true escala=101 siguiente_igual=true guardado".
Una línea que empieza con ERROR = no se cambió nada después de ese punto; revisar.
Basado en el script original del editor, probado con 5 tomas exactas el vie 06-11-2026.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import puente  # noqa: E402

BUSCAR = r"""(function(){var nombre=%s, ruta=%s, binNom=%s, importar=%s;
function rec(b,f){for(var i=0;i<b.children.numItems;i++){var c=b.children[i];if(c.type==2){var r=rec(c,f);if(r)return r;}else if(f(c))return c;}return null;}
var p=rec(app.project.rootItem,function(c){var m=''; try{m=c.getMediaPath();}catch(e){} return m==ruta || (c.name==nombre && m.indexOf(nombre)>=0);});
if(p) return 'OK '+p.nodeId+' '+p.treePath;
if(!importar) return 'NADA';
var bin=null; for(var i=0;i<app.project.rootItem.children.numItems;i++){var c=app.project.rootItem.children[i]; if(c.type==2 && c.name==binNom) bin=c;}
if(!bin){ app.project.rootItem.createBin(binNom);
  for(var i=0;i<app.project.rootItem.children.numItems;i++){var c=app.project.rootItem.children[i]; if(c.type==2 && c.name==binNom) bin=c;} }
app.project.importFiles([ruta], true, bin || app.project.rootItem, false);
p=rec(app.project.rootItem,function(c){var m=''; try{m=c.getMediaPath();}catch(e){} return m==ruta;});
return p ? 'IMPORTADO '+p.nodeId+' '+p.treePath : 'ERROR no se pudo importar '+ruta;})()"""

PONER = r"""(function(){var P=app.project; var s=P.activeSequence; if(!s) return 'ERROR no hay secuencia activa';
var esperada=%s; if(esperada && s.name!=esperada) return 'ERROR la secuencia activa es '+s.name;
var solo=%d, ini=%f, desde=%f, escala=%f, prueba=%s, nid=%s;
function esCapa(c){
  try { if(c.projectItem && c.projectItem.isAdjustmentLayer && c.projectItem.isAdjustmentLayer()) return true; } catch(e){}
  var n=(c.projectItem ? c.projectItem.name : '') + '|' + c.name;
  return n.indexOf('Adjustment Layer')>=0 || n.indexOf('Capa de ajuste')>=0;
}
var cap=null, tr=null, ti=-1, best=1;
for(var t=0;t<s.videoTracks.numTracks;t++){ if(solo && t!=solo-1) continue; var T=s.videoTracks[t];
  for(var i=0;i<T.clips.numItems;i++){var c=T.clips[i]; var d=Math.abs(c.start.seconds-ini);
    if(esCapa(c) && d<best){best=d;cap=c;tr=T;ti=t;}}}
if(!cap) return 'ERROR no hay capa de ajuste a menos de 1 s de '+ini.toFixed(3);
var stT=cap.start.ticks, enT=cap.end.ticks, st=cap.start.seconds, dur=cap.end.seconds-cap.start.seconds;
if(prueba) return 'PRUEBA capa '+st.toFixed(3)+'-'+cap.end.seconds.toFixed(3)+' ('+dur.toFixed(3)+' s) en V'+(ti+1)+' de '+s.name+' ('+P.name+')';
var p=null; function rec(b){for(var i=0;i<b.children.numItems;i++){var c=b.children[i];if(c.type==2)rec(c);else if(c.nodeId==nid)p=c;}} rec(P.rootItem);
if(!p) return 'ERROR el archivo ya no está en el proyecto';
var nxt=[];for(var i=0;i<tr.clips.numItems;i++){var c=tr.clips[i];if(c.start.seconds>=cap.end.seconds-0.001&&c.start.seconds<cap.end.seconds+5)nxt.push(c.name+'@'+c.start.ticks);}
cap.remove(0,0);
p.setInPoint(desde,4); p.setOutPoint(desde+dur,4); tr.overwriteClip(p, st); p.clearInPoint(4); p.clearOutPoint(4);
var n=null; for(var i=0;i<tr.clips.numItems;i++){var c=tr.clips[i]; if(c.projectItem && c.projectItem.nodeId==nid && Math.abs(c.start.seconds-st)<0.05) n=c;}
if(!n) return 'ERROR la capa se borró pero la toma no quedó en la timeline: revisar a mano (Cmd+Z)';
var t2=new Time(); t2.ticks=enT; n.end=t2;
var sc='?'; for(var k=0;k<n.components.numItems;k++){var cm=n.components[k]; if(cm.matchName=='AE.ADBE Motion'){
  for(var j=0;j<cm.properties.numItems;j++){var pr=cm.properties[j]; if(pr.displayName=='Scale'||pr.displayName=='Escala'){pr.setValue(escala,true); sc=pr.getValue();}}}}
var nxt2=[];for(var i=0;i<tr.clips.numItems;i++){var c=tr.clips[i];if(c.start.seconds>=n.end.seconds-0.001&&c.start.seconds<n.end.seconds+5)nxt2.push(c.name+'@'+c.start.ticks);}
P.save();
return 'puesto '+n.start.seconds.toFixed(3)+'-'+n.end.seconds.toFixed(3)+' capa '+st.toFixed(3)+'-'+(st+dur).toFixed(3)
 +' exacto='+(n.start.ticks==stT&&n.end.ticks==enT)+' escala='+sc+' siguiente_igual='+(nxt.join(',')==nxt2.join(','))+' guardado';})()"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archivo", help="ruta del archivo aprobado (normalmente en EXTRA/ del proyecto)")
    ap.add_argument("inicio", type=float, help="inicio aproximado de la capa, en segundos (de listar_capas.py)")
    ap.add_argument("--pista", type=int, default=0, help="pista de video (V2 = 2); por defecto busca en todas")
    ap.add_argument("--secuencia", help="nombre esperado de la secuencia activa (se verifica)")
    ap.add_argument("--desde", type=float, default=0.0, help="segundo de la toma desde donde usarla (arranque que no sirve)")
    ap.add_argument("--escala", type=float, default=101.0, help="Motion > Scale en %% (101 por defecto)")
    ap.add_argument("--bin", default="EXTRA", help="bin donde importarla si no está en el proyecto")
    ap.add_argument("--prueba", action="store_true", help="solo buscar, no cambiar nada")
    a = ap.parse_args()
    ruta = os.path.abspath(os.path.expanduser(a.archivo))
    if not os.path.isfile(ruta):
        sys.exit("ERROR no existe el archivo %s" % ruta)
    nombre = os.path.basename(ruta)

    def es(js, espera=90):
        return puente.extendscript(js, espera)

    r = es(BUSCAR % (json.dumps(nombre), json.dumps(ruta), json.dumps(a.bin), "false" if a.prueba else "true"))
    print("proyecto:", r)
    if r.startswith("ERROR"):
        sys.exit(1)
    nid = r.split()[1] if not r.startswith("NADA") else ""
    out = es(PONER % (json.dumps(a.secuencia or ""), a.pista, a.inicio, a.desde, a.escala,
                      "true" if a.prueba else "false", json.dumps(nid)))
    print(out)
    if out.startswith("ERROR") or "exacto=false" in out or "siguiente_igual=false" in out:
        sys.exit(1)


if __name__ == "__main__":
    main()
