# Author: Musawir Ahmed
"""Interactive music-player menu: search YouTube, pick a song, watch the crew dance to it."""
import codecs, json, math, os, random, re, select, shutil, sys, time

from .common import *
from .sprites import *
from .stage import LIGHT_MODES, THEMES, to_cells, serialize
from .songs import youtube_search, fetch_youtube, library, local_meta, fmt_duration
from .player import prepare, perform

try:
    import termios, tty
except ImportError:                                           # pragma: no cover
    termios = tty = None

SETTINGS_FILE = os.path.expanduser("~/.config/claude-dance/settings.json")
ACCENT, DIM, TEXT, HI, ERR = (255, 175, 95), (140, 135, 165), (235, 232, 225), (255, 220, 160), (255, 120, 120)
SAVED_KEYS = ("lights", "theme", "plain", "no_viz", "no_lyrics", "formation")


def col(text, c, bold=False):
    return "\x1b[%s38;2;%d;%d;%dm%s\x1b[0m" % ("1;" if bold else "", *c, text)


def clip(text, width):
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[:max(0, width - 1)] + "…"


KEYMAP = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end"}
TILDE = {"3": "delete", "5": "pgup", "6": "pgdn", "1": "home", "4": "end"}


def parse_keys(data, decoder):
    """Raw terminal bytes -> list of key names ('up', 'enter', 'esc', 'backspace', or a character)."""
    out, i = [], 0
    while i < len(data):
        if data[i:i + 1] == b"\x1b":
            m = re.match(rb"\x1b(?:\[|O)([0-9;]*)([A-Za-z~])", data[i:])
            if m:
                out.append(TILDE.get(m.group(1).decode()[:1], "?") if m.group(2) == b"~" else KEYMAP.get(m.group(2).decode(), "?"))
                i += m.end()
            else:
                out.append("esc")
                i += 1
            continue
        j = i
        while j < len(data) and data[j] != 0x1b:
            j += 1
        for ch in decoder.decode(data[i:j]):
            if ch in "\r\n":
                out.append("enter")
            elif ch in "\x7f\x08":
                out.append("backspace")
            elif ch == "\t":
                out.append("tab")
            elif ch == "\x03":
                raise KeyboardInterrupt
            elif ch.isprintable():
                out.append(ch)
        i = j
    return out


class UI:
    """The terminal: raw keys, alternate screen, drawing."""

    def __init__(self):
        self.fd, self.old = sys.stdin.fileno(), None
        self.dec = codecs.getincrementaldecoder("utf-8")(errors="ignore")

    def start(self):
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        sys.stdout.write("\x1b[?1049h\x1b[?25l")
        sys.stdout.flush()

    def stop(self):
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        if self.old:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
            termios.tcflush(self.fd, termios.TCIFLUSH)

    def size(self):
        c, r = shutil.get_terminal_size((80, 24))
        return c, max(r, 12)

    def keys(self, timeout=None):
        if not select.select([self.fd], [], [], timeout)[0]:
            return []
        return parse_keys(os.read(self.fd, 256), self.dec)

    def draw(self, lines, overlay=()):
        cols, rows = self.size()
        sys.stdout.write("\x1b[H" + "\x1b[K\n".join(lines[:rows - 1]) + "\x1b[K\x1b[J")
        for r, c, text in overlay:
            sys.stdout.write("\x1b[%d;%dH%s" % (r, c, text))
        sys.stdout.flush()

    def header(self, subtitle=""):
        cols, _ = self.size()
        return ["", "  " + col("♪ CLAUDE DANCE", ACCENT, True) + col("   terminal music player", DIM)
                + ((col("   ·   " + subtitle, TEXT)) if subtitle else ""),
                "  " + col("─" * max(10, cols - 4), (70, 66, 100))]

    def splash(self, lines):
        cols, rows = self.size()
        body = self.header() + [""] * max(1, (rows - 8) // 3)
        body += ["  " + col(l, TEXT if i == 0 else DIM) for i, l in enumerate(lines)]
        self.draw(body)

    def alert(self, text):
        self.splash([text, "", "press any key"])
        while not self.keys(None):
            pass


class Mini:
    """A little dancing Claude for the main screen."""

    def __init__(self):
        self.fit, self.next, self.t0 = random_outfit(), 0.0, 0.0
        self.a = self.b = make_pose(PARTY[0])

    def lines(self, now):
        if now >= self.next:
            self.a, self.b, self.t0, self.next = self.b, make_pose(random.choice(PARTY), 0.9), now, now + 0.5
        pose = blend(self.a, self.b, ease_back(min(1.0, (now - self.t0) / 0.35)))
        pose["dy"] -= 1.5 * abs(math.sin(now * 6.3))
        g = shrink(sprite(pose, ORANGE, 0, int(now * 3) % 11 == 0, pose["dy"] < -2.4, self.fit))
        g = g + [[None] * len(g[0])] * (len(g) % 2)
        return serialize(to_cells(g, len(g[0]), len(g) // 2))


# ----------------------------------------------------------------------------------- state + settings
class State:
    def __init__(self):
        self.queue, self.history, self.repeat = [], [], "off"

    def add_history(self, q):
        self.history = [q] + [h for h in self.history if h != q][:9]


def load_settings(args, st, build_parser):
    try:
        saved = json.load(open(SETTINGS_FILE))
    except (OSError, ValueError):
        saved = {}
    defaults = build_parser().parse_args([])
    for k in SAVED_KEYS:
        if k in saved and getattr(args, k) == getattr(defaults, k):
            setattr(args, k, saved[k])
    if args.crew == "1" and not saved.get("crew_n"):
        args.crew_n = 3                                       # a small crew looks best in the player
    elif args.crew == "1":
        args.crew_n = saved["crew_n"]
    if not args.dance and saved.get("names"):
        args.names = saved["names"]
    st.history, st.repeat = saved.get("history", []), saved.get("repeat", "off")


def save_settings(args, st):
    data = {k: getattr(args, k) for k in SAVED_KEYS}
    data.update(crew_n=args.crew_n, names=args.names, history=st.history, repeat=st.repeat)
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        json.dump(data, open(SETTINGS_FILE, "w"), ensure_ascii=False, indent=1)
    except OSError:
        pass


def cycle(values, current, step):
    i = values.index(current) if current in values else 0
    return values[(i + step) % len(values)]


def settings_items(args, st):
    """[(label, getter, setter(step))] for the settings screen."""
    styles = ["auto (from the song)"] + list(STYLES) + ["random mix"]

    def style_get():
        if not args.names:
            return styles[0]
        return styles[-1] if len(args.names) > 1 else args.names[0]

    def style_set(step):
        v = cycle(styles, style_get(), step)
        args.names = [] if v == styles[0] else (list(STYLES) if v == styles[-1] else [v])

    def toggle(attr, invert=False):
        return (lambda: "on" if bool(getattr(args, attr)) != invert else "off",
                lambda step: setattr(args, attr, not getattr(args, attr)))

    return [
        ("Dancers", lambda: str(args.crew_n), lambda s: setattr(args, "crew_n", cycle([1, 2, 3, 4, 5, 6, 8], args.crew_n, s))),
        ("Dance style", style_get, style_set),
        ("Formation", lambda: args.formation, lambda s: setattr(args, "formation", cycle(["auto"] + FORMATIONS, args.formation, s))),
        ("Lights", lambda: args.lights, lambda s: setattr(args, "lights", cycle(LIGHT_MODES, args.lights, s))),
        ("Theme", lambda: args.theme, lambda s: setattr(args, "theme", cycle(THEMES, args.theme, s))),
        ("Outfits and wigs",) + toggle("plain", invert=True),
        ("Lyrics",) + toggle("no_lyrics", invert=True),
        ("Equalizer",) + toggle("no_viz", invert=True),
        ("Repeat song", lambda: "on" if st.repeat == "song" else "off", lambda s: setattr(st, "repeat", "off" if st.repeat == "song" else "song")),
    ]


# ----------------------------------------------------------------------------------- generic screens
def pick(ui, items, fmt, hints, subtitle="", hotkeys=(), start=0, empty="Nothing here yet.", animate=None, footer=()):
    """List picker. Returns (key, index): key is 'enter', 'esc' or one of `hotkeys`."""
    sel, dirty = min(start, max(0, len(items) - 1)), True
    while True:
        if dirty or animate:
            cols, rows = ui.size()
            page = max(3, rows - 8 - len(footer))
            top = max(0, min(sel - page // 2, max(0, len(items) - page)))
            lines = ui.header(subtitle) + [""]
            for i in range(top, min(len(items), top + page)):
                text = fmt(items[i], cols - 8)
                lines.append(("  " + col("▶ ", ACCENT, True) + col(text, HI, True)) if i == sel else ("    " + col(text, TEXT)))
            if not items:
                lines.append("    " + col(empty, DIM))
            if len(items) > page:
                lines.append("    " + col("%d/%d" % (sel + 1, len(items)), DIM))
            lines += [""] + list(footer) + ["  " + col(hints, DIM)]
            overlay = []
            if animate and cols >= 62:
                overlay = [(4 + i, cols - 20, l) for i, l in enumerate(animate.lines(time.time()))]
            ui.draw(lines, overlay)
            dirty = False
        for k in ui.keys(0.1 if animate else None):
            dirty = True
            if k in ("up", "k") and items:
                sel = (sel - 1) % len(items)
            elif k in ("down", "j") and items:
                sel = (sel + 1) % len(items)
            elif k == "pgup":
                sel = max(0, sel - 8)
            elif k == "pgdn":
                sel = min(len(items) - 1, sel + 8)
            elif k == "home":
                sel = 0
            elif k == "end":
                sel = max(0, len(items) - 1)
            elif k == "enter" and items:
                return "enter", sel
            elif k == "esc":
                return "esc", sel
            elif k in hotkeys:
                return k, sel


def ask(ui, prompt, history):
    text, hi = "", -1
    while True:
        cols, rows = ui.size()
        lines = ui.header("search") + ["", "  " + col(prompt, TEXT), "",
                                       "  " + col("› ", ACCENT, True) + col(text, HI, True) + col("▏", ACCENT)]
        if history:
            lines += ["", "  " + col("recent (↑/↓):", DIM)]
            lines += ["    " + col(("▸ " if i == hi else "  ") + clip(h, cols - 12), HI if i == hi else DIM) for i, h in enumerate(history[:6])]
        lines += ["", "  " + col("[enter] search   [esc] back", DIM)]
        ui.draw(lines)
        for k in ui.keys(None):
            if k == "enter":
                return text.strip() or None
            if k == "esc":
                return None
            if k == "backspace":
                text, hi = text[:-1], -1
            elif k == "up" and history:
                hi = min(min(len(history), 6) - 1, hi + 1); text = history[hi]
            elif k == "down" and history:
                hi = max(-1, hi - 1); text = history[hi] if hi >= 0 else ""
            elif len(k) == 1:
                text, hi = text + k, -1


def fmt_entry(e, width):
    dur = fmt_duration(e.get("duration"))
    who = clip(e.get("uploader") or "", 22)
    room = max(10, width - len(dur) - len(who) - 8)
    return "%s   %s%s" % (clip(e["title"], room), dur, ("   " + who) if who else "")


# ----------------------------------------------------------------------------------- playing
def play_one(ui, args, st, e):
    ui.splash(["Preparing: " + e["title"], "", "…"])
    if not e.get("path"):
        if e["kind"] == "youtube":
            ui.splash(["Downloading: " + e["title"], "", "first time only - it is cached afterwards"])
            path, meta = fetch_youtube(e["value"], quiet=True)
            if not path:
                ui.alert("Could not download that song (no internet, or yt-dlp missing?)")
                return "error"
            e["path"], e["meta"] = path, meta
        else:
            e["path"], e["meta"] = e["value"], local_meta(e["value"])
    plan = prepare(e["path"], e["meta"], args, say=lambda m: ui.splash([e["title"], "", m]))
    ui.stop()
    try:
        return perform(plan, args, reply=None if args.claude else "", quit_text="menu", print_reply=False)
    finally:
        ui.start()


def play(ui, args, st, entry):
    cur = entry
    while cur:
        action = play_one(ui, args, st, cur)
        if action in ("quit", "error"):
            return
        if st.repeat == "song":
            continue
        cur = st.queue.pop(0) if st.queue else None


def to_entry(r):
    return {"title": r["title"], "uploader": r.get("uploader", ""), "duration": r.get("duration"),
            "kind": r.get("kind", "youtube"), "value": r.get("value") or r.get("url")}


# ----------------------------------------------------------------------------------- screens
def results_screen(ui, args, st, query, results):
    sel = 0
    while True:
        k, sel = pick(ui, results, fmt_entry, "[↑↓] move   [enter] play   [a] add to queue   [p] play all   [/] new search   [esc] back",
                      subtitle="results for “%s”" % clip(query, 30), hotkeys=("a", "p", "/"), start=sel)
        if k == "esc":
            return "back"
        if k == "/":
            return "search"
        if k == "a":
            st.queue.append(to_entry(results[sel]))
        elif k == "p":
            st.queue = [to_entry(r) for r in results[sel + 1:]]
            play(ui, args, st, to_entry(results[sel]))
        elif k == "enter":
            play(ui, args, st, to_entry(results[sel]))


def search_screen(ui, args, st):
    while True:
        q = ask(ui, "Search YouTube - a song, an artist, or paste a link", st.history)
        if not q:
            return
        ui.splash(["Searching for “%s” …" % q])
        try:
            results = youtube_search(q, 12)
        except Exception as e:
            ui.alert("Search failed: %s" % clip(e, 90))
            continue
        if not results:
            ui.alert("No results for “%s”" % q)
            continue
        st.add_history(q)
        save_settings(args, st)
        results_screen(ui, args, st, q, results)             # esc or "/" both return to the search box


def library_screen(ui, args, st):
    sel = 0
    while True:
        items = [to_entry(i) | {"kind": "file", "value": i["value"]} for i in library(args.songs_dir)]
        k, sel = pick(ui, items, fmt_entry, "[enter] play   [a] add to queue   [p] play all   [esc] back",
                      subtitle="my library", hotkeys=("a", "p"), start=sel,
                      empty="No songs yet. Search YouTube, or drop mp3 files into the songs folder.")
        if k == "esc":
            return
        if not items:
            continue
        if k == "a":
            st.queue.append(items[sel])
        elif k == "p":
            st.queue = items[sel + 1:]
            play(ui, args, st, items[sel])
        else:
            play(ui, args, st, items[sel])


def queue_screen(ui, args, st):
    sel = 0
    while True:
        k, sel = pick(ui, st.queue, fmt_entry, "[enter] play from here   [d] remove   [c] clear   [esc] back",
                      subtitle="queue", hotkeys=("d", "c"), start=sel, empty="The queue is empty. Press [a] on a song to add it.")
        if k == "esc":
            return
        if k == "c":
            st.queue = []
        elif k == "d" and st.queue:
            st.queue.pop(sel)
        elif k == "enter":
            entry = st.queue[sel]
            st.queue = st.queue[sel + 1:]
            play(ui, args, st, entry)


def settings_screen(ui, args, st):
    items, sel = settings_items(args, st), 0
    while True:
        cols, rows = ui.size()
        lines = ui.header("settings") + [""]
        for i, (label, get, _) in enumerate(items):
            on = i == sel
            lines.append("  " + (col("▶ ", ACCENT, True) if on else "  ") + col(label.ljust(18), HI if on else TEXT, on)
                         + col("‹ ", DIM) + col(get(), ACCENT if on else TEXT, on) + col(" ›", DIM))
        lines += ["", "  " + col("[↑↓] move   [←/→/enter] change   [esc] back (saved)", DIM)]
        ui.draw(lines)
        for k in ui.keys(None):
            if k == "up":
                sel = (sel - 1) % len(items)
            elif k == "down":
                sel = (sel + 1) % len(items)
            elif k in ("left", "right", "enter"):
                items[sel][2](-1 if k == "left" else 1)
            elif k == "esc":
                save_settings(args, st)
                return


def main_screen(ui, args, st):
    mini, sel = Mini(), 0
    while True:
        n_lib = len(library(args.songs_dir))
        items = [("search", "Search YouTube"), ("library", "My library   (%d songs)" % n_lib),
                 ("queue", "Queue   (%d)" % len(st.queue)), ("settings", "Settings"), ("quit", "Quit")]
        summary = "dancers %d · style %s · lights %s · %s theme" % (
            args.crew_n, "/".join(args.names) if len(args.names) == 1 else ("auto" if not args.names else "mix"), args.lights, args.theme)
        k, sel = pick(ui, items, lambda it, w: it[1], "[↑↓] move   [enter] select   [/] search   [q] quit", hotkeys=("/", "q"),
                      start=sel, animate=mini, footer=["  " + col(summary, DIM)])
        choice = "search" if k == "/" else ("quit" if k in ("q", "esc") else items[sel][0])
        if choice == "quit":
            return
        {"search": search_screen, "library": library_screen, "queue": queue_screen, "settings": settings_screen}[choice](ui, args, st)


def run_menu(args):
    from .cli import build_parser
    if not (sys.stdin.isatty() and sys.stdout.isatty() and termios):
        sys.exit("The menu needs an interactive terminal. Use --youtube / --song to play without it.")
    args.full = True                                          # a music player plays whole songs
    st = State()
    load_settings(args, st, build_parser)
    ui = UI()
    ui.start()
    try:
        main_screen(ui, args, st)
    finally:
        ui.stop()
        save_settings(args, st)
