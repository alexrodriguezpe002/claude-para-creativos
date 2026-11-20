# Guía de la sesión — para quien facilita

Cómo llevar la sesión de implementación de Claude Code con creativos de publicidad y video: qué preparar,
el orden del día con tiempos, qué decir, qué pegar y qué hacer si algo falla.

---

## 1. Antes de la sesión

**Que traigan ellos:**
- La computadora cargada y **la contraseña de la computadora** (la instalación la pide).
- La cuenta de Claude **Pro o superior** con sesión iniciada en el navegador.
- La app de escritorio de Claude descargada (claude.ai/download) si es posible.
- **Sus procesos por escrito** (los que repiten o quieren delegar).
- **Un material real** para la primera victoria: un video o audio corto (2–5 min), una carpeta de rodaje
  desordenada o un brief de cliente.
- ChatGPT abierto con su cuenta (para exportar el perfil).
- **Cuenta de GitHub** creada y la invitación al repo aceptada (si no tienen, se crea ahí mismo en github.com).

**Que lleves tú:**
- La presentación abierta y esta guía en el celular.
- Cargador, y hotspot por si el wifi falla (la instalación descarga bastante).
- Saber si cada uno usa **Mac o Windows** (cambia la instalación, ver §3).

---

## 2. Orden del día (≈ 3 h 50, con pausa)

| Hora | Bloque | Diapositivas | Sale con |
|---|---|---|---|
| 0:00 | Bienvenida y expectativas | 1–3 | Qué quiere llevarse cada uno |
| 0:15 | **Conceptos** (enseñar a pescar) | 4–14 | El mapa mental: sesión, contexto, skill, modelos, límites |
| 0:55 | **Posibilidades** | 15–18 | Ganas: Gmail, nube, celular, casos reales |
| 1:10 | **Instalación** | 19 | Claude Code + el kit funcionando |
| 1:40 | *Pausa 10 min* | | |
| 1:50 | **Perfil** (`conóceme`) | 21 | Claude ya los conoce |
| 2:10 | **Primera victoria** | | Un resultado real con su material |
| 2:30 | **Auditoría** (`auditemos mis procesos`) | 22 | Su informe a medida |
| 3:10 | **Primera skill** (`crear-skill`) | 20 | Su primera automatización, probada |
| 3:40 | Hábitos, plan y cierre | 23–24 | Fecha de seguimiento |

Si el tiempo no alcanza: la primera skill puede quedar como tarea con fecha, pero **la auditoría no se corta**.

---

## 3. Instalación

### 3.1 Claude Code
- **Lo más fácil:** app de escritorio de Claude → pestaña **Code** → elegir la carpeta de usuario (la casita).
- **En la terminal** (lo pediste vos, así lo tienen en los dos lados):
  - Mac: abrir Terminal y pegar `curl -fsSL https://claude.ai/install.sh | bash`. Después `claude` e iniciar
    sesión con su cuenta.
  - Windows: primero **Git for Windows** (git-scm.com). Después PowerShell:
    `irm https://claude.ai/install.ps1 | iex`. Cerrar y abrir PowerShell, `claude`, iniciar sesión.
- En Mac, si al usar `git` aparece la ventana de "herramientas de línea de comandos", aceptar e instalar
  (unos minutos): es normal.

### 3.2 El kit (desde la app)
**Ellos** en la app, que puede estar en inglés (probado en un usuario nuevo de la Mac, jue 19-11-2026):

1. **Customize › Plugins › + Add › Add marketplace** (en español: Personalizar › Plugins › Agregar). Escribir
   `/plugin` en una conversación de Code abre la misma pantalla.
2. En **URL**, `alexrodriguezpe002/claude-para-creativos` (o la ruta de la carpeta del kit si la reciben en el disco o un ZIP) →
   **Sync**.
   - El repo es público: no pide cuenta de GitHub ni token. Si sale «This marketplace could not be accessed… enter a
     personal access token below», la URL quedó mal escrita. No crear tokens.
3. En la prueba quedaron instalados **los 4 plugins** («Creativos base», «Creativos video», «Creativos animacion» y
   «Creativos oficina», con «Installed locally»). No hay «Sincronizar automáticamente»: las mejoras llegan con
   «actualiza el kit».
4. Cerrar la app por completo y volver a abrirla. El chequeo (3.3) les pregunta qué hacen y apaga los plugins que
   no usan.

Si el botón no aparece: en la pestaña Code, pedirle a Claude "instala el kit siguiendo INSTALAR.md" (camino B o C).
En una Mac, el respaldo de siempre: clonar el repo y `zsh instalar.sh`.

**Si ya tenían la versión 1** (la del primer taller): "actualiza el kit". Pasa todo a plugins sin perder su perfil
ni su memoria; las skills viejas quedan en `~/.claude/skills-anteriores/`.

### 3.3 Chequeo
- Pestaña Code, carpeta de usuario: **"haz el chequeo"**. Sale una lista ✅/❌; lo que esté en ❌ Claude lo
  arregla con su permiso (git, GitHub, Python, ffmpeg, node, memoria única). Si pide la contraseña de la
  computadora, la escriben ellos.
- Escribir `/` y ver que aparecen las skills del kit (`/creativos-base:conoceme`, etc.). Igual se piden hablando.

---

## 4. Perfil

1. **"conóceme"**: si no hay nada exportado, Claude les da el prompt para pegar en **ChatGPT** y en **Claude
   (claude.ai)** (está en la skill `conoceme`, `references/exportar-perfil.md`).
2. Que guarden cada respuesta en `~/MI-SISTEMA-CLAUDE/` (o se la peguen a Claude Code).
3. Claude une todo, pregunta con opciones lo que falta (hasta tres tandas; después pregunta si siguen), les
   muestra el perfil y lo escribe con su OK.
4. Prueba de que funcionó: abrir una **sesión nueva** y preguntar "¿qué sabes de mí?". Este es el momento en que
   se entiende lo del contexto: decirlo en voz alta.

---

## 5. Primera victoria (elegir una según el material que trajeron)

| Trajo | Le dice a Claude | Ve |
|---|---|---|
| Un video o audio | "transcribe este video y dame 3 momentos para reels" | TXT + SRT + momentos con tiempos |
| Carpeta desordenada | "ordena esta carpeta de material" | El plan, lo aplica, y lo deshace |
| Un brief | "tengo este brief" + pegarlo | Idea central, 3 conceptos, guion, shotlist |
| Un link de video (YouTube, Vimeo, Dropbox, Drive) | "baja este video y ármame el proyecto de Premiere: <link>" | La carpeta del proyecto, el video en MEDIA y Premiere abierto con la secuencia armada |

La primera vez que transcribe, descarga el modelo (2–5 min): aprovechar para hablar mientras.

---

## 6. Auditoría

- Que digan **"auditemos mis procesos"** y le pasen sus procesos (archivo, texto o foto de la libreta).
- Claude pregunta lo que falta (banco en `plugins/creativos-oficina/skills/auditoria-procesos/references/preguntas.md`).
- Tu papel: **escuchar y empujar las preguntas de "expandir el alcance"** (lo que pasa antes y después de
  cada proceso). Ahí suelen salir las mejores ideas.
- Preguntas tuyas para sumar, en voz alta, si no salen solas:
  - "¿Qué te pide siempre el cliente que te da pereza?"
  - "¿Qué hiciste esta semana que ya habías hecho igual el mes pasado?"
  - "¿Qué cosa no haces porque no te da el tiempo, pero sabes que te traería clientes?"
  - "¿En qué parte de tu trabajo eres insustituible? Eso no se delega."
  - "Si tuvieras un asistente humano mañana, ¿qué le darías primero?"
- Sale el informe en `~/MI-SISTEMA-CLAUDE/auditoria/`. Leerlo juntos y elegir la quick win.

---

## 7. Primera skill

- **"hagamos una skill para <la quick win>"**. Que tengan a mano un ejemplo real.
- Al terminar: **sesión nueva** y pedirla con sus palabras, sin decir el nombre de la skill. Si se activa sola,
  entendieron qué es una skill.
- Corregir una vez delante tuyo (que vean que la skill se mejora, no solo el resultado).

---

## 8. Cómo enseñar (para que aprendan a pescar)

- **Manos en su teclado, no en el tuyo.** Tú dices qué escribir; ellos escriben.
- Cuando Claude pida permiso, **lee en voz alta qué va a hacer** y por qué es seguro (o no).
- Cuando algo falle, que le pregunten a Claude **"¿qué pasó? explícamelo simple"** antes de que tú lo
  arregles: es el hábito más útil que se pueden llevar.
- Celebrar la primera victoria. La motivación de los primeros días decide si lo siguen usando.
- Cada vez que digan "eso lo hago siempre", decir **"eso es una skill"** y anotarlo en su diario de
  fricciones.

---

## 9. Problemas comunes

| Pasa | Qué hacer |
|---|---|
| `claude: command not found` | Cerrar y abrir la terminal. Si sigue, pedirle a la app de escritorio que lo arregle |
| Windows: Claude no puede correr comandos | Falta Git for Windows |
| Mac: ventana de "herramientas de línea de comandos" | Instalar y esperar; es para `git` |
| Falta Python, git, ffmpeg o node | "haz el chequeo": dice qué falta y lo instala con su permiso (instaladores oficiales) |
| El kit no aparece después de instalarlo | Cerrar la app por completo y volver a abrirla; revisar que el plugin esté activado en Customize › Plugins (Personalizar) |
| La app pide un *personal access token* («This marketplace could not be accessed…») | La URL quedó mal escrita: tiene que ser `alexrodriguezpe002/claude-para-creativos`. Si es el repo privado de un equipo, no crear tokens: instalar desde la pestaña Code con la sesión de GitHub (INSTALAR.md, camino C) o desde la carpeta del kit |
| Al agregar la tienda desde la pestaña Code o la terminal sale «unable to get password» o «SSH host key is not in your known_hosts» | Falta la sesión de GitHub en esa compu (no es el kit): `gh auth login` y `gh auth setup-git`, que es lo que hace «haz el chequeo». Después, agregar la tienda de nuevo |
| macOS avisa «App Background Activity — "python" can run in the background» | Es el asistente de edición o el vigilante de tarjetas, que corren solos. Es normal: no hay que tocar nada |
| gh dice «A new release of gh is available… brew upgrade gh» | Se puede ignorar |
| Control+C no desconecta el celular | Clic dentro de la pestaña que dice Connected y **⌃ control + C** (⌘ cmd + C copia). Después de un segundo ▷ quedan dos pestañas: es la que dice Connected |
| En el celular, la sesión cae en otra compu | Pasa con dos usuarios en la misma Mac (a un participante no). Al abrir la sesión, elegir el entorno **PROYECTOS** |
| El registro de proyectos, el respaldo o el sonido no andan en Cowork | Los automatismos solo corren en la pestaña Code. En Cowork se pide: «actualiza el registro del proyecto» |
| Claude escribió un DONDE-QUEDAMOS.md o armó otra carpeta de proyectos | Falta `~/PROYECTOS`: «haz el chequeo» la crea. El registro avisa y Claude pasa el estado a `MD FILES/` |
| Skills repetidas o el registro avisa dos veces | Les quedó la versión 1: "actualiza el kit" |
| "Límite de uso alcanzado" | El plan Pro tiene cupo que se renueva en unas horas: seguir con lo que no use Claude (escribir procesos) |
| La skill no se activa | Cerrar y abrir Claude; si sigue, la `description` necesita las frases que ellos usan ("propón esta mejora" la lleva al kit) |
| GitHub pide login y no tienen invitación | Invitarlos ahí mismo desde tu celular (Settings → Collaborators) |

---

## 10. Después de la sesión

- **Ese mismo día:** subir las skills que hayan salido a `a-medida/<nombre>/` del repo privado (el del equipo o el
  tuyo; nunca al público), limpias, sin datos de clientes. Ellos las bajan con "actualiza el kit". Si una le sirve a todo el grupo, que entre al plugin con
  `proponer-mejora` (y la apruebas con `revisar-propuestas`).
- **A los 3–4 días:** mensaje corto: "¿usaste la skill? ¿qué falló?".
- **A las 2 semanas:** sesión de seguimiento (1 h): leer su diario de fricciones, segunda auditoría corta,
  segunda skill, y conectar **Gmail y Calendar** si quieren (ahí ya tienen la base).
- **Grupo de WhatsApp** del grupo para dudas y para compartir skills que sirvan a ambos (hacen trabajos
  parecidos: una skill de uno le puede servir al otro).
- **Medir:** que anoten cuánto tardaban antes y cuánto después en el proceso de la quick win. Ese número
  convence más que cualquier explicación.
