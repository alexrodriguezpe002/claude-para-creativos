---
name: clean-captions
description: Word-by-word captions that read clean. One physical line (width measured in a real browser with the caption font), 2-5 words, at least 0.7 s, sentence-aware splits with no dangling connectors, a capital letter after a period, fixed spellings like "3D", and none of the speaker's disfluencies (no fillers, no "you know,"/"I mean," crutches, no stutter repeats, no false starts). Then checked against the real audio. Use it when building or fixing captions for explainer-vertical or Prospect P videos, for example when the user points at a caption error in them (lowercase after a period, a repeated word, "3d", a missing word). Not for Premiere SRTs (premiere-captions + subtitle-audit). The other clients have their own caption skills. Use it only in explainer-vertical or Prospect P work (or another project under OTHER PROJECTS), or when the user names this skill. For CLA, CLC, CLE, CLB, CLD or CLF, don't use it even if the same words come up, unless the user names the skill.
---

# Clean captions

Engine: `scripts/captions.py`. It works as a module (`build_captions`) and from the command
line (`text`, `measure`). Audio check: `scripts/check_vs_audio.py`. All of it was proven on
the Prospect P videos, where the editor corrected captions over five rounds; each rule below comes
from one of those corrections.

## The rules and why

| Rule | Why |
|---|---|
| **One physical line, always.** Line width = the sum of word widths **measured in a browser** with the caption font loaded, plus spaces, ≤ 892 px at 64 px on a 1080 frame. | fontTools and character counts both come out narrower than the render and let through lines that later wrap. |
| **2–5 words per card**, 4 is the comfortable length. | The editor's limit (17 Sept). |
| **≥ 0.7 s on screen.** | Under 0.5 s a card is a blink; one delivered "it." for 0.11 s and nobody saw it. |
| **A period closes the line**, and no lone word after it. | Sentences read as units. |
| **No card ends on a connector** (a, the, of, to, and, but, it's…), except at a sentence end; a phrasal verb is never split ("figure \| out"). | A card that ends on "the" leaves the next one limping. |
| **Capital letter after . ? !**, judged on the text **as shown**. | A cut can remove what came before: a clause that began mid-sentence appeared in lowercase after a period. |
| **Fixed spellings** (`CASE_FIX`, e.g. `3d` → `3D`). | The editor: "cada vez que digan 3d, la D tiene que estar en mayúsculas". |
| **No disfluencies.** Remove fillers (uh, um…), crutches ("you know,", "I mean," when they carry the comma), a lone "Okay.", "Well," opening a sentence, and a function word repeated back to back ("a, a" → "a"). Content repeats stay ("much, much bigger" is emphasis). | "Si Prospect P se equivocó o estuvo pensando qué decir, no tienes que repetir las palabras… aplica para todos los videos… error al hablar, tartamudear y muletillas en general." |
| **False starts are removed by hand** (`drop`): "options, a list, a menu" → "options, a menu"; "it's the timing of it" → "the timing of it"; "Sure, I mean, we, and we tried." → "Sure, we tried." | No rule catches them reliably; they need reading. |
| **Dangling punctuation is fixed by hand** (`text_fix`): "a far cheaper, version of, the tool" → "a far cheaper version of the tool". | Removing a filler leaves its comma behind. |
| **A camera cut closes the line**; a splice that only removed silence (`cont`) or joins one sentence (`joins`) does not. | A caption must never carry over the speaker switch. "And I" alone on a card came from closing at a silence splice. |
| **Each word belongs to the cut where it starts.** If it starts in a gap, it belongs to the next cut when ≥ 0.08 s of it falls inside. | Whisper stretches ends and starts words early after pauses; the old rule lost words next to cuts ("like", "that", "how"). |
| **The audio is not changed.** | On camera a stutter can't be cut; the caption is where it gets cleaned. |

The editor's own punctuation, when they edit captions themselves, is theirs; don't "correct" a
period of theirs into a comma.

## Workflow

1. **Build.** The engines call `build_captions(words, cuts, seg_map, widths, cont=…, joins=…,
   drop=…, text_fix=…, case_fix=…)` and get cards with per-word timing.
2. **Measure new words.** A word missing from the widths table is estimated, and the engine
   warns. Measure the missing ones in Chromium:

   ```bash
   C="${CLAUDE_SKILL_DIR}/scripts/captions.py"
   python3 "$C" measure --widths <brand>/caption-widths.json --font <brand>/fonts/<Caption-600>.woff2 \
       --from-html <project>/index.html
   ```

   The command re-measures a control word already in the table (DNA if present, otherwise
   the first one) and refuses to save if it doesn't match, which guards against a different
   font or weight. **New font:** start from an empty table and add `--space` the first time,
   because the width of a space is font-specific (15.68 px for Space Grotesk 600 at 64 px).
   **Needs:** node, the puppeteer-core that `npx hyperframes` installs under `~/.npm/_npx`
   (run any hyperframes command once), and a Chromium headless shell in
   `~/Library/Caches/ms-playwright`. The script says which one is missing. A capitalized word
   counts as a new word ("Writing" ≠ "writing"). Rebuild after measuring.
3. **Read the whole text, end to end, for every video.**

   ```bash
   python3 "$C" text <project>/index.html --widths <brand>/caption-widths.json
   ```

   It flags lowercase after a period, repeated words, fillers, crutches and words without a
   measured width. Then read it yourself for false starts. A missing word or a dangling
   connector is a systematic bug: sweep every card and every group boundary, not only the
   one the user pointed at.
4. **Check against the real audio:**

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/check_vs_audio.py" <project> [<project> …]
   ```

   How to read the differences:
   - **Expected:** fillers and crutches removed on purpose, and dropped false starts.
   - **Whisper's mistakes:** plural vs singular, "tourists" vs "tourism". Decide with a
     second pass on the short clip (large-v3), not with the episode transcript.
   - **Alignment ghosts:** difflib reports a word as missing that is on screen ("but",
     "all" on Prospect P). Grep the card before touching anything.
   - **Real errors:** a word heard and written nowhere, or written and never said. Fix those.

## When you finish

In Spanish:

- how many cards per video;
- what was cleaned (quote 2–3 before → after);
- words measured, if any;
- the audio check result, separating expected differences from real ones.
