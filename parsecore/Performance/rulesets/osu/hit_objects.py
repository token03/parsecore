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
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

from parsecore.Beatmap.utils import Pos, f32
from parsecore.Beatmap.section.enums import GameMode as BeatmapGameMode
from parsecore.Beatmap.section.hit_objects.slider import (
    Curve, SliderEventType, generate_slider_events,
)

from ...data.beatmap import (
    DifficultyPoint, TimingPoint,
    difficulty_point_at, timing_point_at,
)
from ...data.hit_objects import HitObject, HoldNote, Slider, Spinner
from ...data.mods import Reflection
from ...utils import (
    _interpolate_curve_position,
    csharp_sort_unstable,
    get_precision_adjusted_beat_length,
    reverse_lerp,
)

if TYPE_CHECKING:
    from ...data.beatmap import PerformanceBeatmap

PLAYFIELD_BASE_SIZE_X: float = 512.0
PLAYFIELD_BASE_SIZE_Y: float = 384.0
OBJECT_RADIUS: float = 64.0
PREEMPT_MIN: float = 450.0

_BASE_SCORING_DIST: float = 100.0

class NestedSliderObjectKind(Enum):
    TICK = "tick"
    REPEAT = "repeat"
    TAIL = "tail"

@dataclass(slots=True)
class NestedSliderObject:
    pos: Pos
    start_time: float
    kind: NestedSliderObjectKind

    def is_tick(self) -> bool:
        return self.kind == NestedSliderObjectKind.TICK

    def is_repeat(self) -> bool:
        return self.kind == NestedSliderObjectKind.REPEAT

    def is_tail(self) -> bool:
        return self.kind == NestedSliderObjectKind.TAIL

@dataclass(slots=True)
class OsuSlider:
    end_time: float
    span_count: float
    path: object
    nested_objects: list[NestedSliderObject] = field(default_factory=list)

    def repeat_count(self) -> int:
        return sum(1 for n in self.nested_objects if n.is_repeat())

    def tick_count(self) -> int:
        return sum(1 for n in self.nested_objects if n.is_tick())

    def large_tick_count(self) -> int:
        return sum(
            1 for n in self.nested_objects if n.is_tick() or n.is_repeat()
        )

    def tail(self) -> Optional[NestedSliderObject]:
        for n in reversed(self.nested_objects):
            if n.is_tail():
                return n
        return None

@dataclass(slots=True)
class OsuObject:
    pos: Pos
    start_time: float
    kind: Optional[object] = None
    stack_height: int = 0
    stack_offset: Pos = field(default_factory=lambda: Pos(0.0, 0.0))

    @classmethod
    def new(
            cls,
            h: HitObject,
            beatmap: "PerformanceBeatmap",
            reflection: Reflection,
    ) -> "OsuObject":
        kind: Optional[object]

        if isinstance(h.kind, Slider):
            kind = _build_osu_slider(h, h.kind, beatmap, reflection)
        elif isinstance(h.kind, Spinner):
            kind = h.kind
        elif isinstance(h.kind, HoldNote):
            kind = Spinner(duration=h.kind.duration)
        else:
            kind = None

        return cls(pos=Pos(h.pos.x, h.pos.y), start_time=h.start_time, kind=kind)

    def is_circle(self) -> bool:
        return self.kind is None

    def is_slider(self) -> bool:
        return isinstance(self.kind, OsuSlider)

    def is_spinner(self) -> bool:
        return isinstance(self.kind, Spinner)

    def end_time(self) -> float:
        if isinstance(self.kind, OsuSlider):
            return self.kind.end_time
        if isinstance(self.kind, Spinner):
            return self.start_time + self.kind.duration
        return self.start_time

    def stacked_pos(self) -> Pos:
        return Pos(self.pos.x + self.stack_offset.x, self.pos.y + self.stack_offset.y)

    def end_pos(self) -> Pos:
        if isinstance(self.kind, OsuSlider):
            t = self.kind.tail()
            return t.pos if t is not None else Pos(0.0, 0.0)
        return self.pos

    def stacked_end_pos(self) -> Pos:
        ep = self.end_pos()
        return Pos(ep.x + self.stack_offset.x, ep.y + self.stack_offset.y)

    def reflect_vertically(self) -> None:
        self.pos = Pos(self.pos.x, PLAYFIELD_BASE_SIZE_Y - self.pos.y)
        self.finalize_nested()

    def reflect_horizontally(self) -> None:
        self.pos = Pos(PLAYFIELD_BASE_SIZE_X - self.pos.x, self.pos.y)
        self.finalize_nested()

    def reflect_both_axes(self) -> None:
        self.pos = Pos(
            PLAYFIELD_BASE_SIZE_X - self.pos.x,
            PLAYFIELD_BASE_SIZE_Y - self.pos.y,
            )
        self.finalize_nested()

    def finalize_nested(self) -> None:
        if isinstance(self.kind, OsuSlider):
            for nested in self.kind.nested_objects:
                nested.pos = Pos(self.pos.x + nested.pos.x, self.pos.y + nested.pos.y)

def _build_osu_slider(
        h: HitObject,
        slider: Slider,
        beatmap: "PerformanceBeatmap",
        reflection: Reflection,
) -> OsuSlider:
    start_time = h.start_time
    slider_multiplier = beatmap.slider_multiplier
    slider_tick_rate = beatmap.slider_tick_rate

    tp = timing_point_at(beatmap.timing_points, start_time)
    beat_len = tp.beat_len if tp is not None else 1000.0

    dp = difficulty_point_at(beatmap.difficulty_points, start_time)
    if dp is not None:
        slider_velocity = dp.slider_velocity
        generate_ticks = dp.generate_ticks
    else:
        slider_velocity = 1.0
        generate_ticks = True

    try:
        path = Curve(BeatmapGameMode.Osu, slider.control_points, slider.expected_dist)
    except Exception:
        path = None

    span_count = float(slider.span_count)

    if path is None or path.dist() <= 0.0:
        return OsuSlider(
            end_time=start_time, span_count=span_count, path=path,
            nested_objects=[],
        )

    if reflection != Reflection.NONE:
        path = _reflect_curve(path, reflection, slider)

    velocity = (
            _BASE_SCORING_DIST * slider_multiplier
            / get_precision_adjusted_beat_length(slider_velocity, beat_len)
    )
    scoring_dist = velocity * beat_len

    end_time = start_time + span_count * path.dist() / velocity
    duration = end_time - start_time
    span_duration = duration / span_count if span_count > 0 else duration

    if beatmap.version < 8:
        tick_dist_multiplier = 1.0 / slider_velocity if slider_velocity != 0 else 1.0
    else:
        tick_dist_multiplier = 1.0

    if generate_ticks:
        tick_dist = scoring_dist / slider_tick_rate * tick_dist_multiplier
    else:
        tick_dist = math.inf

    events = list(generate_slider_events(
        start_time=start_time,
        span_duration=span_duration,
        velocity=velocity,
        tick_dist=tick_dist,
        total_dist=path.dist(),
        span_count=int(span_count),
    ))

    def _span_at(progress: float) -> int:
        return int(progress * span_count)

    def _obj_progress_at(progress: float) -> float:
        p = (progress * span_count) % 1.0
        return 1.0 - p if _span_at(progress) % 2 == 1 else p

    end_path_pos = _interpolate_curve_position(path, _obj_progress_at(1.0))
    if end_path_pos is None:
        end_path_pos = Pos(0.0, 0.0)

    nested: list[NestedSliderObject] = []
    for e in events:
        if e.kind == SliderEventType.Tick:
            pos = _interpolate_curve_position(path, e.path_progress)
            if pos is not None:
                nested.append(NestedSliderObject(
                    pos=Pos(pos.x, pos.y),
                    start_time=e.time,
                    kind=NestedSliderObjectKind.TICK,
                ))
        elif e.kind == SliderEventType.Repeat:
            pos = _interpolate_curve_position(path, e.path_progress)
            if pos is not None:
                nested.append(NestedSliderObject(
                    pos=Pos(pos.x, pos.y),
                    start_time=start_time + (e.span_idx + 1) * span_duration,
                    kind=NestedSliderObjectKind.REPEAT,
                ))
        elif e.kind == SliderEventType.Tail:
            nested.append(NestedSliderObject(
                pos=Pos(end_path_pos.x, end_path_pos.y),
                start_time=e.time,
                kind=NestedSliderObjectKind.TAIL,
            ))

    csharp_sort_unstable(nested, key=lambda n: n.start_time)

    return OsuSlider(
        end_time=end_time,
        span_count=span_count,
        path=path,
        nested_objects=nested,
    )

def _reflect_curve(curve, reflection: Reflection, slider: Slider):
    import copy as _copy

    def transform(p: Pos) -> Pos:
        if reflection == Reflection.VERTICAL:
            return Pos(p.x, -p.y)
        if reflection == Reflection.HORIZONTAL:
            return Pos(-p.x, p.y)
        if reflection == Reflection.BOTH:
            return Pos(-p.x, -p.y)
        return p

    new_points = []
    for cp in slider.control_points:
        new_cp = _copy.copy(cp)
        new_cp.pos = transform(cp.pos)
        new_points.append(new_cp)

    try:
        return Curve(BeatmapGameMode.Osu, new_points, slider.expected_dist)
    except Exception:
        return curve

_BROKEN_GAMEFIELD_ROUNDING_ALLOWANCE: float = 1.00041

@dataclass(slots=True)
class ScalingFactor:
    factor: float
    radius: float
    scale: float

    @classmethod
    def new(cls, cs: float) -> "ScalingFactor":
        cs = f32(cs)
        diff_range_value = (cs - 5.0) / 5.0
        inner = 1.0 - f32(0.7) * diff_range_value
        scale = f32(f32(f32(inner) / 2.0) * f32(_BROKEN_GAMEFIELD_ROUNDING_ALLOWANCE))
        radius = f32(OBJECT_RADIUS * scale)
        factor = f32(_OSU_DIFF_NORMALIZED_RADIUS / f32(radius)) if radius != 0 else math.inf
        return cls(factor=factor, radius=radius, scale=scale)

    def stack_offset(self, stack_height: int) -> Pos:
        offset = f32(f32(float(stack_height) * self.scale) * f32(-6.4))
        return Pos(offset, offset)

_OSU_DIFF_NORMALIZED_RADIUS: float = 50.0
_OSU_DIFF_NORMALIZED_DIAMETER: float = 100.0
_OSU_DIFF_MIN_DELTA_TIME: float = 25.0
_OSU_DIFF_MAX_SLIDER_RADIUS: float = float(f32(50.0 * f32(2.4)))
_OSU_DIFF_ASSUMED_SLIDER_RADIUS: float = float(f32(50.0 * f32(1.8)))

_HD_FADE_OUT_DURATION_MULTIPLIER: float = 0.3

@dataclass(slots=True)
class OsuDifficultyObject:
    idx: int = 0
    base: OsuObject = field(default_factory=lambda: OsuObject(Pos(0.0, 0.0), 0.0))
    start_time: float = 0.0
    delta_time: float = 0.0
    adjusted_delta_time: float = 0.0
    last_object_end_delta_time: float = 0.0

    jump_dist: float = 0.0
    lazy_jump_dist: float = 0.0
    min_jump_dist: float = 0.0
    min_jump_time: float = 0.0
    travel_dist: float = 0.0
    travel_time: float = 0.0
    lazy_end_pos: Optional[Pos] = None
    lazy_travel_dist: float = 0.0
    lazy_travel_time: float = 0.0
    angle: Optional[float] = None
    normalised_vector_angle: Optional[float] = None
    small_circle_bonus: float = 1.0

    @classmethod
    def new(
            cls,
            hit_object: OsuObject,
            last_object: OsuObject,
            last_diff_obj: Optional["OsuDifficultyObject"],
            last_last_diff_obj: Optional["OsuDifficultyObject"],
            clock_rate: float,
            idx: int,
            scaling_factor: ScalingFactor,
    ) -> "OsuDifficultyObject":
        delta_time = (hit_object.start_time - last_object.start_time) / clock_rate
        start_time = hit_object.start_time / clock_rate
        strain_time = max(delta_time, _OSU_DIFF_MIN_DELTA_TIME)
        small_circle_bonus = max(1.0, 1.0 + (30.0 - scaling_factor.radius) / 70.0)

        if last_diff_obj is not None:
            last_end = last_object.end_time() / clock_rate
            last_object_end_delta_time = max(
                start_time - last_end, _OSU_DIFF_MIN_DELTA_TIME
            )
        else:
            last_object_end_delta_time = strain_time

        obj = cls(
            idx=idx,
            base=hit_object,
            start_time=start_time,
            delta_time=delta_time,
            adjusted_delta_time=strain_time,
            last_object_end_delta_time=last_object_end_delta_time,
            small_circle_bonus=small_circle_bonus,
        )
        obj._compute_slider_cursor_pos(scaling_factor.radius)
        obj._set_distances(
            last_object, last_diff_obj, last_last_diff_obj, clock_rate, scaling_factor
        )
        return obj

    def _set_distances(
            self,
            last_object: OsuObject,
            last_diff_obj: Optional["OsuDifficultyObject"],
            last_last_diff_obj: Optional["OsuDifficultyObject"],
            clock_rate: float,
            scaling_factor: ScalingFactor,
    ) -> None:
        if isinstance(self.base.kind, OsuSlider):
            slider = self.base.kind
            self.travel_dist = self.lazy_travel_dist * max(
                1.0, math.pow(slider.repeat_count(), 0.3)
            )
            self.travel_time = max(
                self.lazy_travel_time / clock_rate, _OSU_DIFF_MIN_DELTA_TIME
            )

        self.min_jump_time = self.adjusted_delta_time

        if self.base.is_spinner() or last_object.is_spinner():
            return

        sf = scaling_factor.factor

        if last_diff_obj is not None:
            last_cursor_pos = self._get_end_cursor_pos(last_diff_obj)
        else:
            last_cursor_pos = last_object.stacked_pos()

        a = self.base.stacked_pos()
        self.jump_dist = float(f32((last_object.stacked_pos() - a).length() * sf))
        self.lazy_jump_dist = float(f32((a - last_cursor_pos).length() * sf))
        self.min_jump_dist = self.lazy_jump_dist

        if last_diff_obj is None:
            return

        if isinstance(last_object.kind, OsuSlider):
            last_slider = last_object.kind
            last_travel_time = max(
                last_diff_obj.lazy_travel_time / clock_rate,
                _OSU_DIFF_MIN_DELTA_TIME,
                )
            self.min_jump_time = max(
                self.adjusted_delta_time - last_travel_time,
                _OSU_DIFF_MIN_DELTA_TIME,
                )

            tail = last_slider.tail()
            tail_pos = tail.pos if tail is not None else last_object.pos
            stacked_tail_pos = Pos(
                tail_pos.x + last_object.stack_offset.x,
                tail_pos.y + last_object.stack_offset.y,
                )
            sp = self.base.stacked_pos()
            tail_jump_dist = f32(f32((stacked_tail_pos - sp).length()) * sf)

            diff = float(f32(
                _OSU_DIFF_MAX_SLIDER_RADIUS - _OSU_DIFF_ASSUMED_SLIDER_RADIUS
            ))
            mn = float(f32(tail_jump_dist - _OSU_DIFF_MAX_SLIDER_RADIUS))
            self.min_jump_dist = max(min(self.lazy_jump_dist - diff, mn), 0.0)

        if last_last_diff_obj is None or last_last_diff_obj.base.is_spinner():
            return

        cur = self.base.stacked_pos()

        last_cursor_for_angle = last_cursor_pos
        if (
            isinstance(last_diff_obj.base.kind, OsuSlider)
            and last_diff_obj.travel_dist > 0
        ):
            last_cursor_for_angle = last_diff_obj.base.stacked_pos()

        last_last_cursor_pos = self._get_end_cursor_pos(last_last_diff_obj)

        angle = self._calculate_angle(cur, last_cursor_for_angle, last_last_cursor_pos)
        slider_angle = self._calculate_slider_angle(
            last_diff_obj, last_last_cursor_pos, cur
        )

        v = cur - last_cursor_for_angle
        self.normalised_vector_angle = math.atan2(abs(v.y), abs(v.x))
        self.angle = min(angle, slider_angle)

    @staticmethod
    def _calculate_angle(current: Pos, last: Pos, last_last: Pos) -> float:
        v1 = last_last - last
        v2 = current - last
        dot = v1.dot(v2)
        det = f32(f32(v1.x * v2.y) - f32(v1.y * v2.x))
        return abs(math.atan2(det, dot))

    def _calculate_slider_angle(
        self,
        last_diff_obj: "OsuDifficultyObject",
        last_last_cursor_pos: Pos,
        cur: Pos,
    ) -> float:
        last_cursor_pos = self._get_end_cursor_pos(last_diff_obj)
        if (
            isinstance(last_diff_obj.base.kind, OsuSlider)
            and last_diff_obj.travel_dist > 0
        ):
            nested = last_diff_obj.base.kind.nested_objects
            so = last_diff_obj.base.stack_offset
            if len(nested) >= 2:
                second_last = nested[-2]
                last_last_cursor_pos = Pos(
                    second_last.pos.x + so.x, second_last.pos.y + so.y
                )
            else:
                last_last_cursor_pos = last_diff_obj.base.stacked_pos()
        return self._calculate_angle(cur, last_cursor_pos, last_last_cursor_pos)

    def _compute_slider_cursor_pos(self, radius: float) -> None:
        TAIL_LENIENCY = -36.0

        if not isinstance(self.base.kind, OsuSlider):
            return
        slider = self.base.kind

        if self.lazy_end_pos is not None:
            return

        pos = self.base.pos
        stack_offset = self.base.stack_offset
        start_time = self.base.start_time
        duration = slider.end_time - start_time

        nested = list(slider.nested_objects)
        tracking_end_time = max(
            start_time + duration + TAIL_LENIENCY,
            start_time + duration / 2.0,
            )

        last_real_tick_idx = -1
        for i, n in enumerate(nested):
            if n.is_tick():
                last_real_tick_idx = i

        if last_real_tick_idx >= 0:
            last_real_tick = nested[last_real_tick_idx]
            if last_real_tick.start_time > tracking_end_time:
                tracking_end_time = last_real_tick.start_time
                tail_slice = nested[last_real_tick_idx:]
                tail_slice = tail_slice[1:] + tail_slice[:1]
                nested = nested[:last_real_tick_idx] + tail_slice

        self.lazy_travel_time = tracking_end_time - start_time

        span_duration = (
            duration / slider.span_count if slider.span_count > 0 else duration
        )
        end_time_min = (
            self.lazy_travel_time / span_duration if span_duration > 0 else 0.0
        )

        if end_time_min % 2.0 >= 1.0:
            end_time_min = 1.0 - (end_time_min % 1.0)
        else:
            end_time_min = end_time_min % 1.0

        end_pos = _interpolate_curve_position(slider.path, end_time_min)
        if end_pos is None:
            end_pos = Pos(0.0, 0.0)
        lazy_end_pos = pos + stack_offset + end_pos

        curr_cursor_pos = pos + stack_offset
        sf = _OSU_DIFF_NORMALIZED_RADIUS / radius if radius > 0 else 0.0

        n_nested = len(nested)
        nested_stack_offset = Pos(stack_offset.x, stack_offset.y)
        for i, nobj in enumerate(nested, start=1):
            curr_movement = nobj.pos + nested_stack_offset - curr_cursor_pos
            curr_movement_len = sf * float(curr_movement.length())
            required_movement = _OSU_DIFF_ASSUMED_SLIDER_RADIUS

            is_last = i == n_nested

            if is_last:
                lazy_movement = lazy_end_pos - curr_cursor_pos
                if lazy_movement.length() < curr_movement.length():
                    curr_movement = lazy_movement
                curr_movement_len = sf * float(curr_movement.length())
            elif nobj.is_repeat():
                required_movement = _OSU_DIFF_NORMALIZED_RADIUS

            if curr_movement_len > required_movement:
                fraction = (
                                   curr_movement_len - required_movement
                           ) / curr_movement_len
                curr_cursor_pos = curr_cursor_pos + curr_movement * fraction
                curr_movement_len *= fraction
                self.lazy_travel_dist += curr_movement_len

            if is_last:
                lazy_end_pos = curr_cursor_pos

        self.lazy_end_pos = lazy_end_pos

    @staticmethod
    def _get_end_cursor_pos(hit_object: "OsuDifficultyObject") -> Pos:
        if hit_object.lazy_end_pos is not None:
            return hit_object.lazy_end_pos
        return hit_object.base.stacked_pos()

    def opacity_at(
            self,
            time: float,
            hidden: bool,
            time_preempt: float,
            time_fade_in: float,
    ) -> float:
        if time > self.base.start_time:
            return 0.0
        fade_in_start_time = self.base.start_time - time_preempt
        fade_in_duration = 400.0 * min(1.0, time_preempt / PREEMPT_MIN)

        if hidden:
            fade_out_start_time = (
                    self.base.start_time - time_preempt + time_fade_in
            )
            fade_out_duration = time_preempt * _HD_FADE_OUT_DURATION_MULTIPLIER
            fi = (
                (time - fade_in_start_time) / fade_in_duration
                if fade_in_duration > 0 else 0.0
            )
            fade_in_val = max(0.0, min(1.0, fi))
            fo = (
                (time - fade_out_start_time) / fade_out_duration
                if fade_out_duration > 0 else 0.0
            )
            fade_out_val = 1.0 - max(0.0, min(1.0, fo))
            return min(fade_in_val, fade_out_val)
        else:
            fi = (
                (time - fade_in_start_time) / fade_in_duration
                if fade_in_duration > 0 else 0.0
            )
            return max(0.0, min(1.0, fi))

    def get_doubletapness(
            self,
            next_obj: Optional["OsuDifficultyObject"],
            hit_window: float,
    ) -> float:
        if next_obj is None:
            return 0.0
        if self.base.is_spinner():
            hit_window = 0.0
        curr_delta_time = max(self.delta_time, 1.0)
        next_delta_time = max(next_obj.delta_time, 1.0)
        delta_diff = abs(next_delta_time - curr_delta_time)
        speed_ratio = curr_delta_time / max(curr_delta_time, delta_diff)
        if hit_window <= 0:
            window_ratio = 1.0
        else:
            window_ratio = min(curr_delta_time / hit_window, 1.0) ** 2.0
        return 1.0 - speed_ratio ** (1.0 - window_ratio)

    def calculate_double_tap_feasibility(
            self,
            next_obj: Optional["OsuDifficultyObject"],
            hit_window_great: float,
    ) -> float:
        if next_obj is None:
            return 0.0
        curr_delta_time = max(self.delta_time, 1.0)
        next_delta_time = max(next_obj.delta_time, 1.0)
        delta_difference = abs(next_delta_time - curr_delta_time)
        speed_ratio = curr_delta_time / max(curr_delta_time, delta_difference)
        wr = min(1.0, curr_delta_time / hit_window_great)
        window_ratio = wr * wr * wr * wr * wr
        rl = reverse_lerp(self.lazy_jump_dist, 100.0, 50.0)
        distance_factor = rl * rl
        return 1.0 - math.pow(speed_ratio, distance_factor * (1.0 - window_ratio))

@dataclass(slots=True)
class OsuDifficultyObjects:

    objects: list[OsuDifficultyObject] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.objects)

    def __getitem__(self, idx: int) -> OsuDifficultyObject:
        return self.objects[idx]

    def previous(
            self, curr: OsuDifficultyObject, backwards_idx: int
    ) -> Optional[OsuDifficultyObject]:
        target = curr.idx - backwards_idx - 1
        if 0 <= target < len(self.objects):
            return self.objects[target]
        return None

    def next(
            self, curr: OsuDifficultyObject, forwards_idx: int
    ) -> Optional[OsuDifficultyObject]:
        target = curr.idx + forwards_idx + 1
        if 0 <= target < len(self.objects):
            return self.objects[target]
        return None