# Author: Musawir Ahmed
"""The dance floor: runs one song from start to finish and returns 'done', 'next' or 'quit'."""
import bisect, math, os, random, select, shutil, signal, subprocess, sys, textwrap, threading, time

from .common import *
from .sprites import *
from .stage import *
from .audio import *

try:                                   # keyboard controls need a real terminal on Unix
    import termios, tty
except ImportError:                    # pragma: no cover (Windows)
    termios = tty = None

HINT = "[space] pause  [n] next  [s] style  [f] formation  [o] outfits  [l] lights  [t] theme  [v] eq  [q] quit"


def next_grid_time(beats, t, per_beat, fallback):
    """Next point after time t on the beat grid, subdividing each beat `per_beat` times (0.5 = every 2nd)."""
    if len(beats) < 2:
        return t + fallback
    mean_iv = (beats[-1] - beats[0]) / (len(beats) - 1)
    i = bisect.bisect_right(beats, t) - 1
    if i < 0:
        return beats[0]
    if i >= len(beats) - 1:                                   # past the tracked beats: extrapolate
        return t + mean_iv / max(per_beat, 0.5)
    iv = beats[i + 1] - beats[i]
    if per_beat < 1:
        k, every = i + 1, max(1, round(1 / per_beat))
        while k % every:
            k += 1
        out = beats[k] if k < len(beats) else beats[-1] + (k - len(beats) + 1) * mean_iv
    else:
        out = beats[i] + (int((t - beats[i]) / iv * per_beat) + 1) * iv / per_beat
    return out if out > t + 0.03 else out + iv / max(per_beat, 0.5)


def snap_per_beat(x):
    return min((0.5, 1, 2, 4), key=lambda c: abs(math.log(max(x, 0.01) / c)))


def dance(song, bpm, max_seconds, prompt, styles, *, mix=False, crew=1, formation="auto", speed=1.0,
          spot=True, title=None, audio_note=None, analysis=None, lyrics=None, lyr_offset=0.0,
          outfits=True, reply=None, viz=True, sync=0.12, keys=True, forever=False, lights="auto", theme="dark", quit_text="quit", print_reply=True):
    crew = max(1, min(crew, 12))
    name = title or (os.path.splitext(os.path.basename(song))[0] if song else "(silent)")
    clock = {"paused_total": 0.0, "paused_at": None}

    def tnow():                                           # time that stands still while paused
        return (clock["paused_at"] or time.time()) - clock["paused_total"]

    no_reply = reply == ""                                      # "" = this is a music player: no reply box
    box = {"text": reply or None, "t": tnow() if reply else None}      # Claude's reply (fetched in the background)

    if reply is None:
        def fetch():
            box["text"] = get_reply(prompt)
            box["t"] = tnow()
        threading.Thread(target=fetch, daemon=True).start()

    proc = None
    cmd = find_player(song) if song else None
    if cmd:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif song:
        audio_note = "NO AUDIO PLAYER FOUND - install mpv (sudo apt install mpv)"

    beats = list(analysis.beats) if analysis and analysis.beats else []
    drops = list(analysis.drops) if analysis and analysis.drops else []
    step = 60.0 / bpm / 2                    # one half-beat (used when we have no beat grid)
    start = tnow()
    cols, rows = shutil.get_terminal_size((80, 24))
    base_energy = min(0.9, max(0.2, (bpm - 70) / 90))      # used when we can't analyse the audio
    inten, flash, pulse, last_beat, next_drop = base_energy, 0.0, 0.0, -1, 0
    lyr_times = [t for t, _ in lyrics] if lyrics else []
    confetti, eq_state = Confetti(theme), []
    msg, msg_until, paused, show_viz = "", 0.0, False, viz and bool(analysis and analysis.samples is not None)
    speed_mul, action = 1.0, "done"
    style_names = list(STYLES)
    audience, aud_w = [], -1

    dancers = []
    for i in range(crew):
        d = {"style": random.choice(styles), "idx": 0, "color": CREW_COLORS[i % len(CREW_COLORS)],
             "rate": 1.0 if i == 0 else random.choice([0.5, 1.0, 1.0, 1.5, 2.0]),
             "off": i > 0 and random.random() < 0.3,                   # dances on the off-beat
             "x": (cols - W) * (i + 0.5) / crew, "y": random.uniform(0, max(1, rows)),
             "vx": 0.0, "vy": 0.0, "tx": 0.0, "ty": 0.0, "wp": 0.0, "next_at": 0.0,
             "cruise": random.uniform(18, 32), "blink": 0.0, "next_blink": random.uniform(1, 4),
             "fit": random_outfit() if outfits else None, "amp_mul": 1.0}
        d["pose"] = d["from"] = d["to"] = make_pose(STYLES[d["style"]][0][0])
        d["t0"], d["dur"] = 0.0, 0.2
        dancers.append(d)

    def pick_formation(prev=None):
        pool = [f for f in FORMATIONS if (f != "conga" or crew >= 3) and (f != "battle" or crew >= 2)]
        return random.choice([f for f in pool if f != prev] or pool)

    cur_form = "roam" if crew == 1 else (pick_formation() if formation == "auto" else formation)
    auto_form = crew > 1 and formation == "auto"
    next_form = start + step * 24
    next_mix = start + step * 16
    trail = []                                                          # leader's path, for the conga line
    wrapped, last = [], start

    fd, old_tty = None, None
    if keys and termios and sys.stdin.isatty():
        try:
            fd = sys.stdin.fileno()
            old_tty = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        except Exception:
            fd = None
    sys.stdout.write("\x1b[?1049h\x1b[?25l")

    def toggle_pause():
        nonlocal paused
        paused = not paused
        if paused:
            clock["paused_at"] = time.time()
        else:
            clock["paused_total"] += time.time() - clock["paused_at"]
            clock["paused_at"] = None
        if proc and proc.poll() is None:
            proc.send_signal(signal.SIGSTOP if paused else signal.SIGCONT)
        if paused:
            sys.stdout.write("\x1b[2;1H  || PAUSED - press space to resume\x1b[K")
            sys.stdout.flush()

    try:
        n = 0
        while forever or tnow() - start < max_seconds:
            # ---------------------------------------------------------------- keyboard
            if fd is not None:
                while select.select([sys.stdin], [], [], 0)[0]:
                    for ch in os.read(fd, 16).decode(errors="ignore"):
                        k = ch.lower()
                        if k == "q":
                            action = "quit"
                        elif k == "n":
                            action = "next"
                        elif ch == " ":
                            toggle_pause()
                        elif k == "s":
                            lead_i = style_names.index(dancers[0]["style"])
                            for j, d in enumerate(dancers):
                                d["style"], d["idx"] = style_names[(lead_i + 1 + j) % len(style_names)], 0
                            mix, msg = False, "style: " + dancers[0]["style"]
                        elif k == "f" and crew > 1:
                            auto_form, cur_form = False, FORMATIONS[(FORMATIONS.index(cur_form) + 1) % len(FORMATIONS)]
                            while (cur_form == "conga" and crew < 3):
                                cur_form = FORMATIONS[(FORMATIONS.index(cur_form) + 1) % len(FORMATIONS)]
                            msg = "formation: " + cur_form
                        elif k == "o":
                            for d in dancers:
                                d["fit"] = random_outfit()
                            msg = "new outfits!"
                        elif k == "l":
                            lights = LIGHT_MODES[(LIGHT_MODES.index(lights) + 1) % len(LIGHT_MODES)]
                            msg = "lights: " + lights
                        elif k == "t":
                            theme = THEMES[(THEMES.index(theme) + 1) % len(THEMES)]
                            confetti.theme = theme
                            msg = "theme: " + theme + " (dark theme = lights glow, light theme = lights tint)"
                        elif k == "v":
                            show_viz = not show_viz and bool(analysis and analysis.samples is not None)
                            msg = "visualizer " + ("on" if show_viz else "off")
                        elif ch in "+=":
                            speed_mul, msg = min(3.0, speed_mul * 1.25), "speed x%.2f" % min(3.0, speed_mul)
                        elif ch in "-_":
                            speed_mul, msg = max(0.3, speed_mul / 1.25), "speed x%.2f" % max(0.3, speed_mul)
                        msg_until = time.time() + 2.0
                if action != "done":
                    break
            if paused:
                time.sleep(0.05)
                continue

            now = tnow()
            dt = min(now - last, 0.1)
            last = now
            at = now - start - sync                               # position in the song
            cols, rows = shutil.get_terminal_size((80, 24))
            rows = max(rows, 10)
            aud_rows, box_top, dy0, dy1 = layout(rows)
            aw, ah = cols, rows * 2                               # the stage covers the whole terminal
            ah_d = dy1 - dy0                                      # the part the dancers may use
            small = ah_d < H + 2 or cols < 60                     # tiny terminal: use half-size dancers
            if aud_w != aw:
                audience, aud_w = make_audience(aw), aw
            SW, SH = (W // 2, H // 2) if small else (W, H)
            kf = 0.5 if small else 1.0
            foot = 21 // (2 if small else 1)

            target = energy_at(analysis.energy if analysis else None, at, base_energy)
            inten += (target - inten) * min(1.0, 2.0 * dt)         # glide, don't jump
            amp = 0.45 + 0.75 * inten
            tempo = 0.5 + 1.1 * inten

            song_done = proc is not None and proc.poll() is not None
            if song_done and proc.returncode not in (0, None) and now - start < 3:
                audio_note = "AUDIO PLAYER FAILED (%s) - is a sound device available?" % os.path.basename(cmd[0])
            if box["text"] is not None and not wrapped:
                wrapped = textwrap.wrap(box["text"], 56) or [""]
            if forever and song_done:                         # song over: cli starts the next one, no pause
                break
            shown = 0
            if wrapped:
                shown = int((now - box["t"]) * 24)
                total = len("".join(wrapped))
                if not forever and shown >= total and (song_done or proc is None) and \
                        now - box["t"] > 0.8 + total / 24 + (3 if proc is None else 0):
                    break

            # ---------------------------------------------------------------- beats, drops, chorus
            if beats:
                bp = beat_phase(beats, at)
                if bp and bp[0] != last_beat:
                    last_beat = bp[0]
                    pulse = 1.0 if last_beat % 4 else 1.5
                    if inten > 0.75 and last_beat % 4 == 0:
                        confetti.burst(aw, 10)
            while next_drop < len(drops) and at >= drops[next_drop]:
                confetti.burst(aw, 90)
                flash, msg, msg_until, next_drop = 1.4, "♫ DROP! ♫", time.time() + 2.0, next_drop + 1
            pulse *= math.exp(-7 * dt)
            flash *= math.exp(-2.5 * dt)

            if mix and now >= next_mix:
                next_mix = now + step * 16
                for d in dancers:
                    d["style"], d["idx"] = random.choice(styles), 0
            if auto_form and now >= next_form:
                next_form = now + step * 24
                cur_form = pick_formation(cur_form)

            slots = formation_slots(cur_form, crew, aw, ah_d, now - start, SW, SH) \
                if cur_form in ("circle", "line", "vee", "battle") else None
            if slots:
                slots = [(x, y + dy0) for x, y in slots]
            solo = int((now - start) / (step * 16)) % crew if cur_form == "battle" else -1
            if slots and cur_form == "battle":
                slots[solo] = ((aw - SW) / 2, dy0 + (ah_d - SH) / 2)           # the soloist steps up to the middle
            if dancers:
                trail.append((now, dancers[0]["x"], dancers[0]["y"]))
                while trail and trail[0][0] < now - 12:
                    trail.pop(0)

            for i, d in enumerate(dancers):
                # --- dance step: ease from the current pose to the next key pose
                moves, order, hold, snap = STYLES[d["style"]]
                d["amp_mul"] = (1.3 if i == solo else 0.55) if cur_form == "battle" else 1.0
                rate = d["rate"] * (1.2 if i == solo else 1.0)
                if at >= d["next_at"]:
                    mv = random.choice(moves) if order == "random" else moves[d["idx"] % len(moves)]
                    d["idx"] += 1
                    d["from"], d["to"] = d["pose"], make_pose(mv, amp * d["amp_mul"])
                    if beats:
                        per = snap_per_beat(2 * rate * tempo / hold)
                        nxt = next_grid_time(beats, at, per, step)
                        if d["off"]:
                            nxt += 0.5 * (60.0 / bpm) / per
                    else:
                        nxt = at + step * hold / (rate * tempo)
                    d["t0"], d["dur"] = at, max(0.08, min(0.45, (nxt - at) * 0.7))
                    d["next_at"] = nxt
                k = 1.0 if snap else ease_back(min(1.0, (at - d["t0"]) / d["dur"]))
                pose = blend(d["from"], d["to"], k)
                d["pose"] = pose
                draw_pose = dict(pose)
                if not snap and not pose["flip"]:                  # bounce on every beat
                    if beats:
                        draw_pose["dy"] -= (1.2 + 1.8 * pulse) * amp
                    else:
                        draw_pose["dy"] -= 1.6 * amp * abs(math.sin(math.pi * at * d["rate"] / (step * 2)))
                d["draw"] = draw_pose

                # --- travel
                spd = speed * speed_mul
                if cur_form == "conga" and i > 0 and trail:
                    want_t = now - i * 0.8
                    tx, ty = min(trail, key=lambda q: abs(q[0] - want_t))[1:]
                    d["tx"], d["ty"], vmax = tx, ty, 90 * spd
                elif slots:
                    d["tx"], d["ty"] = slots[i]
                    vmax = 70 * spd * (0.4 + inten)
                else:
                    d["wp"] -= dt
                    if d["wp"] <= 0 or math.hypot(d["tx"] - d["x"], d["ty"] - d["y"]) < 3:
                        d["tx"], d["ty"] = random.uniform(0, max(1, aw - SW)), random.uniform(dy0, max(dy0 + 1, dy1 - SH))
                        d["wp"] = random.uniform(2, 5)
                    vmax = d["cruise"] * spd * (0.35 + 1.3 * inten)
                dx, dy = d["tx"] - d["x"], d["ty"] - d["y"]
                dist = math.hypot(dx, dy)
                want = min(vmax, dist * 2.5)
                dvx, dvy = (dx / dist * want, dy / dist * want) if dist > 0.5 else (0.0, 0.0)
                d["vx"] += (dvx - d["vx"]) * min(1.0, 4 * dt)
                d["vy"] += (dvy - d["vy"]) * min(1.0, 4 * dt)
                d["x"] = min(max(d["x"] + d["vx"] * dt, 0), max(0, aw - SW))
                d["y"] = min(max(d["y"] + d["vy"] * dt, dy0), max(dy0, dy1 - SH))

                d["next_blink"] -= dt
                if d["next_blink"] <= 0:
                    d["blink"], d["next_blink"] = 0.12, random.uniform(1.5, 4.5)
                d["blink"] = max(0.0, d["blink"] - dt)

            # ---------------------------------------------------------------- draw the stage
            if spot:
                canvas = build_stage(aw, ah, now - start, dancers[0], dancers[1:], flash, foot, kf,
                                     lighting(lights, inten, pulse, now - start, max(last_beat, 0), theme), theme)
            else:
                canvas = [[None] * aw for _ in range(ah)]
            if show_viz:
                draw_equalizer(canvas, aw, ah, band_levels(analysis, at), eq_state, theme, base=ah - 2 * aud_rows)
            for d in dancers:                                      # shadows first
                oy = int(d["y"]) + foot + 1
                lift = max(0.0, -d["draw"]["dy"])
                half = max(2, int((8 - lift * 1.2) * kf))
                mid = int(d["x"] + SW / 2 + d["draw"]["dx"] * kf)
                if 0 <= oy < ah:
                    for x in range(mid - half, mid + half):
                        if 0 <= x < aw:
                            base = canvas[oy][x]
                            canvas[oy][x] = tuple(int(c * 0.5) for c in base) if base else SHADOW
            for i, d in enumerate(sorted(dancers, key=lambda q: q["y"])):
                face = 1 if d["vx"] > 6 else (-1 if d["vx"] < -6 else 0)
                if cur_form == "battle":
                    face = 1 if dancers.index(d) % 2 == 0 else -1
                dp = d["draw"]
                happy = dp["dy"] < -2.4 or (dp["la"] > 120 and dp["ra"] > 120)
                gr = sprite(dp, d["color"], face, d["blink"] > 0, happy, d["fit"])
                if small:
                    gr = shrink(gr)
                ox, oy = int(d["x"]), int(d["y"])
                if spot and not dp["flip"]:                            # soft reflection on the floor
                    gy = oy + foot + 1
                    for r in range(1, 8 // (2 if small else 1) + 1):
                        sy_, dy_ = foot - r + 1, gy + r
                        if 0 <= sy_ < len(gr) and 0 <= dy_ < ah:
                            for xx in range(len(gr[sy_])):
                                c, px = gr[sy_][xx], ox + xx
                                if c is not None and 0 <= px < aw and canvas[dy_][px] is not None:
                                    b_ = canvas[dy_][px]
                                    f_ = 0.30 - 0.025 * r
                                    canvas[dy_][px] = tuple(int(b_[i] * (1 - f_) + c[i] * f_) for i in range(3))
                for yy in range(len(gr)):
                    cy = oy + yy
                    if 0 <= cy < ah:
                        row, src = canvas[cy], gr[yy]
                        for xx in range(len(src)):
                            c = src[xx]
                            if c is not None and 0 <= ox + xx < aw:
                                row[ox + xx] = c
            if aud_rows:
                draw_audience(canvas, aw, ah, 2 * aud_rows, now - start, inten, pulse, flash, theme, audience)
            confetti.update(dt, ah)
            confetti.draw(canvas, aw, ah)

            cells = to_cells(canvas, aw, ah // 2)

            # ---------------------------------------------------------------- the text box
            idx = bisect.bisect_right(lyr_times, at - lyr_offset) - 1 if lyrics else -1
            cur = lyrics[idx][1] if idx >= 0 else ""
            nxt = lyrics[idx + 1][1] if lyrics and idx + 1 < len(lyrics) else ""
            lyric_live = bool(cur.strip())
            reply_hold = wrapped and now < box["t"] + len("".join(wrapped[:2])) / 24 + 3.5
            box_rows = cells[box_top:box_top + 4]                       # the card floats over the stage
            if wrapped and (reply_hold or not lyric_live):             # Claude's reply (shown first)
                l1, l2 = wrapped[0], (wrapped[1] if len(wrapped) > 1 else "")
                if len(wrapped) > 2:
                    l2 = l2[:55] + "…"
                draw_lyrics(box_rows, l1[:shown], l2[:max(0, shown - len(l1))], BUBBLE_FG, BUBBLE_FG, "",
                            full=max(len(l1), len(l2)) + 2)
            elif lyric_live:
                span = (lyr_times[idx + 1] - lyr_times[idx]) if idx + 1 < len(lyr_times) else 4.0
                prog = min(1.0, (at - lyr_offset - lyr_times[idx]) / max(0.8, min(span, 9.0) * 0.85))
                draw_lyrics(box_rows, cur, nxt, progress=prog)
            elif not wrapped:
                if no_reply:
                    draw_lyrics(box_rows, name[:56], "", (200, 195, 215))
                else:
                    draw_lyrics(box_rows, "Claude is thinking" + "." * (n // 8 % 4), "", (175, 170, 190), pad="")
            else:
                draw_lyrics(box_rows, "", nxt)

            tags = " | ".join(dict.fromkeys(d["style"] for d in dancers))
            meter = "▁▂▃▄▅▆▇█"[min(7, int(inten * 8))]
            head = "  ♪ ♫  %s  [%s]  %d BPM  energy %s  lights %s  %s  ♫ ♪" % (
                name, tags, bpm, meter, lights, cur_form if crew > 1 else "")
            hint = ("  " + msg) if (msg and time.time() < msg_until) else (
                "  " + HINT.replace("[q] quit", "[q] " + quit_text) if fd is not None else "")
            if audio_note:
                head = "  !! " + audio_note
            overlay_chip(cells, 0, 0, head.strip()[:cols - 4], (255, 205, 150))
            if hint.strip():
                overlay_chip(cells, 1, 0, hint.strip()[:cols - 4], (170, 165, 200))
            sys.stdout.write("\x1b[H" + "\x1b[K\n".join(serialize(cells)) + "\x1b[K\x1b[J")
            sys.stdout.flush()
            n += 1
            time.sleep(max(0.0, 1 / 30 - (tnow() - now)))
    finally:
        if proc and proc.poll() is None:
            if paused:
                proc.send_signal(signal.SIGCONT)
            proc.terminate()
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        if fd is not None and old_tty is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_tty)
            termios.tcflush(fd, termios.TCIFLUSH)
        if box["text"] and print_reply:
            print(box["text"])
        sys.stdout.flush()
    return action
