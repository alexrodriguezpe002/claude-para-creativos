---
name: revisar-propuestas
description: "Para quien mantiene el kit del equipo: lista las propuestas de mejora abiertas (pull requests), resume cada una en fácil (qué cambia, a quién le llega, qué riesgo tiene), puede probarla en una carpeta aparte y, solo con un OK explícito, la une al kit; si no convence, deja un comentario a quien la propuso. También deshace una unión. Usar cuando diga \"¿qué propuestas hay?\", \"revisa las propuestas\", \"aprueba la propuesta de…\", \"une la mejora de…\", \"deshaz la última mejora\". No sirve para proponer cambios (eso es proponer-mejora)."
---

# Revisar propuestas del kit

Unir una propuesta cambia el kit **para todo el equipo** con la próxima actualización: cada unión, cada comentario
y cada vuelta atrás se hacen solo con un OK explícito de la persona, propuesta por propuesta.

## 1. Repo y permiso

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/proponer-mejora/scripts/repo_del_kit.py"     # Windows: py -3
gh api repos/<dueño>/<repo> --jq '.permissions | {admin, maintain}'
```

- Si `REPO` sale vacío, preguntar de qué repo es el kit.
- Sin `admin` ni `maintain`: decirle que solo quien mantiene el kit puede unir propuestas. Puede ver la lista
  (paso 2), nada más.
- `gh` sin instalar o sin sesión: skill `chequeo`.

## 2. Lista en fácil

```bash
gh pr list --repo <dueño>/<repo> --state open \
  --json number,title,author,createdAt,isDraft,additions,deletions,files,body
```

Para cada una, en una tabla o lista corta:
- **Qué cambia**, en una línea sin jerga.
- **A quién le llega:** qué plugin (base = todos; video, animación, oficina = ese grupo) y qué skills.
- **Riesgo:** *bajo* si solo cambia textos de una skill; *medio* si cambia scripts o varias skills; *alto* si toca
  los hooks (`hooks/`), los manifiestos (`.claude-plugin/`), `chequeo` o algo que corre solo en cada sesión.
- Quién la propuso y hace cuánto (con el día de la semana).

El detalle, solo si lo pide: `gh pr diff <n> --repo <dueño>/<repo>`.

### Fichas de equipo

Si la propuesta cambia `…/equipo/personas/*.md` (una ficha de la skill `ficha-de-equipo`), probarla siempre (paso 3)
y, en esa carpeta, revisar cada ficha que cambia:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/ficha-de-equipo/scripts/ficha.py" revisar <ficha>      # Windows: py -3
```

- Mostrar el `RESULTADO` y cada `PROBLEMA` en palabras simples.
- `RECHAZADA` → **nunca unir**: pedir cambios diciendo qué dato sacar (teléfono, correo, salud, familia, un campo
  que no está en la lista…).
- Si la propuso otra persona que la de la ficha: la ficha tiene que decir «con el OK de <esa persona>», y preguntarle
  a quien revisa si le consta.
- Riesgo *bajo* si la revisión dio OK y solo cambian la ficha, `EQUIPO.md` y `skills/equipo/SKILL.md`.

## 3. Probar (recomendado si el riesgo no es bajo)

En una carpeta temporal, nunca en la copia de trabajo de nadie:
```bash
T=$(mktemp -d) && gh repo clone <dueño>/<repo> "$T/kit" && cd "$T/kit" && gh pr checkout <n>
claude plugin validate . && claude plugin validate plugins/<plugin>      # si existe el comando claude
python3 -m py_compile <scripts .py tocados>; bash -n <scripts .sh tocados>
```
Contarle qué se probó y qué dio. Borrar la carpeta temporal al terminar.

## 4. Decidir, una por una

Pregunta con opciones (la recomendada primero, con su porqué en una línea):
1. **Unir** (recomendada si el riesgo es bajo o las pruebas pasaron)
2. **Pedir cambios**: se le muestra el comentario antes de enviarlo
3. **Dejarla para después**

- Unir, solo con ese OK: `gh pr merge <n> --repo <dueño>/<repo> --squash --delete-branch`.
- Comentar: `gh pr comment <n> --repo <dueño>/<repo> --body-file <archivo>`, con un texto amable y concreto: qué
  falta y por qué.
- Nunca cerrar ni borrar una propuesta sin que lo pida.

## 5. Deshacer una unión

Nunca reescribir la historia (nada de `push --force`). Se deshace con **otra propuesta** que revierte el cambio:

```bash
SHA=$(gh pr view <n> --repo <dueño>/<repo> --json mergeCommit --jq .mergeCommit.oid)
T=$(mktemp -d) && gh repo clone <dueño>/<repo> "$T/kit" && cd "$T/kit"
git switch -c revertir/pr-<n>-<aaaa-mm-dd> && git revert --no-edit "$SHA"
git push -u origin revertir/pr-<n>-<aaaa-mm-dd>
gh pr create --repo <dueño>/<repo> --title "Deshacer: <título de la propuesta>" --body "Vuelve atrás la #<n>: <por qué>."
```

Mostrarle qué se deshace y, con su OK, unir esa propuesta como en el paso 4.

## Cuando termines

Una línea por propuesta: unida, comentada o pendiente. Recordarle que al equipo le llega con "Sincronizar
automáticamente" en la app o con `actualizar-kit`.
