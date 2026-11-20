# Instrucciones para Claude: instalar el kit

Las lee el Claude de la persona que instala. Haz tú todo lo que se pueda; pregúntale solo lo que no se puede
saber. Lo que se hace con clics en la app lo hace ella: explícale dónde tocar, de a un paso.

El kit es un **marketplace de plugins** (`creativos`) en el repo público `alexrodriguezpe002/claude-para-creativos`:
`creativos-base` para todos y un plugin por grupo (`creativos-video`, `creativos-animacion`, `creativos-oficina`).

## 1. ¿Ya está?

- `~/.claude/plugins/installed_plugins.json` con `creativos-base@…`, o una carpeta `creativos-base` dentro de
  `~/.claude/plugins/synced/` → ya está: ir al paso 4.
- `~/.claude/skills/conoceme` (u otras skills del kit sueltas) sin plugins → tiene la **versión 1**: instalar (paso 2)
  y después pasarla a la 2 (paso 5).

## 2. Instalar (un camino, en este orden de preferencia)

**A. Desde la app.** Lo hace la persona (la app puede estar en inglés): **Customize › Plugins › + Add › Add
marketplace** (en español: Personalizar › Plugins › Agregar) → en **URL**, `alexrodriguezpe002/claude-para-creativos`
→ **Sync**. Escribir `/plugin` en la pestaña Code abre esa misma pantalla (no es un menú de texto). Si un botón no
aparece con ese nombre, pedirle una captura.
- El repo es **público**: la app no pide cuenta de GitHub ni token. Si dice «This marketplace could not be accessed.
  If this is a private repository hosted on github.com, enter a personal access token below.», la URL quedó mal
  escrita: revisarla. Con el repo **privado de un equipo** sale lo mismo, y ahí no hacer que la persona cree tokens:
  usar C con su sesión de GitHub.
- La app puede instalar los 4 plugins de una vez (pasó en la prueba del jue 19-11-2026): el chequeo (paso 4)
  pregunta cuáles usa y apaga el resto.

**B. Desde una carpeta** (la del disco o un ZIP del kit, descomprimido): igual que A, pero en **URL** la ruta de la
carpeta que tiene `.claude-plugin/marketplace.json`. Probado: instala igual. Para traer mejoras, "actualiza el kit"
(`plugin update` vuelve a leer la carpeta; si la carpeta es una copia de git, antes `git pull`).

**C. Con el comando `claude`** (el de la terminal o el que trae la app; en Mac:
`~/Library/Application Support/Claude/claude-code/<versión>/…/claude.app/Contents/MacOS/claude`). Para el repo
público no hace falta nada más. Para el repo privado de un equipo hace falta `gh` con sesión y `gh auth setup-git`
(lo deja el chequeo); sin eso falla con «unable to get password» o «SSH host key is not in your known_hosts».
```bash
claude plugin marketplace add alexrodriguezpe002/claude-para-creativos
claude plugin install creativos-base@creativos
claude plugin install creativos-video@creativos          # y los grupos que use
```
**D. En una Mac, desde la terminal (respaldo):**
```bash
git clone https://github.com/alexrodriguezpe002/claude-para-creativos ~/claude-para-creativos
zsh ~/claude-para-creativos/instalar.sh            # pregunta los grupos; --grupos "video animacion" para no preguntar
```

## 3. Cerrar y volver a abrir la app

Las sesiones abiertas no ven los plugins nuevos. Que cierre la app por completo (Cmd+Q en Mac) y la vuelva a abrir.

## 4. Chequeo y perfil

En una sesión nueva de la pestaña Code, en su carpeta de usuario:
1. **"haz el chequeo"** (skill `chequeo`): pregunta qué hace para dejar solo los plugins de su trabajo, revisa git,
   GitHub, Python, ffmpeg y node (si usa video o animación), la carpeta de proyectos, la memoria única, el perfil y
   los avisos al celular, y arregla lo que falte con su permiso.
2. **"conóceme"** (skill `conoceme`): arma su perfil y el `~/.claude/CLAUDE.md` que lo carga siempre.

## 5. Si tenía la versión 1

Skill `actualizar-kit`, parte "Pasar de la versión 1": mueve las skills viejas a `~/.claude/skills-anteriores/`
(no borra nada), quita los hooks repetidos de `settings.json` (con copia antes) y deja su `CLAUDE.md`, su perfil y su
memoria como estaban.

## 6. Skills a medida

Si el repo privado de su equipo tiene una carpeta suya en `a-medida/<nombre>/`: skill `actualizar-kit`, parte
"Skills a medida". La
carpeta `referencias/` no se instala.

## 7. Cerrar

- Celular: preguntarle (🔔) si quiere conectarlo ahora; si sí, skill `conectar-celular` (en Windows, pendiente de prueba).
- Contarle en 5 o 6 líneas qué quedó:
  - "conóceme" → su perfil; "auditemos mis procesos" → qué automatizar primero; "hagamos una skill para…" → su
    primera automatización;
  - cada trabajo tiene su carpeta (`~/PROYECTOS/<CLIENTE>/<PROYECTO>/` o donde ya los guarda): Claude anota cada
    uno en su `MD FILES/` y lo lee al retomarlo;
  - "haz un retro" al cerrar un trabajo mejora las skills; "propón esta mejora" la lleva al kit del equipo;
  - "actualiza el kit" trae lo nuevo.
