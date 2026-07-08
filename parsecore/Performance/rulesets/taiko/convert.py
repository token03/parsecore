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
from typing import TYPE_CHECKING

from ....Beatmap.utils import f32
from ...data.beatmap import (
    EffectPoint,
    PerformanceBeatmap,
    difficulty_point_at,
    effect_point_at,
    timing_point_at,
)
from ...utils import get_precision_adjusted_beat_length, ieee_div, rust_min
from ...data.hit_objects import HitObject, Slider
from .hit_objects import TaikoObject

if TYPE_CHECKING:
    from ...data.mods import PerformanceMods

VELOCITY_MULTIPLIER = float(f32(1.4))
OSU_BASE_SCORING_DIST = 100.0

_F64_EPSILON = 2.220446049250313e-16


def _as_u32(x: float) -> int:
    if math.isnan(x):
        return 0
    if x <= 0.0:
        return 0
    if x >= 4294967295.0:
        return 4294967295
    return int(x)


def _insert_effect_point(points: list[EffectPoint], ep: EffectPoint) -> None:
    lo, hi = 0, len(points)
    while lo < hi:
        mid = (lo + hi) // 2
        t = points[mid].time
        if t < ep.time:
            lo = mid + 1
        elif t > ep.time:
            hi = mid
        else:
            points[mid] = ep
            return
    points.insert(lo, ep)


def convert_to_taiko_objects(
        pm: PerformanceBeatmap,
        mods: "PerformanceMods",
) -> list[TaikoObject]:
    out: list[TaikoObject] = []
    is_convert = pm.is_convert

    last_scroll_speed = 1.0

    for h in pm.hit_objects:
        if h.is_slider():
            assert isinstance(h.kind, Slider)
            slider = h.kind

            diff_point = difficulty_point_at(pm.difficulty_points, h.start_time)
            slider_velocity = (
                diff_point.slider_velocity if diff_point is not None else 1.0
            )

            if is_convert:
                if not abs(last_scroll_speed - slider_velocity) <= _F64_EPSILON:
                    ep_curr = effect_point_at(pm.effect_points, h.start_time)
                    curr_kiai = ep_curr.kiai if ep_curr is not None else False
                    new_ep = EffectPoint.create(h.start_time, curr_kiai)
                    new_ep.scroll_speed = slider_velocity
                    last_scroll_speed = slider_velocity
                    _insert_effect_point(pm.effect_points, new_ep)

                ticks = _maybe_split_slider(pm, h, slider, slider_velocity)
                if ticks is not None:
                    for tick_time, tick_sound in ticks:
                        out.append(TaikoObject.from_hit(
                            tick_time, is_circle=True, hit_sound=tick_sound,
                        ))
                    continue

            out.append(TaikoObject.from_hit(
                h.start_time, is_circle=False, hit_sound=h.hit_sound,
            ))
        elif h.is_circle():
            out.append(TaikoObject.from_hit(
                h.start_time, is_circle=True, hit_sound=h.hit_sound,
            ))
        elif h.is_spinner() or h.is_hold_note():
            out.append(TaikoObject.from_hit(
                h.start_time, is_circle=False, hit_sound=h.hit_sound,
            ))
        else:
            out.append(TaikoObject.from_hit(
                h.start_time, is_circle=True, hit_sound=h.hit_sound,
            ))

    out.sort(key=lambda o: o.start_time)

    return out


def _maybe_split_slider(
        pm: PerformanceBeatmap,
        obj: HitObject,
        slider: Slider,
        slider_velocity: float,
) -> list[tuple[float, int]] | None:
    spans = float(slider.span_count)
    dist = slider.expected_dist if slider.expected_dist is not None else 0.0
    dist *= VELOCITY_MULTIPLIER
    dist *= spans

    timing_point = timing_point_at(pm.timing_points, obj.start_time)
    timing_beat_len = timing_point.beat_len if timing_point is not None else 1000.0

    beat_len = get_precision_adjusted_beat_length(slider_velocity, timing_beat_len)

    slider_scoring_point_dist = ieee_div(
        OSU_BASE_SCORING_DIST * (pm.slider_multiplier * VELOCITY_MULTIPLIER),
        pm.slider_tick_rate,
    )

    taiko_vel = slider_scoring_point_dist * pm.slider_tick_rate
    duration = _as_u32(ieee_div(dist, taiko_vel) * beat_len)

    osu_vel = taiko_vel * ieee_div(1000.0, beat_len)

    if pm.version >= 8:
        beat_len = timing_beat_len

    tick_spacing = rust_min(
        ieee_div(beat_len, pm.slider_tick_rate),
        ieee_div(float(duration), spans),
    )

    should_split = (
        tick_spacing > 0.0
        and ieee_div(dist, osu_vel) * 1000.0 < 2.0 * beat_len
    )
    if not should_split:
        return None

    node_sounds = slider.node_sounds or []
    edge_sound_count = max(len(node_sounds), 1)

    ticks: list[tuple[float, int]] = []
    i = 0
    j = float(obj.start_time)
    limit = obj.start_time + float(duration) + tick_spacing / 8.0
    while j <= limit:
        sound = node_sounds[i] if i < len(node_sounds) else obj.hit_sound
        ticks.append((j, int(sound)))

        if tick_spacing == 0.0:
            break

        j += tick_spacing
        i = (i + 1) % edge_sound_count

    return ticks
