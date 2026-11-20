---
name: mdfilesummary
description: "Registro de cada proyecto en la carpeta `MD FILES/` del proyecto (al lado de MATERIAL, HYPERFRAMES, RENDERS) — un resumen global por proyecto y un archivo por cada video — para retomar cualquier trabajo, hoy o meses después, sin releer todo ni buscar la sesión vieja. Se crea sola al empezar un proyecto de HyperFrames, o con el primer entregable (SRT, render, export) en la carpeta de un proyecto (un hook arma el esqueleto y avisa), se actualiza en cada hito (build terminado, ronda de correcciones, render) y cada vez que la persona la pide. Usar cuando diga \"crea un proyecto\", \"proyecto nuevo\", \"actualiza el md\", \"haz el resumen\", \"guarda el estado\", \"anota dónde quedamos\" (nunca en un DONDE-QUEDAMOS.md suelto), \"retomemos <proyecto>\", \"¿qué hicimos en el video de…?\", \"¿te acuerdas de…?\", \"mis proyectos están en tal carpeta\", cuando llegue un aviso \"📁 MD FILES\", cuando pida \"un md de la sesión\" (archivo MD para cargar en otro chat), o cuando haya que escribir CUALQUIER md de sesión para un proyecto: todos van a su `MD FILES/`. Índice general en `~/.claude/registro-proyectos/INDICE.md`."
---

# MD FILES — el registro de cada proyecto

Cada proyecto guarda su historia en **una sola carpeta**, `MD FILES/`, dentro de la carpeta del proyecto. Nunca MD sueltos dentro de un video, en Descargas o en el Escritorio. Sirve para dos cosas:

1. Retomar un trabajo largo sin releer todo el material.
2. Que en una sesión nueva, meses después, Claude encuentre en segundos qué se hizo en un video y por qué, sin buscar la conversación vieja.

## Qué pide cada comando

- **`/mdfilesummary` (o "el md file")** → crear o actualizar el MD de lo que se está haciendo ahora: si ya hay uno de ese trabajo, se actualiza; si no, se crea. **No se contesta con un resumen en el chat**: basta una línea con el link al archivo.
- **"Un md de la sesión"** → un **archivo MD de toda la sesión**, pensado para cargarlo en otro chat: qué se hizo, decisiones, pendientes con fecha y día de la semana, archivos tocados. Si la sesión es de un proyecto, va en su `MD FILES/` como anexo; si mezcla temas, en `~/.claude/documentos/sesiones/AAAA-MM-DD — <tema>.md`. Nunca reemplazarlo por un mensaje en el chat.

- **"Crea un proyecto" / "anota dónde quedamos"** → la carpeta va en `~/PROYECTOS/<CLIENTE>/<PROYECTO>/` (o en una
  raíz de `carpetas.json`) y el estado, en su `MD FILES/`: `python3 "${CLAUDE_SKILL_DIR}/scripts/md_files.py" ensure
  "<carpeta del proyecto>"` crea el registro, y después se completa. **Nunca** un `DONDE-QUEDAMOS.md`, `NOTAS.md` o
  `ESTADO.md` suelto: si se escribe uno en la carpeta de un proyecto, el hook crea el registro y pide pasar el
  contenido (prueba del jue 19-11-2026: 3 de 3 sesiones lo escribieron a mano).
- El registro se escribe mejor con **Edit o Write** (el hook lo ve al instante). Un script también vale: el hook
  reconoce por la hora lo que escribió un comando de esta sesión.

## Dónde va (cómo elige la carpeta del proyecto)

El hook actúa en **cualquier carpeta de proyecto**, esté donde esté (disco interno, disco externo, Google Drive, Dropbox). La carpeta del proyecto es, en este orden:

1. La que **ya tiene `MD FILES/`**.
2. La que tiene **al menos dos carpetas de la plantilla**: MATERIAL, HYPERFRAMES, RENDERS, PREMIERE, AFTER, AUDIO, MUSIC, EXTRA, GRAFICA, MEDIA.
3. `<carpeta de proyectos>/<CLIENTE>/<PROYECTO>/`, si la persona declaró dónde guarda sus proyectos (ver abajo). Sin declarar nada, vale `~/PROYECTOS/`.
4. **La carpeta que la persona abrió** en la sesión (en la app: el botón de carpeta), cuando el trabajo cae adentro.

**Nunca** crea `MD FILES/` en: la carpeta de usuario, el Escritorio, Descargas, Documentos, Películas, Imágenes, Música, la raíz de un disco, la raíz de una nube (iCloud Drive, Mi unidad, OneDrive, Dropbox), `~/.claude`, carpetas ocultas, carpetas del sistema, ni en un repositorio de código. Si la persona abrió una de esas, el hook no hace nada: el registro aparece cuando abre la carpeta del proyecto.

Para saber qué carpeta tomaría (o por qué ninguna): `python3 "${CLAUDE_SKILL_DIR}/scripts/md_files.py" donde "<ruta>" --cwd "<carpeta abierta>"`.

### Las carpetas de la persona (archivo propio, opcional)

Si la persona guarda los proyectos en otro lado ("mis proyectos están en el disco TRABAJO, en CLIENTES"), o quiere que una carpeta nunca tenga registro, se anota en **`~/.claude/registro-proyectos/carpetas.json`** (es de ella: nunca va al repo del kit):

```json
{
  "raices": ["/Volumes/TRABAJO/CLIENTES", "~/PROYECTOS"],
  "ignorar": ["~/Desktop/Pruebas"]
}
```

- `raices`: carpetas que tienen adentro `<CLIENTE>/<PROYECTO>/`. El índice las recorre (hasta 4 niveles).
- `ignorar`: carpetas donde nunca se crea nada.
- Antes de escribirlo, mostrarle a la persona el contenido y confirmar las rutas (que existan). Si ya existe, agregar sin borrar lo que tenía.

### Adentro de `MD FILES/`

| Archivo | Qué es |
|---|---|
| `<PROYECTO> — Resumen.md` | **Global.** La puerta de entrada: qué es, estado de cada video, decisiones que aplican a todo, pendientes, historial corto. Se mantiene corto: el detalle va en los archivos de cada video. |
| `<PROYECTO> — <Video>.md` | **Uno por video** de HyperFrames: qué es, estado, correcciones por ronda, decisiones y por qué. `Spot 2026 Snippet 4` → `Spot 2026 — Snippet 4.md`. |
| Anexos | Auditorías, propuestas, planes, handoffs de sesión, archivos viejos. Nombre descriptivo; se listan en el Resumen. |

El trabajo que no es de HyperFrames (captions en Premiere, selección de momentos, entrega) va en una sección del Resumen global. Si pasa de ~40 líneas, a un anexo (`<PROYECTO> — Captions.md`).

**Lo que NO va a `MD FILES/`** porque lo leen herramientas desde su lugar, y moverlo rompe cosas:
- Dentro de cada proyecto de HyperFrames: `AGENTS.md`, `CLAUDE.md`, `DESIGN.md`, `BRIEF.md`, `STORYBOARD.md`, `SCRIPT.md`, `BEATS.md`.
- `README.md` de carpetas de handoff, docs de `ASSETS/`, transcripts que leen los scripts.

## Lo que hace el hook solo

Script `scripts/md_files.py`, conectado por el plugin `creativos-base` (su `hooks/hooks.json`). No hace falta llamarlo:

- **Al crear o trabajar en un proyecto de HyperFrames** (escribir un archivo del proyecto, `hyperframes init`, `preview`, `render`, o un Bash que deja cambios en la carpeta del video): crea `MD FILES/`, el Resumen y el archivo del video si faltan, anota la sesión en `## Sesiones` y avisa con un mensaje **📁 MD FILES**. Un comando que solo lee (`grep`, `ffprobe`, un gate que mide) no crea ni anota nada. Lo que dejan los gates (`.gates-cache/`, `snapshots/`) no cuenta.
- **En proyectos sin HyperFrames** (Premiere, captions, entregas): se activa cuando Claude escribe un entregable en la carpeta del proyecto: `.srt`, un export o render (`.mp4`, `.mov`, audio), un timeline (`.xml`, `.fcpxml`, `.prproj`). En una carpeta abierta sin plantilla ni registro cuentan solo video, audio, subtítulos y líneas de tiempo (un `.txt` o una imagen sueltos no arman un proyecto).
- **Si la sesión trabaja en un proyecto que ya tiene registro:** avisa una vez dónde está, para leerlo antes de seguir.
- **Si se escribe un MD de sesión fuera de `MD FILES/`** en un proyecto con registro: avisa para moverlo.
- **Al terminar una respuesta que cambió archivos de un proyecto** sin actualizar su registro: pide actualizarlo. La creación, el render y el Studio abierto después de un build piden siempre; las ediciones y los entregables sueltos, como mucho cada 20 minutos.
- **Cuando la persona nombra un proyecto** (por su nombre, su código "EP 12" o un alias): le pasa a Claude la ruta del Resumen para leerlo antes de responder.
- **Si otra sesión cambió el registro** desde la última vez que esta lo vio: lo avisa con los archivos y la hora. Lo que escribe la herramienta actual no cuenta.
- **Archivos de prueba que arma Claude** no cuentan como entregables. Convención: el nombre empieza con `ZZ` o termina en `-PRUEBA`/`_PRUEBA` antes de la extensión.
- **Mantiene el índice** `~/.claude/registro-proyectos/INDICE.md` (y `indice.json`, `proyectos.json`).

El hook arma el esqueleto; **el contenido lo escribe Claude**. Un esqueleto sin completar no le sirve a nadie.

Si falta Python, el hook no hace nada y no molesta (el `chequeo` lo detecta). Errores: `~/.claude/registro-proyectos/errores.log`.

## Cuándo escribir

1. **Al empezar el proyecto** (el hook avisa): completar el Resumen y el archivo de cada video con lo que ya se sabe: material, duración y formato, con qué skill o herramienta se arma, tema, plan.
2. **En cada hito:** build terminado, cada ronda de correcciones, cada render o entrega, cualquier decisión con trade-off, y siempre que el trabajo se corte a mitad de camino.
3. **Cada vez que la persona pide la skill.** Se actualiza lo que hay; nunca se crea otro archivo para el mismo proyecto o video.
4. **Cuando la persona cuenta una decisión o un cambio del proyecto**, aunque sea de pasada ("el video 2 es otra toma del 3"; "borré esa secuencia"; "este no va"): anotarlo **en ese momento**. Otras sesiones abiertas leen el mismo registro y es lo único que tienen para entender lo que ven.

Correcciones chicas seguidas (px, colores, un timing): una línea por ronda, no una por cambio.

## Cómo actualizar

**Frontmatter.** Siempre al día: el índice y el aviso salen de ahí.
- `actualizado:` la fecha de hoy.
- `estado:` `en curso` · `entregado` · `pausado` · `cerrado`.
- `resumen:` una línea que sirva sola: qué es y en qué estado está. Es lo único que se ve si el disco no está conectado.
- `alias:` otros nombres con los que la persona puede nombrar el proyecto (invitado, tema). Ej.: `[boda Ana, video de Ana y Luis]`.

**Resumen global:** tabla de Videos y estado → se reescriben (reflejan HOY). Decisiones → con el porqué y la fecha. Pendiente → en el orden en que conviene retomarlo. Historial → una línea por sesión o hito, se agrega y no se borra: `- **2026-09-23** — qué se logró`.

**Archivo del video:** Estado actual → se reescribe. Correcciones → por ronda (`### Ronda 3 — 2026-09-14`, y debajo cada pedido → qué se hizo). Decisiones y por qué → lo que costó decidir, para no volver a preguntarlo.

**Releer antes de escribir.** Puede haber otra sesión escribiendo en el mismo registro: leer la versión actual del archivo, no la que se leyó horas antes.

**`## Sesiones` la mantiene el hook.** No borrarla ni reescribirla.

**Qué va y qué no:** va lo que no se deduce mirando el material (estado, decisiones y porqués, lo que la persona pidió y lo que rechazó, pendientes, rutas puntuales). No va lo que ya vive en otro lado (el código, el transcript, el `BEATS.md`): se linkea, no se copia. Nunca contraseñas, claves ni datos personales de terceros (correos, teléfonos).

## Antes de preguntarle a la persona por algo raro en un proyecto

1. Releer **ahora** el Resumen y el archivo del video: puede haberlo explicado otra sesión.
2. Si no está, buscar en las sesiones de su lista `## Sesiones`: los archivos `~/.claude/projects/<carpeta>/<id>.jsonl` (son grandes: buscar con `grep`, no leerlos enteros).
3. Si se encuentra, anotarlo en el registro y seguir sin preguntar.
4. Recién si no aparece en ningún lado, preguntar, con lo que se sabe.

## Retomar o buscar un proyecto viejo

1. Si llegó el aviso 📁 MD FILES, leer ese Resumen. Si no: `~/.claude/registro-proyectos/INDICE.md`, o `buscar` (abajo).
2. Leer el Resumen global; después el archivo del video; los anexos, solo si hace falta.
3. Si el MD no basta, abrir las sesiones de `## Sesiones` (paso 2 de arriba).
4. Proyectos que alguna sesión tocó pero que no tienen `MD FILES/`: al final del índice, en "Sesiones de proyectos sin registro".
5. Si el disco del proyecto está desconectado, el índice tiene el resumen de una línea; para el detalle, pedirle a la persona que lo conecte.

## Comandos

```bash
S="${CLAUDE_SKILL_DIR}/scripts/md_files.py"     # en Windows: python en vez de python3
python3 "$S" ensure "<ruta de un proyecto o de un video>"   # crear el registro a mano
python3 "$S" donde "<ruta>" --cwd "<carpeta abierta>"        # qué carpeta tomaría, o por qué ninguna
python3 "$S" buscar "EP 12"                                  # qué registros coinciden
python3 "$S" indice                                          # regenerar el índice
python3 "$S" backfill                                        # simular los vínculos sesión→proyecto (--aplicar escribe)
```

`backfill --aplicar` escribe en los Resumen de varios proyectos: mostrar antes la simulación y aplicarlo solo si la persona dice que sí.

## Cuando termines

Una línea para la persona: qué archivo se creó o actualizó, con link. Sin resumen en el chat y sin subir nada a GitHub. Si lo pidió el hook en un hito, basta con "Registro actualizado."

## Antes de preguntar o entregar: releer
Varias sesiones pueden trabajar a la vez en el mismo proyecto. Antes de preguntarle a la persona por algo raro
(una secuencia que no está, un archivo renombrado) y antes de cualquier entrega, releer **ahora** el Resumen y el
archivo del video completos: otra sesión pudo haberlo explicado, y el "Pendiente" puede estar viejo. Lo que la
persona cuente de un proyecto, aunque sea de pasada, se anota en ese momento.
