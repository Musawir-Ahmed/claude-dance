# Author: Musawir Ahmed
"""Claude Code integration: pop up a dance (with Claude's last reply in the text box) after a response.

  python3 dance.py --hook --crew random            # what the Stop hook runs
  python3 dance.py --install-hook [--yes]          # show / write the hook entry in ~/.claude/settings.json

A random wait (--min-wait .. --max-wait seconds) is enforced between dances, so it only pops up now and then.
"""
import json, os, random, shutil, subprocess, sys, tempfile, time

STATE_FILE = os.path.expanduser("~/.cache/claude-dance/state.json")
SETTINGS = os.path.expanduser("~/.claude/settings.json")

TERMINALS = [                       # (executable, args placed before the command)
    ("kitty", []), ("alacritty", ["-e"]), ("gnome-terminal", ["--"]), ("konsole", ["-e"]),
    ("xfce4-terminal", ["-x"]), ("tilix", ["-e"]), ("wezterm", ["start", "--"]),
    ("x-terminal-emulator", ["-e"]), ("xterm", ["-e"]),
]


def last_assistant_text(transcript_path, limit=260):
    """The most recent assistant text in a Claude Code transcript (JSONL), trimmed to a short snippet."""
    try:
        lines = open(transcript_path, encoding="utf-8").read().splitlines()
    except (OSError, TypeError):
        return None
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        msg = entry.get("message") or {}
        if entry.get("type") != "assistant" and msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            text = content
        else:
            text = " ".join(b.get("text", "") for b in (content or []) if isinstance(b, dict) and b.get("type") == "text")
        text = " ".join(text.split())
        if text:
            return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"
    return None


def due(min_wait, max_wait, now=None, state_file=STATE_FILE):
    """True if the random waiting period since the last dance is over (and starts the next period)."""
    now = now or time.time()
    try:
        state = json.load(open(state_file))
    except (OSError, ValueError):
        state = {}
    if now < state.get("last", 0) + state.get("wait", 0):
        return False
    try:
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        json.dump({"last": now, "wait": random.uniform(min_wait, max_wait)}, open(state_file, "w"))
    except OSError:
        pass
    return True


def terminal_command(cmd):
    """Wrap `cmd` (a list) so it opens in a new terminal window / tmux popup. None if we can't find one."""
    if os.environ.get("TMUX") and shutil.which("tmux"):
        return ["tmux", "display-popup", "-E", "-w", "90%", "-h", "90%", " ".join(map(_quote, cmd))]
    for exe, pre in TERMINALS:
        if shutil.which(exe):
            return [exe, *pre, *cmd]
    return None


def _quote(s):
    import shlex
    return shlex.quote(s)


def run_hook(passthrough, min_wait=120, max_wait=900, dry_run=False, stdin=None):
    """Called by the Claude Code Stop hook. Never raises and never blocks. Returns the command it spawned."""
    try:
        data = json.load(stdin or sys.stdin)
    except Exception:
        data = {}
    if data.get("stop_hook_active"):
        return None
    if not due(min_wait, max_wait):
        return None
    reply = last_assistant_text(data.get("transcript_path")) or "All done! Here's a little dance for you."
    fd, path = tempfile.mkstemp(prefix="claude-dance-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(reply)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cmd = [sys.executable, os.path.join(here, "dance.py"), "--reply-file", path, "--delete-reply-file",
           "--max-seconds", "30", *passthrough]
    wrapped = terminal_command(cmd)
    if dry_run or not wrapped:
        return wrapped or cmd
    subprocess.Popen(wrapped, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return wrapped


def install_hook(passthrough, write=False, settings_path=SETTINGS):
    """Return the hook JSON entry; with write=True merge it into settings.json (with a backup)."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command = " ".join([_quote(sys.executable), _quote(os.path.join(here, "dance.py")), "--hook", *map(_quote, passthrough)])
    entry = {"matcher": "", "hooks": [{"type": "command", "command": command}]}
    if write:
        try:
            settings = json.load(open(settings_path))
        except (OSError, ValueError):
            settings = {}
        stops = settings.setdefault("hooks", {}).setdefault("Stop", [])
        if any(command == h.get("command") for e in stops for h in e.get("hooks", [])):
            return entry, False
        if os.path.exists(settings_path):
            shutil.copy(settings_path, settings_path + ".bak-claude-dance")
        stops.append(entry)
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        json.dump(settings, open(settings_path, "w"), indent=2)
    return entry, write


def uninstall_hook(settings_path=SETTINGS):
    """Remove every Claude Dance Stop hook from settings.json (backup kept). Returns how many were removed."""
    try:
        settings = json.load(open(settings_path))
    except (OSError, ValueError):
        return 0
    stops, removed, kept = settings.get("hooks", {}).get("Stop", []), 0, []
    for entry in stops:
        hooks = [x for x in entry.get("hooks", []) if "dance.py" not in x.get("command", "") or "--hook" not in x.get("command", "")]
        removed += len(entry.get("hooks", [])) - len(hooks)
        if hooks:
            kept.append({**entry, "hooks": hooks})
    if removed:
        shutil.copy(settings_path, settings_path + ".bak-claude-dance")
        if kept:
            settings["hooks"]["Stop"] = kept
        else:
            settings["hooks"].pop("Stop", None)
            if not settings["hooks"]:
                settings.pop("hooks")
        json.dump(settings, open(settings_path, "w"), indent=2)
    return removed
