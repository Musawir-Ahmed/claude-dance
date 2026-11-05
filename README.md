# Claude Dance

Claude's mascot dances in your terminal to a song, wearing random outfits and wigs, while a text box shows
the lyrics (and Claude's reply). Python 3 only, no pip packages.

**Music-player mode:** just run `python3 dance.py` - a menu opens: search YouTube, pick a song, it downloads and the crew
dances to it. Also: library (downloaded + your own files), queue, settings (saved), recent searches. Add `--light`, `--crew 4`
etc. to set the menu's defaults. `q` while dancing goes back to the menu; `--no-menu` skips the menu.

```bash
python3 dance.py --youtube "بشرة خير" --crew 3 --claude "tell me good news" --full
python3 dance.py --song songs/my.mp3 --dance salsa --formation circle
python3 dance.py --youtube "song one" --youtube "song two" --shuffle      # playlist
python3 dance.py --all --loop --min-wait 300 --max-wait 1800               # pops up now and then
```

Needs: an audio player (mpv, ffplay, vlc...), `ffmpeg` for beat/loudness analysis, and `yt-dlp` for `--youtube`
(`pip install --user --break-system-packages yt-dlp`). Without ffmpeg it still dances, using the tempo only.

## What it does
* **Beat sync** - tempo and beat times are tracked from the audio; moves land on beats, each dancer on
  their own subdivision (half-time, on-beat, double-time, some off-beat). `--sync 0.2` if moves land late.
* **Energy** - quiet parts: slow, small moves. Loud parts: fast, big moves. Sudden loud parts ("drops") fire confetti and a light flash.
* **Style from metadata** - title/tags/genre pick the dance (`--dance` overrides). Styles: party salsa breakdance disco robot floss moonwalk wave.
* **Formations** - roam, circle, line, vee, conga (follow the leader), battle (two crews, solos). `--formation auto` cycles.
* **Text box** - synced lyrics (LRCLIB, else YouTube captions, else a `song.lrc` next to the file) with the current words lit;
  Claude's reply is shown there first. `--lyrics-offset 2` shifts the lyrics.
* **Lights** (`--lights auto|low|high|strobe|pulse|disco|off`, key `l`) - `auto` follows the music: dim and slow when quiet, more beams, brightness and sparkles when loud.
* **Light mode** (`--light` or `--theme light`, key `t`): a bright stage for light terminals; lights tint instead of glow.
* **Never closes by itself** with `--forever` (song after song) until you press `q` or Ctrl-C.
* **Equalizer** along the floor, **follow-spot** and colour beams, **small-terminal mode** (half-size dancers).

## Keys
`space` pause - `n` next song - `s` style - `f` formation - `o` new outfits - `l` lights - `t` dark/light theme - `v` equalizer - `+`/`-` speed - `q` quit

## Claude Code hook (dance after Claude answers)
```bash
python3 dance.py --install-hook --crew random          # prints the entry
python3 dance.py --install-hook --crew random --yes    # merges it into ~/.claude/settings.json (backup kept)
```
After a response it opens a new terminal window (or a tmux popup) with the dance and Claude's last reply, but only
once the random wait (`--min-wait`/`--max-wait`, default 120-900 s) has passed.

## Layout
`dance.py` launcher - `cdance/` (`show` main loop, `sprites` characters/outfits, `stage` lights/text box/effects,
`audio` analysis, `lyrics`, `songs` metadata + YouTube + queue, `hook`, `cli`) - `tests/` (`python3 -m unittest discover -s tests`).
Downloads are cached in `songs/youtube/`. Use downloaded audio for personal use only.

---
Created by **Musawir Ahmed**.
