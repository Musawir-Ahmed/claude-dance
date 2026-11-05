# Author: Musawir Ahmed
import argparse, array, bisect, glob, html, json, math, os, random, re, shutil, signal, subprocess, sys, textwrap, threading, time
import urllib.parse, urllib.request
from .common import *
from .sprites import *


SHADOW = (72, 72, 80)


BUBBLE_BG = (28, 26, 46)


BUBBLE_FG = (240, 236, 228)


BUBBLE_EDGE = (130, 120, 175)
PIT = (16, 14, 26)            # the strip under the stage that holds the text box
LIT, UNLIT = (255, 175, 95), (135, 130, 152)


STAGE = (13, 13, 28)


WARM = (255, 236, 190)


BEAMS = [((255, 60, 170), 0.12, 0.0), ((60, 200, 255), 0.88, 2.4)]


LIGHT_STAGE = (214, 218, 236)
THEMES = ["dark", "light"]
_BACKDROPS = {}


def stage_base(theme):
    return LIGHT_STAGE if theme == "light" else STAGE


def _mix(a, b, f):
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


def backdrop(aw, ah, theme):
    """Back wall with a horizon, a tiled floor and side curtains (cached per size and theme)."""
    key = (aw, ah, theme)
    if key in _BACKDROPS:
        return _BACKDROPS[key]
    if len(_BACKDROPS) > 6:
        _BACKDROPS.clear()
    light = theme == "light"
    top, hor, f0, f1, curtain = (((200, 206, 228), (226, 220, 228), (190, 178, 192), (160, 148, 168), (196, 104, 132)) if light else
                                 ((8, 8, 20), (26, 20, 46), (32, 24, 50), (56, 42, 76), (84, 18, 48)))
    hy, cw = int(ah * 0.62), max(4, min(10, aw // 16))
    rows = []
    for y in range(ah):
        if y < hy:
            c = _mix(top, hor, y / max(1, hy))
        else:
            c = _mix(f0, f1, (y - hy) / max(1, ah - hy))
            if y == hy or (y - hy) % 6 == 0:                       # floor tile lines
                c = _mix(c, (255, 255, 255) if not light else (90, 70, 100), 0.10)
        row = [c] * aw
        for x in range(min(cw, aw // 2)):                          # curtains with folds
            fold = 0.72 + 0.28 * math.sin(x * 1.7)
            row[x] = tuple(int(v * fold) for v in curtain)
            row[aw - 1 - x] = tuple(int(v * (0.72 + 0.28 * math.sin((x + 1) * 1.7))) for v in curtain)
        rows.append(row)
    _BACKDROPS[key] = rows
    return rows


LIGHT_MODES = ["auto", "low", "high", "strobe", "pulse", "disco", "off"]
BEAMS.extend([((255, 200, 60), 0.35, 4.1), ((120, 255, 140), 0.65, 5.5)])


def _hue(t, a=1.0):
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(t % 1.0, 0.8, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255)), a


def lighting(mode, inten, pulse, t, beat=0, theme="dark"):
    """Light settings for one frame.
    master = overall brightness, beams = how many colour beams, speed = sweep speed, spot = follow-spot
    strength, wash = (colour, alpha) tint over the whole stage, sparkle = number of mirror-ball glints."""
    if mode == "auto":                         # follows the music: dim and slow when quiet, bright and busy when loud
        return {"master": 0.40 + 0.85 * inten, "beams": 1 + int(inten * 3.5), "speed": 0.5 + 1.5 * inten,
                "spot": 0.8 + 0.4 * inten, "wash": None, "sparkle": int(max(0.0, inten - 0.6) * 45)}
    table = {
        "low": {"master": 0.40, "beams": 1, "speed": 0.45, "spot": 0.8, "wash": ((255, 150, 80), 0.05), "sparkle": 0},
        "high": {"master": 1.30, "beams": 4, "speed": 1.9, "spot": 1.25, "wash": None, "sparkle": 8},
        "strobe": {"master": 1.0, "beams": 2, "speed": 2.2, "spot": 1.0,
                   "wash": ((255, 255, 255), 0.45)
                   if (beat % 2 == 0 and pulse > 0.35) else None, "sparkle": 0},
        "pulse": {"master": 0.9, "beams": 2, "speed": 1.0, "spot": 1.0,
                  "wash": _hue(t * 0.05, 0.08 + 0.28 * pulse), "sparkle": 0},
        "disco": {"master": 1.0, "beams": 4, "speed": 1.5, "spot": 0.9, "wash": _hue(t * 0.1, 0.06), "sparkle": 26},
        "off": {"master": 0.0, "beams": 0, "speed": 1.0, "spot": 0.0, "wash": None, "sparkle": 0},
    }
    return table.get(mode, table["low"])


def build_stage(aw, ah, t, lead, others, flash=0.0, foot=21, k=1.0, light=None, theme="dark"):
    """The stage: backdrop + follow spot + colour beams from lamps at the top, shaped by `light`."""
    L = light or lighting("auto", 0.5, 0.0, t)
    bg = [row[:] for row in backdrop(aw, ah, theme)]
    gain = 0.62 if theme == "light" else 1.0                  # bright stages clip sooner
    if L["wash"]:
        col, wa = L["wash"]
        memo = {}
        for y in range(ah):
            row = bg[y]
            for x in range(aw):
                c = row[x]
                if c not in memo:
                    memo[c] = tuple(min(255, int(c[i] + col[i] * wa)) for i in range(3))
                row[x] = memo[c]
    master = L["master"] * gain

    def add(x, y, col, a):
        a *= master
        if a < 0.08 or not (0 <= x < aw and 0 <= y < ah):
            return
        a = round(a * 6) / 6                       # few light levels -> long colour runs
        r, g_, b = bg[y][x]
        bg[y][x] = (min(255, int(r + col[0] * a)), min(255, int(g_ + col[1] * a)), min(255, int(b + col[2] * a)))

    def cone(ax, tx, ty, hw0, hw1, col, peak):
        ty = max(1, min(ty, ah - 1))
        for y in range(ty + 1):
            f = y / ty
            xc, hw = ax + (tx - ax) * f, hw0 + (hw1 - hw0) * f
            for x in range(int(xc - hw), int(xc + hw) + 1):
                add(x, y, col, peak * max(0.0, 1 - abs(x - xc) / hw) ** 0.8 * (1 - 0.35 * f))

    def pool(cx, cy, rx, ry, col, peak):
        for y in range(int(cy - ry), int(cy + ry) + 1):
            for x in range(int(cx - rx), int(cx + rx) + 1):
                d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
                if d < 1:
                    add(x, y, col, peak * (1 - d))

    if L["master"] <= 0:
        return bg
    floor_y = max(1, min(ah - 3, int(ah * 0.62) + (ah - int(ah * 0.62)) // 2))
    for col, fx, ph in BEAMS[:L["beams"]]:         # colour beams sweeping the floor
        tx = aw * (0.5 + 0.38 * math.sin(t * 0.8 * L["speed"] + ph))
        cone(aw * fx, tx, floor_y, 1, 11 * k + 1, col, 0.34 + 0.25 * flash)
        pool(tx, floor_y, 14 * k + 1, 3, col, 0.42 + 0.2 * flash)
        lx_ = int(aw * fx)                         # the lamp fixture the beam comes from
        for y_ in (0, 1):
            for x_ in range(lx_ - 2, lx_ + 3):
                if 0 <= x_ < aw:
                    bg[y_][x_] = (44, 44, 54)
        for x_ in range(lx_ - 1, lx_ + 2):
            if 0 <= x_ < aw:
                bg[1][x_] = tuple(min(255, int(v * 0.5 + 130)) for v in col)
    for d in others:                               # soft pools for the rest of the crew
        pool(d["x"] + W * k / 2, d["y"] + foot, 15 * k + 1, 3, d["color"], 0.34 + 0.2 * flash)
    lx, ly = lead["x"] + W * k / 2, lead["y"] + foot     # the follow spot
    cone(lx + 10 * math.sin(t * 1.2), lx, int(ly), 2, 16 * k + 1, WARM, (0.5 + 0.3 * flash) * L["spot"])
    pool(lx, ly, 20 * k + 1, 4, WARM, (0.62 + 0.3 * flash) * L["spot"])
    for i in range(L["sparkle"]):                  # mirror-ball glints drifting over the stage
        x = int(aw * (0.5 + 0.47 * math.sin(t * (0.4 + 0.13 * i) + i * 2.1)))
        y = int(ah * (0.5 + 0.45 * math.sin(t * (0.3 + 0.07 * i) + i * 1.7)))
        col = CONFETTI[i % len(CONFETTI)]
        add(x, y, col, 1.1)
        add(x + 1, y, col, 0.7)
    return bg


def to_cells(canvas, cols, rows):
    cells = []
    for r in range(rows):
        top, bot = canvas[2 * r], canvas[2 * r + 1]
        row = []
        for x in range(cols):
            t, b = top[x], bot[x]
            if t is None and b is None:
                row.append((" ", None, None))
            elif b is None:
                row.append(("▀", t, None))
            elif t is None:
                row.append(("▄", b, None))
            elif t == b:
                row.append((" ", None, t))
            else:
                row.append(("▀", t, b))
        cells.append(row)
    return cells


def serialize(cells):
    lines = []
    for row in cells:
        parts, prev = [], (None, None)
        for ch, fg, bg in row:
            if ch == " " and bg is None:
                fg = None
            if (fg, bg) != prev:
                parts.append("\x1b[0m")
                if fg:
                    parts.append("\x1b[38;2;%d;%d;%dm" % fg)
                if bg:
                    parts.append("\x1b[48;2;%d;%d;%dm" % bg)
                prev = (fg, bg)
            parts.append(ch)
        parts.append("\x1b[0m")
        lines.append("".join(parts))
    return lines


def draw_lyrics(rows_cells, cur, nxt, c1=LIT, c2=(150, 145, 168), pad="♪ ", full=0, progress=None):
    """The one text box, under the stage: lyrics (current + dim next line) or Claude's reply.
    `full` reserves width so the box doesn't jump while text types out. `progress` (0..1) lights up
    the words of the current line one by one, karaoke style (timing is spread evenly over the line)."""
    cols = len(rows_cells[0])
    maxw = max(10, min(cols - 8, 60))
    clip = lambda t: t if len(t) <= maxw else t[:maxw - 1] + "…"
    cur, nxt = clip(cur or "♪ ♪ ♪"), clip(nxt)
    inner = max(len(cur) + len(pad), len(nxt), 24, full)
    bw = inner + 4
    left = max(0, (cols - bw) // 2)

    def put(r, c, ch, fg):
        if 0 <= c < cols:
            rows_cells[r][c] = (ch, fg, BUBBLE_BG)

    for r in range(4):
        for c in range(bw):
            put(r, left + c, " ", BUBBLE_FG)
    for c in range(bw):
        put(0, left + c, "─", BUBBLE_EDGE); put(3, left + c, "─", BUBBLE_EDGE)
    for r in (1, 2):
        put(r, left, "│", BUBBLE_EDGE); put(r, left + bw - 1, "│", BUBBLE_EDGE)
    put(0, left, "╭", BUBBLE_EDGE); put(0, left + bw - 1, "╮", BUBBLE_EDGE)
    put(3, left, "╰", BUBBLE_EDGE); put(3, left + bw - 1, "╯", BUBBLE_EDGE)

    for r, text, fg in ((1, pad + cur, c1), (2, nxt, c2)):
        start_c = left + 2 + (max(0, (inner - len(text)) // 2) if pad else 0)
        words_total = max(1, len(cur.split()))
        rtl = any("\u0590" <= ch <= "\u08ff" or "\ufb50" <= ch <= "\ufeff" for ch in text)
        # right-to-left scripts keep one colour: splitting the line into colour runs scrambles the word order
        sung = math.ceil(progress * words_total) if (progress is not None and r == 1 and not rtl) else None
        word = -1
        prev_space = True
        for j, ch in enumerate(text):
            color = fg
            if sung is not None:
                if j >= len(pad):
                    if ch != " " and prev_space:
                        word += 1
                    prev_space = ch == " "
                    color = LIT if word < sung else UNLIT
                else:
                    color = LIT
            put(r, start_c + j, ch, color)


def formation_slots(kind, n, aw, ah, t, sw=W, sh=H):
    """Target top-left positions for each dancer in a formation (sw x sh = sprite size)."""
    cx, cy = (aw - sw) / 2, (ah - sh) / 2
    if kind == "line":
        gap = min(sw + 2, (aw - sw) / max(1, n - 1)) if n > 1 else 0
        return [(cx - gap * (n - 1) / 2 + i * gap, cy) for i in range(n)]
    if kind == "circle":
        rx = min(cx, 10 + 4 * n)
        ry = min(cy, rx * 0.55)
        return [(cx + rx * math.cos(t * 0.8 + 6.2832 * i / n),
                 cy + ry * math.sin(t * 0.8 + 6.2832 * i / n)) for i in range(n)]
    if kind == "battle":                                   # two crews face to face
        out = []
        for i in range(n):
            team, k = i % 2, i // 2
            out.append((aw * (0.12 if team == 0 else 0.88) - sw / 2 + (sw * 0.25 if team == 0 else -sw * 0.25),
                        cy + (k - (n // 4)) * sh * 0.55))
        return out
    out = []                                               # vee
    for i in range(n):
        k = (i + 1) // 2
        side = 0 if i == 0 else (-1 if i % 2 else 1)
        out.append((cx + side * k * sw * 0.8, cy + sh * 0.6 - k * sh * 0.55))
    return out


# ----------------------------------------------------------------- confetti and equalizer
CONFETTI = [(255, 90, 120), (255, 200, 60), (90, 200, 255), (120, 230, 140), (190, 130, 255), (255, 255, 255)]
CONFETTI_LIGHT = [(235, 50, 90), (240, 160, 20), (30, 140, 230), (40, 170, 90), (140, 70, 230), (50, 50, 100)]


class Confetti:
    def __init__(self, theme="dark"):
        self.p, self.theme = [], theme

    def burst(self, aw, n=70, y=0.0):
        for _ in range(n):
            self.p.append([random.uniform(0, aw), y + random.uniform(-2, 2), random.uniform(-8, 8),
                           random.uniform(4, 22), random.choice(CONFETTI_LIGHT if self.theme == "light" else CONFETTI), random.uniform(2.5, 5.0)])

    def update(self, dt, ah):
        for q in self.p:
            q[0] += q[2] * dt; q[1] += q[3] * dt
            q[2] += random.uniform(-14, 14) * dt            # flutter
            q[3] = min(q[3] + 18 * dt, 26)
            q[5] -= dt
        self.p = [q for q in self.p if q[5] > 0 and q[1] < ah]

    def draw(self, canvas, aw, ah):
        for x, y, _, _, c, _ in self.p:
            xi, yi = int(x), int(y)
            if 0 <= xi < aw and 0 <= yi < ah:
                canvas[yi][xi] = c
                if 0 <= xi + 1 < aw and (xi + yi) % 2 == 0:
                    canvas[yi][xi + 1] = c


def draw_equalizer(canvas, aw, ah, levels, state, theme="dark", base=None):
    """Translucent spectrum bars along the floor, behind the dancers. `state` keeps the falloff."""
    if not levels:
        return
    bars = max(8, min(aw // 3, 48))
    if len(state) != bars:
        state[:] = [0.0] * bars
    maxh = max(4, min(14, ah // 4))
    for b in range(bars):
        pos = b / (bars - 1) * (len(levels) - 1)
        i = int(pos)
        lv = levels[i] + (levels[min(i + 1, len(levels) - 1)] - levels[i]) * (pos - i)
        state[b] = max(lv, state[b] * 0.86)
        h = int(state[b] ** 0.8 * maxh)
        f = b / (bars - 1)
        col = (int(255 * (1 - f) + 60 * f), int(60 * (1 - f) + 200 * f), int(170 * (1 - f) + 255 * f))
        x0 = int(b * aw / bars)
        floor = ah if base is None else base
        for y in range(max(0, floor - h), min(ah, floor)):
            for x in (x0, x0 + 1):
                if 0 <= x < aw:
                    bg = canvas[y][x] or (0, 0, 0)
                    canvas[y][x] = tuple(int(bg[k] * (0.3 if theme == "light" else 0.5) + col[k] * (0.7 if theme == "light" else 0.5)) for k in range(3))



# ----------------------------------------------------------------- layout, title chips, audience
def layout(rows):
    """-> (audience text rows, first row of the text box, dancer area top px, dancer area bottom px).
    The stage background covers every row; the text box and title float over it."""
    aud = 5 if rows >= 32 else 4 if rows >= 24 else 3 if rows >= 18 else 0
    box_top = rows - aud - 5
    if box_top < 6:
        aud, box_top = 0, max(4, rows - 5)
    return aud, box_top, 2, 2 * box_top


def overlay_chip(cells, row, col, text, fg, bg=(18, 16, 32)):
    """Write text over the stage on a small solid chip (one colour run, so right-to-left text stays intact)."""
    if not 0 <= row < len(cells) or not text:
        return
    width = len(cells[row])
    for i, ch in enumerate(" " + text + " "):
        c = col + i
        if 0 <= c < width:
            cells[row][c] = (ch, fg, bg)


def make_audience(aw, seed=7):
    """Two rows of people along the bottom, drawn as plain black / grey silhouettes."""
    rnd = random.Random(seed * 1000 + aw)
    people = []
    for row, gap, off in ((0, 8, 4), (1, 10, 1)):                   # 0 = back row, 1 = front row
        x = off + rnd.randint(0, 3)
        while x < aw - 1:
            people.append({"x": x, "row": row, "phase": rnd.uniform(0, 6.28), "thr": rnd.random(),
                           "fan": rnd.random() < 0.13, "color": rnd.choice(CREW_COLORS),
                           "stick": rnd.choice(CONFETTI)})
            x += gap + rnd.randint(-1, 2)
    return people


def draw_audience(canvas, aw, ah, band, t, inten, pulse, flash, theme, people):
    """The crowd (`band` pixel rows tall) sways, bobs on the beat, and raises glow sticks / phone lights."""
    light = theme == "light"
    body = {1: (38, 38, 38) if light else (6, 6, 6), 0: (92, 92, 92) if light else (26, 26, 26)}   # black / grey people
    rim = (150, 150, 150) if light else (78, 78, 78)
    raise_p = min(1.0, 0.10 + inten * 0.8 + flash * 0.6)
    phones = inten < 0.45 and flash < 0.3

    def rect(x0, y0, x1, y1, c):
        for y in range(y0, y1 + 1):
            if 0 <= y < ah:
                for x in range(x0, x1 + 1):
                    if 0 <= x < aw:
                        canvas[y][x] = c

    bob = -1 if pulse > 0.5 else 0
    for p in people:
        front = p["row"] == 1
        x = p["x"] + int(round(math.sin(t * 2.2 + p["phase"])))
        col = body[p["row"]]
        head_top = ah - band + (1 if front else 0) + bob
        hs = 5 if front else 4                                       # head size
        sh_top = head_top + hs
        if p["thr"] < raise_p and band >= 6:                        # arms up (drawn behind the head)
            wave = math.sin(t * 3.0 + p["phase"]) > 0
            for side in (-1, 1):
                if inten < 0.6 and (side == 1) == wave:
                    continue
                ax = x + side * (hs // 2 + 2)
                top = sh_top - (8 if front else 6)
                rect(ax, top, ax + 1, sh_top, col)
                if phones:                                           # phone light: pale screen with a dim halo
                    rect(ax, top - 3, ax + 1, top - 1, (225, 225, 225))
                    rect(ax - 1, top - 4, ax + 2, top - 4, (95, 95, 95))
                else:                                                # light stick: plain white
                    rect(ax, top - 3, ax, top - 1, (235, 235, 235))
        rect(x - hs // 2, head_top, x + (hs - 1) // 2, head_top + hs - 1, col)          # head
        rect(x - 1, head_top, x + 1, head_top, rim)                                      # rim light on the head
        rect(x - (hs + 1) // 2 - 1, sh_top, x + (hs + 1) // 2 + 1, ah - 1, col)       # shoulders
