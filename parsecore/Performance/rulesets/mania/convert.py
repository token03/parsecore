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

osu! -> mania conversion is a faithful port of rosu-pp 27a6724
`src/mania/convert/` (itself a port of osu!stable's legacy pattern
generator), including the legacy osu! RNG consumption order.
"""

from __future__ import annotations

import math
from collections import deque
from typing import TYPE_CHECKING, Callable, Optional

from ....Beatmap.utils import f32
from ...data.beatmap import (
    PerformanceBeatmap,
    difficulty_point_at,
    effect_point_at,
    timing_point_at,
)
from ...data.hit_objects import HitObject, HoldNote, Slider, Spinner
from ...utils import OsuRandom, get_precision_adjusted_beat_length
from .hit_objects import ManiaObject, column_for_x

if TYPE_CHECKING:
    from ...data.mods import PerformanceMods

BASE_SCORING_DIST = 100.0

_MAX_NOTES_FOR_DENSITY = 7
_I32_MAX = 2147483647

_WHISTLE = 1 << 1
_FINISH = 1 << 2
_CLAP = 1 << 3

_FORCE_STACK = 1 << 0
_FORCE_NOT_STACK = 1 << 1
_KEEP_SINGLE = 1 << 2
_LOW_PROBABILITY = 1 << 3
_GATHERED = 1 << 7
_MIRROR = 1 << 8
_REVERSE = 1 << 9
_CYCLE = 1 << 10
_STAIR = 1 << 11
_REVERSE_STAIR = 1 << 12


def _rte_i32(v: float) -> int:
    if math.isnan(v):
        return 0
    r = round(v)
    if r <= -2147483648:
        return -2147483648
    if r >= _I32_MAX:
        return _I32_MAX
    return int(r)


def _as_i32(v: float) -> int:
    if math.isnan(v):
        return 0
    if v <= -2147483648.0:
        return -2147483648
    if v >= 2147483647.0:
        return 2147483647
    return int(v)


def _i32_div(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


class _CObj:

    __slots__ = ("start_time", "duration", "column")

    def __init__(self, start_time: float, duration: float | None, column: int) -> None:
        self.start_time = start_time
        self.duration = duration
        self.column = column

    def end_time(self) -> float:
        return self.start_time if self.duration is None else self.start_time + self.duration


class _Pattern:
    __slots__ = ("objs", "contained")

    def __init__(self) -> None:
        self.objs: list[_CObj] = []
        self.contained: int = 0

    def add(self, obj: _CObj) -> None:
        self.objs.append(obj)
        self.contained |= 1 << obj.column

    def column_has_obj(self, column: int) -> bool:
        return (self.contained >> column) & 1 == 1

    def column_with_objs(self) -> int:
        return bin(self.contained).count("1")

    def append_from(self, other: "_Pattern") -> None:
        self.objs.extend(other.objs)
        other.objs.clear()
        self.contained |= other.contained
        other.contained = 0


class _PatternGenerator:

    __slots__ = ("hit_object", "total_columns", "random", "conv_diff")

    def __init__(
            self,
            hit_object: HitObject,
            total_columns: int,
            random: OsuRandom,
            conv_diff: float,
    ) -> None:
        self.hit_object = hit_object
        self.total_columns = total_columns
        self.random = random
        self.conv_diff = conv_diff

    def random_start(self) -> int:
        return 1 if self.total_columns == 8 else 0

    def get_column(self, allow_special: bool = False) -> int:
        if allow_special and self.total_columns == 8:
            local_x_divisor = float(f32(512.0 / 7.0))
            v = math.floor(float(f32(self.hit_object.pos.x / local_x_divisor)))
            return min(max(int(v), 0), 6) + 1

        return column_for_x(self.hit_object.pos.x, self.total_columns)

    def get_random_note_count(
            self,
            p2: float,
            p3: float,
            p4: float = 0.0,
            p5: float = 0.0,
            p6: float = 0.0,
    ) -> int:
        val = self.random.next_double()

        if val >= 1.0 - p6:
            return 6
        if val >= 1.0 - p5:
            return 5
        if val >= 1.0 - p4:
            return 4
        if val >= 1.0 - p3:
            return 3
        return 1 + (1 if val >= 1.0 - p2 else 0)

    def conversion_difficulty(self) -> float:
        return self.conv_diff

    def get_random_column(
            self, lower: Optional[int] = None, upper: Optional[int] = None
    ) -> int:
        lo = self.random_start() if lower is None else lower
        hi = self.total_columns if upper is None else upper
        return self.random.next_int_range(lo, hi)


def _calculate_conversion_difficulty(pm: PerformanceBeatmap) -> float:
    objs = pm.hit_objects
    last_obj_time = objs[-1].start_time if objs else 0.0
    first_obj_time = objs[0].start_time if objs else 0.0

    total_break_time = 0.0
    for b_start, b_end in pm.breaks:
        total_break_time += b_end - b_start

    drain_time = _as_i32((last_obj_time - first_obj_time - total_break_time) / 1000.0)

    if drain_time == 0:
        drain_time = 10_000

    ar = pm.base_ar
    ar_clamped = min(max(ar, 4.0), 7.0)
    conversion_difficulty = float(f32(pm.base_hp + ar_clamped)) / 1.5
    conversion_difficulty += float(len(objs)) / float(drain_time) * 9.0
    conversion_difficulty /= 38.0
    conversion_difficulty *= 5.0
    conversion_difficulty /= 1.15
    conversion_difficulty = min(conversion_difficulty, 12.0)

    return conversion_difficulty


class _HitObjectPatternGenerator:

    def __init__(
            self,
            random: OsuRandom,
            hit_object: HitObject,
            sample: int,
            total_columns: int,
            prev_time: float,
            prev_pos_x: float,
            prev_pos_y: float,
            prev_stair: int,
            prev_pattern: _Pattern,
            density: float,
            pm: PerformanceBeatmap,
            conv_diff: float,
    ) -> None:
        tp = timing_point_at(pm.timing_points, hit_object.start_time)
        beat_len = tp.beat_len if tp is not None else 1000.0

        dx = float(f32(hit_object.pos.x - prev_pos_x))
        dy = float(f32(hit_object.pos.y - prev_pos_y))
        pos_separation = float(f32(math.sqrt(float(f32(f32(dx * dx) + f32(dy * dy))))))
        time_separation = hit_object.start_time - prev_time

        convert_type = 0

        if time_separation <= 80.0:
            convert_type |= _FORCE_NOT_STACK | _KEEP_SINGLE
        elif time_separation <= 95.0:
            convert_type |= _FORCE_NOT_STACK | _KEEP_SINGLE | prev_stair
        elif time_separation <= 105.0:
            convert_type |= _FORCE_NOT_STACK | _LOW_PROBABILITY
        elif time_separation <= 125.0:
            convert_type |= _FORCE_NOT_STACK
        elif time_separation <= 135.0 and pos_separation < 20.0:
            convert_type |= _CYCLE | _KEEP_SINGLE
        elif time_separation <= 150.0 and pos_separation < 20.0:
            convert_type |= _FORCE_STACK | _LOW_PROBABILITY
        elif pos_separation < 20.0 and density >= beat_len / 2.5:
            convert_type |= _REVERSE | _LOW_PROBABILITY
        elif density < beat_len / 2.5:
            pass
        else:
            ep = effect_point_at(pm.effect_points, hit_object.start_time)
            kiai = ep.kiai if ep is not None else False
            if not kiai:
                convert_type |= _LOW_PROBABILITY

        if not convert_type & _KEEP_SINGLE:
            if sample & _FINISH and total_columns != 8:
                convert_type |= _MIRROR
            elif sample & _CLAP:
                convert_type |= _GATHERED

        self.sample = sample
        self.stair_type = prev_stair
        self.convert_type = convert_type
        self.prev_pattern = prev_pattern
        self.inner = _PatternGenerator(hit_object, total_columns, random, conv_diff)

    def _note(self, column: int) -> _CObj:
        return _CObj(self.inner.hit_object.start_time, None, column)

    def generate(self) -> _Pattern:
        pattern = self._generate_core()

        for obj in pattern.objs:
            col = obj.column

            if self.convert_type & _STAIR and col == self.inner.total_columns - 1:
                self.stair_type = _REVERSE_STAIR

            if self.convert_type & _REVERSE_STAIR and col == self.inner.random_start():
                self.stair_type = _STAIR

        return pattern

    def _generate_core(self) -> _Pattern:
        if self.inner.total_columns == 1:
            p = _Pattern()
            p.add(self._note(0))
            return p

        last_column = (
            self.prev_pattern.objs[-1].column if self.prev_pattern.objs else 0
        )
        random_start = self.inner.random_start()
        total_columns = self.inner.total_columns

        if self.convert_type & _REVERSE and self.prev_pattern.objs:
            pattern = _Pattern()
            for i in range(random_start, total_columns):
                if self.prev_pattern.column_has_obj(i):
                    pattern.add(self._note(random_start + total_columns - i - 1))
            return pattern

        if (
                self.convert_type & _CYCLE
                and len(self.prev_pattern.objs) == 1
                and (total_columns != 8 or last_column != 0)
                and (total_columns % 2 == 0 or last_column != total_columns // 2)
        ):
            pattern = _Pattern()
            pattern.add(self._note(random_start + total_columns - last_column - 1))
            return pattern

        if self.convert_type & _FORCE_STACK and self.prev_pattern.objs:
            pattern = _Pattern()
            for i in range(random_start, total_columns):
                if self.prev_pattern.column_has_obj(i):
                    pattern.add(self._note(i))
            return pattern

        if len(self.prev_pattern.objs) == 1:
            if self.convert_type & _STAIR:
                target_column = last_column + 1
                if target_column == total_columns:
                    target_column = random_start
                pattern = _Pattern()
                pattern.add(self._note(target_column))
                return pattern

            if self.convert_type & _REVERSE_STAIR:
                target_column = last_column - 1
                if target_column == random_start - 1:
                    target_column = total_columns - 1
                pattern = _Pattern()
                pattern.add(self._note(target_column))
                return pattern

        if self.convert_type & _KEEP_SINGLE:
            return self._generate_random_notes(1)

        conversion_diff = self.inner.conversion_difficulty()

        if self.convert_type & _MIRROR:
            if conversion_diff > 6.5:
                return self._generate_random_pattern_with_mirrored(0.12, 0.38, 0.12)
            if conversion_diff > 4.0:
                return self._generate_random_pattern_with_mirrored(0.12, 0.17, 0.0)
            return self._generate_random_pattern_with_mirrored(0.12, 0.0, 0.0)

        if conversion_diff > 6.5:
            if self.convert_type & _LOW_PROBABILITY:
                return self._generate_random_pattern(0.78, 0.42, 0.0, 0.0)
            return self._generate_random_pattern(1.0, 0.62, 0.0, 0.0)

        if conversion_diff > 4.0:
            if self.convert_type & _LOW_PROBABILITY:
                return self._generate_random_pattern(0.35, 0.08, 0.0, 0.0)
            return self._generate_random_pattern(0.52, 0.15, 0.0, 0.0)

        if conversion_diff > 2.0:
            if self.convert_type & _LOW_PROBABILITY:
                return self._generate_random_pattern(0.18, 0.0, 0.0, 0.0)
            return self._generate_random_pattern(0.45, 0.0, 0.0, 0.0)

        return self._generate_random_pattern(0.0, 0.0, 0.0, 0.0)

    def _generate_random_notes(self, note_count: int) -> _Pattern:
        pattern = _Pattern()

        allow_stacking = not self.convert_type & _FORCE_NOT_STACK

        if not allow_stacking:
            note_count = min(
                self.inner.total_columns
                - self.inner.random_start()
                - self.prev_pattern.column_with_objs(),
                note_count,
            )

        next_column = self.inner.get_column(allow_special=True)

        for _ in range(max(0, note_count)):
            if allow_stacking:
                next_column = self._find_available_column(
                    next_column, None, self._get_next_column, [pattern],
                )
            else:
                next_column = self._find_available_column(
                    next_column, None, self._get_next_column,
                    [pattern, self.prev_pattern],
                )

            pattern.add(self._note(next_column))

        return pattern

    def _get_next_column(self, last: int) -> int:
        if self.convert_type & _GATHERED:
            last += 1
            if last == self.inner.total_columns:
                last = self.inner.random_start()
        else:
            last = self.inner.get_random_column()

        return last

    def _has_special_column(self) -> bool:
        return bool(self.sample & _CLAP) and bool(self.sample & _FINISH)

    def _generate_random_pattern(
            self, p2: float, p3: float, p4: float, p5: float
    ) -> _Pattern:
        random_note_count = self._get_random_note_count(p2, p3, p4, p5)
        pattern = self._generate_random_notes(random_note_count)

        if self.inner.random_start() > 0 and self._has_special_column():
            pattern.add(self._note(0))

        return pattern

    def _get_random_note_count(
            self, p2: float, p3: float, p4: float, p5: float
    ) -> int:
        total_columns = self.inner.total_columns
        if total_columns == 2:
            p2 = 0.0
            p3 = 0.0
            p4 = 0.0
            p5 = 0.0
        elif total_columns == 3:
            p2 = min(p2, 0.1)
            p3 = 0.0
            p4 = 0.0
            p5 = 0.0
        elif total_columns == 4:
            p2 = min(p2, 0.23)
            p3 = min(p3, 0.04)
            p4 = 0.0
            p5 = 0.0
        elif total_columns == 5:
            p3 = min(p3, 0.15)
            p4 = min(p4, 0.03)
            p5 = 0.0

        if self.sample & _CLAP:
            p2 = 1.0

        return self.inner.get_random_note_count(p2, p3, p4, p5)

    def _generate_random_pattern_with_mirrored(
            self, centre_probability: float, p2: float, p3: float
    ) -> _Pattern:
        if self.convert_type & _FORCE_NOT_STACK:
            return self._generate_random_pattern(
                1.0 / 2.0 + p2 / 2.0, p2, (p2 + p3) / 2.0, p3
            )

        pattern = _Pattern()

        note_count, add_to_centre = self._get_random_note_count_mirrored(
            centre_probability, p2, p3
        )

        total_columns = self.inner.total_columns
        if total_columns % 2 == 0:
            column_limit = total_columns // 2
        else:
            column_limit = (total_columns - 1) // 2

        next_column = self.inner.get_random_column(None, column_limit)

        for _ in range(max(0, note_count)):
            next_column = self._find_available_column(
                next_column, column_limit, None, [pattern],
            )

            pattern.add(self._note(next_column))

            column = self.inner.random_start() + total_columns - next_column - 1
            pattern.add(self._note(column))

        if add_to_centre:
            pattern.add(self._note(total_columns // 2))

        if self.inner.random_start() > 0 and self._has_special_column():
            pattern.add(self._note(0))

        return pattern

    def _get_random_note_count_mirrored(
            self, centre_probability: float, p2: float, p3: float
    ) -> tuple[int, bool]:
        total_columns = self.inner.total_columns

        if total_columns == 2:
            centre_probability = 0.0
            p2 = 0.0
            p3 = 0.0
        elif total_columns == 3:
            centre_probability = min(centre_probability, 0.03)
            p2 = 0.0
            p3 = 0.0
        elif total_columns == 4:
            centre_probability = 0.0
            p2 = 1.0 - max((1.0 - p2) * 2.0, 0.8)
            p3 = 0.0
        elif total_columns == 5:
            centre_probability = min(centre_probability, 0.03)
            p3 = 0.0
        elif total_columns == 6:
            centre_probability = 0.0
            p2 = 1.0 - max((1.0 - p2) * 2.0, 0.05)
            p3 = 1.0 - max((1.0 - p3) * 2.0, 0.85)

        p2 = min(max(p2, 0.0), 1.0)
        p3 = min(max(p3, 0.0), 1.0)

        centre_val = self.inner.random.next_double()
        note_count = self.inner.get_random_note_count(p2, p3)

        add_to_centre = (
                total_columns % 2 != 0
                and note_count != 3
                and centre_val > 1.0 - centre_probability
        )

        return note_count, add_to_centre

    def _find_available_column(
            self,
            initial_column: int,
            upper: Optional[int],
            next_column: Optional[Callable[[int], int]],
            patterns: list[_Pattern],
    ) -> int:
        lower = self.inner.random_start()
        if upper is None:
            upper = self.inner.total_columns

        def is_valid(column: int) -> bool:
            return all(not p.column_has_obj(column) for p in patterns)

        if is_valid(initial_column):
            return initial_column

        assert any(is_valid(c) for c in range(lower, upper))

        while True:
            if next_column is not None:
                initial_column = next_column(initial_column)
            else:
                initial_column = self.inner.get_random_column(lower, upper)

            if is_valid(initial_column):
                return initial_column


class _PathObjectPatternGenerator:

    def __init__(
            self,
            random: OsuRandom,
            hit_object: HitObject,
            sample: int,
            total_columns: int,
            prev_pattern: _Pattern,
            pm: PerformanceBeatmap,
            repeats: int,
            expected_dist: float | None,
            node_sounds: list[int],
            conv_diff: float,
    ) -> None:
        tp = timing_point_at(pm.timing_points, hit_object.start_time)
        timing_beat_len = tp.beat_len if tp is not None else 1000.0

        dp = difficulty_point_at(pm.difficulty_points, hit_object.start_time)
        slider_velocity = dp.slider_velocity if dp is not None else 1.0

        ep = effect_point_at(pm.effect_points, hit_object.start_time)
        kiai = ep.kiai if ep is not None else False

        self.convert_type = 0 if kiai else _LOW_PROBABILITY

        beat_len = get_precision_adjusted_beat_length(slider_velocity, timing_beat_len)

        self.span_count = repeats + 1
        self.start_time = _rte_i32(hit_object.start_time)

        dist = expected_dist if expected_dist is not None else 0.0

        self.end_time = _as_i32(
            math.floor(
                float(self.start_time)
                + dist * beat_len * float(self.span_count) * 0.01 / pm.slider_multiplier
            )
        )

        self.segment_duration = _i32_div(
            self.end_time - self.start_time, self.span_count
        )

        self.sample = sample
        self.prev_pattern = prev_pattern
        self.node_sounds = node_sounds
        self.inner = _PatternGenerator(hit_object, total_columns, random, conv_diff)

    def _slider_note(self, column: int, start_time: int, end_time: int) -> _CObj:
        if start_time == end_time:
            return _CObj(float(start_time), None, column)
        return _CObj(float(start_time), float(end_time) - float(start_time), column)

    def generate(self) -> list[_Pattern]:
        orig_pattern = self._generate()

        if len(orig_pattern.objs) == 1:
            return [orig_pattern]

        intermediate_pattern = _Pattern()
        end_time_pattern = _Pattern()

        for obj in orig_pattern.objs:
            if self.end_time != _rte_i32(obj.end_time()):
                intermediate_pattern.add(obj)
            else:
                end_time_pattern.add(obj)

        return [intermediate_pattern, end_time_pattern]

    def _generate(self) -> _Pattern:
        conversion_diff = self.inner.conversion_difficulty()

        if self.inner.total_columns == 1:
            p = _Pattern()
            p.add(self._slider_note(0, self.start_time, self.end_time))
            return p

        if self.span_count > 1:
            if self.segment_duration <= 90:
                return self._generate_random_hold_notes(self.start_time, 1)

            if self.segment_duration <= 120:
                self.convert_type |= _FORCE_NOT_STACK
                return self._generate_random_notes(
                    self.start_time, self.span_count + 1
                )

            if self.segment_duration <= 160:
                return self._generate_stair(self.start_time)

            if self.segment_duration <= 200 and conversion_diff > 3.0:
                return self._generate_random_multiple_notes(self.start_time)

            if self.end_time - self.start_time >= 4000:
                return self._generate_n_random_notes(self.start_time, 0.23, 0.0, 0.0)

            if (
                    self.segment_duration > 400
                    and self.span_count
                    < self.inner.total_columns - 1 - self.inner.random_start()
            ):
                return self._generate_tiled_hold_notes(self.start_time)

            return self._generate_hold_and_normal_notes(
                self.start_time, conversion_diff
            )

        if self.segment_duration <= 110:
            if self.prev_pattern.column_with_objs() < self.inner.total_columns:
                self.convert_type |= _FORCE_NOT_STACK
            else:
                self.convert_type &= ~_FORCE_NOT_STACK

            note_count = 1 + (1 if self.segment_duration >= 80 else 0)
            return self._generate_random_notes(self.start_time, note_count)

        if conversion_diff > 6.5:
            if self.convert_type & _LOW_PROBABILITY:
                return self._generate_n_random_notes(self.start_time, 0.78, 0.3, 0.0)
            return self._generate_n_random_notes(self.start_time, 0.85, 0.36, 0.03)

        if conversion_diff > 4.0:
            if self.convert_type & _LOW_PROBABILITY:
                return self._generate_n_random_notes(self.start_time, 0.43, 0.08, 0.0)
            return self._generate_n_random_notes(self.start_time, 0.56, 0.18, 0.0)

        if conversion_diff > 2.5:
            if self.convert_type & _LOW_PROBABILITY:
                return self._generate_n_random_notes(self.start_time, 0.3, 0.0, 0.0)
            return self._generate_n_random_notes(self.start_time, 0.37, 0.08, 0.0)

        if self.convert_type & _LOW_PROBABILITY:
            return self._generate_n_random_notes(self.start_time, 0.17, 0.0, 0.0)
        return self._generate_n_random_notes(self.start_time, 0.27, 0.0, 0.0)

    def _generate_random_hold_notes(self, start_time: int, note_count: int) -> _Pattern:
        pattern = _Pattern()

        random_start = self.inner.random_start()
        usable_columns = (
                self.inner.total_columns
                - random_start
                - self.prev_pattern.column_with_objs()
        )
        next_column = self.inner.get_random_column()

        for _ in range(max(0, min(usable_columns, note_count))):
            next_column = self._find_available_column(
                next_column, None, [pattern, self.prev_pattern],
            )
            pattern.add(self._slider_note(next_column, start_time, self.end_time))

        for _ in range(max(0, note_count - max(usable_columns, 0))):
            next_column = self._find_available_column(next_column, None, [pattern])
            pattern.add(self._slider_note(next_column, start_time, self.end_time))

        return pattern

    def _generate_random_notes(self, start_time: int, note_count: int) -> _Pattern:
        next_column = self.inner.get_column(allow_special=True)

        if (
                self.convert_type & _FORCE_NOT_STACK
                and self.prev_pattern.column_with_objs() < self.inner.total_columns
        ):
            next_column = self._find_available_column(
                next_column, None, [self.prev_pattern],
            )

        last_column = next_column
        pattern = _Pattern()

        for _ in range(max(0, note_count)):
            pattern.add(self._slider_note(next_column, start_time, start_time))

            lc = last_column
            next_column = self._find_available_column(
                next_column, lambda c, lc=lc: c != lc, [],
            )
            last_column = next_column
            start_time += self.segment_duration

        return pattern

    def _generate_stair(self, start_time: int) -> _Pattern:
        column = self.inner.get_column(allow_special=True)
        increasing = self.inner.random.next_double() > 0.5
        pattern = _Pattern()

        for _ in range(self.span_count + 1):
            pattern.add(self._slider_note(column, start_time, start_time))
            start_time += self.segment_duration

            if increasing:
                if column >= self.inner.total_columns - 1:
                    increasing = False
                    column -= 1
                else:
                    column += 1
            elif column <= self.inner.random_start():
                increasing = True
                column += 1
            else:
                column -= 1

        return pattern

    def _generate_random_multiple_notes(self, start_time: int) -> _Pattern:
        legacy = 4 <= self.inner.total_columns <= 8
        interval = self.inner.random.next_int_range(
            1, self.inner.total_columns - (1 if legacy else 0)
        )

        next_column = self.inner.get_column(allow_special=True)
        random_start = self.inner.random_start()
        not_2k = self.inner.total_columns > 2
        pattern = _Pattern()

        for _ in range(self.span_count + 1):
            pattern.add(self._slider_note(next_column, start_time, start_time))

            next_column += interval
            if next_column >= self.inner.total_columns - random_start:
                next_column = (
                        next_column
                        - self.inner.total_columns
                        - random_start
                        + (1 if legacy else 0)
                )
            next_column += random_start

            if not_2k:
                pattern.add(self._slider_note(next_column, start_time, start_time))

            next_column = self.inner.get_random_column()
            start_time += self.segment_duration

        return pattern

    def _generate_n_random_notes(
            self, start_time: int, p2: float, p3: float, p4: float
    ) -> _Pattern:
        total_columns = self.inner.total_columns
        if total_columns == 2:
            p2 = 0.0
            p3 = 0.0
            p4 = 0.0
        elif total_columns == 3:
            p2 = min(p2, 0.1)
            p3 = 0.0
            p4 = 0.0
        elif total_columns == 4:
            p2 = min(p2, 0.3)
            p3 = min(p3, 0.04)
            p4 = 0.0
        elif total_columns == 5:
            p2 = min(p2, 0.34)
            p3 = min(p3, 0.1)
            p4 = min(p4, 0.03)

        def is_double_sample(sample: int) -> bool:
            return bool(sample & (_CLAP | _FINISH))

        can_generate_two_notes = not self.convert_type & _LOW_PROBABILITY and (
                is_double_sample(self.sample)
                or is_double_sample(self._sample_info_list_at(self.start_time))
        )

        if can_generate_two_notes:
            p2 = 1.0

        note_count = self.inner.get_random_note_count(p2, p3, p4)

        return self._generate_random_hold_notes(start_time, note_count)

    def _generate_tiled_hold_notes(self, start_time: int) -> _Pattern:
        column_repeat = min(self.span_count, self.inner.total_columns)

        end_time = start_time + self.segment_duration * self.span_count

        next_column = self.inner.get_column(allow_special=True)

        if (
                self.convert_type & _FORCE_NOT_STACK
                and self.prev_pattern.column_with_objs() < self.inner.total_columns
        ):
            next_column = self._find_available_column(
                next_column, None, [self.prev_pattern],
            )

        pattern = _Pattern()

        for _ in range(max(0, column_repeat)):
            next_column = self._find_available_column(next_column, None, [pattern])
            pattern.add(self._slider_note(next_column, start_time, end_time))
            start_time += self.segment_duration

        return pattern

    def _generate_hold_and_normal_notes(
            self, start_time: int, conversion_diff: float
    ) -> _Pattern:
        pattern = _Pattern()

        hold_column = self.inner.get_column(allow_special=True)

        if (
                self.convert_type & _FORCE_NOT_STACK
                and self.prev_pattern.column_with_objs() < self.inner.total_columns
        ):
            hold_column = self._find_available_column(
                hold_column, None, [self.prev_pattern],
            )

        pattern.add(self._slider_note(hold_column, start_time, self.end_time))

        next_column = self.inner.get_random_column()

        if conversion_diff > 6.5:
            note_count = self.inner.get_random_note_count(0.63, 0.0)
        elif conversion_diff > 4.0:
            p2 = 0.12 if self.inner.total_columns < 6 else 0.45
            note_count = self.inner.get_random_note_count(p2, 0.0)
        elif conversion_diff > 2.5:
            p2 = 0.0 if self.inner.total_columns < 6 else 0.24
            note_count = self.inner.get_random_note_count(p2, 0.0)
        else:
            note_count = 0

        note_count = min(note_count, self.inner.total_columns - 1)

        sample = self._sample_info_list_at(start_time)
        ignore_head = not sample & (_WHISTLE | _FINISH | _CLAP)

        row_pattern = _Pattern()

        for _ in range(self.span_count + 1):
            if not (ignore_head and start_time == self.start_time):
                for _ in range(max(0, note_count)):
                    hc = hold_column
                    next_column = self._find_available_column(
                        next_column, lambda c, hc=hc: c != hc, [row_pattern],
                    )
                    row_pattern.add(
                        self._slider_note(next_column, start_time, start_time)
                    )

            pattern.append_from(row_pattern)
            start_time += self.segment_duration

        return pattern

    def _sample_info_list_at(self, time: int) -> int:
        samples = self._note_samples_at(time)
        return samples[0] if samples else self.sample

    def _note_samples_at(self, time: int) -> list[int]:
        if self.segment_duration == 0:
            idx = 0
        else:
            idx = _i32_div(time - self.start_time, self.segment_duration)
        return self.node_sounds[idx:]

    def _find_available_column(
            self,
            initial_column: int,
            validation: Optional[Callable[[int], bool]],
            patterns: list[_Pattern],
    ) -> int:
        lower = self.inner.random_start()
        upper = self.inner.total_columns

        def is_valid(column: int) -> bool:
            if validation is not None and not validation(column):
                return False
            return all(not p.column_has_obj(column) for p in patterns)

        if is_valid(initial_column):
            return initial_column

        assert any(is_valid(c) for c in range(lower, upper))

        while True:
            initial_column = self.inner.get_random_column(lower, upper)
            if is_valid(initial_column):
                return initial_column


class _EndTimeObjectPatternGenerator:

    def __init__(
            self,
            random: OsuRandom,
            hit_object: HitObject,
            end_time: float,
            sample: int,
            total_columns: int,
            prev_pattern: _Pattern,
            conv_diff: float,
    ) -> None:
        if prev_pattern.column_with_objs() == total_columns:
            self.convert_type = 0
        else:
            self.convert_type = _FORCE_NOT_STACK

        self.end_time = end_time
        self.sample = sample
        self.prev_pattern = prev_pattern
        self.inner = _PatternGenerator(hit_object, total_columns, random, conv_diff)

    def _end_time_note(self, column: int, hold: bool) -> _CObj:
        start = self.inner.hit_object.start_time
        if hold:
            return _CObj(start, self.end_time - start, column)
        return _CObj(start, None, column)

    def generate(self) -> _Pattern:
        generate_hold = self.end_time - self.inner.hit_object.start_time >= 100.0
        pattern = _Pattern()

        if self.inner.total_columns == 8:
            if (
                    self.sample & _FINISH
                    and self.end_time - self.inner.hit_object.start_time < 1000.0
            ):
                pattern.add(self._end_time_note(0, generate_hold))
            else:
                column = self._get_random_column(self.inner.random_start())
                pattern.add(self._end_time_note(column, generate_hold))
        else:
            column = self._get_random_column(0)
            pattern.add(self._end_time_note(column, generate_hold))

        return pattern

    def _get_random_column(self, lower: int) -> int:
        column = self.inner.get_random_column(lower, None)

        if self.convert_type & _FORCE_NOT_STACK:
            return self._find_available_column(column, lower, [self.prev_pattern])
        return self._find_available_column(column, lower, [])

    def _find_available_column(
            self, initial_column: int, lower: int, patterns: list[_Pattern]
    ) -> int:
        upper = self.inner.total_columns

        def is_valid(column: int) -> bool:
            return all(not p.column_has_obj(column) for p in patterns)

        if is_valid(initial_column):
            return initial_column

        assert any(is_valid(c) for c in range(lower, upper))

        while True:
            initial_column = self.inner.get_random_column(lower, upper)
            if is_valid(initial_column):
                return initial_column


def _target_columns(pm: PerformanceBeatmap, mods: "PerformanceMods | None") -> float:
    keys = getattr(mods, "mania_keys", None) if mods is not None else None
    if keys is not None:
        return float(keys)

    rounded_cs = float(round(f32(pm.base_cs)))
    rounded_od = float(round(f32(pm.base_od)))

    if pm.hit_objects:
        count_slider_or_spinner = sum(
            1 for h in pm.hit_objects
            if isinstance(h.kind, (Slider, Spinner))
        )
        percent_slider_or_spinner = (
                float(count_slider_or_spinner) / float(len(pm.hit_objects))
        )

        if percent_slider_or_spinner < 0.2:
            return 7.0
        if percent_slider_or_spinner < 0.3 or rounded_cs >= 5.0:
            return 7.0 if rounded_od > 5.0 else 6.0
        if percent_slider_or_spinner > 0.6:
            return 5.0 if rounded_od > 4.0 else 4.0

    return float(max(min(int(rounded_od) + 1, 7), 4))


def _convert_osu_to_mania(
        pm: PerformanceBeatmap,
        mods: "PerformanceMods | None",
) -> tuple[list[_CObj], int]:
    hp_cs = float(f32(pm.base_hp + pm.base_cs))
    od_412 = float(f32(pm.base_od * float(f32(41.2))))
    seed = _rte_i32(hp_cs) * 20 + _as_i32(od_412) + _rte_i32(pm.base_ar)

    random = OsuRandom(seed)

    total_columns = int(_target_columns(pm, mods))
    conv_diff = _calculate_conversion_difficulty(pm)

    prev_note_times: deque[float] = deque(maxlen=_MAX_NOTES_FOR_DENSITY)
    density_ref = [float(_I32_MAX)]

    def compute_density(new_note_time: float) -> None:
        prev_note_times.append(new_note_time)
        if len(prev_note_times) >= 2:
            density_ref[0] = (
                    (prev_note_times[-1] - prev_note_times[0]) / len(prev_note_times)
            )

    prev_time = 0.0
    prev_pos_x = 0.0
    prev_pos_y = 0.0
    prev_pattern = _Pattern()
    prev_stair = _STAIR

    new_objects: list[_CObj] = []

    for h in pm.hit_objects:
        sound = h.hit_sound

        if h.is_slider():
            assert isinstance(h.kind, Slider)
            slider = h.kind

            generator = _PathObjectPatternGenerator(
                random, h, sound, total_columns, prev_pattern, pm,
                slider.repeats, slider.expected_dist,
                [int(s) for s in (slider.node_sounds or [])], conv_diff,
            )

            segment_duration = float(generator.segment_duration)

            for i in range(slider.repeats + 2):
                time = h.start_time + segment_duration * float(i)
                prev_time = time
                prev_pos_x = h.pos.x
                prev_pos_y = h.pos.y
                compute_density(time)

            for new_pattern in generator.generate():
                new_objects.extend(new_pattern.objs)
                prev_pattern = new_pattern
        elif h.is_spinner() or h.is_hold_note():
            assert isinstance(h.kind, (Spinner, HoldNote))
            end_time = h.start_time + h.kind.duration

            generator = _EndTimeObjectPatternGenerator(
                random, h, end_time, sound, total_columns, prev_pattern, conv_diff,
            )

            prev_time = end_time
            prev_pos_x = 256.0
            prev_pos_y = 192.0
            compute_density(end_time)

            new_pattern = generator.generate()
            new_objects.extend(new_pattern.objs)
        else:
            compute_density(h.start_time)

            generator = _HitObjectPatternGenerator(
                random, h, sound, total_columns,
                prev_time, prev_pos_x, prev_pos_y, prev_stair,
                prev_pattern, density_ref[0], pm, conv_diff,
            )

            new_pattern = generator.generate()

            prev_stair = generator.stair_type
            prev_time = h.start_time
            prev_pos_x = h.pos.x
            prev_pos_y = h.pos.y

            new_objects.extend(new_pattern.objs)
            prev_pattern = new_pattern

    new_objects.sort(key=lambda o: o.start_time)

    return new_objects, total_columns


def convert_to_mania_objects(
        pm: PerformanceBeatmap,
        *,
        mods: "PerformanceMods | None" = None,
        total_columns: int | None = None,
) -> tuple[list[ManiaObject], int, int, int]:
    if pm.is_convert:
        converted, columns = _convert_osu_to_mania(pm, mods)

        out: list[ManiaObject] = []
        max_combo = 0
        n_hold_notes = 0

        for obj in converted:
            if obj.duration is None:
                out.append(ManiaObject(
                    start_time=obj.start_time, end_time=obj.start_time,
                    column=obj.column,
                ))
                max_combo += 1
            else:
                out.append(ManiaObject(
                    start_time=obj.start_time,
                    end_time=obj.start_time + obj.duration,
                    column=obj.column,
                ))
                max_combo += 1 + int(obj.duration / 100.0)
                n_hold_notes += 1

        return out, max_combo, n_hold_notes, columns

    if total_columns is None:
        total_columns = max(1, round(pm.base_cs))

    out = []
    max_combo = 0
    n_hold_notes = 0

    for h in pm.hit_objects:
        column = column_for_x(h.pos.x, total_columns)

        if h.is_circle():
            out.append(ManiaObject(
                start_time=h.start_time, end_time=h.start_time, column=column,
            ))
            max_combo += 1
            continue

        if h.is_slider():
            assert isinstance(h.kind, Slider)
            slider = h.kind

            dist = slider.expected_dist if slider.expected_dist is not None else 0.0

            tp = timing_point_at(pm.timing_points, h.start_time)
            beat_len = tp.beat_len if tp is not None else 1000.0

            dp = difficulty_point_at(pm.difficulty_points, h.start_time)
            slider_velocity = dp.slider_velocity if dp is not None else 1.0

            scoring_dist = BASE_SCORING_DIST * pm.slider_multiplier * slider_velocity
            velocity = scoring_dist / beat_len if beat_len != 0 else 0.0

            span_count = slider.repeats + 1
            duration = (span_count * dist / velocity) if velocity != 0 else 0.0
            end_time = h.start_time + duration

            out.append(ManiaObject(start_time=h.start_time, end_time=end_time, column=column))
            max_combo += 1 + int(duration / 100.0)
            n_hold_notes += 1
            continue

        if h.is_hold_note() or h.is_spinner():
            assert isinstance(h.kind, (HoldNote, Spinner))
            duration = h.kind.duration
            out.append(ManiaObject(
                start_time=h.start_time, end_time=h.start_time + duration, column=column,
            ))
            max_combo += 1 + int(duration / 100.0)
            n_hold_notes += 1
            continue

        out.append(ManiaObject(
            start_time=h.start_time, end_time=h.start_time, column=column,
        ))
        max_combo += 1

    return out, max_combo, n_hold_notes, total_columns
