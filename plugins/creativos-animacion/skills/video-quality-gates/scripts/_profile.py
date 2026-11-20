"""Client profile for the gates: the numbers and switches that differ by client.

The checks are client-neutral. What changes from one client to another — the
type floor, the beat caps, whether a beat carries coordinate crosses, how
content is told apart from the ground on a rendered frame — lives in the
client's own data skill, in `<client>-brand/references/gates.json`, and is
merged over the defaults below.

The defaults are CLA's numbers, unchanged: CLA was the first client built on
these gates, and a project with no profile has to measure exactly as it did
before profiles existed. The one exception is the client's spellings
(`captions.vocabulary`): the defaults carry none, each brand brings its own.

A profile is chosen by the project's path (`match.path_contains`, or the client's
folder name in this computer's `~/.studio-video/config.json` — video_config.py),
or forced with GATES_CLIENT=<client>. No client is named in this file or in any gate.

A project that matches no profile does not get measured with the defaults by
accident: `load()` stops with exit code 2 and says how to choose one. A copy in
a scratch folder, or a client that has no `gates.json` yet, used to pass and
fail against another client's numbers without a word. GATES_CLIENT=default asks
for the defaults on purpose.

What this computer learned goes last. A number the user asked for once and
that `learned.py add … --set` recorded lives in
`~/.studio-video/learned/<client>.gates.json` (Path.home(), so the same on
Windows) and is merged over the client's profile — every gate, and the caption
grouping script, then works with it, and says so in yellow. Deleting the file
gives back the client's own numbers. GATES_NO_LEARNED=1 ignores it (a
regression run, or the owner reviewing what someone else learned).
"""

import copy
import glob
import json
import os
import sys
from pathlib import Path

import _platform as P
from _lang import T  # noqa: E402 — the user's language (video_config.py set lang)

# The brands are the sibling skills of this one (`<client>-brand`), wherever the
# skills live: ~/.claude/skills/ on the owner's Mac, the plugin's skills/ folder on
# any other computer. GATES_SKILLS_DIR points at another copy (a frozen regression set).
SKILLS = str(P.skills_dir())

DEFAULTS = {
    "client": "default",
    "source": None,
    # How a graphic beat is recognised in index.html: the id of its container.
    "beat_id": r"beat-[\w-]+",
    # The CSS selector the browser measurements use to find the same containers.
    "beat_selector": '[id^="beat-"]',
    "build": {
        "texture_required": True,
        "texture_re": (r'feturbulence|repeating-linear-gradient|clatexture|topofilter'
                       r'|id="[^"]*(?:topo|tex|grain)|class="[^"]*(?:topo|texture|grid-tex)'),
        "texture_builder_re": r"clatexture",
        "coord_crosses": [4, 9],
        "green_tokens": ["--g500", "--g600", "--g700", "--g400", "--g300", "--g200",
                         "--g100", "--g800", "--g900", "--green", "#4fb3ff", "#2f8fd8"],
        "ground": {"selector": r"html\s*,\s*body", "allowed": ["var(--ink)", "#000"],
                   "message": T("el fondo por defecto es --ink (#000000) 100% opaco", "the default ground is --ink (#000000), 100% opaque")},
        "opaque_beats": False,
        "svg_origin_check": False,
    },
    "text": {
        "floor_portrait": 48.0,
        "comfort_portrait": 56.0,
        "floor_landscape": 24.0,
        "max_sizes_per_beat": 3,
        "exempt_classes": ["eyebrow"],
        # A floor per ROLE on top of the general floor: a headline, a takeaway line,
        # a primary label each have a size under which they stop reading as what
        # they are, and that size is higher than the floor of the smallest label.
        # A list of {"role", "class_re", "min"}: any element whose own class, or the
        # class of a container it sits in inside the beat, matches `class_re` must
        # measure at least `min` px. A landscape (teaser) frame is held to a role
        # only when it gives `min_landscape`. [] switches it off.
        "role_floors": [],
    },
    "captions": {
        "max_words_snippet": 5,
        "max_words_teaser": 10,
        "min_words": 3,
        "min_dur_fail": 0.5,
        "min_dur_warn": 0.7,
        # The client's spellings, checked in captions and beat text alike — the brand's
        # gates.json brings its own list: [{"re": <regex>, "flags": "i", "fix": "<the
        # right spelling>"}], e.g. {"re": r"\bweb[\s\-]site\b", "flags": "i", "fix":
        # "website (one word)"}. [] = no spelling rule.
        "vocabulary": [],
        # Nothing waits on screen (the editor, CLB ep3, 2026-10-01, for every video): a
        # pause of `min` seconds or more inside a card fails, and a card that
        # opens more than `early_tol` before the voice comes back after one
        # warns. Pauses are measured on the clip's own audio (10 ms RMS under an
        # adaptive floor — _common.voice_pauses), not with silencedetect, which
        # lists none under CLA's room tone. null switches the check off.
        "pauses": {"min": 0.40, "early_tol": 0.10},
        # How a card enters and leaves when the brand animates it instead of cutting
        # (the shared rule is a hard cut — `tl.set`). null = the shared rule. A
        # brand that animates declares it once and the caption gate checks the
        # project's own tween calls against the declaration (duration, ease and
        # offset), instead of calling every animated card a fade:
        #   {"mode": "fade",
        #    "in":  {"duration": 0.25, "ease": "expo.out",  "y_from": -14},
        #    "out": {"duration": 0.18, "ease": "power3.in", "y_to": 10},
        #    "applies_to": ["snippet", "teaser"]}
        # An `in`/`out` left out means that side is a hard cut. `mode: "per_word"`
        # is a brand whose words enter one by one (the check is the same).
        "entrance": None,
        # A card ending on a connector followed by a comma, semicolon, colon or dash
        # ("what's going on,") has closed its clause: it is not hanging. False keeps
        # the strict reading (CLA, CLB); true is for a brand whose speech has a lot
        # of "on,", "in,", "of," closing a phrase.
        "connector_comma_closes": False,
        # Grouping only: a word that straddles a cut goes BEFORE it when the clip's own
        # audio is silent from inside the word up to the cut (the voice ended, Whisper
        # stretched the word over the silence). False keeps "the first word after the
        # cut" — CLB ep3 S2's "Everyone" straddles a cut inside the pause that precedes
        # it and belongs after the cut, which the same evidence would send before it.
        "cut_word_by_voice": False,
        # A card may cross a JUMP CUT of the same shot — never a camera change or a change
        # of speaker (the editor, 2026-10-03, "sí, para todos") — and only when splitting it at
        # the cut would leave a single dangling word or a flash (a card under
        # `min_dur_fail`). "Same shot" is measured: the frames on the two sides of the cut,
        # downscaled to gray, share most of their pixels — `static` is the share that
        # changed by 8 levels or less over the whole frame, `edge_static` the same over the
        # frame's outer ring (the background, not the person), `mean_diff` the mean change.
        # Calibrated 2026-10-03 on 59 jump cuts of CLB ep2/ep3 and CLE ep2 (static 0.38-0.95,
        # edge 0.47-1.00, mean 0.007-0.131) against 11 camera and speaker changes of CLA ep4
        # and CLD ep1 (static 0.04-0.08, edge 0.03-0.10, mean 0.248-0.455): 59 of 59 jump cuts
        # and 0 of 11 camera changes read as the same shot with these limits, and each limit
        # sits well inside the gap (_common.py, "Is a cut the same shot?"). `same_shot: false` switches the permission off (every
        # cut is a boundary again); a cut scene detection lists at the profile's
        # `cuts.scene_threshold` is a camera change and is never measured as the same shot.
        "cross_cut": {
            "same_shot": True,
            "static_min": 0.30,
            "edge_static_min": 0.40,
            "mean_diff_max": 0.20,
            # a part is a "flash" under this many seconds; null = captions.min_dur_fail (0.5 s,
            # "never under 0.5 s"). The editor's words were "un parpadeo"; 0.7 (min_dur_warn, the
            # working minimum) would also let a card cross to avoid a merely brief one
            "flash_under": None,
        },
        # What the grouping script (podcast-captions) aims for between the
        # floor and the cap; the gates do not read these.
        "target_words_snippet": 3.5,
        "target_words_teaser": 6.0,
        # Every card opens with its voice, and every said word is on a card (the editor, 2026-10-03,
        # CLC ep1 S3: "some words appear AFTER they are said … some words are missing").
        # Measured on the clip's own voice (word_timing.py: each stretch between pauses heard
        # alone by faster-whisper `model`, short silences re-heard in pieces, every word anchored
        # to where the voice is), never on transcript.json's times. A card is late when it shows
        # after its first word's voice (or after the cut / the beat exit it must wait for) by more
        # than `late_warn` (WARN caption-late-near) or `late_fail` (FAIL caption-late); early when
        # it shows before it by more than `early_warn` / `early_fail` (a card on a cut and the
        # video's first card open early by rule). Under a music bed the measurement has no pauses
        # to anchor to and both become WARN (caption-late-bed / caption-early-bed). Calibrated
        # 2026-10-03: the measurement agrees with large-v3 run the same way within 0.16 s on
        # 91-93 % of the words of five clips (median +0.06 s), so 0.20 s is the first lateness it
        # tells from its own spread; the CLC ep1 S3 rebuild the editor sent back had 11 cards over 0.35 s late (worst 1.87 s),
        # its rebuild with this process none (worst real 0.18 s); every delivered array of the
        # regression set has 1-5 cards over 0.35 s, each one checked by ear to be really late
        # (the same drifting transcript). A said word heard at p >= `missing_p` — or at p >=
        # `doubtful_p` by both this pass and transcript.json — with no card and no declared rule
        # fails (caption-missing-word); a phrase heard less surely warns (caption-doubtful-word).
        # `add_p`: the grouping script adds a word heard this surely that the text lacks.
        # `off: true` skips all of it.
        "timing": {
            "model": "small",
            "language": "en",
            "late_warn": 0.20,
            "late_fail": 0.35,
            "early_warn": 0.35,
            "early_fail": 0.70,
            "missing_p": 0.70,
            "doubtful_p": 0.35,
            "add_p": 0.70,
            "off": False,
        },
    },
    "variety": {
        "open_on_speaker": 5.0,
        "beat_caps": [[60.0, 2], [90.0, 3], [1e9, 4]],
        "max_beat_dur": 8.0,
        "min_gap": 5.0,
        "dead_hold": 2.5,
        # One animation never covers two speakers. true/false for every format, or a
        # value per format — {"snippet": false, "teaser": "detected"}. "detected"
        # counts only the cuts scene detection sees (a speaker change), not the
        # jump cuts listed in cuts.txt: a teaser of two hosts lists the jump cuts
        # inside each host's stretch too, and a beat may cover those.
        "beat_across_cut": True,
        # Two beats of one project never share a ground (background). False = off.
        # With more beats than `ground_unique_up_to` (the brand has only so many
        # grounds) only two in a row may not share one.
        "ground_repeat": False,
        "ground_unique_up_to": 3,
        # A run of beats with no video between them is allowed only when the
        # speaker stays on screen in a picture-in-picture for the whole run.
        "contiguous_with_pip": False,
        "pip_re": None,
        # The last beat either rides out with the video or leaves enough face
        # time after it; ending a moment before the end flashes the video.
        "end_flash": None,
        # A beat that runs to the end of the video with no speaker visible.
        "end_on_graphic": False,
        "scheme_rotation": None,
    },
    # cut_out: the brand's beats leave by a straight hard cut with no retreat first
    # (a declared exception to the mirror). true = a beat with no retreat is a note,
    # not beat-exit-hard-cut; a beat that does retreat is still checked.
    "exits": {"cut_out": False},
    # A fixed end card appended after the speech (a brand outro): {"id_re": "outro"}
    # names the clip's element ids. The end checks (caption-early-end, caption-overrun,
    # end-flash, a beat that rides out with the video, the grouping script's last
    # card) then measure against where the card starts, not against the whole
    # composition. null = the composition ends with the speech.
    "outro": None,
    # Camera cuts: the project's own cuts.txt (one time in seconds per line) plus
    # ffmpeg scene detection at this threshold, merged. 0.35 is calibrated on
    # CLA's speaker changes. `require_list` is for a client whose cuts scene
    # detection cannot see (jump cuts inside one take): without cuts.txt the
    # caption gate then says the cuts went unchecked instead of passing.
    "cuts": {
        "scene_threshold": 0.35,
        "require_list": False,
    },
    "balance": {
        "ink": {"mode": "luminance", "threshold": 80},
        "green_max": 0.10,
        "outer_tol": 0.025,
        "side_tol": 0.150,
        "gap_abs": 200,
        "gap_share": 0.25,
    },
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _profiles():
    for path in sorted(glob.glob(os.path.join(SKILLS, "*-brand", "references", "gates.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        data["source"] = path
        yield data


def load(project_dir, strict=True):
    """The merged profile for one project.

    strict (every gate, through `_common.project_dir`): no matching profile, or a
    GATES_CLIENT that names none, prints why and exits with code 2 — the gate did
    not run, which is neither a PASS nor a FAIL. strict=False returns the
    defaults silently; it is only for module import, before the project is known.
    """
    forced = os.environ.get("GATES_CLIENT", "").strip().lower()
    if forced == "default":
        out = copy.deepcopy(DEFAULTS)
        out["forced_default"] = True
        return out
    # compared with forward slashes and in capitals: a Windows path
    # (D:\\the studio\\CLIENT A\\ep4\\…) matches the same hints as a Mac one
    where = _norm(os.path.abspath(project_dir)) + "/"
    folders = _config_folders()
    seen = []
    for data in _profiles():
        client = str(data.get("client", "")).lower()
        hints = list((data.get("match") or {}).get("path_contains") or [])
        if folders.get(client):
            hints.append(folders[client])
        seen.append((client, hints))
        if forced:
            if client == forced:
                return apply_learned(_merge(DEFAULTS, data))
            continue
        if any(_norm(h) in where for h in hints):
            return apply_learned(_merge(DEFAULTS, data))
    if strict:
        _stop(project_dir, forced, seen)
    return copy.deepcopy(DEFAULTS)


def _norm(path):
    return str(path).replace("\\", "/").upper()


def _config_folders():
    """{client: path hint} from this computer's config.json ('/NAME/' or a full path), or {}."""
    try:
        import video_config
        return video_config.client_folders()
    except Exception:
        return {}


# ── What this computer learned ───────────────────────────────────────────────

def learned_dir():
    """Where this computer keeps what its user taught the skills — one file per client."""
    env = os.environ.get("STUDIO_LEARNED_DIR", "").strip()
    return Path(env) if env else P.user_dir() / "learned"


def _get(d, path):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            raise KeyError(path)
        cur = cur[k]
    return cur


def _set(d, path, value):
    keys = path.split(".")
    cur = d
    for k in keys[:-1]:
        if not isinstance(cur.get(k), dict):
            cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value


def learned_overrides(client):
    """Active numeric overrides learned on this computer for one client: a list of dicts."""
    p = learned_dir() / ("%s.gates.json" % client)
    if not p.is_file():
        return [], p
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.stderr.write(T("\033[33mAPRENDIDO ilegible\033[0m %s: %s — no lo apliqué\n", "\033[33mLEARNED unreadable\033[0m %s: %s — not applied\n") % (p, e))
        return [], p
    out = [o for o in data.get("overrides") or []
           if o.get("status", "active") == "active" and o.get("path")]
    return out, p


def apply_learned(prof):
    """Merge this computer's learned overrides over a client's profile, and remember which."""
    if os.environ.get("GATES_NO_LEARNED"):
        return prof
    client = str(prof.get("client", "")).lower()
    if not client or client == "default":
        return prof
    overs, path = learned_overrides(client)
    applied = []
    for o in overs:
        try:
            brand = _get(prof, o["path"])
        except KeyError:
            brand = None
        _set(prof, o["path"], o.get("value"))
        applied.append(dict(o, brand=brand, file=str(path)))
    if applied:
        prof["learned"] = applied
    return prof


# The profile sections each gate reads, to print only the overrides it used.
GATE_SECTIONS = {
    "build": ("build", "beat_id", "beat_selector"),
    "hf-check": ("hf_check",),
    "text-size": ("text",),
    "text-fit": ("text",),
    "captions": ("captions", "cuts", "transcript_tokens", "outro"),
    "variety": ("variety", "cuts", "beat_id", "outro"),
    "exits": ("exits", "outro"),
    "balance": ("balance",),
    "grouping": ("captions", "cuts", "transcript_tokens", "outro"),
}


def learned_lines(p, gate=None):
    """The yellow lines that say a learned number is in force — none when nothing was learned."""
    out = []
    secs = GATE_SECTIONS.get(gate) if gate else None
    for o in p.get("learned") or []:
        top = o["path"].split(".")[0]
        if secs and top not in secs:
            continue
        line = (T("\033[33mAPRENDIDO %s (%s): %s %s → %s\033[0m  · %s", "\033[33mLEARNED %s (%s): %s %s → %s\033[0m  · %s")
                % (o.get("id", "?"), o.get("date", "?"), o["path"],
                   json.dumps(o.get("brand")), json.dumps(o.get("value")),
                   o["file"].replace(str(Path.home()), "~")))
        out.append(line)
        if o.get("brand") == o.get("value"):
            out.append(T("  \033[33m└ la marca ya dice lo mismo: el aprendido sobra (learned.py prune)\033[0m", "  \033[33m└ the brand already says the same: the learned value is redundant (learned.py prune)\033[0m"))
        elif "was" in o and o.get("was") != o.get("brand"):
            out.append(T("  \033[33m└ OJO: la marca cambió este número desde que se aprendió (era %s, ahora %s) — "
                       "se aplica el aprendido; confirmalo con quien lo pidió\033[0m",
                         "  \033[33m└ WARNING: the brand changed this number since it was learned (was %s, now %s) — "
                       "the learned value applies; confirm it with whoever asked for it\033[0m")
                       % (json.dumps(o.get("was")), json.dumps(o.get("brand"))))
    return out


def _stop(project_dir, forced, seen):
    known = ", ".join("%s (%s)" % (c, " · ".join(h) or T("sin ruta", "no path")) for c, h in seen) or T("ninguno", "none")
    w = sys.stderr.write
    w(T("\n\033[31mSIN PERFIL DE CLIENTE — los gates no corrieron (código 2).\033[0m\n", "\n\033[31mNO CLIENT PROFILE — the gates did not run (exit 2).\033[0m\n"))
    if forced:
        w(T("  GATES_CLIENT=%s no es ningún perfil. Perfiles: %s.\n", "  GATES_CLIENT=%s is not a profile. Profiles: %s.\n") % (forced, known))
    else:
        w(T("  %s\n  no coincide con ningún perfil. Perfiles: %s.\n", "  %s\n  does not match any profile. Profiles: %s.\n")
          % (os.path.abspath(project_dir), known))
    w(T("  Medir con los números de otro cliente da PASS y FAIL falsos. Elegí uno:\n"
      "    GATES_CLIENT=<cliente> python3 run_gates.py \"<proyecto>\"   (p. ej. una copia en scratch)\n"
      "    GATES_CLIENT=default python3 run_gates.py \"<proyecto>\"    (los números por defecto, a propósito)\n"
      "  (en Windows, py -3 en vez de python3). Si el proyecto está en la carpeta del\n"
      "  cliente pero con otro nombre, decláralo una vez: video_config.py set-folder <cliente> \"<carpeta>\".\n"
      "  Un cliente nuevo necesita su <cliente>-brand/references/gates.json\n"
      "  (video-quality-gates SKILL.md, «Client profiles»).\n\n",
        "  Measuring with another client's numbers gives false PASS and FAIL. Pick one:\n"
      "    GATES_CLIENT=<client> python3 run_gates.py \"<project>\"   (e.g. a copy in scratch)\n"
      "    GATES_CLIENT=default python3 run_gates.py \"<project>\"    (the default numbers, on purpose)\n"
      "  (on Windows, py -3 instead of python3). If the project is in the client's folder\n"
      "  but under another name, declare it once: video_config.py set-folder <client> \"<folder>\".\n"
      "  A new client needs its <client>-brand/references/gates.json\n"
      "  (video-quality-gates SKILL.md, “Client profiles”).\n\n"))
    sys.exit(2)


def describe(p):
    """One line for the gate output: which profile measured this project."""
    if p.get("source"):
        return T("perfil %s (%s)", "profile %s (%s)") % (p["client"], p["source"].replace(os.path.expanduser("~"), "~"))
    if p.get("forced_default"):
        return T("perfil por defecto, pedido con GATES_CLIENT=default (números de CLA)", "default profile, requested with GATES_CLIENT=default (CLA's numbers)")
    return T("perfil por defecto (números de CLA)", "default profile (CLA's numbers)")
