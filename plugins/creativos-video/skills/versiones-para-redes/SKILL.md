---
name: versiones-para-redes
description: "Saca de un render maestro las versiones para cada red social: vertical 9:16 (Reels, TikTok, Shorts), cuadrada 1:1, 4:5 (feed de Instagram) y 16:9 (YouTube), cada una con fondo desenfocado o con recorte, y una versión liviana para mandar por WhatsApp. Si se pide, les quema subtítulos desde un SRT y les pone el logo. Deja una hoja con un cuadro de cada versión para revisarlas de un vistazo. Nunca toca el maestro. Mac y Windows; funciona desde el celular. Usar cuando la persona diga «sácame las versiones para redes», «hazme el vertical», «pásalo a 9:16», «la versión cuadrada», «el 4:5 para Instagram», «una versión liviana para WhatsApp», «adaptaciones», «ponle subtítulos quemados», «ponle el logo», o termine un render y pida adaptarlo."
---

# Versiones para redes

Motor: `${CLAUDE_SKILL_DIR}/scripts/versiones.py` (siempre entre comillas). Toma **un** video terminado (el maestro)
y saca las versiones con ffmpeg. No reemplaza la edición: un 9:16 pensado desde el rodaje siempre queda mejor; esto
es para adaptar rápido lo que ya está aprobado.

## Preparar (solo la primera vez; Claude lo hace solo)
Usa el entorno propio `venv-video` (el mismo de `video-a-premiere` y `sincronizar-audio`). **Pillow** hace falta para
los subtítulos y la hoja de revisión; **imageio-ffmpeg**, solo si la computadora no tiene ffmpeg. Avisar en una línea
qué se instala:
- Mac: `python3 -m venv ~/.claude/venv-video && ~/.claude/venv-video/bin/pip install -q numpy pillow imageio-ffmpeg gdown`
- Windows: `py -3 -m venv %USERPROFILE%\.claude\venv-video` y
  `%USERPROFILE%\.claude\venv-video\Scripts\pip install -q numpy pillow imageio-ffmpeg gdown`
  (la misma línea que `sincronizar-audio` y `video-a-premiere`: con una vez alcanza para todas)

Abajo, `<py>` es el Python del entorno. Prueba en una computadora nueva (unos 15 s): `<py> "<motor>" autoprueba`.

## Pasos
1. **Datos** (con la herramienta de preguntas, opciones + escribir la suya; lo que ya dijo no se pregunta):
   - El **maestro** (si no lo pasó: el render más nuevo de la carpeta del proyecto, y confirmar cuál es).
   - **Formatos** (selección múltiple): 9:16, 1:1, 4:5 y 16:9 (Recomendado: todos), y la versión de WhatsApp (sí).
   - **Cómo llenar el formato** cuando cambia la forma del cuadro:
     - **Fondo desenfocado** (Recomendado): se ve el cuadro entero, con el mismo video desenfocado detrás. No se
       pierde nada.
     - **Recorte**: llena la pantalla, pero se pierde lo de los costados (o de arriba y abajo). Si lo importante no
       está al centro, preguntar dónde está: `--foco 0.2` (izquierda) … `0.8` (derecha), `--foco-v` de arriba a abajo.
   - **Subtítulos quemados**: solo si los pide o si hay un `.srt` al lado del maestro (ofrecerlo). Sin SRT: primero
     `transcribir` y revisarlo (`subtitle-audit`). `--caja` los pone sobre una caja negra (se leen en cualquier fondo).
   - **Logo**: solo si lo pide (`--logo logo.png`, `--logo-pos arriba-derecha|arriba-izquierda|abajo-derecha|abajo-izquierda`).
2. **Correr** (si el maestro dura más de 3 minutos, en segundo plano y avisar al terminar):
   ```
   <py> "<motor>" "<maestro>" [--formatos 9x16,1x1,4x5,16x9] [--modo fondo|recorte] [--foco 0.5] [--srt "<archivo.srt>"] [--caja] [--logo "<logo.png>"] [--sin-whatsapp]
   ```
   Por defecto deja todo en `<maestro>_VERSIONES/`, al lado del maestro (`--salida` para otra carpeta).
3. **Revisar antes de entregar**: abrir `revision.jpg` (un cuadro de cada versión, uno al lado del otro) y mirarlo.
   Si el recorte cortó una cara o un texto, repetir con otro `--foco` o con `--modo fondo`. Si un subtítulo tapa algo
   importante, decirlo.
4. **Contarle** qué salió (formato, tamaño, peso) y dónde, y mostrarle la hoja de revisión. Desde el celular, mandarle
   la hoja como imagen.

## Qué sale
| Archivo | Para qué | Tamaño |
|---|---|---|
| `<maestro>_9x16_reels-tiktok-shorts.mp4` | Reels, TikTok, Shorts, historias | 1080×1920 |
| `<maestro>_1x1_feed.mp4` | Feed cuadrado | 1080×1080 |
| `<maestro>_4x5_feed-instagram.mp4` | Feed de Instagram (ocupa más pantalla que el cuadrado) | 1080×1350 |
| `<maestro>_16x9_youtube.mp4` | YouTube, web, presentaciones | 1920×1080 |
| `<maestro>_whatsapp.mp4` | Mandar al cliente un avance para que lo vea en el celular | 720 de lado corto, hasta 16 MB |
| `revision.jpg` · `informe_versiones.html` | Revisar todo de un vistazo | — |

Calidad: H.264 con calidad alta (CRF 18) y audio AAC de 192 kb/s, lista para subir; la de WhatsApp baja la calidad
hasta entrar en el tope (`--whatsapp-mb 16`, se puede cambiar). Los subtítulos en vertical quedan arriba de la zona
de los botones de las apps.

## Si algo sale mal
| Qué dice | Qué hacer |
|---|---|
| «El maestro es HDR» | Pasa con videos de iPhone o renders en HDR: las versiones saldrían lavadas. Exportar el maestro en SDR (Rec. 709) y repetir. |
| «demasiado largo para 16 MB» | El video dura mucho para WhatsApp a buena calidad: mandarlo como documento, o subir el tope (`--whatsapp-mb 64`). |
| Código 4 «falta Pillow» | Correrlo con `<py>` (ver Preparar). |
| El recorte corta a alguien | Repetir con `--foco` hacia donde está la persona, o con `--modo fondo`. |

## Reglas
- Nunca toca el maestro ni pisa archivos: si una versión ya existe, la nueva lleva `_2`. Solo borra sus propios
  temporales (y una versión que quedó a medias por un error).
- Son adaptaciones automáticas: antes de publicar, la persona mira la hoja de revisión (y el video, si hay subtítulos).
- Lo de cada marca (tipografía de los subtítulos, logo, posición) se guarda en su perfil o en su `MD FILES/` y se usa
  la próxima vez sin preguntar (`--fuente "<archivo.ttf>"` para su tipografía).

## Probado y sin probar
- **Probado (jue 19-11-2026, Mac):** `autoprueba` con el Python de la Mac y con el entorno propio sin Homebrew ni
  ffprobe. Un maestro 16:9 → las 4 versiones y la de WhatsApp, con subtítulos y logo: tamaños exactos, misma
  duración, con audio. El subtítulo aparece solo en su tiempo (medido en los píxeles del cuadro) y cada versión se
  revisó como imagen. Además, un maestro vertical sin audio pasado a 16:9 con recorte, y el 9:16 con caja y foco a
  la izquierda.
- **Sin probar:** Windows (las fuentes de Windows están previstas: Arial Bold o Segoe UI Bold), maestros reales
  largos (más de 10 minutos), cuadros de 60 fps o más, y cómo lo comprimen de nuevo Instagram y TikTok.
