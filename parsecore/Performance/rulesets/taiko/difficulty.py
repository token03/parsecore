"""osu!taiko star-rating calculation.

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
from .convert import convert_to_taiko_objects
from .skills import create_taiko_difficulty_objects, eval_skills, run_skills

@dataclass(slots=True)
class TaikoDifficultyAttributes:
    """Difficulty attributes of a taiko beatmap (stars, per-skill values, hit windows)."""
    stamina: float = 0.0
    rhythm: float = 0.0
    color: float = 0.0
    reading: float = 0.0
    great_hit_window: float = 0.0
    ok_hit_window: float = 0.0
    mono_stamina_factor: float = 0.0
    mechanical_difficulty: float = 0.0
    consistency_factor: float = 0.0
    stars: float = 0.0
    max_combo: int = 0
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
) -> TaikoDifficultyAttributes:
    """Compute the taiko difficulty attributes for a beatmap and mods.

    Args:
        pm: The performance beatmap.
        mods: The mods and clock rate.

    Returns:
        The taiko difficulty attributes.
    """
    adjusted = AdjustedBeatmapAttributes.create(
        base_cs=pm.base_cs, base_ar=pm.base_ar,
        base_od=pm.base_od, base_hp=pm.base_hp,
        mode=GameMode.TAIKO, mods=mods,
        ar_override=as_override(ar_override),
        cs_override=as_override(cs_override),
        hp_override=as_override(hp_override),
        od_override=as_override(od_override),
    )

    great_hit_window = adjusted.hit_windows.od_great or 0.0
    ok_hit_window = adjusted.hit_windows.od_ok or 0.0
    clock_rate = adjusted.clock_rate
    taiko_objects = convert_to_taiko_objects(pm, mods)

    take = passed_objects if passed_objects is not None else len(taiko_objects)
    if passed_objects is not None and 0 <= passed_objects < len(taiko_objects):
        n_diff_objects = 0
        max_combo = 0
        for obj in taiko_objects:
            if max_combo >= take:
                break
            n_diff_objects += 1
            if obj.is_hit():
                max_combo += 1
    else:
        n_diff_objects = len(taiko_objects)
        max_combo = sum(1 for obj in taiko_objects if obj.is_hit())

    global_slider_velocity = pm.slider_multiplier
    if mods.hr:
        global_slider_velocity *= 1.4 * 4.0 / 3.0
    elif mods.ez:
        global_slider_velocity *= 0.8
    if mods.scroll_speed is not None:
        global_slider_velocity *= float(mods.scroll_speed)

    diff_objects = create_taiko_difficulty_objects(
        pm=pm,
        taiko_objects=taiko_objects,
        clock_rate=clock_rate,
        global_slider_velocity=global_slider_velocity,
    )

    skill_limit = max(0, n_diff_objects - 2) if passed_objects is not None else None

    skills = run_skills(
        diff_objects=diff_objects,
        great_hit_window=great_hit_window,
        is_convert=pm.is_convert,
        skill_limit=skill_limit,
    )

    result = eval_skills(
        skills=skills,
        is_convert=pm.is_convert,
        is_relax=mods.rx,
    )

    return TaikoDifficultyAttributes(
        stamina=result.stamina,
        rhythm=result.rhythm,
        color=result.color,
        reading=result.reading,
        great_hit_window=great_hit_window,
        ok_hit_window=ok_hit_window,
        mono_stamina_factor=result.mono_stamina_factor,
        mechanical_difficulty=result.mechanical_difficulty,
        consistency_factor=result.consistency_factor,
        stars=result.stars,
        max_combo=max_combo,
        is_convert=pm.is_convert,
        clock_rate=clock_rate,
        ar=adjusted.ar,
        cs=adjusted.cs,
        hp=adjusted.hp,
        od=adjusted.od,
    )