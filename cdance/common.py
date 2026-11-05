# Author: Musawir Ahmed
import argparse, array, bisect, glob, html, json, math, os, random, re, shutil, signal, subprocess, sys, textwrap, threading, time
import urllib.parse, urllib.request


AUDIO_EXTS = ("mp3", "ogg", "wav", "m4a", "opus", "flac", "webm", "mp4")


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "songs", "youtube")


def find_ytdlp():
    exe = shutil.which("yt-dlp") or os.path.expanduser("~/.local/bin/yt-dlp")
    if os.path.exists(exe):
        return [exe]
    if subprocess.run([sys.executable, "-c", "import yt_dlp"], capture_output=True).returncode == 0:
        return [sys.executable, "-m", "yt_dlp"]
    return None


REPLIES = [
    "بشرة خير! Good news is on the way, keep going.",
    "Bushra khair! Your code compiles on the first try today. (Probably.)",
    "All tests are green in my dreams, and soon in yours too.",
    "Take a breath, drink some water, and ship it. I'm dancing for you!",
    "You asked for a reply, so here is a dance and a smile. :)",
    "بشرة خير إن شاء الله - something good is coming your way.",
]


def get_reply(prompt):
    if prompt and shutil.which("claude"):
        try:
            r = subprocess.run(["claude", "-p", prompt + " (reply in 2 short sentences)"],
                               capture_output=True, text=True, timeout=90)
            if r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
    return random.choice(REPLIES)
