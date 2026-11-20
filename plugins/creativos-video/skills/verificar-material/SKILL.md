---
name: verificar-material
description: "Comprueba que una copia de material de cámara (un respaldo viejo, un disco de rodaje, una carpeta que entregaron) sigue idéntica a cuando se copió: relee cada archivo y lo compara con su manifiesto .mhl (los de descargar-tarjeta, Hedge, OffShoot, ShotPut o Silverstack; MHL 1.1 y ASC MHL). Dice qué cambió, qué falta y qué se agregó, compara dos copias entre sí, repara una copia dañada desde la buena sin borrar nada, crea el manifiesto de una carpeta que no tiene y rehace el informe. Mac y Windows. Usar cuando la persona diga «verifica el respaldo», «¿está bien este disco?», «¿se dañó algo?», «compara las dos copias», «revisa el material del rodaje de octubre», «este clip no abre, ¿se corrompió?», «haz el checksum», «crea el manifiesto» o «pásame el informe de la descarga». Es para material de cámara; el respaldo del sistema de Claude es «respaldar»."
---

# Verificar material

Motor (el mismo de descargar-tarjeta): `${CLAUDE_PLUGIN_ROOT}/skills/descargar-tarjeta/scripts/descarga.py`.
Mac: `python3 "<motor>"` · Windows: `py "<motor>"`. Solo lee, salvo «reparar» y «manifiesto», que piden OK.

## 1. Verificar

```
python3 "<motor>" verificar "<carpeta de la tarjeta>" ["<la otra copia de esa tarjeta>"]
```

- Se verifica **la carpeta de cada tarjeta** (la que tiene el `.mhl` en su raíz, o una carpeta `ascmhl/`), no el
  disco entero. Si la persona da un disco o un proyecto, buscar esas carpetas (los `.mhl` y las `ascmhl/`) y
  verificar cada una; si son muchas o pesan mucho, en segundo plano.
- Dos carpetas con el mismo nombre (A001 en cada disco) además se comparan entre sí; `--comparar` lo fuerza.
- `--rapido`: solo mira que estén todos y con su tamaño (segundos). Sirve de primer vistazo; la verificación real
  relee todo (en un disco rígido, unos 150–250 MB/s).

Resultado, en simple: ✅ idénticos · ❌ CAMBIÓ (el archivo tiene otros bytes) · ❌ Falta · ❌ Tamaño distinto ·
ℹ️ archivos nuevos (agregados después) · ⚠️ no se pudo comprobar. Queda `_DESCARGA/verificacion_<fecha>.csv`.

## 2. Si algo cambió o falta

Preguntar (🔔) si se repara, diciendo desde dónde: la otra copia o la tarjeta, si todavía no se formateó.

```
python3 "<motor>" reparar "<copia dañada>" --desde "<copia buena o tarjeta>"
```

Antes de copiar comprueba que el bueno coincide con el manifiesto; después verifica la copia nueva. El dañado no se
borra: queda como `<archivo>.DANADO_<fecha>` (se borra a mano si la persona quiere). Si no hay ninguna copia
buena, decirlo claro y no tocar nada. Un disco que empieza a dar errores: copiar su material a otro disco cuanto
antes (con `descargar-tarjeta`, usando la carpeta como origen).

## 3. Sin manifiesto

No hay contra qué comparar: explicarlo. Ofrecer crear uno (con OK):
`python3 "<motor>" manifiesto "<carpeta>"`. Certifica cómo están los archivos **hoy**: desde ahí, verificar avisa
si algo cambia.

## 4. Manifiestos con xxHash (OffShoot y Hedge lo usan por defecto)

Python no trae xxHash: esas huellas salen como «no se pudo comprobar». Con el OK de la persona, instalarlo una vez
en un entorno propio y verificar con ese Python:
- Mac: `python3 -m venv ~/MI-SISTEMA-CLAUDE/respaldo-material/venv` y
  `~/MI-SISTEMA-CLAUDE/respaldo-material/venv/bin/pip install xxhash`; después
  `~/MI-SISTEMA-CLAUDE/respaldo-material/venv/bin/python "<motor>" verificar …`.
- Windows: `py -m venv %USERPROFILE%\MI-SISTEMA-CLAUDE\respaldo-material\venv`, luego `…\venv\Scripts\pip install xxhash`
  y `…\venv\Scripts\python "<motor>" verificar …`.

## 5. Informe

`python3 "<motor>" informe "<carpeta de la tarjeta>"` rehace el informe (HTML para ver o imprimir a PDF, y CSV):
clips, duración, códec, resolución, fps, audio y huellas. Duración y códec salen si hay ffprobe (viene con ffmpeg).

## Cada cuánto

Discos rígidos guardados: una verificación cada pocos meses y siempre antes de borrar la última copia de algo.
Material que se entrega a un cliente: verificar antes de entregar y pasar el informe.
