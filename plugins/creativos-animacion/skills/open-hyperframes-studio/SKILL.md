---
name: open-hyperframes-studio
description: Open an existing HyperFrames project in the Studio (the browser preview) from the project's name the user gives. Use when the user asks to open, launch, start or preview a project in HyperFrames Studio — e.g. "abre en hyperframes studio Campaña verano", "levanta el preview del reel institucional", "abre el studio del reel del cliente X". Finds the project folder (the one holding index.html) under ~/PROYECTOS, runs `npx hyperframes preview` in the background and reports the Studio's real URL. Does NOT create projects or render.
---

# Open HyperFrames Studio

Finds an **existing** HyperFrames project and opens it in the Studio. It does not
create, edit or render anything.

## What the user asks

Phrases like:
- "abre en hyperframes studio Campaña verano"
- "levanta el preview del reel institucional"

Take from it the **project** (folder name, topic or alias) and, if there are several
videos inside, **which one**.

## Where the projects are

Every project lives in `~/PROYECTOS/<CLIENTE O MARCA>/<PROYECTO>/`, and its HyperFrames
projects in `HYPERFRAMES/<video>/`. The index `~/.claude/registro-proyectos/INDICE.md`
lists every project with its aliases: read it first to turn a nickname into a folder.

## Step 1 — Find the project

A HyperFrames project is **any folder that holds `index.html`**. **Do not assume paths: search.**

```bash
find ~/PROYECTOS -maxdepth 6 -iname "index.html" -not -path "*/node_modules/*" 2>/dev/null
```

Filter the candidates against the request:
- "teaser" → folders with `teaser`
- "snippet 2" → folders with `snippet` and `2`
- "F2" / "fragment 2" → folders with `f2`

Resolution:
- **One match** → open it, no question.
- **Several, and the request is specific** ("snippet 2") → take the exact match.
- **A plural request** → open **each one** on its own port. "snippets" opens every
  snippet of the episode (snippet 1 → 3010, snippet 2 → 3011, snippet 3 → 3012…);
  the same with "the teasers" / "the fragments" when there are F1/F2/F3.
- **Several, and a generic singular request** ("the teaser" with F1/F2/F3) → ask
  which one, listing the options.
- **None** → report which project folders do exist in that episode.

## Step 2 — Start the Studio

From the project folder (the one with `index.html`), in the background:

```bash
cd "<absolute path of the project>" && npx hyperframes preview --port 3010
```

- Run it with `run_in_background: true`.
- HyperFrames picks another port by itself if 3010 is taken.
- Wait ~3 s and read the process output for the **real port** and the **Studio URL**
  it prints (`http://localhost:<port>/#project/<folder-name>`).
- To open several projects at once (a plural request), start **one process per
  project** on consecutive ports (3010, 3011, 3012…) and read each real URL.

On the owner's Mac, open every Studio URL in **Google Chrome** right away (`open -a "Google Chrome" "<url>"`) — he asked for it (2026-10-13). On other computers the clickable URL is enough unless the user asks.

## Step 3 — Report (in the user's language)

- Which project(s) were opened, and the path.
- The **real Studio URL** (clickable). Several: one line per project with its URL.
- That the preview keeps running in the background (hot reload on).

## Rules

- **Never** run `npx hyperframes render` from this skill.
- Do not edit `index.html` or any file of the project.
- The preview is read-only over a project that already exists; this skill only opens it.

## Lecciones del trabajo (en español)

- **Varios Studios abiertos a la vez vuelven inestable el navegador** (capturas en blanco, pestañas que no
  responden). Si Claude revisa varios proyectos: uno por vez, verificar y cerrar su pestaña antes de abrir el
  siguiente.
- **Si Claude mueve el Studio desde el navegador:** un clic en la regla del timeline no mueve el cabezal; hace falta
  arrastrar. Cada píxel arrastrado avanza más o menos `duración total / 64` segundos.
