# Author: Musawir Ahmed
import argparse, array, bisect, glob, html, json, math, os, random, re, shutil, signal, subprocess, sys, textwrap, threading, time
import urllib.parse, urllib.request
from .common import *
from .sprites import *
from .audio import *
from .lyrics import *


GENRE_RULES = {
    "breakdance": (95, ["hip hop", "hip-hop", "hiphop", "rap", "trap", "drill", "boom bap", "breakbeat", "rnb"]),
    "salsa": (100, ["salsa", "latin", "reggaeton", "bachata", "merengue", "cumbia", "mambo", "rumba", "flamenco"]),
    "disco": (118, ["disco", "funk", "soul", "motown", "80s", "70s", "synthwave", "retro", "groove"]),
    "robot": (128, ["techno", "edm", "electronic", "house", "trance", "dubstep", "industrial", "electro", "robot"]),
    "floss": (120, ["pop", "dance", "kids", "viral", "tiktok", "remix", "k-pop", "kpop", "party mix"]),
    "moonwalk": (116, ["michael jackson", "jackson 5", "thriller", "billie jean", "smooth criminal", "moonwalk"]),
    "wave": (92, ["chill", "lofi", "lo-fi", "ambient", "relax", "r&b", "slow jam", "lounge"]),
    "party": (105, ["nasheed", "anasheed", "islamic", "arabic", "nashid", "بشرة", "نشيد", "أناشيد", "folk",
                    "bushra", "boshret", "boshra", "bushrah", "بشرى", "bollywood", "wedding", "celebration", "happy", "acoustic", "eid", "طرب"]),
}


def decide_style(meta):
    """Score every style against the song's metadata. Returns (style or None, runner_up, reason)."""
    fields = [(str(meta.get("title") or ""), 3), (" ".join(meta.get("tags") or []), 2),
              (" ".join([str(meta.get("genre") or ""), str(meta.get("artist") or ""),
                         " ".join(meta.get("categories") or []), str(meta.get("uploader") or "")]), 2),
              (str(meta.get("description") or "")[:400], 1)]
    hits, score = {}, {}
    for style, (_, words) in GENRE_RULES.items():
        for text, weight in fields:
            low = text.lower()
            for w in words:
                if w in low:
                    hits.setdefault(style, set()).add(w)
                    score[style] = score.get(style, 0) + weight
    ranked = sorted(score, key=lambda k: -score[k])
    if not ranked:
        return None, None, "no genre hints in metadata"
    best = ranked[0]
    return best, (ranked[1] if len(ranked) > 1 else None), "matched %s" % ", ".join(sorted(hits[best])[:3])


def local_meta(path):
    meta = {"title": os.path.splitext(os.path.basename(path))[0].replace("_", " ")}
    side = os.path.splitext(path)[0] + ".json"
    if os.path.exists(side):
        try:
            meta.update(json.load(open(side, encoding="utf-8")))
            return meta
        except (OSError, ValueError):
            pass
    if shutil.which("ffprobe"):
        try:
            r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
                               capture_output=True, text=True, timeout=20)
            fmt = json.loads(r.stdout).get("format", {})
            tags = {k.lower(): v for k, v in fmt.get("tags", {}).items()}
            for k in ("title", "artist", "genre"):
                if tags.get(k):
                    meta[k] = tags[k]
            if tags.get("bpm") or tags.get("tbpm"):
                meta["bpm"] = float(tags.get("bpm") or tags.get("tbpm"))
            meta["duration"] = float(fmt.get("duration", 0)) or None
        except Exception:
            pass
    return meta


def youtube_api_lookup(query, key):
    """Optional: YouTube Data API v3 -> (video url, snippet metadata). Needs YOUTUBE_API_KEY."""
    def call(endpoint, **params):
        params["key"] = key
        url = "https://www.googleapis.com/youtube/v3/%s?%s" % (endpoint, urllib.parse.urlencode(params))
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode())
    m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", query)
    vid = m.group(1) if m else call("search", part="id", q=query, type="video", maxResults=1,
                                    videoCategoryId="10")["items"][0]["id"]["videoId"]
    sn = call("videos", part="snippet", id=vid)["items"][0]["snippet"]
    meta = {"title": html.unescape(sn.get("title", "")), "tags": sn.get("tags", []),
            "uploader": sn.get("channelTitle"), "description": sn.get("description", ""),
            "categories": [sn.get("categoryId", "")]}
    return "https://www.youtube.com/watch?v=" + vid, meta


def fetch_youtube(query, quiet=False):
    """Find/download a song from YouTube. Returns (audio file path, metadata) or (None, None)."""
    say = (lambda *a, **k: None) if quiet else print
    ytdlp = find_ytdlp()
    if not ytdlp:
        say("yt-dlp is not installed. Install it with:\n"
              "  pip install --user --break-system-packages yt-dlp     (or: pipx install yt-dlp)")
        return None, None
    api_meta, target = None, query
    key = os.environ.get("YOUTUBE_API_KEY")
    if key:
        try:
            target, api_meta = youtube_api_lookup(query, key)
        except Exception as e:
            say("YouTube API lookup failed (%s) - falling back to yt-dlp search." % e)
    if target == query and not re.match(r"https?://", query):
        target = "ytsearch1:" + query
    os.makedirs(CACHE_DIR, exist_ok=True)
    say("Fetching from YouTube: %s" % query)
    r = subprocess.run([*ytdlp, "--no-playlist", "-q", "--no-warnings", "--dump-json", "--no-simulate",
                        "-f", "bestaudio[ext=m4a]/bestaudio/best",
                        "-o", os.path.join(CACHE_DIR, "%(id)s.%(ext)s"), target],
                       capture_output=True, text=True, timeout=300)
    try:
        info = json.loads(r.stdout.strip().splitlines()[-1])
        if info.get("_type") == "playlist":
            info = info["entries"][0]
        path = (info.get("requested_downloads") or [{}])[0].get("filepath") or info.get("_filename")
    except Exception:
        say("Could not download that video: %s" % (r.stderr.strip().splitlines() or ["unknown error"])[-1])
        return None, None
    meta = {"title": info.get("track") or info.get("title"), "artist": info.get("artist"),
            "genre": info.get("genre"), "tags": info.get("tags") or [], "categories": info.get("categories") or [],
            "uploader": info.get("uploader"), "description": info.get("description") or "",
            "duration": info.get("duration")}
    if api_meta:                                    # the API's snippet is the authoritative metadata
        meta.update({k: v for k, v in api_meta.items() if v})
    try:                                            # remember it so replaying with --song still knows the title
        with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
    except OSError:
        pass
    return path, meta


def song_files(songs_dir):
    files = []
    for ext in AUDIO_EXTS:
        files += glob.glob(os.path.join(songs_dir, "*." + ext))
        files += glob.glob(os.path.join(songs_dir, "youtube", "*." + ext))
    return sorted(files)


def build_queue(args):
    """The list of things to play: [("youtube", query) | ("file", path)], in order."""
    q = [("youtube", y) for y in (args.youtube or [])] + [("file", f) for f in (args.song or [])]
    if args.playlist_file:
        for line in open(args.playlist_file, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                q.append(("file", line) if os.path.exists(line) else ("youtube", line))
    if args.all:
        q += [("file", f) for f in song_files(args.songs_dir)]
    if not q:                                           # nothing asked for: one random local song
        files = song_files(args.songs_dir)
        q = [("file", random.choice(files))] if files else [("none", None)]
    if args.shuffle:
        random.shuffle(q)
    return q


def load_source(src):
    """-> (path or None, metadata dict)"""
    kind, value = src
    if kind == "youtube":
        path, meta = fetch_youtube(value)
        return (path, meta) if path else (None, {})
    if kind == "file":
        return value, local_meta(value)
    return None, {}


def plan_song(path, meta, args, names, analysis=None):
    """Decide style(s), tempo and length from the song. Returns (styles, bpm, max_seconds, notes)."""
    notes = []
    best, second, why = decide_style(meta) if meta else (None, None, "no metadata")
    if names:                                                      # user chose explicitly
        styles = names
        notes.append("style: %s (you chose)" % "/".join(names))
    elif best:
        styles = [best] if args.crew_n == 1 else [best, best, second or random.choice(list(STYLES))]
        notes.append("style: %s (%s)" % (best, why))
    else:
        styles = list(STYLES)
        notes.append("style: random (%s)" % why)

    bpm = args.bpm
    if bpm:
        notes.append("bpm: %g (you chose)" % bpm)
    else:
        text = " ".join([str(meta.get("title") or ""), " ".join(meta.get("tags") or []),
                         str(meta.get("description") or "")[:300]]).lower()
        m = re.search(r"\b(\d{2,3})\s*bpm\b", text)
        det = None
        if meta.get("bpm"):
            bpm, src = float(meta["bpm"]), "file tag"
        elif m and 60 <= int(m.group(1)) <= 200:
            bpm, src = float(m.group(1)), "from the title/description"
        elif analysis and analysis.bpm:
            bpm, src = analysis.bpm, "detected from the audio"
        elif best and not names:
            bpm, src = GENRE_RULES[best][0], "typical for %s; install ffmpeg to detect it from the audio" % best
        else:
            bpm, src = 125.0, "default; install ffmpeg to detect it from the audio"
        while bpm < 80:
            bpm *= 2
        while bpm > 170:
            bpm /= 2
        notes.append("bpm: %.0f (%s)" % (bpm, src))
    notes.append("energy: follows the song's loudness (slow and small when quiet, fast and big when loud)"
                 if analysis and analysis.energy else "energy: from the tempo only (ffmpeg not available)")
    if analysis and analysis.beats:
        notes.append("beats: %d tracked - moves land on the beat%s" % (
            len(analysis.beats), ", %d drops" % len(analysis.drops) if analysis.drops else ""))

    max_s = args.max_seconds
    if args.full:
        max_s = float(meta.get("duration") or 3600) + (5 if meta.get("duration") else 0)
    return styles, bpm, max_s, notes


def fmt_duration(sec):
    if not sec:
        return "--:--"
    sec = int(sec)
    return "%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60) if sec >= 3600 else "%d:%02d" % (sec // 60, sec % 60)


def youtube_search(query, n=10):
    """Search YouTube with yt-dlp (no API key needed). Returns [{id, title, uploader, duration, url}]."""
    ytdlp = find_ytdlp()
    if not ytdlp:
        raise RuntimeError("yt-dlp is not installed:  pip install --user --break-system-packages yt-dlp")
    target = query if re.match(r"https?://", query) else "ytsearch%d:%s" % (n, query)
    r = subprocess.run([*ytdlp, "-q", "--no-warnings", "--flat-playlist", "--dump-json", target],
                       capture_output=True, text=True, timeout=90)
    out = []
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        vid = d.get("id")
        if not vid:
            continue
        out.append({"id": vid, "title": d.get("title") or vid, "uploader": d.get("uploader") or d.get("channel") or "",
                    "duration": d.get("duration"), "url": "https://www.youtube.com/watch?v=" + vid})
    if not out and r.returncode != 0:
        raise RuntimeError((r.stderr.strip().splitlines() or ["search failed (no internet?)"])[-1])
    return out


def library(songs_dir):
    """Songs already on disk (downloads and your own files), newest first."""
    items = []
    for f in song_files(songs_dir):
        meta = {}
        side = os.path.splitext(f)[0] + ".json"
        if os.path.exists(side):
            try:
                meta = json.load(open(side, encoding="utf-8"))
            except (OSError, ValueError):
                pass
        items.append({"title": meta.get("title") or os.path.splitext(os.path.basename(f))[0].replace("_", " "),
                      "uploader": meta.get("uploader") or "", "duration": meta.get("duration"),
                      "kind": "file", "value": f, "mtime": os.path.getmtime(f)})
    return sorted(items, key=lambda i: -i["mtime"])
