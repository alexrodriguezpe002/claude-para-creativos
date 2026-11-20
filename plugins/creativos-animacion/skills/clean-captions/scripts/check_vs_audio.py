#!/usr/bin/env python3
"""Captions vs the real audio: what the voice track says against what is written.

Transcribes each project's voice audio with faster-whisper large-v3 and compares
it word by word (lowercase, no punctuation) with the caption words in index.html.
Prints how many words it read on each side and every difference with its second.
Exits with code 2 if the input is empty (a check that reads nothing must not pass).

    python3 check_vs_audio.py <project_dir> [<project_dir> ...] [--audio voice.m4a]

How to read the result: every difference gets looked at, but not every
difference is an error.
  - Expected: fillers and crutches removed on purpose ("uh", "you know", "I mean",
    "Okay"), false starts listed in the drop list.
  - Whisper's own mistakes: singular/plural, "tourists" vs "tourism". Decide with
    a second pass on the short clip, not with the episode transcript.
  - Alignment ghosts: difflib sometimes reports a word as missing when it is on
    screen ("but", "all" in Prospect P V1/V3). Grep the card in index.html before
    touching anything.
  - Real problems: a word that is heard and is not in any card, or a card with a
    word nobody says. Those get fixed.
"""
import argparse
import difflib
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from captions import cards_from_html  # noqa: E402

norm = lambda s: re.sub(r"[^a-z0-9']", "", s.lower().replace("’", "'"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projects", nargs="+")
    ap.add_argument("--audio", default="voice.m4a", help="audio file inside each project (default voice.m4a)")
    ap.add_argument("--model", default="large-v3")
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    m = WhisperModel(a.model, device="cpu", compute_type="int8")
    bad = 0
    for p in a.projects:
        proj = pathlib.Path(p)
        audio = proj / a.audio
        segs, _ = m.transcribe(str(audio), language="en", word_timestamps=True, beam_size=5,
                               vad_filter=False, condition_on_previous_text=False)
        heard = [(norm(w.word), w.start, w.word.strip()) for s in segs for w in s.words if norm(w.word)]
        written = []
        for t, ws in cards_from_html(proj / "index.html"):
            written += [(norm(w), t, w) for w in ws if norm(w)]
        if not heard or not written:
            print("%s: read %d words from the audio and %d written — empty input" % (proj.name, len(heard), len(written)))
            sys.exit(2)
        A, B = [h[0] for h in heard], [w[0] for w in written]
        ops = [o for o in difflib.SequenceMatcher(a=A, b=B, autojunk=False).get_opcodes() if o[0] != "equal"]
        print("\n%-26s %d words in the audio · %d written · %d difference(s)" % (proj.name, len(A), len(B), len(ops)))
        for tag, i1, i2, j1, j2 in ops:
            t = heard[i1][1] if i1 < len(heard) else heard[-1][1]
            print("   %6.2fs  %-7s heard [%s]  written [%s]" % (
                t, tag, " ".join(h[2] for h in heard[i1:i2]), " ".join(w[2] for w in written[j1:j2])))
        bad += len(ops)
    return 0


if __name__ == "__main__":
    sys.exit(main())
