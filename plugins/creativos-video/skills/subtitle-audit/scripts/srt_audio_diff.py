#!/usr/bin/env python3
"""Pass 1 of a subtitle audit: transcribe the video's real audio and diff it
against the subtitle file, word by word.

Outputs into --out:
  audio.wav       16 kHz mono extraction (reused by verify_spots.py)
  asr.json        segments + word timestamps + per-word confidence
  candidates.md   every divergence, with cue number, timecode and ASR confidence
  pauses.md       measured silence at each cue boundary (period vs comma evidence)

Nothing here decides anything. It produces the candidate list that passes 2 and 3
adjudicate. Treat a single pass as a hypothesis, never as a verdict.
"""
import argparse, json, os, re, subprocess, sys, difflib

ACCENTS = str.maketrans("áéíóúüÁÉÍÓÚÜ", "aeiouuAEIOUU")


def parse_srt(path):
    """Return [(index, start_str, end_str, text)] and remember the raw encoding."""
    raw = open(path, encoding="utf-8-sig").read().replace("\r\n", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0].strip())
        except ValueError:
            continue
        if "-->" not in lines[1]:
            continue
        start, end = [t.strip() for t in lines[1].split("-->")]
        cues.append((idx, start, end, " ".join(lines[2:]).strip()))
    return cues


def to_sec(ts):
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def mmss(ts):
    x = to_sec(ts)
    return f"{int(x // 60):d}:{x % 60:05.2f}"


def norm(text):
    t = text.lower().translate(ACCENTS)
    t = re.sub(r"[^\w%ñ ]", " ", t)
    return t.split()


def extract_audio(video, out_wav):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", video,
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out_wav],
        check=True)


def transcribe(wav, lang, model_name):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        wav, language=lang, word_timestamps=True, beam_size=5,
        vad_filter=True, vad_parameters=dict(min_silence_duration_ms=300),
        condition_on_previous_text=False)
    out = []
    for s in segments:
        words = [{"w": w.word, "s": round(w.start, 3), "e": round(w.end, 3),
                  "p": round(w.probability, 3)} for w in (s.words or [])]
        out.append({"start": round(s.start, 3), "end": round(s.end, 3),
                    "text": s.text, "words": words})
        print(f"[{s.start:7.2f} -> {s.end:7.2f}] {s.text}", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--srt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="es")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--reuse", action="store_true",
                    help="reuse an existing asr.json in --out instead of re-transcribing")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    wav = os.path.join(args.out, "audio.wav")
    asr_path = os.path.join(args.out, "asr.json")

    if not os.path.exists(wav):
        extract_audio(args.video, wav)
    if args.reuse and os.path.exists(asr_path):
        asr = json.load(open(asr_path))
        print(f"(reusing {asr_path})")
    else:
        asr = transcribe(wav, args.lang, args.model)
        json.dump(asr, open(asr_path, "w"), ensure_ascii=False, indent=1)

    cues = parse_srt(args.srt)
    srt_words = []           # (norm_word, cue_idx, start_ts)
    for idx, start, _end, text in cues:
        for w in norm(text):
            srt_words.append((w, idx, start))
    asr_words = []           # (norm_word, start_sec, prob)
    for seg in asr:
        for w in seg["words"]:
            n = norm(w["w"])
            if n:
                asr_words.append((n[0], w["s"], w["p"]))

    A = [w[0] for w in srt_words]
    B = [w[0] for w in asr_words]
    sm = difflib.SequenceMatcher(None, A, B, autojunk=False)

    lines = [f"# Candidates — {os.path.basename(args.srt)}",
             "",
             f"SRT words: {len(A)} · ASR words: {len(B)}",
             "",
             "Low ASR confidence (p<0.5) means the audio is genuinely unclear there —",
             "send it to pass 2/3, do not accept the ASR reading.",
             ""]
    n = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        n += 1
        cue = srt_words[min(i1, len(srt_words) - 1)][1]
        ts = srt_words[min(i1, len(srt_words) - 1)][2]
        at = asr_words[j1][1] if j1 < len(asr_words) else -1
        before = " ".join(A[max(0, i1 - 6):i1])
        after = " ".join(A[i2:i2 + 6])
        probs = ", ".join(f"{asr_words[k][0]}:{asr_words[k][2]}"
                          for k in range(j1, min(j2, j1 + 6)))
        lines += [
            f"## {n}. cue #{cue} · {mmss(ts)} · audio {at:.2f}s · {tag}",
            f"- context: …{before} **[…]** {after}…",
            f"- SRT: «{' '.join(A[i1:i2])}»",
            f"- ASR: «{' '.join(B[j1:j2])}»",
            f"- ASR confidence: {probs or '—'}",
            ""]
    lines.insert(3, f"**{n} divergences found.**")
    open(os.path.join(args.out, "candidates.md"), "w").write("\n".join(lines))

    # Pause at every cue boundary: the evidence for period vs comma vs no break.
    #
    # Thresholds are RELATIVE to this speaker. An absolute "0.45s = period" rule is
    # useless: a fast speaker can deliver seven minutes with no gap above 0.40s, and
    # every boundary would read as "no pause". What matters is whether a gap is long
    # FOR THIS PERSON, so classify by percentile of their own inter-word gaps.
    flat = [(w["w"].strip(), w["s"], w["e"]) for seg in asr for w in seg["words"]]
    inter = sorted(max(0.0, flat[i + 1][1] - flat[i][2]) for i in range(len(flat) - 1))

    def pct(p):
        if not inter:
            return 0.0
        return inter[min(len(inter) - 1, int(p / 100 * len(inter)))]

    # Floors stop the labels degenerating: a continuous speaker can have a median
    # and a p90 of exactly 0.00s, and "pause >= 0.00s" would label everything a pause.
    p90, p98 = max(pct(90), 0.08), max(pct(98), 0.15)
    pl = ["# Pauses at cue boundaries", "",
          f"Speaker's own inter-word gaps: median {pct(50):.2f}s · "
          f"p90 {pct(90):.2f}s · p98 {pct(98):.2f}s · max {inter[-1] if inter else 0:.2f}s",
          "",
          "A boundary is classed against THIS speaker, not an absolute threshold:",
          f"**LONG PAUSE** ≥ {p98:.2f}s · **pause** ≥ {p90:.2f}s · else no break.",
          "(Thresholds are this speaker's p98/p90 with a floor of 0.15s/0.08s.)",
          "",
          "If the max gap in the whole file is small (a fast, continuous speaker), then",
          "NO boundary is a real sentence stop and punctuation must be decided on",
          "grammar alone — say so in the report instead of inventing pauses.",
          "",
          "`mid-word` means the cue splits a word in two — there is no pause there at all,",
          "whatever punctuation the subtitle shows.",
          "",
          "A period in a subtitle does not force a pause, so this is evidence for a",
          "sentence boundary, never a rule. Use it to catch a period where the speaker",
          "clearly ran on, and a run-on where they clearly stopped.",
          ""]
    rows, conflicts = [], []
    for i in range(len(cues) - 1):
        end_s = to_sec(cues[i][2])
        tail, head = cues[i][3][-30:], cues[i + 1][3][:30]
        stops = cues[i][3].rstrip().endswith((".", "!", "?", "…"))
        spanning = [w for w in flat if w[1] < end_s < w[2]]
        if spanning:
            gap, verdict = 0.0, f"mid-word («{spanning[0][0]}»)"
        else:
            prev_w = [w for w in flat if w[2] <= end_s]
            next_w = [w for w in flat if w[1] >= end_s]
            if not prev_w or not next_w:
                continue
            gap = next_w[0][1] - prev_w[-1][2]
            verdict = ("LONG PAUSE" if gap >= p98 else
                       ("pause" if gap >= p90 else "no break"))
        rows.append(f"- #{cues[i][0]:>3} {mmss(cues[i][2])} gap **{gap:.2f}s** → {verdict} "
                    f"— «…{tail}» + «{head}…»")
        # The only two cases worth a human's time.
        if stops and gap < p90:
            conflicts.append(
                f"- **#{cues[i][0]} {mmss(cues[i][2])} — sentence-ending punctuation but "
                f"no stop in the audio** ({verdict}). Consider comma + lowercase.\n"
                f"  «…{tail}» + «{head}…»")
        elif not stops and gap >= p98:
            conflicts.append(
                f"- **#{cues[i][0]} {mmss(cues[i][2])} — clear stop in the audio "
                f"({gap:.2f}s) but the text runs on.** Consider a period.\n"
                f"  «…{tail}» + «{head}…»")

    # Guard against a speaker who simply never stops. If their longest gap in the
    # whole file is short, then "no pause at this period" is true of EVERY period and
    # flagging them all is noise dressed as evidence. Say there is no signal instead.
    max_gap = inter[-1] if inter else 0.0
    n_stops = sum(1 for i in range(len(cues) - 1)
                  if cues[i][3].rstrip().endswith((".", "!", "?", "…")))
    flagged = sum(1 for c in conflicts if "no stop in the audio" in c)
    no_signal = max_gap < 0.6 or (n_stops and flagged / n_stops > 0.25)
    if no_signal:
        conflicts = []      # neither direction is trustworthy when nobody ever stops
        note = [
            f"> **No usable pause signal in this file.** The speaker's longest gap is "
            f"{max_gap:.2f}s and {flagged} of {n_stops} sentence endings have no stop, "
            f"i.e. they speak continuously.",
            ">",
            "> Propose no punctuation change from timing here, in either direction. A "
            "0.00s gap at one period is not evidence when *every* period in the file is "
            "0.00s — it is not selective. Decide punctuation on grammar, and state in "
            "the report that the pause data was inconclusive for this speaker rather "
            "than quoting a gap as if it singled that boundary out.",
            ""]
    else:
        note = []

    head_lines = pl + ["## Boundaries where punctuation and audio disagree", ""]
    head_lines += note
    head_lines += (conflicts or ["- none"])
    head_lines += ["", f"## All {len(rows)} boundaries", ""] + rows
    open(os.path.join(args.out, "pauses.md"), "w").write("\n".join(head_lines))
    if no_signal:
        print(f"pause signal: NONE (max gap {max_gap:.2f}s) — decide punctuation on grammar")
    print(f"punctuation/audio conflicts: {len(conflicts)}")

    print(f"\n{n} divergences → {args.out}/candidates.md")
    print(f"pause table    → {args.out}/pauses.md")
    if n == 0:
        print("WARNING: zero divergences. Verify the SRT and the audio really match "
              "(wrong file? silent track?) before reporting a clean result.")


if __name__ == "__main__":
    sys.exit(main())
