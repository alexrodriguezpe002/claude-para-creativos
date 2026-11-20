---
name: actualizar-kit
description: "Pone al día el kit del equipo (los plugins creativos-…) y pasa una instalación vieja (versión 1: skills sueltas en ~/.claude/skills y hooks en settings.json) a la versión 2 sin perder nada: lo viejo se mueve a una carpeta de respaldo, nunca se borra, y el CLAUDE.md, el perfil y la memoria quedan como estaban. Usar cuando diga \"actualiza el kit\", \"actualiza mis skills\", \"Alex subió algo nuevo\", \"baja lo nuevo del kit\", \"pasa el kit a la versión 2\", o cuando el chequeo marque `v1-migrar`."
---

# Actualizar el kit

Dos partes: **traer lo nuevo** (siempre) y **pasar de la versión 1** (solo si quedan restos de la versión
vieja). Lo que se mueve va a una carpeta de respaldo; nada se borra.

## 1. Ver qué hay

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/proponer-mejora/scripts/repo_del_kit.py"     # Windows: py -3
```

Imprime `MARKETPLACE`, `PLUGINS`, `REPO`, `ORIGEN`, `CARPETA`, `CLI` (el comando `claude`, si hay), `V1`
(cuántas skills de la versión 1 hay sueltas) y `HOOKS_V1`.

## 2. Traer lo nuevo

**Si `ORIGEN=app`** (lo instaló desde la app): la app no muestra una opción para que las mejoras lleguen solas
(probado el jue 19-11-2026: «Add marketplace» no tiene «Sync automatically»). Traerlas como abajo, con el `CLI`: la
app guarda la tienda en el mismo lugar. Si no hay `CLI`, en la app: Customize › Plugins › el plugin › menú **…**
(si ofrece actualizar), o quitar la tienda y agregarla de nuevo. Después, **cerrar la app por completo y volver a
abrirla**.

**Si `ORIGEN=github`, `git` o `carpeta`** (instalado con `/plugin` o con la terminal), con el `CLI`:
1. Si es `carpeta` y esa carpeta es una copia de git: `git -C "<CARPETA>" status --porcelain` (si hay cambios,
   parar y preguntar) y `git -C "<CARPETA>" pull --ff-only`.
2. Anotar las versiones de ahora: `"<CLI>" plugin list` (cada plugin muestra `Version: <código>`).
3. Traer lo nuevo:
   ```bash
   "<CLI>" plugin marketplace update <MARKETPLACE>
   "<CLI>" plugin update <plugin>@<MARKETPLACE>        # uno por cada plugin de PLUGINS
   ```
   Con una tienda de carpeta la versión dice «unknown», y `plugin update` igual vuelve a leer la carpeta («refreshed
   from source»; probado el jue 19-11-2026).
4. Contarle qué cambió: el `installLocation` del marketplace en `~/.claude/plugins/known_marketplaces.json` es
   una copia de git; `git -C <installLocation> log --oneline <versión anterior>..HEAD`, en 2 o 3 líneas sin jerga.
5. Que **cierre la app por completo y la vuelva a abrir** (o cierre y abra la terminal): las sesiones abiertas
   no ven lo nuevo.
6. Para que llegue solo la próxima vez (opcional, solo si usa la terminal): `claude` › `/plugin` › Marketplaces ›
   el del kit › **Enable auto-update**. En la app, `/plugin` abre Customize y esa opción no está: queda «actualiza
   el kit».

**Si no hay `CLI` ni vino de la app:** en la app, Customize › Plugins (escribir `/plugin` abre esa pantalla), y
después cerrar y abrir la app.

## 3. Pasar de la versión 1 (si `V1` > 0 o `HOOKS_V1=sí`)

La versión 1 copiaba las skills a `~/.claude/skills` y escribía los hooks en `settings.json`. Con los plugins
eso quedaría **repetido** (dos skills con el mismo nombre, el registro corriendo dos veces).

1. Simular (no cambia nada) y mostrarle el resultado en fácil:
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/migrar_v1.py"
   ```
2. Si dice "Se quedan donde están (falta el plugin …)": tenía skills de un grupo que no instaló. Preguntar con
   opciones (la recomendada primero):
   1. **Instalar ese grupo (Recomendado si usa esas skills)**: desde la app, o con
      `"<CLI>" plugin install <plugin>@<MARKETPLACE>`.
   2. No lo uso: se guardan igual en el respaldo (`--tambien <plugin>` en el paso 3).
3. Con su OK (opciones: **Pasar a la versión 2 (Recomendado)** / Ver el detalle antes / Ahora no):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/migrar_v1.py" --aplicar --memoria --quitar-bloque-memoria
   ```
   - Mueve las skills viejas a `~/.claude/skills-anteriores/<fecha>-v1/`.
   - Quita de `settings.json` solo los hooks que puso la versión 1 (copia antes: `settings.json.antes-de-v2-<fecha>`).
   - `--memoria`: todas las sesiones usan la memoria que ya tenía (`autoMemoryDirectory`).
   - `--quitar-bloque-memoria`: saca del `CLAUDE.md` el bloque "MEMORIA-UNICA", que con lo anterior sobra (copia
     antes). Si no se puede saber que sobra, lo deja.
   - No toca su perfil, su memoria, sus skills propias, `~/.claude/remote-control` ni `~/kit-claude-creativos`.
4. Si alguna skill vieja la había cambiado a mano, su versión quedó en `skills-anteriores`: se puede volver a
   poner como skill propia **con otro nombre**, o llevar el cambio al kit con `proponer-mejora`.
5. Cerrar la app por completo y volver a abrirla.

## 4. Skills a medida (si tiene)

Si en el repo del kit hay una carpeta suya en `a-medida/<nombre>/`: clonar el repo en una carpeta temporal
(`gh repo clone <REPO> "$(mktemp -d)/kit"`) y copiar a `~/.claude/skills/` cada carpeta de ahí que tenga un
`SKILL.md` directamente adentro (la anterior, a `~/.claude/skills-anteriores/<fecha>/`). **Nunca** `referencias/`
(son para leer, no se instalan) y nunca dentro de los plugins. Borrar la carpeta temporal al terminar.

## 5. CLAUDE.md

Comparar sus secciones con `${CLAUDE_PLUGIN_ROOT}/skills/conoceme/references/plantilla-CLAUDE.md`. Si le falta
una sección de la plantilla, mostrársela y agregarla al final con su OK (con su nombre en lugar de `{{NOMBRE}}`,
copia antes: `CLAUDE.md.antes-de-actualizar-<fecha>`). Nunca borrar ni reescribir lo que ya tiene.

## 6. Cerrar

Correr el `chequeo` y contarle en 2 o 3 líneas: qué llegó de nuevo, qué se movió (y dónde quedó) y qué falta.
