# Author: Musawir Ahmed
import argparse, array, bisect, glob, html, json, math, os, random, re, shutil, signal, subprocess, sys, textwrap, threading, time
import urllib.parse, urllib.request
from .common import *


W, H = 32, 26          # sprite size in pixels (a terminal cell = 1 wide x 2 pixels tall)
ORANGE = (217, 119, 87)


EYE = (35, 22, 22)


BLUSH = (255, 168, 150)


CREW_COLORS = [ORANGE, (96, 165, 250), (110, 200, 130), (236, 110, 160),
               (240, 200, 80), (170, 130, 230), (90, 210, 210), (240, 140, 60)]


PARTY = [
    (0, 0, 0, 0, 0, 0), (-1, -1, 2, 0, 1, 0), (0, 0, 1, 1, 0, 0),
    (1, -1, 0, 2, 0, 1), (0, -1, 2, 2, 0, 0), (-1, 0, 1, 0, 0, 1),
    (1, 0, 0, 1, 1, 0), (0, -1, 1, 1, 1, 1), (-1, -1, 2, 1, 0, 1),
    (1, -1, 1, 2, 1, 0),
]


SALSA = [
    (-1, 0, 2, 1, 0, 1, 0, 1), (0, 0, 1, 1, 0, 0), (1, 0, 1, 2, 1, 0, 0, 1), (0, 0, 1, 1, 0, 0),
    (-1, 0, 2, 1, 0, 1, 0, 1), (0, 0, 1, 1, 0, 0), (1, 0, 1, 2, 1, 0, 0, 1), (0, 0, 1, 1, 0, 0),
    (0, 0, 1, 1, 0, 0, 0, 0, 1), (0, 0, 2, 2, 0, 0, 0, 0, 1),   # spin turn
]


BREAK = [
    (-1, 0, 1, 1, 1, 0, 0, 1), (1, 0, 1, 1, 0, 1, 0, 1),        # top rock
    (-1, 0, 1, 1, 1, 0, 0, 2), (1, 0, 1, 1, 0, 1, 0, 2),
    (0, 0, 1, 0, 1, 0, 1, 0), (0, 0, 0, 1, 0, 1, 1, 0),         # freeze
    (0, 0, 0, 0, 0, 0, 1, 0, 1), (1, 0, 0, 0, 0, 0, 1, 0, 1),   # head spin
    (0, 0, 0, 0, 0, 0, 1, 0, 1), (-1, 0, 0, 0, 0, 0, 1, 0, 1),
    (-1, 0, 1, 1, 1, 0, 1, 0), (1, 0, 1, 1, 0, 1, 1, 0),        # windmill
    (-1, 0, 1, 1, 0, 1, 1, 0), (1, 0, 1, 1, 1, 0, 1, 0),
]


DISCO = [
    (-1, 0, 2, 0, 1, 0), (0, 0, 0, 0, 0, 0), (1, 0, 0, 2, 0, 1), (0, 0, 0, 0, 0, 0),
    (-1, 0, 2, 0, 1, 0), (0, 0, 0, 0, 0, 0), (1, 0, 0, 2, 0, 1), (0, -1, 2, 2, 0, 0),
]


ROBOT = [
    (0, 0, 1, 0, 0, 0), (0, 0, 2, 0, 0, 0), (0, 0, 2, 1, 0, 0),
    (0, 0, 1, 1, 0, 0), (0, 0, 0, 1, 0, 0), (0, 0, 0, 0, 0, 0),
]


FLOSS = [
    (1, 0, 2, 0, 0, 0, 0, 1), (-1, 0, 0, 2, 0, 0, 0, 1),
    (1, 0, 2, 0, 0, 0, 0, 1), (-1, 0, 0, 2, 0, 0, 0, 1),
    (0, 0, 1, 1, 0, 0, 0, 2), (0, -1, 2, 2, 0, 0),
]


MOONWALK = [
    (1.0, 0, 1, 0, 1, 0), (0.6, 0, 0, 1, 0, 1), (0.2, 0, 1, 0, 1, 0),
    (-0.2, 0, 0, 1, 0, 1), (-0.6, 0, 1, 0, 1, 0), (-1.0, 0, 0, 1, 0, 1),
    (0, -1, 2, 2, 0, 0), (0, 0, 1, 1, 0, 0),
]
WAVE = [
    (0, 0, 0, 0, 0, 0), (0, 0, 1, 0, 0, 0), (0, 0, 2, 1, 0, 0), (0, 0, 2, 2, 0, 0),
    (0, 0, 1, 2, 0, 0), (0, 0, 0, 1, 0, 0), (0, 0, 0, 0, 0, 0), (0, -1, 2, 2, 0, 0),
]
# name -> (moves, order, half-beats per move, snappy?)
STYLES = {
    "party": (PARTY, "random", 1, False),
    "salsa": (SALSA, "cycle", 1, False),
    "breakdance": (BREAK, "cycle", 1, False),
    "disco": (DISCO, "cycle", 1, False),
    "robot": (ROBOT, "cycle", 1, True),
    "floss": (FLOSS, "cycle", 1, False),
    "moonwalk": (MOONWALK, "cycle", 1, False),
    "wave": (WAVE, "cycle", 1, False),
}


FORMATIONS = ["roam", "circle", "line", "vee", "conga", "battle"]


ARM_ANGLE = {0: 22.0, 1: 92.0, 2: 165.0}


NUM_KEYS = ("dx", "dy", "la", "ra", "ll", "rl", "sq", "nar")


def make_pose(move, amp=1.0):
    """amp scales how big the move is: 0.45 = small and gentle ... 1.2 = full out."""
    dx, dy, la, ra, ll, rl, flip, sq, nar = tuple(move) + (0,) * (9 - len(move))
    arm = lambda a: ARM_ANGLE[0] + (ARM_ANGLE[a] - ARM_ANGLE[0]) * amp
    return {"dx": dx * 2.5 * amp, "dy": dy * 2.5 * amp, "la": arm(la), "ra": arm(ra),
            "ll": ll * 3.0 * amp, "rl": rl * 3.0 * amp, "sq": sq * 1.5 * amp, "nar": float(nar), "flip": flip}


def lerp(a, b, t):
    return a + (b - a) * t


def ease_back(t):                     # fast start, small overshoot, settle: reads as a "pop"
    t -= 1
    return 1 + 2.4 * t ** 3 + 1.4 * t ** 2


def blend(a, b, t):
    p = {k: lerp(a[k], b[k], t) for k in NUM_KEYS}
    p["flip"] = b["flip"] if t > 0.5 else a["flip"]
    return p


SHIRTS = [(66, 153, 225), (88, 196, 120), (235, 87, 120), (250, 204, 68), (155, 110, 235),
          (240, 240, 240), (60, 60, 70), (255, 140, 60), (40, 170, 170)]


COATS = [(95, 72, 60), (55, 65, 90), (150, 150, 160), (170, 55, 55), (38, 38, 46), (60, 90, 70)]


SUITS = [(40, 48, 78), (36, 36, 42), (70, 70, 80), (90, 60, 70)]


TIES = [(200, 50, 60), (60, 120, 220), (250, 200, 60), (80, 190, 120)]


HAIR_COLORS = [(38, 30, 30), (110, 70, 40), (240, 200, 90), (190, 60, 40), (255, 120, 190),
               (80, 140, 255), (160, 100, 230), (70, 200, 130), (225, 225, 232), "rainbow"]


RAINBOW = [(235, 70, 70), (250, 150, 50), (250, 220, 70), (90, 200, 110), (80, 150, 250), (160, 100, 230)]


HEADS = ["afro", "mohawk", "bob", "long", "pompadour", "pigtails", "spikes",
         "tophat", "cap", "beanie", "partyhat", "crown", None]


def dim(c, f):
    return tuple(int(v * f) for v in c)


def random_outfit():
    top = random.choice(["tee", "tee", "hoodie", "sweater", "coat", "suit", None])
    fit = {"top": top, "tc": random.choice(SHIRTS), "tc2": (240, 240, 240),
           "tie": random.choice(TIES), "shoes": random.choice([(240, 240, 240), (40, 36, 36), (200, 60, 60)]),
           "head": random.choice(HEADS), "hc": random.choice(HAIR_COLORS), "hc2": random.choice(SHIRTS)}
    if top == "sweater":
        fit["tc2"] = random.choice([c for c in SHIRTS if c != fit["tc"]])
    if top == "coat":
        fit["tc"], fit["tc2"] = random.choice(COATS), random.choice([(240, 240, 240), (200, 60, 60), (70, 120, 200)])
    if top == "suit":
        fit["tc"] = random.choice(SUITS)
        fit["pants"], fit["pc"] = "long", dim(fit["tc"], 0.9)
    else:
        kind = random.choice(["jeans", "jeans", "shorts", "khaki", "black", None])
        fit["pants"] = kind if (kind or top) else None
        fit["pc"] = {"jeans": (62, 98, 170), "shorts": random.choice([(62, 98, 170), (200, 180, 120), (90, 90, 100)]),
                     "khaki": (196, 170, 110), "black": (44, 44, 52)}.get(kind)
    return fit


def sprite(p, color, face=0, blink=False, happy=False, fit=None):
    """Draw the mascot (plus outfit, hair or hat) from a pose into a W x H pixel grid."""
    shade = tuple(int(c * 0.80) for c in color)
    g = [[None] * W for _ in range(H)]

    def rect(x0, y0, x1, y1, c):
        for y in range(int(round(y0)), int(round(y1)) + 1):
            if 0 <= y < H:
                for x in range(int(round(x0)), int(round(x1)) + 1):
                    if 0 <= x < W:
                        g[y][x] = c(x) if callable(c) else c

    def dot(x, y, c):
        rect(x, y, x, y, c)

    nar = min(1.0, max(0.0, p["nar"]))
    sc = 1 - 0.55 * nar
    cx = W / 2 + p["dx"]
    bw = 16 * sc
    left, right = cx - bw / 2, cx + bw / 2 - 1
    sq, oy = max(0.0, p["sq"]), p["dy"]
    top, bot = 7 + sq + oy, 17 + sq + oy
    ground = 21 + oy
    f = fit or {}
    top_kind, pants = f.get("top"), f.get("pants")

    def sym(y, half, c):                                # horizontal span centred on the body
        rect(cx - half, top + y, cx + half - 1, top + y, c)

    # --- legs (with trousers / shorts and shoes)
    for i, off in enumerate((-6, -3, 2, 5)):
        lift = max(0.0, p["ll"] if i < 2 else p["rl"])
        lx = cx + off * sc
        y1 = max(bot + 1, ground - lift)
        rect(lx, bot + 1, lx + 1, y1, shade)
        if pants:
            long_legs = pants != "shorts"
            rect(lx, bot + 1, lx + 1, y1 if long_legs else min(y1, bot + 2), f["pc"])
        if fit:
            rect(lx, y1, lx + 1, y1, f["shoes"])

    # --- body
    rect(left, top, right, bot - 1, color)
    rect(left, bot, right, bot, shade)
    if not fit:
        for (x, y) in ((left, top), (right, top), (left, bot), (right, bot)):
            dot(x, y, None)
    else:
        for (x, y) in ((left, top), (right, top)):
            dot(x, y, None)

    # --- clothes
    sleeve, sleeve_len = None, 0
    if top_kind:
        tc, tc2 = f["tc"], f["tc2"]
        r0 = top + 7
        if top_kind in ("tee", "hoodie"):
            rect(left, r0, right, bot - 1, tc); sleeve, sleeve_len = tc, 1 if top_kind == "tee" else 3
            if top_kind == "hoodie":
                rect(cx - 3, bot - 3, cx + 2, bot - 1, dim(tc, 0.82))
                for dy_ in (0, 1):
                    dot(cx - 2, r0 + dy_, (245, 245, 245)); dot(cx + 1, r0 + dy_, (245, 245, 245))
        elif top_kind == "sweater":
            for y in range(int(round(r0)), int(round(bot))):
                rect(left, y, right, y, tc if (y % 2) else tc2)
            sleeve, sleeve_len = tc, 3
        elif top_kind == "coat":
            rect(left, r0, right, bot + 2, tc)
            rect(cx - 1, r0 + 1, cx, bot + 2, tc2)                          # open front, lining
            rect(left, top + 10, right, top + 10, dim(tc, 0.7))             # belt
            dot(cx - 2, r0, dim(tc, 0.7)); dot(cx + 1, r0, dim(tc, 0.7))
            sleeve, sleeve_len = tc, 4
        elif top_kind == "suit":
            rect(left, r0, right, bot, tc)
            rect(cx - 1, r0, cx, bot - 3, (245, 245, 245))                  # shirt
            rect(cx - 1, r0 + 1, cx, bot - 3, f["tie"])                     # tie
            dot(cx - 2, r0, dim(tc, 0.7)); dot(cx + 1, r0, dim(tc, 0.7))
            dot(right - 2, r0 + 2, (245, 245, 245))                         # pocket square
            sleeve, sleeve_len = tc, 3
    if pants and top_kind not in ("coat", "suit"):
        rect(left, bot, right, bot, f["pc"])

    # --- hair / wigs / hats (before the eyes so bangs never cover them)
    head, hc = f.get("head"), f.get("hc")
    if hc == "rainbow":
        hc = lambda x: RAINBOW[(int(x) // 2) % len(RAINBOW)]
    if head and nar < 0.8:
        if head == "afro":
            for y, half in ((-5, 3), (-4, 5), (-3, 6), (-2, 7), (-1, 8), (0, 9)):
                sym(y, half, hc)
            for y in (1, 2, 3):
                rect(cx - 9, top + y, cx - 8, top + y, hc); rect(cx + 8, top + y, cx + 9, top + y, hc)
        elif head == "mohawk":
            rect(cx - 1, top - 5, cx, top - 1, hc)
            for dx_, h in ((-3, 3), (2, 3), (-5, 1), (4, 1)):
                rect(cx + dx_, top - h, cx + dx_, top - 1, hc)
        elif head in ("bob", "long", "pigtails"):
            sym(-2, 7, hc); sym(-1, 8, hc); sym(0, 9, hc)
            rect(left + 1, top, right - 1, top + 1, hc)                      # fringe
            if head == "bob":
                rect(cx - 9, top, cx - 8, top + 7, hc); rect(cx + 7, top, cx + 8, top + 7, hc)
            elif head == "long":
                rect(cx - 10, top, cx - 8, top + 10, hc); rect(cx + 7, top, cx + 9, top + 10, hc)
            else:
                rect(cx - 12, top + 1, cx - 11, top + 6, hc); rect(cx + 10, top + 1, cx + 11, top + 6, hc)
                rect(cx - 10, top, cx - 8, top + 1, f["hc2"]); rect(cx + 7, top, cx + 9, top + 1, f["hc2"])
        elif head == "pompadour":
            sym(-1, 8, hc); rect(cx - 6, top - 3, cx + 6, top - 2, hc); rect(cx - 4, top - 5, cx + 3, top - 4, hc)
            rect(left + 1, top, right - 1, top, hc)
        elif head == "spikes":
            sym(-1, 8, hc)
            for dx_ in range(-7, 8, 3):
                rect(cx + dx_, top - 3, cx + dx_ + 1, top - 2, hc); dot(cx + dx_, top - 4, hc)
        elif head == "tophat":
            rect(cx - 4, top - 8, cx + 3, top - 2, (36, 34, 40)); rect(cx - 4, top - 3, cx + 3, top - 3, f["hc2"])
            sym(-1, 8, (36, 34, 40))
        elif head == "cap":
            sym(-3, 5, f["hc2"]); sym(-2, 7, f["hc2"]); sym(-1, 8, f["hc2"])
            rect(cx + 2, top, cx + 10, top, dim(f["hc2"], 0.7)); dot(cx, top - 4, dim(f["hc2"], 0.7))
        elif head == "beanie":
            rect(cx - 1, top - 6, cx, top - 5, (245, 245, 245))
            sym(-4, 3, f["hc2"]); sym(-3, 6, f["hc2"]); sym(-2, 7, (245, 245, 245)); sym(-1, 8, f["hc2"])
        elif head == "partyhat":
            for y, half in ((-8, 1), (-7, 1), (-6, 2), (-5, 2), (-4, 3), (-3, 3), (-2, 4), (-1, 4)):
                sym(y, half, f["hc2"])
            for dx_, y in ((-1, -5), (1, -3), (-2, -2), (0, -7)):
                dot(cx + dx_, top + y, (250, 230, 90))
            dot(cx - 1, top - 9, (250, 230, 90)); dot(cx, top - 9, (250, 230, 90))
        elif head == "crown":
            rect(cx - 5, top - 3, cx + 4, top - 1, (250, 205, 60))
            for dx_ in (-5, -1, 0, 4):
                dot(cx + dx_, top - 4, (250, 205, 60))
            dot(cx - 1, top - 2, (220, 60, 80)); dot(cx, top - 2, (220, 60, 80))

    # --- face
    if nar < 0.7:
        for ex in (-5, 3):
            x = cx + ex * sc + face
            if happy:                                                  # ^ ^
                dot(x - 1, top + 4, EYE); dot(x, top + 3, EYE); dot(x + 1, top + 3, EYE); dot(x + 2, top + 4, EYE)
            elif blink:
                rect(x, top + 4, x + 1, top + 4, EYE)
            else:
                rect(x, top + 2, x + 1, top + 5, EYE)
                dot(x, top + 2, (255, 255, 255))                       # sparkle
        rect(cx - 7.5, top + 6, cx - 6.5, top + 6, BLUSH)              # rosy cheeks
        rect(cx + 6, top + 6, cx + 7, top + 6, BLUSH)
        if happy and fit:                                              # small smile that clears the clothes
            rect(cx - 1, top + 6, cx, top + 6, EYE)
        elif happy:
            dot(cx - 2, top + 6, EYE); rect(cx - 1, top + 7, cx, top + 7, EYE); dot(cx + 1, top + 6, EYE)

    # --- arms (sleeves if they are wearing one)
    if nar < 0.6:
        sy = top + 6
        for side, ang in ((-1, p["la"]), (1, p["ra"])):
            a = math.radians(min(180.0, max(0.0, ang)))
            for k in range(0, 5):
                ax = (left - 2 - math.sin(a) * k) if side < 0 else (right + 1 + math.sin(a) * k)
                ay = sy + math.cos(a) * k
                rect(ax, ay, ax + 1, ay + 1, sleeve if (sleeve and k < sleeve_len) else color)

    if p["flip"]:
        g.reverse()
    return g


def shrink(g):
    """Half-size sprite for small terminals (keeps eyes and thin limbs visible)."""
    h, w = len(g) // 2, len(g[0]) // 2
    out = [[None] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            block = [g[2 * y][2 * x], g[2 * y][2 * x + 1], g[2 * y + 1][2 * x], g[2 * y + 1][2 * x + 1]]
            if EYE in block:
                out[y][x] = EYE
                continue
            solid = [c for c in block if c is not None]
            if len(solid) >= 2:
                out[y][x] = max(set(solid), key=solid.count)
    return out
