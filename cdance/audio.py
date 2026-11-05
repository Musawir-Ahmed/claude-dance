# Author: Musawir Ahmed
"""Audio analysis: tempo, beat times, loudness over time, 'drops', and live band levels."""
import array, math, shutil, subprocess

RATE = 4000                      # analysis sample rate (Hz)
BAND_FREQS = (55, 110, 220, 400, 700, 1000, 1450, 1900)


class Analysis:
    """Everything we learned about a song. Any field may be None if it could not be computed."""

    def __init__(self, bpm=None, energy=None, beats=None, drops=None, samples=None):
        self.bpm, self.energy, self.beats, self.drops, self.samples = bpm, energy, beats or [], drops or [], samples
        self.band_peak = [1e-6] * len(BAND_FREQS)


def onset_envelope(samples, rate=RATE, fps=100):
    """Onset strength: positive change in short-time amplitude."""
    hop = max(1, rate // fps)
    env = [sum(map(abs, samples[i:i + hop])) / hop for i in range(0, len(samples) - hop, hop)]
    if len(env) < 4:
        return []
    onset = [max(0.0, env[i] - env[i - 1]) for i in range(1, len(env))]
    mean = sum(onset) / len(onset)
    return [v - mean for v in onset]


def bpm_from_samples(samples, rate=RATE, lo=80, hi=165):
    """Tempo from an onset-strength autocorrelation (pure Python, ~10 ms frames)."""
    onset = onset_envelope(samples, rate)
    if len(onset) < 400:
        return None
    fps = rate / max(1, rate // 100)
    scores = {}
    for lag in range(int(fps * 60 / 200), int(fps * 60 / 40) + 2):
        scores[lag] = sum(onset[i] * onset[i + lag] for i in range(len(onset) - lag)) / (len(onset) - lag)
    best, best_score = None, 0.0
    for lag in range(int(fps * 60 / hi), int(fps * 60 / lo) + 1):
        sc = scores.get(lag, 0) + 0.5 * scores.get(lag * 2, 0)      # reward the bar-level repeat too
        if sc > best_score:
            best, best_score = lag, sc
    if best is None:
        return None
    a, b, c = scores.get(best - 1, 0), scores[best], scores.get(best + 1, 0)   # parabolic refine
    denom = a - 2 * b + c
    off = 0.5 * (a - c) / denom if denom else 0
    return 60.0 * fps / (best + max(-1, min(1, off)))


def track_beats(samples, bpm, rate=RATE):
    """Beat times in seconds (dynamic-programming beat tracker, Ellis 2007). [] if it fails."""
    if not bpm:
        return []
    onset = onset_envelope(samples, rate)
    onset = [max(onset[i], onset[i + 1]) for i in range(0, len(onset) - 1, 2)]   # 100 fps -> 50 fps
    fps = 50.0
    if len(onset) < 200:
        return []
    sd = math.sqrt(sum(v * v for v in onset) / len(onset)) or 1.0
    onset = [v / sd for v in onset]
    period = fps * 60.0 / bpm
    lo, hi = max(1, int(period * 0.5)), int(period * 2)
    tight = 100.0
    pen = [0.0] + [tight * math.log(g / period) ** 2 for g in range(1, hi + 2)]
    n = len(onset)
    cum, back = [0.0] * n, [-1] * n
    for t in range(n):
        best, bp = 0.0, -1
        for p in range(max(0, t - hi), t - lo + 1):
            sc = cum[p] - pen[t - p]
            if sc > best:
                best, bp = sc, p
        cum[t], back[t] = onset[t] + best, bp
    tail = int(period)
    t = max(range(max(0, n - tail), n), key=lambda i: cum[i])
    beats = []
    while t >= 0:
        beats.append(t / fps)
        t = back[t]
    beats.reverse()
    return beats


def find_drops(curve, rise=0.28, within=3, cooldown=16):
    """Moments where the music suddenly gets much louder (energy curve is 0.5 s per point)."""
    drops, last = [], -1000
    for i in range(within, len(curve)):
        if curve[i] - min(curve[i - within:i]) >= rise and i - last >= cooldown and curve[i] > 0.5:
            drops.append(i * 0.5); last = i
    return drops


def analyze_audio(path, max_seconds=600):
    """Decode once with ffmpeg and learn tempo, beats, loudness curve and drops. None if impossible."""
    if not shutil.which("ffmpeg"):
        return None
    try:
        out = subprocess.run(["ffmpeg", "-v", "quiet", "-t", str(max_seconds), "-i", path,
                              "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                             capture_output=True, timeout=240).stdout
        samples = array.array("h")
        samples.frombytes(out[:len(out) // 2 * 2])
    except Exception:
        return None
    win = RATE // 2
    if len(samples) < RATE * 10:
        return None
    raw = [sum(map(abs, samples[i:i + win])) / win for i in range(0, len(samples) - win + 1, win)]
    ordered = sorted(raw)
    lo, hi = ordered[int(len(ordered) * 0.10)], ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    norm = [min(1.0, max(0.0, (v - lo) / (hi - lo + 1e-9))) for v in raw]
    curve = [sum(norm[max(0, i - 3):i + 4]) / len(norm[max(0, i - 3):i + 4]) for i in range(len(norm))]
    seg = samples[RATE * 5: RATE * 50] if len(samples) > RATE * 50 else samples
    bpm = bpm_from_samples(seg)
    an = Analysis(bpm, curve, track_beats(samples, bpm) if bpm else [], find_drops(norm), samples)
    for t in range(3, len(samples) // RATE, max(1, len(samples) // RATE // 40)):   # warm up the auto-gain
        band_levels(an, t)
    return an


def energy_at(curve, t, fallback):
    if not curve:
        return fallback
    x = max(0.0, t) / 0.5
    i = min(int(x), len(curve) - 1)
    j = min(i + 1, len(curve) - 1)
    return curve[i] + (curve[j] - curve[i]) * (x - int(x))


def band_levels(an, t, win=240):
    """Live 8-band spectrum (0..1) around time t via the Goertzel algorithm - cheap enough per frame."""
    if not an or an.samples is None:
        return None
    i = int(t * RATE)
    chunk = an.samples[max(0, i - win // 2): i + win // 2]
    if len(chunk) < win // 2:
        return [0.0] * len(BAND_FREQS)
    levels = []
    for k, f in enumerate(BAND_FREQS):
        coeff = 2 * math.cos(2 * math.pi * f / RATE)
        s1 = s2 = 0.0
        for x in chunk:
            s1, s2 = x + coeff * s1 - s2, s1
        power = math.sqrt(max(0.0, s1 * s1 + s2 * s2 - coeff * s1 * s2)) / len(chunk)
        an.band_peak[k] = max(an.band_peak[k] * 0.995, power)          # slowly decaying auto-gain
        levels.append(power)
    floor = 0.25 * max(an.band_peak)                                   # quiet bands can't be inflated to full height
    return [min(1.0, v / max(an.band_peak[k], floor, 1e-9)) for k, v in enumerate(levels)]


def beat_phase(beats, t):
    """(index of the last beat, fraction 0..1 of the way to the next one), or None."""
    from bisect import bisect_right
    if len(beats) < 2:
        return None
    i = bisect_right(beats, t) - 1
    if i < 0 or i >= len(beats) - 1:
        return None
    return i, (t - beats[i]) / (beats[i + 1] - beats[i])


def find_player(path):
    for name, args in (
        ("mpv", ["--no-video", "--really-quiet"]),
        ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
        ("cvlc", ["--play-and-exit", "--intf", "dummy"]),
        ("paplay", []),
        ("afplay", []),
    ):
        if shutil.which(name):
            return [name, *args, path]
    return None
