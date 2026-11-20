---
name: video-a-premiere
description: Baja UN video de un link (YouTube, Vimeo, Instagram, TikTok, Dropbox, Google Drive, link directo o un archivo de la computadora), arma la carpeta del proyecto y abre Premiere Pro con una secuencia del mismo formato que el video y el video ya puesto en la línea de tiempo. Usar cuando la persona diga "baja este video y ármame el proyecto", "hazme el proyecto de Premiere con este link", "quiero editar este video", "descarga este material y ponlo en Premiere", "nuevo proyecto con este video", o pegue un link de video pidiendo editarlo. Para varios archivos de un rodaje, bajar de a uno.
---

# Video a Premiere

Un link → carpeta del proyecto → video en `MEDIA/` → Premiere abierto con la secuencia armada.

## Preparar (solo la primera vez; Claude lo hace solo)
Revisar qué falta y, si falta algo, contarle en una línea qué se va a instalar antes de hacerlo.
- **Entorno de Python** (para medir el video, ffmpeg incluido, y bajar de Drive):
  - Mac: `python3 -m venv ~/.claude/venv-video && ~/.claude/venv-video/bin/pip install -q numpy pillow imageio-ffmpeg gdown`
  - Windows: `py -m venv %USERPROFILE%\.claude\venv-video` y `%USERPROFILE%\.claude\venv-video\Scripts\pip install -q numpy pillow imageio-ffmpeg gdown` (la misma línea en las skills de video)
- **yt-dlp actualizado + deno** (YouTube los necesita a los dos; **no** usar el yt-dlp de pip: con el Python de la
  Mac queda una versión vieja que YouTube rechaza con "The page needs to be reloaded"):
  - Mac con Homebrew: `brew install yt-dlp deno`
  - Mac sin Homebrew: `mkdir -p ~/.claude/bin && curl -L -o ~/.claude/bin/yt-dlp https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos && chmod +x ~/.claude/bin/yt-dlp`
    y `curl -fsSL https://deno.land/install.sh | sh -s -- -y`
  - Windows: `winget install yt-dlp.yt-dlp DenoLand.Deno`
- Si YouTube falla más adelante, lo primero es actualizar: `~/.claude/bin/yt-dlp -U` o `brew upgrade yt-dlp`.

## Pasos
1. **Datos.** Si no los dio, preguntar con la herramienta de preguntas (opciones + escribir la suya): el link,
   el cliente y el nombre del proyecto (sugerir uno con la fecha, `MM-DD NOMBRE`). Si es un video largo de
   YouTube y solo quiere un tramo, preguntar desde y hasta qué minuto.
2. **Carpeta.** `~/PROYECTOS/<CLIENTE>/<MM-DD NOMBRE>/` con `MEDIA/` y `PREMIERE/`. Si ya existe, usarla sin
   pisar nada.
3. **Bajar** (si tarda más de un minuto, en segundo plano):
   ```
   <python del venv> "${CLAUDE_SKILL_DIR}/scripts/bajar_video.py" "<link>" "<carpeta>/MEDIA" --nombre "<nombre corto>" [--desde 1:20 --hasta 1:45]
   ```
   La última línea dice `ARCHIVO=<ruta>`. Un archivo de la computadora se **copia** a MEDIA; el original no se toca.
   WeTransfer no deja bajar por código: pedirle que lo baje del navegador y pase la ruta.
4. **Armar y abrir Premiere.** Antes, pedirle que **cierre Premiere** si lo tiene abierto con otro proyecto.
   ```
   <python del venv> "${CLAUDE_SKILL_DIR}/scripts/armar_premiere.py" "<ARCHIVO>" "<carpeta>/PREMIERE" --nombre "<MM-DD NOMBRE>"
   ```
   Escribe `<MM-DD NOMBRE>.xml` (una secuencia del tamaño y los cuadros por segundo del video, con el video
   entero en V1 y el audio en A1/A2) y lo abre con Premiere.
5. **Cerrar.** Decirle: "Guárdalo con Cmd+S (Ctrl+S en Windows) dentro de la carpeta PREMIERE". Contarle el formato
   de la secuencia (por ejemplo 1080×1920 vertical, 30 fps) y anotar el proyecto en su `MD FILES/` (`mdfilesummary`).

## Lo que está probado y lo que no
- **Probado** (13-11-2026, Premiere 26.3): YouTube con tramo, el XML crea la secuencia del formato correcto con el
  video en V1 y el audio en A1 y A2 (un canal por pista). Con una sola pista estéreo, Premiere pierde el audio:
  no cambiarlo.
- **Sin probar:** qué hace Premiere si al abrir el XML ya tiene otro proyecto abierto (por eso se cierra antes),
  links de Drive y de Dropbox, y Windows.

## Derechos
Un video de YouTube o de redes es de quien lo subió. Sirve como referencia o para un corte interno; para
publicarlo hace falta permiso o que sea material libre. Si va a ir en una pieza para un cliente, recordárselo en
una línea.

## Nombres
Si el proyecto ya existe y tiene un patrón de nombres (secuencias, bins, precomps), lo nuevo sigue ese patrón:
después de `BEFORE AI 1` va `BEFORE AI 2`, no un código inventado. Solo si no hay patrón, proponer uno.
