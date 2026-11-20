---
name: transcribir
description: Transcribe audio o video (entrevistas, podcasts, audios de WhatsApp, rodajes) en la propia computadora, sin subir nada a internet, y deja un TXT con tiempos y un SRT de subtítulos al lado del archivo. Sirve para buscar frases, elegir momentos para reels, armar subtítulos para Premiere, DaVinci o CapCut. Usar cuando la persona diga "transcribe este video", "pásame a texto este audio", "hazme los subtítulos", "sácame el SRT", o arrastre un archivo de audio o video.
---

# Transcribir

Usa **faster-whisper** con el modelo **`large-v3`** (el más preciso, el mismo que se usa para captions de trabajos reales), en la propia
computadora. La primera vez descarga el modelo (unos 3 GB, puede tardar varios minutos); después queda guardado
y no se vuelve a bajar.

## Preparar (solo la primera vez)
Crear un entorno propio para no tocar el Python del sistema:
- Mac: `python3 -m venv ~/.claude/venv-transcribir && ~/.claude/venv-transcribir/bin/pip install -q faster-whisper`
- Windows: `py -m venv %USERPROFILE%\.claude\venv-transcribir` y luego
  `%USERPROFILE%\.claude\venv-transcribir\Scripts\pip install -q faster-whisper`

## Correr
```
<python del venv> "${CLAUDE_SKILL_DIR}/scripts/transcribir.py" "<archivo>" [--idioma es] [--modelo small|medium|large-v3] [--max-caracteres 42]
```
- Por defecto: español, modelo `large-v3` (el más preciso: nombres, acentos, audio difícil). Tarda más o menos
  lo mismo que dura el audio. Solo si la persona pide un borrador rápido o la compu es muy lenta: `--modelo small`.
- Si el archivo dura más de 3 minutos, correrlo en segundo plano y avisar cuando termine.
- Deja `<archivo>.txt` (con tiempos) y `<archivo>.srt` al lado del original. Nunca toca el original.

## Después
- Revisar el TXT: nombres propios, marcas y términos del cliente suelen salir mal. Corregirlos en ambos
  archivos (preguntar con 🔔 los que no se puedan deducir del perfil o del brief).
- Si son subtítulos para redes: líneas cortas (máx. 42 caracteres), sin muletillas repetidas.
- Si pidió momentos para reels: proponer 3 a 5 fragmentos con tiempo de inicio y fin, la frase gancho y por qué.

## Si faltan frases o aparecen frases inventadas
El filtro de voz (VAD) a veces se come habla real (una pregunta del público, una frase dicha bajito) y, sin el
filtro, Whisper inventa párrafos enteros en los tramos difíciles. Ninguno de los dos avisa. Si en el TXT falta algo
que se oye, o aparece algo que nadie dijo: volver a transcribir **solo ese tramo** (recortado con ffmpeg) sin el
filtro, y aceptar lo nuevo solo si es creíble (sin letras raras, sin palabras repetidas en bucle, no más de unas 4
palabras por segundo). Nunca reemplazar la transcripción entera por la de sin filtro.
