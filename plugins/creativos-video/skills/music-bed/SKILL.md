---
name: music-bed
description: "Choose and mix background music under a voice for social videos. Proposes 3-5 Epidemic Sound tracks per video (public catalog: BPM, mood, length, link) for the user to license, then mixes by loudness — voice -15 LUFS, music 10 LU under with gentle ducking, a 2.5 kHz carve, a limiter — in two passes, and checks with Whisper that no word is lost. Use it when an explainer-vertical, Prospect P or OTHER PROJECTS video needs music, when the user says the music is too loud, too quiet or \"casi inexistente\", or hands over Epidemic songs (ES_*.wav). Also the music of every Client B (CLB) snippet, of every Client E (CLE) snippet and teaser (22-25 LU under the voice, steady) and of every Client A (CLA) and Client C (CLC) snippet and teaser (CLA 17 LU, teaser 18.7, CLC 18; steady, equal-power fades, the teasers' CTA sound), since none of them passes through Premiere any more (2026-10-01 / 2026-10-03). For CLD or CLF, don't use it unless the user names the skill."
---

# Music bed

Script: `scripts/musicbed.py`. It works as a module for the video engines and from the
command line (`python3` on Mac, `py -3` or `python` on Windows; it needs ffmpeg,
numpy for `--level`, and faster-whisper for `check`). Proven on the three Prospect P videos (24 Sept 2026).

## What the editor wants (2026-09-24 — the rule for every bed)

- *"Quiero que la voz no sea opacada por la música, pero sí quiero que la música esté
  presente. No me gusta cuando la música está casi inexistente."*
- The editor suggested "voice -6, music -18 peak" and left the method open: "si existe una forma
  mejor, adelante".
- **The better way is loudness.** A mastered song has a much smaller peak-to-loudness range
  than a voice, so equal peak gaps don't sound like anything in particular. And Instagram,
  TikTok and YouTube normalize by LUFS.

## Choosing the songs (propose, the user decides)

1. **Understand each video before searching:** topic, emotional arc, pace of the speech,
   length. A reflective documentary piece is not a hype reel.
2. **Search Epidemic Sound** (public endpoint, no login) with 2–4 different phrasings per
   video. Mix mood words, genre and use:

   ```bash
   M="<this skill's folder>/scripts/musicbed.py"
   python3 "$M" search "reflective hopeful cinematic piano documentary" --min-length 90 --limit 10
   python3 "$M" search "curious minimal electronic pulse" --bpm 80-110 --min-length 90
   ```

3. **Filter:**
   - no vocals (they fight the voice);
   - length at least the video plus the tail (≥ 90 s is a safe floor);
   - no big drops or builds where the key line lands;
   - energy that matches the video.
4. **Tempo:** Epidemic tags some tracks at double tempo (salsa, mambo, guaracha: a 99 BPM
   track shows as 198). The script prints the half-time value next to anything over 140;
   judge with your ears, not the tag.
5. **Present 3–5 options per video:** title, artist, why it fits (one line), BPM, energy,
   length, and the link `https://www.epidemicsound.com/track/<slug>/`.
   - You can download the low-quality preview to check it (`preview <slug> --out x.mp3`).
   - The file that goes in the video is the **WAV the user downloads from the team's
     Epidemic account** (`ES_<Title> - <Artist>.wav`). That is what keeps the license clean.
   **If the search endpoint stops answering** (it is the public site's, not a documented
   API): search on epidemicsound.com in the Browser pane (no login needed to browse), or ask
   the user for 2–3 references they like and search by artist.
6. **The user's downloads:** when they say they downloaded songs, look in their Downloads
   folder (`~/Downloads`; on Windows `C:\Users\<name>\Downloads`) for the new `ES_*.wav`
   files. Copy them to `<project>/MEDIA/MUSICA/`. If they say it doesn't matter which song
   goes where, pair them by mood and say why.

## The mix

The engines call `mix()` automatically for any video with `music` in its spec. By hand:

```bash
python3 "$M" mix --voice voice.m4a --song "cancion.wav" --out mix.m4a \
    --total 52.77 --speech-end 50.97 [--start 8]
```

- **Voice** at -15 LUFS, with a 70 Hz high-pass to take the rumble out of a call.
- **Music 10 LU under the voice while the speaker talks.** The voice ducks it gently
  (sidechain, 40 ms attack, 650 ms release, no pumping), so it rises in the pauses and in the
  tail.
- **-3 dB, one octave wide, at 2.5 kHz** on the music, where consonants live: the music can be
  present without masking them.
- Fade in 0.35 s, fade out over the tail (1.2–2 s). Limiter at -1 dBTP. AAC 256k.
- **Two passes.** How much the voice pushes the music down depends on how much the speaker
  talks, so the bed is measured under the voice and corrected once. In the first Prospect P pass it
  sat 2.5 dB lower than planned.
- `--start` skips a long or empty intro. Prospect P's songs all started at 0.
- `--fade-out S` sets the closing fade (it always ends at `--total`; default 1.2–2 s from the
  tail), `--fade-curve qsin` makes it equal-power instead of linear, and `--sfx FILE@S`
  (repeatable) adds a sound effect at its own level from that time, summed before the
  limiter and left out of the bed measurement. Without them the mix is the same as always
  (checked byte for byte, 2026-10-03).
- If the user wants more or less music, change `gap`: 8 LU is more present, 12 LU is more
  discreet. Tell them the number.

## Client B

The editor, 2026-10-01: *"De aquí en adelante, music-bed también va para CLB. Ahora yo ya no voy a poner la
música desde Premiere, lo vas a hacer tú."* Proven that day on CLB ep3 S1–S2.

- **The songs:** the 8 approved CLB songs (the seven in use plus a spare) in the Drive
  assets folder "the studio Video Skills — Assets", `music/clb/` — the source since the user's
  2026-10-03 review (the team's "CLB > New Music" also holds songs that were not approved).
  This computer's copy: `video_config.py music clb` (in `video-quality-gates/scripts/`; on the
  owner's Mac `CLIENT B/MUSIC/CLB-*.wav`, also in the MUSIC bin of `TEMPLATE CLB.prproj`);
  without one, ask the user where they keep it and set it once (`video_config.py set-music clb
  "<folder>"`). The user picks them, or says "no importa en cuál video": then pair by mood and
  say why. No search, no Epidemic.
- **No hit to land:** *"todas las canciones de Client B en verdad no tienen un momento fuerte
  porque todas las canciones son muy relajadas… Lo Fi."*
- **Take the low parts out, always** — *"quitar las partes que suenan muy bajo. Normalmente siempre
  suele ser el comienzo de la canción."* Start where the song is full (on a bar line), and if a quiet
  stretch falls inside the video, cut it out on the bar grid with a 0.25 s crossfade (CLB ep3 S2:
  the song 23.00→62.57 + 86.31→, a 22 s quiet middle removed). Check the bed with ebur128
  short-term every 3 s: the spread should stay within ~2 LU.
- **Level as a bed, not the Prospect P default** (the editor asked for it on CLB: *"la música debe
  sonar más como una cama que no opaca lo que dice la voz"*): roughly 18–24 dB under the voice,
  a beat-driven song lower than a smooth one; a steady bed, no pumping; the file at −16 LUFS,
  true peak under −1.5 dBFS.
  ```bash
  python3 "$M" mix --voice voice.wav --song bed.wav --out "<project>/CLB <NNN> Snippet <n> MIX.wav" \
      --total <video s> --speech-end <last word s> --voice-lufs -16 --gap 20 --steady --tp -1.5
  ```
  CLB ep3: S1 (lofi with a beat) `--gap 20` → bed −36.2 LUFS; S2 (acoustic) `--gap 18`
  → −34.2; both mixes −16.0 LUFS, −3.4 / −2.8 dBTP, Whisper 0 words lost.
  `--level` flattens a song's own swings with a slow gain curve (only if a quiet part cannot be cut).
- **The voice** is the snippet's own clean audio (Adobe Podcast in the owner's Premiere render;
  Studio Sound in a Descript export). The mix goes next to `index.html` and the
  `<audio id="a-roll-audio">` plays it; the HyperFrames render kept it exactly (−16.0 LUFS in the MP4).
- **Longer than the song?** Not needed on CLB so far (short videos). If a video outlasts the
  song's full part, cut it on the bar grid instead of letting the weak parts in.

## Client E (CLE)

The editor, 2026-10-03: CLE has no Premiere step. A snippet or a teaser is one HyperFrames
project built from the Descript export, and the music goes into its mix the way CLB's
does. The level is not the Prospect P default: it comes from the approved CLE ep2 renders
(`cle-brand/references/finish.md`, "Music bed", has the measured table) — the bed
there was brought down after the note *"music competing with each host"*.

- **Level: 22–25 LU under the voice, default 23, steady, no ducking.** Measured on
  the approved snippets: 17.8 / 25.3 / 22.7 LU (S1 / S2 / S3); S2 and S3 are the
  corrected ones. The bed stays level in the pauses and under speech: `--steady`.
  A percussive marimba goes to the low end of the range.
- **The file: −16 LUFS, true peak under −1.5 dBTP** (`--voice-lufs -16 --tp -1.5`).
  Two of the approved files clipped at 0.0 dBFS; do not ship that.
- **The songs:** warm marimba / lo-fi, never dark or cinematic: CLE's approved set (six
  tracks, plus the other editor's three CLE ep1 tracks). They are in the Drive folder "the studio Video Skills —
  Assets" (`music/cle/`) and on the owner's disk in `CLIENT E/ep1/MUSIC/`;
  this computer's copy is `video_config.py music cle` (without one, ask the user and
  `video_config.py set-music cle "<folder>"`). No search and no Epidemic: the user
  picks, or says it does not matter and the pairing is by mood, with the reason.
- **Start where the song is full** (one of the set: −20 → −14 LUFS short-term over its
  first 16 s, so `--start 16`), on a bar line, and check the bed with ebur128
  short-term every 3 s: it should stay within ~2 LU.
  ```bash
  python3 "$M" mix --voice voice.wav --song "<track>" --out "<project>/CLE <NNN> Snippet <n> MIX.wav" \
      --total <speech end> --speech-end <last word s> --start <s> \
      --voice-lufs -16 --gap 23 --steady --tp -1.5
  ```
  `--total` is the end of the speech, not of the composition: the fixed 5 s outro card
  carries its own audio. CLE ep2 S2 rebuilt (2026-10-03): `--start 16
  --gap 25` → voice −16.0, bed −41.0, mix −16.1 LUFS, peak −5.1 dBTP; the HyperFrames
  render kept −16.1.
- **The voice** is the Descript export's own audio (already cleaned). The mix goes next
  to `index.html`, the `<audio id="a-roll-audio">` plays it, and the `<video>` is muted.
- Then `check` (below): 0 words lost, or only fillers sinking under the music.

## Client A (CLA)

The editor, 2026-10-03: CLA no longer passes through Premiere — the music, the teaser's CTA and
its transition come out of the HyperFrames project. Everything here is measured on the
approved CLA ep4 (`cla-brand/references/finish.md` has the tables).

- **Level: 17 LU under the voice in the snippets, 18.7 in the teaser, steady, no ducking**
  (`--gap 17` / `--gap 18.7`), as the approved ep4: S1–S3 16.9 / 16.7 / 16.0 LU (S4, 24.5, is
  the quiet one), teaser 18.7. The general rule is 18–24 under the voice; for CLA the approved
  ep4 level wins. A song busier than these ambient beds goes 2 LU lower. Bed level in pauses =
  under speech.
- **The file: −16 LUFS, true peak under −1.5 dBTP**; full from the first frame (`--start`
  where the song is already full); an **equal-power** closing fade, `--fade-curve qsin`
  (Premiere's Constant Power).
- **The songs, by slot as in ep3/ep4:** one song per slot (S1, S2, S3, teaser), each started
  where it is already full (ep4: `--start` 15.5, 12.4, 2.0 and 12.6) — 4 of the 6 Epidemic
  WAVs of CLA's approved set (the 6 in the Drive assets folder's `music/cla/`; the other two
  are the alternatives). This computer's folder: `video_config.py music cla`. No search: the
  user picks from the set; until then, ep4's.
  ```bash
  python3 "$M" mix --voice voice.wav --song "<song>" --out "<project>/CLA <NNN> Snippet <n> MIX.wav" \
      --total <video s> --speech-end <last word s> --start <s> \
      --voice-lufs -16 --gap 17 --steady --tp -1.5 --fade-curve qsin
  ```
- **The teaser, twice**, at `--gap 18.7`. Without CTA: `--total <video s> --fade-out 1.13`. With CTA (the
  card lasts 4.05 s): `--total <video s + 4.05> --fade-out 4.09 --sfx
  "<teaser-cta-sfx.wav>@<video s − 0.792>"` — the bed keeps playing under the card and
  the CTA sound (`cla-brand/assets/teaser-cta-sfx.wav`, from `video_config.py asset`) is
  summed before the limiter, left out of the bed measurement. The rest of the CTA (card,
  zoom) is `cla-brand/scripts/teaser_cta.py`.
- **The voice** is the Descript export's own audio; on the owner's Mac, when the start
  is a Premiere render that already has music, use the clean voice from `AUDIO RENDERS/`
  — never the render's audio, or the song plays twice.
- CLA ep4 rebuilt (2026-10-03): S1 → voice −16.0, bed −34.2 (18.2 LU),
  mix −16.0 LUFS, −2.7 dBTP; teaser with CTA → mix −16.0 LUFS, −1.9 dBTP, the 4 s under the
  card at −23.2 LUFS (approved −22.7; with linear fades it came out 3 LU lower).
- Then `check` (below).

## Client C (CLC)

The editor, 2026-10-03: CLC no longer passes through Premiere either — the bed and the teaser's
CTA come out of the HyperFrames project. Measured on the approved CLC ep1
(`clc-brand/references/finish.md` has the tables).

- **Level: 18 LU under the voice, steady, no ducking.** Approved ep1: 22.1 / 19.4 /
  14.8 LU (S1–S3), teaser 17.3; the bed is as loud in the pauses as under speech. The
  general rule is 18–24.
- **The file: −16 LUFS, true peak under −1.5 dBTP**; full from the first frame (`--start`
  where the song is already full); an equal-power closing fade, `--fade-curve qsin` —
  `--fade-out 2` on a snippet, `1.75` on the teaser (ep1: 1.7–2.9 s).
- **The songs:** CLC's four approved songs, in the Drive assets folder "the studio Video
  Skills — Assets", `music/clc/` (the user, 2026-10-03); this computer's copy `video_config.py
  music clc`, without one ask the user and `video_config.py set-music clc "<folder>"`. By slot
  as ep1 and ep3 shipped: S1 and S2 share one song (`--start 21.3`), S3 takes another
  (`--start 18`, where its intro fills), the teaser a third (`--start 0`). No search, no
  Epidemic: the user picks from the set, or the slot decides.
  ```bash
  python3 "$M" mix --voice "<export>" --song "<song>" --out "<project>/CLC <NNN> Snippet <k> MIX.wav" \
      --total <video s> --speech-end <last word s> --start <s> \
      --voice-lufs -16 --gap 18 --steady --tp -1.5 --fade-out 2 --fade-curve qsin
  ```
- **The teaser, twice.** Without CTA: `--total <video s> --fade-out 1.75`. With CTA (the
  card lasts 4.05 s): `--total <video s + 4.05> --fade-out 1.75 --sfx
  "<teaser-cta-sfx.wav>@<video s − 0.792>"` — CLC's song stays full under the card and
  fades only in its last 1.75 s (CLA's fades over the whole card); the CTA sound is CLA's
  file (`video_config.py asset cla-brand/assets/teaser-cta-sfx.wav`): CLC ep1's sequence
  has the same seven effects at the same gains. The card and the zoom: `teaser_cta.py`
  (`clc-teaser-full`).
- **The voice** is the Descript export's own audio; on the owner's Mac, when the start is
  a Premiere base that already has a song, the clean voice from `AUDIO RENDERS/` —
  never the base's audio.
- CLC ep1 rebuilt (2026-10-03): S3 `--start 18` → voice −16.0, bed −34.1
  (18.1 LU), mix −16.0 LUFS, −1.9 dBTP, the 30 fps render −16.0; teaser with CTA → mix
  −16.0 LUFS, −1.9 dBTP, the card's tail −23.9 LUFS with the approved one's momentary
  curve (approved −22.3, which clipped at 0.0 dBTP).
- Then `check` (below).

## Prove the voice survives

```bash
python3 "$M" check --voice voice.m4a --mix mix.m4a
```

Whisper reads the voice alone and the mix and lists every word the mix loses. The model is
faster-whisper `small` by default (the one caption timing already downloaded, ~490 MB once;
a few times faster than the audio on a laptop CPU); `--model large-v3` is the strongest (3 GB
the first time, several times slower on a CPU — the owner's Mac has it) and is the one to
confirm a word that `small` says was lost.

- **Expected:** "uh"/"um" sinking under the music.
- **Anything else:** get a second pass on that short clip before blaming the music. On Prospect P,
  "it's" and "all" looked lost and were both present on the second pass.

## Reporting

In the user's language:

- which song went to which video and why;
- the measured numbers (voice -15 LUFS, music -25 LUFS under the voice, mix -15, peak -1 dBTP);
- the same in their terms if they asked in peaks;
- the Whisper check result;
- how to change the level if they want.

HyperFrames' render may lower the whole mix by ~0.7 dB evenly. The voice/music relation
stays the same; it is not an error.
