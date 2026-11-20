#!/usr/bin/env python3
"""Hoja de contacto con título y subtítulo por imagen (o por el cuadro de un video), para mandarle al editor.

  python3 contact_sheet.py salida.jpg "img1.png|1A · Salivales|3/4 derecha" "clip.mp4@1.5|2E · Oral|frontal" ...

Un video se indica como ruta@segundo. Opciones: --width 600 (ancho de cada miniatura), --cols 5.
"""
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

args = sys.argv[1:]
width, cols = 600, 5
if "--width" in args:
    i = args.index("--width"); width = int(args[i + 1]); del args[i:i + 2]
if "--cols" in args:
    i = args.index("--cols"); cols = int(args[i + 1]); del args[i:i + 2]
out, items = args[0], args[1:]
if not items:
    print("sin imágenes"); sys.exit(2)

BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
F, f = ImageFont.truetype(BOLD, max(22, width // 16)), ImageFont.truetype(REG, max(18, width // 21))


def load(spec):
    if "@" in spec and spec.rsplit("@", 1)[0].lower().endswith((".mp4", ".mov")):
        path, t = spec.rsplit("@", 1)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", t, "-i", path, "-frames:v", "1", tmp], check=True)
        return Image.open(tmp).convert("RGB")
    return Image.open(spec).convert("RGB")


tiles = []
for it in items:
    parts = it.split("|") + ["", ""]
    im = load(parts[0])
    h = int(width * im.height / im.width)
    tiles.append((im.resize((width, h), Image.LANCZOS), parts[1], parts[2]))
pad, head = 16, max(80, width // 6)
th = max(t[0].height for t in tiles)
c = min(cols, len(tiles)); r = (len(tiles) + c - 1) // c
sheet = Image.new("RGB", (c * (width + pad) + pad, r * (th + head + pad) + pad), (16, 16, 16))
d = ImageDraw.Draw(sheet)
for k, (im, t1, t2) in enumerate(tiles):
    x = pad + (k % c) * (width + pad); y = pad + (k // c) * (th + head + pad)
    d.text((x + 4, y), t1, font=F, fill=(255, 210, 90))
    d.text((x + 4, y + head // 2), t2, font=f, fill=(210, 210, 210))
    sheet.paste(im, (x, y + head))
sheet.save(out, quality=90)
print(out, sheet.size, len(tiles), "miniaturas")
