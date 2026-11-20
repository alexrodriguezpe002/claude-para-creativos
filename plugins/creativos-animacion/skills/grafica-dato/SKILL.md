---
name: grafica-dato
description: Gráfica animada en HyperFrames que ilustra un dato que dice alguien en cámara (un porcentaje, una proporción, "en nuestro país", "3 de cada 4"), con la marca del cliente y sincronizada palabra por palabra con el audio. Es mayormente gráfica en movimiento (mapa del país que se dibuja y se llena de puntos-persona, dona o pastel que se llena con contador) y el texto mínimo, solo las palabras clave. Incluye contornos de países de Natural Earth, un generador por configuración y la extracción de tiempos de palabras del audio del corte. Usar cuando se pida "grafícame lo que dice el invitado", "una gráfica del 75%", "hacé una gráfica en hyperframes de este dato", "que se vea el mapa del país", o cualquier cifra o estadística de un video que se quiera mostrar. Los colores y la tipografía salen de la skill de datos del cliente (ej. `<cliente>-brand`).
---

# Gráfica de un dato

Validado el 2026-09-28 en un video real. `assets/ejemplo-75.json` tiene los tiempos, tamaños y movimiento que
funcionaron, con una frase y unos colores de ejemplo, inventados: «Actualmente, en nuestro país, el 75 por ciento de las personas tiene
celular», sobre el mapa de Ecuador. Sirve de punto de partida y para probar el generador.

HyperFrames se pasa siempre por la skill `hyperframes` (ruta `motion-graphics`, categoría stat/map).
Con el diseño decidido acá se construye directo. Se trabaja en el **disco interno**; HyperFrames
falla en exFAT.

## Lo que pidió el editor para estas gráficas

Que lo que más resalte sean gráficas y animaciones en movimiento: si la persona habla de su país, un
mapa; si dice "setenta y cinco por ciento", un gráfico de barras o de pastel. Texto sí, pero mínimo:
solo para resaltar las palabras más importantes.

Lo primero que se le propuso (un número grande con figuras de personas y dos frases) tenía demasiado
texto. Quedaron tres palabras en pantalla: el país, el valor y la palabra clave.

## Paso a paso

1. **La frase y sus tiempos.** El editor suele mandar una captura de la timeline con la sección marcada:
   inicio, largo en el monitor de programa (ej. 6:15 a 23,976 = 6,6 s) y los fps de la secuencia.
   Después:
   `python3 scripts/words.py "<proyecto>/AUDIO PARA IA/<corte>.wav" <desde> <largo> --desde-seccion <inicio>`
   da cada palabra en segundos relativos al inicio de la sección.
2. **Guion visual pegado a las palabras.** Una cosa nueva por grupo de palabras, en el momento en que
   se dicen. En el ejemplo del 75%:
   - "Actualmente": se dibuja el contorno.
   - "en nuestro país": el nombre y los puntos.
   - "el 75 por ciento": sube el mapa, se llena la dona, rueda el contador y el 75% de los puntos se
     pone naranja en la misma ola.
   - "de las personas": laten los puntos.
   - "tiene celular": las palabras con una línea debajo.
   Dejar ~0,5 s de sobra al final para que el editor corte.
3. **Mapa del país:** `python3 scripts/geo_pais.py <País en inglés> geo.json` (Natural Earth 50m,
   incluido). Para Ecuador como en el ejemplo: `--acercar -85,8.4 --lat0 -1.8`, que acerca las
   Galápagos (da `assets/geo-ecuador.json`). Revisar la vista previa PNG.
4. **Composición:** copiar `assets/ejemplo-75.json` como `config.json`, cambiar país, valor, palabras
   y tiempos. Después `python3 scripts/build_mapa_dona.py config.json index.html`. Fuente de la marca
   en `assets/fonts/` del proyecto.
5. **Validar:** `npx hyperframes lint .`, `npx hyperframes check .` y
   `npx hyperframes snapshot --at <un momento por cada paso del guion>`. Mirar cada captura: que
   ningún texto tape el mapa y que el valor final sea el correcto.
6. **Render a los fps de la secuencia:** `npx hyperframes render . --fps 24000/1001 -q delivery -o renders/<nombre>.mp4`
   (la secuencia de la gráfica validada iba a 23,976; en cada cliente, preguntar o mirar Sequence Settings,
   nunca deducirlos del XML).
7. **Gate:** `media-quality-gates/scripts/qc_render.py <mp4> --fps 24000/1001 --res 1080x1920 --min-dur <largo de la sección>`.

## Decisiones que funcionaron

- **Texto en el color oscuro, gráfica en el de acento** (en el ejemplo, azul y naranja): un acento claro sobre fondo
  claro no pasa el contraste.
  El check de HyperFrames lo marca como error de contraste.
- **Contador seek-safe:** tiras de dígitos que ruedan con `y`. Un contador por `onUpdate` sale
  congelado en el render. Las tiras quedan fuera de cuadro a propósito:
  `data-layout-allow-overflow="true"`.
- **Dona con `stroke-dashoffset`** sobre un círculo rotado −90°. El anillo de "impacto" escala con
  `svgOrigin`, no con `transformOrigin`, porque en SVG este se mide contra la caja del elemento.
- **Puntos-persona:** 52 dentro del territorio, repartidos por muestreo tipo Poisson. Los que no se
  pintan salen al azar con semilla fija, para que se vean repartidos y el render sea determinista.
- **El plano nunca queda quieto:** micro-cámara (escala 1→1,035), dos luces que se desplazan y un
  brillo que respira detrás de la dona. Es una elección de diseño de esta gráfica, no una regla de la marca.
- **Sin logo del cliente** en una gráfica de datos del país. Preguntar si se quiere agregar.
- **El contorno se baja una vez y queda en el HTML.** El bloque `world-map` del registro usa 110m, que
  a este tamaño se ve poligonal, y además lo baja de internet en cada render.

## Si el dato pide otra forma

El generador cubre mapa + dona + palabras. Para barras, "3 de cada 4" con figuras, una línea de
tiempo o dos países, partir del mismo `index.html` (marca, fondo, cámara y contador ya resueltos) y
cambiar la pieza central. El registro de HyperFrames tiene bloques de gráficos
(`npx hyperframes catalog --query "<qué>"`), pero traen su propia estética: adaptarlos a la marca.

## Archivos

- `scripts/words.py` — tiempos de cada palabra en un tramo del audio (faster-whisper medium).
- `scripts/geo_pais.py` — contorno + puntos de cualquier país → `geo.json` + vista previa.
- `scripts/build_mapa_dona.py` — genera la composición desde `config.json`.
- `assets/countries-50m.json` — Natural Earth 50m (world-atlas@2), dominio público.
- `assets/geo-ecuador.json` — Ecuador ya proyectado, con las Galápagos acercadas (el del ejemplo).
- `assets/ejemplo-75.json` — la configuración de la gráfica del 75%, con frase y colores de ejemplo.

## Rótulos
Ningún texto cae adentro del área donde se dibuja el gráfico: los rótulos van arriba del gráfico o debajo del eje,
con su alto completo despejado. Si dos series terminan en el mismo punto, distinguirlas con terminadores distintos
(círculo abierto y lleno). Verificarlo en un cuadro a tamaño real.
