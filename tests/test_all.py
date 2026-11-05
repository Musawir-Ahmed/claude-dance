# Author: Musawir Ahmed
"""Run with:  python3 -m unittest discover -s tests -v   (standard library only)"""
import array, io, json, math, os, random, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cdance import audio, hook, lyrics, menu, songs, sprites, stage
from cdance.show import next_grid_time, snap_per_beat


def click_track(bpm, seconds=30, first=0.37, rate=audio.RATE):
    random.seed(2)
    n = rate * seconds
    smp, period = array.array("h", [0]) * n, rate * 60 / bpm
    start = int(first * rate)
    for i in range(n):
        ph = ((i - start) % period) / rate if i >= start else 9
        smp[i] = int((12000 * math.exp(-ph * 30) * math.sin(2 * math.pi * 80 * ph) if ph < 0.15 else 0) + random.randint(-300, 300))
    return smp


class AudioTests(unittest.TestCase):
    def test_tempo_detection(self):
        for bpm in (96, 120, 140):
            self.assertAlmostEqual(audio.bpm_from_samples(click_track(bpm)), bpm, delta=1.5)

    def test_beats_land_on_the_clicks(self):
        smp = click_track(100)
        beats = audio.track_beats(smp, audio.bpm_from_samples(smp))
        self.assertGreater(len(beats), 45)
        errors = [min(abs(b - (0.37 + k * 0.6)) for k in range(70)) for b in beats]
        self.assertLess(sorted(errors)[len(errors) // 2], 0.03)

    def test_drops_found_on_sudden_loudness(self):
        curve = [0.1] * 20 + [0.9] * 20
        self.assertEqual(audio.find_drops(curve), [10.0])

    def test_band_levels_respond_to_a_tone(self):
        rate, f = audio.RATE, 220
        smp = array.array("h", [int(10000 * math.sin(2 * math.pi * f * i / rate)) for i in range(rate * 2)])
        levels = audio.band_levels(audio.Analysis(samples=smp), 1.0)
        self.assertEqual(levels.index(max(levels)), audio.BAND_FREQS.index(220))
        self.assertLess(sorted(levels)[-2], 0.5)            # the other bands stay low

    def test_beat_phase(self):
        self.assertEqual(audio.beat_phase([0, 1, 2], 1.5), (1, 0.5))
        self.assertIsNone(audio.beat_phase([0, 1, 2], 5))


class BeatGridTests(unittest.TestCase):
    beats = [1.0, 2.0, 3.0, 4.0]

    def test_subdivisions(self):
        self.assertAlmostEqual(next_grid_time(self.beats, 1.1, 1, 0.5), 2.0)
        self.assertAlmostEqual(next_grid_time(self.beats, 1.1, 2, 0.5), 1.5)
        self.assertAlmostEqual(next_grid_time(self.beats, 1.6, 4, 0.5), 1.75)

    def test_half_time_skips_every_other_beat(self):
        # half-time lands only on every 2nd beat (indices 0, 2, 4...), so after 1.1 the next one is beat 2 = 3.0
        self.assertAlmostEqual(next_grid_time(self.beats, 1.1, 0.5, 0.5), 3.0)
        self.assertAlmostEqual(next_grid_time(self.beats, 3.1, 0.5, 0.5), 3.1 + 1.0 * 1.0, delta=1.5)

    def test_no_beats_falls_back(self):
        self.assertAlmostEqual(next_grid_time([], 5.0, 1, 0.3), 5.3)

    def test_snap(self):
        self.assertEqual(snap_per_beat(1.7), 2)
        self.assertEqual(snap_per_beat(0.6), 0.5)


class SongTests(unittest.TestCase):
    def test_style_from_metadata(self):
        self.assertEqual(songs.decide_style({"title": "Hips Don't Lie", "tags": ["latin"]})[0], "salsa")
        self.assertEqual(songs.decide_style({"title": "Boshret Kheir"})[0], "party")
        self.assertEqual(songs.decide_style({"title": "Billie Jean - Michael Jackson"})[0], "moonwalk")
        self.assertIsNone(songs.decide_style({"title": "cooking lecture"})[0])

    def test_queue(self):
        class A: youtube = ["x", "y"]; song = ["a.mp3"]; playlist_file = None; all = False; shuffle = False; songs_dir = "/nonexistent"
        self.assertEqual(songs.build_queue(A), [("youtube", "x"), ("youtube", "y"), ("file", "a.mp3")])
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("# comment\nhello world\nhttps://youtu.be/abc\n")
        class B(A): youtube = None; song = None; playlist_file = f.name
        self.assertEqual(songs.build_queue(B), [("youtube", "hello world"), ("youtube", "https://youtu.be/abc")])
        os.remove(f.name)


class LyricsTests(unittest.TestCase):
    def test_lrc(self):
        self.assertEqual(lyrics.parse_lrc("[00:01.50]hello\n[01:02.00]world\njunk"), [(1.5, "hello"), (62.0, "world")])

    def test_vtt_rolling_captions_deduped(self):
        vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nline one\n\n00:00:03.000 --> 00:00:05.000\nline one\nline two\n"
        self.assertEqual(lyrics.parse_vtt(vtt, rolling=True), [(1.0, "line one"), (3.0, "line two")])

    def test_title_cleanup(self):
        c = lyrics.title_candidates({"title": "حسين الجسمي - بشرة خير (فيديو كليب) | Hussain Al Jassmi - Boshret Kheir | 2014"})
        self.assertIn("Hussain Al Jassmi Boshret Kheir", c)
        self.assertNotIn("2014", c)


class SpriteTests(unittest.TestCase):
    def test_every_move_and_outfit_renders(self):
        random.seed(5)
        for name, (moves, _, _, _) in sprites.STYLES.items():
            for mv in moves:
                for _ in range(3):
                    g = sprites.sprite(sprites.make_pose(mv, 0.8), sprites.ORANGE, 1, False, random.random() < 0.5, sprites.random_outfit())
                    self.assertEqual((len(g), len(g[0])), (sprites.H, sprites.W))
                    self.assertTrue(any(c is not None for row in g for c in row))

    def test_shrink_keeps_eyes(self):
        g = sprites.sprite(sprites.make_pose(sprites.PARTY[0]), sprites.ORANGE)
        small = sprites.shrink(g)
        self.assertEqual((len(small), len(small[0])), (sprites.H // 2, sprites.W // 2))
        self.assertTrue(any(c == sprites.EYE for row in small for c in row))


class StageTests(unittest.TestCase):
    def test_formations_inside_screen(self):
        for kind in ("line", "circle", "vee", "battle"):
            for n in (1, 2, 5):
                self.assertEqual(len(stage.formation_slots(kind, n, 120, 60, 1.0)), n)

    def test_karaoke_lights_words_in_order(self):
        cells = [[(" ", None, None)] * 80 for _ in range(4)]
        stage.draw_lyrics(cells, "one two three four", "", progress=0.5)
        row = cells[1]
        lit = [c[1] == stage.LIT for c in row if c[0] not in " │♪"]
        self.assertTrue(lit[0] and not lit[-1])

    def test_lighting_modes(self):
        lead = {"x": 40, "y": 20, "color": (217, 119, 87)}
        mean = {}
        for mode in stage.LIGHT_MODES:
            bg = stage.build_stage(100, 60, 3.0, lead, [], 0, 21, 1.0, stage.lighting(mode, 0.5, 0.8, 3.0, 2))
            self.assertEqual((len(bg), len(bg[0])), (60, 100))
            mean[mode] = sum(sum(px) for row in bg for px in row) / (60 * 100 * 3)
        self.assertLess(mean["off"], mean["low"])
        self.assertLess(mean["low"], mean["high"])
        self.assertGreater(mean["strobe"], mean["high"])

    def test_light_theme_is_bright_and_tints_not_glows(self):
        lead = {"x": 40, "y": 20, "color": (217, 119, 87)}
        bg = stage.build_stage(100, 60, 3.0, lead, [], 0, 21, 1.0, stage.lighting("high", 0.9, 0, 3.0, 0, "light"), "light")
        mean = sum(sum(px) for row in bg for px in row) / (60 * 100 * 3)
        self.assertGreater(mean, 190)
        self.assertTrue(all(0 <= v <= 255 for row in bg for px in row for v in px))

    def test_auto_lights_follow_energy(self):
        quiet, loud = stage.lighting("auto", 0.1, 0, 0), stage.lighting("auto", 0.95, 0, 0)
        self.assertLess(quiet["master"], loud["master"])
        self.assertLess(quiet["beams"], loud["beams"])
        self.assertEqual(quiet["sparkle"], 0)

    def test_rtl_lyrics_keep_a_single_colour(self):
        cells = [[(" ", None, None)] * 80 for _ in range(4)]
        stage.draw_lyrics(cells, "ماتستخفش فيها صوك", "", progress=0.5)
        colours = {c[1] for c in cells[1] if c[0] not in " │"}
        self.assertEqual(len(colours), 1)

    def test_layout_gives_every_size_a_sane_split(self):
        for rows in (10, 14, 18, 24, 30, 40, 60):
            aud, box_top, dy0, dy1 = stage.layout(rows)
            self.assertLessEqual(box_top + 4 + aud, rows)           # box and audience fit under each other
            self.assertGreaterEqual(dy1, dy0)
            self.assertLessEqual(dy1, 2 * rows)
        self.assertEqual(stage.layout(34)[0], 5)
        self.assertEqual(stage.layout(10)[0], 0)

    def test_audience_reacts_to_energy_and_stays_on_screen(self):
        people = stage.make_audience(100)
        self.assertEqual(people, stage.make_audience(100))           # same crowd for the same width
        counts = {}
        for inten in (0.1, 0.95):
            canvas = [[(0, 0, 0)] * 100 for _ in range(60)]
            stage.draw_audience(canvas, 100, 60, 10, 1.0, inten, 0.0, 0.0, "dark", people)
            counts[inten] = sum(1 for row in canvas for c in row if c != (0, 0, 0))
        self.assertGreater(counts[0.95], counts[0.1])                # more hands (and glow sticks) up when loud

    def test_audience_is_greyscale(self):
        for theme in ("dark", "light"):
            canvas = [[(120, 130, 140)] * 100 for _ in range(60)]
            stage.draw_audience(canvas, 100, 60, 10, 1.0, 0.95, 0.0, 1.0, theme, stage.make_audience(100))
            for row in canvas:
                for c in row:
                    if c != (120, 130, 140):
                        self.assertEqual(c[0], c[1]); self.assertEqual(c[1], c[2])

    def test_overlay_chip_is_one_colour_run(self):
        cells = [[(" ", None, (200, 200, 200))] * 30 for _ in range(2)]
        stage.overlay_chip(cells, 0, 1, "hello", (255, 255, 255))
        self.assertEqual({c[2] for c in cells[0][1:8]}, {(18, 16, 32)})

    def test_render_roundtrip(self):
        canvas = [[(10, 10, 10)] * 6 for _ in range(4)]
        self.assertEqual(len(stage.serialize(stage.to_cells(canvas, 6, 2))), 2)


class HookTests(unittest.TestCase):
    def transcript(self, texts):
        f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        for role, t in texts:
            f.write(json.dumps({"type": role, "message": {"role": role, "content": [{"type": "text", "text": t}]}}) + "\n")
        f.close()
        return f.name

    def test_reads_last_assistant_reply(self):
        p = self.transcript([("user", "hi"), ("assistant", "first"), ("user", "more"), ("assistant", "All   done!\nGreat.")])
        self.assertEqual(hook.last_assistant_text(p), "All done! Great.")
        os.remove(p)

    def test_random_interval_gate(self):
        state = os.path.join(tempfile.mkdtemp(), "s.json")
        self.assertTrue(hook.due(100, 100, now=1000, state_file=state))
        self.assertFalse(hook.due(100, 100, now=1050, state_file=state))
        self.assertTrue(hook.due(100, 100, now=1101, state_file=state))

    def test_hook_builds_command_without_spawning(self):
        p = self.transcript([("assistant", "Done")])
        os.environ.pop("TMUX", None)
        real_due, cmd = hook.due, None
        try:
            hook.due = lambda *a, **k: True
            cmd = hook.run_hook(["--crew", "3"], dry_run=True, stdin=io.StringIO(json.dumps({"transcript_path": p})))
        finally:
            hook.due = real_due
            os.remove(p)
        self.assertIsNotNone(cmd)
        joined = " ".join(cmd)
        self.assertIn("--reply-file", joined)
        self.assertIn("--crew 3", joined)

    def test_install_merges_without_duplicates(self):
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        json.dump({"theme": "dark"}, open(path, "w"))
        hook.install_hook(["--crew", "2"], write=True, settings_path=path)
        hook.install_hook(["--crew", "2"], write=True, settings_path=path)
        data = json.load(open(path))
        self.assertEqual(data["theme"], "dark")
        self.assertEqual(len(data["hooks"]["Stop"]), 1)


class MenuTests(unittest.TestCase):
    def keys(self, data):
        import codecs
        return menu.parse_keys(data, codecs.getincrementaldecoder("utf-8")(errors="ignore"))

    def test_key_parsing(self):
        self.assertEqual(self.keys(b"\x1b[A\x1b[B\x1b[C\x1b[D"), ["up", "down", "right", "left"])
        self.assertEqual(self.keys(b"\r"), ["enter"])
        self.assertEqual(self.keys(b"\x7f"), ["backspace"])
        self.assertEqual(self.keys(b"\x1b"), ["esc"])
        self.assertEqual(self.keys(b"a/"), ["a", "/"])

    def test_arabic_input_is_decoded(self):
        self.assertEqual("".join(self.keys("بشرة".encode())), "بشرة")

    def test_split_utf8_bytes_across_reads(self):
        import codecs
        dec = codecs.getincrementaldecoder("utf-8")(errors="ignore")
        raw = "ب".encode()
        self.assertEqual(menu.parse_keys(raw[:1], dec) + menu.parse_keys(raw[1:], dec), ["ب"])

    def test_search_results_parsing(self):
        fake = '{"id": "abc", "title": "Song A", "uploader": "X", "duration": 227}\nnot json\n{"id": "def", "title": "Song B", "channel": "Y"}\n'
        class R: stdout, stderr, returncode = fake, "", 0
        real_run, real_find = songs.subprocess.run, songs.find_ytdlp
        songs.subprocess.run, songs.find_ytdlp = (lambda *a, **k: R), (lambda: ["yt-dlp"])
        try:
            out = songs.youtube_search("x")
        finally:
            songs.subprocess.run, songs.find_ytdlp = real_run, real_find
        self.assertEqual([r["title"] for r in out], ["Song A", "Song B"])
        self.assertEqual(out[0]["url"], "https://www.youtube.com/watch?v=abc")
        self.assertEqual(out[1]["uploader"], "Y")

    def test_duration_format(self):
        self.assertEqual(songs.fmt_duration(227), "3:47")
        self.assertEqual(songs.fmt_duration(3725), "1:02:05")
        self.assertEqual(songs.fmt_duration(None), "--:--")

    def test_library_uses_sidecar_titles(self):
        d = tempfile.mkdtemp()
        open(os.path.join(d, "a.mp3"), "w").close()
        open(os.path.join(d, "b_song.mp3"), "w").close()
        json.dump({"title": "Nice Title", "duration": 100}, open(os.path.join(d, "a.json"), "w"))
        titles = sorted(i["title"] for i in songs.library(d))
        self.assertEqual(titles, ["Nice Title", "b song"])

    def test_settings_cycle_and_style_mapping(self):
        import argparse
        args = argparse.Namespace(crew_n=3, names=[], formation="auto", lights="auto", theme="dark",
                                  plain=False, no_lyrics=False, no_viz=False)
        st = menu.State()
        items = {label: (get, setter) for label, get, setter in menu.settings_items(args, st)}
        items["Dancers"][1](1)
        self.assertEqual(args.crew_n, 4)
        items["Theme"][1](1)
        self.assertEqual(args.theme, "light")
        items["Dance style"][1](1)
        self.assertEqual(args.names, [list(sprites.STYLES)[0]])
        items["Outfits and wigs"][1](1)
        self.assertEqual(items["Outfits and wigs"][0](), "off")

    def test_mini_dancer_renders(self):
        self.assertGreater(len(menu.Mini().lines(time.time())), 3)


class UninstallTests(unittest.TestCase):
    def test_uninstall_removes_only_our_hook(self):
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        other = {"matcher": "", "hooks": [{"type": "command", "command": "echo hi"}]}
        json.dump({"theme": "dark", "hooks": {"Stop": [other]}}, open(path, "w"))
        hook.install_hook(["--crew", "2"], write=True, settings_path=path)
        self.assertEqual(hook.uninstall_hook(path), 1)
        data = json.load(open(path))
        self.assertEqual(data["hooks"]["Stop"], [other])
        self.assertEqual(data["theme"], "dark")
        self.assertEqual(hook.uninstall_hook(path), 0)

    def test_uninstall_cleans_empty_hooks_section(self):
        path = os.path.join(tempfile.mkdtemp(), "settings.json")
        json.dump({"theme": "dark"}, open(path, "w"))
        hook.install_hook([], write=True, settings_path=path)
        hook.uninstall_hook(path)
        self.assertEqual(json.load(open(path)), {"theme": "dark"})


if __name__ == "__main__":
    unittest.main()
