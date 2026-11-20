# How podcast-audio-clean was measured against Adobe Podcast

Built 2026-10-03. Everything here was measured on the user's own files; nothing is a default
from a paper.

## The material — 13 snippets with the user's Adobe Podcast version

For every snippet the user exported the edited audio (`AUDIO PARA IA/<clip>_001.wav`), ran it
through Adobe Podcast Enhance Speech v2 and got back `AUDIO RENDERS/<clip>_001-esv2-<strength>p-bg-<bg>p-music-10p.wav`.
Same length, aligned to 0–1 sample, 48 kHz dual mono: a perfect before/after pair.

| Set | Clips | Adobe settings |
|---|---|---|
| Fitting (7) | CLB ep3 S1–S2 (iPhone, scripted), CLA ep4 S1–S4 + teaser (podcast, noisy guests) | strength 50–82 %, background 10 % |
| Held out (6) | CLB ep2 S1–S2, CLC ep1 S2, CLC ep3 S1, CLE ep1 S1, CLE ep2 S1 | strength 50–93 %, background 10–15 % |

The EQ and the background rule were fitted on the 7 and checked on the 6; the check's limits
were set on all 13 (they describe Adobe's range).

## What was tried (first, cheap pass on the 7)

| Option | Runs on Windows CPU + Python 3.12 (pip)? | Noise in pauses @ −16 LUFS (Adobe −49.9) | Voice/pause ratio (Adobe 34.3 dB) | Verdict |
|---|---|---|---|---|
| ffmpeg `afftdn` / `anlmdn` | yes | −34 (≈ raw) | 18.5 | useless here |
| RNNoise (`arnndn`, 6 models) | yes | −42 … −45 | 22–29 | baseline, kept as fallback |
| **DeepFilterNet3** | **yes, as the official standalone binary** (pip: no — DeepFilterLib 0.5.6 has Windows wheels only for cp38–cp311, numpy < 2) | −44.6 … −50.5 (by limit) | 29–35 | **chosen** |
| MossFormer2_SE_48K (ClearerVoice) | pip, heavy (torch, torchvision, OpenCV, librosa; numpy < 2 → Python ≤ 3.12); 4.7× real time on 8 M1 cores | −42.9 | 27.1 | dropped: less noise removal than DFN, NISQA 3.63 vs 3.94, 1.5 GB of packages |
| resemble-enhance | needs Python ≥ 3.10 + deepspeed | — | — | out (not installable on the floor Python) |
| WPE dereverberation (numpy) before DFN | yes | no change | no change | dropped: echo tail on CLB ep3 −38.5 vs −38.4 without it |

DeepFilterNet's Python package and the binary give the same model; the binary suppresses a
little more at full strength (voice/pause 33.2 vs 31.3 dB) and is identical with a limit.

## The deep pass — 13 clips, three finalists + the shipped chain

Means over 13 clips. NISQA and DNSMOS are non-intrusive quality predictors (1–5); NISQA is
level-sensitive, so its row compares files at the same loudness (−16 LUFS). NISQA was used to
measure only — its weights are CC BY-NC-SA, so it is not part of the skill.

| | Raw | RNNoise | MossFormer2 | DFN3 limit 40 | **Shipped chain** | Adobe Podcast |
|---|---|---|---|---|---|---|
| Voice over pauses (dB) | 25.9 | 32.3 | 31.2 | 35.5 | **36.7** | 35.8 |
| Noise in pauses @ −16 LUFS (dBFS) | −41.7 | −48.1 | −47.0 | −51.4 | **−52.5** | −51.4 |
| Pause-level spread (dB, gating) | 5.5 | 7.4 | 8.8 | 12.4 | **8.3** | 6.2 |
| Spectral balance vs Adobe (dB, mean abs., 100 Hz–12.5 kHz) | 2.67 | 2.54 | 2.60 | 2.80 | **2.18** | 0 |
| Frame-wise distance to Adobe (dB) | 5.82 | 5.30 | 5.38 | 5.40 | **5.06** | 0 |
| DNSMOS overall (own level; at −16 LUFS in brackets) | 2.76 (2.70) | 2.92 | 2.98 | 3.18 | **3.16** (−16) | 3.36 (3.27) |
| NISQA MOS at −16 LUFS | 3.32 | — | — | — | **3.73** | 4.55 |

By group (shipped chain vs Adobe at −16 LUFS):

| | Noise in pauses (QC, dBFS) | DNSMOS | NISQA @ −16 |
|---|---|---|---|
| CLB ep3 (iPhone, quiet room) | −57.1 / −58.0 vs −58.8 / −58.9 | 3.09 vs 3.19 (raw 2.89) | 3.87 vs 4.65 (raw 3.44) |
| CLA ep4 (noisy guests) | −52.6 … −56.0 vs −47.8 … −55.0 | 3.09 vs 3.19 (raw 2.10) | 3.16 vs 4.30 (raw 2.38) |
| Held-out 6 | −51.8 … −63.4 vs −50.5 … −60.5 | 3.23 vs 3.37 (raw 3.13) | 4.17 vs 4.73 (raw 4.07) |

Intelligibility (Whisper small.en on the 13 clips): mean word probability raw 0.947 · chain
0.947 · Adobe 0.944; words under p 0.5: 2.4 % · 2.4 % · 2.7 %; words that differ from the
transcript of Adobe's version: raw 3.7 % · chain 3.7 %. The cleaning neither costs nor gains words.

**Reading:** the noise removal reaches Adobe's level (gaps equal or lower on 11 of 13 clips; on
CLB ep3 0.9–1.7 dB above, inaudible), the EQ brings the timbre measurably closer, nothing is shifted
or eaten. DNSMOS (a noise-suppression quality predictor) closes 81 % of the raw→Adobe gap
(2.70 → 3.16 vs 3.27). NISQA (overall speech quality: coloration, reverberation, bandwidth)
closes only 33 % (3.32 → 3.73 vs 4.55): Adobe re-synthesises the voice. The gap is largest on
noisy calls (CLA ep4: 3.16 vs 4.30) and on the band-limited CLC ep3 (3.31 vs 5.01), smaller on a
quiet iPhone recording (CLB ep3: 3.87 vs 4.65 — drier, fuller voice in Adobe; echo tail after
phrases −38/−42 dB here vs −49/−44 in Adobe) and on clean ones (held-out: 4.17 vs 4.73).
CLE ep1 is the one clip where this chain scored above Adobe (4.50 vs 4.33).

## The voice EQ

`fixed` = Adobe's 1/3-octave speech spectrum minus DeepFilterNet's, both normalised on
500 Hz–2 kHz, mean over clips:

| Band | 63–125 Hz | 800 Hz | 1–1.25 kHz | 2 kHz | 2.5–3.15 kHz | 4–5 kHz | 6.3 kHz | 8 kHz | 10–16 kHz |
|---|---|---|---|---|---|---|---|---|---|
| Fitting set (7) | −1…−2 | +1.5 | +3.2…+3.7 | −2.0 | −3.1…−3.4 | −5.4 | −5.8 | −5.6 | −1.5…−6.2 |
| Held out (6) | +1…+5 | +0.4 | +1.7…+1.8 | −1.6 | −3.0…−3.5 | −3.9…−4.1 | −2.9 | −0.6 | +4…+11 |

They agree within ±1.5 dB from 315 Hz to 5 kHz; outside it Adobe's change depends on the
recording (on CLC/CLE it adds the highs it re-synthesises), so the shipped curve is the fitting
set's, taken only on 315 Hz–6.3 kHz with a one-band taper (250 Hz −0.2 dB, 8 kHz −0.7 dB, held
beyond), smoothed, clamped to ±6 dB. Applied
as a zero-phase linear-phase FIR (16384 taps, delay removed — lag 0 measured). On the held-out
clips it lowers the balance distance to Adobe from 2.96 to 2.59 dB (fitting set 2.67 → 1.84);
it changes NISQA by −0.04 on average (the drop seen first came from the louder level, not the EQ).

## The background level (`--atten auto`)

DeepFilterNet's attenuation limit is a plain mix: output = lim·input + (1−lim)·fully-cleaned
(checked against the binary's own `-a 20/30/40` outputs: residual 71–79 dB down, i.e. 16-bit
noise). Sweep of the gap level (dBFS @ −16 LUFS, without EQ) / its spread (dB):

| Clip | Adobe | 12 dB | 20 dB | 25 dB | 30 dB | 40 dB | full |
|---|---|---|---|---|---|---|---|
| CLB ep3 S1 | −58.8 / 5.5 | −50.2 / 3.7 | −52.3 / 4.7 | −53.0 / 5.5 | −53.3 / 6.2 | −53.6 / 7.7 | −53.8 / 13.1 |
| CLA ep4 S4 | −47.8 / 3.0 | −38.3 / 2.5 | −44.7 / 2.7 | −47.8 / 3.3 | −50.1 / 4.1 | −52.2 / 6.0 | −53.1 / 9.3 |
| CLC ep3 S1 | −60.5 / 5.9 | −60.7 / 10.5 | −60.8 / 13.5 | −60.9 / 15.6 | −60.8 / 17.7 | −60.9 / 21.9 | −60.8 / 25.4 |
| CLE ep2 S1 | −54.1 / 9.9 | −63.3 / 11.4 | −63.6 / 14.8 | −63.6 / 17.0 | −63.6 / 19.1 | −63.7 / 23.0 | −63.6 / 26.3 |

On clean recordings the level stops falling at 12 dB and more only gates the gaps; on noisy
ones it keeps falling to ~40. Rule: the mildest step of 12/15/20/25/30/35/40 dB within 1 dB
of full suppression. Chosen: 12 (CLB ep2, CLC ep1, CLC ep3, CLE ep2), 25 (CLB ep3, CLE ep1),
35–40 (CLA ep4). Spread over 13 clips: 8.3 dB (Adobe 6.2) instead of 12.4–12.6 at a fixed 40.

## The quality check

Measured on output vs its own input; the voice/gaps segmentation comes from the cleaned voice
(20 ms frames; voice = within 30 dB of the loud 30 %; gaps ≥ 30 ms from voice — edited snippets
have almost no long pauses, the silences were cut).

| Clip | Input voice/gaps (dB) | Input bandwidth | Gaps after (dBFS) | Adobe's gaps | Verdict |
|---|---|---|---|---|---|
| CLB ep3 S1 | 28.4 | 12.5 kHz | −57.1 | −58.8 | ok |
| CLB ep3 S2 | 31.2 | 12.5 | −58.0 | −58.9 | ok |
| CLB ep2 S1 | 41.5 | 12.5 | −58.5 | −55.7 | ok |
| CLB ep2 S2 | 41.7 | 12.5 | −59.3 | −51.7 | ok |
| CLC ep1 S2 | 35.9 | 12.5 | −54.1 | −53.0 | ok |
| CLE ep2 S1 | 45.6 | 10.0 | −63.4 | −54.1 | ok |
| CLA ep4 S1 | 22.0 | 12.5 | −55.4 | −55.0 | studio-sound (input-noisy) |
| CLA ep4 S2 | 13.5 | 12.5 | −54.7 | −49.4 | studio-sound (input-noisy) |
| CLA ep4 S3 | 16.0 | 12.5 | −52.6 | −50.3 | studio-sound (input-noisy) |
| CLA ep4 S4 | 12.7 | 12.5 | −53.3 | −47.8 | studio-sound (input-noisy) |
| CLA ep4 teaser | 14.6 | 12.5 | −56.0 | −50.3 | studio-sound (input-noisy) |
| CLE ep1 S1 | 21.0 | 12.5 | −51.8 | −50.5 | studio-sound (input-noisy) |
| CLC ep3 S1 | 45.1 | **8.0** | −61.4 | −60.5 | studio-sound (band-limited) |

- `input-noisy` (< 25 dB): set where the predicted-quality gap to Adobe opens — CLA ep4 at
  12.7–22 dB: NISQA 3.09–3.27 vs 4.01–4.48 (same level). It is conservative: CLE ep1 (21 dB,
  stationary hiss) came out better than Adobe's (NISQA 4.50 vs 4.33) and is still sent to Studio
  Sound — a false alarm costs one Studio Sound pass, a miss costs a worse delivery.
- `band-limited`: CLC ep3's raw stops at 8 kHz (a 16 kHz call); Adobe rebuilt 8–16 kHz
  (NISQA at −16 LUFS: Adobe 5.01, raw 3.23, this chain 3.31).
- `noise-left` −47 dBFS (Adobe's worst −47.8) and `echo-left` −20 dB (Adobe's worst −23.1) never
  fired on the chain's output; `voice-damaged` fired only on Adobe's CLE ep2 version (three word
  endings Adobe made much drier — most likely its dereverberation, not damage; in `check` mode
  that shows as `review`, a prompt to listen).
- `pumping` is only a warning: Adobe's own CLB ep2 S2 shows the same spread (breaths in the gaps).
- A first version of the dropout detector used one global noise floor and flagged the CLA
  teaser's noisy stretch: DeepFilterNet removing a hum under the voice looked like lost voice.
  The local (per-second) floor fixed it; the detector now only reads frames where the voice is
  ≥ 20 dB over its local background.

## Speed and portability

- deep-filter 0.5.6: ~15× real time on one Apple M1 Pro core; a 30–90 s clip end-to-end
  (decode, denoise, EQ, three loudness passes, check) 6–20 s.
- Two bugs found and fixed while measuring: ffmpeg `firequalizer` with `delay` shifted the
  output 50 ms (replaced by the numpy FIR); `arnndn` delays by one 10 ms frame (the skill now
  aligns every engine's output to the input by cross-correlation; `lag_samples` is reported).
- Binaries pinned by size + SHA-256 (`scripts/aclib/engines.py`): Windows x64, macOS arm64/x86_64,
  Linux x86_64/aarch64 from the v0.5.6 GitHub release; RNNoise `std.rnnn` from
  richardpl/arnndn-models.
