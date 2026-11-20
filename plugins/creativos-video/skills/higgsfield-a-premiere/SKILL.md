---
name: higgsfield-a-premiere
description: Tomas generadas con Higgsfield (imagen con Nano Banana Pro → video con Kling 3.0) para una edición en Premiere Pro, medidas por capas de ajuste. Quien edita marca en la timeline cada hueco con una capa de ajuste; Claude mide las capas (duración exacta, qué se dice en ese tramo, formato de la secuencia), propone cada toma con su costo, la genera con aprobación entre medio y, cuando se aprueba, la pone en la timeline en lugar de su capa, con la duración exacta y escala 101 %. Usar cuando se pida "hagamos las tomas de Higgsfield para las capas de ajuste", "llena los huecos con Higgsfield", "mide las capas de ajuste", "genera lo que va en las capas", "pon la toma en su capa", "ya aprobé la toma 3, ponla", o cualquier pedido de animaciones o escenas generadas con IA para un video que se edita en Premiere. También si se genera en la web de Higgsfield y Claude solo escribe los prompts y después pone los archivos en la timeline.
---

# Higgsfield → Premiere, medido por capas de ajuste

Orquestador: el orden de los pasos y quién aprueba. Cómo generar imágenes y videos está en
`higgsfield-imagen-video` (cargarla siempre). Proceso probado en decenas de tomas desde el 2026-09-28.

**La idea:** quien edita arma el corte en Premiere y, donde va una toma generada, pone una **capa de ajuste**
del largo exacto del hueco. Esa capa es la medida: dice cuánto tiene que durar la toma, dónde va y qué se dice
mientras está en pantalla. Cuando una toma se aprueba, reemplaza a su capa. Nada se acomoda a mano.

## Antes de nada (una sola vez)

1. **Premiere abierto con el proyecto**, y el panel **MCP Bridge** conectado (Window > Extensions > MCP Bridge).
   Es un panel de código abierto (`github.com/hetpatel-11/Adobe_Premiere_Pro_MCP`) que deja que Claude le mande
   órdenes a Premiere. Si `ls /tmp/premiere-mcp-bridge` falla, falta instalarlo o abrirlo: guiar la instalación
   con el README de ese repo. El submenú Extensions está vacío hasta que hay un proyecto abierto.
2. **Higgsfield por la terminal**, con la cuenta de la persona: ver "Cuenta" en `higgsfield-imagen-video`.
3. **Carpeta del proyecto** con `EXTRA/` (ahí van las tomas aprobadas). Si no existe, crearla.
4. Si el cliente tiene una skill de marca (`<cliente>-brand`: look, imágenes aprobadas, decisiones), cargarla.
   Si no tiene y va a haber más videos de ese cliente, ofrecer armarla con `crear-skill` al terminar.

Scripts: `python3 scripts/<script>.py` desde la carpeta de esta skill (en Mac, si `python3` pide instalar
herramientas de Xcode, usar `/opt/homebrew/bin/python3`).

## Pasos y dónde aprueba quien edita

| # | Paso | Cómo | Aprueba |
|---|---|---|---|
| 1 | **Marcar los huecos** | Quien edita: una capa de ajuste por toma (File > New > Adjustment Layer, arrastrarla a V2 o la pista que use) con el largo exacto del hueco. Puede renombrarla con la idea ("manos que tiemblan") | — |
| 2 | **Medir** | `listar_capas.py [--srt transcripcion.srt] [--json capas.json]` | — |
| 3 | **Proponer** cada toma | Ficha de dirección por capa (opción segura + de autor), duración a pedir, formato y costo | **Sí**, antes de generar nada |
| 4 | **Imágenes** | `higgsfield-imagen-video` paso 3: una imagen por opción, revisión de cerca | **Sí**: elige con la hoja de contacto |
| 5 | **Videos** | `higgsfield-imagen-video` paso 4: prompt de movimiento, Kling, `qc_clip.py`, tira | **Sí**: el prompt (salvo que haya dicho "lanza") y el video |
| 6 | **A la timeline** | Copiar a `EXTRA/`, `poner_en_capa.py` | Solo lo aprobado entra |
| 7 | **Registro** | `mdfilesummary`: una fila por toma | — |

**Cada toma avanza por su cuenta.** Si la imagen de la toma 1 está aprobada y la persona todavía mira la 4, el
video de la 1 se lanza ya. Mientras Higgsfield genera, se pone en la timeline lo que ya se aprobó.

### 2. Medir

`listar_capas.py` lee la secuencia activa y da, por capa: pista, inicio, fin, duración exacta, **duración a
pedir** y nombre; con `--srt` agrega lo que se dice en ese tramo (sirve el SRT de la secuencia, por ejemplo el
de `transcribir` o de los captions). También da el tamaño de la secuencia y el formato a pedir (9:16, 16:9, 1:1)
y el costo aproximado de los videos.

- **Duración a pedir = el segundo entero siguiente, nunca justo** (2,4 s → 3 s; 3,0 s → 4 s): sobra un poco y
  se elige el mejor tramo. Kling no acepta menos de 3 s, así que un hueco de 1 s igual sale de 3: decirlo en
  la propuesta.
- Medir el hueco en la timeline, no en la frase.
- Si no hay capas, no adivinar los huecos: pedirle a quien edita que las ponga, o que diga dónde va cada toma.

### 3. Proponer

Por capa, en español y simple: qué cuenta la toma, qué se ve, desde dónde mira la cámara, la luz, el detalle,
el movimiento, la duración y el costo (2 créditos por imagen, 1,5 por segundo de Kling 3.0 pro). La ficha de
dirección y los 12 recursos están en `higgsfield-imagen-video/references/direccion-de-fotografia.md`.
"Dos opciones" son dos imágenes en total. Se genera solo lo aprobado: nada de variantes "por las dudas".

### 6. A la timeline

1. Copiar la toma aprobada a `EXTRA/` con un nombre claro, en mayúsculas y sin tildes (`MANOS TEMBLOR.mp4`).
   Verificar con `ffprobe` que se copió entera. Las versiones descartadas no se dejan en `EXTRA/`.
2. Volver a medir **justo antes**: la timeline se mueve mientras se trabaja; nunca confiar en un tiempo viejo.
3. `python3 scripts/poner_en_capa.py "<ruta en EXTRA>" <inicio de la capa> --prueba` → dice qué capa encontró.
4. Sin `--prueba`, hace todo de una:
   - importa la toma al bin EXTRA si no está en el proyecto;
   - borra la capa y pone la toma **en la misma pista y tramo**, con **la duración exacta de la capa**;
   - corrige el cuadro de menos (Kling sale a 24 fps y la secuencia suele ir a 23,976);
   - Motion > Scale en **101 %** (al 100 % se ve un borde de lo que está detrás: Kling sale 1076×1928);
   - verifica que el clip siguiente no se movió y guarda el proyecto.
   Si el arranque de la toma no sirve, `--desde <segundo>` usa la toma desde ahí.
5. Leer la salida: tiene que decir `exacto=true` y `siguiente_igual=true`. Una línea con `ERROR` se resuelve
   antes de seguir (Cmd+Z en Premiere deshace el último cambio).

Reglas de quien edita: la toma **reemplaza** a la capa, nunca va encima en otra pista; lo que no se aprobó no entra;
una toma aprobada sin capa no se adivina: se pregunta dónde va; al terminar, el proyecto queda guardado.

## Si se genera en la web de Higgsfield

Hay quien prefiere generar a mano en la web (para aprender el oficio, o porque el plan tiene generaciones
ilimitadas solo en la web). Entonces Claude **no lanza nada**: mide las capas (paso 2) y entrega, por capa, el
prompt de imagen y el de movimiento en inglés, el modelo, la duración, el formato y **el nombre con el que
guardar el archivo**, en una página o documento con botones de copiar. La persona genera, guarda en `EXTRA/` y
Claude sigue en el paso 6.

## Qué se aprende y dónde se escribe

| Aprendizaje | Va en |
|---|---|
| Gusto o decisión de quien edita para un cliente | `<cliente>-brand` (o la memoria si es general) |
| Cómo se porta Kling o Nano Banana (y qué frase lo arregló) | tabla de `higgsfield-imagen-video` |
| Un encuadre o recurso que funcionó o falló | `higgsfield-imagen-video/references/direccion-de-fotografia.md` |
| Algo de Premiere (una pista, un efecto, un tiempo) | esta skill |

## Archivos

- `scripts/listar_capas.py`: mide las capas de ajuste de la secuencia activa. No cambia nada.
- `scripts/poner_en_capa.py`: pone una toma aprobada en lugar de su capa. `--prueba` no cambia nada.
- `scripts/puente.py`: cómo se habla con Premiere (lo usan los otros dos).
