---
name: hyperframes-mp4-render
description: Render HyperFrames projects as MP4 at 1920×1080 (landscape) or 1080×1920 (portrait), high quality, at the frame rate its destination needs — 30 fps for a delivery, the base video's own rate when it goes back into an editing sequence (Premiere, on the owner's Mac). Use when asked to render, export ("exportar", "renderizar") or deliver ("entregar") an MP4 from a HyperFrames project. Always uses at least Full HD — never 720p or lower. Mac and Windows.
---

# HyperFrames MP4 Render

Renders a HyperFrames project as **MP4 · Full HD · High Quality**, ready to deliver to
a client (or, on the owner's Mac, to bring back into Premiere).

## fps — according to where the file goes

Decided by the editor on 2026-10-01 and applied the same day, when the delivery templates
moved to 30 fps sequences (*"los templates para los videos [...] deben tener sus
secuencias a 30fps"*):

| Destination | `--fps` | Check |
|---|---|---|
| **Delivery** (client, Drive, delivery page) — the default | `30` | `r_frame_rate` = `30/1`, or it is not delivered |
| **Back into an editing sequence** (overlay, a base to edit — the owner's Premiere) | the exact fps of the base `<video>`, read with ffprobe and passed as a rational (`24000/1001`, never `24`) | the same as the base |
| **No base video** | `30` by default; a client whose brand uses another rate, that rate (e.g. 23.976) | — |

A delivery at 30 over a base that is not 30 is rendered anyway, with a note (it does
not block): over 23.976 one frame of the speaker in five is repeated.

> When the request includes **uploading it to Drive**, use `hyperframes-render-to-drive`
> instead: it renders the same way and also files it in the episode's Drive folder with
> the right name, replacing the previous version in place (Mac and Windows).

The orientation follows the project's dimensions:
- **Landscape:** 1920×1080 → `--resolution landscape`
- **Portrait:** 1080×1920 → `--resolution portrait`
- **Square:** 1080×1080 → `--resolution square`

Commands below run in Claude Code's shell (bash on Mac, Git Bash on Windows).

---

## Process

### 1 — Find the project

A valid project is a folder that contains `index.html`.

If the user gave a Studio URL (`http://localhost:<port>/#project/<folder-name>`):
on Mac or Linux the process serving that port knows the exact folder —

```bash
for p in $(lsof -ti tcp:<PORT>); do lsof -p $p 2>/dev/null | awk '$4=="cwd"{print $NF}'; done
```

— and on Windows (no `lsof`) the folder name is in the URL: search for it as below.
If they gave a path, use it.

If they gave a name (no Studio running), search this computer's client folders —
`<video-quality-gates>` is that skill's folder (a sibling of this one); on Windows
`py -3` instead of `python3`:

```bash
python3 "<video-quality-gates>/scripts/video_config.py" find <client> <words of the name>
#   e.g.  find cla 067 snippet 2   ·   find clb 020   ·   find cle teaser
```

It lists every folder with an `index.html` under the client's folder whose path holds
every word. With no config yet it says what to ask the user. For a project outside
the client folders, search from the folder the user names:

```bash
find "<folder>" -maxdepth 5 -name index.html -not -path "*/node_modules/*" 2>/dev/null | head -20
```

One candidate → go on. Several → list them and ask.

---

### 2 — Detect the orientation

Read `index.html` and look for the composition root's dimensions (`data-width` /
`data-height` on the root, `--comp-width` / `--comp-height` in `:root`, or the
size of the `.stage` / `#root` container):

```bash
grep -E 'data-width|data-height|--comp-width|--comp-height|width.*1080|width.*1920|height.*1920|height.*1080' "<project_dir>/index.html" | head -20
```

- `width > height` → **landscape** (`--resolution landscape`)
- `height > width` → **portrait** (`--resolution portrait`)
- `width == height` → **square** (`--resolution square`)

If the dimensions cannot be read from the HTML, assume landscape (1920×1080).

---

### 3 — Render

Run it as a background task (long renders can exceed the normal timeout):

```bash
cd "<project_dir>" && npx hyperframes render \
  --format mp4 \
  --fps <30 | the base's fps> \
  --quality high \
  --resolution <landscape|portrait|square>
```

Use `run_in_background: true`. The output goes to `renders/<project-name>_<timestamp>.mp4`
inside the project folder by default. To name it:

```bash
cd "<project_dir>" && npx hyperframes render \
  --format mp4 \
  --fps <30 | the base's fps> \
  --quality high \
  --resolution <landscape|portrait|square> \
  --output "<project_dir>/renders/<name>.mp4"
```

---

### 4 — Check the output

Once the render finishes (exit 0), confirm the file exists and has a plausible size:

```bash
OUTPUT="<path_to_output.mp4>"
[ -s "$OUTPUT" ] && echo "OK" || echo "EMPTY OR MISSING"
ffprobe -i "$OUTPUT" -show_format -v error 2>&1 | grep -E "duration|size|bit_rate"
```

And the resolution and fps:

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate \
  -of csv=p=0 "$OUTPUT"
```

Expected for a delivery:
- Landscape: `1920,1080,30/1`
- Portrait: `1080,1920,30/1`
- Square: `1080,1080,30/1`

Back into an editing sequence: the `r_frame_rate` must be the base's.

---

### 5 — Report

In the user's language, with the file's path and its data:

```
✅ Render ready:
- renders/My-Snippet_2026-06-30_14-30-00.mp4
  1920×1080 · 30 fps · MP4 · High Quality · 287 MB
```

---

## Quick flag reference

| Parameter | Value |
|---|---|
| `--format` | `mp4` |
| `--fps` | `30` for a delivery; the base's fps when it goes back into a sequence |
| `--quality` | `high` |
| `--resolution` | `landscape` / `portrait` / `square`, from the project |

**Never use** `720p`, `draft`, or leave out `--resolution` in this workflow — Full HD
at least, always.

---

## Edge cases

- **Project not found:** say so clearly, do not go on.
- **Render fails (exit ≠ 0):** show the last lines of the log and do not report success.
- **Empty output:** the CLI can exit 0 after a capture error; if `[ -s "$OUTPUT" ]`
  fails, treat it as a failed render.
- **Several projects:** render one at a time; start the next when one finishes.
