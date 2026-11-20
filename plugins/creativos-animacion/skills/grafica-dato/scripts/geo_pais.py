#!/usr/bin/env python3
"""Contorno de un país (Natural Earth 50m, world-atlas) → paths SVG en un cuadro, más puntos repartidos
adentro del territorio principal (muestreo tipo Poisson con semilla fija). Sale un geo.json para
build_mapa_dona.py y una vista previa PNG.

  python3 geo_pais.py Ecuador geo.json [--caja 90,0,900,900] [--dist 58] [--borde 16] [--semilla 218]
                      [--acercar -85,8.4]     # polígonos al oeste de -85° se corren 8,4° al este (Galápagos)
                      [--lat0 -1.8]           # latitud de la proyección (por defecto, la media del país)
Ecuador con las Galápagos acercadas (así está assets/geo-ecuador.json): --acercar -85,8.4 --lat0 -1.8 (el resto
por defecto).

El nombre es el de Natural Earth en inglés (Ecuador, Peru, Colombia, Spain, United States of America…).
"""
import json, math, pathlib, random, sys
from PIL import Image, ImageDraw
a = sys.argv[1:]
if len(a) < 2:
    print(__doc__); sys.exit(2)
name, out = a[0], a[1]
opt = lambda k, d: a[a.index(k) + 1] if k in a else d
bx, by, bw, bh = [float(v) for v in opt("--caja", "90,0,900,900").split(",")]
MIN_D, EDGE, SEED = float(opt("--dist", 58)), float(opt("--borde", 16)), int(opt("--semilla", 218))
acercar = [float(v) for v in opt("--acercar", "").split(",")] if "--acercar" in a else None
t = json.load(open(pathlib.Path(__file__).resolve().parent.parent / "assets" / "countries-50m.json"))
sx, sy = t["transform"]["scale"]; tx, ty = t["transform"]["translate"]
def arc(i):
    x = y = 0; pts = []
    for dx, dy in t["arcs"][i if i >= 0 else ~i]:
        x += dx; y += dy; pts.append((x * sx + tx, y * sy + ty))
    return pts if i >= 0 else pts[::-1]
def ring(idx):
    out_ = []
    for k, i in enumerate(idx):
        p = arc(i); out_.extend(p if k == 0 else p[1:])
    return out_
g = next((g for g in t["objects"]["countries"]["geometries"] if g.get("properties", {}).get("name") == name), None)
if not g:
    print("no está en Natural Earth:", name); sys.exit(2)
polys = [[ring(r) for r in poly] for poly in (g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]])]
main = max(polys, key=lambda p: len(p[0]))
lejanas = [p for p in polys if acercar and max(q[0] for q in p[0]) < acercar[0]]
islas = [p for p in polys if p is not main and p not in lejanas]
lat0 = math.radians(float(opt("--lat0", sum(q[1] for q in main[0]) / len(main[0]))))
proj = lambda lon, lat: (lon * math.cos(lat0), -lat)
shift = acercar[1] if acercar else 0.0
allp = [proj(*q) for p in [main] + islas for q in p[0]] + [proj(q[0] + shift, q[1]) for p in lejanas for q in p[0]]
xs, ys = zip(*allp); k = min(bw / (max(xs) - min(xs)), bh / (max(ys) - min(ys)))
ox = bx + (bw - (max(xs) - min(xs)) * k) / 2; oy = by + (bh - (max(ys) - min(ys)) * k) / 2
def px(lon, lat, s=0.0):
    X, Y = proj(lon + s, lat); return (ox + (X - min(xs)) * k, oy + (Y - min(ys)) * k)
def d_of(p, s=0.0):
    return " ".join("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in (px(lo, la, s) for lo, la in r)) + " Z" for r in p)
poly_px = [px(*q) for q in main[0]]
def inside(x, y):
    c = False
    for i in range(len(poly_px)):
        x1, y1 = poly_px[i]; x2, y2 = poly_px[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: c = not c
    return c
def edge(x, y):
    b = 1e9
    for i in range(len(poly_px)):
        x1, y1 = poly_px[i]; x2, y2 = poly_px[i - 1]; dx, dy = x2 - x1, y2 - y1; L = dx * dx + dy * dy or 1e-9
        u = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / L)); b = min(b, math.hypot(x - x1 - u * dx, y - y1 - u * dy))
    return b
rng = random.Random(SEED); x0 = min(p[0] for p in poly_px); x1 = max(p[0] for p in poly_px)
y0 = min(p[1] for p in poly_px); y1 = max(p[1] for p in poly_px); dots = []
for _ in range(60000):
    x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
    if inside(x, y) and edge(x, y) > EDGE and all(math.hypot(x - p, y - q) > MIN_D for p, q in dots): dots.append((x, y))
res = {"pais": name, "caja": [bx, by, bw, bh], "principal": d_of(main[0:]), "islas": " ".join(d_of(p) for p in islas),
       "lejanas": " ".join(d_of(p, shift) for p in lejanas), "puntos": [[round(x, 1), round(y, 1)] for x, y in dots],
       "bbox": [round(x0), round(y0), round(x1), round(y1)]}
json.dump(res, open(out, "w"))
im = Image.new("RGB", (int(bx * 2 + bw), int(by * 2 + bh)), (245, 245, 245)); dr = ImageDraw.Draw(im)
for p in [main] + islas: dr.polygon([px(*q) for q in p[0]], fill=(212, 226, 238), outline=(15, 92, 158))
for p in lejanas: dr.polygon([px(q[0], q[1], shift) for q in p[0]], fill=(212, 226, 238), outline=(15, 92, 158))
for x, y in dots: dr.ellipse([x - 9, y - 9, x + 9, y + 9], fill=(242, 113, 28))
prev = str(pathlib.Path(out).with_suffix(".png")); im.save(prev)
print(f"{name}: {len(polys)} polígonos, {len(dots)} puntos, vista previa {prev}")
