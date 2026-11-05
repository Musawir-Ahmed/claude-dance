# Author: Musawir Ahmed
"""Prepare and play one song (shared by the command line and the menu)."""
import os

from .audio import analyze_audio
from .lyrics import find_lyrics
from .songs import plan_song
from .show import dance


def prepare(path, meta, args, say=print):
    """Analyse the audio, pick style/tempo, look up lyrics. Returns a plan dict for perform()."""
    analysis = None
    if path:
        say("Analysing the audio...")
        analysis = analyze_audio(path)
    styles, bpm, max_s, notes = plan_song(path, meta, args, args.names, analysis)
    lyrics = []
    if path and not args.no_lyrics:
        say("Looking for lyrics...")
        lyrics = find_lyrics(path, meta)
    notes.append("lyrics: %d lines found" % len(lyrics) if lyrics else "lyrics: none found")
    title = (meta.get("title") if meta else None) or (os.path.basename(path) if path else "(silent)")
    return {"path": path, "meta": meta, "analysis": analysis, "styles": styles, "bpm": bpm, "max_s": max_s,
            "notes": notes, "lyrics": lyrics, "title": title}


def perform(plan, args, reply=None, forever=False, quit_text="quit", print_reply=True):
    """Run the dance for a prepared song. Returns 'done', 'next' or 'quit'."""
    return dance(plan["path"], plan["bpm"], float("inf") if forever else plan["max_s"], args.claude, plan["styles"],
                 mix=args.mix, crew=args.crew_n, formation=args.formation, speed=args.speed, spot=not args.no_spot,
                 title=plan["title"],
                 audio_note=None if plan["path"] else "SILENT - no song (drop an mp3 in songs/ or use --youtube)",
                 analysis=plan["analysis"], lyrics=plan["lyrics"], lyr_offset=args.lyrics_offset,
                 outfits=not args.plain, reply=reply, viz=not args.no_viz, sync=args.sync, keys=not args.no_keys,
                 forever=forever, lights=args.lights, theme=args.theme, quit_text=quit_text, print_reply=print_reply)
