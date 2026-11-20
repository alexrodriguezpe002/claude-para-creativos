#!/usr/bin/env python3
"""Is this computer ready for the studio's video skills? `run_gates.py --doctor`.

    python3 run_gates.py --doctor                    (Windows: py -3 run_gates.py --doctor)
    python3 run_gates.py --doctor --no-install       only look, install nothing
    python3 run_gates.py --doctor --no-transcribe    skip the two speech tests (faster)

Checks, in order, what the skills need, and installs what is per user and never in git —
the Python packages (pip, for this user), playwright-core (the library the browser
measurements drive Chrome with, into ~/.studio-video/node), the reframe's two face
models and the speech model — unless --no-install. Everything else it names, with how to
get it:

  python      3.8 or newer, and the packages the skills import: Pillow (balance gate),
              numpy + faster-whisper (caption timing on the voice, second pass, music-bed
              check), fonttools + brotli (CLC's beats), OpenCV (podcast-reframe)
  ffmpeg      ffmpeg + ffprobe (cuts, pauses, loudness) and a self-test of the
              same-shot measure on a synthetic clip (a card may cross a jump cut)
  node        Node.js 20 or newer, npx (HyperFrames and the browser measurements)
  hyperframes `npx hyperframes --version` (the first run downloads it)
  browser     playwright-core + a Chromium: Google Chrome, the one HyperFrames
              downloads for its renders, or Microsoft Edge
  speech      a real transcription of a test sentence this computer speaks itself
              (say on a Mac, SAPI on Windows): with faster-whisper — the model caption
              timing uses, downloaded the first time (~490 MB) — and with HyperFrames'
              own whisper.cpp (`hyperframes init --video` and `hyperframes transcribe`;
              on Windows it may need to build it the first time). If HyperFrames cannot,
              transcribe_fw.py writes the same transcript.json with faster-whisper.
  reframe     the two face models podcast-reframe uses (10 MB, checked byte for byte)
  raw takes   the own doctors of podcast-snippet-select, podcast-rough-cut and
              podcast-audio-clean, only looking (a video that starts from the raw takes or
              the raw episode needs them; the Descript export does not): each one's
              `doctor --fix` installs it the first time — the rough cut's speech model is
              faster-whisper large-v3, ~3 GB
  config      ~/.studio-video/config.json (video_config.py): where the projects,
              the songs and the assets folder are, and the language — asked once
  skills      the sibling skills this one reads (brands with gates.json, captions…)
  assets      the files git does not carry (cle-brand/assets/outro.mp4, cla-brand/assets/teaser-cta-sfx.wav)
  drive       the way hyperframes-render-to-drive reaches Drive (gws, Google Drive for desktop, or a
              delivery/ folder), when that skill is next to this one — never blocking

Exit 0 = ready, 1 = something required is missing (the lines marked ✗ say what).
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _platform as P  # noqa: E402
import video_config as V  # noqa: E402
from _lang import LANG, T  # noqa: E402

OK, BAD, WARN = "\033[32m✓\033[0m", "\033[31m✗\033[0m", "\033[33m!\033[0m"
PY = "py -3" if P.IS_WIN else "python3"

# import name → (required, what it is for)
MODULES = (
    ("PIL", True, T("Pillow — el gate de balance", "Pillow — the balance gate")),
    ("numpy", True, T("numpy — tiempos de captions, music-bed --level, el reencuadre",
                      "numpy — caption timing, music-bed --level, the reframe")),
    ("faster_whisper", True, T("faster-whisper — los tiempos de los captions medidos sobre la voz (sin él: "
                               "WARN timing-unverified), el segundo pase y music-bed check",
                               "faster-whisper — caption timing measured on the voice (without it: WARN "
                               "timing-unverified), the second pass and music-bed check")),
    ("fontTools", "clc-brand", T("fonttools — los beats de CLC miden su texto (el script de proyecto de clc-brand)",
                                "fonttools — CLC's beats measure their own text (clc-brand's project script)")),
    ("brotli", "clc-brand", T("brotli — fontTools lee las fuentes .woff2 de CLC con él",
                             "brotli — fontTools reads CLC's .woff2 fonts with it")),
    ("cv2", "podcast-reframe", T("OpenCV — podcast-reframe encuentra las caras",
                                 "OpenCV — podcast-reframe finds the faces")),
)


def _ver(cmd, rx=r"(\d+(?:\.\d+)+)", timeout=180):
    try:
        out = P.run_text(cmd, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(rx, (out.stdout or "") + (out.stderr or ""))
    return m.group(1) if m else ("?" if out.returncode == 0 else None)


def _speech_tests(line, install):
    """The two real transcriptions of a sentence this computer speaks: faster-whisper, then
    HyperFrames' whisper.cpp. faster-whisper failing is ✗ (caption timing needs it); HyperFrames
    failing is a warning, because transcribe_fw.py writes the same transcript.json."""
    fw = os.path.join(HERE, "transcribe_fw.py")
    if not P.have_module("faster_whisper"):
        line(BAD, T("transcribir", "transcription"), T("sin faster-whisper no se puede probar",
                                                       "cannot be tested without faster-whisper"))
        return
    first = not _fw_model_cached("small")
    if first:
        if not install:
            line(WARN, T("transcribir", "transcription"),
                 T("el modelo small de faster-whisper (~490 MB) no está todavía: corré --doctor sin --no-install",
                   "faster-whisper's small model (~490 MB) is not here yet: run --doctor without --no-install"))
            return
        print(T("    · bajando el modelo small de faster-whisper (~490 MB, una sola vez)…",
                "    · downloading faster-whisper's small model (~490 MB, once)…"), flush=True)
    try:
        out = P.run_text([sys.executable, fw, "--selftest", "--json"], timeout=3600)
        res = json.loads((out.stdout or "").strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as e:
        res = {"ok": False, "error": str(e)[:200]}
    if res.get("ok"):
        speed = (res["audio_s"] / res["transcribe_s"]) if res.get("transcribe_s") else 0
        line(OK, T("transcribir", "transcription"),
             T("faster-whisper %s: oyó %d/%d palabras de una frase de %.1f s en %.1f s (≈%.0f× más rápido que "
               "el audio; modelo cargado en %.1f s) · voz: %s",
               "faster-whisper %s: heard %d/%d words of a %.1f s sentence in %.1f s (≈%.0f× faster than the "
               "audio; model loaded in %.1f s) · voice: %s")
             % (res["model"], res["matched"], res["expected"], res["audio_s"], res["transcribe_s"], speed,
                res["load_s"], res["voice"]))
    elif res.get("voice") is None or "test audio" in str(res.get("error")) or "audio de prueba" in str(res.get("error")):
        line(WARN, T("transcribir", "transcription"), T("no probado: %s", "not tested: %s") % res.get("error"))
    elif res.get("transcribe_s") is not None:
        # the model loaded and ran: the engine works; the computer's voice may not be an English one
        line(WARN, T("transcribir", "transcription"),
             T("faster-whisper corre (modelo cargado en %.1f s) pero oyó otra cosa: «%s» — ¿la voz de la computadora no "
               "es en inglés? Probalo con un video real", "faster-whisper runs (model loaded in %.1f s) but heard "
               "something else: “%s” — is the computer's voice not an English one? Check it on a real video")
             % (res.get("load_s") or 0, (res.get("heard") or "")[:80]))
    else:
        line(BAD, T("transcribir", "transcription"), "faster-whisper: %s%s" % (
            res.get("error"), (" · " + T("oyó «%s»", "heard “%s”") % res.get("heard")) if res.get("heard") else ""))
        return
    # HyperFrames' own transcription (whisper.cpp), on the same kind of clip
    npx = P.npx_command()
    if not npx:
        return
    tmp = tempfile.mkdtemp(prefix="dcv-hf-asr-")
    try:
        sys.path.insert(0, HERE)
        import transcribe_fw as TF
        wav = os.path.join(tmp, "selftest.wav")
        ok, how = TF.speak(TF.SELFTEST_TEXT, wav)
        if not ok:
            return
        t0 = time.time()
        try:
            out = P.run_text(npx + ["--yes", "hyperframes", "transcribe", wav, "--model", "small.en", "--language",
                                    "en", "--json", "-d", tmp], timeout=3600, cwd=tmp)
            tail = ((out.stderr or "") + (out.stdout or "")).strip()
        except (OSError, subprocess.SubprocessError) as e:
            out, tail = None, str(e)
        secs = time.time() - t0
        words = []
        try:
            with open(os.path.join(tmp, "transcript.json"), encoding="utf-8") as fh:
                words = [w.get("text", "") for w in json.load(fh) if isinstance(w, dict)]
        except (OSError, ValueError, TypeError):
            pass
        heard = [TF._norm(w) for w in words]
        matched = sum(1 for w in TF.SELFTEST_WORDS if any(x in heard for x in w.split("|")))
        if out is not None and out.returncode == 0 and matched >= len(TF.SELFTEST_WORDS) // 2:
            line(OK, "hyperframes asr", T("whisper.cpp: oyó %d/%d palabras en %.0f s (la primera vez incluye bajar "
                                          "el modelo y, en Windows, compilarlo)",
                                          "whisper.cpp: heard %d/%d words in %.0f s (the first time includes "
                                          "downloading the model and, on Windows, building it)")
                 % (matched, len(TF.SELFTEST_WORDS), secs))
        else:
            line(WARN, "hyperframes asr",
                 T("HyperFrames no pudo transcribir (%s). No bloquea: creá el proyecto con "
                   "`npx hyperframes init <carpeta> --video <archivo> --skip-transcribe` y después "
                   "`%s \"<video-quality-gates>/scripts/transcribe_fw.py\" \"<carpeta>/<video>\"` escribe el "
                   "mismo transcript.json con faster-whisper",
                   "HyperFrames could not transcribe (%s). Not blocking: create the project with "
                   "`npx hyperframes init <folder> --video <file> --skip-transcribe`, then "
                   "`%s \"<video-quality-gates>/scripts/transcribe_fw.py\" \"<folder>/<video>\"` writes the "
                   "same transcript.json with faster-whisper")
                 % ((tail.splitlines()[-1] if tail else T("sin salida", "no output"))[:160], PY))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def _fw_model_cached(name):
    """Is faster-whisper's model already in this user's Hugging Face cache (no download)?"""
    try:
        from huggingface_hub import scan_cache_dir
        return any(r.repo_id == "Systran/faster-whisper-%s" % name for r in scan_cache_dir().repos)
    except Exception:                                # an old huggingface_hub, no cache yet…
        return False


def main(argv):
    install = "--no-install" not in argv
    transcribe = "--no-transcribe" not in argv
    bad = []

    def line(mark, what, detail=""):
        print("  %s %-12s %s" % (mark, what, detail), flush=True)
        if mark == BAD:
            bad.append(what)

    win = " (Windows: py -3)" if P.IS_WIN else ""
    sk = P.skills_dir()
    print(T("the studio video skills — ¿está lista esta computadora?\n",
            "the studio video skills — is this computer ready?\n"))

    # python and its packages (the missing ones installed for this user, in one pip call)
    v = sys.version_info
    line(OK if v >= (3, 8) else BAD, "python", "%d.%d.%d · %s%s" % (v[0], v[1], v[2], sys.executable, win))
    wanted = [(mod, need, why) for mod, need, why in MODULES
              if need is True or (isinstance(need, str) and (sk / need / "SKILL.md").is_file())]
    missing = [mod for mod, _, _ in wanted if not P.have_module(mod)]
    if missing and install and v >= (3, 8):
        ok, msg = P.pip_install([P.PIP_NAMES.get(m, m) for m in missing])
        print("    · %s" % (msg if ok else msg[-300:]))
    for mod, need, why in wanted:
        ok, ver = P.module_version(mod) if P.have_module(mod) else (False, "")
        if ok:
            line(OK, mod, "%s · %s" % (ver, why.split(" — ")[0]))
        else:
            line(BAD, mod, T("falta: %s — %s -m pip install %s", "missing: %s — %s -m pip install %s")
                 % (why, PY, P.PIP_NAMES.get(mod, mod)) + ((" (%s)" % ver) if ver else ""))

    # ffmpeg
    for tool in ("ffmpeg", "ffprobe"):
        path = P.exe(tool)
        vv = _ver([path, "-version"], r"version\s+(\S+)") if path else None
        line(OK if vv else BAD, tool, ("%s · %s" % (vv, path)) if vv else
             T("falta — Windows: winget install Gyan.FFmpeg · Mac: brew install ffmpeg",
               "missing — Windows: winget install Gyan.FFmpeg · Mac: brew install ffmpeg"))

    # the same-shot measure (a caption card may cross a jump cut of the same shot): needs ffmpeg's
    # select + showinfo to hand back the frames on both sides of a cut
    if P.exe("ffmpeg"):
        try:
            import _common
            ok, detail = _common.shot_selftest()
        except Exception as e:                      # a doctor reports, it does not crash
            ok, detail = False, "%s: %s" % (type(e).__name__, e)
        # optional: without it every cut stays a boundary for a caption card, as before — not a missing piece
        line(OK if ok else WARN, T("mismo plano", "same shot"), detail if ok else
             detail + T(" — sin esto ninguna tarjeta puede cruzar un corte de salto (todos son frontera)",
                        " — without it no card may cross a jump cut (every cut is a boundary)"))

    # node + npx
    node = P.node_command()
    nv = _ver(node + ["--version"]) if node else None
    major = int(nv.split(".")[0]) if nv and nv[0].isdigit() else 0
    line(OK if major >= 20 else BAD, "node", ("%s · %s" % (nv, node[0])) if nv else
         T("falta — Node.js LTS (nodejs.org; Windows: winget install OpenJS.NodeJS.LTS)",
           "missing — Node.js LTS (nodejs.org; Windows: winget install OpenJS.NodeJS.LTS)"))
    npx = P.npx_command()
    line(OK if npx else BAD, "npx", " ".join(npx) if npx else T("falta (viene con Node.js)",
                                                                  "missing (it comes with Node.js)"))

    # hyperframes
    if npx:
        hv = _ver(npx + ["--yes", "hyperframes", "--version"], timeout=900)   # the first run downloads it
        line(OK if hv else BAD, "hyperframes", hv or T("npx hyperframes --version no respondió",
                                                       "npx hyperframes --version did not answer"))
    else:
        line(BAD, "hyperframes", T("sin npx no corre", "cannot run without npx"))

    # browser
    if node:
        rep = P.browser_report()
        if not rep.get("playwright") and install:
            ok, msg = P.install_playwright()
            print("    · %s" % msg)
            rep = P.browser_report()
        pw = rep.get("playwright")
        line(OK if pw else BAD, "playwright", ("%s · %s" % (rep.get("version") or "?", P.tilde(pw))) if pw else
             T("falta — run_gates.py --doctor lo instala en %s", "missing — run_gates.py --doctor installs it in %s")
             % P.tilde(P.node_dir()))
        br = rep.get("browser")
        line(OK if br else BAD, T("navegador", "browser"), P.tilde(br) if br else
             (rep.get("error") or T("ningún Chromium", "no Chromium")) + T(" — instalá Google Chrome",
                                                                          " — install Google Chrome"))
    else:
        line(BAD, "playwright", T("sin Node.js no hay medición en el navegador",
                                  "without Node.js there is no browser measurement"))

    # speech: a real transcription with each engine the skills use
    if transcribe:
        _speech_tests(line, install)
    else:
        line(WARN, T("transcribir", "transcription"), T("no probado (--no-transcribe)", "not tested (--no-transcribe)"))

    # the reframe's face models (podcast-reframe, when it is next to this skill)
    rf = sk / "podcast-reframe" / "scripts"
    if (rf / "reframe.py").is_file():
        try:
            sys.path.insert(0, str(rf))
            from reframelib import models as RM
            if install and P.have_module("cv2"):
                for n in RM.missing():
                    try:
                        RM.path(n)
                    except Exception as e:          # offline, a proxy: said below
                        print("    · %s" % str(e).splitlines()[0])
            gone = RM.missing()
            line(OK if not gone else BAD, T("caras", "face models"),
                 (T("los 2 modelos de podcast-reframe · %s", "podcast-reframe's 2 models · %s")
                  % P.tilde(RM.cache_dir())) if not gone else
                 T("faltan %s — reframe.py doctor --fix los baja (10 MB)", "missing %s — reframe.py doctor --fix "
                   "downloads them (10 MB)") % ", ".join(gone))
        except Exception as e:                      # a doctor reports, it does not crash
            line(WARN, T("caras", "face models"), "%s: %s" % (type(e).__name__, e))

    # the steps from the raw takes: each skill's own doctor, only looking (a WARN, never a ✗:
    # a video made from the Descript export does not need them)
    for skill, script, args, first in (
            ("podcast-snippet-select", "doctor.py", [], "doctor.py --fix"),
            ("podcast-rough-cut", "roughcut.py", ["doctor"],
             T("roughcut.py doctor --fix (baja faster-whisper large-v3, ~3 GB)",
               "roughcut.py doctor --fix (downloads faster-whisper large-v3, ~3 GB)")),
            ("podcast-audio-clean", "audio_clean.py", ["doctor"],
             T("audio_clean.py doctor --fix (deep-filter, 27 MB)", "audio_clean.py doctor --fix (deep-filter, 27 MB)"))):
        f = sk / skill / "scripts" / script
        if not f.is_file():
            continue
        try:
            r = subprocess.run([sys.executable, str(f)] + args, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300,
                               env=dict(os.environ, STUDIO_LANG=LANG))
            ok = r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        line(OK if ok else WARN, skill.replace("podcast-", ""),
             T("listo (desde el material en bruto)", "ready (from the raw takes)") if ok else
             T("falta algo — solo para empezar desde el material en bruto; la primera vez: %s",
               "something is missing — only to start from the raw takes; the first time: %s") % first)

    # config
    cfg = V.load()
    if cfg is None:
        line(BAD, "config", T("falta %s — se pregunta una vez (video_config.py show)",
                              "missing %s — asked once (video_config.py show)") % P.tilde(V.config_path()))
    else:
        roots = []
        for c in sorted(V.CLIENTS):
            r = V.client_root(c, cfg)
            if r and r.is_dir():
                roots.append(c)
        line(OK if roots else WARN, "config", T("%s · carpetas presentes: %s", "%s · folders present: %s")
             % (P.tilde(V.config_path()), ", ".join(roots) or T("ninguna (¿disco o Drive sin montar?)",
                                                                 "none (a disk or Drive not mounted?)")))
        line(OK, T("idioma", "language"), T("%s · lo cambia video_config.py set lang en|es",
                                             "%s · video_config.py set lang en|es changes it") % LANG)
        for c in V.MUSIC_CLIENTS:
            d = V.music_dir(c, cfg)
            if d and d.is_dir():
                line(OK, T("música ", "music ") + c, str(d))
            elif d:
                line(WARN, T("música ", "music ") + c,
                     T("la carpeta del config no existe acá: %s (video_config.py set-music %s …)",
                       "the config's folder does not exist here: %s (video_config.py set-music %s …)") % (d, c))
            else:
                line(WARN, T("música ", "music ") + c,
                     T("sin carpeta de canciones (video_config.py set-music %s …)",
                       "no song folder (video_config.py set-music %s …)") % c + " — " + V.music_hint(c))

    # the way to Drive of hyperframes-render-to-drive, when it is next to this skill (never a ✗:
    # without gws or Drive for desktop the MP4s go to a delivery/ folder to drag into Drive)
    rd = sk / "hyperframes-render-to-drive" / "scripts" / "render_to_drive.py"
    if rd.is_file():
        try:
            sys.path.insert(0, str(rd.parent))
            import render_to_drive as RD
            _, st = RD.pick_way(cfg)
            way, ds = st.get("way"), st.get("desktop") or {}
            line(OK if way in ("api", "desktop") else WARN, "drive",
                 (T("API (gws · %s)", "API (gws · %s)") % (st.get("api") or {}).get("user")) if way == "api" else
                 (T("Drive para escritorio · %s", "Drive for desktop · %s") % ds.get("root")
                  + ("" if ds.get("source") == "config" else T(" (encontrado; guardalo: video_config.py set drive_root …)",
                                                               " (found; keep it: video_config.py set drive_root …)")))
                 if way == "desktop" else
                 T("ni gws ni Drive para escritorio: hyperframes-render-to-drive deja los MP4 en delivery/ para "
                   "arrastrarlos a Drive", "neither gws nor Drive for desktop: hyperframes-render-to-drive leaves the "
                   "MP4s in delivery/ to drag into Drive"))
        except Exception as e:                      # a doctor reports, it does not crash
            line(WARN, "drive", "%s: %s" % (type(e).__name__, e))

    # sibling skills
    brands = sorted(p.parent.parent.name for p in sk.glob("*-brand/references/gates.json"))
    line(OK if brands else BAD, T("perfiles", "profiles"), "%s · %s" % (", ".join(brands) or T("ninguno", "none"),
                                                                       P.tilde(sk)))
    for need in ("podcast-captions", "podcast-beat-plan", "podcast-beat-build"):
        here = (sk / need / "SKILL.md").is_file()
        line(OK if here else WARN, need, T("junto a esta skill", "next to this skill") if here else
             T("no está junto a esta skill", "not next to this skill"))

    # assets that are not in git
    for rel in V.ASSETS:
        if not (sk / rel.split("/")[0]).is_dir():
            continue
        p, how = V.asset(rel, cfg)
        line(OK if p else WARN, "asset", ("%s (%s)" % (rel, how)) if p else
             T("%s: %s — bajá la carpeta de Drive «%s» y video_config.py set assets_root …",
               "%s: %s — download the Drive folder “%s” and video_config.py set assets_root …")
             % (rel, how, V.ASSETS_DRIVE_NAME))

    learned = P.user_dir() / "learned"
    owner = (P.user_dir() / "OWNER").is_file()
    line(OK, T("aprendido", "learned"), T("%s · dueño de las skills: %s", "%s · owner of the skills: %s")
         % (P.tilde(learned), T("SÍ", "YES") if owner else "no"))

    print("")
    if bad:
        print(T("\033[31mFALTA\033[0m  %s", "\033[31mMISSING\033[0m  %s") % ", ".join(bad))
        return 1
    print(T("\033[32mLISTA\033[0m  todo lo que los gates necesitan está en esta computadora",
            "\033[32mREADY\033[0m  everything the skills need is on this computer"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
