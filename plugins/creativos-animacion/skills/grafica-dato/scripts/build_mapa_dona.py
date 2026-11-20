#!/usr/bin/env python3
"""Gráfica de un dato con mapa + dona (pastel) + palabras clave, con la marca del cliente → index.html de HyperFrames.

  python3 build_mapa_dona.py config.json proyecto/index.html

El país se dibuja y se llena de puntos (personas); el N % de los puntos se vuelve naranja mientras la dona
se llena al N % con un contador que rueda (seek-safe: tiras de dígitos, nunca onUpdate); al final entran
las palabras clave con una línea debajo. Todo el plano respira: micro-cámara y luces de fondo.
Ver assets/ejemplo-75.json (una gráfica del 75% de ejemplo) para el formato de config.json.
Valor soportado: 1–99 (dos dígitos como máximo).
"""
import json
import math
import pathlib
import random
import sys

from PIL import ImageFont

cfg_path, out_path = sys.argv[1:3]
K = json.load(open(cfg_path))
proj = pathlib.Path(out_path).parent
geo = json.load(open(proj / K["geo"]))
W, H, DUR = K.get("width", 1080), K.get("height", 1920), K.get("duration", 7)
col = K.get("colores", {})
BLUE, ORANGE = col.get("azul", "#0F5C9E"), col.get("naranja", "#F2711C")
PAPER, PAPER2, LAND = col.get("papel", "#f7f7f7"), col.get("papel2", "#ececec"), col.get("tierra", "#d4e2ee")


def rgba(hexc, alpha):
    """'#RRGGBB' + opacidad (texto, ej. "0.30") -> 'rgba(r,g,b,a)': las luces y la sombra salen de la marca."""
    h = hexc.lstrip("#")
    return "rgba(%d,%d,%d,%s)" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


VAL = int(K["valor"]); assert 1 <= VAL <= 99, "valor entre 1 y 99"
SUF = K.get("sufijo", "%")
PAIS = K.get("pais", "")
PAL = K.get("palabras", [])
FPS = str(K.get("fps", "24000/1001"))
FONT = K.get("font_file", "assets/fonts/marca.ttf")
T = dict(contorno=0.12, pais=1.5, puntos=1.6, sube=2.2, dona=2.45, llena=2.6, llena_dur=1.0, sufijo=3.05,
         pulso=3.75, palabra1=4.95, palabra2=5.3, subrayado=5.55)
T.update(K.get("tiempos", {}))

dots = geo["puntos"]
n = len(dots)
n_or = round(n * VAL / 100)
rng = random.Random(K.get("semilla", 75))
blue_idx = set(rng.sample(range(n), n - n_or))            # los que quedan azules, repartidos
orange = [i for i in range(n) if i not in blue_idx]
orange.sort(key=lambda i: dots[i][0] + 0.35 * dots[i][1])  # ola de oeste a este
pop_order = list(range(n)); rng.shuffle(pop_order)

circles = "".join(f'<circle id="d{i}" class="dot" cx="{x}" cy="{y}" r="0" />' for i, (x, y) in enumerate(dots))

R, SW = 262, 74                                             # dona: radio y grosor
C = 2 * math.pi * R
TENS_N = VAL // 10
TENS = "".join(f"<span>{d}</span>" for d in range(0, TENS_N + 1))
ONES = "".join(f"<span>{d % 10}</span>" for d in range(0, VAL + 1))
DIG = 196                                                   # alto de cada cifra (px)
if K.get("subrayado_ancho"):
    UW = int(K["subrayado_ancho"])
else:
    _f = ImageFont.truetype(str(proj / FONT), 118)
    try: _f.set_variation_by_axes([800])
    except Exception: pass
    UW = int(_f.getlength(PAL[-1]) + 20) if PAL else 0
W1 = PAL[0] if len(PAL) == 2 else ""
W2 = PAL[-1] if PAL else ""
UTOP = 1500 + (104 if W1 else 0) + 132 + 6

html = f"""<!doctype html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      @font-face {{ font-family: "Marca"; src: url("{FONT}") format("truetype"); font-weight: 200 800; }}
      :root {{ --blue: {BLUE}; --orange: {ORANGE}; --paper: {PAPER}; --paper-2: {PAPER2}; --land: {LAND}; }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: {W}px; height: {H}px; overflow: hidden; background: var(--paper); }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; font-family: "Marca", sans-serif; }}
      #bg {{ position: absolute; inset: 0; background: linear-gradient(160deg, #fbfbfb 0%, var(--paper) 45%, var(--paper-2) 100%); }}
      .light {{ position: absolute; border-radius: 50%; pointer-events: none; }}
      #light1 {{ width: 1500px; height: 1500px; left: -420px; top: -380px;
                 background: radial-gradient(circle, rgba(255,255,255,0.95) 0%, rgba(255,255,255,0) 62%); }}
      #light2 {{ width: 1100px; height: 1100px; left: -10px; top: 560px; opacity: 0;
                 background: radial-gradient(circle, {rgba(ORANGE, "0.30")} 0%, {rgba(ORANGE, "0")} 65%); }}
      #light3 {{ width: 1200px; height: 1200px; left: -60px; top: -200px;
                 background: radial-gradient(circle, {rgba(BLUE, "0.10")} 0%, {rgba(BLUE, "0")} 62%); }}
      #stage {{ position: absolute; inset: 0; }}
      #mapwrap {{ position: absolute; left: 0; top: 0; width: {W}px; height: 900px; }}
      #mapsvg {{ position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible;
                 filter: drop-shadow(0 22px 34px {rgba(BLUE, "0.20")}); }}
      .land {{ fill: var(--land); fill-opacity: 0; stroke: var(--blue); stroke-width: 4; stroke-linejoin: round; }}
      .isle {{ fill: var(--land); stroke: var(--blue); stroke-width: 3; stroke-linejoin: round; opacity: 0; }}
      .dot {{ fill: var(--blue); fill-opacity: 0.55; }}
      #ecu-label {{ position: absolute; left: 0; right: 0; top: 836px; text-align: center; font-weight: 800; font-size: 74px; letter-spacing: 0.14em; padding-left: 0.14em;
                    color: var(--blue); opacity: 0; }}
      #donut {{ position: absolute; left: {540 - 340}px; top: {1110 - 340}px; width: 680px; height: 680px; opacity: 0; }}
      #donut svg {{ position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }}
      .track {{ fill: none; stroke: var(--blue); stroke-opacity: 0.12; stroke-width: {SW}; }}
      .arc {{ fill: none; stroke: var(--orange); stroke-width: {SW}; stroke-dasharray: {C:.2f} {C:.2f};
              stroke-dashoffset: {C:.2f}; }}
      .ring {{ fill: none; stroke: var(--orange); stroke-width: 6; opacity: 0; }}
      #count {{ position: absolute; left: 0; right: 0; top: {340 - DIG // 2}px; height: {DIG}px; display: flex;
                justify-content: center; align-items: flex-start; color: var(--blue); font-weight: 800;
                font-size: {DIG}px; line-height: {DIG}px; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }}
      .roll {{ height: {DIG}px; overflow: hidden; }}
      .strip {{ display: flex; flex-direction: column; }}
      .strip span {{ display: block; height: {DIG}px; }}
      #pct {{ font-size: 118px; line-height: {DIG}px; color: var(--blue); margin-left: 6px; opacity: 0; }}
      #words {{ position: absolute; left: 0; right: 0; top: 1500px; text-align: center; }}
      .w {{ display: block; font-weight: 800; letter-spacing: 0.04em; opacity: 0; }}
      #w1 {{ font-size: 92px; line-height: 104px; color: var(--blue); }}
      #w2 {{ font-size: 118px; line-height: 132px; color: var(--blue); }}
      #w2bar {{ position: absolute; left: 50%; top: {UTOP}px; width: {UW}px; margin-left: -{UW // 2}px; height: 16px;
                border-radius: 8px; background: var(--orange); transform-origin: 0 50%; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{DUR}" data-fps="{FPS}"
         data-width="{W}" data-height="{H}">
      <div id="scene" class="clip" data-start="0" data-duration="{DUR}" data-track-index="0">
        <div id="bg"></div>
        <div id="light3" class="light"></div>
        <div id="light1" class="light"></div>
        <div id="light2" class="light"></div>
        <div id="stage">
          <div id="mapwrap">
            <svg id="mapsvg" viewBox="0 0 {W} 900" xmlns="http://www.w3.org/2000/svg">
              <path id="ecu-main" class="land" d="{geo['principal']}" />
              <path id="ecu-coast" class="isle" d="{geo['islas'] or 'M0,0'}" />
              <path id="ecu-gal" class="isle" d="{geo['lejanas'] or 'M0,0'}" />
              <g id="dots">{circles}</g>
            </svg>
            <div id="ecu-label">{PAIS}</div>
          </div>
          <div id="donut">
            <svg viewBox="0 0 680 680" xmlns="http://www.w3.org/2000/svg">
              <circle class="track" cx="340" cy="340" r="{R}" />
              <circle id="arc" class="arc" cx="340" cy="340" r="{R}" transform="rotate(-90 340 340)" />
              <circle id="ring" class="ring" cx="340" cy="340" r="{R + SW / 2 + 8:.0f}" />
            </svg>
            <div id="count">
              <div class="roll"><div id="tens" class="strip" data-layout-allow-overflow="true">{TENS}</div></div>
              <div class="roll"><div id="ones" class="strip" data-layout-allow-overflow="true">{ONES}</div></div>
              <div id="pct">{SUF}</div>
            </div>
          </div>
          <div id="words"><span id="w1" class="w">{W1}</span><span id="w2" class="w">{W2}</span></div>
          <div id="w2bar"></div>
        </div>
      </div>
    </div>
    <script>
      const C = {C:.2f}, DIG = {DIG};
      const POP = {json.dumps(pop_order)};
      const ORANGE_ORDER = {json.dumps(orange)};
      const tl = gsap.timeline({{ paused: true }});

      // cámara y fondo vivo, todo el plano
      tl.fromTo("#stage", {{ scale: 1 }}, {{ scale: 1.035, duration: {DUR}, ease: "sine.inOut", transformOrigin: "50% 45%" }}, 0);
      tl.fromTo("#light1", {{ x: -140, y: 80 }}, {{ x: 160, y: -60, duration: {DUR}, ease: "sine.inOut" }}, 0);
      tl.fromTo("#light3", {{ x: 60, y: 0 }}, {{ x: -80, y: 120, duration: {DUR}, ease: "sine.inOut" }}, 0);

      // 1 · las primeras palabras de la frase: el mapa se dibuja
      const main = document.getElementById("ecu-main");
      const L = main.getTotalLength();
      tl.fromTo("#mapwrap", {{ y: 360, scale: 1 }}, {{ y: 360, scale: 1, duration: 0.01 }}, 0);
      tl.set(main, {{ strokeDasharray: L, strokeDashoffset: L, fillOpacity: 0 }}, 0);
      tl.to(main, {{ strokeDashoffset: 0, duration: 1.15, ease: "power2.inOut" }}, {T["contorno"]});
      tl.to(main, {{ fillOpacity: 1, duration: 0.7, ease: "power1.out" }}, {T["contorno"] + 0.63:.2f});
      tl.fromTo(["#ecu-coast", "#ecu-gal"], {{ opacity: 0 }}, {{ opacity: 1, duration: 0.5, ease: "power1.out" }}, {T["contorno"] + 0.88:.2f});

      // 2 · "en nuestro país": el nombre del país y los puntos-persona por todo el territorio
      tl.fromTo("#ecu-label", {{ autoAlpha: 0, y: 26 }}, {{ autoAlpha: 1, y: 0, duration: 0.45, ease: "power3.out" }}, {T["pais"]});
      POP.forEach((i, k) => {{
        tl.fromTo("#d" + i, {{ attr: {{ r: 0 }} }}, {{ attr: {{ r: 13 }}, duration: 0.28, ease: "back.out(2.2)" }}, {T["puntos"]} + k * 0.011);
      }});

      // 3 · "el 75 %": el mapa sube, entra la dona, se llena y los puntos se vuelven naranjas
      tl.to("#mapwrap", {{ y: -40, scale: 0.6, duration: 0.7, ease: "power3.inOut", transformOrigin: "540px 450px" }}, {T["sube"]});
      tl.fromTo("#donut", {{ autoAlpha: 0, scale: 0.86 }}, {{ autoAlpha: 1, scale: 1, duration: 0.55, ease: "power3.out" }}, {T["dona"]});
      tl.fromTo("#light2", {{ opacity: 0, scale: 0.85 }}, {{ opacity: 1, scale: 1.05, duration: 1.2, ease: "power2.out" }}, {T["dona"] + 0.05:.2f});
      tl.fromTo("#arc", {{ strokeDashoffset: C }}, {{ strokeDashoffset: C * {1 - VAL / 100:.4f}, duration: {T["llena_dur"]}, ease: "power2.out" }}, {T["llena"]});
      tl.fromTo("#tens", {{ y: 0 }}, {{ y: -{TENS_N} * DIG, duration: {T["llena_dur"]}, ease: "power2.out" }}, {T["llena"]});
      tl.fromTo("#ones", {{ y: 0 }}, {{ y: -{VAL} * DIG, duration: {T["llena_dur"]}, ease: "power2.out" }}, {T["llena"]});
      tl.fromTo("#pct", {{ autoAlpha: 0, scale: 0.6 }}, {{ autoAlpha: 1, scale: 1, duration: 0.35, ease: "back.out(2)" }}, {T["sufijo"]});
      ORANGE_ORDER.forEach((i, k) => {{
        const t = {T["llena"]} + k * {0.022 * 39 / max(1, n_or):.4f};
        tl.to("#d" + i, {{ fill: "{ORANGE}", fillOpacity: 1, duration: 0.18, ease: "power1.out" }}, t);
        tl.to("#d" + i, {{ attr: {{ r: 18 }}, duration: 0.14, ease: "power2.out" }}, t);
        tl.to("#d" + i, {{ attr: {{ r: 13 }}, duration: 0.26, ease: "power2.inOut" }}, t + 0.14);
      }});
      tl.fromTo("#ring", {{ opacity: 0.55, scale: 1 }}, {{ opacity: 0, scale: 1.18, duration: 0.8, ease: "power2.out", svgOrigin: "340 340" }}, {T["llena"] + T["llena_dur"] - 0.05:.2f});

      // 4 · "de las personas": los puntos naranjas laten una vez
      ORANGE_ORDER.forEach((i, k) => {{
        const t = {T["pulso"]} + k * {0.012 * 39 / max(1, n_or):.4f};
        tl.to("#d" + i, {{ attr: {{ r: 16 }}, duration: 0.18, ease: "sine.out" }}, t);
        tl.to("#d" + i, {{ attr: {{ r: 13 }}, duration: 0.3, ease: "sine.inOut" }}, t + 0.18);
      }});

      // 5 · las palabras clave, con la línea debajo
      tl.fromTo("#w1", {{ autoAlpha: 0, y: 46 }}, {{ autoAlpha: 1, y: 0, duration: 0.5, ease: "power3.out" }}, {T["palabra1"]});
      tl.fromTo("#w2", {{ autoAlpha: 0, y: 46, scale: 0.94 }}, {{ autoAlpha: 1, y: 0, scale: 1, duration: 0.55, ease: "power3.out" }}, {T["palabra2"]});

      tl.fromTo("#w2bar", {{ scaleX: 0 }}, {{ scaleX: 1, duration: 0.5, ease: "power3.inOut" }}, {T["subrayado"]});

      // 6 · cierre: el brillo de la dona respira
      tl.to("#light2", {{ opacity: 0.7, duration: 0.8, ease: "sine.inOut", yoyo: true, repeat: {max(0, int((DUR - T["pulso"] - 0.05) / 0.8) - 1)} }}, {T["pulso"] + 0.05:.2f});

      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
"""
open(out_path, "w").write(html)
print("ok", out_path, f"· {PAIS} · {VAL}{SUF} · puntos {n}, naranjas {n_or} · palabras {PAL} · {FPS} fps, {DUR}s")
