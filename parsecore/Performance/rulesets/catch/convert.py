"""Conversion of parsed objects into osu!catch fruits, droplets and juice streams.

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

from parsecore.Beatmap.utils import F32_EPSILON, f32

from ...data.beatmap import PerformanceBeatmap
from ...data.hit_objects import HoldNote, Slider, Spinner
from ...data.mods import Reflection
from ...utils import OsuRandom, clamp, cmp_key

from .hit_objects import (
    NestedKind,
    ObjectCountBuilder,
    PalpableObject,
    banana_count,
    build_juice_stream,
)

RNG_SEED = 1337

PLAYFIELD_WIDTH = 512.0

_AREA_CATCHER_SIZE = 106.75
_ALLOWED_CATCH_RANGE = 0.8
BASE_SPEED = 1.0

_F32_0_7 = float(f32(0.7))
_F32_0_8 = float(f32(0.8))
_F32_TIME_OFFSET = f32(f32(1000.0 / 60.0) / 4.0)

def calculate_catch_width(cs: float) -> float:
    """Return the catcher width for a circle size.

    Args:
        cs: The circle size.

    Returns:
        The catcher width in osu! pixels.
    """
    return _catch_width_by_scale(_calculate_scale(cs))

def _catch_width_by_scale(scale: float) -> float:
    """Return the catcher width for a given catcher scale."""
    return f32(f32(_AREA_CATCHER_SIZE * abs(scale)) * _F32_0_8)

def _calculate_scale(cs: float) -> float:
    """Return the catcher scale for a circle size (f32-faithful)."""
    inner = 1.0 - _F32_0_7 * ((cs - 5.0) / 5.0)
    return f32(f32(f32(f32(inner) / 2.0) * 1.0) * 2.0)

def convert_objects(
        beatmap: PerformanceBeatmap,
        count: ObjectCountBuilder,
        reflection: Reflection,
        hr_offsets: bool,
        cs: float,
) -> list[PalpableObject]:
    """Convert a beatmap's objects into catch palpable objects.

    Args:
        beatmap: The performance beatmap.
        count: The object-count builder to record fruits/droplets into.
        reflection: How Hard Rock reflects object positions.
        hr_offsets: Whether Hard Rock position offsets are applied.
        cs: The circle size.

    Returns:
        The generated palpable objects in time order.
    """
    palpable_objects: list[PalpableObject] = []

    rng = OsuRandom(RNG_SEED)
    hr_state: list = [None, 0.0]

    for h in beatmap.hit_objects:
        kind = h.kind

        if kind is None:
            count.record_fruit()
            x_offset = 0.0

            if hr_offsets:
                x_offset = _apply_hr_offset(
                    h.pos.x, x_offset, h.start_time, hr_state, rng,
                )

            palpable_objects.append(
                PalpableObject(h.pos.x, x_offset, h.start_time)
            )
        elif isinstance(kind, Slider):
            effective_x = clamp(h.pos.x, 0.0, PLAYFIELD_WIDTH)
            stream = build_juice_stream(
                effective_x, h.start_time, kind, beatmap, count,
            )

            last_cp_x = (
                stream.control_points[-1].pos.x if stream.control_points else 0.0
            )
            hr_state[0] = f32(h.pos.x + last_cp_x)
            hr_state[1] = h.start_time

            for nested in stream.nested_objects:
                if nested.kind in (NestedKind.DROPLET, NestedKind.TINY_DROPLET):
                    rng.next_int()

            for nested in stream.nested_objects:
                if nested.kind != NestedKind.TINY_DROPLET:
                    palpable_objects.append(
                        PalpableObject(nested.pos, 0.0, nested.start_time)
                    )
        elif isinstance(kind, (Spinner, HoldNote)):
            for _ in range(banana_count(h.start_time, h.start_time + kind.duration)):
                rng.next_double()
                rng.next_int()
                rng.next_int()
                rng.next_int()

    if reflection == Reflection.HORIZONTAL:
        for obj in palpable_objects:
            obj.x = f32(PLAYFIELD_WIDTH - obj.x)
            obj.x_offset = -obj.x_offset

    palpable_objects.sort(key=lambda o: cmp_key(o.start_time))
    _initialize_hyper_dash(cs, palpable_objects)

    return palpable_objects

def _apply_hr_offset(
        x: float,
        x_offset: float,
        start_time: float,
        hr_state: list,
        rng: OsuRandom,
) -> float:
    """Apply the Hard Rock horizontal position offset to a fruit."""
    offset_pos = x

    last_pos = hr_state[0]
    if last_pos is None or abs(last_pos) < F32_EPSILON:
        hr_state[0] = offset_pos
        hr_state[1] = start_time
        return x_offset

    pos_diff = f32(offset_pos - last_pos)
    time_diff = int(start_time - hr_state[1])

    if time_diff > 1000:
        hr_state[0] = offset_pos
        hr_state[1] = start_time
        return x_offset

    if abs(f32(pos_diff - 0.0)) <= F32_EPSILON:
        offset_pos = _apply_random_offset(offset_pos, float(time_diff) / 4.0, rng)
        return f32(offset_pos - x)

    if abs(pos_diff) < float(f32(int(time_diff / 3))):
        offset_pos = _apply_offset(offset_pos, pos_diff)

    x_offset = f32(offset_pos - x)

    hr_state[0] = offset_pos
    hr_state[1] = start_time
    return x_offset

def _apply_random_offset(pos: float, max_offset: float, rng: OsuRandom) -> float:
    """Apply a legacy-RNG horizontal jitter to a droplet position."""
    right = rng.next_bool()
    rand = min(f32(rng.next_double_range(0.0, max(max_offset, 0.0))), 20.0)

    if right:
        if f32(pos + rand) <= PLAYFIELD_WIDTH:
            pos = f32(pos + rand)
        else:
            pos = f32(pos - rand)
    elif f32(pos - rand) >= 0.0:
        pos = f32(pos - rand)
    else:
        pos = f32(pos + rand)

    return pos

def _apply_offset(pos: float, amount: float) -> float:
    """Shift a position horizontally, clamped to the playfield."""
    if amount > 0.0:
        if f32(pos + amount) < PLAYFIELD_WIDTH:
            pos = f32(pos + amount)
    elif f32(pos + amount) > 0.0:
        pos = f32(pos + amount)

    return pos

def _initialize_hyper_dash(cs: float, palpable_objects: list[PalpableObject]) -> None:
    """Mark objects requiring a hyperdash and record the needed dash distance."""
    half_catcher_width = float(f32(calculate_catch_width(cs) / 2.0))
    half_catcher_width /= _F32_0_8

    last_dir = 0
    last_excess = half_catcher_width

    for i in range(max(0, len(palpable_objects) - 1)):
        nxt = palpable_objects[i + 1]
        curr = palpable_objects[i]

        this_dir = 1 if nxt.effective_x() > curr.effective_x() else -1

        time_to_next = float(f32(
            f32(int(nxt.start_time) - int(curr.start_time)) - _F32_TIME_OFFSET
        ))

        dist_to_next = float(f32(abs(f32(nxt.effective_x() - curr.effective_x())))) - (
            last_excess if last_dir == this_dir else half_catcher_width
        )

        dist_to_hyper = f32(time_to_next * BASE_SPEED - dist_to_next)

        if dist_to_hyper < 0.0:
            curr.hyper_dash = True
            last_excess = half_catcher_width
        else:
            curr.dist_to_hyper_dash = dist_to_hyper
            last_excess = clamp(float(dist_to_hyper), 0.0, half_catcher_width)

        last_dir = this_dir
