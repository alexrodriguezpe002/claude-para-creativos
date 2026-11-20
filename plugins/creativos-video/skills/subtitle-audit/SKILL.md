---
name: subtitle-audit
description: "Audit a subtitle/caption file (SRT/VTT) against the video's real audio and report every spelling, accent, punctuation and mishearing error before it reaches a client. Use whenever the user hands over a video plus its subtitle file and asks to check, proofread, review, verify or correct the subtitles — \"revisá los subtítulos\", \"chequeá la ortografía y la puntuación del SRT\", \"¿están bien los captions?\", \"quiero quedar bien con el cliente antes de entregar\", \"corregí el archivo de subtítulos\". Multi-pass: transcribes with faster-whisper, diffs word by word, re-checks every ambiguous spot on isolated and slowed audio, measures pauses and intonation, then splits the findings into objective errors and judgment calls. Writes a corrected copy without touching the original or its timecodes. Tuned for Spanish, voseo included; works for any language faster-whisper supports. Not for creating captions from scratch — that is caption-creator and the per-client caption skills."
---

# Subtitle Audit

Proofread an existing subtitle file **against the audio it claims to transcribe**. The
deliverable is a findings report the user can act on, plus a corrected copy of the file.

**The core discipline: one ASR pass is a hypothesis, never a verdict.** Whisper is
confidently wrong often enough that acting on a single reading will put errors in front
of a client. Every divergence gets adjudicated by a second and third pass before it
reaches the report.

## Scope

**In:** an existing `.srt`/`.vtt` + the video it belongs to. Spelling, accents,
punctuation, capitalisation, mishearings, dropped and duplicated words.

**Out:** creating captions from scratch (`caption-creator`, or the per-client caption
skills), caption styling/size/position, timing rebuilds, translation. If the user asks for
those, say so and point at the right skill rather than half-doing it here.

## Requirements

`ffmpeg`/`ffprobe`, Python with `faster-whisper` and `numpy`. On the owner's machine all
are installed and the `large-v3` model is cached. If a tool is missing, say which check
you cannot run — never let an unchecked item pass silently.

## Inputs

- **The video** — the actual render the subtitles ship with, not an earlier cut.
- **The subtitle file.**
- **The language/variant** if it isn't obvious. Ask only if it matters: the client's variant
  changes real decisions — voseo, for one (see `references/spanish.md`).

## Procedure

### Pass 1 — transcribe and diff

```
python scripts/srt_audio_diff.py --video <video> --srt <file.srt> --out <workdir>
```

Writes `audio.wav`, `asr.json`, `candidates.md` (every divergence with cue number,
timecode and ASR confidence) and `pauses.md`. Takes a few minutes for a 7-minute video.
`--reuse` skips re-transcribing if `asr.json` already exists.

Read `candidates.md`. **Do not write the report from it** — it is the to-do list.

### Pass 2 and 3 — adjudicate every ambiguous spot

```
python scripts/verify_spots.py --audio <workdir>/audio.wav \
    --spots "0.0-3.0:necesitas_vs_necesitan,236.6-241.0:llevo_vs_llego" \
    --tempos 1.0,0.6,0.5
```

Pass 2 re-transcribes each spot **isolated**, so the surrounding sentence can't bias the
model. Pass 3 repeats it **slowed**. Slowing is what actually resolves final `-s`,
unstressed syllables (`nos`/`los`/`las`) and short function words.

Send every divergence here, not just the low-confidence ones. In the session this skill
came from, a `llevo la …` read as `llego a la …` (as in `llevo la cocina` → `llego a la
cocina`) at 0.86 confidence at normal speed and corrected itself only at 0.6×. In a workshop
recording, a `hablar con …` read as `largo …` (as in `hablar con el equipo` → `largo el
equipo`) three times at 1.0× and resolved only at 0.6× — the subtitle was right and a
normal-speed ASR reading was wrong three times in a row.

Generate the `--spots` list from `candidates.md` instead of typing it:

```
python scripts/adjudicar.py --candidates <workdir>/candidates.md --spots-out <workdir>/spots.txt
python scripts/verify_spots.py --audio <workdir>/audio.wav --spots "$(cat <workdir>/spots.txt)" --tempos 1.0,0.6
python scripts/adjudicar.py --candidates <workdir>/candidates.md --log <workdir>/verify.log
```

`adjudicar.py` prints one block per divergence with the reading at each tempo and whether
the SRT word / the ASR word appears in each. It does not decide; it makes the decision
fast and traceable.

**Two failure modes of the isolated re-read, both seen for real:**

- **Too little context makes the model hallucinate.** With ±0.6s it returned a phrase
  that is not in the audio (the way `tener en cuenta` can come back as `la encuesta`), and a
  fix made from that reading introduced a duplicated word into the file. Use **at least
  ±1.0s** of context (`adjudicar.py --margen`, default 1.0). If a reading looks like a different sentence than
  the surrounding cues, widen the spot before concluding anything.
- **"Gracias." / "Excelente." / a chunk of your own `initial_prompt` is not a reading.** It
  is Whisper filling silence or a voice it cannot hear (audience, far microphone). Treat
  the spot as **unresolved** — the subtitle stands on the editor's ear — never as evidence
  that the words are not there. `adjudicar.py` marks these `SIN SEÑAL`.

**Restart hallucination.** When the speaker starts a phrase, stumbles and restarts,
Whisper hears the opening twice and fills the first attempt with plausible text from
earlier context, at p ≈ 0.00 on some word — made-up examples of the shape: `vamos a revisar
[el presupuesto anual]. Vamos a revisar estos…`, `los [proveedores], los productores`. Four
of these reached a client. If a divergence sits right before a repeated opening and contains
a p < 0.05 word, the SRT text is probably the hallucination and the whole first attempt
should go — a stutter is written once.

How to read the result:
- **All tempos agree, high confidence** → the ASR reading is right; the subtitle is wrong.
- **All tempos agree, the subtitle is also defensible** → weigh grammar. Say which.
- **Tempos disagree** → ASR cannot resolve it. Decide on grammar and **flag it to the user as
  a listen-check with the timecode.** Never present a coin-flip as a finding.

### Question marks — only if punctuation is in doubt

```
python scripts/verify_spots.py --audio <workdir>/audio.wav --spots "..." --pitch \
    --ref-question "279.5-280.1" --ref-statement "13.4-13.9"
```

Always pass a **confirmed question and a confirmed statement from the same video** as
references. Absolute Hz means nothing across speakers.

⚠️ **In Spanish, pronominal questions (qué / por qué / cuál / cómo) fall at the end
exactly like statements.** Only yes/no questions reliably rise. A falling contour is
never evidence against a question mark.

### Pauses — period vs comma

`pauses.md` classifies each cue boundary against **this speaker's own** gap distribution,
and flags `mid-word` when a cue splits a word (no pause there at all, whatever the
punctuation says).

**If it reports "No usable pause signal", believe it and move on.** A continuous speaker
can deliver seven minutes with no gap above 0.40s; then a 0.00s gap at one period is not
evidence, because *every* period in the file is 0.00s. It isn't selective. Decide on
grammar and say the timing was inconclusive — do not quote a gap as if it singled that
boundary out.

**Chained subtitles have no pause signal by construction.** When the editor chains cues
(each cue ends exactly where the next starts, which is how the editor builds them), every
boundary lands inside a Whisper word and `pauses.md` labels all of them `mid-word`. That
is a property of the file, not of the speech. **Do not try to recover a pause signal from
audio energy instead**: in a room with an audience the dynamic range is ~20 dB and an
energy threshold marks "silence" inside 14–34% of words. It fabricates pauses. Whisper's
inter-word gap under-reports them. Neither is usable; say so and decide on grammar.

### Structural check

Also scan for cues under **0.7s** (a flicker nobody can read), overlapping cues, and
cues whose text exceeds two physical lines. Report these separately from the text
findings — the user asked about text, so lead with text.

Also check, because each one shipped once:
- **Consecutive cues with identical text.** A stutter written twice. Confirm with
  `verify_spots` that the phrase is said once, then fuse with `scripts/quitar_duplicados.py`.
- **Leading/trailing spaces in a cue.** Premiere renders them as a horizontal offset.
- **A cue that starts with `%` or `$`**, or a number split across two cues (`30` / `% de…`).
- **A cue that ends in the colloquial emphasis `re`** ("me re" / "gustó"). The editor: "re" always
  shows on the same line as what follows. Fix by moving the boundary (2026-10-29).
- **A money amount without `$`** (Spanish): "una cámara de 5.000" → `$5.000`, also when
  "dólares" is not said, and "10.000 dólares" → `$10.000`. Counted things (personas,
  clientes, meses) never get `$`. The editor, 2026-10-29.
- **Rhetorical `no?` at the end of a sentence** — only if the client wants them removed (some
  do). The audio will confirm they are said; removing them is style, say so.
- Missing `¿` when the cue ends in `?` — but first check whether the `¿` sits in the
  previous cue of the same sentence, which is fine.

### Cuts — a word is read when it is said (edited videos only)

When the subtitles belong to a Premiere timeline and its cuts are available (`cortes.json`
from `premiere-captions/scripts/premiere_bridge.py cortes`), this is a **blocking gate**:

```
python scripts/cruce_cortes.py --srt <file.srt> --cortes <workdir>/cortes.json
```

**No cue may contain words from both sides of a cut.** A word goes with the side of the cut
where it is actually heard; if it is said after the cut it opens the next cue, even if that
leaves the previous one short. Otherwise the viewer reads a word that has not been said yet
(the editor, 2026-10-28: it happened ~38 times in one recorded class). Only real cuts count (material
removed); a clip split with nothing removed is not a cut. The one tolerated case — a cue
running past a cut only to reach 0.5 s on screen — prints as `aviso`, not a failure.
Exit 1 = do not deliver.

The same rule applies to every fix: a word recovered at a cue boundary next to a cut goes to
the side where it is heard **on the timeline audio**, and `quitar_duplicados.py` must get
`--cortes` so it never fuses two cues across a cut (it keeps the one after the cut).

## Classifying findings — this is the part that matters

The editor reviews before applying, and has said so explicitly. So every finding must say
whether there is anything to decide:

| Class | What it is | How to present |
|---|---|---|
| **Objective spelling** | Misspelling, missing accent, word split in two | Apply. Nothing to decide. |
| **Objective punctuation** | Missing period, capital after a comma, missing list commas | Apply. Nothing to decide. |
| **Mishearing** | The file says a different word than the audio | Apply, cite the passes that agree, give the timecode to spot-check. |
| **Judgment — sentence breaks** | Period vs comma where both read fine | Propose, mark as the editor's call, say what you based it on. |
| **Judgment — speaker's own errors** | Agreement (`recetas … probados`), `con el cual` for a plural, an adverb that agrees (`rápidos`) | **Never silently fix.** Ask: literal transcription or correct Spanish? |
| **Unresolved audio** | Tempos disagree | Flag with timecode as a listen-check. State it's a coin flip. |

**Two hard rules learned from the first run of this workflow:**

1. **Always give the exact before → after for every single change.** Never a category
   name alone. The editor asked "specify what the changes are" after getting a grouped summary
   — a table of counts is not reviewable.
2. **Separate "I checked this and it was fine" from "I changed this".** Those are
   different lists and mixing them wastes their review time. If a group has zero changes,
   say "zero changes, nothing to apply" up front.

## Writing the corrected file

Build `fixes.json`:

```json
[{"cue": 58, "old": "El orden ya viene prestablecido",
              "new": "El orden ya viene preestablecido",
              "type": "spelling", "note": "RAE: preestablecido"}]
```

```
python scripts/apply_fixes.py --srt <file.srt> --fixes fixes.json
```

Writes `<name> CORREGIDO.srt` beside the original. It **refuses** to write over the
source, preserves UTF-8 BOM and CRLF (Premiere and Descript depend on them), keeps every
cue number and timecode byte-identical, and asserts zero timecode drift.

`old` must match the cue exactly. Any mismatch is reported and **not** applied — this is
the guard that catches an off-by-one in cue numbers. **Report the applied/total count
verbatim from the script's output.** Do not state from memory that a change landed.

Then diff and eyeball it:

```
diff <(tr -d '\r' < original.srt) <(tr -d '\r' < "original CORREGIDO.srt")
```

If there are confirmed duplicate cues, run `quitar_duplicados.py` **on the corrected file,
after `apply_fixes.py`**, into a new name (with `--cortes` when the video is an edited
timeline: across a cut it deletes the earlier cue instead of fusing). It is the only step that changes timecodes (the
fused cue absorbs the duplicate's end time). Report it as its own line: "N timecodes
changed by fusing N duplicates" — never fold it into the apply_fixes count, which must
stay at zero.

**One line of the report is not negotiable:** "timecodes idénticos al origen: X de Y".
Compute it from the files, not from memory.

## Report format

```
AUDITORÍA DE SUBTÍTULOS — <archivo>
Método: <n> pases · <m> divergencias · señal de pausa: <sí/no>

🔴 ERRORES QUE CAMBIAN EL SENTIDO
  <timecode> «antes» → «después» — <evidencia>

ORTOGRAFÍA  (objetivo, nada que decidir)
  <tabla antes → después>

PUNTUACIÓN  (objetivo)
  <tabla antes → después>

CRITERIO — decidís vos
  <antes → después, con el porqué y la alternativa>

🔔 ESCUCHAR  (<n> puntos, el audio no se resuelve solo)
  <timecode> — qué escuchar exactamente

REVISADO Y CORRECTO  (cero cambios)
  <lo que se verificó y estaba bien>
```

Timecodes in `m:ss` so the user can scrub straight to them. Lead with anything that changes
meaning — one wrong word in a call-to-action outranks twenty missing accents.

Respond in Spanish. See `references/spanish.md` for the language-specific traps.
