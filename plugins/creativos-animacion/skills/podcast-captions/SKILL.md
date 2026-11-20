---
name: podcast-captions
description: The one caption process for every video client of the studio in HyperFrames — the bottom captions of a snippet or a teaser, inline in the same index.html and GSAP timeline. Holds every rule shared by all clients, written once — what is said decides the words and the cleaned text their spelling, times measured on the clip's own voice (every card opens with its first word; every said word is on a card unless a declared rule removed it), a second ASR pass for doubtful words, one physical line measured in Chrome with the real font, words per card, the 0.7 s minimum, hard cuts, punctuation, fillers and stutters, cuts and speakers as boundaries (a jump cut of the same shot may be crossed, measured), no dangling connector, nothing waiting after a pause, the layer — plus the grouping script and the gate. The look comes from the client's `<client>-brand/references/captions.md`. Loaded by clb-snippet-captions, cla-snippet-captions and the client orchestrators; use it directly for any client whose brand has a captions.md.
---

# Captions — the shared process

What is the same for every client lives here: the criteria. What differs — the
**look** — lives in the client's brand, in `<client>-brand/references/captions.md`
(face, weight, size, colour, plate or scrim, case, position and safe zone, words
per card, emphasis, declared exceptions), and its numbers in
`<client>-brand/references/gates.json` → `captions`. The editor, 2026-10-03: captions
of one line, with their word count and a size legible on a phone, plus the pause
and cut rules, are shared; each client keeps its own look.

The longer quotes of what someone says in an episode are made up for this kit, each one
showing the same case; the short fragments, the times and the numbers are the real ones.

## Before anything

1. Load the client's brand skill and read `references/captions.md` and
   `references/decisions.md` (when the brand has one).
2. Read what this computer learned for the client — rules the user gave once:

   ```bash
   python3 "<video-quality-gates>/scripts/learned.py" show <client>
   ```

   `<video-quality-gates>` is the `video-quality-gates` skill's folder and
   `<podcast-captions>` this skill's own folder — siblings. On Windows run `py -3`
   (or `python`) where the commands say `python3`.

   Every active rule there applies as if it were in the brand; where they
   disagree, the learned rule is the user's newer word. Numbers in it are already
   merged into the gates and the grouping script, and print as `LEARNED`
   (`APRENDIDO` when the computer's language is Spanish — `video_config.py set lang`).
3. Have the inputs in the project folder: `transcript.json` (Whisper on the exact
   video the project plays — its words, never its times), `cuts.txt`
   (`podcast-beat-plan` step 2b), the clip's cleaned text (below), and the clip's
   voice: the export's own audio, or a clean voice file next to it (`voice.wav`).
   faster-whisper measures the words on it (`run_gates.py --doctor` says whether
   this computer has it).

## The rules, in one list

1. **Inline, always** — same `index.html`, same `tl`, never a `captions.html`
   sub-composition: sub-compositions load into the same window and their
   `window.__timelines["main"]` overwrites the project's, killing every beat.
2. **What is said decides which words appear; the cleaned text decides how they
   are written; the times are measured on the clip's own voice** — never
   transcript.json's own times, which drift up to 1.5 s inside a phrase (CLC ep1
   S3, 2026-10-03), nor another transcript's (CLB ep1 raced up to a second ahead).
3. **A doubtful word gets a second ASR pass** — the strongest model on this
   computer — before it goes on screen, or comes off it.
4. **One physical line**, measured in Chrome with the font loaded — never by eye,
   never by word count. Split a card that does not fit; never shrink the type.
5. **Words per card** — the brand's cap; at least 3 unless it closes a sentence.
6. **At least 0.7 s on screen, never under 0.5 s.**
7. **Hard cut in and out** (`tl.set`), unless the brand declares an exception —
   in its captions.md for the reader and in its `gates.json` → `captions.entrance`
   for the gate, which then checks the project's tween calls against the declared
   durations, eases and offsets (CLE: fade in 0.25 s, out 0.18 s).
8. **A period ends the card**; punctuation follows how it was said; a sentence
   starts with a capital; the punctuation a card ends on, once the user set it,
   is theirs.
9. **Fillers out, stutters once**, every other word exactly once.
10. **A cut is a boundary**, and so is a change of speaker: the card closes on the
    cut, the next opens on it, and the first words after it are there. **One
    exception — a jump cut of the same shot**, which a card may cross when splitting
    it there would leave a single dangling word or a flash. Never a camera change,
    never a change of speaker ("The one cut a card may cross", below).
11. **No connector hanging** at the end of a card — it opens the next one (except
    before a measured pause, and — for a brand whose profile says so,
    `captions.connector_comma_closes` — when a comma closed the clause:
    "what's going on,").
12. **Never split a number from its word** — "round 2", "3 things", "90 days".
13. **Nothing waits on screen**: words said after a pause open the next card; a
    card after a pause opens where the voice comes back, after a cut on the cut.
14. **One card replaces the next** with no hole, except under a full-frame beat —
    whose words are left out.
15. **The last card holds 2 s** when nothing follows, never past the end of the
    video — or past where the brand's fixed outro card starts.
16. **The layer**: `#cap-layer` is a `clip` with its timing; its stacking is
    set by z-index and its place in the HTML matches it, and a caption group a
    beat covers on purpose says so.
17. **Legible on a phone**: the brand's caption size, never under its type floor.
18. **One report is a sweep**: re-derive the whole array, never patch the one line
    that was pointed at.
19. **Every card opens with its voice, and every said word is on a card**: a card
    shows when its first word starts (or on the cut, or as the beat leaves, when it
    has to wait for one), within 0.20 s; a said word stays off the cards only by a
    declared rule — filler, stutter, restart, under a full-frame beat, `~~by hand~~` —
    and the script and the gate print each one with its rule.

The reasons, the numbers and the how follow, in the same order.

## Text

**What is said decides which words appear; the cleaned text decides how they are
written** (the editor, 2026-10-03, on the CLC ep1 S3 rebuild next to their approved version:
*"some words are missing … the approved one had more words"*). The grouping script
compares the text with the words measured on the clip's voice ("Timing", below):

- a word the voice says surely — heard at p ≥ `captions.timing.add_p` (0.70), or heard
  by both the voice pass and transcript.json — that the text lacks is **added**, spelled
  as heard, and the report lists it under "agregadas";
- a phrase heard unsurely is **not** added — one sure word inside a doubtful phrase is
  not a word: after "the report" in CLC ep1 S3 three models hear "by Friday", "my
  Friday" and "buy fried eggs". It is listed as DUDOSA, the gate warns
  (`caption-doubtful-word`), and the second pass decides;
- a text word the voice pass does not hear stays, timed inside the voice between its
  neighbours, and is listed; when nobody hears it — the voice pass, transcript.json and
  the second pass — it comes out;
- a word said and left out on purpose that no automatic rule covers (a restart the
  speaker corrects, "Okay." alone) is written `~~like this~~` in the text: it never
  reaches the screen and the gate counts it as declared.

Every said word that does not reach the screen is printed with its rule: filler,
stutter, restart, under a beat, by hand. CLC ep1 S3's rebuild lost "who" (the approved
text had it; a cleanup that trusted two small-model passes took it out) and "you need"
(said 0.3 s before beat 2, timed inside it by the drifting transcript) — and no gate
saw either.

**The source of the words** is the brand's (its captions.md says which file):
CLB has the batch's cleaned transcript; CLA corrects the clip's own transcript.
Save the clip's part as plain text in the project (`captions-text.txt`). When
there is no cleaned transcript, start from the clip's own Whisper words and
correct them:

```bash
python3 "<podcast-captions>/scripts/group_captions.py" "<project>" --dump-text > "<project>/captions-text.txt"
```

Correct spelling, names, numbers and punctuation; never invent or swap words.
A phrase that reads odd or vulgar for no narrative reason is almost always a
phonetic miss ("I scream sales" → "ice cream sales", CLC ep2). Spellings come from the
brand's `vocabulary.md`, and the gate checks them. A speaker label at the start
of a line — `Jane Doe:` or `[00:12] Jane Doe:` — opens a new card and
is dropped. `*word*` marks an emphasis word, for a brand that has emphasis.

**A doubtful word** — `p < 0.5` in transcript.json, a word the voice pass heard
under `captions.timing.missing_p` (the DOUBTFUL — DUDOSAS — list of the report), a name, an acronym —
gets a second pass on its own audio before it is captioned:

```bash
python3 "<podcast-captions>/scripts/second_pass.py" "<project>" [--at 45.9,50.2]
```

It cuts ±3 s around each one and transcribes the piece alone, with no prompt, with
the strongest model this computer already has (large-v3, else medium, else small).
It decides the **word**, never the time (in CLB ep3 S1 it put "and" 0.75 s
early); the time is the voice pass's. When it hears nothing, noise or something prompt-like where the first
pass had words, those words were invented while the speaker restarted a
sentence: they are not captioned. A word fixed here is fixed in transcript.json
too, or the gate reports it missing. CLB ep2 shipped a misheard acronym; CLA ep4 found an
invented "of" (p = 0.37) this way.

**Fillers are not captioned** (the editor, 2026-09-10: *"Elimina de los captions las
palabras que son muletillas o que no llevan a nada, por ejemplo 'you know'"*):
`um`, `uh`, `erm`, `hmm` and the like, and `you know,` / `I mean,` used as a
parenthesis, come out — the grouping script does it, and the gate reports them
as dropped on purpose. Quotatives (`I was like, hey…`), `so`, `of course` and
`look` stay: they carry the speaker's voice. **Always out** (the editor,
2026-10-03: *a card never opens on a word that adds nothing*): `Okay` / `Okay.` and
`Well,` opening a sentence or a card — strike them in the text (`~~Okay.~~`);
`well` inside a sentence ("it went well") stays. By hand, when it carries nothing:
a restart the speaker
corrects ("a list, a menu") — the test is whether removing it changes what the
sentence says or how it sounds. Remove the comma that belonged to a filler with
it: `"But, you know, nobody asked…"` → `"But nobody asked…"`.

**A stutter is written once**: a function word said twice ("the the", "I I") and
a two- or three-word restart ("we were we were") come out. **A content word
said twice is emphasis and stays** ("much, much bigger"). The gate measures
what the voice says and forgives, by itself, a word said twice in a row, a restart
of two or three words — also with one word between ("the step that, the step you
skip", CLA ep4 S3) — and a function-word restart ("move on to the, to pricing",
CLB ep2 S1); any other said word left out by hand is written `~~like this~~` in the
text, or the gate fails `caption-missing-word`.

## The DOM — one shape for every client

The brand's captions.md gives the CSS; the structure is this one, and the gates
and the grouping script read it:

```html
<!-- after the <video>/<audio>; before the beats when they cover it (see below) -->
<div id="cap-layer" class="cap-layer clip" data-start="0" data-duration="<video duration>"
     data-track-index="<free track>"></div>
```

```js
// start/end are final numbers — no expression inside the array
const CAPTIONS = [
  { start: 0.22, end: 0.92, words: [{t:"Start"},{t:"with"},{t:"the"},{t:"basics"}] },
  // { t: "word", e: true } — an emphasis word, for a brand that has emphasis
];

const capLayer = document.getElementById("cap-layer");
CAPTIONS.forEach((g, gi) => {
  const el = document.createElement("div");
  el.className = "caption-group"; el.id = "cap" + gi;
  el.setAttribute("data-layout-allow-occlusion", "true");   // a beat covers it on purpose
  const text = document.createElement("div");
  text.className = "cap-text";
  g.words.forEach((w) => {
    const s = document.createElement("span");
    s.className = "cap-word" + (w.e ? " emph" : "");
    s.textContent = w.t;
    text.appendChild(s);
  });
  el.appendChild(text);
  capLayer.appendChild(el);
});
CAPTIONS.forEach((g, gi) => {
  tl.set("#cap" + gi, { autoAlpha: 1 }, g.start);
  tl.set("#cap" + gi, { autoAlpha: 0 }, g.end);
});
```

```css
.cap-word { display:inline-block; margin-right:.22em; }   /* the gap the measurement uses */
.cap-word:last-child { margin-right:0; }
```

- **`class="clip"` and the timing attributes on `#cap-layer`**, or the Studio
  places the caption track late (CLA ep2: "los captions aparecen desde el
  segundo 18").
- **Stacking is set with z-index, and the HTML order says the same thing.** The
  brand's captions.md says which layer is on top. Where opaque full-frame beats
  hide the captions (CLB, CLA), the beats carry the higher z-index and the caption
  layer is written **before** them: written after them, `hyperframes check`
  blames the beat's own text for the overlap with a caption hidden under it
  (measured on a copy of CLA ep4 S2, 2026-10-03: `content_overlap` moved from
  `#cap20` to `#b1-missed-label`). Where the captions stay over the graphics (a
  video that is mostly animation — Prospect P), the layer goes **after** the beats
  with the higher z-index: a caption layer with no z-index written before a
  full-frame beat is covered by it, and nothing reports it (2026-09-17).
- **`data-layout-allow-occlusion="true"` on every caption group** an opaque beat
  covers on purpose — `hyperframes check` then stops reporting the hidden
  caption's contrast and occlusion (CLB ep2). It does not silence a
  `content_overlap` with the beat's text: that one the caption gate settles by
  measuring the stacking (`hf_check.caption_under_beat`), and the grouping no
  longer leaves cards running under a beat.
- **`tl.set` at both ends** and nothing else, in the project's one timeline,
  before `window.__timelines["main"] = tl`. Caption groups are not clip elements,
  so `autoAlpha` is right here (on a beat container it is not). **A brand that
  declares an entrance** (`captions.entrance`, e.g. CLE's fade) writes it as the
  block of three calls its captions.md gives — `tl.fromTo(sel, {autoAlpha: 0, y: -14},
  {autoAlpha: 1, y: 0, duration: 0.25, ease: "expo.out"}, start)`, `tl.to(sel, {…},
  end - out)`, `tl.set(sel, {autoAlpha: 0, …}, end)` — with the numbers as literals:
  the gate reads them (`caption-entrance-mismatch`). The card times in the array do
  not change; the fade happens inside them.
- A brand with another DOM (its own class names) declares them in its
  `gates.json` → `captions.dom` = `{layer, group, text, word}`.

## The grouping script — the whole array in one pass

Write the DOM and the brand's CSS first; then:

```bash
python3 "<podcast-captions>/scripts/group_captions.py" "<project>" \
  --text "<project>/captions-text.txt" --write
```

It times the cleaned words with the words **measured on the clip's voice**
("Timing", below — never transcript.json's times), adds what the voice says surely
and the text lacks, lists what it heard unsurely and the text words it did not hear
("Text", above), drops fillers and stutters,
measures every word in Chrome **with the project's own caption CSS and font**,
takes cuts, beats and pauses as hard boundaries, and splits the rest with a
dynamic programme: one physical line, the brand's word cap, avoiding cards
under 0.7 s, hanging connectors, one-word cards, a number split from its word,
a subject split from its verb. Numbers come from the client's profile (and what
this computer learned). Emphasis already in the array is carried over to the
same words. `--explain` prints why each card was cut where it was. `--write`
keeps the previous array in `.captions-backup/`.

**Four inputs a text file can carry.** A speaker label at the start of a line
(`Jane Doe:`) opens a new card and is dropped. A `||` between two words forces a
card break there without a label — for a phrase the script would join and the
speaker's rhythm splits; written apart or glued to a word (`two||`), it never
reaches the screen. `*word*` marks an emphasis word. `~~words~~` are said and left
out on purpose: they never reach the screen, and the gate counts them as declared. A typographic apostrophe
(`don’t`, as Google Docs writes it) and Whisper's `don't` are the same word for the
script and for the gate.

**Where a cut falls inside a word.** The editor cuts inside the first word after a
cut, so a word that straddles a cut is the first one after it. Whisper also
stretches a word over the silence that follows it, so for a profile that asks
(`captions.cut_word_by_voice`, CLE) a word whose voice is entirely before the cut —
the clip's own audio is silent from inside the word up to the cut, and the word has
at least 0.08 s of voice before that silence — is the last one before it ("like,
*really*": CLE ep2 S2, voice 8.19–8.54, silence to the cut at 8.84). It is off for
CLB and CLA: CLB ep3 S2's "Everyone" straddles a cut that falls inside the pause
before it, with its voice after the silence, and must stay after the cut.

**The measured line is the text holder's content box**: the brand's plate drawn by
the holder's own padding and background (`max-width: 940px` with 44 px each side,
`box-sizing: border-box`) leaves 852 px for the words, and a group that is narrower
than the holder's max-width wins (the same plate in a group with 114 px of side
padding: 852 − 88 = 764). The room a group gives is measured with one word wider
than the frame inside it, so a group that shrinks to its text is read as all the
room it has, never as the width of the text it happens to hold. The grouping
script (`measure_caption_words.js`) and the gate (`measure_captions.js`) compute
it the same way and read the same number (checked on five layouts,
`_prep-lunes/P6-tests/test_measure_browser.py` on the owner's Mac, 2026-10-03; before, the two could
differ by 90–140 px and a shrinking group gave the script a 187 px line). A plate
drawn by `::before` (CLE) needs none of this.

It is a first pass, not the verdict: read its report (doubtful words, cards that
wait after a cut, cards it had to open early or close late), then the gate.
Checked on 2026-10-03 against delivered work — "Calibration" below.

## Grouping

**A period ends the card.** A new sentence never starts on the card that holds
the previous one's full stop.

**Rules first, with flexibility — timing above all** (the editor, 2026-10-03). Every rule here is
followed first. When following one would break the phrase, a single exception among many good
cards is accepted — a two-word card, a card a little under 0.7 s (never under 0.5 s: that flicker
always fails), a connector just before a beat: *one card that is "wrong" among many that are
right does not hurt the video*. The gate warns on a single hanging connector and fails from two.
**Timing is never the exception:** "lo más importante siempre va a ser el timing de las captions".

**No hanging connector.** A card never ends on a preposition, conjunction,
article or possessive (the gate's list plus the brand's `connectors_extra`):
that word opens the next card. Exceptions: "than"; a word carrying the
sentence's final period; and a connector followed by a measured pause of the
profile's minimum — what is said after the pause opens the next card, and the
speaker's rhythm wins (the editor, 2026-09-22: *"por como está hablando… queda
mejor"*). The gate forgives exactly that one and says so. A connector with
nowhere to go — it cannot close its card and a cut or a full stop keeps it from
the next — is left out rather than forced into a broken card (CLA ep4: "of",
"that").

**Never split a number from its word** — "round | 2" and "3 | things" read as
two ideas (CLB ep3).

**A cut is a boundary, and an input.** `cuts.txt` and scene detection at the
client's threshold, merged (`podcast-beat-plan` 2b; a single-take client lists
its cuts from the edit). The card closes exactly on the cut and the next opens on
it — no hole, not a frame later. A card that survives a cut sits on the next
shot; with two speakers it puts one person's words on the other's face, the most
visible caption bug there is (CLA ep4: 0.40 s of one speaker's line over the other's face).
**At a cut, measure the audio, not Whisper**: Whisper stretches the last word
before a cut, and the editor cuts inside the first word after one (49 of 51 cuts
in one workshop recording) — that word is captioned whole, on the new shot. A change
of speaker without a cut (labels in the text) is a boundary the same way.

**The one cut a card may cross — a jump cut of the same shot.** The editor, 2026-10-03,
asked whether a card may cross a jump cut of the same person when the alternative is
a flash (CLB ep3 S2: "And ask", 0.26 s between a full stop and a jump cut) or a word
left hanging (CLE ep2 S2: "without | a plan, like, really", the cut falling between
a connector and the rest of its phrase) — *"sí, para todos"*, every client. So:

- **When.** A card may span a jump cut of the same shot **only** when splitting it at
  the cut would leave a single dangling word (a connector at the end of the part
  before the cut, or a lone word that does not close its sentence) or a flash (a part
  under `min_dur_fail`, 0.5 s). With any other split available the card closes on the
  cut, as before: crossing is the last resort, not a way to build longer cards. A card
  that spans several such cuts is judged cut by cut on the two segments next to each
  (the card split at every cut it spans), so a word left alone between two cuts
  justifies crossing both. The number of seconds that makes a flash is the profile's
  `captions.cross_cut.flash_under` (null = `min_dur_fail`; 0.7 would also let a card cross
  to avoid a merely brief one).
- **Never** a camera change, never a change of speaker: those stay hard boundaries,
  `caption-across-cut` FAIL, whatever the card would leave.
- **Same shot is measured, not assumed** (`video-quality-gates/_common.py`,
  "Is a cut the same shot?"): the frames on the two sides of the cut, 96×96 gray, and
  how much of the picture did not change — `static` (share of pixels within 8 levels
  over the whole frame), `edge_static` (the same over the outer ring: the background,
  not the person) and `mean_diff`. Limits in the profile, `captions.cross_cut`: static
  ≥ 0.30, edge ≥ 0.40, change ≤ 0.20. On the 59 jump cuts of CLB ep2/ep3 and CLE ep2 the
  readings are static 0.38–0.95, edge 0.47–1.00, change 0.007–0.131; on the 11 camera
  and speaker changes of CLA ep4 and CLD ep1, static 0.04–0.08, edge 0.03–0.10, change
  0.25–0.46 — 59 of 59 and 0 of 11 read right. A cut that scene detection lists at the
  profile's threshold is a camera change without measuring. **Both the script and the
  gate print the three numbers of every cut a card crosses**; a clip with no video to
  read keeps every cut a boundary and says so.
- **The script** treats such a cut as *soft*: it no longer splits the stretch, and a
  card spanning one is legal only when `check_captions.crossing_reasons` (built on
  `split_reasons`) — the gate's own test — finds a reason for each cut it spans, at a cost of 25 (under a flash or a hanging connector, over a
  lone word). Which side of the cut a straddling word is on is decided by the one
  function both use (`check_captions.word_after_cut`). Its report says which cuts
  were soft, and for each crossing card the reason and the evidence.
- **The gate** accepts exactly that: a crossing card on a same-shot cut with a reason is
  a note with the numbers (`caption-across-cut` stays a FAIL when the cut is another
  shot, when the split would have been fine, or when every word of the card is on one
  side of the cut — it only lingers, or opens early: close or open it on the cut).
- **Off:** `captions.cross_cut.same_shot: false` in the profile (or
  `learned.py add <client> … --set captions.cross_cut.same_shot=false`) makes every cut a
  boundary again. The limits are numbers a client can recalibrate the same way.

What the measure cannot see: a change of speaker inside one shot (a wide two-shot with
no camera change) — the labels in the text are what split those, so keep them.

**Both examples were the drifting transcript** (measured on the voice later that day,
2026-10-03). CLE ep2 S2: "without" is said after the 7.17 cut — heard alone, 5.0–7.17 s
is "the rest of the team" and 7.17–9.0 s "without a plan like"; CLB ep3 S2: "And ask"
is said 54.26–54.66, after the 54.13 cut, and between "left." (53.58) and the cut there is
only silence. With the voice's times neither card needs to cross. The rule stands — it is
the editor's — the script simply finds fewer cases; say so when one appears.

**A card is on screen for at least 0.7 s, never under 0.5 s.** Under 0.5 s it is
2–3 frames: CLA ep1 shipped "it." for 0.11 s. A shorter card merges with its
neighbour. When it cannot (a cut or a full stop on both sides), the script opens
it into the gap after the previous word (never before that word ends) and, still
under 0.5 s in continuous speech, closes it up to 0.25 s later — the gate then
reports what is left.

**A sentence starts with a capital — two sweeps over the whole video**: card
against card, and every caption word against transcript.json for periods the
caption lost (`caption-lost-period`). The one legitimate lowercase opening: the
sentence began behind a full-frame beat. Punctuation follows how the line was
said: a list said with falling intonation is separate sentences, or at least
commas (the editor, CLA ep4). **The punctuation the user gave a card is theirs**:
correct spelling, never turn their full stop into a comma (on one long talk: 22 of 26
suggestions accepted, the 3 rejected were all that).

## One physical line, measured

```js
await document.fonts.load('<weight> <size>px <family>');
await document.fonts.ready;          // plus ~300 ms — a fallback face measures narrower
```

The script and the gate both measure in Chrome with the project's CSS: CLA ep1's
first pass, measured before the font arrived, shipped 44 two-line cards of 106.
`caption-two-lines` and `caption-overflow` block; `caption-near-limit` warns
within 60 px. **When a card does not fit, split it** — the time boundary is the
real timestamp of the word that opens the second half, never a fraction of the
duration (that drifted 0.42 s in CLA ep1 v2 and came back as "overlapping
words"). `width-not-measured` is a WARN, never a pass.

## Pauses — nothing waits on screen

The editor, 2026-10-01, on CLB ep3 S2 ("FOR WEEK 1, AND YOU"), for every video from
then on:

> antes de pronunciar esas palabras, ella hace una pausa. Entonces, me parece
> visualmente más placentero que esas palabras estén en la siguiente línea,
> porque si no, esas palabras están en la misma línea esperando a ser
> pronunciadas… quisiera que tengas en cuenta para los siguientes captions en
> futuros videos.

1. **Words said after a pause open the next card.** A pause of the profile's
   minimum (0.40 s) inside a card splits it, even when every word would fit.
2. **A card after a pause opens where the voice comes back**, never at Whisper's
   time: Whisper starts the word after a pause 0.15–0.35 s early (CLB ep3 S1,
   "and the plan").
3. **A card after a cut opens on the cut**, never before it (CLB ep3 S2, "Everyone
   on that call").

The pauses are measured on the clip's own audio — the RMS level in 10 ms windows
under a floor set from the clip itself (`_common.voice_pauses`) — and on the clean
voice when the project folder holds one (`voice.wav`, or `… VOICE.wav`): a base whose
audio already carries a music bed hides most pauses (CLA ep4 S1: 1 found under the
bed, 4 on the clean voice), and the gate then warns `pauses-limited`. Not
silencedetect, which lists none under CLA's room tone; not the word gaps of
transcript.json, which whisper.cpp fills (CLB ep3 S2: nine pauses of 0.40 s or
more, not one word gap that long). The gate checks both rules
(`caption-holds-pause` FAIL, `caption-opens-early` WARN) and prints how many
pauses it measured, zero included.

## Timing — every card opens with its voice

**The times come from the clip's own voice, never from transcript.json** (the editor,
2026-10-03, on the CLC ep1 S3 rebuild: *"some words appear AFTER they are said"*).
`transcript.json` is whisper.cpp small.en without DTW (`hyperframes transcribe`):
right words, drifting times. On CLC ep1 S3 the transcript of the clean voice and the
one of the same cut with its music bed disagree by up to 1.5 s on the same word, the
rebuild timed by the first one showed cards up to 1.86 s after the voice, and the
same drift put "you need" (said 0.3 s before beat 2) under the beat, so it was left
out. So `video-quality-gates/scripts/word_timing.py` measures every word:

1. the voice — a clean voice file in the project, else the a-roll, else the
   `<audio>` — cut at its pauses (10 ms RMS under the clip's own floor, the floor of
   the pause rule);
2. every stretch between two pauses heard **alone** by faster-whisper
   (`captions.timing.model`, `small`), so a word can only land in the stretch where it
   is said: which side of a pause a short word is on is decided by what each side
   says ("that's the plan. | And the plan", CLB ep3 S1 — a whole-clip large-v3 pass
   put "and" before the pause, each side heard alone puts it after, where the editor had
   placed the card);
3. where a word seems to run across a short silence inside a stretch (0.06–0.15 s:
   too short to split a stretch, since a stop inside a word can be that long), the
   stretch is heard again in two pieces cut at that silence, and the pieces win only
   when they hear the very same words — a cut inside a word would change them (CLC ep1
   S3: "… | there's", 0.11 s apart, was timed 0.5 s early inside one stretch;
   "labor | talent" and "goes | to bring" likewise, each checked by hearing the two
   sides alone);
4. every word anchored to the voice: no word starts in a silence, the first word of
   a stretch starts where the voice starts.

It is cached per voice file in `.gates-cache/word-timing.json`; the grouping script
and the gate read the same measurement, and
`python3 "<video-quality-gates>/scripts/word_timing.py" "<project>" --words` prints
it — **use it for beat cues too**. Without faster-whisper the transcript's words are
anchored to the voice instead (a start in a pause and a word across a pause are
fixed, the drift inside a phrase is not); the report and the gate say so
(`timing-unverified`); under a music bed it cannot anchor to pauses and the gate only
warns (`caption-late-bed`) — put the clean voice in the project. Checked 2026-10-03
against large-v3 run the same way: 91–93 % of the words start within 0.16 s of it on CLC
ep1 S3, CLB ep3 S1/S2, CLA ep4 S1 and CLE ep2 S2 (median +0.06 s, the small model a touch
later), and where the two disagreed by more, the audio cut in two sided with the
measurement in every case checked ("there's", "talent", "to bring", "losing" in CLC ep1
S3).

**The tolerance — and why.** A card opens at its first word's measured start (after
a cut, on the cut; after a beat, as the beat leaves) and never early into a silence.
In fast speech the 0.5 s floor and "open with the voice" collide: three cards for 1.3 s
of "Wait, so he just quit on the very first day?". Then the short
cards borrow from the one that closes the phrase, card after card, and none opens more
than 0.18 s after its word (`LATE_MAX`; it was 0.25 s for one card at a time — that
quarter second was the "appears after it is said").
The gate warns from 0.20 s late (`caption-late-near`) and fails from 0.35 s
(`caption-late`); early, it warns from 0.35 s and fails from 0.70 s (a card on a cut and
the video's first card open early by rule). 0.20 s is the first lateness the measure can
tell from its own spread; 0.35 s is about ten frames. The numbers are the profile's
`captions.timing` and per-client tunable — "Calibration" says what the editor's delivered
arrays measure against them.

Every card ends where the next one opens — `CAPTIONS[i].end === CAPTIONS[i+1].start`
within the profile's seam tolerance — so one line replaces the next with no blank
flash. The only hole is under a full-frame beat, whose words are left out (a word
said as the beat leaves is shown; "under" is measured with the voice's times, the
same test in the script and the gate).

**Treat one report as a sweep.** A pattern Whisper produces once it produces
everywhere: re-derive the whole array with the script instead of hand-fixing the
lines that were pointed at — in CLC ep1 a first pass fixed the 6 flagged points and
a second found 13 more of the same kind. Before handing over, count that every
word of the text is on exactly one card.

## The last card

Holds 2 s when nothing follows, but **never past the end of the video**
(`caption-overrun`: CLB ep2 S6 showed solid frames after its last caption). The
brand may cut it earlier (CLA teaser: at the burned-in CTA card). **When a fixed
outro card follows the speech** (the profile's `outro.id_re` names its clip — CLE's
5 s card), the last card ends where the card starts: the grouping script does it
(CLE ep2 S2 left the last card at 63.80 with the outro at 61.94), the gate warns
`caption-into-outro` otherwise, and `caption-early-end` / `end-flash` measure
against the end of the speech instead of reporting the card's 5 s.

## Gate

```bash
python3 "<video-quality-gates>/scripts/check_captions.py" "<project>"
```

After every caption change, and inside the full run before handing over. Against the
voice it prints how many cards it measured and how late they are (median, p90, worst),
and fails `caption-late` (a card more than 0.35 s after its first word), warns
`caption-late-near` (0.20–0.35 s), `caption-early` / `caption-early-near` (0.70 / 0.35 s
before it); fails `caption-missing-word` (a word the voice says surely, on no card, that
no rule took out) and warns `caption-doubtful-word` (heard unsurely: the second pass
decides) and `caption-unheard-word` (a card word the voice pass does not hear); with no
voice to measure, `timing-not-measured`, and without faster-whisper `timing-unverified` —
never a silent pass. A FAIL
blocks; the mechanical ones get fixed and re-measured without asking — re-run the
grouping script, it keeps the text and the emphasis — and anything that changes
what the viewer reads goes to the user with the frame (`video-quality-gates`,
"The loop"). At the end of a round of the user's corrections, each correction is
classified and the recurring ones are written down for next time (same section).

## Calibration — what the script does on approved work

Regenerated from scratch on copies on 2026-10-03 (same text, same `transcript.json`,
same cuts) and gated next to the delivered arrays:

| Clip | Same cards as delivered | Gate, regenerated | Gate, delivered |
|---|---|---|---|
| CLB ep3 S1 | 14 of 22, same 79 words | WARN: 3 brief, 1 near the limit | WARN (with its own cuts.txt); FAIL `caption-across-cut` with the edit's 8 cuts (#12 "of how much they put" lingers 0.10 s past the 12.83 cut, every word before it: still a FAIL, the card must close on the cut) |
| CLB ep3 S2 | 28 of 42; one word more ("about", said as a beat leaves) | WARN: 4 brief, 5 choppy | WARN; with the edit's 17 cuts, `caption-across-cut` ×2 until 2026-10-03, now accepted (see below) |
| CLB ep3 S2, edit cuts | 28 of 42 | WARN: 4 brief, 5 choppy. "And ask what the next" crosses the 54.13 jump cut — same shot (static 0.68 · edge 0.77 · change 0.036), and split there "And ask" would last 0.26 s. Before the exception: FAIL `caption-flicker` | the same card and #22 "skips your strongest point." (crosses 44.37: split there "skips" lasts 0.49 s, alone) — FAIL `caption-across-cut` ×2, both accepted since 2026-10-03 |
| CLE ep2 S2, flat text | 44 cards (45 before) | "without a plan, like, really" crosses the 7.17 jump cut — same shot (static 0.89 · edge 1.00 · change 0.016), split there "without" would hang alone; no caption FAIL. Before: "of the team without" hanging | FAIL `caption-dangling` on "without" alone (the editor's pick: one card) |
| CLA ep4 S3 | 14 of 39 | FAIL `caption-missing-words` (the stutter written once, as delivered) | the same, plus `caption-dangling` "…timeline of when" |
| CLA ep4 S1 | 10 of 31 — the other 38 words sit under the two full-frame beats, where the delivered array kept cards nobody sees | WARN: 2 choppy, 1 near the limit | WARN: 3 brief, 5 choppy, 1 near the limit |

The cards that differ are split elsewhere inside the same phrase, with the
same words and times; the measured width, the floors, the cuts and the pauses
are all respected. What the script cannot know is phrasing taste: it may split
a compound a person keeps whole ("new | real estate | agents"), so read the
array once from top to bottom before handing over. It crosses a cut only as "The one
cut a card may cross" says — a jump cut of the same shot, measured, and a flash or a
hanging word otherwise — and never a camera change; where neither works (two cuts 0.3 s
apart with a camera change between them) the gate's FAIL goes to the user with the
frame. Re-run dry over the 20 regression copies that have a caption array in the shared shape
(CLA ep4 ×5, CLB ep3 ×2 and again with the edit's cuts ×2, CLB ep2 ×7 and again with the
edit's cuts ×3, the CLE test fed its text without forced breaks) the arrays are identical
to the previous script's in 18; the two that change are the two cards above (CLD ep1's
three have no such array).
Emphasis already in an array is carried over (CLA ep4 S3: 10 of 10 words).

### Timing against the voice — calibration (2026-10-03)

Measured against a reference made the same way with large-v3 (another, larger model than
the process's `small`), on the clean voices; lateness = card shown − first word's voice
(median / p90 / worst), and the cards more than 0.35 s late:

| Clip | Delivered array | This process, same words (dry, on copies) |
|---|---|---|
| CLC ep1 S3 | approved 31/8: −70 / +210 / +455 ms, 1 — but 15 cards over 0.35 s *early*; the rebuild the editor sent back: +40 / +512 / **+1870 ms, 11**, "you need", "who" and "by Friday" missing | v2: +55 / +152 / +375 ms, 1 (*) — no said word missing |
| CLB ep3 S1 | +60 / +543 / +690 ms, 3 ("yourself doing", "the job.", "Having your 3": the transcript drifted at the end) | +40 / +100 / +175 ms, 0 |
| CLB ep3 S2 | +2 / +260 / +910 ms, 3 ("on" said before the pause, its card after it) | +12 / +120 / +380 ms, 1 (*) |
| CLA ep4 S1 | +65 / +460 / +700 ms, 3 ("a podcast about …" 0.6 s late) | +10 / +100 / +150 ms, 0 |
| CLE ep2 S2 (P2's rebuild) | +10 / +310 / +485 ms, 4 | +35 / +105 / +500 ms, 1 (*) |

(*) The reference's mistake each time, heard by cutting the audio in two: "losing" starts
at 60.35 (CLC), "instead" after 22.40 (CLB ep3 S2), "with" after 59.2 (CLE).

**Every delivered array of the regression set fails `caption-late`** (1–5 cards each, 0.35–1.0 s),
except CLB ep2 S2 and S4 and the CLA bases whose audio carries the bed (`caption-late-bed`,
WARN). Each one checked by ear is really late — the same drift: CLB ep2 S1 "are guaranteed"
(1.0 s), S5 "high level." (0.75), S7 "broken down" (0.6), CLE "for" (0.5), CLD ep1 S2 "it was"
(0.7), CLA ep4 S4 "gotta get creative" (0.6). `caption-missing-word` on delivered work: CLB ep3
S2 "thinking about" (said as beat 4 leaves), CLE "where." (before beat 1) and "clear process"
(as beat 2 leaves), CLA ep4 Teaser "but" and CLB ep2 S7 "is", "we've" (left out by hand —
now they would be written `~~ ~~`); CLD
ep1's are false — its segments are not readable beats yet (`_pending.beat_id`), as before.

## A new client

Its brand gets `references/captions.md` — copy `references/brand-caption-style.md`
from this skill and fill it — and its numbers in `references/gates.json` →
`captions`. Nothing in this skill changes.

---

## Non-negotiables

- Inline, never a sub-composition; `#cap-layer` a `clip` with its timing, its z-index and HTML order matching what is on top
- What is said decides the words, the cleaned text their spelling; times measured on the clip's own voice (`word_timing.py`), never transcript.json's; doubtful words get a second pass
- Every card opens with its first word (≤ 0.20 s late), every said word on a card unless a declared rule took it out — printed with the rule
- One physical line, measured with the font loaded; split, never shrink
- `tl.set` in and out, unless the brand declares an exception
- ≥0.7 s per card, never <0.5 s
- A period ends the card; punctuation as it was said; the user's final punctuation stays
- Fillers out, stutters once, every other word exactly once
- Cuts and speaker changes are boundaries; no card across or after one — except a card that crosses a jump cut of the same shot (measured) because splitting it would leave a single dangling word or a flash
- No hanging connector, except before a real pause; no number split from its word
- Nothing waits on screen after a pause; a card after a cut opens on the cut
- The last card never outlives the video
- The brand's look, from its captions.md; nothing about a client written here
- `check_captions.py` passes, or the user decided otherwise

> Timing measured on the clip's own voice (`word_timing.py`) — approved by the user on 2026-10-03 after comparing the CLC ep1 S3 rebuild with their approved version ("el timing de CLC está muy bien").

## Lecciones del trabajo (en español)

- **Siempre centrados** en el cuadro (o en la ventana, si hay marco). Si a ese tamaño algo los pisa (la burbuja de
  cámara, un logo), se achican hasta que el más largo entre centrado; nunca se corren de lado.
- **En español:** el "re" de énfasis ("me re gustó") nunca cierra una tarjeta: va con lo que sigue. Los montos de
  plata llevan `$` aunque no se diga "dólares" ("una propuesta de $10.000"); las cantidades de cosas, no.
