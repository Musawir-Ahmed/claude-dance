# Author: Musawir Ahmed
import argparse, array, bisect, glob, html, json, math, os, random, re, shutil, signal, subprocess, sys, textwrap, threading, time
import urllib.parse, urllib.request
from .common import *


LRCLIB_UA = "ClaudeDance/1.0 (terminal dance toy)"


def parse_lrc(text):
    out = []
    for line in text.splitlines():
        stamps = re.findall(r"\[(\d+):(\d+(?:\.\d+)?)\]", line)
        if stamps:
            txt = re.sub(r"\[[^\]]*\]", "", line).strip()
            out += [(int(m) * 60 + float(sec), txt) for m, sec in stamps]
    return sorted(out)


def parse_vtt(text, rolling=False):
    out, last = [], None
    for block in re.split(r"\n\s*\n", text.replace("\r", "")):
        m = re.search(r"(?:(\d+):)?(\d+):(\d+)[.,](\d+)\s+-->", block)
        if not m:
            continue
        t = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000
        body = [re.sub(r"<[^>]+>", "", l).strip() for l in block.splitlines()[1:] if "-->" not in l]
        body = [l for l in body if l]
        if not body:
            continue
        txt = body[-1] if rolling else " ".join(body)
        if txt != last:
            out.append((t, txt)); last = txt
    return out


def title_candidates(meta):
    cands = []
    if meta.get("artist") and meta.get("title"):
        cands.append("%s %s" % (meta["artist"], meta["title"]))
    for seg in str(meta.get("title") or "").split("|"):
        seg = re.sub(r"[\(\[][^\)\]]*[\)\]]", "", seg)
        seg = re.sub(r"\b(official|video|lyrics?|audio|clip|hd|4k|mv)\b", "", seg, flags=re.I)
        seg = re.sub(r"\s+", " ", seg.replace(" - ", " ")).strip(" -–—")
        if seg and not re.fullmatch(r"\d{4}", seg):
            cands.append(seg)
    return list(dict.fromkeys(cands))[:5]


def lrclib_lookup(meta):
    duration = meta.get("duration")
    best, best_diff = None, 1e9
    for q in title_candidates(meta):
        try:
            req = urllib.request.Request("https://lrclib.net/api/search?" + urllib.parse.urlencode({"q": q}),
                                         headers={"User-Agent": LRCLIB_UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                results = json.loads(r.read().decode())
        except Exception:
            continue
        qtok = set(re.findall(r"\w+", q.lower()))
        for item in results:
            if not item.get("syncedLyrics"):
                continue
            ttok = set(re.findall(r"\w+", str(item.get("trackName") or "").lower()))
            if not ttok or len(ttok & qtok) / len(ttok) < 0.6:          # must really be this song
                continue
            diff = abs((item.get("duration") or 0) - duration) if duration else 0
            if diff < best_diff:
                best, best_diff = item, diff
        if best and best_diff <= 8:
            break
    if best and best_diff <= 25:
        return parse_lrc(best["syncedLyrics"])
    return []


def youtube_captions(video_id):
    ytdlp = find_ytdlp()
    if not ytdlp:
        return []
    os.makedirs(CACHE_DIR, exist_ok=True)
    for auto in (False, True):                                   # real subtitles first, then auto-captions
        for old in glob.glob(os.path.join(CACHE_DIR, video_id + ".*.vtt")):
            os.remove(old)
        subprocess.run([*ytdlp, "-q", "--no-warnings", "--skip-download",
                        "--write-auto-subs" if auto else "--write-subs", "--sub-langs", "ar.*,ar,en.*,en",
                        "--sub-format", "vtt", "-o", os.path.join(CACHE_DIR, video_id + ".%(ext)s"),
                        "https://www.youtube.com/watch?v=" + video_id], capture_output=True, timeout=120)
        files = glob.glob(os.path.join(CACHE_DIR, video_id + ".*.vtt"))
        if files:
            lines = parse_vtt(open(files[0], encoding="utf-8").read(), rolling=auto)
            for f in files:
                os.remove(f)
            if len(lines) >= 4:
                return lines
    return []


def find_lyrics(path, meta):
    """Synced lyrics: a sidecar .lrc, else LRCLIB, else YouTube captions. Returns [(seconds, text)]."""
    lrc = os.path.splitext(path)[0] + ".lrc"
    if os.path.exists(lrc):
        return parse_lrc(open(lrc, encoding="utf-8").read())
    lines = lrclib_lookup(meta)
    if not lines and os.path.dirname(os.path.abspath(path)) == CACHE_DIR:
        lines = youtube_captions(os.path.splitext(os.path.basename(path))[0])
    if lines:
        try:
            with open(lrc, "w", encoding="utf-8") as f:
                f.write("\n".join("[%02d:%05.2f]%s" % (t // 60, t % 60, txt) for t, txt in lines))
        except OSError:
            pass
    return lines
