#!/usr/bin/env python3
# Author: Musawir Ahmed
"""Claude Dance - the Claude mascot dances in your terminal while a song plays,
and the reply appears in a speech bubble that follows the lead dancer.

  python3 dance.py                       # one dance, random song from ./songs
  python3 dance.py --crew 4              # a team, each on their own beat
  python3 dance.py --dance salsa         # salsa party breakdance disco robot floss
  python3 dance.py --formation circle    # roam circle line vee (default: auto-cycles)
  python3 dance.py --song songs/bushra_khair.mp3 --bpm 100
  python3 dance.py --youtube "بشرة خير"      # fetch from YouTube; style + tempo come from its metadata
  python3 dance.py --claude "tell me good news"    # reply from `claude -p`
  python3 dance.py --loop                # come back at random intervals

Put your own audio files (mp3/ogg/wav/m4a/opus) in ./songs.
Needs one of: mpv, ffplay, cvlc, paplay, afplay (otherwise it dances silently)."""
from cdance.cli import main

if __name__ == "__main__":
    main()
