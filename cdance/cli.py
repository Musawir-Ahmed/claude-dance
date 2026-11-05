# Author: Musawir Ahmed
import argparse, json, os, random, shutil, signal, sys, time

from .common import *
from .sprites import *
from .stage import LIGHT_MODES, THEMES
from .audio import analyze_audio
from .lyrics import find_lyrics
from .songs import build_queue, load_source, plan_song
from .player import prepare, perform
from . import hook

VALUE_FLAGS = {"--min-wait", "--max-wait"}            # hook-only flags that are not passed on to the dance
SWITCH_FLAGS = {"--hook", "--install-hook", "--uninstall-hook", "--yes", "--hook-dry-run"}


def build_parser():
    ap = argparse.ArgumentParser(description="Make Claude dance in your terminal")
    src = ap.add_argument_group("songs")
    src.add_argument("--youtube", action="append", metavar="QUERY_OR_URL",
                     help="search YouTube (or give a URL) and play it; repeat for a playlist")
    src.add_argument("--song", action="append", help="audio file to play; repeat for a playlist")
    src.add_argument("--playlist-file", help="text file, one song per line (file path, URL or search words)")
    src.add_argument("--all", action="store_true", help="play every song in ./songs")
    src.add_argument("--shuffle", action="store_true", help="shuffle the playlist")
    src.add_argument("--songs-dir", default=os.path.join(ROOT, "songs"))
    src.add_argument("--full", action="store_true", help="dance for the whole song")
    src.add_argument("--menu", action="store_true", help="open the music-player menu (default when no song is given)")
    src.add_argument("--no-menu", action="store_true", help="never open the menu; play a random local song instead")
    src.add_argument("--forever", "--endless", action="store_true",
                     help="never close by itself: keep dancing, song after song, until you press q or Ctrl-C")
    src.add_argument("--max-seconds", type=float, default=45, help="longest single dance (default 45)")
    src.add_argument("--no-lyrics", action="store_true", help="don't look up lyrics")
    src.add_argument("--lyrics-offset", type=float, default=0.0, metavar="SEC",
                     help="shift lyrics later (+) or earlier (-) if they are out of sync")

    d = ap.add_argument_group("dancing")
    d.add_argument("--dance", default=None, metavar="STYLE",
                   help="%s; comma-separate to pick randomly from several; 'random' = any. "
                        "Default: chosen from the song's metadata" % ", ".join(STYLES))
    d.add_argument("--mix", action="store_true", help="switch style every 8 beats")
    d.add_argument("--list-dances", action="store_true")
    d.add_argument("--crew", default="1", metavar="N", help="number of dancers, each on their own beat (or 'random')")
    d.add_argument("--formation", default="auto", metavar="F", help="auto (cycles), " + ", ".join(FORMATIONS))
    d.add_argument("--no-roam", action="store_true", help="same as --formation line")
    d.add_argument("--speed", type=float, default=1.0, help="how fast dancers travel (default 1.0)")
    d.add_argument("--bpm", type=float, default=None, help="override the tempo (default: detected)")
    d.add_argument("--sync", type=float, default=0.12, metavar="SEC",
                   help="audio start latency; raise it if the moves land late (default 0.12)")

    look = ap.add_argument_group("look")
    look.add_argument("--plain", action="store_true", help="no outfits, hair or hats")
    look.add_argument("--lights", default="auto", metavar="MODE",
                      help="auto (follows the music), low, high, strobe, pulse, disco, off. Press l to cycle")
    look.add_argument("--theme", default="dark", choices=["dark", "light"],
                      help="dark stage (default) or light stage for light-coloured terminals. Press t to switch")
    look.add_argument("--light", dest="theme", action="store_const", const="light", help="same as --theme light")
    look.add_argument("--no-spot", action="store_true", help="plain terminal background, no stage lighting")
    look.add_argument("--no-viz", action="store_true", help="hide the equalizer")
    look.add_argument("--no-keys", action="store_true", help="disable keyboard controls")

    c = ap.add_argument_group("Claude")
    c.add_argument("--claude", metavar="PROMPT", help="get the reply from `claude -p PROMPT`")
    c.add_argument("--reply-file", help="show the text in this file as the reply")
    c.add_argument("--delete-reply-file", action="store_true", help=argparse.SUPPRESS)
    c.add_argument("--hook", action="store_true", help="run as a Claude Code Stop hook (pops up a dance now and then)")
    c.add_argument("--install-hook", action="store_true", help="show the Stop-hook entry for ~/.claude/settings.json")
    c.add_argument("--uninstall-hook", action="store_true", help="remove the Claude Code Stop hook (turns the popups off)")
    c.add_argument("--yes", action="store_true", help="with --install-hook: really write it")
    c.add_argument("--hook-dry-run", action="store_true", help=argparse.SUPPRESS)
    c.add_argument("--loop", action="store_true", help="repeat forever at random intervals")
    c.add_argument("--min-wait", type=float, default=None, help="min seconds between dances (default 60; 120 for the hook)")
    c.add_argument("--max-wait", type=float, default=None, help="max seconds between dances (default 600; 900 for the hook)")
    return ap


def passthrough_args(argv):
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
        elif a in VALUE_FLAGS:
            skip = True
        elif any(a.startswith(f + "=") for f in VALUE_FLAGS) or a in SWITCH_FLAGS:
            continue
        else:
            out.append(a)
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ap = build_parser()
    args = ap.parse_args(argv)

    if args.list_dances:
        print("\n".join(STYLES)); return
    if args.uninstall_hook:
        n = hook.uninstall_hook()
        print("Removed %d Claude Dance hook(s) from %s." % (n, hook.SETTINGS) if n else "No Claude Dance hook was installed.")
        return
    if args.install_hook:
        entry, wrote = hook.install_hook(passthrough_args(argv), write=args.yes)
        print(json.dumps({"hooks": {"Stop": [entry]}}, indent=2))
        print("\nWritten to %s" % hook.SETTINGS if wrote else
              "\nNot written. Re-run with --yes to merge it into %s (a backup is kept), or paste it there yourself." % hook.SETTINGS)
        return
    if args.hook:
        hook.run_hook(passthrough_args(argv), args.min_wait or 120, args.max_wait or 900, args.hook_dry_run)
        return
    min_wait, max_wait = args.min_wait or 60, args.max_wait or 600

    names = [n.strip().lower() for n in (args.dance or "").split(",") if n.strip()]
    if "random" in names or "all" in names:
        names = list(STYLES)
    bad = [n for n in names if n not in STYLES]
    if bad:
        ap.error("unknown dance %s (choose from: %s)" % (", ".join(bad), ", ".join(STYLES)))
    formation = "line" if args.no_roam else args.formation.lower()
    if formation not in ["auto"] + FORMATIONS:
        ap.error("--formation must be one of: auto, " + ", ".join(FORMATIONS))
    if args.crew.lower() == "random":
        crew = random.randint(2, 5)
    else:
        try:
            crew = int(args.crew)
        except ValueError:
            ap.error("--crew must be a number or 'random'")
    args.crew_n = crew
    if args.lights not in LIGHT_MODES:
        ap.error("--lights must be one of: " + ", ".join(LIGHT_MODES))

    reply = None
    if args.reply_file:
        try:
            reply = open(args.reply_file, encoding="utf-8").read().strip() or None
            if args.delete_reply_file:
                os.remove(args.reply_file)
        except OSError:
            pass

    args.names, args.formation = names, formation
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    explicit = bool(args.youtube or args.song or args.playlist_file or args.all)
    if args.menu or (not explicit and not args.no_menu and not args.forever and not args.reply_file
                     and sys.stdin.isatty() and sys.stdout.isatty()):
        from .menu import run_menu
        return run_menu(args)
    while True:
        played, action = 0, "done"
        for src in build_queue(args):
            song, meta = load_source(src)
            if src[0] in ("youtube", "file") and not song:
                print("Skipping %s (no audio)." % src[1])
                continue
            plan = prepare(song, meta, args)
            print("Now playing: %s\n  %s" % (plan["title"], "\n  ".join(plan["notes"])))
            action = perform(plan, args, reply=reply, forever=args.forever)
            played += 1
            reply = None                                   # the reply is only for the first song
            if action == "quit":
                return
        if args.youtube and not played and not args.loop:
            sys.exit("Could not get audio from YouTube (see the message above), so I'm not dancing silently.")
        if args.forever and played:                        # endless: straight on to the next round
            continue
        if action == "next" and not explicit:              # 'n' with random local songs: pick another
            continue
        if not args.loop:
            break
        wait = random.uniform(min_wait, max_wait)
        print("Next dance in %d s (Ctrl-C to stop)" % wait)
        time.sleep(wait)
