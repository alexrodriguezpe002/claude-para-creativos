---
name: podcast-audio-clean
description: "Clean the voice of an edited snippet or teaser on this computer (CPU only, Windows/Mac/Linux) — the step the user did with Adobe Podcast's Enhance Speech — and say honestly whether it reaches that bar or Descript's Studio Sound is the better tool for this recording. DeepFilterNet3 (official build, no GPU, no Python ML) + the voice EQ measured on the user's Adobe Podcast versions + -16 LUFS, then a check with a JSON verdict ('ok' or 'studio-sound', with reasons). Input: the edited clip (podcast-rough-cut's MP4 or WAV, a Descript export, any video or audio). Output: '<name> clean.wav' (same length, sample-aligned) + '<name> clean.json'. Use when the user asks to clean, denoise or enhance a clip's audio (\"limpiá el audio\", \"sacale el ruido\"), when an orchestrator reaches the audio step, or to check a Studio Sound export (`check`). For now the cleaning is a preview only: the delivered voice comes from Adobe Podcast or Studio Sound (2026-10-03). Does not cut, choose moments, reframe or mix music."
---

# Podcast audio clean — the Adobe Podcast step, on this computer

The user cleaned every snippet's voice with Adobe Podcast (Enhance Speech v2, strength 50–93 %,
background 10 %) before animating it. This skill does that step locally and — just as
important — **says when it is not good enough**, so the person knows to use Descript's Studio
Sound for that clip instead. It never pretends: the check is set on the user's own Adobe
versions of 13 snippets (`references/measured.md`).

**What it matches and what it does not.** It removes background noise as well as Adobe did
(noise in the gaps equal or lower on 11 of 13 clips, 0.9–1.7 dB above on CLB ep3's two; DNSMOS
2.70 → 3.16 vs Adobe 3.27) and moves the voice towards Adobe's timbre in the band where Adobe
does the same thing on every client (315 Hz – 6.3 kHz). It does **not** rebuild a voice: Adobe and Studio Sound re-synthesise
speech (they take the room out of a reverberant voice, restore the highs of a call recorded at
16 kHz, make a call voice sound like a studio mic) — overall predicted quality (NISQA, same
level) 3.73 here vs 4.55 for Adobe, raw 3.32. On a noisy call or a band-limited recording that
difference is large, and the check routes the clip to Studio Sound; on a clean recording it is
smaller, and `ok` means the background is at Adobe's level and nothing broke — not that it
equals Studio Sound. Which one the user delivers on `ok` clips is the user's call.

**The owner's decision (2026-10-03): not yet.** Local cleaning does not reach Adobe Podcast, so it
is never the delivered sound. The owner uploads the cut clip's WAV (`podcast-rough-cut` writes it)
to Adobe Podcast; the team cleans it in Descript Studio Sound (or the tool the user uses). Until the
clean sound comes back, `clean` is a preview only; `check` measures what comes back.

## Where it sits

```
raw ──► podcast-snippet-select ──► podcast-rough-cut ──► podcast-audio-clean (optional) ──► podcast-reframe ──► build
                                    <name>.mp4 + <name>.wav      <name> clean.wav + .json
```

**After the cut, never before.** It is where the user cleaned (Adobe got the edited snippet's
audio, `AUDIO PARA IA/`), and it is right for three reasons: the cut is decided on the raw sound,
the way the user hears it (podcast-rough-cut places its cuts on the raw voice); the snippet is a few seconds
to a few minutes instead of an hour of episode (seconds of CPU instead of half an hour); and
moments joined from different microphones or takes come out with one even background instead of
a jump of room tone at every cut. Studio Sound, the fallback, also takes the cut clip.

## Setup (once per computer)

```bash
python3 "<podcast-audio-clean>/scripts/audio_clean.py" doctor --fix
```

`<podcast-audio-clean>` is this skill's folder. On Windows run `py -3` (or `python`) where this
says `python3`. It needs Python 3.8+, numpy and ffmpeg (the package's usual requirements), plus:

- **DeepFilterNet 0.5.6** — the official standalone build of DeepFilterNet3 (`deep-filter`,
  MIT/Apache-2.0) for Windows x64, macOS (Apple silicon, Intel) or Linux: 27–39 MB, downloaded
  once into `~/.studio-video/models/audio-clean/` and checked by SHA-256
  (`AUDIO_CLEAN_MODELS` overrides the folder). No Python ML packages, no GPU. `pip install
  deepfilternet` is deliberately not used: its compiled part only has Windows wheels for
  Python 3.8–3.11 and pins numpy < 2, so it does not install on the Python 3.12 of the package's
  Windows guide.
- **RNNoise `std.rnnn`** (0.3 MB, SHA-256) — the fallback through ffmpeg's `arnndn` filter on a
  system with no DeepFilterNet build (and the baseline it was measured against).

## Run

```bash
python3 "<podcast-audio-clean>/scripts/audio_clean.py" clean "<name>.wav"            # or the MP4
python3 "<podcast-audio-clean>/scripts/audio_clean.py" clean "<name>.mp4" --mux "<name> clean.mp4"
```

| Writes | What |
|---|---|
| `<name> clean.wav` | 48 kHz, 24-bit, stereo (both channels the same; `--mono` for one), **same length as the input and sample-aligned** (checked by cross-correlation: lips stay on the voice), integrated **−16 LUFS** — a little less when the true peak would pass −1.5 dBTP (`level.peak_limited` in the JSON) — one gain for the whole file (no compression — Adobe does not compress either) |
| `<name> clean.json` | settings, the measurements, `verdict`, `reasons` (codes + English text), `warnings` |
| `--mux OUT.mp4` | a copy of the input video with the cleaned sound (video stream copied untouched, AAC 320 kbps) |

The last line printed is `##JSON## {"verdict": ..., "reasons": [...], "wav": ..., "json": ..., "mux": ...}`.
**Exit codes:** `0` good enough · `3` use Studio Sound (the files are still written, for
comparison) · `2` nothing to clean (no audio, no voice, < 1 s) · `1` could not run.

The chain: DeepFilterNet3 at full suppression → **background level chosen per clip** (below) →
70 Hz high-pass + the voice EQ → −16 LUFS → the check. ~6–20 s for a 30–90 s clip on a laptop
CPU (the denoiser runs ~15× real time on one core).

Options: `--atten auto|DB` (how far the background goes down; `auto` default), `--no-eq`
(denoise only, no high-pass, no EQ), `--hp HZ` (70), `--lufs N|keep` (−16), `--tp DB` (−1.5),
`--engine dfn|rnnoise`, `--mono`, `--start S --duration D` (a test excerpt), `--out`, `--json`.

### The background level (`--atten auto`)

DeepFilterNet's attenuation limit is exactly a mix of the fully cleaned voice with a little of the
original (verified on the binary's own output, identical to 16-bit precision), so the denoiser
runs once and the amount of background kept is chosen afterwards: the **mildest** of 12–40 dB
whose background in the gaps between words is within 1 dB of what full suppression reaches.
Past that point more suppression only makes the gaps go dead and come back without lowering
the background. On the 13 clips: clean recordings (CLB ep2, CLC ep1/ep3, CLE ep2) → 12 dB,
CLB ep3 and CLE ep1 → 25 dB, the noisy CLA ep4 calls → 35–40 dB — the same steady background
Adobe's "background 10 %" leaves, instead of gating.

### The voice EQ

What Adobe Podcast did beyond removing noise, measured as Adobe minus DeepFilterNet on the
user's clips: about +3 dB at 1–1.25 kHz and −3 to −5 dB from 2.5 to 5 kHz (a warmer, less
edgy voice). Fitted on CLB ep3 + CLA ep4 and checked on six other snippets (CLB ep2, CLC ep1/ep3,
CLE ep1/ep2): within ±1.5 dB between 315 Hz and 5 kHz, so only that band is touched; below and
above it Adobe's change depends on the recording (on CLC/CLE it adds 4–10 dB of highs it
re-synthesises), so those are left (nearly) flat: 0 dB below 200 Hz, the curve tapers to −0.7 dB
at 8 kHz and stays there. Constants in `scripts/audio_clean.py` (`EQ_CENTERS`, `EQ_GAINS`).

## The quality check — `ok` or `studio-sound`

Measured on the output against its own input (no reference file needed), with the voice
brought to −16 LUFS so every clip compares. Any reason below makes the verdict `studio-sound`.
The limits come from the user's Adobe versions (`references/measured.md`).

| Reason code | Fires when | Why it means Studio Sound |
|---|---|---|
| `input-noisy` | the input's voice is < 25 dB over the gaps between words | the cleaner removes the noise, but the voice stays a call voice; on CLA ep4 (12.7–22 dB) predicted quality (NISQA, same level) was 3.1–3.3 here vs 4.0–4.5 for Adobe |
| `band-limited` | the input's voice stops below 10 kHz | a call sampled at 16 kHz (CLC ep3: 8 kHz); Studio Sound/Adobe rebuild the highs, a denoiser cannot |
| `noisy-stretch` | the worst 3 s of the input are < 8 dB voice over background | one joined moment from a bad mic |
| `noise-left` | gaps louder than −47 dBFS after cleaning | Adobe's worst clip left −47.8 |
| `echo-left` | the voice 50–150 ms after a phrase ends is > −20 dB under its end | room echo the denoiser kept (Adobe's worst: −23) |
| `voice-damaged` | > 2 times a minute a clearly carried syllable drops ≥ 10 dB for ≥ 60 ms | the cleaner ate voice |
| `input-clipped` | > 20 runs of samples stuck at full scale | distortion in the recording |

Warnings never change the verdict: `pumping` (the gaps go dead and come back, audible range),
`few-pauses`, `little-clear-voice`, `shifted`. On the 13 clips the check says **ok** for CLB ep2
S1–S2, CLB ep3 S1–S2, CLC ep1 S2, CLE ep2 S1 and **studio-sound** for CLA ep4 S1–S4 + teaser and
CLE ep1 S1 (noisy input) and CLC ep3 S1 (band-limited).

**When it says studio-sound:** clean the same edited clip in Descript (Studio Sound; the user's
Adobe strengths were 50–93 %, start around the middle), export the audio as WAV and use that
file instead. `check` measures any cleaned file with the same yardstick (here the input's own
limits are only warnings, the verdict is about the result: `ok` or `review`):

```bash
python3 "<podcast-audio-clean>/scripts/audio_clean.py" check "<name>.wav" "<name> studio sound.wav" --json check.json
```

## For orchestrators

1. After `podcast-rough-cut`: `audio_clean.py clean "<cut>.mp4" --mux "<cut> clean.mp4"`
   (writes `<cut> clean.wav`, `<cut> clean.json` and the base video with the cleaned sound).
2. Read the `##JSON##` line (or the exit code). `ok` (0) → continue with `<cut> clean.mp4` as
   the base: everything after it (reframe copies the sound untouched, music-bed levels the voice
   itself) reads the base video's sound, so nothing else changes. `studio-sound` (3) → tell the
   user in one line which reason fired and that the clip should go through Descript's Studio
   Sound; keep building on the uncleaned `<cut>.mp4` meanwhile and swap the sound when their
   WAV arrives (`--mux` is plain ffmpeg: `-map 0:v -map 1:a -c:v copy`) — never stop the whole
   build for it.
3. Nothing here is required: a clip with no audio step still builds (the step is optional, as
   the user decided).

JSON keys the orchestrator may read: `verdict`, `reasons`, `warnings`, `output`, `seconds`,
`settings.atten_db`, `metrics.noise_floor`, `metrics.input_noise_floor`, `metrics.input_snr`,
`metrics.input_bandwidth_khz`, `metrics.dropouts_per_min`, `metrics.echo_tail`,
`metrics.output_lufs`, `metrics.output_true_peak`, `metrics.lag_samples` (always 0).

## Files

- `scripts/audio_clean.py` — the CLI (`doctor`, `clean`, `check`), the EQ constants.
- `scripts/aclib/engines.py` — DeepFilterNet binary and RNNoise model: URLs, sizes, SHA-256, download.
- `scripts/aclib/dsp.py` — audio in/out through ffmpeg, the zero-phase EQ, loudness, alignment, the background mix.
- `scripts/aclib/qc.py` — the quality check and its limits (`LIMITS`).
- `references/measured.md` — how it was measured against Adobe Podcast, every number, what was tried and dropped.
