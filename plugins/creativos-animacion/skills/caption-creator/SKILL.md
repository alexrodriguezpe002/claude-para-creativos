---
name: caption-creator
description: Adds synced animated captions to a HyperFrames project. Transcribes the video with Whisper (word-level timestamps), reviews and corrects the transcript autonomously for spelling/grammar (no manual review by the editor required), groups words into natural phrase blocks, and builds a GSAP caption composition with two visual modes — bottom (word-by-word drop+fade at the lower third, with pop for emphasis) and hero (the text fills the full screen with a rapid stagger entrance, used for impactful lines). Use when the user asks to add captions, subtitles, or "los captions" to a HyperFrames project — whether it's a CLA teaser, a snippet, a CLF clip, or any other video.
---

# Caption Creator

Generates a synced animated caption overlay for a HyperFrames project. The output is a `captions.html` file — a sub-composition the editor can render standalone or reference from a parent composition.

The actual animation uses the `hyperframes` skill (composition HTML + GSAP) and the `hyperframes-cli` skill (transcription, lint, preview). Read `references/captions.md` from the `hyperframes` skill for the full caption system spec. This file covers the workflow and what makes captions good for the editor's work.

## ⚠ Proyecto con timeline `main` existente (snippets CLA y similares)

Si el proyecto ya tiene un `index.html` con animaciones gráficas y un `window.__timelines['main'] = tl` (como los snippets de `cla-snippet-creator`), **no usar este workflow para crear `captions.html` como sub-composición**. Las sub-composiciones cargan inline en la misma ventana: su `window.__timelines['main']` pisa el del proyecto y todos los segmentos de animación dejan de funcionar.

El flujo correcto para esos proyectos:

- Saltear el paso 4 de este skill (construir `captions.html`)
- Insertar el builder de grupos + tweens directamente en el `index.html` del proyecto, **antes de `window.__timelines['main'] = tl`**
- Usar el template de captions inline documentado en `cla-snippet-creator`, paso 5 (que incluye la lógica de posición dinámica por `layout`)

**Cuándo sí usar este workflow con `captions.html` standalone:** proyectos que solo tienen captions — sin animaciones gráficas con su propio `main` timeline — donde la sub-composición no colisiona con nada.

---

## Priorities (in order)

1. **Ortografía y gramática correctas.** Claude revisa y corrige el texto de forma autónoma antes de construir nada — sin esperar al editor. Nunca inventar ni sustituir palabras ajenas a lo que se dijo.
2. **Sincronización exacta.** Los captions aparecen cuando el locutor dice la palabra, no antes, no después.
3. **Animación limpia.** Entrada y salida suaves — nunca cortes abruptos ni flashes.

## Inputs

Confirmar antes de arrancar:

1. **Path al video** — en qué clip/snippet se van a agregar los captions.
2. **Orientación** — portrait (1080×1920), landscape (1920×1080), o square (1080×1080). Determina posición y tamaño de fuente.
3. **Idioma del audio** — inglés, español, u otro. Crítico para elegir el modelo correcto (ver paso 1).
4. **Dónde crear el archivo** — por defecto: `captions.html` en la raíz del proyecto HyperFrames existente, o en el mismo directorio del video si no hay proyecto todavía.

Si algo es ambiguo, preguntar con una sola pregunta corta.

## Workflow

### 1. Transcribir con Whisper

```bash
# Audio en inglés (la mayoría de los clips del estudio)
npx hyperframes transcribe assets/<clip>.mp4 --model small.en

# Si el audio es en español
npx hyperframes transcribe assets/<clip>.mp4 --model small --language es

# Si la calidad de audio es baja o hay ruido de fondo
npx hyperframes transcribe assets/<clip>.mp4 --model medium.en
```

**Resultado esperado:** `transcript.json` en la raíz del proyecto — un array de objetos `{ text, start, end }` con timestamps por palabra.

Si el transcript tiene >20% de tokens `♪`/`?` o palabras sin sentido → reintentar con `medium.en`. Si sigue fallando, decirle al editor que el audio no es apto para transcripción automática y pedir un `.srt` o `.vtt` manual.

### 2. Leer el transcript y corregirlo de forma autónoma

Leer el `transcript.json`, reconstruir el texto corrido y **revisarlo y corregirlo por cuenta propia, sin esperar al editor**:

- Corregir palabras mal transcritas por Whisper, ortografía, mayúsculas de nombres propios y marcas, y puntuación.
- Pulir la gramática para que las captions lean bien.
- **Nunca inventar ni sustituir palabras ajenas a lo que se dijo** — mantener fiel el contenido hablado; solo arreglar errores, no reescribir el mensaje.
- Marcar los cambios de speaker donde corresponda. Si el transcript ya viene con etiquetas de speaker (de una herramienta de diarización), respetarlas directamente.

Este texto corregido es la fuente de verdad para el contenido en pantalla. Anotar las correcciones hechas para incluirlas en el reporte final al editor, y seguir directo al build.

### 3. Agrupar palabras en bloques de caption

Con el texto ya corregido, construir el array `GROUPS`. Cada grupo contiene un array `words` con los timestamps individuales de cada palabra — son la base de la animación palabra por palabra.

**Reglas de agrupación** (en orden de prioridad — las primeras son inviolables):

- **NUNCA mezclar palabras de speakers distintos en un mismo grupo.** Cambio de speaker = corte inmediato, sin excepciones. No importa cuán corta sea la frase ni cuántas palabras queden: el grupo cierra ahí. Si el siguiente speaker dice solo una o dos palabras, ese grupo tiene una o dos palabras — así tiene que ser.
- **Máximo 5 palabras por grupo** en contenido conversacional/profesional (los clientes del estudio: CLF, CLA).
- **Cortar en pausa >250ms** entre palabras (gap entre `end` de una y `start` de la siguiente).
- **Cortar en fin de oración** (`.`, `!`, `?`) aunque no se haya llegado al máximo.
- **No cortar en medio de una frase natural.** "in the bread and butter" no se parte en "in the bread" / "and butter".
- `end` del grupo = `end` de la última palabra + 150ms de buffer.
- **Ningún caption puede seguir en pantalla cuando el video corta de una persona a otra.** Si el clip tiene cortes de cámara (de un speaker a otro), el `end` de un grupo nunca debe pasar del corte. El texto del speaker anterior sobre la cara del siguiente se lee como un error de sincronización. Esta regla puede pisar el buffer de 150ms: si el corte cae antes, el `end` se recorta al corte aunque el grupo dure muy poco — no importa.

**Detección de cortes de cámara.** Cuando se trabaja sobre footage real (teaser, snippet, clip — no animación pura), detectar los cortes con ffprobe antes de fijar los `end`:

```bash
ffprobe -v quiet -show_frames -select_streams v \
  -f lavfi "movie='<path al video>',select=gt(scene\,0.35)" \
  2>&1 | grep best_effort_timestamp_time
```

Cada `best_effort_timestamp_time` es un corte en segundos. Cruzar esa lista con los grupos: si el `end` de un grupo cae después de un corte y el corte coincide con un cambio de speaker, recortar el `end` exactamente al timestamp del corte. Si por la calidad del video no se detectan cortes confiables, seguir con el timing por palabra normal — esta verificación es best-effort, no bloqueante.

**Corregir el lag de onset de Whisper.** Whisper marca **tarde el primer word de cada frase después de una pausa** — típicamente 0.18–0.40s, y lo peor cae en los cambios de speaker. Es la causa #1 de que un caption se sienta "con un pequeño delay" aunque los timestamps parezcan correctos. Las palabras a mitad de frase sí están bien; el problema es solo el arranque tras silencio. Medir los onsets reales con `silencedetect`:

```bash
ffmpeg -i "<path al video>" -af "silencedetect=noise=-30dB:d=0.18" -f null - 2>&1 | grep silence_end
```

Cada `silence_end` es un onset real de voz (la voz arranca ahí). Cruzarlo con el transcript: para cada grupo cuyo primer word cae justo después de un `silence_end`, calcular `lag = ts_whisper − silence_end` y, si es ≥ ~0.15s, **desplazar el grupo entero por ese lag** (restarlo a `start`, a cada `ts` y al `end`). Se desplaza el grupo completo —no solo la primera palabra— porque el espaciado *interno* de Whisper es preciso; lo que llega tarde es el offset absoluto de arranque.

- **No aplicar un lead global uniforme.** Desplazar todo por igual adelanta los captions que ya estaban sincronizados. La corrección es por-grupo-post-pausa, nunca global.
- Si no hay `silence_end` antes de un grupo (frase encadenada sin pausa), no tocar — Whisper acierta a mitad de speech run.
- Esta corrección es independiente del recorte por corte de cámara: una baja el `start` al onset real, la otra baja el `end` al corte. Pueden aplicarse al mismo grupo.
- **Si `silencedetect` con el threshold estándar (`-30dB:d=0.18`) no resuelve una duda o el editor reporta timing "raro" en un tramo ya auditado, no confiar en Whisper ni en ese único pase — bajar a un análisis de envolvente RMS fino** (ventana 6-8ms, hop 3-4ms, sobre PCM extraído con `ffmpeg -ac 1 -ar 16000 -f s16le`) para ubicar el onset acústico real palabra por palabra. Whisper puede estar mal por 0.1-0.4s en un word específico sin que el resto de la frase esté afectado — no es un problema de threshold, es que el modelo erró ese timestamp puntual.

**Nunca asumir que una palabra "falta" en el transcript de Whisper es un recorte intencional de muletillas.** Cruzar cada grupo contra el transcript palabra-por-palabra completo (no contra el texto corrido reconstruido) antes de armar `GROUPS`. Un patrón real y recurrente: Whisper (o un paso de limpieza previo) se come la primera palabra de una frase nueva justo después de una pausa larga — "well", "so", "it", "I think", pronombres cortos antes de un verbo — exactamente donde también hay lag de onset (ver arriba). Si el `start` corregido de un grupo queda más tarde que el `end` original y hay una palabra del transcript en esa ventana que no aparece en ningún grupo, es una palabra perdida, no un silencio. Agregarla. Regla dura: por cada palabra del transcript completo, debe existir exactamente un `word` en algún grupo — hacer ese conteo antes de dar por terminada la corrección, no solo revisar los puntos que el editor señaló.

**Palabras de enlace (preposiciones, conjunciones, "just so", posesivo+sustantivo) nunca cierran un grupo — abren el siguiente.** Si el corte natural por pausa/máximo-de-palabras deja "...we start WITH" al final de una tarjeta y "the easy part, then..." al inicio de la próxima, mover "WITH" a la tarjeta siguiente: "...we start" / "WITH the easy part, then...". Mismo criterio para "BUT", "YOUR" (antes de un sustantivo: "...than YOUR" → "YOUR budget..."), "KEEPING" (antes de su objeto), o modismos que no se pueden partir ("just so you know" se mueve completo, nunca solo "just"). Motivo: una preposición o conjunción sola al final de una línea lee como frase cortada a mitad de camino; el viewer arma mejor la oración si el conector abre la idea que sigue. Revisar esto en **cada** borde de grupo, no solo donde algo se vea obviamente raro — es el error de agrupación más común y silencioso.

Agregar un campo `speaker` a cada grupo para trazabilidad:

```js
{ start: 4.2, end: 6.8, speaker: "A", emphasis: false, words: [...] }
```

**Modo de cada grupo** — cada grupo tiene un campo `mode`:

- `"bottom"` — caption estándar en la parte baja de pantalla, word-by-word synced a timestamps individuales de Whisper. Es el modo default para la mayoría de los grupos.
- `"hero"` — el texto ocupa toda la pantalla, centrado verticalmente, fuente grande. Las palabras entran en stagger rápido desde `group.start` (no desde timestamps individuales — el efecto visual importa más que el sync exacto). Se usa para líneas particularmente impactantes o relevantes.

**Coordinación con el teaser:** cuando se trabaja en un proyecto `cla-teaser-creator`, los grupos `mode: "hero"` deben coincidir con los slots que NO tienen una animación gráfica asignada. Si un slot tiene animación gráfica (card + icon), ese momento tendrá bottom caption (que quedará oculta bajo la capa opaca de la animación). Si un slot es hero caption, no hay animación gráfica — el caption ES la animación de ese momento. Esta decisión la define el teaser skill antes de invocar el caption workflow.

**Detección de énfasis** — solo aplica a grupos `mode: "bottom"`. Marcar `emphasis: true` en la palabra o en el grupo entero:

- **Por palabra:** números y estadísticas ("12", "3 cities"), nombres propios, términos clave del tema, palabras en ALL CAPS en el original.
- **Por grupo entero:** grupos de 1-3 palabras que sean un remate o punch line ("Worth it.", "Never again.", etc.). Si el grupo es énfasis, todas sus palabras usan el pop.
- Cuando hay dudas, marcar como énfasis — se puede aflojar, nunca se puede recuperar el impacto si queda plano.

**Estructura del array:**

```js
var GROUPS = [
  {
    start: 0.0,
    end: 2.5,
    mode: "bottom",          // "bottom" | "hero"
    speaker: "A",
    emphasis: false,         // true = todas las palabras usan pop (solo aplica en mode "bottom")
    words: [
      { text: "In",     start: 0.00, end: 0.28, emphasis: false },
      { text: "12",     start: 0.32, end: 0.54, emphasis: true  }, // número → pop
      { text: "weeks",  start: 0.56, end: 0.82, emphasis: true  },
      { text: "we",     start: 0.88, end: 0.98, emphasis: false },
      { text: "had",    start: 1.02, end: 1.12, emphasis: false }
    ]
  },
  {
    start: 8.2,
    end: 11.0,
    mode: "hero",            // esta línea toma toda la pantalla
    speaker: "A",
    emphasis: true,
    words: [
      { text: "Worth",     start: 8.20, end: 8.55 },
      { text: "it.",       start: 8.60, end: 9.10 }
    ]
  }
  // ...
];
```

Cuando el texto fue corregido, preservar los timestamps originales del transcript y asignar el texto corregido. Si una corrección cambia el número de palabras, mantener el span de tiempo del segmento original distribuyendo proporcionalmente.

### Cortes de cámara, mayúsculas y tartamudeos — barrido obligatorio

Cuatro reglas que en CLA ep4 costaron tres rondas de correcciones. Aplican a
cualquier cliente: son del habla, no de la marca.

**El corte de cámara es frontera de grupo, y es un dato de entrada.** Se detecta
antes de agrupar, no se verifica después mirando frames:

```bash
ffmpeg -hide_banner -loglevel error -i "<clip>.mp4" \
  -vf "select='gt(scene,0.35)',metadata=print:file=-" -an -f null - 2>&1 \
  | grep pts_time | sed 's/.*pts_time://' > cuts.txt
```

La tarjeta anterior cierra **exactamente** en el corte y la siguiente abre en el
corte — ni un frame después, y sin hueco en el medio. Un caption que sobrevive al
corte queda sobre la cara del speaker nuevo: es el bug que el editor marcó con captura
en CLA ep4 (0.40s de la línea de un speaker encima de la cara del otro), y había cuatro casos
en el episodio cuando sólo se había señalado uno.

**En un corte no se le cree el timestamp a Whisper: se mide.** Whisper estira la
última palabra del que deja de hablar hasta donde arranca la voz siguiente. Casi
siempre la palabra entera cabe antes del corte, así que no hay que sacrificar
ninguna:

```bash
ffmpeg -i clip.mp4 -af "silencedetect=noise=-34dB:d=0.06" -f null -
# si silencedetect no ve nada, envolvente RMS a ventana de 10ms
```

**Mayúscula después de punto — barrido del video completo, dos pasadas.** (a)
tarjeta contra tarjeta, buscando una que abra en minúscula después de un punto;
(b) cada palabra del array alineada contra el transcript, para encontrar los
**puntos que el transcript tiene y el caption perdió** — ése no se ve leyendo
sólo el array. La puntuación sigue **cómo se dijo**: si el speaker enumera con
entonación de cierre, son oraciones distintas, o al menos llevan comas. Única
minúscula legítima: la oración empezó detrás de un gráfico full-screen.

**El tartamudeo se escribe una sola vez.** "we were we were" queda en "we
were". Los speakers se equivocan y el caption lo hace notar lo menos posible. Y un
conector que no puede cerrar su tarjeta ni abrir la siguiente se omite del
display, en vez de forzar una tarjeta rota.
**Las muletillas no se subtitulan.** El editor, 2026-09-10: *"Elimina de los captions
las palabras que son muletillas o que no llevan a nada, por ejemplo 'you know'."*
Fuera: `you know`, `um`, `uh`, `erm`, `I mean`. **Dentro**: todo lo que lleva la
voz del speaker aunque no sea literario — los quotativos (`I was like, hey…`,
`He's like, oh…`), `so`, `of course`, `look`. La prueba: si sacarla no cambia lo
que dice ni cómo suena, se va.

Al sacar una muletilla la región se **reagrupa**, no se edita nada más: la
tarjeta vecina absorbe su tiempo (la continuidad no tiene huecos) y la
puntuación del paréntesis se va con ella — `"But, you know, nobody asked…"`
queda `"But nobody asked…"`, no `"But, nobody asked…"`. `check_captions.py` las
reporta como *muletillas fuera del display a propósito* en vez de contarlas en
`caption-missing-words`; la lista está en `FILLER_WORDS` / `FILLER_PHRASES`.


### 4. Construir la composición `captions.html`

Leer `references/captions.md` del skill `hyperframes` para el spec completo del sistema de captions.

**Estructura de la composición:**

```html
<!DOCTYPE html>
<html>
<head>
<style>
  :root {
    --cap-font: 'Inter', sans-serif;
    --cap-size: 64px;       /* bottom landscape: 64px | portrait: 84px | square: 68px */
    --hero-size: 120px;     /* hero landscape: 120px | portrait: 140px | square: 128px */
    --cap-weight: 600;
    --cap-color: #ffffff;
    --cap-shadow: 0 2px 14px rgba(0,0,0,0.9), 0 1px 4px rgba(0,0,0,0.65);
    --hero-shadow: 0 4px 32px rgba(0,0,0,0.95), 0 2px 8px rgba(0,0,0,0.7);
    --cap-bottom: 80px;     /* landscape: 80px | portrait: 180px | square: 80px */
  }

  body { margin: 0; overflow: hidden; background: transparent; }

  /* Base: todos los grupos son absolute, inicialmente invisibles */
  .caption-group {
    position: absolute;
    left: 0; right: 0;
    font-family: var(--cap-font);
    font-weight: var(--cap-weight);
    color: var(--cap-color);
    line-height: 1.3;
    visibility: hidden;
    /* NUNCA overflow:hidden — corta transforms de scale en palabras énfasis */
  }

  /* BOTTOM: pie de pantalla */
  .caption-group--bottom {
    bottom: var(--cap-bottom);
    text-align: center;
    font-size: var(--cap-size);
    text-shadow: var(--cap-shadow);
    padding: 0 80px;
  }

  /* HERO: ocupa toda la pantalla, centrado verticalmente */
  .caption-group--hero {
    top: 0; bottom: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
    gap: 0 0.2em;
    font-size: var(--hero-size);
    text-shadow: var(--hero-shadow);
    padding: 0 100px;
    text-align: center;
  }

  /* Cada palabra: inline-block para que y/scale funcionen */
  .cap-word {
    display: inline-block;
    opacity: 0;
    transform-origin: center bottom;
  }

  /* Bottom mode: margen entre palabras (hero usa flex gap) */
  .caption-group--bottom .cap-word { margin-right: 0.22em; }
  .caption-group--bottom .cap-word:last-child { margin-right: 0; }
</style>
</head>
<body>

<script>
// ─── DATOS ───────────────────────────────────────────────────────────────────
var GROUPS = [
  {
    start: 0.0, end: 2.5,
    mode: "bottom",          // "bottom" | "hero"
    speaker: "A",
    emphasis: false,
    words: [
      { text: "In",     start: 0.00, end: 0.28, emphasis: false },
      { text: "12",     start: 0.32, end: 0.54, emphasis: true  },
      { text: "weeks",  start: 0.56, end: 0.82, emphasis: true  },
      { text: "we",     start: 0.88, end: 0.98, emphasis: false },
      { text: "had",    start: 1.02, end: 1.12, emphasis: false }
    ]
  },
  {
    start: 8.2, end: 11.0,
    mode: "hero",
    speaker: "A",
    emphasis: true,
    words: [
      { text: "Worth",     start: 8.20, end: 8.55 },
      { text: "it.",       start: 8.60, end: 9.10 }
    ]
  }
  // ... más grupos
];

// ─── HTML ────────────────────────────────────────────────────────────────────
GROUPS.forEach(function(group, gi) {
  var isHero = group.mode === 'hero';
  var groupEl = document.createElement('div');
  groupEl.id = 'cg-' + gi;
  groupEl.className = 'caption-group ' + (isHero ? 'caption-group--hero' : 'caption-group--bottom');

  // fitTextFontSize: evita overflow en frases largas
  var groupText = group.words.map(function(w) { return w.text; }).join(' ');
  var fit = window.__hyperframes.fitTextFontSize(groupText, {
    fontFamily: 'Inter',
    fontWeight: 600,
    // Hero: más ancho disponible; bottom: igual
    maxWidth: isHero
      ? /* landscape: 1720 | portrait: 880 | square: 880 */ 1720
      : /* landscape: 1800 | portrait: 960 | square: 960 */ 1800,
    baseFontSize: isHero
      ? /* landscape: 120 | portrait: 140 | square: 128 */ 120
      : /* landscape: 64  | portrait: 84  | square: 68  */ 64,
    minFontSize: isHero ? 60 : 36
  });
  groupEl.style.fontSize = fit.fontSize + 'px';

  group.words.forEach(function(word, wi) {
    var span = document.createElement('span');
    span.id = 'cg-' + gi + '-w' + wi;
    span.className = 'cap-word';
    span.textContent = word.text;
    groupEl.appendChild(span);
  });

  document.body.appendChild(groupEl);
});

// ─── TIMELINE ────────────────────────────────────────────────────────────────
var tl = gsap.timeline({ paused: true });

GROUPS.forEach(function(group, gi) {
  var groupEl = document.getElementById('cg-' + gi);
  var isHero = group.mode === 'hero';
  var wordIds = group.words.map(function(_, wi) { return '#cg-' + gi + '-w' + wi; });

  // Hacer visible el contenedor antes de la primera palabra
  tl.set(groupEl, { visibility: 'visible' }, Math.max(0, group.start - 0.01));

  if (isHero) {
    // ── HERO: stagger rápido desde group.start ─────────────────────────────
    // Las palabras entran juntas en cascada — el efecto visual prima sobre el sync exacto
    group.words.forEach(function(word, wi) {
      var wEl = document.getElementById('cg-' + gi + '-w' + wi);
      var offset = wi * 0.045; // stagger de 45ms entre palabras
      tl.set(wEl, { opacity: 0, y: -40 }, Math.max(0, group.start - 0.005));
      tl.to(wEl,  { opacity: 1, y: 0, duration: 0.3, ease: 'expo.out' }, group.start + offset);
    });

    // Salida: todas juntas, fade only, ligeramente más lento que bottom
    tl.to(wordIds, { opacity: 0, duration: 0.25, ease: 'power2.in', stagger: 0 }, group.end - 0.25);

  } else {
    // ── BOTTOM: cada palabra en su timestamp exacto de Whisper ────────────
    group.words.forEach(function(word, wi) {
      var wEl = document.getElementById('cg-' + gi + '-w' + wi);
      var isEmphasis = word.emphasis || group.emphasis;

      if (isEmphasis) {
        // POP: scale desde 0.65 con overshoot
        tl.set(wEl, { opacity: 0, scale: 0.65, y: 0 }, Math.max(0, word.start - 0.005));
        tl.to(wEl,  { opacity: 1, scale: 1, y: 0, duration: 0.24, ease: 'back.out(1.7)' }, word.start);
      } else {
        // DROP + FADE: baja desde arriba, empieza rápido, termina lento
        tl.set(wEl, { opacity: 0, y: -16 }, Math.max(0, word.start - 0.005));
        tl.to(wEl,  { opacity: 1, y: 0, duration: 0.2, ease: 'power3.out' }, word.start);
      }
    });

    // Salida: todas juntas, fade only
    tl.to(wordIds, { opacity: 0, duration: 0.18, ease: 'power2.in', stagger: 0 }, group.end - 0.18);
  }

  // KILL determinístico — obligatorio para ambos modos
  tl.set(groupEl, { visibility: 'hidden' }, group.end);
  tl.set(wordIds,  { opacity: 0 }, group.end);
});

// ─── SELF-LINT ───────────────────────────────────────────────────────────────
GROUPS.forEach(function(group, gi) {
  var el = document.getElementById('cg-' + gi);
  if (!el) return;
  tl.seek(group.end + 0.01);
  if (window.getComputedStyle(el).visibility !== 'hidden') {
    console.warn('[caption-lint] grupo ' + gi + ' visible en t=' + (group.end + 0.01).toFixed(2) + 's');
  }
});
tl.seek(0);

window.__timelines['main'] = tl;
</script>
</body>
</html>
```

**Adaptaciones por orientación** (ajustar las variables CSS y los valores en `fitTextFontSize`):

| Orientación | `--cap-size` | `--hero-size` | `--cap-bottom` | bottom maxWidth | hero maxWidth |
|---|---|---|---|---|---|
| Landscape 1920×1080 | 64px | 120px | 80px | 1800 | 1720 |
| Portrait 1080×1920 | 84px | 140px | 180px | 960 | 880 |
| Square 1080×1080 | 68px | 128px | 80px | 960 | 880 |

**Brand overrides:**
- **CLA:** `font-family: 'Anton', sans-serif`, `text-transform: uppercase`, `font-weight: 400`. Énfasis bottom en azul `#4FB3FF` + pop. Hero en blanco puro — la tipografía masiva es suficiente.
- **CLF:** `font-family: 'DM Sans', sans-serif`, `font-weight: 500`. Énfasis en rojo `#D7263D` + pop.
- **Sin brand definida:** `Inter` + blanco.

**Sobre hero mode:**
- `expo.out` con `y: -40` crea una caída dramática que se asienta con precisión — ejecutivo sin ser plano.
- El stagger de 45ms entre palabras hace la entrada legible sin ser lenta.
- No usar `back.out` en hero (tono ejecutivo). Si se necesita más punch, acortar el `duration` a 0.22s.
- Si la línea hero es muy corta (1–2 palabras), reducir el stagger a 0ms — entran simultáneas.

### 5. Lint

```bash
npx hyperframes lint
```

Corregir todos los errores antes de abrir el studio. Si `inspect` reporta texto cortado, acortar el copy del grupo — no bajar el font size.

### 6. Abrir studio

```bash
npx hyperframes preview --port 3020 &
sleep 2
open "http://localhost:3020"
```

Puerto 3020 por default para captions (3010–3019 reservados para snippets/clips).

**Nunca correr `npx hyperframes render`** — el editor exporta desde Premiere.

## Los non-negotiables

- **Un grupo = un solo speaker.** Si dos speakers hablan en el mismo clip, cada uno tiene sus propios grupos. Jamás una línea mezcla palabras de voces distintas.
- **Ningún caption sobrevive a un corte de cámara que cambia de speaker.** Sobre footage real, detectar cortes con ffprobe (ver paso 3) y recortar el `end` del grupo al corte. El caption del speaker anterior nunca queda sobre la cara del siguiente.
- **Los inicios de frase se corrigen al onset real, no al timestamp de Whisper.** Sobre footage real, medir onsets con `silencedetect` (ver paso 3) y desplazar el grupo entero por el lag medido. Nunca un lead global uniforme.
- **Cada palabra del transcript completo aparece en exactamente un grupo.** Contar antes de terminar — Whisper (o un paso de limpieza previo) suele comerse la primera palabra de una frase nueva tras una pausa larga ("well", "so", "it", "I think"). No es lo mismo que una muletilla descartada a propósito.
- **Ninguna palabra de enlace (preposición, conjunción, posesivo antes de su sustantivo) cierra un grupo.** Si el corte natural la deja al final de una tarjeta, se mueve a abrir la siguiente. Revisar todos los bordes de grupo, no solo los que se ven raros a simple vista.
- **Hero y graphic animation no coexisten en el mismo slot de tiempo.** Un momento es hero caption O animación gráfica, nunca los dos. En el teaser, esta decisión se toma en el paso de diseño antes de construir las composiciones.
- **Hero mode usa `expo.out`, nunca `back.out`.** El tono ejecutivo del teaser excluye el overshoot en hero. `back.out(1.7)` solo en bottom mode para palabras énfasis.
- **Todos los tweens van en el `main` timeline.** Nunca `gsap.to()` standalone — el engine determinístico de HyperFrames no los captura en render.
- **Kill determinístico en cada grupo.** `tl.set(el, { opacity: 0, visibility: 'hidden' }, group.end)` — sin esto los captions se acumulan en pantalla.
- **`data-start` en el sub-composition debe coincidir con el primer `group.start`.** Si se usa como sub-composition, `data-start="0"` y `data-duration` = duración total del video.
- **Un solo grupo visible a la vez.** Verificar solapamientos en el self-lint; si dos grupos se superponen, ajustar el `end` del primero.
- **No usar `overflow: hidden`** en el contenedor — corta animaciones de scale y efectos de glow.
- **No `Math.random()`, no `Date.now()`** — la composición se renderiza de forma determinística.
- **Line breaks balanceados** — nunca una sola palabra sola en la segunda línea. Verificar en el frame renderizado.

## Cómo integrar en un proyecto existente

Para usar `captions.html` como overlay dentro de un `index.html` ya armado:

```html
<!-- En index.html, dentro del scene o como track global -->
<div
  data-composition-id="captions"
  data-composition-src="captions.html"
  data-start="0"
  data-duration="<duración total del video>"
  style="position:absolute;inset:0;pointer-events:none;z-index:50"
></div>
```

## Cuando termina

Responderle al usuario en español:

- Cuántos grupos de captions quedaron y la duración total cubierta
- Un resumen de las correcciones de transcript hechas de forma autónoma; si no hubo, decirlo
- Puerto del studio (3020)
- Recordatorio de que **no se renderizó** — él termina en Premiere

No hacer un resumen largo ni listar cada paso.

## Referencias

- `references/captions.md` (skill `hyperframes`) — spec completo del sistema de captions, estilo por tono, posicionamiento, overflow prevention, caption exit guarantee
- `references/dynamic-techniques.md` (skill `hyperframes`) — técnicas avanzadas: karaoke, clip-path reveal, slam words
- `references/transcript-guide.md` (skill `hyperframes`) — modelos Whisper, quality check, cleaning, APIs externas
- `hyperframes-cli` skill — `transcribe`, `lint`, `inspect`, `preview`
- `gsap` skill — timeline API, easing
