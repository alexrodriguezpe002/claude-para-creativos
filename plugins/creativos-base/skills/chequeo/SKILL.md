---
name: chequeo
description: "Revisa si la computadora tiene todo lo que usa el kit y da una lista ✅/❌ con el arreglo de cada ❌: sistema, git, GitHub (gh y su sesión), Python, ffmpeg y node (si usa video o animación), los plugins del kit (y deja solo los de su trabajo), la carpeta de proyectos, la memoria única, el perfil y los avisos al celular. Arregla lo que falta solo con permiso, con instaladores oficiales. Mac y Windows. Usar cuando la persona diga \"haz el chequeo\", \"revisa mi compu\", \"¿me falta algo?\", \"¿está todo instalado?\", \"algo no anda con el kit\", después de instalar el kit desde la app, o cuando una skill falla porque falta un programa."
---

# Chequeo

Primero se mira, después se arregla. **El script solo lee**: no instala, no cambia ni borra nada.

## 1. Correr el chequeo

- Mac:
  ```bash
  bash "${CLAUDE_SKILL_DIR}/scripts/chequeo.sh"
  ```
- Windows (PowerShell):
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_SKILL_DIR}/scripts/chequeo.ps1"
  ```

La salida es la misma en los dos: una línea por punto (✅, ❌ o ⚠️), el resumen y `CODIGOS:` con el arreglo de
cada ❌ y ⚠️ (abajo).

## 2. Mostrarlo en fácil

Copiarle la lista tal cual y, debajo, en dos o tres líneas: qué está bien, qué falta y para qué sirve lo que
falta ("sin gh no puedes proponer mejoras al kit"). Sin jerga.

## 3. Preguntar qué arreglar (un menú)

Una pregunta con opciones (AskUserQuestion), la recomendada primero:
1. **Arreglar todo, en orden (Recomendado)**: el orden de abajo; se avisa antes de cada ventana o contraseña.
2. Elegir cuáles.
3. Nada por ahora.

**Reglas al arreglar:**
- Nada se instala ni se cambia sin ese OK. Si algo pide la **contraseña de la computadora**, la escribe la
  persona en la ventana de Apple o de Windows, o en la terminal: Claude nunca la ve ni la escribe.
- Solo instaladores oficiales: en Mac los `.pkg` de cada proyecto (sin Homebrew, salvo que la persona ya lo use);
  en Windows `winget` o el instalador oficial.
- Antes de tocar `~/.claude/settings.json`: copia a `settings.json.antes-del-chequeo-<aaaa-mm-dd>`. Si el archivo
  no es JSON válido, no se toca: se le explica.
- Las ventanas de Apple o de Windows (instaladores, permisos, avisos) **no salen** en las capturas que toma
  Claude: que no se vean no prueba que no aparecieron. Preguntarle a la persona qué ve en su pantalla.
- Después de instalar programas: cerrar la app de Claude por completo y volver a abrirla (así los ve), y volver
  a correr el chequeo. Reportar solo lo que el segundo chequeo confirma.
- **"Está pero no arranca"** = instalación rota (por ejemplo, le falta una librería después de una
  actualización). Se reinstala con lo mismo que lo instaló: si la ruta es de Homebrew (`/opt/homebrew/…` o
  `/usr/local/Cellar/…`), `brew reinstall <programa>`; si no, su instalador oficial de abajo. Instalar otro
  igual no alcanza: las sesiones siguen encontrando primero el roto.

## 4. Los arreglos (en este orden)

**`plugins-elegir`** — Va primero: decide si hacen falta ffmpeg y node. La app instala los 4 plugins del kit y cada
uno suma skills a cada sesión (más gasto, y Claude elige peor la skill). Una pregunta con varias respuestas
(AskUserQuestion, multiSelect): ¿qué haces? **Video y edición** (`creativos-video`) · **Animación con código**
(`creativos-animacion`) · **Procesos y oficina** (`creativos-oficina`). El base va siempre. Con la copia de
`settings.json` antes, apagar los que no eligió en `"enabledPlugins"`: `"creativos-animacion@creativos": false` (lo
que va después de `@` es el de `installed_plugins.json`). Se vuelven a prender con `true` o en Customize › Plugins.
Vale para las sesiones nuevas.

**`git-mac`** — Herramientas de línea de comandos de Apple (traen git y Python 3). Avisar antes: *"Va a salir una
ventana de Apple: toca Instalar y acepta. Tarda 5 a 15 minutos."* Correr `xcode-select --install` y esperar a que
la persona diga que terminó.

**`git-win`** — Git for Windows (trae Git Bash, que usan los hooks del kit):
`winget install --id Git.Git -e --source winget`. Sin winget: el instalador de https://git-scm.com/download/win
con las opciones por defecto.

**`git-linux`** — con el gestor de paquetes del sistema (`sudo apt install git`); la contraseña la escribe la persona.

**`gh-instalar`** — GitHub CLI.
- Mac: el `.pkg` oficial de la última versión en https://github.com/cli/cli/releases/latest (archivo
  `gh_<versión>_macOS_universal.pkg`). Bajarlo a Descargas con `curl -L -o`, decir nombre y tamaño, y abrirlo con
  `open`: la persona sigue el instalador de Apple (Continuar, Instalar, su contraseña).
- Windows: `winget install --id GitHub.cli -e --source winget`, o el `.msi` de https://cli.github.com.

**`gh-login`** — conectar su cuenta de GitHub. Es interactivo: se lo da en un bloque para que lo corra con ▷ en
la terminal de la app:
```bash
gh auth login --hostname github.com --git-protocol https --web
```
Muestra un código de un solo uso y abre el navegador: la persona lo pega y autoriza. Después, `gh auth setup-git`
(ese sí lo puede correr Claude).

**`python-instalar`** — En Mac, `git-mac` ya trae Python 3: primero eso y volver a chequear. Si aun así falta, el
`.pkg` oficial de https://www.python.org/downloads/macos/. En Windows:
`winget install --id Python.Python.3.12 -e --source winget` (o el instalador de python.org marcando "Add
python.exe to PATH").

**`node-instalar`** — Node.js LTS. Mac: el `.pkg` oficial (la versión LTS más nueva de https://nodejs.org/dist/index.json,
archivo `node-<versión>.pkg`), bajado y abierto como el de gh. Windows:
`winget install --id OpenJS.NodeJS.LTS -e --source winget`. Con el plugin de animación, después: el `--doctor` de
la skill `video-quality-gates` (una vez; deja lista la medición en el navegador de los controles de calidad).

**`ffmpeg-instalar`** — ffmpeg no tiene instalador `.pkg` oficial.
- Mac: los builds estáticos que enlaza la página oficial (https://ffmpeg.org/download.html, sección macOS), el
  de su procesador (el chequeo dice si es Apple Silicon o Intel). Bajar `ffmpeg` y `ffprobe`, descomprimir y
  copiarlos a `/usr/local/bin` con un bloque que la persona corre con ▷ (pide su contraseña):
  `sudo mkdir -p /usr/local/bin && sudo cp ffmpeg ffprobe /usr/local/bin/`. Si ya usa Homebrew:
  `brew install ffmpeg`.
- Windows: `winget install --id Gyan.FFmpeg -e --source winget` (el build que enlaza ffmpeg.org).

**`plugins-instalar`** — Los plugins del kit se instalan desde la app (puede estar en inglés): Customize › Plugins ›
+ Add › Add marketplace, con el repo del kit (`alexrodriguezpe002/claude-para-creativos`, público: no pide cuenta ni token) o la
ruta de su carpeta, y Sync. Con el repo privado de un equipo la app pide un *personal access token*: no hacer que la
persona lo cree; usar la carpeta o, con `gh` conectado, el comando `claude` (`claude plugin marketplace add
<dueño>/<repo>` y `claude plugin install <prefijo>-base@<marketplace>`).
Detalle en el `INSTALAR.md` del kit.

**`v1-migrar`** — Hay una instalación vieja del kit (skills sueltas o hooks en `settings.json`). Usar la skill
`actualizar-kit`, parte "Pasar de la versión 1": mueve (no borra) las skills viejas y quita los hooks duplicados,
con permiso.

**`proyectos-carpeta`** — Dónde guarda sus trabajos. Una pregunta: **En una carpeta PROYECTOS (Recomendado)** →
crear `~/PROYECTOS` (Windows: `%USERPROFILE%\PROYECTOS`); cada trabajo va en `PROYECTOS/<CLIENTE>/<PROYECTO>/` ·
**Ya los guardo en otro lado** (un disco, Drive) → esa ruta a `~/.claude/registro-proyectos/carpetas.json` (skill
`mdfilesummary`, «Las carpetas de la persona»). Sin esto, Claude inventa una carpeta distinta en cada sesión (en la
prueba la creó dentro de MI-SISTEMA-CLAUDE y lo anotó en la memoria).

**`memoria-unica`** — Que todas las sesiones usen una sola memoria, abran la carpeta que abran. Con permiso,
agregar a `~/.claude/settings.json` (con la copia antes) la ruta que sugirió el chequeo:
`"autoMemoryDirectory": "<ruta>"`, con la ruta completa (Mac: `/Users/<usuario>/MI-SISTEMA-CLAUDE/memoria`;
Windows: `C:\\Users\\<usuario>\\MI-SISTEMA-CLAUDE\\memoria`, con las barras dobles del JSON). En una instalación nueva
va en `~/MI-SISTEMA-CLAUDE/memoria`, al lado del perfil, para que la persona la vea en el Finder o el Explorador:
crear la carpeta antes. Si ya había memoria en la carpeta de usuario (instalación vieja), se usa esa para no perder
nada. Vale para las sesiones nuevas.

**`avisos-celular`** (opcional) — Que llegue un aviso al celular cuando Claude necesita algo o termina. Con
permiso, en `settings.json`: `"inputNeededNotifEnabled": true` y `"agentPushNotifEnabled": true`.

**`perfil-conoceme`** — Al final, porque es una conversación: ofrecer seguir con la skill `conoceme`.

## 5. Cerrar

Volver a correr el chequeo, mostrar la lista nueva y decir en una línea qué quedó pendiente (si algo).
