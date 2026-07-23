<div align="center">

![ParseCore](https://i.imgur.com/35asYBQ.jpeg)

**Python library for osu! beatmap parsing, mod handling, and performance point calculation.**

[![PyPI Version](https://img.shields.io/pypi/v/parsecore?style=for-the-badge&color=pink)](https://pypi.org/project/parsecore/)
[![Python](https://img.shields.io/pypi/pyversions/parsecore?style=for-the-badge&color=blue)](https://pypi.org/project/parsecore/)
[![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](LICENSE)
[![Typing](https://img.shields.io/badge/typing-checked-blue?style=for-the-badge)](https://mypy-lang.org/)
[![Code Style](https://img.shields.io/badge/code%20style-ruff-orange?style=for-the-badge)](https://docs.astral.sh/ruff/)
[![Discord](https://img.shields.io/discord/1499516844711608350?style=for-the-badge&logo=discord&label=discord&color=5865F2)](https://discord.gg/9p7whE7QxQ)
[![Docs](https://img.shields.io/readthedocs/parsecore?style=for-the-badge&logo=readthedocs&logoColor=white&label=docs)](https://parsecore.readthedocs.io)
[![Translated with Crowdin](https://img.shields.io/badge/translated%20by-Crowdin-2E3340?style=for-the-badge&logo=crowdin&logoColor=white)](https://crowdin.com/project/parsecore)
[![Downloads](https://img.shields.io/pepy/dt/parsecore?style=for-the-badge&color=blueviolet&logo=pypi&logoColor=white&label=downloads)](https://pepy.tech/project/parsecore)
[![Downloads](https://img.shields.io/pypi/dm/parsecore?style=for-the-badge&color=blueviolet&logo=pypi&logoColor=white&label=downloads%2Fmonth)](https://pypi.org/project/parsecore/)

</div>

---

### Features

- **Beatmap Parsing** - Full `.osu` file parsing including all sections: General, Metadata, Difficulty, Events, Timing Points, Hit Objects, Colors, and Editor
- **Mod Handling** - Complete mod system supporting all osu! game modes (osu!, Taiko, Catch, Mania) with legacy and modern mod representations
- **Star Rating & PP Calculation** - Complete difficulty and performance calculation for **all four rulesets** (osu!, osu!taiko, osu!catch, osu!mania)
- **Up to date** - Implements the **2026 Q2 pp/star rating rework** (osu! deploy `2026.702.1`, July 2026): the new osu! Reading skill, Snap/Flow aim, deviation-based speed pp, reworked taiko rhythm, catch linear-spacing nerf
- **Bit-exact** - Verified **bit-for-bit identical** to the official osu! C# implementation across a 4,400+ case test matrix (all rulesets, all mod combinations, converts, lazer & stable scores)
- **Converts** - Faithful osu! → taiko / catch / mania conversion, including the legacy mania pattern generator with osu!stable RNG and key mods (1K-9K)
- **Lazer & Stable scores** - Both scoring systems supported: lazer slider statistics (slider tail hits, large ticks) as well as classic scores incl. score-based miss estimation from `legacy_total_score`
- **Type-safe** - Fully typed codebase, mypy-checked

---

### Installation

```bash
pip install parsecore
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add parsecore
```

**Requires Python 3.10+**

---

### Quick Start

### Beatmap Parsing

```python
from parsecore.Beatmap import Beatmap

beatmap = Beatmap.from_path("path/to/map.osu")

print(beatmap.metadata.title)
print(beatmap.metadata.version)
print(beatmap.difficulty.approach_rate)
print(beatmap.difficulty.circle_size)

for obj in beatmap.hit_objects.hit_objects:
    print(obj)

for tp in beatmap.timing_points.control_points.timing_points:
    print(tp.time, 60000 / tp.beat_len)  # start time, BPM
```

### Star Rating (Difficulty)

```python
from parsecore.Performance import Beatmap, Difficulty

bm = Beatmap.from_path("path/to/map.osu")

# NoMod
attrs = Difficulty().calculate(bm)
print(attrs.stars, attrs.max_combo)

# Mods via legacy bitflags (HD = 8, DT = 64, ...)
attrs = Difficulty().mods(8 | 64).calculate(bm)
print(attrs.stars)

# osu! attributes include the per-skill breakdown of the 2026 rework
print(attrs.aim, attrs.speed, attrs.reading, attrs.flashlight)

# Custom clock rate, difficulty overrides, partial plays
attrs = (
    Difficulty()
    .mods(64)
    .clock_rate(1.3)
    .ar(10, fixed=True)   # fixed=True: use as-is; fixed=False: mods still apply
    .passed_objects(500)  # difficulty of the first 500 objects only
    .calculate(bm)
)
```

### Performance Points (PP)

```python
from parsecore.Performance import Beatmap, Performance

bm = Beatmap.from_path("path/to/map.osu")

# From accuracy (the score state is generated automatically)
result = Performance(bm).mods(64).accuracy(98.5).misses(2).calculate()
print(result.pp)

# From an explicit score state (osu!lazer score)
result = (
    Performance(bm)
    .lazer(True)
    .n300(194).n100(0).n50(0).misses(0)
    .combo(277)
    .slider_end_hits(68)
    .large_tick_hits(15)
    .calculate()
)
print(result.pp, result.pp_aim, result.pp_speed, result.pp_acc, result.pp_reading)

# osu!(stable) / classic score, incl. score-based miss estimation
result = (
    Performance(bm)
    .lazer(False)
    .n300(2020).n100(27).misses(4)
    .combo(1699)
    .legacy_total_score(31_546_804)
    .calculate()
)
print(result.pp, result.effective_miss_count)
```

### Converts (osu! → taiko / catch / mania)

```python
from parsecore.Beatmap.beatmap import Beatmap as UserBeatmap
from parsecore.Performance import Beatmap, Difficulty, GameMode

user_map = UserBeatmap.from_path("path/to/osu_map.osu")

# Play an osu! map in another ruleset
bm = Beatmap.from_user_beatmap(user_map, override_mode=GameMode.MANIA)
attrs = Difficulty().calculate(bm)
print(attrs.stars, attrs.n_objects, attrs.n_hold_notes)

# mania key mods change the column count of converts (7K = 1 << 18)
attrs = Difficulty().mods(1 << 18).calculate(bm)
```

### Mod Handling

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

---

### How the pp calculation works

`parsecore.Performance` is a pure-Python port of the **official osu! difficulty and
performance algorithms** (ppy/osu, deploy `2026.702.1`) not of a third-party
reimplementation. The pipeline:

1. **Parse** - the `.osu` file is decoded into hit objects, timing/difficulty/effect
   points with osu!-faithful float semantics (positions and curve math are computed
   in 32-bit floats exactly like the game client).
2. **Convert** - if the target ruleset differs from the map's native mode, the map
   is converted first (taiko drum-roll splitting with scroll-speed effect points,
   catch mode flag, mania legacy pattern generator with osu!stable RNG).
3. **Preprocess** - per-ruleset difficulty objects are built (distances, angles,
   rhythm groupings, effective BPM, ...).
4. **Skills** - each ruleset evaluates its skills (osu!: Aim, Speed, Reading,
   Flashlight; taiko: Rhythm, Reading, Colour, Stamina; catch: Movement;
   mania: Strain) and aggregates them into the star rating.
5. **Performance** - the score state (either given explicitly or generated from
   accuracy/miss count) is combined with the difficulty attributes into pp,
   including miss penalties, slider-break estimation and the classic/lazer
   scoring differences.

Every step reproduces the C# reference including its floating-point quirks
(f32 intermediates, IEEE division semantics, integer-exponent powers as explicit
multiplication, C# sorting algorithms, legacy RNG), which is what makes the
results **bit-identical** rather than merely close.

#### Verification

Correctness is enforced by a parity test suite that compares parsecore against an
oracle built from the official `ppy.osu.Game` packages:

- 4,400+ cases: star ratings and pp across all four rulesets
- extended mod matrix (EZ/HR/DT/NC/HT/HD/FL/TD/RX/AP/SO, key mods 1K-9K, combinations)
- all convert directions, native maps, edge-case and pathological maps
- randomized full score states, partial states, fails, lazer & stable scores
- **result: 0 differences every value bit-identical to the official implementation**

> **Note:** After a pp rework deploys, public calculators and bots that rely on
> outdated libraries can disagree with parsecore. When in doubt: new scores set
> in-game receive exactly the values parsecore computes.

---

### Project Structure

```
parsecore/
├── Beatmap/                # .osu file parsing and encoding
│   ├── beatmap.py
│   ├── reader.py
│   ├── encode.py
│   └── section/            # Individual section parsers
│       ├── general.py
│       ├── metadata.py
│       ├── difficulty.py
│       ├── timing_points.py
│       ├── hit_objects/
│       └── ...
├── Mods/                   # Mod system
│   ├── game_mod.py
│   ├── game_mods.py
│   ├── game_mode.py
│   ├── generated_mods.py
│   └── ...
└── Performance/            # Star rating & pp calculation
    ├── api.py              # Public API: Beatmap, Difficulty, Performance
    ├── utils.py            # Rust/C#-faithful float & RNG helpers
    ├── data/               # Beatmap model, mods, score state, attributes
    └── rulesets/
        ├── osu/            # Aim, Speed, Reading, Flashlight + pp
        ├── taiko/          # Rhythm, Reading, Colour, Stamina + pp
        ├── catch/          # Movement + pp, gradual calculation
        └── mania/          # Strain + pp, legacy convert pattern generator
```

---

### Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

### Security

To report a security vulnerability, see [SECURITY.md](SECURITY.md).

### Translations

parsecore's documentation is translated by the community on [Crowdin](https://crowdin.com/project/parsecore). Want to see it in your language? Join the project and help translate no coding required.

**Currently supported languages**

| Language | |
| --- | --- |
| 🇺🇸 English (US) | Source |
| 🇩🇪 German | [Translate →](https://crowdin.com/project/parsecore) |
| 🇫🇷 French | [Translate →](https://crowdin.com/project/parsecore) |
| 🇱🇺 Luxembourgish | [Translate →](https://crowdin.com/project/parsecore) |
| 🇵🇹 Portuguese | [Translate →](https://crowdin.com/project/parsecore) |

_The live translated site is on [Read the Docs](https://parsecore.readthedocs.io). Want to help? Join the project on [Crowdin](https://crowdin.com/project/parsecore) no coding required._

---

<p align="center">
	<img src="https://raw.githubusercontent.com/catppuccin/catppuccin/main/assets/footers/gray0_ctp_on_line.svg?sanitize=true" />
</p>

<p align="center">
        <code>&copy 2026-Present <a href="https://github.com/O-Lib">O!Lib Team</a></code>
</p>
