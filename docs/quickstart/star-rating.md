# Star rating (difficulty)

Use {class}`~parsecore.Performance.api.Difficulty` to compute the star rating and the
per-skill difficulty attributes.

```python
from parsecore.Performance import Beatmap, Difficulty

bm = Beatmap.from_path("path/to/map.osu")

# NoMod
attrs = Difficulty().calculate(bm)
print(attrs.stars, attrs.max_combo)

# Mods via legacy bitflags (HD = 8, DT = 64, ...)
attrs = Difficulty().mods(8 | 64).calculate(bm)
print(attrs.stars)

# osu! attributes expose the per-skill breakdown of the 2026 rework
print(attrs.aim, attrs.speed, attrs.reading, attrs.flashlight)
```

## Clock rate, overrides and partial maps

```python
attrs = (
    Difficulty()
    .mods(64)
    .clock_rate(1.3)
    .ar(10, fixed=True)   # fixed=True: use as-is; fixed=False: mods still adjust it
    .passed_objects(500)  # difficulty of the first 500 objects only
    .calculate(bm)
)
```

:::{note}
`fixed=False` (the default) means EZ/HR and the clock rate still adjust the value, just
like an in-game difficulty override; `fixed=True` uses your value verbatim.
:::

Each ruleset returns its own attributes type see {doc}`../api/performance`.
