#!/usr/bin/env python3
"""What this computer learned from its user — one file per client.

When the user corrects something that holds for every future video of a client
("never more than 4 words a card", "from now on…"), the correction is written
down once, on this computer, and every skill of that client reads it before it
plans, builds or captions:

    ~/.studio-video/learned/<client>.md          the rules, in the user's words
    ~/.studio-video/learned/<client>.gates.json  the numbers among them, which
                                                     _profile.py merges over the
                                                     client's gates.json

(`Path.home()`: on Windows that is C:\\Users\\<name>\\.studio-video\\learned.)
The team skill does not change: the owner of the skills reviews these files and
promotes what stays. Commands:

    learned.py where                      the folder, and whether this is the owner's computer
    learned.py show <client> [--all]      the active rules (run it before planning or building)
    learned.py add <client> --said "<the user's words>" --rule "<the rule>"
               [--set captions.max_words_snippet=4] [--area captions] [--where "<video, round>"]
               [--by "<who>"] [--new]
    learned.py remove  <client> <id>               the user withdrew it
    learned.py promote <client> <id> [--to "<file>"] [--file <md>]   it is in the team skill now
    learned.py reject  <client> <id> --why "<…>" [--file <md>]      the owner decided against it
    learned.py prune   <client>                    drop what is promoted or already in the brand
    learned.py review  <path-to-someone's-<client>.md>   the owner, before promoting

Fixes and detours — on a computer that is not the owner's, every change to a file
of a skill, every way around a skill that failed and every gate or script that
failed and was got past another way is written down at that moment, in the same
folder (`fixes.md`, one entry F-NNN each), for the owner to review when he is back:

    learned.py fix --skill <skill> (--failed "<the real output>" | --failed-file <log>)
               --cause "<why>" --change "<files + what changed, or the step done by hand>"
               --checked "<how it was verified>" --team yes|no|decide --why "<one line>"
               [--files "<a>, <b>"] [--kind edit|workaround|gate] [--where "<video, step>"]
               [--patch <diff file>] [--open] [--by "<who>"]
    learned.py fix-update <id> [--solved "<how>"] [--checked "<…>"] [--plugin "<shelf clone>"]
               [--shelf "<pull request or commit link>"] [--merged]
    learned.py report [--out <file>]       WHAT-CHANGED.md: the one document for the owner
                                           (fixes + learned rules + what is open); also
                                           rebuilt by every fix / fix-update
    learned.py show fixes [--all]          the log
    learned.py review "<someone's learned folder>"        the owner: the whole document
    learned.py promote|reject fixes <id> --file "<their folder>/fixes.md" …   his decision

`--plugin` copies the entry into the plugin's FIXES.md in the shelf clone, so the
pull request that carries a fix carries its entry too.

STUDIO_LEARNED_DIR moves the folder (tests). Exit 2 = refused, nothing written.
"""

import argparse
import datetime
import getpass
import json
import os
import re
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _profile  # noqa: E402
from _lang import T  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")   # Windows consoles default to cp1252
    except (AttributeError, ValueError):
        pass

HEAD_RE = re.compile(r"^## ([LF]-\d{3,})\b.*$", re.M)        # L-: a learned rule · F-: a fix
STATUS_RE = re.compile(r"^- \*\*Status:\*\* .*$", re.M)


def refuse(msg):
    sys.stderr.write("refused: %s\n" % msg)
    sys.exit(2)


def owner_marker():
    return _profile.learned_dir().parent / "OWNER"


def files(client):
    d = _profile.learned_dir()
    return d / ("%s.md" % client), d / ("%s.gates.json" % client)


def header(client):
    return (
        "# What this computer learned — %s\n\n"
        "Corrections the user of this computer gave once that hold for every future\n"
        "video of this client. Every %s skill reads this file before planning, building\n"
        "or captioning (`learned.py show %s`) and applies each **active** rule as if it\n"
        "were written in the client's brand skill; where the two disagree, the rule here\n"
        "is the newer word of the user. The numbers among them are also in\n"
        "`%s.gates.json`, which the gates and the caption grouping merge over the brand's\n"
        "own numbers and announce in yellow (`APRENDIDO`).\n\n"
        "Nothing here changes the team skill: its owner reviews this file and promotes\n"
        "what stays (`video-quality-gates` SKILL.md → \"Corrections become rules\").\n"
        "Delete a block (or `learned.py remove`) and the skill forgets it.\n"
    ) % (client, client.upper(), client, client)


def read_md(path):
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def blocks(text):
    """[(id, block_text)] in file order."""
    heads = list(HEAD_RE.finditer(text))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.append((m.group(1), text[m.start():end]))
    return out


def status_of(block):
    m = STATUS_RE.search(block)
    return m.group(0).split(":**", 1)[1].strip().split()[0].lower() if m else "active"


def read_json(path):
    if not path.is_file():
        return {"overrides": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        refuse("%s is not valid JSON — fix it by hand first" % path)


def write_json(path, client, data):
    data["client"] = client
    data["_comment"] = ("Numbers learned on this computer, merged by video-quality-gates/scripts/"
                        "_profile.py over %s-brand/references/gates.json. The rules in words are in %s.md."
                        % (client, client))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def next_id(text, data):
    nums = [int(i[2:]) for i, _ in blocks(text)]
    nums += [int(str(o.get("id", "L-0"))[2:]) for o in data.get("overrides") or []
             if re.match(r"L-\d+$", str(o.get("id", "")))]
    return "L-%03d" % (max(nums or [0]) + 1)


def parse_set(spec):
    if "=" not in spec:
        refuse("--set takes path=value, e.g. captions.max_words_snippet=4")
    path, raw = spec.split("=", 1)
    path = path.strip()
    try:
        value = json.loads(raw)
    except ValueError:
        value = raw.strip()
    return path, value


def same_kind(a, b):
    if a is None:
        return True
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool)
    if isinstance(a, (int, float)):
        return isinstance(b, (int, float))
    return type(a) is type(b)


def cmd_where(_args):
    d = _profile.learned_dir()
    print("learned folder: %s" % d)
    present = sorted(p.name for p in d.glob("*")) if d.is_dir() else []
    print("files: %s" % (", ".join(present) or "none"))
    om = owner_marker()
    if om.is_file():
        print("owner of the skills: YES (%s) — a correction here can go straight into "
              "<client>-brand/references/decisions.md and gates.json" % om)
    else:
        print("owner of the skills: no — corrections stay in the learned file until the owner promotes them")
    fx = fix_blocks(read_md(d / FIXES_MD))
    if fx:
        print(T("registro de arreglos: %s — %d entrada(s), %d abierta(s) · documento para el dueño: %s",
                "fix log: %s — %d entr(ies), %d open · the document for the owner: %s")
              % (d / FIXES_MD, len(fx), sum(status_of(b) == "open" for _, b in fx), d / REPORT_MD))
    return 0


def cmd_show(args):
    if args.client == FIXES:
        return show_fixes(args.all)
    md, js = files(args.client)
    text = read_md(md)
    data = read_json(js)
    shown = [(i, b) for i, b in blocks(text) if args.all or status_of(b) == "active"]
    if not shown:
        print("Nothing learned on this computer for %s (%s)." % (args.client, md))
        return 0
    print("Learned on this computer for %s — %d %srule(s) (%s):\n"
          % (args.client, len(shown), "" if args.all else "active ", md))
    for _, b in shown:
        print(b.rstrip() + "\n")
    active = [o for o in data.get("overrides") or [] if o.get("status", "active") == "active"]
    if active:
        print("Numbers the gates apply (%s):" % js)
        for o in active:
            print("  %s  %s = %s  (the brand had %s)" % (o["id"], o["path"], json.dumps(o["value"]),
                                                         json.dumps(o.get("was"))))
    return 0


def cmd_add(args):
    client = args.client.lower()
    if client == FIXES:
        refuse(T("«fixes» es el registro de arreglos, no un cliente: learned.py fix …",
                 "\"fixes\" is the fix log, not a client: learned.py fix …"))
    md, js = files(client)
    text = read_md(md) or header(client)
    data = read_json(js)
    said = args.said.strip()
    rule = args.rule.strip()
    if not said or not rule:
        refuse("--said (the user's own words) and --rule (the rule) are both required")
    override = None
    if args.set:
        path, value = parse_set(args.set)
        os.environ["GATES_CLIENT"] = client
        os.environ["GATES_NO_LEARNED"] = "1"
        try:
            prof = _profile.load(".", strict=True)
        except SystemExit:
            refuse("no gates profile for %r — a client's numbers live in <client>-brand/references/gates.json"
                     % client)
        try:
            was = _profile._get(prof, path)
        except KeyError:
            if not args.new:
                top = path.split(".")[0]
                keys = sorted(prof.get(top, {}).keys()) if isinstance(prof.get(top), dict) else sorted(prof)
                refuse("%s is not a number the gates read (typo?). Keys under %s: %s. "
                         "If it is a new key that a gate does read, repeat with --new."
                         % (path, top, ", ".join(keys)))
            was = None
        if not same_kind(was, value):
            refuse("%s is a %s in the brand (%s) and the new value is %s"
                     % (path, type(was).__name__, json.dumps(was), json.dumps(value)))
        if was == value:
            refuse("the brand already says %s = %s — nothing to learn" % (path, json.dumps(value)))
        override = {"path": path, "value": value, "was": was}
    lid = next_id(text, data)
    today = datetime.date.today().isoformat()
    by = args.by or getpass.getuser()
    where = (", " + args.where) if args.where else ""
    lines = ["", "## %s · %s · %s" % (lid, today, args.area),
             "- **Said** (%s%s): \"%s\"" % (by, where, said.replace("\n", " ")),
             "- **Rule:** %s" % rule.replace("\n", " ")]
    if override:
        lines.append("- **Number:** `%s` = %s (the brand said %s) — the gates and the caption grouping apply it"
                     % (override["path"], json.dumps(override["value"]), json.dumps(override["was"])))
    lines.append("- **Status:** active — learned on this computer, not in the team skill yet")
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(text.rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    if override:
        data.setdefault("overrides", []).append(dict(
            id=lid, date=today, said=said, rule=rule, by=by, where=args.where or "",
            status="active", **override))
        write_json(js, client, data)
    print("%s saved in %s%s" % (lid, md, (" and %s" % js) if override else ""))
    if override:
        print("  %s: %s → %s from the next gate run" % (override["path"], json.dumps(override["was"]),
                                                      json.dumps(override["value"])))
    return 0


def _set_status(client, lid, status_text, json_status, md_path=None):
    md, js = files(client)
    md = Path(md_path) if md_path else md
    js = md.with_name("%s.gates.json" % client) if md_path else js
    text = read_md(md)
    found = False
    out = []
    for i, b in blocks(text):
        if i == lid:
            found = True
            # a function, not a string: a Windows path in --to ("clb-brand\references\…") is not a regex escape
            b = STATUS_RE.sub(lambda _m: "- **Status:** " + status_text, b) if STATUS_RE.search(b) \
                else b.rstrip() + "\n- **Status:** " + status_text + "\n"
        out.append(b)
    if not found:
        refuse("%s is not in %s" % (lid, md))
    head = text[:HEAD_RE.search(text).start()] if HEAD_RE.search(text) else text
    md.write_text(head + "".join(out), encoding="utf-8")
    data = read_json(js)
    for o in data.get("overrides") or []:
        if o.get("id") == lid:
            o["status"] = json_status
    if js.is_file():
        write_json(js, client, data)
    print("%s → %s (%s)" % (lid, status_text, md))
    return 0


def cmd_promote(args):
    to = (" into " + args.to) if args.to else ""
    return _set_status(args.client.lower(), args.id,
                       "promoted (%s%s) — in the team skill now" % (datetime.date.today().isoformat(), to),
                       "promoted", args.file)


def cmd_reject(args):
    return _set_status(args.client.lower(), args.id,
                       "rejected (%s): %s" % (datetime.date.today().isoformat(), args.why.strip()),
                       "rejected", args.file)


def cmd_remove(args):
    client = args.client.lower()
    md, js = files(client)
    text = read_md(md)
    kept = [(i, b) for i, b in blocks(text) if i != args.id]
    if len(kept) == len(blocks(text)):
        refuse("%s is not in %s" % (args.id, md))
    head = text[:HEAD_RE.search(text).start()]
    md.write_text(head + "".join(b for _, b in kept), encoding="utf-8")
    data = read_json(js)
    data["overrides"] = [o for o in data.get("overrides") or [] if o.get("id") != args.id]
    if js.is_file():
        write_json(js, client, data)
    print("%s removed from %s" % (args.id, md))
    return 0


def cmd_prune(args):
    client = args.client.lower()
    md, js = files(client)
    os.environ["GATES_CLIENT"] = client
    os.environ["GATES_NO_LEARNED"] = "1"
    try:
        prof = _profile.load(".", strict=True) if client != FIXES else {}
    except SystemExit:
        prof = {}
    data = read_json(js)
    drop = set()
    for o in data.get("overrides") or []:
        try:
            brand = _profile._get(prof, o["path"])
        except KeyError:
            brand = None
        if o.get("status") == "promoted" or brand == o.get("value"):
            drop.add(o["id"])
    text = read_md(md)
    for i, b in blocks(text):
        if status_of(b) == "promoted":
            drop.add(i)
    if not drop:
        print("nothing to prune for %s" % client)
        return 0
    head = text[:HEAD_RE.search(text).start()] if HEAD_RE.search(text) else text
    md.write_text(head + "".join(b for i, b in blocks(text) if i not in drop), encoding="utf-8")
    data["overrides"] = [o for o in data.get("overrides") or [] if o.get("id") not in drop]
    if js.is_file():
        write_json(js, client, data)
    print("pruned %s: %s" % (client, ", ".join(sorted(drop))))
    return 0


def cmd_review(args):
    md = Path(args.file)
    if md.is_dir() or md.name in (FIXES_MD, REPORT_MD):
        return review_folder(md if md.is_dir() else md.parent)
    text = read_md(md)
    if not text:
        refuse("could not read %s" % md)
    m = re.match(r"(.+)\.md$", md.name)
    client = m.group(1) if m else "?"
    js = md.with_name("%s.gates.json" % client)
    data = read_json(js)
    os.environ["GATES_CLIENT"] = client
    os.environ["GATES_NO_LEARNED"] = "1"
    try:
        prof = _profile.load(".", strict=True)
    except SystemExit:
        prof = {}
    print("Review of %s — %d entr%s\n" % (md, len(blocks(text)), "y" if len(blocks(text)) == 1 else "ies"))
    for i, b in blocks(text):
        print(b.rstrip())
        for o in data.get("overrides") or []:
            if o.get("id") == i:
                try:
                    brand = _profile._get(prof, o["path"])
                except KeyError:
                    brand = None
                print("  → the brand says %s = %s today" % (o["path"], json.dumps(brand)))
        print("")
    print("Promote: write it into %s-brand/references/decisions.md (and gates.json for a number), "
          "then `learned.py promote %s <id> --file \"%s\"`." % (client, client, md))
    return 0


# ── Fixes and detours on a computer that is not the owner's ──────────────────

FIXES = "fixes"                       # `show / promote / reject / remove / prune fixes …`
FIXES_MD = "fixes.md"
REPORT_MD = "WHAT-CHANGED.md"
PLUGIN_FIXES_MD = "FIXES.md"
TEAM = ("yes", "no", "decide")
KINDS = ("edit", "workaround", "gate")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
PATCH_INLINE = 80                     # a patch up to this many lines is shown inside the document
SHELF_NO = "no — only on this computer"
PENDING = "pull request in preparation (the entry is in the shelf clone's FIXES.md)"

FIXES_HEADER = (
    "# Fixes and detours on this computer\n\n"
    "Every time Claude changed a file of a skill of the podcast-video plugin on this\n"
    "computer, worked around a skill that failed (a step by hand, a patch, another\n"
    "command) or got past a failing gate or script another way, it wrote it down here\n"
    "at that moment, before going on. The owner of the skills reads it when he is back\n"
    "and decides what goes into the team skills (`video-quality-gates` SKILL.md →\n"
    "\"The loop\", 6–7). `learned.py fix` adds an entry, `learned.py fix-update`\n"
    "completes one; WHAT-CHANGED.md, next to this file, is the one document for the\n"
    "owner, rebuilt after every entry (`learned.py report`).\n"
)

PLUGIN_FIXES_HEADER = (
    "# Fixes merged from other computers\n\n"
    "One entry per fix to a skill of this plugin made on a computer that is not the\n"
    "owner's and merged through a pull request: the same pull request carries the\n"
    "change and its entry, copied from that computer's fix log\n"
    "(`video-quality-gates/scripts/learned.py fix-update <id> --plugin …`). The owner\n"
    "of the skills reads them when he is back and decides what stays\n"
    "(`video-quality-gates` SKILL.md → \"The loop\", 7). That computer's whole log, with\n"
    "the detours that changed no file, is its `.studio-video/learned/fixes.md`, and\n"
    "the WHAT-CHANGED.md next to it. The sync tools never touch this file.\n"
)


def write_lf(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:     # the same bytes on Windows
        fh.write(text)


def read_any(path):
    """A log or a diff as text, whoever wrote it: UTF-8, PowerShell's UTF-16, or cp1252."""
    try:
        raw = Path(path).read_bytes()
    except OSError as e:
        refuse(T("no pude leer %s: %s", "could not read %s: %s") % (path, e))
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def one_line(s):
    return " ".join(str(s or "").split())


def trim_output(text, head=6, tail=20, width=300):
    """The real output, short: colours out, long lines cut, the middle of a long log cut."""
    lines = [ANSI_RE.sub("", ln).rstrip() for ln in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    lines = [ln if len(ln) <= width else ln[:width] + " …" for ln in lines]
    if len(lines) > head + tail + 1:
        lines = lines[:head] + ["… (%d lines cut) …" % (len(lines) - head - tail)] + lines[-tail:]
    return "\n".join(lines)


def fenced(text, lang="", indent=""):
    fence = "`" * (max([len(r) for r in re.findall(r"`+", text)] + [2]) + 1)
    body = "\n".join((indent + ln) if ln else "" for ln in text.split("\n"))
    return "%s%s%s\n%s\n%s%s" % (indent, fence, lang, body, indent, fence)


def field(block, label):
    m = re.search(r"^- \*\*%s:\*\* (.*)$" % re.escape(label), block, re.M)
    return m.group(1).strip() if m else ""


def set_field(block, label, value):
    rx = re.compile(r"^- \*\*%s:\*\* .*$" % re.escape(label), re.M)
    line = "- **%s:** %s" % (label, value)
    if rx.search(block):
        return rx.sub(lambda _m: line, block, count=1)
    m = STATUS_RE.search(block)
    return block[:m.start()] + line + "\n" + block[m.start():] if m else block.rstrip() + "\n" + line + "\n"


def fix_blocks(text):
    return [(i, b) for i, b in blocks(text) if i.startswith("F-")]


def fix_head(block):
    """[id, time, by, skill, kind] of '## F-001 · 2026-10-12 14:03 -05:00 · ana · video-quality-gates · edit'."""
    return (block.split("\n", 1)[0][3:].split(" · ") + [""] * 5)[:5]


def stamp():
    s = datetime.datetime.now().astimezone().isoformat(timespec="minutes")   # 2026-10-12T14:03-05:00
    return "%s %s %s" % (s[:10], s[11:16], s[16:])


def shelf_link(block):
    s = field(block, "Shelf")
    tail = s.split(" — ", 1)[1].strip() if " — " in s else ""
    return "" if s.startswith("no") or tail == PENDING else tail


def plugin_fixes(arg):
    """<plugin>/FIXES.md in a clone of the shelf — the plugin folder, or the clone's root."""
    p = Path(os.path.expanduser(arg)).resolve()
    for cand in (p, p / "skills" / "video" / "podcast-video"):
        if (cand / ".claude-plugin" / "plugin.json").is_file():
            if not any((d / ".git").exists() for d in [cand] + list(cand.parents)):
                refuse(T("%s no está dentro de un clon del shelf (no hay .git): FIXES.md va en el clon desde el que sale el PR",
                         "%s is not inside a clone of the shelf (no .git above it): FIXES.md goes into the clone "
                         "the pull request is made from") % cand)
            return cand / PLUGIN_FIXES_MD
    refuse(T("no encuentro el plugin podcast-video en %s (ni en su skills/video/podcast-video)",
             "no podcast-video plugin in %s (nor in its skills/video/podcast-video)") % p)


def to_plugin(target, block):
    """Write (or replace) one entry in the plugin's FIXES.md: it travels in the fix's own pull request."""
    b = re.sub(r"^- \*\*Patch:\*\* .*\n", "", block, flags=re.M)       # the diff is the pull request's own
    link = shelf_link(block)
    b = set_field(b, "Shelf", "the pull request that added this entry" + ((" — " + link) if link else ""))
    text = read_md(target) or PLUGIN_FIXES_HEADER
    me, out, put = fix_head(b)[:3], [], False
    for _, ob in fix_blocks(text):
        if fix_head(ob)[:3] == me:
            out.append(b)
            put = True
        else:
            out.append(ob)
    if not put:
        out.append(b)
    m = HEAD_RE.search(text)
    head = text[:m.start()] if m else text
    write_lf(target, head.rstrip() + "\n\n" + "\n\n".join(x.strip() for x in out) + "\n")


def _collect(folder):
    groups = {"open": [], "shelf": [], "team": [], "local": [], "decided": []}
    for i, b in fix_blocks(read_md(folder / FIXES_MD)):
        st, team = status_of(b), field(b, "For the team skill").split(" ", 1)[0].lower()
        key = ("open" if st == "open" else "decided" if st in ("promoted", "rejected")
               else "shelf" if not field(b, "Shelf").startswith("no")
               else "team" if team in ("yes", "decide") else "local")
        groups[key].append((i, b))
    rules = []
    for md in sorted(folder.glob("*.md")):
        if md.name not in (FIXES_MD, REPORT_MD):
            bl = [(i, b) for i, b in blocks(read_md(md)) if i.startswith("L-")]
            if bl:
                rules.append((md.stem, bl))
    return groups, rules


def _summary(groups, rules):
    nfix = sum(len(v) for v in groups.values())
    active = [(c, sum(status_of(b) == "active" for _, b in bl)) for c, bl in rules]
    return (T("%d arreglo(s): %d sin resolver, %d en el shelf, %d a decidir para la skill del equipo, %d solo locales, "
              "%d ya decididos · %d regla(s) aprendida(s) activa(s)%s",
              "%d fix(es): %d still open, %d in the shelf, %d to decide for the team skill, %d local only, "
              "%d already decided · %d learned rule(s) active%s")
            % (nfix, len(groups["open"]), len(groups["shelf"]), len(groups["team"]), len(groups["local"]),
               len(groups["decided"]), sum(n for _, n in active),
               (" (%s)" % ", ".join("%s %d" % (c, n) for c, n in active if n)) if any(n for _, n in active) else ""))


def brand_value(client, path):
    os.environ["GATES_CLIENT"] = client
    os.environ["GATES_NO_LEARNED"] = "1"
    try:
        return _profile._get(_profile.load(".", strict=True), path)
    except (SystemExit, KeyError):
        return None


def build_report(folder, owner=False):
    """WHAT-CHANGED.md: the one document for the owner — fixes, learned rules, what is open."""
    groups, rules = _collect(folder)
    here = ('"%s"' % folder) if owner else T('"<esta carpeta>"', '"<this folder>"')
    L = ["# " + T("Qué cambió mientras no estabas", "What changed while you were away"), "",
         T("Armado el %s con `learned.py %s`, de `%s`. Se rehace solo con cada arreglo anotado; "
           "`learned.py review %s` lo rehace en la computadora del dueño con lo último de la carpeta.",
           "Built %s with `learned.py %s`, from `%s`. It is rebuilt after every fix logged; "
           "`learned.py review %s` rebuilds it on the owner's computer from the latest files in the folder.")
         % (stamp(), "review" if owner else "report", folder, here), "",
         "**%s** %s." % (T("En resumen:", "In short:"), _summary(groups, rules))]
    n = 0
    for key, title in (("open", T("Sin resolver", "Still open — not solved")),
                       ("shelf", T("En el shelf (el PR lleva el cambio y su entrada en FIXES.md)",
                                   "In the shelf (the pull request carries the change and its entry in FIXES.md)")),
                       ("team", T("Solo en esta computadora — ¿para la skill del equipo?: sí / a decidir",
                                  "Only on this computer — for the team skill: yes / to decide")),
                       ("local", T("Solo en esta computadora — no para la skill del equipo",
                                   "Only on this computer — not for the team skill"))):
        if not groups[key]:
            continue
        n += 1
        L += ["", "## %d. %s" % (n, title)]
        for i, b in groups[key]:
            L += ["", "#" + b.strip()]
            pf = folder / "fixes" / (i + ".patch")
            if pf.is_file():
                diff = read_any(pf).rstrip("\n")
                if diff.count("\n") < PATCH_INLINE:
                    L += ["", fenced(diff, "diff")]
    if rules:
        n += 1
        L += ["", "## %d. %s" % (n, T("Reglas aprendidas de las correcciones", "Rules learned from corrections"))]
        for client, bl in rules:
            act = [(i, b) for i, b in bl if status_of(b) == "active"]
            L += ["", "### %s — %s (`%s.md`%s)" % (
                client.upper(), T("%d activa(s)", "%d active") % len(act), client,
                (T(", %d ya decidida(s)", ", %d already decided") % (len(bl) - len(act))) if len(bl) > len(act) else "")]
            overs = read_json(folder / ("%s.gates.json" % client)).get("overrides") or [] if owner else []
            for i, b in act:
                L += ["", "##" + b.strip()]
                for o in overs:
                    if o.get("id") == i and o.get("path"):
                        L.append(T("  → la marca dice hoy %s = %s", "  → the brand says %s = %s today")
                                 % (o["path"], json.dumps(brand_value(client, o["path"]))))
    if groups["decided"]:
        n += 1
        L += ["", "## %d. %s" % (n, T("Ya decidido por el dueño", "Already decided by the owner")), ""]
        L += ["- %s · %s · %s" % (i, fix_head(b)[3], field(b, "Status")) for i, b in groups["decided"]]
    n += 1
    fx = '"%s"' % (folder / FIXES_MD) if owner else T('"<esta carpeta>/fixes.md"', '"<this folder>/fixes.md"')
    L += ["", "## %d. %s" % (n, T("Para el dueño", "For the owner")), "",
          T("1. `learned.py review %s` muestra todo esto de nuevo, desde los archivos, en tu idioma y con cada número "
            "aprendido al lado del valor de la marca hoy.",
            "1. `learned.py review %s` prints all of this again from the files, in your language, with each learned "
            "number next to the brand's value today.") % here,
          T("2. **Sin resolver:** un error que las skills todavía tienen — arreglarlo primero.",
            "2. **Still open:** a bug the skills still have — fix it first."),
          T("3. **En el shelf:** el cambio ya está en el plugin (el PR y su entrada en FIXES.md); `sync_from_shelf.py "
            "--diff` muestra lo que tus skills no tienen. Se queda → `--apply` y `learned.py promote fixes <id> --file %s`; "
            "no → deshacerlo en un PR y `learned.py reject fixes <id> --why \"<…>\" --file %s`.",
            "3. **In the shelf:** the change is in the plugin already (the pull request, and its entry in FIXES.md); "
            "`sync_from_shelf.py --diff` shows what your own skills don't have yet. Keep it → `--apply`, then "
            "`learned.py promote fixes <id> --file %s`; undo it → a pull request, then "
            "`learned.py reject fixes <id> --why \"<…>\" --file %s`.") % (fx, fx),
          T("4. **Solo en esta computadora, para la skill del equipo:** aplicar el cambio en tus skills (el parche de la "
            "entrada, o lo que dice «Change»), `sync_to_shelf.py`, PR, y `promote fixes <id>` como arriba; si no vale, "
            "`reject … --why`.",
            "4. **Only on this computer, for the team skill:** apply the change to your skills (the entry's patch, or "
            "what \"Change\" says), `sync_to_shelf.py`, a pull request, then `promote fixes <id>` as above; not worth "
            "it → `reject … --why`."),
          T("5. **No para la skill del equipo:** nada, salvo que no estés de acuerdo.",
            "5. **Not for the team skill:** nothing to do, unless you disagree."),
          T("6. **Reglas aprendidas:** `video-quality-gates` SKILL.md → «The loop», 5 (promote / keep local / reject).",
            "6. **Learned rules:** `video-quality-gates` SKILL.md → \"The loop\", 5 (promote / keep local / reject).")]
    return "\n".join(L) + "\n"


def write_report(folder):
    out = Path(folder) / REPORT_MD
    write_lf(out, build_report(Path(folder)))
    return out


def cmd_fix(args):
    path = _profile.learned_dir() / FIXES_MD
    text = read_md(path) or FIXES_HEADER
    failed = trim_output(read_any(args.failed_file) if args.failed_file else args.failed)
    if not failed.strip():
        refuse(T("--failed / --failed-file vacío: va la salida real de lo que falló",
                 "--failed / --failed-file is empty: it takes the real output of what failed"))
    for name in ("skill", "cause", "change", "why"):
        if not one_line(getattr(args, name)):
            refuse(T("--%s vacío", "--%s is empty") % name)
    if not args.open and not one_line(args.checked):
        refuse(T("--checked (cómo se comprobó) hace falta, salvo con --open (sin resolver)",
                 "--checked (how it was verified) is required, except with --open (not solved)"))
    fid = "F-%03d" % (max([int(i[2:]) for i, _ in fix_blocks(text)] or [0]) + 1)
    kind = args.kind or ("edit" if args.files else "workaround")
    lines = ["## %s · %s · %s · %s · %s" % (fid, stamp(), one_line(args.by) or getpass.getuser(),
                                            one_line(args.skill), kind)]
    if args.where:
        lines.append("- **Where:** %s" % one_line(args.where))
    if args.files:
        lines.append("- **Files:** %s" % one_line(args.files))
    lines += ["- **Failed:**", fenced(failed, indent="  "),
              "- **Cause:** %s" % one_line(args.cause),
              "- **Change:** %s" % one_line(args.change)]
    if args.patch:
        diff = read_any(args.patch).replace("\r\n", "\n")
        write_lf(path.parent / "fixes" / (fid + ".patch"), diff)
        lines.append("- **Patch:** fixes/%s.patch (%d lines)" % (fid, len(diff.rstrip("\n").split("\n"))))
    lines += ["- **Checked:** %s" % (one_line(args.checked) or "not yet"),
              "- **Shelf:** " + SHELF_NO,
              "- **For the team skill:** %s — %s" % (args.team, one_line(args.why)),
              "- **Status:** " + ("open — not solved yet" if args.open else "done — solved on this computer")]
    write_lf(path, text.rstrip() + "\n\n" + "\n".join(lines) + "\n")
    rep = write_report(path.parent)
    print(T("%s guardado en %s — %s · %s · ¿para la skill del equipo?: %s",
            "%s saved in %s — %s · %s · for the team skill: %s") % (fid, path, kind, one_line(args.skill), args.team))
    print(T("  documento para el dueño al día: %s", "  the document for the owner is up to date: %s") % rep)
    if args.open:
        print(T('  sigue abierto: cuando se resuelva, learned.py fix-update %s --solved "<cómo>" --checked "<cómo se comprobó>"',
                '  still open: once solved, learned.py fix-update %s --solved "<how>" --checked "<how it was verified>"')
              % fid)
    print(T('  si va al shelf: antes del commit, learned.py fix-update %s --plugin "<clon del shelf>"; con el PR, '
            '--shelf "<link>" (y --merged al fusionarlo)',
            '  if it goes to the shelf: before the commit, learned.py fix-update %s --plugin "<shelf clone>"; with the '
            'pull request, --shelf "<link>" (and --merged once merged)') % fid)
    if owner_marker().is_file():
        print(T("  (esta es la computadora del dueño: un arreglo va directo a la skill; el registro es para las otras)",
                "  (this is the owner's computer: a fix goes straight into the skill; the log is for the other computers)"))
    return 0


def cmd_fix_update(args):
    path = _profile.learned_dir() / FIXES_MD
    text = read_md(path)
    fid = args.id.upper()
    found = [b for i, b in fix_blocks(text) if i == fid]
    if not found:
        refuse(T("%s no está en %s", "%s is not in %s") % (fid, path))
    if not (args.solved or args.checked or args.shelf or args.merged or args.plugin):
        refuse(T("nada que cambiar: --solved, --checked, --shelf, --merged o --plugin",
                 "nothing to change: --solved, --checked, --shelf, --merged or --plugin"))
    old = b = found[0]
    if args.solved:
        if status_of(b) != "open":
            refuse(T("%s no está abierto (%s)", "%s is not open (%s)") % (fid, field(b, "Status")))
        if not one_line(args.checked):
            refuse(T("--solved necesita --checked (cómo se comprobó)", "--solved needs --checked (how it was verified)"))
        today = datetime.date.today().isoformat()
        b = set_field(b, "Change", "%s · Solved %s: %s" % (field(b, "Change"), today, one_line(args.solved)))
        b = set_field(b, "Status", "done — solved on this computer (%s)" % today)
    if args.checked:
        b = set_field(b, "Checked", one_line(args.checked))
    link = one_line(args.shelf) or shelf_link(b)
    if args.merged and not link:
        refuse(T("--merged necesita el link del PR o del commit (--shelf)",
                 "--merged needs the pull request or commit link (--shelf)"))
    target = plugin_fixes(args.plugin) if args.plugin else None          # refused before anything is written
    if args.merged:
        b = set_field(b, "Shelf", "merged — " + link)
    elif args.shelf:
        b = set_field(b, "Shelf", "proposed — " + link)
    elif target and field(b, "Shelf").startswith("no"):
        b = set_field(b, "Shelf", "proposed — " + PENDING)
    write_lf(path, text.replace(old, b, 1))
    if target:
        to_plugin(target, b)
    rep = write_report(path.parent)
    print(T("%s actualizado en %s — %s · shelf: %s", "%s updated in %s — %s · shelf: %s")
          % (fid, path, field(b, "Status"), field(b, "Shelf")))
    if target:
        print(T("  copiado a %s: va en el mismo commit que el arreglo",
                "  copied into %s: it goes in the same commit as the fix") % target)
    print(T("  documento para el dueño al día: %s", "  the document for the owner is up to date: %s") % rep)
    return 0


def cmd_report(args):
    folder = _profile.learned_dir()
    out = Path(args.out) if args.out else folder / REPORT_MD
    write_lf(out, build_report(folder))
    print(T("Documento para el dueño: %s", "The document for the owner: %s") % out)
    print("  " + _summary(*_collect(folder)))
    print(T('  antes de que vuelva el dueño: copiar la carpeta %s entera a la carpeta de Drive "the studio Video Skills — '
            'Assets" como learned-<nombre>',
            '  before the owner is back: copy the whole folder %s into the Drive folder "the studio Video Skills — '
            'Assets" as learned-<name>') % folder)
    return 0


def show_fixes(all_):
    path = _profile.learned_dir() / FIXES_MD
    fx = [(i, b) for i, b in fix_blocks(read_md(path)) if all_ or status_of(b) not in ("promoted", "rejected")]
    if not fx:
        print(T("Sin arreglos anotados en esta computadora (%s).", "No fixes logged on this computer (%s).") % path)
        return 0
    print(T("Registro de arreglos de esta computadora — %d entrada(s) (%s):\n",
            "Fix log of this computer — %d entr(ies) (%s):\n") % (len(fx), path))
    for _, b in fx:
        print(b.rstrip() + "\n")
    return 0


def review_folder(folder):
    groups, rules = _collect(folder) if folder.is_dir() else ({}, [])
    if not any(groups.values()) and not rules:
        refuse(T("%s no tiene arreglos ni reglas aprendidas", "%s holds no fixes and no learned rules") % folder)
    print(build_report(folder, owner=True), end="")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("where")
    s = sub.add_parser("show"); s.add_argument("client"); s.add_argument("--all", action="store_true")
    a = sub.add_parser("add")
    a.add_argument("client"); a.add_argument("--said", required=True); a.add_argument("--rule", required=True)
    a.add_argument("--set"); a.add_argument("--area", default="general"); a.add_argument("--where")
    a.add_argument("--by"); a.add_argument("--new", action="store_true")
    for name in ("remove", "promote", "reject"):
        x = sub.add_parser(name); x.add_argument("client"); x.add_argument("id")
        if name != "remove":
            x.add_argument("--file")
        if name == "promote":
            x.add_argument("--to")
        if name == "reject":
            x.add_argument("--why", required=True)
    p = sub.add_parser("prune"); p.add_argument("client")
    r = sub.add_parser("review"); r.add_argument("file")
    f = sub.add_parser("fix")
    f.add_argument("--skill", required=True)
    g = f.add_mutually_exclusive_group(required=True)
    g.add_argument("--failed"); g.add_argument("--failed-file")
    f.add_argument("--cause", required=True); f.add_argument("--change", required=True)
    f.add_argument("--checked"); f.add_argument("--team", choices=TEAM, required=True)
    f.add_argument("--why", required=True); f.add_argument("--files"); f.add_argument("--kind", choices=KINDS)
    f.add_argument("--where"); f.add_argument("--patch"); f.add_argument("--open", action="store_true")
    f.add_argument("--by")
    u = sub.add_parser("fix-update"); u.add_argument("id")
    u.add_argument("--solved"); u.add_argument("--checked"); u.add_argument("--shelf")
    u.add_argument("--merged", action="store_true"); u.add_argument("--plugin")
    rp = sub.add_parser("report"); rp.add_argument("--out")
    args = ap.parse_args()
    if getattr(args, "client", None):
        args.client = args.client.lower()
    return {"where": cmd_where, "show": cmd_show, "add": cmd_add, "remove": cmd_remove,
            "promote": cmd_promote, "reject": cmd_reject, "prune": cmd_prune,
            "review": cmd_review, "fix": cmd_fix, "fix-update": cmd_fix_update,
            "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
