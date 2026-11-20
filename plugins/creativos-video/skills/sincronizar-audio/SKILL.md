---
name: sincronizar-audio
description: "Sincroniza el audio de una grabadora (Zoom, Tascam, Rode, Sound Devices…) o de otra cámara con los clips de video por la forma de onda, sin timecode ni claqueta: dice dónde cae cada clip en la grabación y con qué confianza, y deja un proyecto XML que abren Premiere y DaVinci (una carpeta por día, por cámara y de audio, y la secuencia del día en orden de grabación, con cada clip y su audio bueno alineado debajo y los clips a revisar marcados), más (si se pide) copias de cada clip con el audio ya pegado, sin recomprimir el video. Hace todo el día de rodaje de una vez, sin abrir el programa de edición, y sirve desde el celular. Nunca toca los originales. Mac y Windows. Usar cuando la persona diga «sincroniza el audio», «pega el audio de la grabadora», «junta el audio del Zoom con los clips», «sincroniza el material de hoy», «sincroniza las cámaras», «el audio va aparte», «doble sistema», «como PluralEyes», o pase una carpeta de clips y otra de audios."
---

# Sincronizar audio

Motor: `${CLAUDE_SKILL_DIR}/scripts/sincronizar.py` (siempre entre comillas). Busca el audio de cada clip dentro de
las grabaciones (correlación de la forma de onda, la misma idea que PluralEyes o la sincronización por audio de
Premiere y DaVinci) y lo confirma con dos tramos más del clip. Precisión medida: menos de 1 cuadro (en las pruebas,
entre 0 y 22 ms; un cuadro a 24 fps son 42 ms).

En una línea, para la persona: «Comparo el sonido de cada clip con el de la grabadora y busco dónde coincide; la
cámara y la grabadora no tienen que haber arrancado juntas».

## Preparar (solo la primera vez; Claude lo hace solo)
Necesita **numpy** y **ffmpeg**. Usa el mismo entorno propio que `video-a-premiere` (`venv-video`). Avisar en una línea
qué se instala antes de hacerlo:
- Mac: `python3 -m venv ~/.claude/venv-video && ~/.claude/venv-video/bin/pip install -q numpy pillow imageio-ffmpeg gdown`
- Windows: `py -3 -m venv %USERPROFILE%\.claude\venv-video` y
  `%USERPROFILE%\.claude\venv-video\Scripts\pip install -q numpy pillow imageio-ffmpeg gdown`

Es la misma línea en `video-a-premiere`, `versiones-para-redes` y el asistente de edición: con una vez alcanza para todas. Si ya existe el entorno, correr igual el `pip install -q numpy pillow imageio-ffmpeg gdown` (salta lo que ya está). Si la computadora tiene
ffmpeg instalado, usa ese; si no, el que trae `imageio-ffmpeg`. Abajo, `<py>` es el Python del entorno
(`~/.claude/venv-video/bin/python` o `%USERPROFILE%\.claude\venv-video\Scripts\python`).

En una computadora nueva, correr primero la prueba (unos 10 s, con material inventado en una carpeta temporal):
`<py> "<motor>" autoprueba` → tiene que terminar en `✅ Autoprueba OK`.

## Pasos
1. **Datos** (lo que no haya dicho, con la herramienta de preguntas: opciones + escribir la suya):
   - Dónde están los **clips** de cámara (carpetas o archivos; puede ser la copia de `descargar-tarjeta`).
   - Dónde están las **grabaciones** (la carpeta de la grabadora, o los clips de la otra cámara). Si no grabó audio
     aparte, sin `--audio`: arma igual el proyecto ordenado, con el audio de la cámara.
   - Puede ser la misma carpeta para las dos cosas (la copia entera del rodaje): de ahí toma los videos como clips y
     los audios sueltos como grabaciones.
   - Dónde dejar el resultado: proponer `<PROYECTO>/SINCRO/`, **fuera** de las carpetas de las tarjetas (así no se
     mezcla con el respaldo verificado).
   - Si quiere además **los clips con el audio ya pegado** (`--copias`): sí para Final Cut, para mandar material
     al director o al cliente, o si edita en un programa que no lee XML.
2. **Correr** (con muchos clips o grabaciones largas, en segundo plano y avisar al terminar; una hora de grabación con
   decenas de clips tarda unos minutos):
   ```
   <py> "<motor>" analizar --clips "<carpeta de clips>" --audio "<carpeta de audios>" --salida "<PROYECTO>/SINCRO" [--nombre "SINCRO BODA"] [--copias]
   ```
   Varias carpetas: repetir la ruta después de `--clips` o `--audio`. Cada clip sale con una línea: ✅ alta,
   🟡 media, ❌ sin coincidencia, 🔇 sin audio, 🎬 sin grabadora. `--cache "<archivo.json>"` guarda el análisis:
   la próxima vez solo analiza lo nuevo (lo usa `asistente-de-edicion`, que hace todo esto solo cuando termina la
   copia de cada tarjeta).
3. **Contarle en 3 líneas**: cuántos quedaron sincronizados; los 🟡 para escuchar antes de usar; los ❌ y por qué
   (ver «Si algo sale mal»). El detalle está en `informe_sincronizacion.html` (abrirlo con `open` o `start`).
4. **Abrir la secuencia**:
   - **Premiere:** Archivo › Importar › el `.xml` → aparece una carpeta con: la **secuencia del día** (los clips uno
     detrás de otro en orden de grabación, las cámaras mezcladas por hora; el audio bueno, alineado debajo; el de la
     cámara, en sus pistas pero apagado, para compararlo), una carpeta por **cámara** (el modelo, si el clip lo dice;
     si no, la carpeta de la tarjeta) y una de **audio**. Con varios días, una carpeta por día. Los 🟡 llevan
     marcador «REVISAR SINCRO» y color amarillo; los ❌, «SIN SINCRO», color rosa y su audio de cámara; el B-roll sin
     audio, «SIN AUDIO» adelante del nombre.
   - Si ese XML no abre bien: `--xml-simple` deja una secuencia suelta por día y formato (sin carpetas, marcadores
     ni colores: la forma más simple).
   - **DaVinci Resolve:** Archivo › Importar › Línea de tiempo (*Import Timeline*) › el `.xml`.
   - **Final Cut Pro:** no lee este XML. Usar las copias de `CLIPS_CON_AUDIO/` (importarlas como cualquier clip) o
     su propia función «Sincronizar clips».
5. Anotar en el `MD FILES/` del proyecto qué se sincronizó y dónde quedó (`mdfilesummary`).

## Qué sale en la carpeta de resultado
- `<nombre> - <día>.xml` — el proyecto (si un día tiene clips de distinto tamaño o cuadros por segundo, una
  secuencia por formato). Con `--xml-simple`, un XML por día y formato.
- `informe_sincronizacion.html` (para mirar), `.csv` (Excel) y `.json` (para Claude).
- `CLIPS_CON_AUDIO/<clip>_SYNC.mov` (con `--copias`) — el video idéntico al original (no se recomprime), el audio
  bueno como primera pista y el de la cámara como segunda (`--sin-audio-camara-en-copias` para no ponerlo), el mismo
  timecode. Las grabadoras de 32 bits flotante conservan sus 32 bits.

## Si algo sale mal
| Qué dice | Qué pasa | Qué hacer |
|---|---|---|
| 🔇 sin audio | El clip no tiene sonido (cámara sin micrófono) | Por forma de onda no se puede: sincronizar a mano con la claqueta o por timecode en el programa. |
| ❌ sin coincidencia | Ese clip no está en esas grabaciones, o se superpone menos de la mitad | Revisar que la carpeta de audio sea la del mismo día y bloque. Si la grabadora arrancó mucho después que la cámara, sincronizarlo a mano. |
| 🟡 media | Coincide, pero con menos certeza: clip muy corto, mucho ruido o viento, o solo un tramo lo confirma | Escuchar el clip en la secuencia antes de usarlo. |
| «también coincide con …» | Dos archivos tienen el mismo audio (pista de seguridad a −12 dB, mezcla y pistas sueltas) | Normal. Se usó el primero; el otro sirve de respaldo. |
| «el audio se corre X ms al final» | Toma larga y relojes distintos (la cámara y la grabadora no cuentan el tiempo igual) | La secuencia queda alineada al principio. Si molesta al final, cortar la toma o ajustar la velocidad del audio en el programa. |
| «ffmpeg no lee BRAW / R3D» | Formatos RAW que ffmpeg no abre | Usar los proxies con audio, o exportar el audio de la cámara a WAV y sincronizar ese. |
| Código 4 «falta numpy» | Se corrió con el Python del sistema | Correrlo con `<py>` (ver Preparar). |

## Reglas
- Solo lee los clips y las grabaciones: **nunca** los mueve, renombra ni cambia. Todo lo nuevo va a la carpeta de
  resultado; si un archivo ya existe, el nuevo lleva `_2`. Solo borra sus propios temporales.
- No sincronizar por encima de un proyecto abierto: la secuencia es nueva, se importa al proyecto que la persona quiera.
- Lo hace solo, sin preguntar más que los datos del paso 1. Desde el celular (Remote Control) funciona igual:
  «sincroniza el material de hoy» y al terminar le cuenta el resultado.
- Los programas de edición también sincronizan por audio, de a un clip o de a grupos y con el programa abierto. Esta
  skill hace el día entero de una vez, deja el informe y las copias, y puede correr mientras la persona sigue grabando.

## Probado y sin probar
- **Probado (jue 19-11-2026, Mac):** `autoprueba` con el Python de la Mac y con el entorno propio sin Homebrew ni
  ffprobe (solo el ffmpeg de pip): 3 de 3 clips en su lugar (error 0 ms), el clip ajeno y el B-roll bien marcados,
  el proyecto con una carpeta por día, la cámara Sony con su modelo (del XML que deja al lado de cada clip) y la otra
  con el nombre de su carpeta, la secuencia en orden de grabación (no de nombre), el marcador «SIN SINCRO», cada
  archivo definido una sola vez, la segunda pasada con `--cache` (nada se vuelve a analizar) y `--xml-simple`.
  Antes, la calibración con voz real: 12 clips de 3 s a 2 min con micrófono de cámara, eco de sala, ruido de 0 a
  25 dB, compresión, AAC o PCM, una grabación partida en dos archivos, un clip que cruza el corte, uno que empieza 6 s
  antes que la grabadora y uno con deriva de reloj: 12 de 12 bien ubicados (error máximo 22 ms) y 10 de 10 clips
  ajenos rechazados; tres tomas de la misma frase, cada clip a su toma; las copias, con el video idéntico byte a byte
  y el timecode conservado; una hora de grabación con 6 clips en 10 s.
- **Ajuste del jue 19-11 (tarde):** en un rodaje de prueba con voces de la Mac, una frase ajena dicha por la misma voz
  salió 🟡 con todo justo en el límite (z 12,2, segundo pico 0,74, un solo tramo que la confirma). Ahora, con un solo
  tramo que confirma, el pico principal tiene que ser claro en algo (z ≥ 20 o segundo pico ≤ 0,55). Repetida la
  calibración con voz real: los 22 clips dan lo mismo que antes; la frase ajena pasa a ❌.
- **Sin probar:** abrir el XML en Premiere y en DaVinci de verdad (lo lee OpenTimelineIO, un lector independiente),
  Windows, material real de cámara y grabadora (deriva real, tarjetas de varias horas), grabadoras polifónicas de más
  de 2 canales, y si la hora que graban algunas cámaras viene corrida (la del XML de Sony trae la zona horaria; la de
  los metadatos se toma como UTC).
