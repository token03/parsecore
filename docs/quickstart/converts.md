# Converts (osu! → taiko / catch / mania)

parsecore converts osu! beatmaps to the other rulesets exactly like the game including
the legacy osu!mania pattern generator with its osu!stable RNG.

```python
from parsecore.Beatmap.beatmap import Beatmap as UserBeatmap
from parsecore.Performance import Beatmap, Difficulty, GameMode

user_map = UserBeatmap.from_path("path/to/osu_map.osu")

# Play an osu! map in another ruleset
bm = Beatmap.from_user_beatmap(user_map, override_mode=GameMode.MANIA)
attrs = Difficulty().calculate(bm)
print(attrs.stars, attrs.n_objects, attrs.n_hold_notes)
```

## Key mods on mania converts

Mania key mods change the **column count** of a convert, and therefore its star rating
and pp (`7K` is the legacy bit `1 << 18`):

```python
attrs = Difficulty().mods(1 << 18).calculate(bm)  # 7K
```

:::{note}
Key mods only affect osu! → mania **converts**. On native mania maps they have no
effect, which matches the game.
:::
