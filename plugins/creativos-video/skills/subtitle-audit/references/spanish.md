# Spanish-specific traps

Every trap here was hit for real in an audit, not taken from a style guide. The example
phrases are made up to show each one.

## Whisper failure modes in Spanish

**English jargon inside Spanish speech gets mangled**, into things like `sprints` →
`es prints` or `backlog` → `baclo`. In the audit the subtitle file was right and the ASR
was wrong. **When the ASR output is a non-word or an absurd word, the subtitle usually wins.**
Do not "correct" a correct file toward a garbled transcription.

**Confidently wrong at normal speed.** A `llevo la …` read as `llego a la …` (as in
`llevo la cocina` → `llego a la cocina`) at 0.86 confidence, twice, and only resolved at
0.6×. High confidence is not truth. Slow every disputed spot.

**Phantom function words.** Whisper inserted a `Te` at the start of a sentence like
`Estoy hablando de los costos`. It vanished when slowed. Short unstressed words are where
it hallucinates.

**Unstressed syllables it cannot hear at all.** A slot like `los temas en los que ___
vamos a enfocar` returned nothing, `los`, and `los` again across four passes. Only `nos`
is grammatical. When ASR gives you noise in a slot, grammar decides — and say so in the
report.

## Voseo

The whole conjugation shifts and it is audible: `necesitás` (stress on the final syllable
+ final `-s`) vs `necesitan`. **Never assume voseo from the fact that the rest of the video
uses it.** A speaker can open addressing *ustedes* and switch to *vos*. In the source
audit the file had the *vos* form and the audio the *ustedes* one (like `necesitás` vs
`necesitan`), four passes at 0.95–0.99 — and it was the first line of the video.

Verify each one. Voseo forms to watch: `venís`, `tenés`, `podés`, `necesitás`, `sos`,
`vení`, `mirá`, `dejá`.

## Punctuation

**`¿` goes where the question starts, not where the sentence starts.**
`Y después, ¿quién paga el envío?` — and it needs the comma before it.

**Pronominal questions fall.** One like `¿Por qué cerramos tan tarde?` drops ~10% in pitch,
exactly like a statement. Only yes/no questions rise. Intonation can confirm a question
mark; it can almost never disprove one.

**Manner `como` takes no accent.** `lo armo exactamente como me lo piden` — modal, not an
indirect question. Compare `vamos a ver cómo armo el menú`, which *is* an indirect
question and does take the accent.

**Capital after a comma** is the most common real error in these files, usually where a
sentence was split across two cues and the second was capitalised out of habit.

**Sentence adverbs at the end take a comma:** `Es lo mismo que antes, básicamente.`

## Accents that go missing

`liderándolo`, `estás` (vs `estas`), `está`, `así`, `acá`, `más`, `qué/cuál/cómo/dónde`
in questions, `sí` affirmative vs `si` conditional. Enclitic pronouns are the worst
offenders: `liderandolo`, `ayudarla`, `ponerse` — check where the stress lands once the
pronoun is attached.

## Compounds written as two words

`sobreactúan` (not `sobre actúan`), `preestablecido` (not `prestablecido`),
`sinvergüenza`, `contrarreloj`. Whisper gets these right far more often than a human
typist does — trust it here.

## The speaker's own grammar errors

The four kinds that turned up in one 7-minute video (phrases made up):

- `los ingredientes ... con el cual cocinamos` → should be `con los cuales`
- `las recetas que estén probados` → should be `probadas`
- `que cocinen rápidos` → should be `rápido` (adverbial)
- `en consonancia de lo que pide el cliente` → should be `con lo que pide`

**These are never a silent fix.** They are a policy question: does the client want a
literal transcription of what was said, or correct Spanish? Ask once, apply the answer to
all of them, and list them together so the decision is made in one go.

Default until told otherwise: **leave them as spoken** and flag them. A caption that
contradicts what the viewer hears is its own kind of error.

## Anglicisms in the copy

English jargon the client works with (for example `copy-paste`, `feedback`, `brief`,
`deadline`, `render`, `sprint`, `backlog`, `daily`, `prompt`) is their working
vocabulary — keep it. The only decision is hyphenation and whether to italicise; match
whatever the rest of the file already does rather than imposing a rule.

Whisper deforms some words **every single time** and with confidence, like `backlog` →
`baclo` / `bac log` / `vaclo` (0.58), `Claude` → `cloud` / `loco`, `cocer` → `coser`
(0.93!), `desglosar` → `desglozar` / `deslizar`, `andamio` → `anda mío` (0.33). When the
ASR word is not Spanish or is absurd in context, the file wins — do not "correct" a right
file toward a garbled ASR, whatever the confidence says.

## Nicknames and first names

A nickname that sounds like an ordinary word is the usual trap: Whisper turns it into that
word or into nonsense (a made-up example: `Lucky` comes back as `laqui`, `luqui`,
`la qui`). The names and nicknames of each client's team go in that client's profile,
`premiere-captions/references/clientes.md`. A name the ASR cannot spell is **never** a
finding against the file: ask the editor once, write it there, and move on.

## Restart hallucination (the one that shipped four times)

The speaker begins a phrase, stumbles, begins again. Whisper transcribes the opening
twice and fills the first attempt with plausible text pulled from earlier in the talk
(made-up words, with the shape and roughly the confidences of the real cases):

```
vamos(1.00) a(0.75) revisar(0.81) el(0.00) presupuesto(0.53) anual.(0.94)
Vamos(0.67) a(0.00) revisar(0.91) estos(0.94) números(1.00)…
```
```
los(0.73) proveedores,(0.54) los(0.01) productores,(0.98)
```
```
Y(0.92) ahí(0.84) entra(0.00) el(0.31) cliente.(0.00) Y(0.14) ahí(0.82) se(1.00) arma(1.00)
```

"el presupuesto anual", "proveedores", "entra el cliente" are not in the audio. The
tell is the **repeated opening** plus **a p < 0.05 word inside the first attempt**. The
whole first attempt goes; the stutter is written once. A `pmin` filter on the group does
not catch it (a correct group fails on one soft word) and a short isolated re-read may
hallucinate too — read it with ±3s and no prompt.

## The speaker's `no?`

Many speakers close sentences with a rhetorical `¿no?` constantly. It is genuinely
said — the slowed audio confirms it every time. Whether it goes in the subtitle is the
client's call: some want them all removed. When removing, close the sentence with the
punctuation the editor uses elsewhere (a period) and list them under style, not under
mishearings.
