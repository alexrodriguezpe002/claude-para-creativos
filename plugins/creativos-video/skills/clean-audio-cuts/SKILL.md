---
name: clean-audio-cuts
description: Put every audio cut of a podcast recut on real silence instead of on Whisper timestamps, trim long pauses only where the speaker isn't on screen, and prove with Whisper that no word was eaten. Use it when setting the in/out points of segments taken from a long episode for explainer-vertical or Prospect P videos, or when the editor hears a clipped or swallowed word in them ("se come la palabra", "empieza con un ummm", "el corte es muy justo"). Not for the editor's own Premiere edits. Use it only in explainer-vertical or Prospect P work (or another project under OTHER PROJECTS), or when the user names this skill. For CLA, CLC, CLE, CLB, CLD or CLF, don't use it even if the same words come up, unless the user names the skill.
---

# Clean audio cuts

Script: `scripts/audiocuts.py`. It works as a module for the video engines and from the
command line.

## Why the transcript cannot place a cut

Whisper's word times are good for **finding** a sentence and for highlighting captions, not
for **cutting** it:

- many word starts come **0.1–0.35 s late**;
- after a pause, the next word starts **early, up to 0.9 s**;
- the last word is **stretched** over the silence that follows.

On the Prospect P master, **25 of 50 cut points placed on Whisper times fell on voice**. Several
ate or split a whole word, the kind of thing you then hear (made-up examples): "-ployee turnover",
"Some-|-times", "So, the bigger" instead of "Also, the bigger ones". V1 started on the tail of
"I mean", and the editor heard "…mmm".

## Procedure for each segment

1. **Find the sentence in the transcript**, then look at the audio around each boundary:

   ```bash
   A="${CLAUDE_SKILL_DIR}/scripts/audiocuts.py"
   python3 "$A" energy --src M.mp4 --at 403.6 --win 0.5          # 10 ms bars
   python3 "$A" gap    --src M.mp4 --between 403.5 403.8           # quietest instant
   python3 "$A" check  --src M.mp4 403.30 403.64 447.50            # silence / valley / ON VOICE
   ```

2. **Where each boundary goes:**
   - **In:** in the silence before the first word you keep. If there is no real silence
     (words run together), use the **valley** between the two words: at least 12 dB under
     the voice around it. With the 40 ms fades that splices clean. Prospect P V1 start: 403.30 was
     ON VOICE ("…mmm-mean"); 403.64 is the valley before "There's".
   - **Out:** after the last word has fully decayed. Keep the breath; don't cut the tail.
   - **Visual boundary:** when the picture changes inside a sentence (the source switches to
     the host at 456.96), put the audio splice in the nearest valley **before** the switch
     frame (456.94). A splice between two ranges that are contiguous in the source still
     applies fades, so it must not sit on a syllable.
3. **Prove it** for every cut you add or move. Whisper large-v3 reads the old and the new
   version, with a prompt that makes it write fillers instead of hiding them:

   ```bash
   python3 $A ab --src M.mp4 --old 403.30-406.40 --new 403.64-406.40
   ```

   Then read both lines. The new one must keep every word you meant to keep and no fragment of
   one you meant to drop.
4. **Two words glued together can't be split.** In Prospect P V1, "but" is fused to "everybody".
   Either keep both or drop both, and match the caption (drop list). Say so in the spec
   comment.

## Silences

- The editor chose the threshold on 17 Sept among three options: **silences of 0.6 s or more are
  cut down to 0.2 s of breath**. They are measured on the audio with `silencedetect`, at
  -34 dB. Never run silencedetect with `-v error`: it prints at info level and you'd get
  nothing.
- **Only where the speaker is not on screen.** Over animation a splice is invisible; on
  camera it is a jump cut. The engines apply `trim_silence` to graphic beats only.
- A splice that only removed a silence does **not** close a caption line: the text on both
  sides is one sentence. The engine records these splices in `cont`.
- Leave **1.8–2.2 s of tail** after the last word of a video.

## Joining two separate moments

To finish an idea with words said a few seconds later, put the second range right after the
first, both boundaries on measured silence.

- Example (made up): "…it works like | a thermostat for the whole team." With the cut ending on
  "a thermo—", the comparison gets lost.
- List the join (master start of the second range) so the caption runs across it
  (`CAPTION_JOINS`).

## Writing the audio

`concat_audio(src, segs, out)` builds one continuous track in **a single ffmpeg pass**, with
a 40 ms fade in and out on every piece. Cutting each piece to AAC and gluing the files looks
the same but adds ~25 ms of codec padding per file: with ten pieces the voice ended 0.25 s
behind the picture.

## When you finish

Tell the user, in Spanish:

- which cuts moved and why (in words they'd use: "se comía el 'So'");
- the old and new start/end;
- that each one was checked with Whisper;
- anything left as is, and why (glued words).
