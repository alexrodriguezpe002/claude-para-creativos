---
name: proponer-mejora
description: "Lleva una mejora al kit del equipo como propuesta (un pull request en GitHub) sin que la persona toque GitHub: prepara el cambio en una copia aparte, lo prueba, le muestra el antes y el después, y solo con su OK lo envía para que quien mantiene el kit lo revise. Usar cuando diga \"propón esta mejora\", \"esto debería quedar en el kit\", \"que la skill de X haga Y para todos\", \"sube este cambio al kit\", \"comparte esta skill con el equipo\", o cuando un retro (skill-retro) aprobó un cambio para una skill del kit. Nunca cambia el kit directamente ni une la propuesta: eso es de revisar-propuestas."
---

# Proponer una mejora al kit

Las skills del kit vienen instaladas como plugins: editar la copia instalada no sirve (la próxima actualización la
pisa) y no le llega a nadie. Las mejoras entran como **propuesta**: quien mantiene el kit la revisa y, si la
aprueba, le llega a todo el equipo.

## Reglas fijas

- **Nunca** push a `main` ni a la rama principal, **nunca** unir (merge) la propuesta: eso es de `revisar-propuestas`.
- Enviar la propuesta **sale afuera** (la ve el equipo en GitHub): se envía solo con el OK explícito del paso 6.
- Sin datos de la persona ni de sus clientes en el cambio: nombres, correos, rutas de su computadora, precios.
  Lo personal va en su perfil o en un archivo de ajustes suyo, no en el kit. La única excepción es la ficha de
  equipo (skill `ficha-de-equipo`): campos fijos, revisada por `ficha.py revisar` y con el OK de la persona.
- Todo con `git` y `gh` en una copia aparte, `~/claude-propuestas/<repo>/`. Nunca en la carpeta del plugin instalado.

## 1. Entender el cambio

Qué skill, qué cambia y por qué (qué pasó). Si viene de un retro, usar el texto aprobado tal cual. Si es una skill
nueva, que tenga su `SKILL.md` con descripción en español y sin datos personales.

## 2. Encontrar el repo del kit y revisar GitHub

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/repo_del_kit.py"     # Windows: py -3
```

- `REPO=dueño/repo` → seguir. Si sale vacío, preguntarle a la persona de dónde instaló el kit (la dirección que
  agregó en la app) y usar esa.
- `gh` instalado y con sesión (`gh auth status`). Si no, la skill `chequeo` lo arregla (`gh-instalar`, `gh-login`).
- ¿Puede escribir en el repo?
  ```bash
  gh api repos/<dueño>/<repo> --jq '.permissions.push'
  ```
  `true` → la rama va al repo del equipo. `false` → va a **su copia** (fork): `gh repo fork <dueño>/<repo> --clone=false`
  (si ya existe, no hace nada).

## 3. Copia de trabajo al día

```bash
D=~/claude-propuestas/<repo>
gh repo clone <dueño>/<repo> "$D"          # solo la primera vez
BASE=$(gh repo view <dueño>/<repo> --json defaultBranchRef --jq .defaultBranchRef.name)
git -C "$D" status --porcelain             # si hay cambios sin enviar de otra vez, PARAR y preguntar
git -C "$D" fetch origin && git -C "$D" switch "$BASE" && git -C "$D" merge --ff-only "origin/$BASE"
```

Con fork, sumar su copia como otro remoto (una vez): `git -C "$D" remote add mio https://github.com/<su-usuario>/<repo>.git`.

Si `git` no tiene nombre ni correo en esa copia, ponerlos **solo en esa copia** con su usuario de GitHub y el
correo privado que da GitHub (así no queda su correo real):
`git -C "$D" config user.name "<login>"` y `git -C "$D" config user.email "<id>+<login>@users.noreply.github.com"`
(el id y el login: `gh api user --jq '.id, .login'`).

## 4. Rama y cambio

- Rama nueva desde la principal al día: `propuesta/<tema-corto>-<aaaa-mm-dd>` (minúsculas, guiones).
- Hacer el cambio en `plugins/<plugin>/skills/<skill>/…`. Lo mínimo que resuelve el problema: corregir antes que
  agregar, sin repetir una regla que ya está en otro lado.

## 5. Probar

- Si existe el comando `claude`: `claude plugin validate "$D"` y `claude plugin validate "$D/plugins/<plugin>"`.
- Scripts tocados: `python3 -m py_compile <archivo>`, `bash -n <archivo>`; si la skill tiene pruebas, correrlas.
- Buscar datos que no deberían ir: `git -C "$D" diff | grep -nEi 'password|contraseña|token|api[_-]?key|@[a-z0-9.-]+\.[a-z]{2,}|/Users/|C:\\Users'`.
  Si aparece algo, sacarlo antes de seguir.

## 6. Mostrar el antes y el después, y pedir el OK

En fácil primero: qué va a cambiar para quien use la skill, en 2–4 líneas, y a quién le llega (qué plugin). Después,
el detalle (`git -C "$D" diff --stat` y las líneas que cambian).

Pregunta con opciones (la recomendada primero):
1. **Enviar la propuesta (Recomendado)**
2. Cambiar algo antes
3. Guardarla sin enviar (queda la rama en su copia; se retoma después)

## 7. Enviar (solo con el OK)

```bash
git -C "$D" add -A && git -C "$D" commit -m "<qué cambia, en una línea>"
git -C "$D" push -u origin <rama>          # con fork: push -u mio <rama>
gh pr create --repo <dueño>/<repo> --base "$BASE" --head <rama> \
  --title "Propuesta: <qué cambia> (<skill>)" --body-file <archivo con el cuerpo>
# con fork: --head <su-usuario>:<rama>
```

Cuerpo en español simple:
```
## Qué cambia
## Por qué (qué pasó)
## A quién le llega      (plugin y skill)
## Cómo se probó
## Riesgo                (bajo / medio / alto, y por qué)
```

## Cuando termines

El link de la propuesta y una línea: "Le llega a quien mantiene el kit; cuando la apruebe, le llega a todos con la
próxima actualización." Si la persona necesita el cambio ya, en su computadora, puede copiar la skill a
`~/.claude/skills/` como skill propia mientras tanto (avisarle que después la borre, para no tener dos).
