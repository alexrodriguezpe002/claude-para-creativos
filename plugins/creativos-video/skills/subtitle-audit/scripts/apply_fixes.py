#!/usr/bin/env python3
"""Write the corrected subtitle file.

Never touches the original: it writes a NEW file next to it. Preserves the
byte-level shape editors depend on — UTF-8 BOM, CRLF line endings, every cue
number and every timecode untouched. Only cue TEXT changes.

fixes.json is a list of objects:
  [{"cue": 58, "old": "Está demasiado prestablecido",
                "new": "Está demasiado preestablecido",
                "type": "spelling", "note": "RAE: preestablecido"}]

"old" must match the cue's current text EXACTLY. Any mismatch is reported and
that fix is NOT applied — it never silently edits the wrong line. Report the
applied/total count to the user verbatim from this script's output; do not
state from memory that a change landed.
"""
import argparse, json, os, re, sys


def parse(path):
    raw = open(path, encoding="utf-8-sig").read().replace("\r\n", "\n")
    order, cues = [], {}
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = block.strip().split("\n")
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        idx = int(lines[0].strip())
        cues[idx] = [lines[1], "\n".join(lines[2:])]
        order.append(idx)
    return order, cues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--srt", required=True)
    ap.add_argument("--fixes", required=True)
    ap.add_argument("--out", default=None,
                    help="default: '<name> CORREGIDO.srt' beside the original")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    order, cues = parse(args.srt)
    fixes = json.load(open(args.fixes, encoding="utf-8"))
    out = args.out or os.path.join(
        os.path.dirname(args.srt),
        os.path.splitext(os.path.basename(args.srt))[0] + " CORREGIDO.srt")
    if os.path.abspath(out) == os.path.abspath(args.srt):
        sys.exit("REFUSED: --out is the original file. Write a new file.")

    applied, failed = 0, []
    for f in fixes:
        idx = int(f["cue"])
        if idx not in cues:
            failed.append((idx, "<cue does not exist>", f["old"]))
            continue
        cur = cues[idx][1].strip()
        if cur == f["old"].strip():
            if not args.dry_run:
                cues[idx][1] = f["new"]
            applied += 1
        else:
            failed.append((idx, cur, f["old"]))

    print(f"Applied {applied}/{len(fixes)} fixes")
    for idx, cur, expected in failed:
        print(f"  NOT APPLIED #{idx}: file has «{cur}» but fix expected «{expected}»")
    if failed:
        print("  → fix the cue numbers or the 'old' strings and re-run. "
              "Do not report these as applied.")

    if args.dry_run:
        print("(dry run — nothing written)")
        return

    body = "\n".join(f"{i}\n{cues[i][0]}\n{cues[i][1]}\n" for i in order)
    open(out, "w", encoding="utf-8-sig", newline="").write(
        "\r\n".join(x.replace("\n", "\r\n") for x in body.split("\n")))

    # Prove nothing but the intended text moved.
    o_order, o_cues = parse(args.srt)
    n_order, n_cues = parse(out)
    assert o_order == n_order, "cue order changed"
    drift = [i for i in o_order if o_cues[i][0] != n_cues[i][0]]
    changed = [i for i in o_order if o_cues[i][1] != n_cues[i][1]]
    print(f"Wrote {out}")
    print(f"  cues: {len(n_order)} · timecodes changed: {len(drift)} (must be 0) "
          f"· text changed: {len(changed)}")
    if drift:
        sys.exit("ERROR: timecodes drifted — do not deliver this file.")


if __name__ == "__main__":
    sys.exit(main())
