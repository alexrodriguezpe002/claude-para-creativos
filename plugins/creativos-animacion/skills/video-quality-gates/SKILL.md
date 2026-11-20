---
name: video-quality-gates
description: "Blocking quality gates for a HyperFrames podcast video — negative space measured on the rendered frame, mobile type floors, caption integrity (timed on the clip's own voice) and line breaks measured in a real browser, beat variety and pacing, mirrored exits, seek-safety and brand invariants. Run after every change to a beat or a caption array, and before showing anything to the user or opening the Studio. The scripts print numbers, not opinions; a FAIL blocks the work until it is fixed or the user decides otherwise — mechanical findings are fixed without asking, creative ones are asked with the frame — and \"The loop\" turns each recurring correction of the user into a rule this computer remembers (learned.py). Each client brings its own numbers and declared exceptions in `<client>-brand/references/gates.json`; a project that matches no profile is not measured (exit 2) unless GATES_CLIENT names one. Also a computer's setup: `run_gates.py --doctor` and video_config.py (folders, songs, language)."
---

# Quality gates

Seven checks, plus the framework's own check for clients that ask for it. Each one exists because the editor had to ask for the same correction
more than once, and each one prints a measured number instead of a judgement.

```bash
cd "<this skill's folder>/scripts"
python3 run_gates.py "<project-dir>"
python3 run_gates.py --doctor          # once per computer — is it ready? (installs what is per user)
```

**Any computer.** The scripts find everything from their own location — the
brands and `podcast-captions` are the sibling skills of this one, in
`~/.claude/skills/` on the owner's Mac or in the plugin's `skills/` folder
anywhere else — and keep this computer's own things in `~/.studio-video/`:
`config.json` (where the projects, the songs and the assets folder are, and the
language — `scripts/video_config.py`, asked once), `learned/` (The loop, 4) and `node/`
(the browser library). On Windows run `py -3` (or `python`) wherever this file says
`python3`; the scripts print UTF-8 and start Node's tools without cmd.exe.
`run_gates.py --doctor` checks Python and installs the packages the skills import, for
this user (Pillow, numpy, faster-whisper, fonttools + brotli for CLC, OpenCV for
`podcast-reframe`), ffmpeg (and runs the same-shot measure on a synthetic clip, to see
that this ffmpeg hands back the frames on both sides of a cut), Node 20+, HyperFrames,
the browser library and a browser, **a real transcription** of a sentence the computer
speaks itself (faster-whisper — the caption-timing model, downloaded the first time —
and HyperFrames' whisper.cpp, which on Windows may have to build itself), the reframe's
face models, the config, the sibling skills and the assets that git does not carry, and
says what is missing (`--no-install` only looks, `--no-transcribe` skips the speech test).
It also asks the own doctors of `podcast-snippet-select`, `podcast-rough-cut` and
`podcast-audio-clean`, only looking: a video started from the raw takes needs them (a WARN
names each one's `doctor --fix`; the rough cut's model is ~3 GB), the Descript export does not.
When HyperFrames cannot transcribe on a computer, `scripts/transcribe_fw.py <video>
[-d <project>]` writes the same `transcript.json` with faster-whisper (create the project
with `npx hyperframes init … --skip-transcribe`).

**The language of the messages** is per person: `lang` in the config (`en` for a new
user, `es` on the owner's computer; `video_config.py set lang en|es`, STUDIO_LANG for
one run). Only the words change — every code (`caption-late`), exit code, `##JSON##` key
and file the scripts read back is the same in both (`scripts/_lang.py`: `T(es, en)`).

| Gate | Catches | Needs a render |
|---|---|---|
| `check_build.py` | seek-safety, timeline overrun, sub-compositions, **the podcast abbreviation or the episode number on screen**; per profile: a missing background texture and coordinate crosses out of range (CLA's brand furniture), green as fill, a translucent beat ground, a bounce or overshoot ease, **colours and fonts outside the person's brand set**, `transformOrigin` mixed with `svgOrigin` | no |
| `check_hf.py` | the framework's own `hyperframes check` — clip contract, caption hard kills, layout, contrast — blocking, minus the codes the profile excuses with a reason; per profile: a caption "overlapping" a beat's text while hidden under that opaque beat is measured in Chrome (`measure_stacking.js`) and dropped with a note. Runs only when the profile asks (CLB, CLA) | a browser |
| `check_text_size.py` | text under the mobile floor, more than one type-size jump, clipped headline mask; per profile: **text under the floor of its role** (headline, takeaway line, primary label — a class on the block or on a container around it) | no |
| `check_text_fit.py` | **type that breaks on more lines than it was written for**, text clipped or escaping a card, wrapped lines left un-centred, a card with the background texture running through it — **measured in Chrome with the font loaded** | a browser |
| `check_captions.py` | **a card that appears after its words are said, or long before** and **a said word on no card without a declared rule** (both against the words measured on the clip's own voice — `word_timing.py`), fade instead of cut, flicker-length lines, gaps, sentence spill, dangling connectors, client spelling, **a card that outlives a camera cut** (cuts from the project's `cuts.txt` and scene detection; a jump cut of the same shot may be crossed, measured on the picture, only when splitting the card there would leave a hanging word or a flash), **a card that holds words said after a pause, or opens before the voice comes back** (pauses measured on the clip's audio), **a sentence starting lowercase**, **two physical lines measured in Chrome**; per profile: a caption colour other than the brand white, **a declared entrance** (the project's own tween calls against the durations, eases and offsets the brand declared), **the end of the speech before a fixed outro card** | a browser, for the width |
| `check_variety.py` | repeated device *or* repeated structure, too many beats, **a beat over 8s**, **under 5s of face between beats**, **a beat crossing a camera cut**, graphic before 5s, dead air, beat-window mismatch; per profile: **a beat crossing a camera cut, per format** (a two-host teaser and a one-host snippet differ), **the same ground on two beats of one project**, **counted series** (one per point, counted as one, every point present), back-to-back beats only under a **speaker PiP**, **a beat that leaves a moment before the end**, **a video that ends on a graphic**, **the same ground on two consecutive snippets** | no |
| `check_exits.py` | **a beat that cuts out instead of leaving the way it came in** (unless the brand declares a straight cut-out), elements that enter and never retreat, a stroke drawn on and never drawn off, a retreat that lands before the cut | no |
| `check_balance.py` | negative space, internal holes, horizontal centering, green coverage — **measured in pixels on the resting frame**; per profile: content told from the ground by colour distance (light grounds), **empty space under the last element**, the speaker PiP counted as mass vertically but not horizontally | yes (~40s/beat) |

Three of these gates need the clip itself. The caption width comes from
`measure_captions.js`, which opens the composition in Chrome at the frame's own
size and waits for the real font. The camera cuts come from two sources, merged:
the project's own `cuts.txt` (one time in seconds per line) and `ffmpeg
scene-detect` over the project's `<video>` at the profile's
`cuts.scene_threshold` (0.35 by default, CLA's speaker changes; cached per
threshold and per video in `.gates-cache/cuts-scene-<t>.json`). Merged, not
replaced, so a stale list never hides a cut the detector sees; the caption and
variety gates print how many came from each (`cuts.txt: 17 · scene>0.35: 0`),
zero included. When something is unavailable the gate says so as a WARN —
`cut-detect-skipped`, `cuts-list-unreadable`, `width-not-measured` — and that is
never a pass.

**Pauses come from the clip's own audio** (since 2026-10-03), for the caption
rule *what is said after a pause opens the next card* (the editor, CLB ep3): the RMS
level in 10 ms windows under a floor taken from the clip itself — halfway
between its quietest tenth and its median, never above 18 dB under its loudest
tenth (`_common.voice_pauses`, cached in `.gates-cache/pauses.json`).
`silencedetect` lists 0–2 pauses per CLA ep4 snippet under the room tone and the
bed, and the word gaps of `transcript.json` cannot be used: whisper.cpp stretches
the word before a pause over it (CLB ep3 Snippet 2: 9 pauses of 0.40 s or more by
silencedetect on its clean voice, not one word gap that long). The RMS floor
finds 3 of 3 and 8 of 9 of CLB ep3's, and on CLA ep4 Snippet 4 nine flat plateaus
at −36 to −41 dB that silencedetect misses. `caption-holds-pause` (FAIL) is a
pause of `captions.pauses.min` (0.40 s) inside a card; `caption-opens-early`
(WARN) a card that opens more than `early_tol` (0.10 s) before the voice comes
back. A connector right before such a pause is not a dangling connector — the
gate prints which ones it let stand. The count is printed, zero included, and a
clip whose audio it could not read says `pauses-not-measured`.

**Measured on the clean voice when there is one, and said when it is not
enough** (2026-10-03). A music bed in the measured audio fills the pauses: CLA
ep4 Snippet 1's Premiere base (the bed is inside the video) shows 1 pause, the
clean voice of the same cut 4 — and three delivered cards hold those pauses. So
the measure takes, in order: a clean voice file in the project folder —
`voice.wav` (music-bed's input, the export's own audio) or a file named
`… VOICE.wav`, never a `MIX`, and only when it is as long as the speech (the
composition up to a fixed outro card, ±1 s; another length, or a file ffmpeg cannot
read, is skipped and said) — then the a-roll, then the `<audio>`. When the measured
audio still carries a bed — the clip's quietest tenth sits less than 3 dB under the
pause floor (`_common.PAUSE_BED_MARGIN`; CLA ep4's bases 0.5–2.2 dB, CLD ep1's teaser
0.4; CLD ep1's snippets 4.1 and 5.9; every clean voice of the regression set
6.2–27.3) — the caption gate warns `pauses-limited`: it can only have found fewer
pauses than there are, so put the clean voice in the project and measure again. A bed
far enough down to leave that tenth 4 dB or more under the floor can still break pauses
up without the warning; the clean voice is the cure there too. A Descript export, which
carries the clean voice, never needs it; the grouping script reads the same
pauses and says the same.

**Caption words are measured on the clip's own voice** (since 2026-10-03,
`scripts/word_timing.py`). The editor sent back the CLC ep1 S3 rebuild because *"some words
appear AFTER they are said, and it seems some words are MISSING"*: its cards were timed
by `transcript.json` — whisper.cpp small.en without DTW, whose times drift up to 1.5 s
inside a phrase — and no gate measured a card against the voice; the missing-word check
compared the captions with that same transcript, so a word it had missed or misplaced
could not be missing. Now the voice (the clean voice file, else the a-roll, else the
`<audio>` — the order of the pauses) is cut at its pauses and every stretch between two
is heard alone by faster-whisper (`captions.timing.model`, `small`, batched): a word can
only land where it is said, and every word is anchored to where the voice starts. Cached
per voice file in `.gates-cache/word-timing.json`; the grouping script reads the same
measurement; `python3 word_timing.py <project> --words` prints it (also the right source
for beat cues). Against it the caption gate fails **`caption-late`** — a card more than
`captions.timing.late_fail` (0.35 s) after its first word, or after the cut or beat exit
it has to wait for — and warns `caption-late-near` (from `late_warn`, 0.20 s);
**`caption-early`** / `caption-early-near` from 0.70 / 0.35 s before it (a card on a cut
and the video's first card open early by rule; a card opening inside a pause is
`caption-opens-early`); **`caption-missing-word`** — a word the voice says surely (p ≥
`missing_p`, 0.70, or heard by both the voice pass and transcript.json), on no card, that
no rule took out (filler, stutter, restart, under a full-frame beat, `~~by hand~~` in
`captions-text.txt`) — with `caption-doubtful-word` for a phrase heard unsurely and
`caption-unheard-word` for a card word the voice pass does not hear (both WARN: the
second pass decides). It prints how many cards it measured and their lateness (median,
p90, worst) and how far `transcript.json` is from the measured times, zero included;
without a readable voice it says `timing-not-measured`, without faster-whisper
`timing-unverified` (the transcript's words anchored to the voice: starts in a pause
fixed, drift inside a phrase not). Under a music bed the measurement has no pauses to anchor
to: late and early cards are then reported as WARN (`caption-late-bed`, `caption-early-bed`)
until the clean voice is in the project. The measure agrees with large-v3 run the same way
within 0.16 s on 91–93 % of the words of five clips (median +0.06 s); where they disagreed by
more, hearing the audio cut in two sided with the measure in every case checked. Calibration
on the delivered arrays: `podcast-captions`, "Calibration".

**A single-take video lists its cuts from the edit.** Jump cuts inside one take
barely move the picture: against the Premiere edits of CLB ep2 and CLB ep3, real
cuts scored 0.034–0.17 and frames with no cut up to 0.079, so no threshold lists
them — and the `cuts.txt` CLB ep3 shipped with, built from a hand-picked one, held
3 of 8 cuts in Snippet 1 and 11 of 17 in Snippet 2. On the owner's Mac, where the
clip comes out of Premiere, `scripts/cuts_from_prproj.py`
reads the V1 edit points of the sequence the clip was rendered from (it only
reads the `.prproj`), refuses to write when the sequence and the clip differ in
length, and writes `cuts.txt`. A profile with `cuts.require_list` (Client B,
CLE) turns a missing `cuts.txt` into `cuts-not-listed` — a WARN that
says the cuts went unchecked, instead of a silent pass.

**Which cuts a caption card may cross** (the editor, 2026-10-03, *"sí, para todos"*). Every
cut in the list is a boundary for a card except one kind: a **jump cut of the same shot**,
and only when splitting the card there would leave a single dangling word (a connector
at the end of the part before the cut, or a lone word that does not close a sentence)
or a flash (a part under `captions.min_dur_fail`, 0.5 s; `captions.cross_cut.flash_under`
changes it) — CLB ep3 S2 "And ask", CLE ep2 S2 "without | it being, like, really". A card
that spans several such cuts is judged cut by cut on the two segments next to each, so a
word left alone between two cuts justifies crossing both. A camera change or a change of
speaker is never crossed. Whether a cut is the same shot is **measured on the picture**, not read from the
list (which holds jump cuts and speaker changes alike): `_common.cut_kinds` decodes the
frames on both sides of the cut in one ffmpeg pass (96×96, gray; cached in
`.gates-cache/cut-shots.json`) and reads `static` (the share of pixels that changed by
8 levels or less), `edge_static` (the same over the outer ring: the background, not the
person) and `mean_diff`; the profile's `captions.cross_cut` says same shot when static ≥
0.30, edge ≥ 0.40 and change ≤ 0.20. Calibrated on 59 jump cuts (CLB ep2/ep3, CLE ep2
S1–S3: static 0.38–0.95, edge 0.47–1.00, change 0.007–0.131) against 11 camera and speaker
changes (CLA ep4, CLD ep1: static 0.04–0.08, edge 0.03–0.10, change 0.248–0.455): 59 of 59
and 0 of 11 read right. A cut that scene detection lists at the profile's threshold is a
camera change and is not measured. `check_captions.py` prints the three numbers for every
cut a card crosses — as a note when the crossing is allowed (it names why: «And ask»
would last 0.26 s, «without» would hang alone), as the evidence of the FAIL when it is
not (another shot, a split that was fine, or a card that only lingers or opens early
because every word is on one side of the cut) — and `caption-across-cut` keeps meaning
what it meant for everything else. Unreadable video = no measurement = every cut a
boundary, with the reason. `captions.cross_cut.same_shot: false` (a profile, or
`learned.py add <client> … --set captions.cross_cut.same_shot=false`) turns it off. It
cannot see a change of speaker inside one shot — keep the speaker labels in the caption
text, which split cards whatever the picture does.

**An edit made outside Premiere** — Descript's export is the starting video of
everyone who does not open Premiere (the other editor) — lists its cuts from the timeline
export of that same composition: Descript → Export → Timeline → **EDL** (CMX3600)
or **FCPXML**.

```bash
python3 cuts_from_edl.py "<timeline.edl | timeline.fcpxml>" --video "<clip.mp4>" --write "<project-dir>"
python3 cuts_from_edl.py --selftest        # builds an EDL (30, 29.97 NDF/DF, 25 fps) and an FCPXML from a known cut list
```

It reads the picture events in record order and prints each edit point — a **cut**
when the source jumps or the media changes, two cuts for a hole in the timeline
(where the picture goes to black and where it comes back), a **through-edit**
(skipped) when the source runs on, a **dissolve** when a transition joins two clips
(counted as a cut, once) — and writes `cuts.txt`. Like the Premiere reader it
**refuses to write** (exit 2) when the timeline and the clip differ in length by
more than `--tolerance` (0.1 s): a range was exported, or it is another version; and
when `--write` is not a folder. An EDL stores timecode and no frame rate, so
`--video` (or `--fps`) gives it; without either it assumes 30 and says so, and
29.97 / 23.976 / 59.94 mean the NTSC rates. Drop-frame timecode is read as such
whether it is written with `;` (`01:00:00;00`, `01;00;00;00`) or with plain colons
under the file's `FCM: DROP FRAME` line. CMX3600 has one picture track: an event
tagged `V`, `AA/V`, `A/V` or `B` is on it (the tag names the channels it carries);
`V2`… are extra tracks, read only with `--track`; audio-only events are left out. A
clip's name comes from `* FROM CLIP NAME` (`* TO CLIP NAME` for a dissolve), and two
events are the same media when the reel matches and, when both carry a name, the
name. A `01:00:00:00` start is taken off the times. FCPXML: connected clips
(`lane`) are ignored, also inside a `<clip>`; a clip with no `start` begins at its
media's start; `tcStart` is taken off; a file with several projects asks for
`--sequence "<name>"`. Premiere XML (xmeml) is named and refused: export EDL or
FCPXML. Confirm two or three cuts with a frame pair (`podcast-beat-plan` 2b). Tests
of every variant: `_prep-lunes/P6-tests/test_edl.py` (owner's Mac).

**The browser is real since 2026-10-01.** `measure_captions.js`,
`measure_beat_text.js` and `measure_stacking.js` (and the caption grouping's word
measure) load `playwright-core` and drive a real Chromium through one helper,
`scripts/_browser.js`. The library comes from this skill's own `node_modules` on
the owner's Mac, or from `~/.studio-video/node`, where `run_gates.py --doctor`
installs it — and where a gate installs it by itself the first time it finds none
(`GATES_NO_INSTALL=1` stops that); it is never in git. The browser is the installed
Google Chrome, else the Chrome HyperFrames downloads for its renders, else
Microsoft Edge (`GATES_CHROME=<path>` forces one). Before 2026-10-01 playwright was
not installed anywhere and every run, for every client, reported
`width-not-measured` / `fit-not-measured` — the two-line and wrap checks had never
actually run. If a WARN of that kind shows up again: `run_gates.py --doctor`.

`--fast` skips the browser measurements of caption width and text fit while
iterating, and the balance render **only while nothing that can move a pixel has
changed** since the last balance run, and that run passed: each balance run saves
a fingerprint of the composition (captions and Studio ids left out) in
`.gates-cache/balance-state.json`, and `--fast` re-measures whenever it differs —
one element taken out of a beat is enough (since 2026-10-03; before, `--fast`
skipped the balance gate without a word, exactly after the edits that needed
it). **Never hand off with `--fast`.**
`--keep` leaves the frames in `<project>/snapshots/` so they can be shown.
`--solo` limits the variety gate to one project instead of the whole episode.

## The loop — after every edit, and after every round of corrections

The skills correct themselves and remember: the gates run after every change,
what is mechanical gets fixed without asking, what is creative is asked with the
frame, and what the user asked once is written down where the next build reads
it. On a computer that is not the owner's, every fix or detour is also logged
for the owner, at that moment (6–7).

### 1. After every edit, however small — measure

```bash
cd "<this skill's folder>/scripts"
python3 run_gates.py "<project-dir>" --fast    # while iterating
python3 check_captions.py "<project-dir>"      # after a caption change: measures the width too
python3 run_gates.py "<project-dir>"           # before showing anything to the user
```

Moving or removing one element re-balances everything around it, which is the
check that used to get skipped: `--fast` re-measures the balance render **and**
the text fit by itself whenever the composition is not the one the last balance
run measured (captions and Studio ids aside). **Never hand off with `--fast`.**

**A FAIL blocks.** Do not continue past it, do not lower a threshold, do not
decide on your own that a finding does not matter, and never turn it into an
open question: it gets fixed, or documented against an explicit request of the
user that contradicts it, quoting their sentence. When the FAIL was caused by a
decision made here and not by a request of theirs, that decision is what is
wrong — revert it (CLA ep4: `too-many-beats` travelled two rounds as "pendiente
tu OK" for a beat nobody had asked for). **Report the gate state by pasting the
output**, never from memory or a partial run (CLA ep4 was reported "5/5 limpio"
while `variety` failed in all four projects).

### 2. Mechanical — fix it, re-run, move on

One obviously correct answer, no content decision inside it. No question.

| Finding | Fix |
|---|---|
| `caption-flicker`, `caption-brief`, `caption-dangling`, `caption-holds-pause`, `caption-two-lines`, `caption-overflow`, `caption-sentence-spill`, `caption-continuity` | re-run `podcast-captions/scripts/group_captions.py` (it keeps the text and the emphasis); what it cannot solve, by hand: merge with the neighbour, move the connector to open the next card, split at the pause, the period or the measured width |
| `caption-opens-early` | open the card where the gate says the voice comes back |
| `caption-entrance-mismatch`, `caption-entrance-missing` | the brand's declared durations, eases and offsets (`captions.entrance`) — copy them from its `captions.md`, never retime or cut the cards to quiet the gate |
| `caption-into-outro` | close the last card where the outro card starts |
| `caption-across-cut` | close on the cut, open the next card on it — re-run the grouping script, which already lets a card cross a jump cut of the same shot when splitting it would leave a hanging word or a flash (a camera or speaker change is never crossed) |
| `caption-lowercase-start`, `caption-lost-period`, `vocabulary` | the capital, the period or the spelling, from the transcript and the brand's vocabulary |
| `caption-late`, `caption-late-near`, `caption-early`, `caption-early-near` | re-run `group_captions.py`: it opens every card on its first word's measured voice; a card that still opens late waits for a cut or a beat — say which |
| `caption-missing-word` | put the word in the text and re-run the grouping script (it adds what the voice says surely by itself) — or, when it is left out on purpose, write it `~~like this~~` in `captions-text.txt`; never quiet it by editing `transcript.json` (before 2026-10-03: `caption-missing-words`, against transcript.json) |
| `caption-doubtful-word`, `caption-unheard-word` | `second_pass.py` (strongest model here): a word it hears goes in, a card word nobody hears comes out |
| `timing-not-measured`, `timing-unverified`, `caption-late-bed`, `caption-early-bed` | the clip's clean voice in the project (`voice.wav`) and faster-whisper (`run_gates.py --doctor`) — until then the card times are unverified |
| `caption-overrun` | end the last card at the video's end |
| `caption-colour`, `off-palette`, `off-brand-font`, `forbidden-ease` | the brand's white, token, face or ease |
| `text-below-floor`, `text-below-role-floor` | raise it to the tier it belongs to (the role floor is the brand's: headline, takeaway line, primary label) |
| a missing texture or crosses (brands that have them) | the recipe the brand maps to that device |
| `onUpdate`, `repeat:-1`, an unpinned `fromTo`, `beat-window-mismatch` | the safe pattern; `data-start` matching the timeline |

### 3. Creative — stop and ask, with the frame

Anything where the fix changes what the viewer sees or what a beat says: which
beat to cut when two share a structure, which of two beats on the same ground
(`ground-repeat`) changes it, whether a layout is recentred or redesigned, whether
a device still fits, a caption that can only be fixed by choosing which words to
lose.

1. Re-run with `--keep` so the frames land in `<project>/snapshots/`.
2. When the finding is about one region, crop it:
   `npx hyperframes snapshot . --at <t> --zoom "<selector>" --zoom-scale 3`
3. Send the frames, captioned with the measured numbers — "margen superior 219px
   vs inferior 545px".
4. When there is a fix worth seeing, apply it in a copy, snapshot that too, and
   send **before and after** side by side. A comparison beats a description.
5. Then ask, prefixed 🔔, recommended option first, each option naming what it
   does to the frame.

Only after the user answers does the work continue. If they say to leave it, say
so in the final summary — their call closes the gate, not yours.

### 4. After a round of the user's corrections — correction → rule

1. **Apply what was asked, and nothing else.** When their change turns a gate
   red, do not make a second, unrequested change to turn it green: document the
   FAIL against their words, or ask with the frame (CLB ep3 S1: asked to remove
   the PiP from the last beat, the build also pulled the beat out 2 s early, and
   that cost a round).
2. **Sweep.** The same defect elsewhere in the video, the batch or the episode
   gets the same fix (CLA ep4: eleven two-line cards when one was pointed at).
   Re-run the gates.
3. **Classify each correction.**
   - **One-off** — about this video's content: a headline's words, a beat moved
     to the second it belongs to, a word of this transcript.
   - **Recurring, a rule** — the user says *always / never / from now on / in
     every video / for the next ones* (*siempre, nunca, de ahora en adelante, en
     futuros videos*); or it is about a property of the client's videos rather
     than one moment (a size, a colour, a timing, a count, a position, a style);
     or the same kind of correction comes up a second time — check the brand's
     `decisions.md` and `learned.py show`. The editor's CLB ep3 pause note (*"quisiera
     que tengas en cuenta para los siguientes captions en futuros videos"*) is
     recurring; *"la animación 1 debe irse al segundo 11"* is one-off.
   - Unsure: one short question — *"¿Esto vale solo para este video o para todos
     los de <cliente>?"*
4. **Write each recurring one down, once, the same day.**
   - **On the owner's computer** (`learned.py where` says `owner of the skills:
     YES`): into `<client>-brand/references/decisions.md` — the date, the user's
     words quoted, who said it — creating the file if the brand has none; its
     number into that client's `gates.json`; a fix with one right answer into the
     gate that would have caught it. Turning it into a new process rule still
     goes through `skill-retro`.
   - **On any other computer:**

     ```bash
     python3 "<this skill's folder>/scripts/learned.py" add <client> \
       --said "<the user's words, verbatim, in their language>" \
       --rule "<the rule, one imperative sentence a future build can apply>" \
       --area <captions|beats|plan|look|pacing> --where "<video, round>" \
       [--set captions.max_words_snippet=4]
     ```

     `--set` when the rule is a number the gates or the caption grouping read;
     it refuses a key no gate reads, a value of the wrong kind, or the value the
     brand already has. The file is `~/.studio-video/learned/<client>.md` — on
     Windows `C:\Users\<name>\.studio-video\learned\` — and the numbers go to
     `<client>.gates.json` next to it.
   - Tell the user in one line what was saved, as what, and where.
5. **Next time it is in force.** Every pipeline of the client reads it before
   planning, building or captioning (`learned.py show <client>`), and every gate
   run merges its numbers over the brand's and prints them in yellow —
   `LEARNED L-001 (2026-10-04): captions.max_words_snippet 5 → 4` (`APRENDIDO` in
   Spanish). A learned
   number the brand has changed since is flagged on the same line. Deleting the
   file (or `learned.py remove <client> <id>`) gives back the brand's numbers;
   `GATES_NO_LEARNED=1` ignores it for one run.

A correction that has to be asked twice is a skill bug.

### 5. Promote — the owner, with someone else's learned file

What another computer learned stays there until the owner of the skills decides.

1. Get that computer's `.studio-video/learned/` folder (one `<client>.md`, plus
   `<client>.gates.json` when it learned a number).
2. `python3 learned.py review "<their folder>/<client>.md"` — every entry, with the
   brand's value today next to each number.
3. For each entry:
   - **promote** — write it into `<client>-brand/references/decisions.md` (date,
     their words, who said it) and the number into `gates.json`; when a gate
     number changed, re-run the regression of "Client profiles" over copies; then
     `learned.py promote <client> <id> --file "<their folder>/<client>.md"`;
   - **keep local** — leave it: it stays in force on that computer only;
   - **reject** — `learned.py reject <client> <id> --why "<…>" --file …`.
4. Ship the brand change with the skills (shelf PR, with the owner's OK), send the
   reviewed file back, and on that computer, once the skills are updated,
   `learned.py prune <client>` drops what is promoted or already in the brand.

### 6. A fix or a detour on someone else's computer — log it, then go on

On a computer that is not the owner's (`learned.py where` → `owner of the skills:
no`), whatever goes wrong is fixed there, with the user — it does not wait for the
owner — and **written down at that moment, before going on, without asking**. The
owner reads it when he is back and decides what goes into the team skills. Log it
when:

- a file of a skill of the plugin changed, even one line;
- a skill was worked around: a step done by hand, a patch, another command;
- a gate or a script failed and was got past another way.

```bash
python3 "<this skill's folder>/scripts/learned.py" fix --skill <skill> \
  --failed-file "<its output, saved to a file>" \
  --cause "<why it failed>" \
  --change "<the files and what changed in them, or the step done by hand>" \
  --checked "<how it was verified: the command and its result>" \
  --team yes|no|decide --why "<one line: why it belongs in the team skill, or not>" \
  [--files "<a>, <b>"] [--where "<video, step>"] [--patch "<diff file>"] [--open]
```

- **The real output**, never a summary from memory: `--failed "<…>"` for a line or
  two, `--failed-file` for a log (colours stripped, the middle of a long one cut).
- `--patch`: the diff of each changed file (`git diff`, or `diff -u` against a copy
  taken before the edit). An edit to the installed plugin is lost at its next
  update; the patch is what the owner can apply.
- `--open`: not solved yet. `learned.py fix-update F-NNN --solved "<how>" --checked
  "<…>"` closes it.
- **A fix that goes to the shelf carries its entry in the same pull request:** before
  the commit, `learned.py fix-update F-NNN --plugin "<the shelf clone>"` writes it into
  the plugin's `FIXES.md` (at the plugin's root; the sync tools never touch it); with
  the pull request, `fix-update F-NNN --shelf "<link>"`, and `--merged` once merged.
- Tell the user in one line: `F-NNN logged for the owner — <what>`.

The log is `learned/fixes.md`, next to the learned rules (on Windows
`C:\Users\<name>\.studio-video\learned\`); `learned.py show fixes` lists it. Every
entry also rebuilds `WHAT-CHANGED.md` beside it: the one document for the owner —
what is still open, what is in the shelf, what is only on this computer, and the
rules learned from corrections (4). `learned.py report` rebuilds it on request
("make the report for the owner"); before the owner is back, the user copies the whole
`learned` folder into the Drive folder "the studio Video Skills — Assets" as
`learned-<name>`. On the owner's computer a fix goes straight into the skill: no log.

### 7. The owner, back — the fix log and the learned rules

1. Get that computer's `learned` folder (`learned-<name>` in the Drive folder) and
   read its `WHAT-CHANGED.md`, or rebuild it from the files, in your language and with
   each learned number next to the brand's value today:
   `python3 learned.py review "<their folder>"`. The fixes merged in the shelf are
   also in the plugin's `FIXES.md` (`git log -p` on it shows when each arrived).
2. For each fix:
   - **still open** — a bug the skills still have: fix it first;
   - **in the shelf** — `sync_from_shelf.py --diff` shows it: keep it (`--apply`) or
     undo it in a pull request;
   - **only on that computer, for the team skill (yes / decide)** — apply it to your
     skills (its patch, or what "Change" says), `sync_to_shelf.py`, a pull request;
   - then `learned.py promote fixes F-NNN --file "<their folder>/fixes.md" [--to
     "<skill file>"]`, or `learned.py reject fixes F-NNN --why "<…>" --file …`.
3. The learned rules: 5, above.
4. Send the reviewed folder back; on that computer, `learned.py prune fixes` drops
   what was promoted.

## Reading a result

```
FAIL balance  CLA ep1 Snippet 2-2
  FAIL [vertical-balance] beat-1 @25.15s: margen superior 219px vs inferior 545px (dif 326px, 17.0%)
       mover el bloque 163 px hacia abajo
  · beat-1 @25.15s · top 219 / bottom 545 · izq 84 / der 131 · hueco máx 234 · verde 1.3%
```

The `·` lines always print, pass or fail — they are the measurements to quote
when reporting, so a summary says "top 219 / bottom 545" and not "se ve bien".

`GATES_JSON=1` adds a `##JSON##` line per gate for programmatic use.

## Calibration

Thresholds are set against real approved work, not invented:

- Vertical balance tolerance 2.5% — the editor noticed a 51px difference on a 1920px
  frame (2.7%) and asked for it to be fixed.
- Internal gap fires at 25% of the content's own height — the case the editor rejected
  twice in CLA ep3 was a headline stranded 340px above 1242px of content.
- The 48px type floor is iOS body size once the frame is scaled to a phone.
- Both CLA ep3 Snippet 1 beats — the ones hand-balanced over three rounds —
  pass the balance gate. Beat 2 of CLA ep1 Teaser 2, the layout the editor singled
  out as good, measures 91/91.

If a threshold produces a finding the user overrules twice for the same reason,
that is a calibration bug: bring it up rather than quietly widening it.

Client B's cases (approved must pass, rejected must fail) are listed in
`clb-brand/references/decisions.md`: the balanced S1/S3/S5–S7 frames of CLB ep2
pass and the S4 panels (551 / 295px, after the editor asked to balance them) fail; the
empty-bottom limit sits between the approved 33% and the 37%+ of the 09-01
rejections; CLB ep1's emphasis-coloured captions and CLB ep2 S3's off-palette berry
fail. The structural fingerprint of `check_variety.py` could not separate CLB's
approved and rejected cases (it reads CLA's markup), so the CLB profile turns it
off and that check is manual at plan time.

## Client profiles

Every number and switch that differs by client lives in
`<client>-brand/references/gates.json` and is merged over the defaults in
`scripts/_profile.py`. The defaults are CLA's numbers. A profile is picked by
the project's path (`match.path_contains`, or the client's folder in this
computer's `~/.studio-video/config.json` — a Windows path matches the same
way) or forced with `GATES_CLIENT=<client>`; `run_gates.py` prints which one
measured the project. No gate names a client.

**No profile, no measurement.** A project whose path matches no profile, or a
`GATES_CLIENT` that names none, stops every gate with exit code 2 and
`SIN PERFIL DE CLIENTE`, listing the profiles that exist (since 2026-10-03).
Before that it was measured with CLA's numbers without a word — a scratch copy of
a CLB project, or a client with no `gates.json` yet, passed and failed against
another client's rules. Today every client but CLC has a profile (CLD an interim one,
`cld-brand`, which only renames CLA's furniture; its look and numbers wait for the
redesign). `GATES_CLIENT=default` asks for the
defaults on purpose and says so in the first line.

What a profile can set: the beat container id (`beat_id`, `beat_selector`); the
brand invariants (texture, crosses, green, ground, opaque beats, forbidden eases,
brand sets per person, `svgOrigin` check); type floors and the size budget, and
whether sizes are read in the browser; caption word band, durations, spelling,
the brand white, numerals written as figures, the seam tolerance, extra hanging
connectors (`connectors_extra`), an early end that a beat covers
(`early_end_ignores_beats`), the pause minimum and tolerance (`pauses`; `null`
switches the check off), the caption DOM's class names (`dom`), whether and how a card may cross a jump cut of the same shot (`cross_cut`) and the target
card length of the grouping script (`target_words_snippet` / `_teaser`); whisper.cpp's own token times instead of an even
spread over each segment (`transcript_tokens`); caps, first beat, beat length,
gaps, counted series, PiP runs, end rules, scheme rotation; where cuts come from
(`cuts.scene_threshold`, `cuts.require_list`); the ink test and
tolerances of the balance gate; the framework check, the codes it excuses, and
whether a caption hidden under an opaque beat is measured instead of reported
(`hf_check.caption_under_beat`).

**Declared exceptions and switches added for CLE (2026-10-03)** — each is written
once, switched by the client's profile, and has a neutral default, so CLA and CLB
measure exactly as before:

| Key | What it does | CLE | CLB / CLA |
|---|---|---|---|
| `captions.entrance` | the brand animates its cards: `{mode, in: {duration, ease, y_from}, out: {duration, ease, y_to}, applies_to: [snippet, teaser]}`. The caption gate reads the tween calls of the block that binds the cards (`tl.fromTo` or `tl.from` in, `tl.to` out) and checks them against it — **`caption-entrance-mismatch`** when a duration, ease or offset differs, **`caption-entrance-missing`** when the brand declares a side and the project cuts. While they match there is no `caption-fade` / `caption-animated-teaser`. An `in` or `out` left out means that side is a hard cut. | fade, in 0.25 s `expo.out` from y −14, out 0.18 s `power3.in` to y +10, snippet and teaser | `null`: hard cut (`caption-fade`; a CLA teaser's slide-in stays a WARN) |
| `captions.timing` | `{model, language, late_warn, late_fail, early_warn, early_fail, missing_p, doubtful_p, add_p, off}`: the words measured on the clip's voice (`word_timing.py`, faster-whisper `model` on each stretch between pauses) and the gates against them — `caption-late(-near)`, `caption-early(-near)`, `caption-missing-word`, `caption-doubtful-word`; `add_p` is the grouping script's (a word heard this surely that the text lacks is added). `CAPTIONS_TIMING_MODEL` overrides the model for one run | the defaults | `small`, `en`, 0.20 / 0.35 s late, 0.35 / 0.70 s early, 0.70 / 0.35 / 0.70, on (every profile, 2026-10-03) |
| `captions.cut_word_by_voice` | grouping only: a word that straddles a cut goes before it when the clip's audio is silent from inside the word to the cut and the word has voice before that silence | `true` | `false` |
| `captions.connector_comma_closes` | a connector followed by a comma, semicolon, colon or dash ("what's going on,") closed its clause: it does not hang — in the gate and in the grouping script | `true` | `false` |
| `captions.cross_cut` | `{same_shot, static_min, edge_static_min, mean_diff_max, flash_under}`: a card may span a jump cut of the same shot — measured on the picture, same shot when static ≥ `static_min`, edge ≥ `edge_static_min` and change ≤ `mean_diff_max` — when splitting it would leave a single dangling word or a flash; a cut scene detection lists, and any camera or speaker change, is never crossed. `same_shot: false` makes every cut a boundary; `flash_under` is the length under which a part is a flash (null = `min_dur_fail`, 0.5 s). The gate prints the numbers of each crossing; the grouping script treats such cuts as soft (cost 25) | on, 0.30 / 0.40 / 0.20 | on, the same numbers (default for every profile, the editor 2026-10-03) |
| `exits.cut_out` | the brand's beats leave by a straight hard cut with no retreat. A beat with no retreat is a note ("sale por corte, declarado por la marca"), not `beat-exit-hard-cut`; a beat that does retreat is still held to `beat-exit-partial`, the stroke drawn and never drawn off, and `beat-exit-early` | `true` | `false`: the mirror is the default |
| `outro` | `{id_re}`: the element ids of a fixed end card appended after the speech (`outro(?:-audio)?`); the earliest `data-start` among them inside the composition is the end of the speech, an id is matched whole. `caption-early-end`, `caption-overrun`/`caption-into-outro`, `end-flash`, "a beat that rides out with the video" and the grouping script's last card measure against where the card starts, not against speech + the card | `(?:outro\|cta)(?:-audio)?` (the 5 s outro, and the teaser's CTA card) | `null`: the composition ends with the speech |
| `text.role_floors` | `[{role, class_re, min, min_landscape?}]`: a floor per role on top of the general one. The element's own class or a container's inside the beat must match `class_re`; `text-below-role-floor`. Measured in the browser (`measure_beat_text.js` reports the classes of every container up to the beat) | headline `^head\d*$` ≥62, foot `^foot\d*$` ≥46, primary label `^primary$` ≥42 | `[]` |
| `variety.beat_across_cut` | one value for every format, or one per format — `{snippet: false, teaser: "detected"}`; `"detected"` counts only the cuts scene detection sees (a speaker change) and not the jump cuts listed in `cuts.txt`, which a two-host teaser lists too | snippet off (one host), teaser `"detected"` | `true` (CLA) / `false` (CLB) |
| `variety.ground_repeat` | two beats of one project never share a ground (`ground-repeat`; `ground-unread` WARN when a beat's ground cannot be read). With more beats than `ground_unique_up_to` (the brand's number of grounds) only two in a row may not; a beat whose ground cannot be read still counts as a beat and never makes its two neighbours "in a row" | `true`, `ground_unique_up_to` 3 | `false` |

None of these names a client. A brand that needs one writes it in its own
`gates.json`; `learned.py add … --set <key>=<value>` can set the scalar ones on
another computer.

**The window a beat is on screen** is what the timeline shows (`visible_start` /
`visible_end`, from `tl.set/to/from/fromTo` on the container), not the declared
`data-start` / `data-duration` — a container that declares the whole video and
enters with `tl.fromTo(…, {autoAlpha: 0}, {autoAlpha: 1}, T)` is read from T
(CLD's segments), and the caption gate treats a word as hidden under a beat only
inside that window.

**CLE's profile (since 2026-10-03).** Client E measures against its
approved CLE ep2 renders (`cle-brand/references/decisions.md`, "Gate calibration"),
and it is the first client to declare exceptions instead of passing through them:
captions that fade (`captions.entrance`), graphics that cut out (`exits.cut_out`),
a fixed 5 s outro (`outro`), a floor per type role (`text.role_floors`), a teaser
that watches speaker changes (`beat_across_cut`), grounds that do not repeat
(`ground_repeat`) and "on," closing a clause (`connector_comma_closes`). Before
those switches existed, the rebuilt CLE ep2 Snippet 2 (the "prueba de fuego") could
not pass: `caption-fade` on all 45 cards, `beat-exit-hard-cut` ×2 and a 5 s
`caption-early-end` were the expected reds. With them the gates read the two
decisions of the editor (2026-10-03, *"básate en los renders de Drive, esos son los
aprobados"*) as decisions: what remained was the one question that was a real
defect of the edit — `caption-dangling` on "without", a connector between two jump
cuts — answered the same day (the card crosses the same-shot cut: the rebuild is
`LIMPIO`, 8 gates), plus the usual WARNs. A project that drifts from the declaration still fails:
retime a fade, or turn it into `tl.set`, and the gate says
`caption-entrance-mismatch` / `caption-entrance-missing`.

**What this computer learned goes on top.** `learned.py add … --set <path>=<value>`
writes a number the user asked for into `~/.studio-video/learned/<client>.gates.json`
(`Path.home()`, the same on Windows; `STUDIO_LEARNED_DIR` moves it), and
`_profile.py` merges it over the client's profile last. `run_gates.py` lists
every learned number under the profile line, and each gate the ones it reads, in
yellow. Delete the file and the brand's numbers are back. See "The loop", 4–5.

**Adding a client:** write its `gates.json` with the numbers its approved work
supports (calibrate as below), then run every existing project of the client and
report what fails. Changing a default changes CLA — don't; give the new client
its own value instead. CLA ep4 is the regression set: its output must stay
identical after any change to the scripts.

**CLA's profile (since 2026-10-01).** The defaults stay CLA's numbers;
`cla-brand/references/gates.json` only switches on four extras, each chosen by
the editor after it was measured on and off over a scratch copy of CLA ep4:

- `connectors_extra` — Client B's list without "while". It found two real
  hanging connectors in delivered work: "…timeline of when" (Snippet 3) and
  "…is on" (Snippet 4). "while" was the one false hit: "for a while",
  a noun, in the Teaser.
- `transcript_tokens` — no finding changed on ep4. Of the twelve words that
  change side of a beat edge, five can be checked against a pause in the audio:
  the token time is right in four, and the one miss puts the word on the very
  frame the beat ends. Snippet 4's transcript has no tokens, so there it changes
  nothing.
- `early_end_ignores_beats` — drops Snippet 3's false `caption-early-end`
  (4.88s, all of it under beat-2).
- `hf_check` with `caption_under_beat` — without it, Snippet 2 fails
  `content_overlap` on caption #20 ("caught") hidden under beat-1 for 0.75s; the
  frames show only the beat. Only the two lint codes CLA's single inline file
  always raises are excused.

Left off: reading `column` only outside a `style=` in the structural
fingerprint — none of the 35 CLA beats the gates can read (ep1, ep3, ep4)
writes its layout inline, so it changes nothing.

CLA ep4 with this profile is the reference: hf-check PASS ×5 (Snippet 2 prints
the one dropped overlap); captions FAIL in Snippet 2 (`service`), Snippet 3
(`that · are` + "when") and Snippet 4 (13 words + "on") — the missing words are
the accepted ASR corrections, the two connectors are real and shipped; variety
FAIL in Snippet 2 (beat-1 9.12s, accepted) and exits FAIL in the Teaser
(accepted). Measure a copy, never the delivered folders, and force
`GATES_CLIENT=cla`: a copy's path does not match the profile, and without it the
gates stop with exit 2.

Re-measured on 2026-10-03 after the cut and profile changes: every verdict and
every finding identical; only the notes changed, to say where the cuts came from
— Snippet 4 has an empty `cuts.txt`, the others none, and scene detection finds
0, 1, 2, 0 and 5 cuts in Snippets 1–4 and the Teaser (the same cuts as before).

Re-measured again on 2026-10-03 after the pause check, the learned overrides and
the connector-before-a-pause exception: every gate's verdict identical in the 14
projects of CLA ep4, CLB ep3 and CLB ep2. Each caption gate prints how many pauses
it measured (CLA ep4: 1, 0, 0, 9 and 1). Snippet 4 adds `caption-holds-pause` to
its already failing caption gate: #24 "he mentioned, oh, I", #37 "some specs and
they" and #52 "But here's a little bit" hold pauses of 0.50, 0.47 and 0.57 s —
flat at −36 to −41 dB in the envelope, real, and three weeks older than the rule.
CLB ep3 changes by the pause note only. CLB ep2 (older than the rule too) adds S7
#17 "REFERENCE IT." holding a 0.41 s pause (FAIL) and three cards that open
0.16–0.64 s before the voice (S1 #90, S5 #10 and #40, WARN), and four of its
dangling connectors now stand because a measured pause follows them (S2 #27, S5
#13 and #39, S6 #87). The final line of a blocked run now says "preguntale al
usuario" and points to "The loop".

Re-measured a third time on 2026-10-03 after the CLE switches (declared entrance,
cut-out exit, outro, role floors, per-format `beat_across_cut`, `ground_repeat`,
comma-closed connectors, the plate padding and `cut_word_by_voice`) and after the
CLD items (`tl.fromTo` windows, `emphasis:`/`mode:` caption ids, the `font:`
shorthand): CLA ep4 ×5, CLB ep3 ×2 and CLB ep2 ×7 give the same verdict **and the same
lines** as before — 0 differences in 14 projects — and the caption grouping, run
dry over the same copies, gives the same 14 arrays. Two things the regression found
and fixed before they shipped: the first `_device` change read CLB ep2's older
`==== SEG 3 — RED FLAG #3 ====` comments as unnamed (10 → 25 beats), and the first
version of the cut-by-voice rule moved CLB ep3 S2's "Everyone" before the cut —
hence the profile key.

Re-measured a fourth time on 2026-10-03 after the portability pass (sibling skills
found from the scripts' own location, the per-computer config, Node and npx started
the Windows way, the shared browser helper, UTF-8 output): CLA ep4 ×5, CLB ep3 ×2,
CLB ep2 ×7, the CLE test rebuild and CLD ep1 ×3 give the same verdict in all 18
projects, both from the owner's skills folder and from a copy laid out as the
installed plugin (no `GATES_SKILLS_DIR`, the browser library from an empty home). The
only line changes: the `beat-too-long` hint now says "si el usuario pidió", and CLE
prints the three "on," cards its comma rule lets stand ("on" is back in CLE's
`connectors_extra`). The caption grouping, run dry over the same copies, gives the
same arrays — CLE's with its punctuated caption text; fed Whisper's raw words, with
no commas, it now keeps "going on" off a card's end, as CLA's list does.

Re-measured a fifth time on 2026-10-03 after the same-shot rule (a card may cross a jump
cut of the same shot — `captions.cross_cut`, measured in `_common.cut_kinds`; the caption
gate's step 10 and the grouping script rewritten around it): 24 copies — CLA ep4 ×5,
CLB ep3 ×2 and CLB ep2 ×7 (the regression set), the CLE test, CLD ep1 ×3, CLB ep3 ×2 and CLB ep2
×3 re-read with the cuts of their Premiere edit (the delivered `cuts.txt` of CLB ep3 held
3 of 8 and 11 of 17), and the CLE test with the editor's card — give the same verdict in 22. The
two that change are the intended ones: CLB ep3 S2 with the edit's 17 cuts (its delivered
`#22 "wastes your best moment."` and `#24 "And ask what the first"` cross jump cuts of the
same shot where splitting would leave a 0.49 s and a 0.35 s flash — `caption-across-cut`
FAIL → both accepted, with their numbers; BLOQUEADO → LIMPIO) and the CLE test rebuilt with
"without it being, like, really" as one card (FAIL → LIMPIO; under the old gate the same
array fails `caption-across-cut`). CLB ep3 S1 #12 (a card that lingers 0.10 s past the 12.83
cut, every word before it) and CLB ep2 S1 #30 (opens 0.04 s before the 23.31 cut, every
word after it) stay FAIL, now with the same-shot numbers and what to do; CLD ep1's teaser cards
over a camera change stay FAIL ("la detección de escena lo lista"). In the 14 projects of
CLA ep4, CLB ep3 and CLB ep2 no finding changed, and CLA ep4's eight speaker changes are
camera changes by scene detection and are never measured as the same shot; the only line
differences are 1 px of measurement noise (hyperframes 0.8.113 → 0.8.114 between the two
runs: the balance of CLB ep3 S1 beat 3, 320 → 321; a caption width, 1067 → 1068 once — 1067
again on re-running either version). The caption grouping, run dry over the 20 copies that
have a caption array, gives the same arrays in 18; the two that change are the two cards
above. Unit tests of the rule: `_prep-lunes/P5-tests/test_same_shot.py`.

Re-measured a sixth time on 2026-10-03 after the audit of everything above (P6: 20
fixes — `cuts_from_edl.py`, the grouping and its measure, `ground_repeat`, `tl.from`,
`opacity: 0.5`, the role floors, the pause source; tests in `_prep-lunes/P6-tests/` on
the owner's Mac): 25 copies — the fifth pass's set (the CLE test as it stands now,
with the editor's card) and P4's CLA ep4 rebuild ×2 — frozen skills of that morning against
the same copy with only the audit's files. 18 give the same verdict and the same lines,
2 change one note's wording (below), and 5 add one WARN and change nothing else: the
new `pauses-limited` on the bases that carry their music bed inside the video — CLA ep4
S1, S2, S3 and the Teaser (the quietest tenth 0.5–2.2 dB under the pause floor) and CLD
ep1's teaser (0.4); S4, whose bed sits 24.5 LU down, does not get it. No gate changes
status anywhere; the caption width limits (952, 1680, 940, 852, 900 px) are the same in
every line. Two notes change wording: the animated-teaser evidence names `tl.from`, and
CLE's role floors now count what they found — the CLE test marks no `primary` label, so
its 42 px floor never applied (the gate used to be silent about it). CLA ep4 S1 and the
Teaser measured with their clean voice next to them (`… VOICE.wav`): 4 and 2 pauses
instead of 1 and 1, and S1's cards #0, #3 and #14 hold three of them
(`caption-holds-pause`) — what P4 found by hand.
