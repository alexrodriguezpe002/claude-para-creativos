---
name: mac-cleanup
description: Libera espacio en el disco interno del Mac del usuario — solo la computadora, sin tocar discos externos. Encuentra y borra cachés de aplicaciones, cachés de versiones de Adobe que ya no están instaladas (el pozo más grande, suelen ser decenas de GB), cachés de npm, logs, temporales y modelos descargados que ya nadie usa. Usar cuando el usuario pida "limpiá mi computadora", "liberá espacio en la Mac", "limpiá el caché", "se me llenó el disco", "no tengo espacio", "borrá lo que no sirve de mi compu", o cualquier variante sobre liberar espacio SIN mencionar discos externos. Si el usuario quiere incluir los discos conectados, usar full-cleanup en su lugar. Borra sola lo 100% regenerable y pregunta por todo lo demás.
---

# Limpieza del Mac

Libera espacio en el disco interno. **No toca discos externos** — para eso está `full-cleanup`.

## La regla que ordena todo

Tres niveles. El nivel decide si se pregunta o no:

| Nivel | Qué es | Qué hago |
|---|---|---|
| **1** | Se regenera solo, o pertenece a una app desinstalada | **Borro sin preguntar** |
| **2** | Se regenera pero cuesta, o es una decisión del usuario | **Muestro y pregunto** |
| **3** | Archivos personales, historial, cosas viejas | **Solo reporto** |

El usuario confirmó este reparto. No promover nada del 2 al 1 por cuenta propia.

## Proceso

### 1. Escanear

```bash
"${CLAUDE_SKILL_DIR}/scripts/scan_mac.sh" /tmp/limpieza
```

No borra nada. Imprime cuánto leyó y sale con código 2 si no leyó nada (un escaneo
que reporta "todo limpio" sin haber leído un solo archivo es peor que no escanear).

Deja `tier1.tsv` y `tier2.tsv` en el directorio de salida.

### 2. Borrar el nivel 1

```bash
"${CLAUDE_SKILL_DIR}/scripts/clean_mac.sh" /tmp/limpieza tier1
```

Vuelve a verificar por su cuenta que no haya apps de Adobe abiertas antes de tocar
la caché compartida. Si las hay, salta esos items y lo dice.

### 3. Presentar el nivel 2 y esperar

Mostrar la tabla con tamaño y qué se pierde en cada caso. Una vez que el usuario elige:

```bash
"${CLAUDE_SKILL_DIR}/scripts/clean_mac.sh" /tmp/limpieza lista /tmp/limpieza/aprobados.txt
```

### 4. Reportar

Tabla de antes/después por disco, y **qué se decidió no borrar y por qué**. Esa
segunda parte importa tanto como la primera.

## Reglas que no se negocian

**Nunca borrar la Media Cache de Adobe con Premiere, After Effects, Media Encoder o
Audition abiertos.** Puede colgar el proyecto que el usuario tenga en pantalla. El script
lo verifica solo, pero si algo se saltea hay que avisarle y ofrecer repetir.

**Nunca cerrar las apps del usuario.** Si hay que cerrar Premiere, se lo pedimos — puede
tener trabajo sin guardar. Es la única cosa de toda la skill que no se hace sola.

**Las cachés de Adobe se borran por versión, no por app.** `~/Library/Caches/Adobe/<App>/<version>/`
guarda una carpeta por versión y **no se limpia al desinstalar**. La regla es
`Adobe <App> 20XX` en `/Applications` → conservar la carpeta que empieza con `XX.`.
Acá aparecieron 78 GB de After Effects 2022/2023/2024 con solo AE 2026 instalado.

**Los modelos de Whisper no se borran a ciegas.** Hay tres cachés y las skills usan dos:
`~/.cache/hyperframes/whisper` (lo usa `npx hyperframes transcribe`) y
`~/.cache/huggingface` (lo usa faster-whisper). El script cuenta las referencias
reales en las skills antes de proponer nada, y nunca los pone en nivel 1.

**Los `._` solo se borran si están huérfanos.** Los que tienen su archivo real al lado
guardan las etiquetas de color del Finder.

## Lo que nunca se toca

- `~/.claude/projects` — el historial de sesiones. El usuario pidió expresamente conservarlo
- `Desktop/POWER BINS`, `POWERGRADES`, `ENCODER PRESET` — sus bins y presets de Premiere
- `Adobe/Common/Motion Graphics Templates` y `Plug-ins` — sus `.mogrt`, no se regeneran
- `~/.claude/skills`, `~/.agents/skills`, `~/.claude/plugins` (los plugins del kit) y la carpeta de memoria
- Nada dentro de `~/Documents`, `~/Pictures` ni proyectos personales

El script tiene esta lista adentro (`PROTECTED`). Si se agrega algo, va ahí, no en el prompt.

## Cómo hablarle al usuario

El usuario es editor de video, no desarrollador. "Caché" sí lo entiende; "AppleDouble",
"TCC" o "cluster size" hay que explicarlos en una línea o no nombrarlos.

- Siempre decir **qué se pierde** al borrar algo, no solo cuánto pesa
- Si algo se regenera, decir **cuánto tarda** ("Premiere va a redibujar las ondas de
  audio la primera vez que abras cada proyecto")
- Cerrar con una tabla de antes/después, no con un párrafo

## Relacionado

- `full-cleanup` — lo mismo más los discos conectados, duplicados e integridad
- Memoria: `reference_disk_cleanup_map`, `reference_exfat_trash_stuck_folder`
