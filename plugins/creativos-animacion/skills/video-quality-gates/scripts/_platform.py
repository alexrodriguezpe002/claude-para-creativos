"""What differs by operating system or by computer, written once for every gate.

* **The console speaks UTF-8.** On Windows, when the output goes to a pipe (Claude
  Code reads it that way), Python writes in the old ANSI code page and the first
  "→" or "—" stops a gate with UnicodeEncodeError.
* **Programs are found the way the system finds them.** On Windows `npx` and `npm`
  are batch files (`npx.cmd`) that `subprocess` cannot start by name and cmd.exe
  re-parses (paths with `&` or `%` break), so Node runs their own scripts instead.
  ffmpeg and Node installed after the terminal was opened (winget, the Node
  installer, Chocolatey, Scoop) are found too: their folders go at the END of PATH,
  so what PATH already finds still wins. Nothing changes on a Mac.
* **Where the skills are**: the folder that holds this skill — `~/.claude/skills/`
  on the owner's Mac, the plugin's `skills/` folder anywhere else — found from this
  file, never from a fixed path. GATES_SKILLS_DIR overrides it (a regression run
  over a frozen copy).
* **Where this computer keeps its own things**: `~/.studio-video/` —
  `config.json` (video_config.py), `learned/` (learned.py), `node/` (the browser
  library the measurements use). `Path.home()`, so `C:\\Users\\<name>\\.studio-video`
  on Windows. STUDIO_VIDEO_HOME overrides it (a test with an empty home).
"""

import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from _lang import T

IS_WIN = os.name == "nt"

# playwright-core, pinned: the version the gates were calibrated with (2026-10-01).
PLAYWRIGHT_SPEC = "playwright-core@1.63.0"


def utf8_console():
    for s in (sys.stdout, sys.stderr):
        enc = (getattr(s, "encoding", "") or "").lower().replace("-", "").replace("_", "")
        if enc != "utf8" and hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass


def _extra_bin_dirs():
    """Folders where Windows installers put ffmpeg and Node.js (empty elsewhere)."""
    if not IS_WIN:
        return []
    home = Path.home()
    local = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
    progs = [os.environ.get(k) for k in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")]
    progs = [p for p in progs if p]
    out = [os.path.join(local, "Microsoft", "WinGet", "Links")]                     # winget (ffmpeg)
    out += sorted(glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages",
                                         "Gyan.FFmpeg*", "*", "bin")), reverse=True)
    out += [os.path.join(p, "nodejs") for p in progs]                               # Node.js installer
    out += [os.path.join(p, "ffmpeg", "bin") for p in progs] + [r"C:\ffmpeg\bin"]  # unzipped by hand
    out.append(os.path.join(os.environ.get("ChocolateyInstall") or r"C:\ProgramData\chocolatey", "bin"))
    out.append(str(home / "scoop" / "shims"))
    return [d for d in out if os.path.isdir(d)]


def widen_path():
    cur = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    have = {os.path.normcase(os.path.normpath(p)) for p in cur}
    add = [d for d in _extra_bin_dirs() if os.path.normcase(os.path.normpath(d)) not in have]
    if add:
        os.environ["PATH"] = os.pathsep.join(cur + add)


utf8_console()
widen_path()


# ── where things are ─────────────────────────────────────────────────────────

def skills_dir():
    """The folder that holds this skill and its siblings (the brands, podcast-captions…)."""
    env = os.environ.get("GATES_SKILLS_DIR", "").strip()
    if env:
        return Path(os.path.expanduser(env))
    return Path(__file__).resolve().parents[2]


def sibling(name):
    """A sibling skill's folder, e.g. sibling("cle-brand")."""
    return skills_dir() / name


def user_dir():
    """This computer's own folder for the video skills: config, learned rules, the browser library."""
    env = os.environ.get("STUDIO_VIDEO_HOME", "").strip()
    return Path(os.path.expanduser(env)) if env else Path.home() / ".studio-video"


def node_dir():
    """Where `run_gates.py --doctor` installs playwright-core for this user (never in git)."""
    env = os.environ.get("STUDIO_NODE_DIR", "").strip()
    return Path(os.path.expanduser(env)) if env else user_dir() / "node"


def tilde(path):
    """A path as the user reads it: the home folder shown as ~."""
    s = str(path)
    home = str(Path.home())
    return "~" + s[len(home):] if s.startswith(home) else s


# ── programs ─────────────────────────────────────────────────────────────────

def exe(name):
    """Full path of a program, or None (on Windows PATHEXT finds npx.cmd, ffmpeg.exe)."""
    return shutil.which(name)


def _node_tool(cmd, cli):
    path = exe(cmd)
    if not path:
        return None
    if IS_WIN and path.lower().endswith((".cmd", ".bat")):
        base = Path(path).parent
        script = base / "node_modules" / "npm" / "bin" / cli
        node = base / "node.exe"
        node = str(node) if node.exists() else exe("node")
        if script.exists() and node:
            return [node, str(script)]
    return [path]


def npx_command():
    """How to start npx here, as an argv prefix — or None when Node is not installed."""
    return _node_tool("npx", "npx-cli.js")


def npm_command():
    return _node_tool("npm", "npm-cli.js")


def node_command():
    path = exe("node")
    return [path] if path else None


def run_text(args, **kw):
    """subprocess.run that reads the program's output as UTF-8 on every system.

    Node and ffmpeg write UTF-8; a Windows console decodes in cp1252 by default and
    either garbles a caption's text or stops on a byte it has no character for.
    """
    kw.setdefault("capture_output", True)
    kw.setdefault("encoding", "utf-8")
    kw.setdefault("errors", "replace")
    return subprocess.run(args, **kw)


# ── the browser library ──────────────────────────────────────────────────────

def browser_report(timeout=120):
    """What the browser measurements would use here: {playwright, browser, error} from _browser.js."""
    node = node_command()
    if not node:
        return {"playwright": None, "browser": None, "error": T("Node.js no está instalado", "Node.js is not installed")}
    js = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_browser.js")
    try:
        out = run_text(node + [js, "--report"], timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return {"playwright": None, "browser": None, "error": str(e)}
    try:
        return json.loads((out.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"playwright": None, "browser": None,
                "error": ((out.stderr or "") + (out.stdout or "")).strip()[-400:] or T("sin salida", "no output")}


def install_playwright(quiet=False):
    """Install playwright-core for this user in ~/.studio-video/node (never in git).

    Returns (ok, message). The library only drives a browser that is already on the
    computer (Chrome, Edge, or the one HyperFrames downloads); it downloads none.
    """
    npm = npm_command()
    if not npm:
        return False, T("npm no está: instalá Node.js (nodejs.org, versión LTS) y volvé a correr --doctor",
                        "npm is missing: install Node.js (nodejs.org, the LTS version) and run --doctor again")
    dest = node_dir()
    try:
        dest.mkdir(parents=True, exist_ok=True)
        pkg = dest / "package.json"
        if not pkg.exists():
            pkg.write_text(json.dumps({"name": "studio-video-node", "private": True,
                                       "description": "browser library of the studio's video gates "
                                                      "(installed by run_gates.py --doctor)"}, indent=2) + "\n",
                           encoding="utf-8")
    except OSError as e:
        return False, T("no pude crear %s: %s", "could not create %s: %s") % (dest, e)
    if not quiet:
        sys.stderr.write(T("· instalando %s en %s (una sola vez, ~10 MB)…\n", "· installing %s in %s (once, ~10 MB)…\n")
                         % (PLAYWRIGHT_SPEC, tilde(dest)))
    try:
        out = run_text(npm + ["install", "--prefix", str(dest), "--no-audit", "--no-fund",
                              "--loglevel", "error", PLAYWRIGHT_SPEC], timeout=600)
    except (OSError, subprocess.SubprocessError) as e:
        return False, T("npm install falló: %s", "npm install failed: %s") % e
    if out.returncode != 0:
        return False, T("npm install falló: %s", "npm install failed: %s") % ((out.stderr or out.stdout or "").strip()[-400:])
    return True, T("playwright-core instalado en %s", "playwright-core installed in %s") % tilde(dest)


# ── Python packages ──────────────────────────────────────────────────────────

# import name → what pip installs. The skills need these on every computer; `run_gates.py --doctor`
# installs the missing ones for this user, and a script that needs one installs it the first time
# (unless GATES_NO_INSTALL=1) — the same "installed on first use" as playwright-core.
PIP_NAMES = {
    "PIL": "pillow",                       # the balance gate
    "numpy": "numpy",                      # caption timing, music-bed --level, the reframe
    "faster_whisper": "faster-whisper",    # caption timing on the voice, second pass, music-bed check
    "fontTools": "fonttools",              # CLC's beats measure their own text (clc-brand's project script)
    "brotli": "brotli",                    # fontTools reads the .woff2 fonts through it
    "cv2": "opencv-python-headless",       # podcast-reframe finds the faces
}


def _in_venv():
    return getattr(sys, "base_prefix", sys.prefix) != sys.prefix


def have_module(name):
    """Is the module importable here (found, not imported: no side effects, no load time)?"""
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def module_version(name, timeout=120):
    """(ok, version or error) — the module imported in a separate Python, so a heavy or broken
    package (faster-whisper, OpenCV) neither slows nor breaks the caller."""
    code = ("import importlib, sys\nm = importlib.import_module(%r)\n"
            "print(getattr(m, '__version__', '') or getattr(getattr(m, 'version', None), '__version__', '') or 'ok')"
            % name)
    try:
        out = run_text([sys.executable, "-c", code], timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    if out.returncode != 0:
        lines = [l for l in (out.stderr or "").strip().splitlines() if l.strip()]
        return False, (lines[-1] if lines else "import failed")[:200]
    return True, (out.stdout or "").strip().splitlines()[-1] if (out.stdout or "").strip() else "ok"


def pip_install(packages, quiet=False, timeout=1800):
    """pip install for this user (in a virtualenv: into it), with the Python that runs this.

    Returns (ok, message). After it, the new packages import in this same process: the user
    site-packages folder is added to sys.path when Python had not created it yet at start-up.
    """
    import importlib
    import site
    packages = [p for p in packages if p]
    if not packages:
        return True, ""
    argv = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]
    if not _in_venv():
        argv.append("--user")
    if not quiet:
        sys.stderr.write("· pip install %s (once, for this user)…\n" % " ".join(packages))
    try:
        out = run_text(argv + packages, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return False, "pip install %s: %s" % (" ".join(packages), e)
    if out.returncode != 0:
        tail = ((out.stderr or "") + (out.stdout or "")).strip()[-500:]
        return False, "pip install %s failed: %s" % (" ".join(packages), tail)
    try:
        user_site = site.getusersitepackages()
        if user_site and os.path.isdir(user_site) and user_site not in sys.path:
            site.addsitedir(user_site)
    except (AttributeError, OSError):
        pass
    importlib.invalidate_caches()
    return True, "installed %s" % " ".join(packages)


def ensure_modules(names, why=""):
    """First use: import names (e.g. ["fontTools", "brotli"]) or install what is missing, once.

    Returns the list of names still missing (empty = all good). GATES_NO_INSTALL=1 never installs.
    """
    missing = [n for n in names if not have_module(n)]
    if not missing or os.environ.get("GATES_NO_INSTALL"):
        return missing
    if why:
        sys.stderr.write("· %s\n" % why)
    pip_install([PIP_NAMES.get(n, n) for n in missing])
    return [n for n in names if not have_module(n)]


def run_node(script, args, timeout=300, env=None):
    """Run one of the browser measurements: a CompletedProcess, or None without Node.

    Exit 3 is the measurement saying playwright or a browser is missing. The first
    time that happens on a computer with no playwright at all, it is installed for
    this user (ensure_playwright) and the measurement runs again — "installed on
    first use". Anything else is returned as it came.
    """
    node = node_command()
    if not node:
        return None
    argv = node + [str(script)] + [str(a) for a in args]
    try:
        out = run_text(argv, timeout=timeout, env=env)
        if out.returncode == 3 and ensure_playwright():
            out = run_text(argv, timeout=timeout, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    return out


_TRIED_INSTALL = False


def ensure_playwright():
    """First use: when no playwright is reachable, install it for this user, once per run.

    True only when it was missing and is installed now — the caller measures again.
    False when it was already there (the failure was something else: no browser, a
    page that does not load) or could not be installed: the caller keeps its WARN.
    GATES_NO_INSTALL=1 never installs.
    """
    global _TRIED_INSTALL
    if _TRIED_INSTALL or os.environ.get("GATES_NO_INSTALL"):
        return False
    _TRIED_INSTALL = True
    rep = browser_report()
    if rep.get("playwright"):
        return False
    ok, msg = install_playwright()
    sys.stderr.write("· %s\n" % msg)
    return ok
