---
name: ordenar-material
description: Ordena y renombra el material de un rodaje o proyecto (videos, audios, fotos, gráficos, documentos) en subcarpetas por tipo, con la fecha adelante del nombre, sin borrar nunca nada y con la opción de deshacer. Primero muestra qué haría y espera el OK. Usar cuando la persona diga "ordena esta carpeta", "organiza el material del rodaje", "renombra los clips por fecha", "esto es un caos", o pase una carpeta llena de archivos sueltos.
---

# Ordenar material

Script: `${CLAUDE_SKILL_DIR}/scripts/ordenar.py` (solo Python, sin instalar nada; ponerlo entre comillas al usarlo).

1. **Simular** (no mueve nada): `python3 <script> "<carpeta>"` (Windows: `py`). Muestra el plan: cuántos
   archivos van a cada subcarpeta (`VIDEO/`, `AUDIO/`, `FOTOS/`, `GRAFICOS/`, `PROYECTOS/`, `DOCUMENTOS/`,
   `OTROS/`) y ejemplos de nombres nuevos (`2026-11-13_C0001.MP4`).
   - `--sin-fecha` si no quiere la fecha en el nombre.
   - `--por-dia` para separar además por día de grabación (útil en rodajes de varios días).
2. Mostrarle el resumen y preguntar (🔔) si se aplica.
3. **Aplicar**: el mismo comando con `--aplicar`. Deja `_ordenar-log.csv` en la carpeta.
4. **Deshacer** si algo no le gusta: `python3 <script> "<carpeta>" --deshacer`.

Si la carpeta ya tiene un patrón de nombres, lo nuevo lo sigue (no inventar otro).

**Copias verificadas y tarjetas: no se tocan.** Si la carpeta es (o está dentro de) una copia sellada —ASC MHL
(carpeta `ascmhl`), un `.mhl` adentro o al lado, las sumas de ShotPut (`*ChecksumFileSPP.*`), `_DESCARGA` de
`descargar-tarjeta`— o tiene la estructura de una tarjeta de cámara (`PRIVATE/M4ROOT`, `XDROOT`, `CONTENTS`, `DCIM`…),
el script frena con código 3 y lo explica: mover algo ahí rompe la verificación y la estructura que Premiere
necesita. Decírselo así y ofrecer el orden en Premiere: `sincronizar-audio` o `asistente-de-edicion` dejan un XML con
una carpeta por día, por cámara y de audio, sin tocar las copias.

Reglas: nunca borrar ni sobrescribir (si un nombre ya existe, se agrega `_2`); no tocar subcarpetas que ya
estén ordenadas ni archivos de proyectos abiertos (Premiere, DaVinci): avisar si hay un `.prproj` que apunta a
ese material, porque al mover los archivos Premiere los va a pedir de nuevo (hay que relinkear).
