---
name: respaldar
description: "Respalda en GitHub, en un repo PRIVADO `claude-respaldo` de la propia cuenta de la persona, lo de Claude en su computadora: la configuración (CLAUDE.md, ajustes sin claves, skills propias, hooks), las conexiones (sin claves), el registro de cada proyecto de ~/PROYECTOS y, solo si la persona dijo que sí, su perfil y su memoria de ~/MI-SISTEMA-CLAUDE. Las auditorías y los procesos de la empresa nunca se respaldan. Corre sola una vez por día y lo restaura en una computadora nueva. Mac y Windows. Usar cuando diga \"respalda mis cosas\", \"haz un respaldo\", \"guarda todo en GitHub\", \"voy a cambiar de computadora\", \"restaura mi respaldo\", \"¿cuándo fue el último respaldo?\", \"no quiero que se respalde mi perfil\", \"falló el respaldo\", o cuando llegue un aviso \"⚠️ RESPALDO\" o \"📦 RESPALDO\"."
---

# Respaldar

Lo de Claude vive en esta computadora. Esta skill lo copia a `~/respaldo-claude/claude-respaldo` y lo sube a
**su** GitHub, a un repo **privado** `claude-respaldo` (si no existe, lo crea privado). Solo la persona lo ve.

| Se guarda | No se guarda |
|---|---|
| `~/.claude`: CLAUDE.md, ajustes (con las claves tapadas), sus skills propias, hooks, comandos, agentes, registro de proyectos | Videos, audios, renders, `MATERIAL/`, archivos de más de 20 MB |
| Conexiones (MCP) de Claude Code y de la app de escritorio, **con las claves tapadas** | Claves, tokens y contraseñas (en la copia dicen `<REDACTADO>`; los originales no se tocan) |
| De cada proyecto en `~/PROYECTOS`: `MD FILES/`, `HYPERFRAMES/` (sin videos ni audios), `CLAUDE.md` | **Auditorías, procesos e informes de la empresa** (`~/MI-SISTEMA-CLAUDE/auditoria/`, `procesos/`): nunca, ni con su sí |
| **Solo con su sí:** `~/MI-SISTEMA-CLAUDE` (perfil, memoria, notas) y la memoria de Claude | Los plugins (se reinstalan desde la app) y las skills viejas de la versión 1 |
| **Solo con su sí y en el respaldo completo:** sus conversaciones con Claude, sin las que pasaron por una auditoría | Cachés, logs, entornos de Python, la app de Claude. Los chats de claude.ai viven en su cuenta |

## La primera vez: ¿perfil y memoria?

Antes del primer respaldo (o cuando `--estado` diga «sin responder», o llegue un aviso `📦 RESPALDO`), preguntarle
**una sola vez**, con opciones (AskUserQuestion), sin jerga:

> **¿Respaldo también tu perfil y tu memoria (lo que Claude sabe de ti)?** Se guardan en TU GitHub privado: solo
> tú lo ves.
> - **Sí, también mi perfil y mi memoria:** si cambias de computadora o se pierde, Claude te sigue conociendo.
> - **No, solo la configuración:** tu perfil y tu memoria quedan solo en esta computadora.
>
> Si tu memoria tiene datos de la empresa que no pueden salir de la computadora, elige «No».

Guardar la respuesta con `--personal si` o `--personal no`. Se cambia igual cuando quiera ("ya no quiero que se
respalde mi perfil" → `--personal no`). Sin respuesta, se respalda todo lo demás y el perfil y la memoria no.
Si antes dijo que sí y ahora dice que no: desde el próximo respaldo ya no se suben, pero las copias anteriores
siguen en el historial de su repo privado. Si quiere borrarlas del todo: borrar el repo en GitHub (con su OK) y
respaldar de nuevo.

## Comandos

```bash
R="${CLAUDE_SKILL_DIR}/scripts/respaldar.py"
python3 "$R"                  # respaldar ahora                                  (Windows: py -3 "$R" …)
python3 "$R" --completo       # también las conversaciones (antes de cambiar de computadora; solo con su sí)
python3 "$R" --estado         # cuándo fue el último, si falló y qué respondió sobre perfil y memoria
python3 "$R" --personal si    # o «no»: su respuesta a «¿perfil y memoria?»
python3 "$R" --restaurar      # en la computadora nueva
python3 "$R" --restaurar --desde "<carpeta>"   # desde una copia en un disco, sin internet
```

Después de respaldar, contarle en 2 líneas qué se subió (lo dice el script) y el link del repo.
Lo que pasó en los automáticos: `~/.claude/respaldo/respaldo.log`.

**Candados (no saltearlos nunca):**
- Si el repo no figura como privado en GitHub, no sube nada.
- Si esta computadora no tiene copia local y en GitHub ya hay un respaldo (computadora nueva sin restaurar), no
  sube nada: primero se restaura. Así una computadora vacía nunca tapa el respaldo bueno.
- Si GitHub tiene un respaldo más nuevo hecho desde otra computadora, no lo pisa.
- Las auditorías y los procesos de la empresa no salen nunca; el perfil, la memoria y las conversaciones, solo
  con su sí.

## Automático

El plugin base trae un hook: la primera vez que le escribe a Claude en el día, lanza el respaldo en segundo plano.
No demora la respuesta y no muestra nada si sale bien. Si falla, avisa con una notificación de la computadora y,
en el próximo mensaje, con un aviso `⚠️ RESPALDO` para Claude: contárselo en una línea y arreglarlo («Si falla»).
Reintenta a la hora; el mismo error se cuenta una vez por día como máximo.
El automático **empieza cuando la persona responde la pregunta del perfil y la memoria** (sí o no): antes no sube
nada ni crea el repo en su cuenta. Mientras no responda, una vez por día llega un aviso `📦 RESPALDO`:
preguntárselo cuando termine lo que está pidiendo.

## Cambiar de computadora

**En la vieja**, el último día:
1. Con su sí al perfil y la memoria: `python3 "$R" --completo` (sube también las conversaciones). Sin su sí:
   `python3 "$R"`. Confirmar que terminó con ✅.
2. Recordarle que los **videos y el material** no van por acá: pasarlos con un disco externo (en Mac también sirve
   el Asistente de Migración).
3. Desde ahí, usar Claude solo en la nueva (si la vieja sigue respaldando, el candado la frena y avisa).

**En la nueva:**
1. Instalar la app de Claude y los plugins del kit como la primera vez (Customize › Plugins, o
   `claude plugin`), con la **misma cuenta de GitHub** (la skill `chequeo` instala `gh` y conecta la cuenta).
2. `python3 "$R" --restaurar` (o `--restaurar --desde "<carpeta>"` si trae la copia en un disco). Hace todo solo:
   - baja el respaldo y pone cada cosa en su lugar; adapta las carpetas si el usuario de la computadora cambió;
   - en `~/.claude` y `~/MI-SISTEMA-CLAUDE` reemplaza por la versión del respaldo (lo que había queda en
     `~/.claude/restaurar-anteriores/<fecha>/`); los ajustes (`settings.json`) de esta computadora no se tocan; un
     archivo con claves tapadas no pisa a uno que ya existe;
   - en `~/PROYECTOS` solo agrega lo que falta: nunca pisa algo que ya pasó con el disco;
   - si en la vieja dijo que sí al perfil y la memoria, esa respuesta viaja con el respaldo.
3. Hacer el `chequeo`: conecta la memoria que volvió (memoria única) y revisa lo demás.
4. Volver a conectar lo que lista el script en «conexiones para volver a conectar» (sus claves no viajan) e
   instalar desde la app los plugins que lista y falten.
5. Contarle qué volvió, que cierre Claude por completo y lo abra de nuevo, y recordarle pasar los videos si falta.

## Si falla

| Mensaje | Qué hacer |
|---|---|
| `falta el programa gh` / `GitHub no tiene la sesión iniciada` | Skill `chequeo` (arreglos `gh-instalar` y `gh-login`). Volver a respaldar. |
| `esta computadora todavía no lo restauró` | Es una computadora nueva: «Cambiar de computadora → En la nueva». |
| `GitHub tiene un respaldo más nuevo hecho desde OTRA computadora` | Preguntarle (🔔) cuál usa ahora. Si esta es la vieja: dejar de usar Claude acá. Si es la nueva: `--restaurar`. |
| `NO es privado` | Explicarle que no se subió nada para cuidar sus datos; con su OK: `gh repo edit <usuario>/claude-respaldo --visibility private --accept-visibility-change-consequences`. |
| `ya hay un respaldo en curso` | Esperar unos minutos y mirar `--estado`. |
| `falló la subida` | Revisar internet y `gh auth status`; reintentar una vez. Si sigue, mostrarle el error en simple. |

**Windows (pendiente de prueba en una computadora con Windows):** todo vale igual con `py -3`. Falta confirmar en
Windows el aviso de falla (globo de PowerShell), el respaldo en segundo plano que lanza el hook y la restauración
cuando el usuario de la computadora cambia.
