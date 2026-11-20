"""(Copia de video-quality-gates/scripts/_lang.py para el kit v2: si cambias una, cambia la otra.)
The language the scripts speak to the user: English or Spanish, one choice per person.

`lang` in ~/.studio-video/config.json ("en" or "es") — video_config.py asks it on the
first run, `video_config.py set lang es` changes it. With no config, or no `lang` in it, the
messages are in English (a new user); the owner's own computer says "es". STUDIO_LANG
overrides it for one run (tests, a one-off). Only the words change: the gate codes
(`caption-late`), the exit codes, the ##JSON## keys and every file the scripts read back are
the same in both languages.

    from _lang import T
    print(T("no encontré beats", "no beats found"))

The language is resolved once per process and exported as STUDIO_LANG, so the gates that
run_gates.py starts and the browser measurements (Node) speak the same one.
"""

import json
import os
from pathlib import Path

LANGS = ("en", "es")
DEFAULT = "en"


def _config_lang():
    env = os.environ.get("STUDIO_VIDEO_HOME", "").strip()
    home = Path(os.path.expanduser(env)) if env else Path.home() / ".studio-video"
    try:
        with open(home / "config.json", encoding="utf-8") as fh:
            value = json.load(fh).get("lang")
    except (OSError, ValueError, AttributeError):
        return None
    value = str(value or "").strip().lower()
    return value if value in LANGS else None


def current():
    """The language of this run: STUDIO_LANG, else the config's `lang`, else English."""
    value = os.environ.get("STUDIO_LANG", "").strip().lower()
    if value in LANGS:
        return value
    return _config_lang() or DEFAULT


LANG = current()
os.environ["STUDIO_LANG"] = LANG          # the child processes (gates, Node) inherit it


def T(es, en):
    """The message in the user's language: `es` in Spanish, `en` in English."""
    return es if LANG == "es" else en
