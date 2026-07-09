"""osu!mania star-rating calculation.

MIT License

Copyright (c) 2026-Present O!Lib Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...data.attributes import AdjustedBeatmapAttributes, as_override
from ...data.beatmap import PerformanceBeatmap
from ...data.mode import GameMode
from ...data.mods import PerformanceMods
from .convert import convert_to_mania_objects
from .skills import (
    _osu_legacy_sort_in_place,
    create_mania_difficulty_objects,
    run_strain,
)


def _cmp_mania_round_start(a: Any, b: Any) -> int:
    """Compare two mania objects by their round-half-even start time (legacy sort key)."""
    ra = int(round(a.start_time))
    rb = int(round(b.start_time))
    return (ra > rb) - (ra < rb)

DIFFICULTY_MULTIPLIER = 0.018

@dataclass(slots=True)
class ManiaDifficultyAttributes:
    """Difficulty attributes of a mania beatmap (stars, object/hold counts, hit windows)."""
    stars: float = 0.0
    n_objects: int = 0
    n_hold_notes: int = 0
    max_combo: int = 0
    great_hit_window: float = 0.0
    good_hit_window: float = 0.0
    is_convert: bool = False
    clock_rate: float = 1.0
    ar: float = 0.0
    cs: float = 0.0
    hp: float = 0.0
    od: float = 0.0

def calculate_difficulty(
        pm: PerformanceBeatmap,
        mods: PerformanceMods,
        *,
        lazer: bool = True,
        ar_override: float | None = None,
        cs_override: float | None = None,
        hp_override: float | None = None,
        od_override: float | None = None,
        passed_objects: int | None = None,
        **_: Any,
) -> ManiaDifficultyAttributes:
    """Compute the mania difficulty attributes for a beatmap and mods.

    Args:
        pm: The performance beatmap.
        mods: The mods and clock rate.

    Returns:
        The mania difficulty attributes.
    """
    adjusted = AdjustedBeatmapAttributes.create(
        base_cs=pm.base_cs, base_ar=pm.base_ar,
        base_od=pm.base_od, base_hp=pm.base_hp,
        mode=GameMode.MANIA, mods=mods,
        ar_override=as_override(ar_override),
        cs_override=as_override(cs_override),
        hp_override=as_override(hp_override),
        od_override=as_override(od_override),
    )

    mania_objects, max_combo_raw, n_hold_notes_raw, total_columns = (
        convert_to_mania_objects(pm, mods=mods)
    )

    _osu_legacy_sort_in_place(mania_objects, _cmp_mania_round_start)

    if passed_objects is not None and passed_objects < len(mania_objects):
        visible = mania_objects[:passed_objects]
        max_combo = 0
        n_hold_notes = 0
        for obj in visible:
            if obj.is_long_note():
                duration = obj.end_time - obj.start_time
                max_combo += 1 + int(duration / 100.0)
                n_hold_notes += 1
            else:
                max_combo += 1
        n_objects = len(visible)
    else:
        visible = mania_objects
        n_objects = len(mania_objects)
        max_combo = max_combo_raw
        n_hold_notes = n_hold_notes_raw

    diff_objects = create_mania_difficulty_objects(
        visible, clock_rate=adjusted.clock_rate, total_columns=total_columns,
    )
    strain = run_strain(diff_objects, total_columns)
    stars = strain.difficulty_value() * DIFFICULTY_MULTIPLIER

    return ManiaDifficultyAttributes(
        stars=stars,
        n_objects=n_objects,
        n_hold_notes=n_hold_notes,
        max_combo=max_combo,
        great_hit_window=adjusted.hit_windows.od_great or 0.0,
        good_hit_window=adjusted.hit_windows.od_ok or 0.0,
        is_convert=pm.is_convert,
        clock_rate=adjusted.clock_rate,
        ar=adjusted.ar,
        cs=adjusted.cs,
        hp=adjusted.hp,
        od=adjusted.od,
    )