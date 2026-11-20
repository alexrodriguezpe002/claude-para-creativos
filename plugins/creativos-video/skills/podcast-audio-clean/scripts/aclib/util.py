"""Small helpers: the console, finding ffmpeg on Mac/Windows/Linux, running it, the user's
language (`T(es, en)`, a copy of video-quality-gates' `_lang.py`), and this computer's folder."""
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

IS_WIN = os.name == "nt"
SKILL = Path(__file__).resolve().parents[2]          # the podcast-audio-clean folder


# ------------------------------------------------------------------ console
# On Windows, when the output goes to a pipe (Claude Code reads it that way), Python writes
# in the old ANSI code page and the first "→" or "—" stops the program.
def _utf8_console():
    for s in (sys.stdout, sys.stderr):
        enc = (getattr(s, "encoding", "") or "").lower().replace("-", "").replace("_", "")
        if enc != "utf8" and hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass


_utf8_console()

# ------------------------------------------------------------------ language
# Kit v2: this skill lives in the creativos-video plugin and video-quality-gates in
# creativos-animacion. An installed plugin is copied on its own, so the sibling folder may not
# exist: aclib/_lang.py is a copy of the gates' `_lang.py`. Both read the same setting
# (`lang` in ~/.studio-video/config.json), so the language is still one choice per person.
# If you change one copy, change the other.
from ._lang import T  # noqa: E402


# ------------------------------------------------------------ finding ffmpeg
def _extra_bin_dirs():
    """Where installers put ffmpeg. The terminal (or Claude Code) may have been opened
    BEFORE the install, so its PATH does not have them yet."""
    out = []
    if IS_WIN:
        home = Path.home()
        local = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        progs = [os.environ.get(k) for k in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")]
        progs = [p for p in progs if p]
        out.append(os.path.join(local, "Microsoft", "WinGet", "Links"))                     # winget
        out += sorted(glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages",
                                             "Gyan.FFmpeg*", "*", "bin")), reverse=True)
        out += [os.path.join(p, "ffmpeg", "bin") for p in progs] + [r"C:\ffmpeg\bin"]        # unzipped by hand
        out.append(os.path.join(os.environ.get("ChocolateyInstall") or r"C:\ProgramData\chocolatey", "bin"))
        out.append(str(home / "scoop" / "shims"))
    else:
        out += ["/opt/homebrew/bin", "/usr/local/bin"]      # Mac/Linux branch only (lint-ok)
    return [d for d in out if os.path.isdir(d)]


def _widen_path():
    cur = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    have = {os.path.normcase(os.path.normpath(p)) for p in cur}
    add = [d for d in _extra_bin_dirs() if os.path.normcase(os.path.normpath(d)) not in have]
    if add:
        os.environ["PATH"] = os.pathsep.join(cur + add)


_widen_path()


class Stop(SystemExit):
    """A problem the person has to know about, in plain words."""

    def __init__(self, msg, code=1):
        sys.stderr.write("\n" + msg.rstrip() + "\n")
        super().__init__(code)


def say(msg=""):
    print(msg, flush=True)


def exe(name):
    return shutil.which(name)


def tool(name):
    f = exe(name)
    if not f:
        raise Stop(T("No encuentro %s. Corré `audio_clean.py doctor`." % name,
                     "%s is not installed (or not on PATH). Run `audio_clean.py doctor`." % name))
    return f


def run(args, check=True, cwd=None, data=None):
    """Run a program; its text output is read as UTF-8 on every system (bytes when `data` is given)."""
    args = [str(a) for a in args]
    try:
        if data is not None:
            r = subprocess.run(args, input=data, capture_output=True, cwd=cwd)
        else:
            r = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace", cwd=cwd)
    except FileNotFoundError:
        raise Stop(T("No pude arrancar `%s`. Corré `audio_clean.py doctor`." % args[0],
                     "Could not start `%s`. Run `audio_clean.py doctor`." % args[0]))
    if check and r.returncode:
        err = r.stderr if isinstance(r.stderr, str) else (r.stderr or b"").decode("utf-8", "replace")
        raise Stop(T("Falló este paso:", "This step failed:") + "\n  %s\n%s" % (" ".join(args)[:400], err[-2000:]))
    return r


def ffmpeg(*args, check=True, cwd=None, data=None):
    return run([tool("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error", *args], check=check, cwd=cwd, data=data)


def user_dir():
    """This computer's own folder for the video skills (the same one the gates use)."""
    env = os.environ.get("STUDIO_VIDEO_HOME", "").strip()
    return Path(os.path.expanduser(env)) if env else Path.home() / ".studio-video"


def tilde(path):
    s, home = str(path), str(Path.home())
    return "~" + s[len(home):] if s.startswith(home) else s


def tempdir(where=None):
    try:
        return tempfile.TemporaryDirectory(dir=where, ignore_cleanup_errors=True)
    except TypeError:                                   # Python before 3.10
        return tempfile.TemporaryDirectory(dir=where)
