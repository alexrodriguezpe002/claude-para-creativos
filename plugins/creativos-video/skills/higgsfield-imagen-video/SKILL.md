---
name: higgsfield-imagen-video
description: Proceso para hacer una toma animada con Higgsfield desde la terminal. Se genera la imagen base con Nano Banana Pro (una por opción, revisión de cerca, correcciones editando la imagen buena) y se anima con Kling 3.0 (prompt de movimiento, revisión cuadro por cuadro, reintentos), con aprobación de quien edita entre medio. Incluye scripts para lanzar en paralelo con modo de prueba que solo consulta el costo, hojas de contacto, historial de prompts, y lo aprendido sobre cómo se portan los modelos. Incluye la guía de dirección de fotografía (que cada encuadre cuente algo, con una biblioteca de referencias de cine descritas en palabras). Usar siempre que haya que generar imágenes o videos en Higgsfield para un video (animaciones médicas, tomas de dron, producto, escenas con personas, también sin cara), cuando se pida "hazlo en Higgsfield", "genera la imagen y anímala", "otra toma como esta", o haya que recuperar cómo se hizo una generación anterior. El estilo de cada cliente sale de su skill de datos (ej. <cliente>-brand).
---

# Higgsfield: imagen → video

Proceso validado el 2026-09-28 (4 animaciones anatómicas + un mapa para un cliente médico). Es
independiente del cliente: el look, los prompts de estilo y las imágenes de referencia salen de la
skill de datos del cliente (`<cliente>-brand`: paleta, look, imágenes aprobadas, decisiones). Los ejemplos de esta skill salen de trabajos reales para un cliente médico; los proyectos se llaman "proyecto A, B, C, D".

**Cuenta (una sola vez):** la CLI de Higgsfield con tu propia cuenta. Si `higgsfield account status` falla:
`npm install -g @higgsfield/cli`, después `higgsfield auth login` (se abre el navegador) y, **el paso que no está
en ninguna guía**, `higgsfield workspace list` + `higgsfield workspace set <id>`: sin él todo comando falla con
`No workspace selected`. Antes de gastar, `higgsfield account status` para ver la cuenta y el saldo. Lo ilimitado
de algunos planes solo funciona en la web, no por la terminal.

## Costos (medidos con `higgsfield generate cost`)

| Modelo | Costo |
|---|---|
| Nano Banana Pro (`nano_banana_pro`), 1k o 2k | 2 créditos por imagen |
| Kling 3.0 pro (`kling3_0 --mode pro`) | 1,5 créditos por segundo: 3 s = 4,5 · 4 s = 6 · 5 s = 7,5. **Mínimo 3 s** (con 1 o 2 s: *"Input should be greater than or equal to 3"*, 2026-10-07) |
| Editar una imagen (corrección con la buena como referencia) | Nano Banana Pro: 2 créditos, lo mismo que una nueva. **Sin probar, más baratos:** Seedream 5.0 Flash y Kling O1 Image 0,5; Nano Banana 2 Lite 1; Flux Kontext 1,5 (2026-10-07). Usarlos solo si dan la misma calidad, y la prueba la pide el editor |
| Wan 3.0 (`wan3_0`) | acepta 2 s: 3,5 créditos. **Sin probar**: solo si iguala la calidad de Kling, y la prueba la pide el editor (2026-10-07) |

Saldo: `higgsfield account status`. Los créditos se cuidan en imagen y en video (el editor, 2026-10-07: *"No podemos gastar tantos créditos de forma innecesaria"*): se genera lo pedido, no variantes "por las dudas". En video se reintenta si el resultado no está a la altura. Para un cliente médico, **la descripción de las dos opciones de cada toma se aprueba antes de generar
cualquier imagen**: el editor la corrige y recién ahí se lanza (`<cliente>-brand/references/decisiones.md`,
2026-10-01). "Dos opciones" son dos imágenes en total (una segura y una creativa), o dos de la idea que eligió el editor si lo pide así (2026-10-07).

Fuera de un pedido no se genera nada.

## El proceso

### 1. Recuperar cómo se hizo lo anterior (gratis)
- Frames de las referencias que pasa el editor:
  `ffmpeg -i ref.mp4 -vf "fps=1,scale=360:-1,tile=4x2" -frames:v 1 hoja.png`, y mirarlas.
- Prompts y ajustes originales: `python3 scripts/hf_history.py --image --since <fecha> --grep <palabra>`
  (también muestra lo que se hizo a mano en la web). Un job id aprobado se reusa como referencia
  con `--image <id>` o `--start-image <id>`, sin volver a subir nada.
- Series de una misma persona en varias escenas (el método: generar a la persona y llevarla a
  otras escenas): `--grep "same woman"` / `--grep "same man"`. Para cada cliente van en
  `<cliente>-brand/references/lifestyle.md`.

### 2. Proponer antes de gastar
Explicar qué se entendió (estilo, duraciones, orden) y proponer cada toma con su **ficha de
dirección**: qué tiene que sentir el espectador, el recurso visual que lo cuenta y por qué, encuadre,
luz, el detalle que cuenta, movimiento y qué rima con las otras tomas. Dar una opción **segura** y
una **de autor**: `references/direccion-de-fotografia.md`. Se trae siempre, sin que el editor la pida:
muchas veces trabaja al apuro. Agregar el costo estimado. Esperar el OK. En un pedido nuevo, el editor
lo pide así explícitamente.

Las referencias de un video (cine, frames, moodboard) sirven **todas a su idea central** y se relacionan entre
sí: nunca se eligen plano por plano según la frase de cada uno.

Fuera de un pedido no se genera nada. Si el editor pasa referencias o ideas para estudiar, se analizan y
se suman a la guía; una prueba se propone y se espera (2026-10-01).

### 3. Imágenes con Nano Banana Pro
- Escribir un plan JSON (formato en `scripts/hf_run.py`): **una imagen por opción** (`"n": 1`, el editor, 2026-10-07), 9:16,
  2k, y como `refs` las imágenes aprobadas del cliente. Primero `--dry-run`: valida el plan y dice
  el costo sin generar. Después lanzarlo sin la bandera.
- **Revisar cada imagen de cerca** (recortes a resolución completa), no la hoja chica: anatomía
  (el especialista lo va a notar), a dónde apunta cada línea si hay rótulos, que no haya
  calavera/raíces si no corresponde, esquinas sin marca de agua.
  **Los detalles realistas no se borran** (texto en libros, etiquetas, bordados, pulseras, logos de
  ropa): al editor le dan "un mundo detrás" (2026-10-07). Se corrige solo un nombre equivocado (otra
  marca, otro negocio, otra persona) o lo que contradice el pedido (una cara o una cabeza cuando no tiene que verse).
- **Tomas sin cara:** revisar el borde superior y las esquinas de cada imagen. En proyecto A se descartaron
  8 de 27 por una cara o media cara asomando; desde el 2026-10-07 no se generan variantes de más: si asoma,
  se corrige editando la imagen y se eligen encuadres que alejan la cabeza (cenital acostado, POV, marco).
- **Vestuario contra la referencia:** comparar la ropa con la imagen de la persona. Nano Banana cambia
  detalles como mangas, cuello o colores (el polo salió sin mangas en 2A y 2B de proyecto C). Si cambió,
  corregirlo editando o decirlo al mostrar la hoja.
- **Persona de referencia con otro encuadre:** *"Use the reference image only for the person … Do not
  copy the framing or the camera angle of the reference"*. Si no, copia la composición.
- **Corregir editando la buena, no regenerando:** usarla como referencia con *"Keep the reference
  image exactly identical… Fix only one thing: …"*. Así se arreglaron las cuerdas vocales y dos
  rótulos. **Excepción: una pose distinta no sale editando** (el brazo cruzado de la 5B de proyecto C siguió
  igual): una pose nueva se regenera.
- Mandarle al editor (SendUserFile) la hoja de lo propuesto en orden de montaje y otra con las
  alternativas, con una línea de por qué se descartó cada una.

### 4. Videos con Kling 3.0 pro
- Mostrarle al editor el prompt de movimiento de cada toma antes de lanzar, salvo que ya haya dicho
  "lanza".
- Plan JSON con `start` (el job id de la imagen aprobada), `duration` y, si hace falta, `end`.
  `--dry-run`, lanzarlo con `run_in_background` y esperar la notificación.
- **Pasar el gate** `scripts/qc_clip.py` con el modo de cámara pedido (y
  `--sin-cara` si la persona no tiene que verse). Mira saltos, deriva, destellos, si hubo movimiento
  y, con `--sin-cara`, piel nueva que entra por los bordes. Además, mirar la tira y
  los recortes: que el movimiento sea el pedido y que la anatomía no se deforme.
- Si falla, reintentar **solo esa toma**, cambiando la frase exacta que causó el problema (tabla de
  abajo). Avisar qué se rehízo y cuánto costó.

### 5. Entrega
Copiar a la carpeta del proyecto con el nombre que usa el cliente, mandarlo, y recién con la
aprobación importarlo al editor. En Premiere, los pasos exactos (medir las capas de ajuste, reemplazarlas) están en `higgsfield-a-premiere`.

**En Premiere, para todos los clientes** (el editor, 2026-10-20): una toma aprobada entra a la timeline **en
lugar de la capa de ajuste** que marca su hueco (misma pista y tramo, capa borrada, **duración exacta de la
capa**) y con Motion > Scale en **101 %**: *"con 100% se ve un poco lo que está detrás del video"*. Falta
confirmar si en vertical pasa lo mismo; en proyecto C (vertical 1080×1920) los Kling de 1076×1928 dejaban
2 px a cada lado al 100 %.

## Cómo se portan los modelos (pagado con créditos)

| Síntoma | Causa | Qué funcionó |
|---|---|---|
| Un órgano se hincha y sale por la boca | "breathe" / "pulse" aplicado a las zonas | *"Every organ keeps exactly its size, shape and position… Only the light changes"* |
| Una zona se prende casi blanca y se vuelve el único foco | brillo libre con cámara fija | misma imagen como `start` **y** `end` + *"no area becomes brighter than the others, no white or yellow hotspots, no flares"* |
| "Slow crane down" termina en acercamiento | Kling interpreta el crane como push-in | *"moving straight down along the throat toward the chest, no zoom, no push-in"* |
| La órbita gira mucho más de lo pedido ("a few degrees" → ~40°) | tendencia del modelo | pedir menos y revisar dónde queda en el segundo que se va a usar |
| El movimiento arranca lento aunque se pida ease-out | casi siempre sale ease-in-out | contar con ~0,3 s casi quietos al inicio |
| Al bajar la cámara aparece anatomía nueva (costillas, pezón) | inventa lo que no estaba en el cuadro | ver en qué segundo aparece y usar el tramo anterior |
| En una toma "sin cara", Kling mete el perfil (nariz, ojo) por el borde del cuadro | la cabeza queda justo afuera de ese borde en la imagen de partida y cualquier movimiento la trae; pedir *"does NOT lean forward… never any part of his face"* la empeoró (2 de 2, Parkinson 2026-10-01) | medir hasta dónde entra (recortes de la esquina, todos los cuadros) y recortar/escalar anclado al lado opuesto con ffmpeg (`crop` + `scale` lanczos, crf 12): gratis. Para la próxima, pedir en la IMAGEN más aire entre el borde y la cabeza fuera de cuadro, o usar encuadres que alejan la cabeza (cenital, POV de un objeto). Lo detecta `qc_clip.py --sin-cara` |
| Nano Banana dibuja a la persona sentada al borde de la cama cuando se pide que intente incorporarse | entiende "struggling to sit up" como "ya sentado" (4 de 4 en el plano lateral, proyecto A) | *"He is still LYING DOWN … not sitting"* + cámara al pie de la cama con el borde superior cortando el pecho |
| Pedir "dos pasos más oscuro" da casi lo mismo que "nublado" (−39 % contra −31 %) | Nano Banana no baja la exposición por número | describir la situación de luz: *"dusk, just after sunset, with all the lamps switched off… the only light is a weak, cool twilight from the window falling on the hands"* (−41/−48 %). Más oscuro todavía: en Premiere |
| Pedir movimiento lento hace cámara lenta de todo el cuadro | riesgo conocido de Kling | *"This is the real slowness of the person, not a slow-motion effect: the coffee surface, the light and the garden behind move at normal speed"* (2 de 2 bien, proyecto A) |
| Una persona que "entra" sale **de espaldas, yéndose** (4B1, proyecto B, 2026-10-06) | el prompt decía *"walks in"* sin decir hacia dónde respecto de la cámara, y además pedía que el niño mirara *"away from the camera"* y la cara del padre *"in shadow against the light"*: el modelo resolvió las tres cosas poniendo a los dos de espaldas, a contraluz | decir la dirección respecto de la cámara y qué parte del cuerpo la mira: *"He is ARRIVING, not leaving… walking INTO the lobby, TOWARD the camera, his body facing the camera… the boy's face turned away, so we only see the back of the boy's head"*. Para esconder la cara de alguien, nombrar qué se ve de esa persona (la nuca), no solo "away from the camera" |
| Nano Banana devuelve `status: nsfw` y no genera nada (quemadura de un niño, proyecto B, 2026-10-06; no cobra) | la combinación de niño + piel lastimada ("reddened patch") + un adulto sujetándole la muñeca | contarlo como primeros auxilios y suavizar la lesión: *"a child's small hand being rinsed under cool running water… a faint light-pink spot… a parent's two hands gently support the child's hand… a calm first-aid moment at home"*. Pasó a la primera |
| Cenital con la mano de un adulto entrando desde una esquina: **Kling mete la cabeza** de esa persona por la esquina (caída, proyecto B, 2026-10-06: el pelo del papá desde los 0,96 s, con salto) | el brazo que entra por la esquina tiene la cabeza justo afuera; pedir "the hand gives a small squeeze" lo hace inclinarse | la misma imagen como `start` y `end` sacó la cabeza, pero el clip quedó **casi quieto** (cambio medio 0,1–0,2: parece una foto). Si el hueco es corto, usar el tramo limpio del primero (medir la esquina cuadro a cuadro y recortar con ffmpeg). Para la próxima: que el brazo del adulto entre por un **borde**, no por una esquina, y sin gestos de fuerza |
| El agua que cae sobre la piel casi no se nota: corre el chorro, pero no se ve el agua recorriendo la mano (quemadura, proyecto B, 2026-10-07; el editor lo aprobó igual, con el comentario) | el prompt pedía *"water flows steadily… glistening reflections"*: describe el chorro, no lo que el agua hace sobre la piel | **sin probar:** describir la textura sobre la piel, en la imagen y en el video: *"a thin sheet of water running over the back of the hand, rivulets tracing the knuckles and dripping from the fingertips, wet glossy skin"* |
| Nano Banana pone la lesión del lado equivocado ("his right shoulder" → hombro izquierdo; 5B de proyecto C, 2026-10-20) | "right" se entiende como el lado derecho de la imagen | nombrar los dos: *"his RIGHT shoulder, which appears on the LEFT side of the image (the figure faces the camera)"*. Para corregir el lado, espejar la imagen gratis con ffmpeg `hflip`. **Cambiar una pose editando no funcionó** (el brazo cruzado siguió igual): una pose distinta se regenera |
| Nano Banana no respeta distancias ni desenfoques de un sujeto ("far away", "out of focus") | resuelve la idea, no la posición | decir dónde cae cada cosa en el cuadro (tercio superior, borde izquierdo, cuánto ocupa) |
| Un golpe deportivo (remate de pádel) sale con **dos toques**: un primer contacto que levanta la pelota y después el remate (3 de 3, proyecto C 2026-10-20; el editor: *"no va acorde a la realidad"*) | la imagen de partida mostraba la pelota sobre la raqueta, o la preparación sola: Kling arma su propio golpe completo y le suma el contacto. Pedir *"only one stroke… touches the racket exactly once"* no alcanzó | **inicio y final**: preparación con la pelota arriba y separada (`start`) + el cuadro después del golpe, raqueta abajo y sin pelota (`end`, editando la de inicio). Salió un solo toque |
| En una órbita sobre rayos X, una estructura (el tendón roto) se corre respecto del hueso | Kling no mantiene rígida la anatomía al girar | para rótulos, el tracker sigue el hueso: medir el desfase cada ~1 s y sumarlo interpolado al track (ver `rotulos-tracking`) |
| Un acercamiento sobre rayos X inventa anatomía (una espiral grande bajo la oreja) y enciende otra estructura en blanco (oído, un proyecto de oído, 2026-11-05) | solo imagen de inicio + *"push-in… inner ear larger in the frame… glow gently breathes"*: Kling completa lo que falta del encuadre y mueve el brillo | **inicio + final**, con el final = recorte de la misma imagen (ffmpeg `crop` + `scale` lanczos al tamaño original, gratis) + *"Nothing new appears… The lighting stays exactly as in the first image"*. Salió limpio a la primera |
| Nano Banana dibuja el cable de un implante (neuroestimulador) cortado en dos o con un extremo suelto (2 de 3, proyecto D, 2026-11-06) | describe el recorrido sin decir que es una sola pieza | *"ONE single continuous wire with no gaps and no loose ends"* + el recorrido completo; editando se arregla el cable, **pero no mueve el dispositivo de lado** (sigue la regla de la pose) |
| Kling: un pulso que "sale del cerebro" estalla en un destello de estrella en la cabeza (síntomas motores, 2026-11-06) | "pulses leave the brain" | *"start quietly inside the brain, with no flash, no burst and no star or lens flare"* + *"Nothing is brighter than the glow of the hand at any moment"*: limpio a la primera |
| Kling: al subir la cámara por un cable, el cable cambia de recorrido y cruza la cara (2026-11-06) | el cable no estaba fijado en el prompt | *"The wire is fixed under the skin and keeps exactly its path at every moment… It never crosses the face, the eye or the cheek, and it never changes shape"*: limpio a la primera |
| Kling: "un pulso sube por el cable" sale como rayas verticales de luz que suben al costado (encendido, 2026-11-06) | lo interpreta como haces, no como algo que sigue el cable | *"a small point of light travels slowly ALONG the existing wire only… No streaks, no beams, no vertical lines"* + el cambio de color con segundos ("from second 3 to 4.5"): limpio a la primera |
| Texto dentro del video | se deforma y no se puede fijar el segundo | nunca: los rótulos van aparte (`rotulos-tracking`) |
| Nano Banana pone mandíbula/raíces de dientes de frente | la "ventana de rayos X" se extiende | *"skin is NOT see-through around the mouth… crowns only"* |
| Nano Banana dibuja rótulos | ortografía y tildes bien; **las líneas no**: en 3 de 6 una faltaba o apuntaba a otra estructura | revisar cada línea; corregir editando |
| Nano Banana ignora "no jaw bone" en 3 de 4 | una sola frase no alcanza | describir la superficie ("softly opaque glass") en vez de solo prohibir |

Salida de Kling: 1076×1928, 24 fps, H.264, sin audio. Se usa tal cual; Premiere lo adapta a la
secuencia.

## Archivos

- `scripts/hf_run.py` — lanza un plan de imágenes o de videos en paralelo, espera, baja y resume.
  Con `--dry-run` valida el plan y consulta el costo sin generar. Si Higgsfield responde 503 (servidor
  caído un momento), reintenta ese job una vez a los 30 s.
- `scripts/contact_sheet.py` — hojas de contacto con título y subtítulo (acepta `video.mp4@1.5`).
- `scripts/hf_history.py` — historial con prompt, referencias y ajustes de cada job.
- `references/prompts.md` — prompts completos que se aprobaron (imagen, edición y video, rayos X y
  personas), para partir de ahí.
- `references/direccion-de-fotografia.md` — la ficha de dirección por toma, la caja de 12 recursos
  narrativos, el look de película, el movimiento que narra y la prueba de proyecto A.
- `references/cine/` — los fotogramas de la biblioteca de referencias (20 al 2026-10-01; `00_hoja.jpg` las
  muestra juntas). Para estudiar, no para subir como estilo. Puede no venir en tu kit: cada fotograma está
  descrito en palabras, con su fuente, en `references/direccion-de-fotografia.md`.
- `scripts/qc_clip.py` — gate de video (saltos, deriva, destellos, movimiento, caras que entran). Necesita `numpy`: `pip3 install numpy`.
