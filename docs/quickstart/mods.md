# Mod handling

parsecore models every osu! mod across all rulesets, plus the classic legacy bitfield
and ruleset-agnostic (intermode) representations.

```python
from parsecore.Mods import GameMods, GameMode

# From an acronym string
mods = GameMods.from_acronyms("HDDT", GameMode.Osu)
print(mods)               # DTHD
print(mods.clock_rate())  # 1.5

# Legacy bitfield conversion
legacy = mods.as_legacy()
print(legacy.bits())      # 72

# Intermode mods (not bound to a specific ruleset)
from parsecore.Mods import GameModsIntermode
intermode = GameModsIntermode.from_acronyms(["HD", "NC"])
print(intermode)          # HDNC
```

## Concrete mod classes

Every mod has a concrete, ruleset-specific class (e.g.
{class}`~parsecore.Mods.generated_mods.HardRockOsu`,
{class}`~parsecore.Mods.generated_mods.DoubleTimeCatch`) carrying its acronym,
description, kind and legacy bit. See the full list in the {doc}`../api/mods` reference.
