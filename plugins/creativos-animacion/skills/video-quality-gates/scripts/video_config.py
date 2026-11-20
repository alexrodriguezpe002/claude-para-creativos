#!/usr/bin/env python3
"""This computer's folders for the studio's video skills — asked once, kept in
~/.studio-video/config.json (C:\\Users\\<name>\\.studio-video\\config.json on Windows).

Nothing in the skills names a disk: where the projects live, what each client's
folder is called, and where the files that git cannot carry (media, the songs) were
downloaded is this file's business, one per person.

    video_config.py show                        the config — or, with none, what to ask the user (exit 2)
    video_config.py init --projects-root "<folder>" [--assets-root "<folder>"]
                         [--folder clb="CLIENT B" ...] [--music clb="<folder>" ...] [--lang en|es]
    video_config.py set projects_root|assets_root "<folder>"
    video_config.py set lang en|es               the language of the scripts' messages (new users: en)
    video_config.py set drive_root "<folder>"    where Google Drive for desktop shows the shared drives
                                                (G:/Shared drives) — hyperframes-render-to-drive
    video_config.py set-drive <client> "<folder>"   that client's episode folders in Drive for desktop,
                                                when they are not under drive_root as in Drive
    video_config.py set-folder <client> "<folder name, or a full path>"
    video_config.py set-music  <client> "<folder with the client's songs>"
    video_config.py where <client> [<episode>]  the client's folder, or the episode's (exit 2 if unknown)
    video_config.py find  <client> <words…>     HyperFrames projects (folders with index.html) of that
                                                client whose path holds every word ("ep4 snippet 2")
    video_config.py asset <path>                a file a skill reads that is not in git, e.g.
                                                cle-brand/assets/outro.mp4: the skill's own copy when
                                                it has one, else <assets_root>/<path> (exit 2 if neither)
    video_config.py music <client>              the client's song folder (exit 2 if unknown)
    video_config.py example                     the owner's config, as a model

`<client>` is the code the brands use: clb, cla, cle, cld, clc. A folder name is
joined to projects_root; a full path is used as it is (a client kept somewhere
else, such as a Google Drive for desktop folder). Run with `python3` on Mac and
Linux, `py -3` (or `python`) on Windows. STUDIO_VIDEO_HOME moves the folder
(tests with an empty home).
"""

import json
import ntpath
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _platform as P  # noqa: E402
from _lang import LANGS, T  # noqa: E402

CLIENTS = {
    "clb": "Client B",
    "cla": "Client A",
    "cle": "Client E",
    "cld": "Client D",
    "clc": "Client C",
}

# The clients whose orchestrators mix a music bed with music-bed (each asks for its songs once),
# and the files the skills read that git cannot carry (media, or over 256 KB) — `doctor` checks both.
MUSIC_CLIENTS = ("clb", "cla", "cle", "clc")
ASSETS = ("cle-brand/assets/outro.mp4", "cla-brand/assets/teaser-cta-sfx.wav")

# The Drive folder that holds what git cannot carry, mirroring the skills' paths
# (cle-brand/assets/outro.mp4 …). Private to its owner until it is shared; each team puts
# its own folder's link in ASSETS_DRIVE_URL ("" = the messages give only the name).
ASSETS_DRIVE_NAME = "the studio Video Skills — Assets"
ASSETS_DRIVE_URL = ""

# The owner's computer, as the example every question points to.
OWNER_EXAMPLE = {
    "version": 1,
    "projects_root": "/Volumes/DISCO/STUDIO",
    "clients": {
        "clb": {"folder": "CLIENT B", "music": "/Volumes/DISCO/STUDIO/CLIENT B/MUSIC"},
        "cla": {"folder": "CLIENT A", "music": "~/Desktop/TEMPLATE/MUSIC/CLA"},
        "cle": {"folder": "CLIENT E",
                "music": "/Volumes/DISCO/STUDIO/CLIENT E/ep1/MUSIC"},
        "cld": {"folder": "CLIENT D"},
        "clc": {"folder": "CLIENT C", "music": "~/Desktop/TEMPLATE/MUSIC/CLC"},
    },
    "assets_root": "",
    "lang": "es",
}

# Where each client's songs come from, for the question asked once (and the doctor's hint):
# music/<client> inside the assets folder (ASSETS_DRIVE_NAME), found without --music. Only the
# songs the user approved are there (2026-10-03); the team's "Editing Assets" folders also hold
# songs that were not, so they are not a source.
MUSIC_SOURCES = {
    "clb": "music/clb",
    "clc": "music/clc",
    "cla": "music/cla",
    "cle": "music/cle",
}


def music_hint(client):
    """Where the client's songs are, in one line for the user."""
    src = MUSIC_SOURCES.get(client)
    if not src:
        return T("esta skill no mezcla música para este cliente", "no music bed for this client")
    return T("están en %s dentro de la carpeta de Drive «%s» (assets_root)",
             "they are in %s inside the Drive folder “%s” (assets_root)") % (src, ASSETS_DRIVE_NAME)


SKIP_DIRS = {"node_modules", ".git", ".gates-cache", ".captions-backup", "renders", "snapshots",
             "__pycache__", ".thumbnails"}


def config_path():
    return P.user_dir() / "config.json"


def _out(p):
    """A path printed for a shell: forward slashes on every system (Git Bash on
    Windows globs and quotes D:/a/b safely; Python, Node and ffmpeg accept it too)."""
    return Path(p).as_posix()


def load():
    """The config as a dict, or None when this computer has none yet."""
    p = config_path()
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.stderr.write(T("config ilegible %s: %s\n", "unreadable config %s: %s\n") % (p, e))
        return None


def save(cfg):
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    cfg.setdefault("version", 1)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def _client_cfg(cfg, client):
    return ((cfg or {}).get("clients") or {}).get(client) or {}


def _is_abs(folder):
    # a Windows path ("D:\\Clients\\CLB") reads as absolute on any system, so a config
    # written on Windows is understood the same way when it is tested elsewhere
    return os.path.isabs(folder) or ntpath.isabs(folder)


def client_root(client, cfg=None):
    """The client's folder as a Path, or None when the config does not say."""
    cfg = load() if cfg is None else cfg
    folder = _client_cfg(cfg, client).get("folder")
    if not folder:
        return None
    folder = os.path.expanduser(folder)
    if _is_abs(folder):
        return Path(folder)
    root = (cfg or {}).get("projects_root")
    return Path(os.path.expanduser(root)) / folder if root else None


def client_folders(cfg=None):
    """{client: path hint} for the gates' profile match — '/NAME/' for a folder name,
    the full path plus '/' for a folder given as one, forward slashes — or {}."""
    cfg = load() if cfg is None else cfg
    out = {}
    for client, c in ((cfg or {}).get("clients") or {}).items():
        folder = os.path.expanduser((c or {}).get("folder") or "")
        if not folder.strip():
            continue
        if _is_abs(folder):
            out[client] = folder.replace("\\", "/").rstrip("/") + "/"
        else:
            out[client] = "/%s/" % folder.replace("\\", "/").strip("/")
    return out


def asset(rel, cfg=None):
    """(path, where) of a file the skills read that git does not carry, or (None, why)."""
    rel = rel.replace("\\", "/").lstrip("/")
    own = P.skills_dir() / rel
    if own.is_file():
        return own, T("la copia de la skill", "the skill's own copy")
    cfg = load() if cfg is None else cfg
    root = (cfg or {}).get("assets_root")
    if root:
        cand = Path(os.path.expanduser(root)) / rel
        if cand.is_file():
            return cand, "assets_root"
        return None, T("no está en %s", "not in %s") % cand
    return None, T("no hay assets_root en %s", "no assets_root in %s") % P.tilde(config_path())


def music_dir(client, cfg=None):
    cfg = load() if cfg is None else cfg
    m = _client_cfg(cfg, client).get("music")
    if m:
        return Path(os.path.expanduser(m))
    root = (cfg or {}).get("assets_root")
    if root:
        cand = Path(os.path.expanduser(root)) / "music" / client
        if cand.is_dir():
            return cand
    return None


def find_projects(client, words, cfg=None, depth=6):
    root = client_root(client, cfg)
    if not root or not root.is_dir():
        return root, []
    words = [w.lower() for w in words if w.strip()]
    hits = []
    base = len(root.parts)
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(("._", "."))]
        if len(Path(d).parts) - base >= depth:
            dirs[:] = []
        if "index.html" in files:
            rel = str(Path(d).relative_to(root)).lower()
            if all(w in rel for w in words):
                hits.append(Path(d))
            dirs[:] = []          # a project: nothing inside it is another one
    return root, sorted(hits)


# ── the command line ─────────────────────────────────────────────────────────

def _ask_text():
    ex = OWNER_EXAMPLE
    folders = ", ".join("%s = %s" % (k, v["folder"]) for k, v in ex["clients"].items())
    return T(
        "No hay configuración en este computador todavía (%s).\n"
        "Preguntale al usuario, una sola vez:\n"
        "  1. ¿En qué carpeta están los proyectos de los clientes? (la que contiene una carpeta por cliente;\n"
        "     en la Mac del dueño: %s)\n"
        "  2. ¿Cómo se llama la carpeta de cada cliente con el que trabaja? (en la del dueño: %s)\n"
        "  3. ¿Dónde bajó la carpeta de Drive «%s»? (el outro de CLE, el sonido del CTA de CLA y CLC,\n"
        "     las canciones aprobadas de cada cliente en music/<cliente>, y lo demás que git no lleva)\n"
        "  4. Las canciones: music/clb, music/clc, music/cla y music/cle dentro de la carpeta del punto 3 — si\n"
        "     están ahí, no hace falta --music; solo si las tiene en otro lado, ¿dónde?\n"
        "  5. ¿En qué idioma quiere los mensajes de los scripts: inglés (en) o español (es)? (por defecto en)\n"
        "Después:\n"
        "  video_config.py init --projects-root \"<1>\" --assets-root \"<3>\" "
        "--folder clb=\"<2>\" --folder cla=\"<2>\" --folder cle=\"<2>\" --folder clc=\"<2>\" "
        "--lang <5>\n"
        "(cada --folder es opcional: sin él se usa el nombre de la Mac del dueño; --music <cliente>=\"<4>\"\n"
        "solo si las canciones no están en la carpeta del punto 3).",
        "This computer has no configuration yet (%s).\n"
        "Ask the user, once:\n"
        "  1. Which folder holds the clients' projects? (the one with a folder per client;\n"
        "     on the owner's Mac: %s)\n"
        "  2. What is each client's folder called, for the clients they work on? (on the owner's: %s)\n"
        "  3. Where did they download the Drive folder “%s”? (CLE's outro, the CLA and CLC CTA sound,\n"
        "     each client's approved songs in music/<client>, and everything else git does not carry)\n"
        "  4. The songs: music/clb, music/clc, music/cla and music/cle inside the folder of question 3 — if\n"
        "     they are there, no --music needed; only if they keep them somewhere else, where?\n"
        "  5. Which language for the scripts' messages: English (en) or Spanish (es)? (default en)\n"
        "Then:\n"
        "  video_config.py init --projects-root \"<1>\" --assets-root \"<3>\" "
        "--folder clb=\"<2>\" --folder cla=\"<2>\" --folder cle=\"<2>\" --folder clc=\"<2>\" "
        "--lang <5>\n"
        "(each --folder is optional: without it the owner's folder name is used; --music <client>=\"<4>\"\n"
        "only if the songs are not in the folder of question 3)."
    ) % (P.tilde(config_path()), ex["projects_root"], folders, ASSETS_DRIVE_NAME)


def _pairs(items, what):
    out = {}
    for it in items or []:
        if "=" not in it:
            sys.exit(T("--%s espera cliente=valor, no %r", "--%s wants client=value, not %r") % (what, it))
        k, v = it.split("=", 1)
        k = k.strip().lower()
        if k not in CLIENTS:
            sys.exit(T("cliente desconocido %r (los códigos: %s)", "unknown client %r (the codes: %s)")
                     % (k, ", ".join(CLIENTS)))
        out[k] = v.strip().strip('"')
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("show")
    sub.add_parser("example")
    i = sub.add_parser("init")
    i.add_argument("--projects-root", required=True)
    i.add_argument("--assets-root", default="")
    i.add_argument("--folder", action="append", default=[])
    i.add_argument("--music", action="append", default=[])
    i.add_argument("--lang", choices=LANGS, default="en", help="the scripts' messages: en (default) or es")
    i.add_argument("--force", action="store_true", help="replace an existing config")
    s = sub.add_parser("set")
    s.add_argument("key", choices=["projects_root", "assets_root", "lang", "drive_root"])
    s.add_argument("value")
    sf = sub.add_parser("set-folder")
    sf.add_argument("client", choices=sorted(CLIENTS))
    sf.add_argument("folder")
    sm = sub.add_parser("set-music")
    sm.add_argument("client", choices=sorted(CLIENTS))
    sm.add_argument("folder")
    sd = sub.add_parser("set-drive")
    sd.add_argument("client", choices=sorted(CLIENTS))
    sd.add_argument("folder")
    w = sub.add_parser("where")
    w.add_argument("client", choices=sorted(CLIENTS))
    w.add_argument("episode", nargs="?")
    f = sub.add_parser("find")
    f.add_argument("client", choices=sorted(CLIENTS))
    f.add_argument("words", nargs="*")
    a = sub.add_parser("asset")
    a.add_argument("path")
    m = sub.add_parser("music")
    m.add_argument("client", choices=sorted(CLIENTS))
    args = ap.parse_args(argv)
    cfg = load()

    if args.cmd in (None, "show"):
        if cfg is None:
            print(_ask_text())
            return 2
        print("%s\n%s" % (P.tilde(config_path()), json.dumps(cfg, indent=2, ensure_ascii=False)))
        for c in sorted(CLIENTS):
            r = client_root(c, cfg)
            if r:
                print("  %-4s %s%s" % (c, r, "" if r.is_dir() else T("   (no existe en este computador)",
                                                                     "   (does not exist on this computer)")))
        if not cfg.get("assets_root"):
            own = all(asset(rel, cfg)[0] for rel in ASSETS)
            print(T("  assets_root sin definir: %s", "  assets_root not set: %s") % (
                T("no hace falta acá, las skills tienen su propia copia de los archivos fuera de git",
                  "not needed here, the skills have their own copy of the files git does not carry") if own else
                T("el outro de CLE, el sonido del CTA de CLA y los demás archivos fuera de git no se encuentran "
                  "(video_config.py set assets_root \"<carpeta de Drive bajada>\")",
                  "CLE's outro, the CLA CTA sound and the other files git does not carry are not found "
                  "(video_config.py set assets_root \"<the downloaded Drive folder>\")")))
        if "lang" not in cfg:
            print(T("  lang sin definir: los mensajes salen en inglés (video_config.py set lang es)",
                    "  lang not set: the messages are in English (video_config.py set lang es)"))
        if cfg.get("drive_root"):
            print("  drive_root %s" % cfg["drive_root"])
        return 0
    if args.cmd == "example":
        print(json.dumps(OWNER_EXAMPLE, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "init":
        if cfg is not None and not args.force:
            print(T("ya hay una configuración en %s — usá set / set-folder, o init --force",
                    "there is a configuration already in %s — use set / set-folder, or init --force")
                  % P.tilde(config_path()))
            return 2
        folders, music = _pairs(args.folder, "folder"), _pairs(args.music, "music")
        clients = {}
        for c in CLIENTS:
            entry = {"folder": folders.get(c) or OWNER_EXAMPLE["clients"][c]["folder"]}
            if music.get(c):
                entry["music"] = music[c]
            clients[c] = entry
        cfg = {"version": 1, "projects_root": args.projects_root, "clients": clients,
               "assets_root": args.assets_root, "lang": args.lang}
        print(T("escrito %s", "written %s") % P.tilde(save(cfg)))
        return main(["show"])
    if cfg is None:
        print(_ask_text())
        return 2
    if args.cmd == "set":
        if args.key == "lang" and args.value.strip().lower() not in LANGS:
            print(T("lang es en o es, no %r", "lang is en or es, not %r") % args.value)
            return 2
        cfg[args.key] = args.value.strip().lower() if args.key == "lang" else args.value
        save(cfg)
        return main(["show"])
    if args.cmd == "set-folder":
        cfg.setdefault("clients", {}).setdefault(args.client, {})["folder"] = args.folder
        save(cfg)
        return main(["show"])
    if args.cmd == "set-music":
        cfg.setdefault("clients", {}).setdefault(args.client, {})["music"] = args.folder
        save(cfg)
        return main(["show"])
    if args.cmd == "set-drive":
        cfg.setdefault("clients", {}).setdefault(args.client, {})["drive"] = args.folder
        save(cfg)
        return main(["show"])
    if args.cmd == "where":
        r = client_root(args.client, cfg)
        if not r:
            print(T("la configuración no dice dónde está %s: video_config.py set-folder %s \"<carpeta>\"",
                    "the configuration does not say where %s is: video_config.py set-folder %s \"<folder>\"")
                  % (CLIENTS[args.client], args.client))
            return 2
        if args.episode:
            r = r / args.episode
        print(_out(r))
        if not r.exists():
            sys.stderr.write(T("(todavía no existe en este computador)\n", "(it does not exist on this computer yet)\n"))
        return 0
    if args.cmd == "find":
        root, hits = find_projects(args.client, args.words, cfg)
        if not root or not root.is_dir():
            print(T("no encuentro la carpeta de %s (%s) — revisá video_config.py show",
                    "cannot find the folder of %s (%s) — check video_config.py show") % (CLIENTS[args.client], root))
            return 2
        for h in hits:
            print(_out(h))
        if not hits:
            sys.stderr.write(T("ningún proyecto (carpeta con index.html) bajo %s con: %s\n",
                               "no project (a folder with index.html) under %s with: %s\n")
                             % (root, " ".join(args.words) or T("(todo)", "(all)")))
            return 1
        return 0
    if args.cmd == "asset":
        p, how = asset(args.path, cfg)
        if p:
            print(_out(p))
            return 0
        print(T("%s: %s.\nNo viaja en git (es media o pesa más de 256 KB). Está en la carpeta de Drive «%s»%s,\n"
                "con la misma ruta: bajala entera y declarala una vez con\n"
                "  video_config.py set assets_root \"<carpeta bajada>\"",
                "%s: %s.\nIt does not travel in git (media, or over 256 KB). It is in the Drive folder “%s”%s,\n"
                "at the same path: download the whole folder and declare it once with\n"
                "  video_config.py set assets_root \"<the downloaded folder>\"")
              % (args.path, how, ASSETS_DRIVE_NAME, (" (%s)" % ASSETS_DRIVE_URL) if ASSETS_DRIVE_URL else ""))
        return 2
    if args.cmd == "music":
        d = music_dir(args.client, cfg)
        if not d:
            print(T("no sé dónde están las canciones de %s en este computador (%s): preguntale al usuario y\n"
                    "  video_config.py set-music %s \"<carpeta>\"",
                    "where the songs of %s are on this computer is not set (%s): ask the user, then\n"
                    "  video_config.py set-music %s \"<folder>\"")
                  % (CLIENTS[args.client], music_hint(args.client), args.client))
            return 2
        print(_out(d))
        if not d.is_dir():
            sys.stderr.write(T("(esa carpeta no existe en este computador)\n", "(that folder does not exist on this computer)\n"))
            return 2
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
