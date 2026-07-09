"""Preparation of osu! objects for calculation (stacking and mod reflection).

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
from typing import TYPE_CHECKING, Optional

from parsecore.Beatmap.section.enums import GameMode as BeatmapGameMode
from parsecore.Beatmap.utils import f32
from ...data.mods import Reflection
from .hit_objects import (
    OBJECT_RADIUS,
    OsuObject,
    OsuSlider,
    ScalingFactor,
)

if TYPE_CHECKING:
    from ...api import Difficulty
    from ...data.beatmap import PerformanceBeatmap
    from .difficulty import OsuDifficultyAttributes

_STACK_DISTANCE: float = 3.0

def prepare_beatmap(
        difficulty: "Difficulty", beatmap: "PerformanceBeatmap"
) -> "PerformanceBeatmap":
    """Convert and stack a beatmap's objects ready for the osu! calculators.

    Args:
        pm: The performance beatmap.
        mods: The mods and clock rate.

    Returns:
        The prepared osu! objects.
    """
    return beatmap

def convert_objects(
        beatmap: "PerformanceBeatmap",
        scaling_factor: ScalingFactor,
        reflection: Reflection,
        time_preempt: float,
        take: int,
        attrs: "OsuDifficultyAttributes",
) -> list[OsuObject]:
    """Build osu! objects from the beatmap and apply mod reflections."""
    osu_objects = [OsuObject.new(h, beatmap, reflection) for h in beatmap.hit_objects]

    for obj in osu_objects[: max(take, 0)]:
        attrs.max_combo += 1
        if obj.is_slider():
            attrs.n_sliders += 1
            slider = obj.kind
            assert isinstance(slider, OsuSlider)
            attrs.n_large_ticks += slider.large_tick_count()
            attrs.max_combo += len(slider.nested_objects)
        elif obj.is_spinner():
            attrs.n_spinners += 1
        else:
            attrs.n_circles += 1

    if reflection == Reflection.VERTICAL:
        for obj in osu_objects:
            obj.reflect_vertically()
    elif reflection == Reflection.HORIZONTAL:
        for obj in osu_objects:
            obj.reflect_horizontally()
    elif reflection == Reflection.BOTH:
        for obj in osu_objects:
            obj.reflect_both_axes()
    else:
        for obj in osu_objects:
            obj.finalize_nested()

    stack_leniency = f32(getattr(beatmap, "stack_leniency", 0.7))
    stack_threshold = time_preempt * stack_leniency

    if beatmap.version >= 6:
        _new_stacking(osu_objects, stack_threshold)
    else:
        _old_stacking(osu_objects, stack_threshold)

    for obj in osu_objects:
        obj.stack_offset = scaling_factor.stack_offset(obj.stack_height)

    return osu_objects

def _new_stacking(hit_objects: list[OsuObject], stack_threshold: float) -> None:
    """Apply osu!lazer's stacking algorithm (format v6+)."""
    if not hit_objects:
        return

    extended_start_idx = 0
    extended_end_idx = len(hit_objects) - 1

    for i in range(extended_end_idx, 0, -1):
        n = i
        obj_i_idx = i


        if hit_objects[obj_i_idx].stack_height != 0 or hit_objects[obj_i_idx].is_spinner():
            continue

        if hit_objects[obj_i_idx].is_circle():
            while n > 0:
                n -= 1

                if hit_objects[n].is_spinner():
                    continue

                if (
                        hit_objects[obj_i_idx].start_time - hit_objects[n].end_time()
                        > stack_threshold
                ):
                    break

                if n < extended_start_idx:
                    hit_objects[n].stack_height = 0
                    extended_start_idx = n

                if (
                        hit_objects[n].is_slider()
                        and hit_objects[n].end_pos().distance(hit_objects[obj_i_idx].pos)
                        < _STACK_DISTANCE
                ):
                    offset = (
                            hit_objects[obj_i_idx].stack_height
                            - hit_objects[n].stack_height
                            + 1
                    )
                    for j in range(n + 1, i + 1):
                        if (
                                hit_objects[n].end_pos().distance(hit_objects[j].pos)
                                < _STACK_DISTANCE
                        ):
                            hit_objects[j].stack_height -= offset

                    break

                if (
                        hit_objects[n].pos.distance(hit_objects[obj_i_idx].pos)
                        < _STACK_DISTANCE
                ):
                    hit_objects[n].stack_height = hit_objects[obj_i_idx].stack_height + 1
                    obj_i_idx = n

        elif hit_objects[obj_i_idx].is_slider():
            while n > 0:
                n -= 1

                if hit_objects[n].is_spinner():
                    continue

                if (
                        hit_objects[obj_i_idx].start_time - hit_objects[n].start_time
                        > stack_threshold
                ):
                    break

                if (
                        hit_objects[n].end_pos().distance(hit_objects[obj_i_idx].pos)
                        < _STACK_DISTANCE
                ):
                    hit_objects[n].stack_height = hit_objects[obj_i_idx].stack_height + 1
                    obj_i_idx = n

def _old_stacking(hit_objects: list[OsuObject], stack_threshold: float) -> None:
    """Apply osu!-stable's legacy stacking algorithm (pre-v6)."""
    for i in range(len(hit_objects)):
        h_i = hit_objects[i]
        if h_i.stack_height != 0 and not h_i.is_slider():
            continue

        start_time = h_i.end_time()

        if isinstance(h_i.kind, OsuSlider):
            slider = h_i.kind
            if slider.repeat_count() % 2 == 0:
                nested = slider.tail()
            else:
                nested = next(
                    (nst for nst in slider.nested_objects if nst.is_repeat()), None
                )
            pos2 = nested.pos if nested is not None else h_i.pos
        else:
            pos2 = h_i.pos

        slider_stack = 0

        for j in range(i + 1, len(hit_objects)):
            if hit_objects[j].start_time - stack_threshold > start_time:
                break

            if hit_objects[j].pos.distance(h_i.pos) < _STACK_DISTANCE:
                h_i.stack_height += 1
                start_time = hit_objects[j].start_time
            elif hit_objects[j].pos.distance(pos2) < _STACK_DISTANCE:
                slider_stack += 1
                hit_objects[j].stack_height -= slider_stack
                start_time = hit_objects[j].start_time