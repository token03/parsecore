"""
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

import math
from dataclasses import dataclass
from typing import Any

from parsecore.Beatmap.utils import f32

from ...data.attributes import AdjustedBeatmapAttributes, as_override
from ...data.beatmap import PerformanceBeatmap
from ...data.mode import GameMode
from ...data.mods import PerformanceMods

from .convert import calculate_catch_width, convert_objects
from .hit_objects import CatchDifficultyObject, ObjectCountBuilder
from .skills import Movement

DIFFICULTY_MULTIPLIER = 4.59

@dataclass(slots=True)
class CatchDifficultyAttributes:
    stars: float = 0.0
    preempt: float = 0.0
    n_fruits: int = 0
    n_droplets: int = 0
    n_tiny_droplets: int = 0
    is_convert: bool = False
    ar: float = 0.0
    cs: float = 0.0
    hp: float = 0.0
    od: float = 0.0
    clock_rate: float = 1.0

    @property
    def max_combo(self) -> int:
        return self.n_fruits + self.n_droplets

def calculate_difficulty(
        pm: PerformanceBeatmap,
        mods: PerformanceMods,
        *,
        lazer: bool = True,
        ar_override: tuple[float, bool] | None = None,
        cs_override: tuple[float, bool] | None = None,
        hp_override: tuple[float, bool] | None = None,
        od_override: tuple[float, bool] | None = None,
        passed_objects: int | None = None,
        **_: Any,
) -> CatchDifficultyAttributes:
    if pm.mode != GameMode.CATCH:
        raise ValueError(f"cannot calculate catch difficulty for {pm.mode.name} map")

    adjusted = AdjustedBeatmapAttributes.create(
        base_cs=pm.base_cs, base_ar=pm.base_ar,
        base_od=pm.base_od, base_hp=pm.base_hp,
        mode=GameMode.CATCH, mods=mods,
        ar_override=as_override(ar_override),
        cs_override=as_override(cs_override),
        hp_override=as_override(hp_override),
        od_override=as_override(od_override),
    )

    take = passed_objects if passed_objects is not None else (1 << 62)
    clock_rate = adjusted.clock_rate
    cs = adjusted.cs

    count = ObjectCountBuilder(take)

    palpable_objects = convert_objects(
        pm, count, mods.reflection, mods.hardrock_offsets, cs,
    )

    half_catcher_width = f32(calculate_catch_width(cs) * 0.5)
    half_catcher_width = f32(
        half_catcher_width
        * f32(1.0 - f32(max(f32(cs - 5.5), 0.0) * 0.0625))
    )

    diff_objects = _create_difficulty_objects(
        clock_rate, half_catcher_width, palpable_objects[:take],
    )

    movement = Movement(clock_rate)
    for curr in diff_objects:
        movement.process(curr, diff_objects)

    stars = math.sqrt(movement.into_difficulty_value()) * DIFFICULTY_MULTIPLIER

    return CatchDifficultyAttributes(
        stars=stars,
        preempt=adjusted.hit_windows.ar or 0.0,
        n_fruits=count.fruits,
        n_droplets=count.droplets,
        n_tiny_droplets=count.tiny_droplets,
        is_convert=pm.is_convert,
        ar=adjusted.ar,
        cs=adjusted.cs,
        hp=adjusted.hp,
        od=adjusted.od,
        clock_rate=clock_rate,
    )

def _create_difficulty_objects(
        clock_rate: float,
        half_catcher_width: float,
        palpable_objects: list,
) -> list[CatchDifficultyObject]:
    if not palpable_objects:
        return []

    scaling_factor = f32(
        CatchDifficultyObject.NORMALIZED_HALF_CATCHER_WIDTH / half_catcher_width
    )

    last_object = palpable_objects[0]
    last_player_pos: float | None = None

    diff_objects: list[CatchDifficultyObject] = []
    for i, hit_object in enumerate(palpable_objects[1:]):
        diff_object = CatchDifficultyObject.new(
            hit_object, last_object, clock_rate, scaling_factor,
            last_player_pos, i,
        )
        last_object = hit_object
        last_player_pos = diff_object.player_pos
        diff_objects.append(diff_object)

    return diff_objects
