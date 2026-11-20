#!/usr/bin/env python3
"""Run every gate over a project and print one verdict.

    python3 run_gates.py <project-dir> [--keep] [--solo] [--fast]
    python3 run_gates.py --doctor [--no-install]

On Windows run `py -3` (or `python`) where this says python3.

--doctor  is this computer ready: Python, Pillow, ffmpeg, Node, HyperFrames, the
        browser library (installed for this user on first use, never in git), a
        Chromium to drive, this computer's config (video_config.py) and the sibling
        skills. Exit 0 = ready.

--keep  leave the measured frames in <project>/snapshots/ to show the user
--solo  check variety against this project only, not the whole episode
--fast  skip the caption width and text-fit browser measurements (reported as
        unverified, never as PASS) and the balance render (~40s per beat) — but
        only while the layout is the one the last balance run measured and that
        run passed. Any change that can move a pixel on a beat (an element added,
        removed, moved or resized; a style; a timeline time) re-runs the balance
        gate and the text-fit measurement even with --fast. Caption edits do not.

Exit code 0 = clean, 1 = at least one FAIL, 2 = not measured (no client profile
matches the path and GATES_CLIENT names none). A FAIL blocks: fix it, or take
the finding to the user with the frame that shows it. Never continue past a red
gate on your own judgement — video-quality-gates SKILL.md, "The loop".
"""

import os
import subprocess
import sys
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _platform  # noqa: E402,F401 — UTF-8 console (the bars and arrows below) and the Windows PATH
GATES = [
    ("build", "check_build.py", []),
    ("text-size", "check_text_size.py", []),
    ("text-fit", "check_text_fit.py", []),
    ("captions", "check_captions.py", []),
    ("variety", "check_variety.py", []),
    ("exits", "check_exits.py", []),
    ("balance", "check_balance.py", []),
]


def main():
    if "--doctor" in sys.argv:
        import doctor
        return doctor.main(sys.argv[1:])
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    project = os.path.abspath(sys.argv[1])
    keep = "--keep" in sys.argv
    solo = "--solo" in sys.argv
    fast = "--fast" in sys.argv

    gates = list(GATES)
    import _profile
    try:
        prof = _profile.load(project)
    except SystemExit:
        # no client profile matches and GATES_CLIENT names none: _profile printed
        # why. Nothing was measured — that is not a PASS.
        print("─" * 62)
        print(T("\033[31mSIN MEDIR\033[0m  %s  ·  ningún perfil de cliente (código 2)", "\033[31mNOT MEASURED\033[0m  %s  ·  no client profile (exit 2)")
              % os.path.basename(project))
        print("─" * 62)
        return 2
    try:
        learned = _profile.learned_lines(prof)
        print("\033[90m%s\033[0m%s\n" % (_profile.describe(prof),
                                         "".join("\n" + l for l in learned)), flush=True)
        if prof.get("hf_check"):
            # the framework's own check, blocking — only for clients whose profile asks
            gates.insert(1, ("hf-check", "check_hf.py", []))
    except Exception:
        pass
    failed, ran = [], []
    # --fast re-measures whatever a layout change can break: the balance render
    # and the text-fit measurement, whenever the composition is not the one the
    # last balance run measured (captions and Studio ids left out of the print)
    unchanged, st, lh = False, None, None
    if fast:
        import _common as C
        try:
            lh = C.layout_hash(C.read_html(project))
        except OSError:
            lh = None
        st = C.balance_state(project)
        unchanged = bool(st and lh and st.get("layout") == lh and st.get("status") in ("PASS", "WARN"))
    for name, script, extra in gates:
        if name == "balance" and fast:
            if unchanged:
                print(T("\033[90m· balance: el layout es el que se midió el %s (%s, %s frame(s)) — "
                      "no lo vuelvo a renderizar con --fast\033[0m\n",
                        "\033[90m· balance: the layout is the one measured on %s (%s, %s frame(s)) — "
                      "not rendering it again with --fast\033[0m\n")
                      % (st.get("when"), st.get("status"), st.get("frames")))
                ran.append(T("balance (sin cambios)", "balance (unchanged)"))
                continue
            print(T("\033[90m· balance: %s — lo mido aunque sea --fast\033[0m", "\033[90m· balance: %s — measuring it even with --fast\033[0m")
                  % (T("todavía no tiene una medición", "no measurement yet") if not st else
                     T("la última medición falló", "the last measurement failed") if st.get("layout") == lh else
                     T("el layout cambió desde la última medición", "the layout changed since the last measurement")), flush=True)
        if name == "text-fit" and fast and not unchanged:
            print(T("\033[90m· text-fit: el layout no es el de la última medición — lo mido en el "
                  "navegador aunque sea --fast\033[0m",
                    "\033[90m· text-fit: the layout is not the one last measured — measuring it in the "
                  "browser even with --fast\033[0m"), flush=True)
        argv = [sys.executable, os.path.join(HERE, script), project] + extra
        if name == "balance" and keep:
            argv.append("--keep")
        if name == "variety" and solo:
            argv.append("--solo")
        if fast and (name == "captions" or (name == "text-fit" and unchanged)):
            argv.append("--fast")     # skips the browser measurement
        code = subprocess.call(argv, cwd=HERE)
        ran.append(name)
        if code == 1:
            failed.append(name)
        elif code not in (0, 1):
            failed.append(name + " (error)")
        print("")

    bar = "─" * 62
    print(bar)
    if failed:
        print(T("\033[31mBLOQUEADO\033[0m  %s  ·  falla: %s", "\033[31mBLOCKED\033[0m  %s  ·  failed: %s")
              % (os.path.basename(project), ", ".join(failed)))
        print(T("No sigas por tu cuenta: arreglá lo que se pueda arreglar sin cambiar", "Do not carry on alone: fix what can be fixed without changing"))
        print(T("una decisión creativa, y para el resto sacá el frame y preguntale al usuario", "a creative decision, and for the rest grab the frame and ask the user"))
        print(T("(video-quality-gates SKILL.md, «The loop»).", "(video-quality-gates SKILL.md, “The loop”)."))
    else:
        print(T("\033[32mLIMPIO\033[0m  %s  ·  %d gates", "\033[32mCLEAN\033[0m  %s  ·  %d gates") % (os.path.basename(project), len(ran)))
    print(bar)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
