# Converts in depth

An osu! beatmap can be played in another ruleset. parsecore reproduces each conversion
exactly like osu!, so converted star ratings and pp match the game.

## osu! → taiko

Circles become don/kat notes (decided by hit sound), and sliders are either kept as drum
rolls or split into a run of hit circles following osu!-stable's tick-spacing and
velocity rules. Scroll-speed effect points are inserted so the new **Reading** skill sees
the right velocities.

## osu! → catch

Objects become fruits, droplets and juice streams. Hyperdashes are detected, and the
legacy RNG is consumed for droplet jitter and banana showers exactly as in the game.

## osu! → mania

This is the most involved conversion: the full **legacy pattern generator** decides how
many columns the map uses and places notes/hold notes using osu!stable's RNG. The
generated pattern and therefore the star rating and pp is bit-identical to osu!.

```python
from parsecore.Beatmap.beatmap import Beatmap as UserBeatmap
from parsecore.Performance import Beatmap, Difficulty, GameMode

bm = Beatmap.from_user_beatmap(
    UserBeatmap.from_path("osu_map.osu"), override_mode=GameMode.TAIKO
)
print(Difficulty().calculate(bm).stars)
```

Native maps of each ruleset are, of course, calculated directly without conversion.
