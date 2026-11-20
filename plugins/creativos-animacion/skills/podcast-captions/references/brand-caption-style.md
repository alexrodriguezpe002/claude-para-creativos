# <Client> — caption style

<!-- Template for `<client>-brand/references/captions.md`. Copy it, fill every
section, delete these comments. The process and every shared rule are in
`podcast-captions`; this file says only what this client's captions look like
and where its words come from. Numbers the gates check go in the brand's
`references/gates.json` → `captions` as well (named in each section). -->

## Where the words come from

<!-- The file that holds the corrected text of each clip, and what to do when
it does not exist yet. E.g. "`<CLIENT> <NNN> Transcript Cleanup.md` at the batch
root — the clip's paragraph, saved as `captions-text.txt`" or "the clip's own
Whisper words (`group_captions.py --dump-text`), corrected against
`vocabulary.md` and the episode transcript". Speaker labels, if the text has
them, as `Name Surname:` at the start of a line. -->

## The look

| | Snippet 1080×1920 | Teaser 1920×1080 |
|---|---|---|
| Face, weight | | |
| Size | | |
| Case | sentence / uppercase | |
| Colour | | |
| Emphasis | none / one word per card in `<token>` on ~N% of cards | |
| Legibility | plate / scrim / shadow (values) | |
| Position | `bottom: …px`, side padding, `max-width` (= the line the measurement uses) | |
| Words per card | max N (gates.json `max_words_snippet` / `max_words_teaser`) | |

<!-- Gates: a brand whose captions are one colour lists it in
`captions.all_white` (no emphasis then); extra hanging connectors in
`captions.connectors_extra`; spellings in `captions.vocabulary`. The caption
size must stay over the brand's type floor for its frame. -->

```css
/* the exact caption CSS for this brand — the grouping script and the gate
   measure the page with it */
.cap-layer    { position:absolute; inset:0; z-index:<n>; pointer-events:none; }
.caption-group { position:absolute; left:0; right:0; bottom:<n>px; padding:0 <n>px;
                 text-align:center; visibility:hidden; }
.cap-text     { display:inline-block; max-width:<n>px; font-family:'<face>'; font-weight:<w>;
                font-size:<n>px; line-height:<n>; color:<c>; }
.cap-word     { display:inline-block; margin-right:.22em; }
.cap-word:last-child { margin-right:0; }
```

<!-- A brand whose DOM uses other class names declares them in gates.json →
`captions.dom` = {"layer": "#…", "group": "…", "text": "…", "word": "…"}. -->

## Stacking

<!-- Which layer is on top, and the HTML order that matches it: "beats
(z-index 50) cover the captions (z-index 40); #cap-layer is written before the
first beat" — the usual case for opaque full-frame beats — or, for a brand whose
captions stay over its graphics, the caption layer after the beats with the
higher z-index (podcast-captions, "The DOM"). -->

## Entrance and exit

Hard cut, `tl.set` only — the shared rule. <!-- Or the declared exception,
with who approved it, when, and where it applies (e.g. "teaser only: the line
slides up into a mask, 0.45 s, exit still a hard cut"), with the code. An
exception is written twice: here for the reader, and in the brand's
`gates.json` → `captions.entrance` for the gate, with the same numbers —
`{"mode": "fade", "in": {"duration": 0.25, "ease": "expo.out", "y_from": -14},
"out": {"duration": 0.18, "ease": "power3.in", "y_to": 10}, "applies_to":
["snippet", "teaser"]}` (CLE). The gate then checks the project's own tween
calls against it; a side left out of `in` / `out` is a hard cut. -->

## The last card

<!-- Holds 2 s after the last word, never past the end of the speech. A brand
with a fixed outro card after the speech declares its clip in `gates.json` →
`outro.id_re` (CLE: `(?:outro|cta)(?:-audio)?` — the outro and the teaser's CTA card); the
last card then ends where the card starts. A connector followed by a comma ("what's going on,") that should not count
as hanging: `captions.connector_comma_closes: true`. -->

## Cuts

<!-- Where this client's cuts come from: speaker changes seen by scene
detection (threshold in gates.json → `cuts.scene_threshold`), or jump cuts that
only the edit lists (`cuts.require_list: true`). A card may span a jump cut of the
same shot — measured on the picture — only when splitting it would leave a single
dangling word or a flash (`podcast-captions`, "The one cut a card may cross"); it is on
for every brand, and a brand that wants every cut to be a boundary says so in
`gates.json` → `captions.cross_cut.same_shot: false`, with the reason. -->

## Decisions

<!-- Pointers to the dated, quoted caption decisions in `decisions.md`. -->
