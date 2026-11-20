---
name: conectar-celular
description: Conecta la computadora de la persona (Mac o Windows) con la app de Claude del celular (Remote Control), para que aparezca en la pestaña Código del celular y pueda abrir sesiones nuevas desde el teléfono, con sus archivos, skills y memoria. Mira el estado sin falsas alarmas, le pone un botón para conectar con un clic, confirma que quedó conectada y, si quiere, la deja siempre conectada (arranca sola al prender la compu). Usar cuando diga "conecta el celular", "conecta mi celular", "reconecta el celular", "el celular no ve la Mac", "no me aparece la computadora en el celular", "voy a trabajar desde el celular", "prepara la compu para el celular", "¿cómo uso Claude desde el celular?", "¿está conectado el celular?", "déjalo siempre conectado", "quita el modo siempre conectado", después de reiniciar la compu, o cualquier variante.
---

# Conectar el celular con la computadora

**Qué logra:** desde la app de Claude del celular, la persona abre sesiones que corren **en su computadora**, con
sus archivos, skills y memoria, como si estuviera sentada frente a ella. Lo hace el servidor
`claude remote-control`, que lanzan los scripts de esta skill.

| Modo | Cómo arranca | Se corta si… |
|---|---|---|
| **En una pestaña** (el normal) | La persona toca ▷ en un comando; queda en una pestaña de la terminal de la app de Claude | cierra la app de Claude o esa pestaña, o reinicia la compu |
| **Siempre conectado** (opcional, *pendiente de prueba*) | Solo, cada vez que inicia sesión; se reconecta solo | apaga la compu |

Aparte, la app de escritorio tiene **Connect new sessions to Remote Control** (Ajustes → Claude Code): con eso, las
sesiones que se abren **en la compu** también se siguen desde el celular. Para **empezar** sesiones nuevas desde el
celular hace falta este servidor.

## Reglas fijas

1. **El clic lo da la persona.** El modo automático de Claude bloquea lanzar el servidor por su cuenta (con Bash,
   `open` o `run_in_terminal`), aunque la persona lo pida. No intentarlo ni buscar otra vía: darle el comando en un
   bloque `bash` (Mac) o `powershell` (Windows); la app le muestra un botón ▷ al lado.
2. **Nunca `pgrep` (ni nada que salga con error) para mirar el estado.** `pgrep` sale con código 1 cuando no hay
   conexión y la app lo muestra como **Failed** en rojo, aunque sea la respuesta esperada: la persona ve una falla
   y después «funciona». Usar siempre `estado.sh` / `estado.ps1`: terminan con 0 y la primera línea dice el estado.
3. **Nunca dos servidores.** El segundo falla («This folder is already served by another Claude Code») y su pestaña
   repite «Se cortó» cada 30 s: parece que nada anda cuando el primero sí. Los scripts ya no abren un segundo; no
   saltear el paso 1.
4. **Nunca la carpeta de inicio** (`~` o `C:\Users\<nombre>`). Ahí Claude Code nunca guarda la confianza: pregunta
   «Trust …? [y/N]» en cada arranque (y cada reconexión se queda esperando esa respuesta) y sin terminal ni arranca.
   Por defecto los scripts usan `~/PROYECTOS`, la carpeta de proyectos del kit.
5. No escribir nunca en la pestaña del servidor: la tecla espacio muestra el QR y la `w` cambia el modo de sesiones.

## Pasos

1. **Mirar el estado** (esto sí lo corre Claude, sin preguntar):
   - Mac: `zsh "${CLAUDE_SKILL_DIR}/scripts/estado.sh"`
   - Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_SKILL_DIR}/scripts/estado.ps1"`

   Según la primera línea:
   - `ESTADO: conectada` → decírselo en una línea, darle solo «En el celular» y terminar.
   - `ESTADO: conectando` → ya hay un servidor que todavía no conecta: casi siempre espera una respuesta en su
     pestaña. Buscarla con `list_terminal_tabs`, leerla con `read_terminal` y decirle qué contestar (abajo, «La
     primera vez»). **No** darle otro comando.
   - `ESTADO: duplicada` → sobra una pestaña: que haga clic en la que repite «Se cortó» y apriete ⌃ control + C (no ⌘ cmd).
   - `ESTADO: no conectada` → paso 2.

2. **Darle el comando**, solo en su bloque, con una línea: «Toca ▷ al lado del comando» y lo de «La primera vez».
   - Mac:
     ```bash
     zsh "${CLAUDE_SKILL_DIR}/scripts/conectar-celular.command"
     ```
   - Windows (*pendiente de prueba*; si no aparece ▷, que lo copie, lo pegue en el panel de terminal de la app y
     apriete Enter):
     ```powershell
     powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_SKILL_DIR}/scripts/conectar-celular.ps1"
     ```
   Si sus proyectos viven en otro lado (un disco), la carpeta va al final entre comillas (Windows: `-Carpeta "…"`).
   La primera vez en esa carpeta vuelve a preguntar «Trust».

3. **Confirmar sin falsas alarmas.** Cuando diga que lo tocó: `estado.sh --esperar 40` (Windows: `-Esperar 40`).
   Espera hasta 40 segundos a que conecte (la primera vez tarda más: login y preguntas).
   - `conectada` → confirmárselo y pasar a «En el celular».
   - `conectando` → leer la pestaña con `read_terminal` y decirle qué contestar o qué falta (navegador, `y`).
     Después, otra vez `--esperar 30`.
   - `no conectada` → leer la pestaña: ¿lo tocó? ¿Hay un mensaje de error? Ver «Problemas conocidos».

4. **Siempre conectado** (opcional, *pendiente de prueba*). Ofrecerlo solo si va a usar mucho el celular, y solo
   después de que conectó una vez en la pestaña (así ya respondió las preguntas, que sin terminal no se pueden
   responder). En 2 líneas: arranca sola al iniciar sesión y se reconecta sola; mientras la compu esté prendida y
   enchufada, queda disponible desde su cuenta de Claude. Con su sí, el comando con ▷:
   - Mac: `zsh "${CLAUDE_SKILL_DIR}/scripts/siempre-conectado.command"` (otra carpeta: al final)
   - Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_SKILL_DIR}/scripts/siempre-conectado.ps1"`

   Quitarlo: el mismo comando con `quitar` (Windows: `-Accion quitar`). Si no estaban dadas las respuestas de la
   primera vez, el script no instala nada y lo dice. En Mac, apenas quede instalado y con la persona al lado: que
   pida desde el celular algo del Escritorio, Documentos o un disco, para que macOS muestre sus avisos y toque
   **Permitir** (si nadie los toca, desde el celular esas carpetas no se pueden leer).

## La primera vez (y nunca más)

Lo único que toca la persona, y solo la primera vez en esa computadora y esa carpeta:
1. **Navegador** (si el Claude Code de la compu no tenía sesión): entrar con su cuenta de Claude, la misma del
   celular, y tocar **Authorize**.
2. **«Enable Remote Control? (y/n)»** → `y` + Enter.
3. **«Trust <carpeta>? [y/N]»** → `y` + Enter.
4. **Mac:** si macOS pregunta si «Claude» puede acceder a una carpeta o a un disco → **Permitir**.

Después de eso, cada vez que reinicia la compu solo hay que tocar ▷ otra vez (o nada, con «siempre conectado»).

## La guía que se le da (en tú, con estos títulos)

**Antes de empezar (una sola vez)**
- Instala la app **Claude** en el celular (App Store o Google Play) y entra con **la misma cuenta** que usas en la
  computadora.

**En la computadora**
1. Toca ▷ al lado del comando. Se abre una pestaña de terminal dentro de la app de Claude.
2. Si se abre el navegador: entra con tu cuenta de Claude y toca **Authorize**.
3. Si pregunta **«Enable Remote Control? (y/n)»** o **«Trust …? [y/N]»**: escribe `y` y aprieta Enter.
4. En Mac, si pregunta si puede acceder a una carpeta o a un disco: **Permitir**.
5. Cuando diga **Connected**, ya está. (La próxima vez no pregunta nada.)

**En el celular**
1. Abre la app de Claude → pestaña **Código** (Code). Tu computadora aparece con su nombre de red (lo dice la
   pestaña de conectar, por ejemplo «MacBook-de-Ana»).
2. Tócala → **Nueva sesión** y elige el entorno **PROYECTOS** (el nombre de la carpeta). Empieza ahí; si el proyecto está en otro lado (un disco),
   díselo a Claude en el primer mensaje («trabaja en la carpeta …»).
3. Pídele lo que quieras, como en la compu. Si una sesión te pide aprobar algo, te llega un aviso y lo apruebas con
   un toque.

**Para que no se corte**
- No cierres la app de Claude en la compu ni esa pestaña: la conexión corre ahí (con «siempre conectado», no hace
  falta).
- Compu **enchufada y con la tapa abierta**. Enchufada, mientras está conectada no se duerme; con batería sí puede
  dormirse, y al despertar se reconecta sola.
- Si se corta (internet, se durmió, se actualizó Claude), **vuelve a conectar sola**: no hay que tocar nada. Si se
  reinició la compu: abre Claude y di **«conecta el celular»**.
- Si macOS ofrece instalar actualizaciones «esta noche», elige **«Remind Me Later»**: el reinicio corta la conexión.
- Para desconectar: haz clic dentro de esa pestaña y aprieta **⌃ control + C** (no ⌘ cmd + C, que copia; en Windows,
  Ctrl + C), o ciérrala. Al desconectar puede aparecer un instante «✔︎ Connected»: es normal; termina con
  «Desconectado. Ya puedes cerrar esta pestaña.»

## Problemas conocidos

| Lo que se ve | Qué pasa y qué hacer |
|---|---|
| «Failed» en rojo al revisar si está conectada | Era `pgrep`: sale con 1 cuando no hay conexión. No es una falla. Usar `estado.sh`. |
| La pestaña repite «Se cortó… reintento» | Si `estado` dice `conectada`, es una **segunda** pestaña que sobra: cerrarla. Si no, es internet o la compu se durmió: reconecta sola. |
| «This folder is already served by another Claude Code» | Ya hay un servidor en esa carpeta. Está conectada: no abrir otro. |
| `conectando` por más de un minuto | Espera una respuesta en la pestaña («Enable…», «Trust…», navegador) o no hay internet. Leer la pestaña con `read_terminal`. |
| «Workspace not trusted» | Falta responder «Trust» en esa carpeta (o se usó la carpeta de inicio). Conectar en la pestaña y responder `y`. |
| «got no answer» | Falta responder «Enable Remote Control?» una vez, en la pestaña. |
| «You must be logged in» / «requires a claude.ai subscription» | Se cerró la sesión del Claude Code de la compu: el script abre el navegador para entrar. Plan Pro o superior. |
| «only available when using Claude via api.anthropic.com» | Lo lanzó otro programa con variables de la app. Los scripts las quitan; si aparece, que toque ▷ (no correrlo desde Claude). |
| La compu no aparece en el celular | Misma cuenta en las dos apps; `estado` = `conectada`; cerrar y abrir la app del celular. |
| Desde el celular no puede leer Escritorio, Documentos o un disco (Mac) | Falta el permiso de macOS: con la persona al lado, repetir el pedido y tocar **Permitir**. |
| Sesiones que piden aprobación | Es lo normal (modo manual). Se aprueban desde el celular con un toque y llega un aviso (`inputNeededNotifEnabled` en `~/.claude/settings.json`; la skill `chequeo` lo revisa). |
| «Siempre conectado» instalado pero `no conectada` | `estado` lee el registro (`~/MI-SISTEMA-CLAUDE/celular/celular.log`) y dice por qué. Lo más común: falta conectar una vez a mano en esa carpeta. |

**Detalles técnicos:** el `claude` de la Terminal puede ser una versión vieja sin Remote Control (pide 2.1.139 o más
nueva): los scripts usan el Claude Code más nuevo que trae la app de escritorio. Mac: sin Python (en una Mac nueva
abriría la ventana de Apple para instalar herramientas). El modo automático usa un agente de launchd
(`com.creativos.conectar-celular`, arranque copiado en `~/MI-SISTEMA-CLAUDE/celular/`); Windows, una tarea del
Programador de tareas («Claude - conectar celular») o, si Windows no deja, un acceso en la carpeta Inicio.
