"""osu!(stable) ScoreV1 simulation used for classic score-based miss estimation.

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

Port of rosu-pp's `osu/legacy_score_simulator` and `osu/utils/legacy_score`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from parsecore.Beatmap.utils import f32

from ...data.hit_objects import Spinner
from ...utils import _round_ties_even, calculate_difficulty_peppy_stars
from .hit_objects import OsuObject, OsuSlider

if TYPE_CHECKING:
    from ...data.beatmap import PerformanceBeatmap

_MAXIMUM_ROTATIONS_PER_SECOND: float = 477.0 / 60.0
_MINIMUM_ROTATIONS_PER_SECOND: float = 3.0

_I32_MIN = -(2 ** 31)
_I32_MAX = 2 ** 31 - 1


def _as_i32(value: float) -> int:
    """Cast a float to a 32-bit int, truncating toward zero and saturating."""
    if value != value:
        return 0
    if value <= _I32_MIN:
        return _I32_MIN
    if value >= _I32_MAX:
        return _I32_MAX
    return int(value)


@dataclass(slots=True)
class LegacyScoreAttributes:
    """Accumulated ScoreV1 values (accuracy score, combo, bonus, ...)."""
    accuracy_score: int = 0
    combo_score: int = 0
    bonus_score_ratio: float = 0.0
    bonus_score: int = 0
    max_combo: int = 0


class _LegacyScoreSimulatorInner:
    """Running ScoreV1 accumulator state during simulation."""
    __slots__ = ("legacy_bonus_score", "standardised_bonus_score", "combo")

    def __init__(self) -> None:
        """Initialise the accumulator at zero."""
        self.legacy_bonus_score = 0
        self.standardised_bonus_score = 0
        self.combo = 0

    def unrolled_recursion(
            self,
            attrs: LegacyScoreAttributes,
            add_score_combo_multiplier: bool,
            is_bonus: bool,
            increase_combo: bool,
            score_increase: int,
            bonus_base_score: int,
    ) -> float | None:
        """Apply one judgement's score and combo contribution."""
        factor: float | None = None

        if add_score_combo_multiplier:
            factor = float(max(self.combo - 1, 0)) * float(score_increase // 25)

        if is_bonus:
            self.legacy_bonus_score += score_increase
            self.standardised_bonus_score += bonus_base_score
        else:
            attrs.accuracy_score += score_increase

        if increase_combo:
            self.combo += 1

        return factor

    def finalize(self, attrs: LegacyScoreAttributes) -> None:
        """Finalise the bonus ratio and max combo onto the attributes."""
        if self.legacy_bonus_score == 0:
            attrs.bonus_score_ratio = 0.0
        else:
            attrs.bonus_score_ratio = (
                    float(self.standardised_bonus_score) / float(self.legacy_bonus_score)
            )

        attrs.bonus_score = self.legacy_bonus_score
        attrs.max_combo = self.combo


class OsuLegacyScoreSimulator:
    """Simulates the maximum osu!-stable ScoreV1 for a beatmap."""
    __slots__ = ("osu_objects", "passed_objects", "inner", "score_multiplier_value")

    def __init__(
            self,
            osu_objects: list[OsuObject],
            beatmap: "PerformanceBeatmap",
            passed_objects: int,
    ) -> None:
        """Initialise the simulator and compute the ScoreV1 difficulty multiplier."""
        hp = f32(beatmap.base_hp)
        od = f32(max(0.0, min(10.0, beatmap.base_od)))
        cs = f32(beatmap.base_cs)

        self.osu_objects = osu_objects
        self.passed_objects = passed_objects
        self.inner = _LegacyScoreSimulatorInner()
        self.score_multiplier_value = float(
            self.score_multiplier(beatmap, passed_objects, hp=hp, od=od, cs=cs)
        )

    @staticmethod
    def score_multiplier(
            beatmap: "PerformanceBeatmap",
            passed_objects: int,
            *,
            hp: float,
            od: float,
            cs: float,
    ) -> int:
        """Return the ScoreV1 difficulty multiplier from the peppy-stars formula."""
        hit_objects = beatmap.hit_objects

        object_count = min(len(hit_objects), max(passed_objects, 0))

        drain_len = 0

        if hit_objects:
            first = hit_objects[0]
            last_idx = max(passed_objects - 1, 0)
            last = hit_objects[last_idx] if last_idx < len(hit_objects) else hit_objects[-1]

            break_len = 0
            for b_start, b_end in beatmap.breaks:
                if not b_end < last.start_time:
                    break
                break_len += _as_i32(_round_ties_even(b_end)) - _as_i32(_round_ties_even(b_start))

            full_len = _as_i32(_round_ties_even(last.start_time)) - _as_i32(
                _round_ties_even(first.start_time)
            )

            drain_len = int((full_len - break_len) / 1000)

        return calculate_difficulty_peppy_stars(object_count, drain_len, hp=hp, od=od, cs=cs)

    def simulate(self) -> LegacyScoreAttributes:
        """Simulate the full map and return the ScoreV1 attributes."""
        attrs = LegacyScoreAttributes()

        for obj in self.osu_objects[: max(self.passed_objects, 0)]:
            self._simulate_hit(obj, attrs)

        self.inner.finalize(attrs)

        return attrs

    def _simulate_hit(self, hit_object: OsuObject, attrs: LegacyScoreAttributes) -> None:
        """Apply the score of one hit object (circle, slider or spinner)."""
        if isinstance(hit_object.kind, OsuSlider):
            slider = hit_object.kind

            self._unrolled_recursion(attrs, False, False, True, 30, 0)

            for nested in slider.nested_objects:
                if nested.is_repeat() or nested.is_tail():
                    self._unrolled_recursion(attrs, False, False, True, 30, 0)
                elif nested.is_tick():
                    self._unrolled_recursion(attrs, False, False, True, 10, 0)

            self._unrolled_recursion(attrs, True, False, False, 300, 0)
        elif isinstance(hit_object.kind, Spinner):
            spinner = hit_object.kind
            seconds_duration = spinner.duration / 1000.0

            total_half_spins_possible = _as_i32(
                seconds_duration * _MAXIMUM_ROTATIONS_PER_SECOND * 2.0
            )
            half_spins_required_for_completion = _as_i32(
                seconds_duration * _MINIMUM_ROTATIONS_PER_SECOND
            )
            half_spins_required_before_bonus = half_spins_required_for_completion + 3

            for i in range(total_half_spins_possible + 1):
                if (
                        i > half_spins_required_before_bonus
                        and (i - half_spins_required_before_bonus) % 2 == 0
                ):
                    self._unrolled_recursion(attrs, False, True, False, 1100, 50)
                elif i > 1 and i % 2 == 0:
                    self._unrolled_recursion(attrs, False, True, False, 100, 10)

            self._unrolled_recursion(attrs, True, False, True, 300, 0)
        else:
            self._unrolled_recursion(attrs, True, False, True, 300, 0)

    def _unrolled_recursion(
            self,
            attrs: LegacyScoreAttributes,
            add_score_combo_multiplier: bool,
            is_bonus: bool,
            increase_combo: bool,
            score_increase: int,
            bonus_base_score: int,
    ) -> None:
        """Apply one judgement's score and combo contribution."""
        factor = self.inner.unrolled_recursion(
            attrs,
            add_score_combo_multiplier,
            is_bonus,
            increase_combo,
            score_increase,
            bonus_base_score,
        )

        if factor is not None:
            attrs.combo_score += _as_i32(factor * self.score_multiplier_value)


def _calculate_spinner_score(spinner: Spinner) -> float:
    """Return the ScoreV1 score of a spinner from its duration."""
    SPIN_SCORE = 100
    BONUS_SPIN_SCORE = 1000

    seconds_duration = spinner.duration / 1000.0

    total_half_spins_possible = _as_i32(
        seconds_duration * _MAXIMUM_ROTATIONS_PER_SECOND * 2.0
    )
    half_spins_required_for_completion = _as_i32(
        seconds_duration * _MINIMUM_ROTATIONS_PER_SECOND
    )
    half_spins_required_before_bonus = half_spins_required_for_completion + 3

    score = 0

    full_spins = int(total_half_spins_possible / 2)

    score += SPIN_SCORE * full_spins

    bonus_spins = int((total_half_spins_possible - half_spins_required_before_bonus) / 2)

    bonus_spins = max(bonus_spins - int(full_spins / 2), 0)

    score += BONUS_SPIN_SCORE * bonus_spins

    return float(score)


class _InnerNestedScorePerObject:
    """Accumulator for the average lazer nested score per object."""
    __slots__ = ("n_sliders", "n_repeats", "amount_of_small_ticks", "spinner_score", "object_count")

    def __init__(self) -> None:
        """Initialise the accumulator."""
        self.n_sliders = 0
        self.n_repeats = 0
        self.amount_of_small_ticks = 0
        self.spinner_score = 0.0
        self.object_count = 0

    def process_next(self, h: OsuObject) -> None:
        """Add one object's nested score contribution."""
        self.object_count += 1

        if isinstance(h.kind, OsuSlider):
            slider = h.kind
            self.n_sliders += 1
            self.n_repeats += slider.repeat_count()
            self.amount_of_small_ticks += slider.tick_count()
        elif isinstance(h.kind, Spinner):
            self.spinner_score += _calculate_spinner_score(h.kind)

    def calculate(self) -> float:
        """Return the average nested score per object."""
        BIG_TICK_SCORE = 30.0
        SMALL_TICK_SCORE = 10.0

        amount_of_big_ticks = self.n_sliders * 2

        amount_of_big_ticks += self.n_repeats

        slider_score = (
                float(amount_of_big_ticks) * BIG_TICK_SCORE
                + float(self.amount_of_small_ticks) * SMALL_TICK_SCORE
        )

        if self.object_count == 0:
            return float("nan")

        return (slider_score + self.spinner_score) / float(self.object_count)


def calculate_nested_score_per_object(objects: list[OsuObject], passed_objects: int) -> float:
    """Return the average lazer nested score per object for a beatmap.

    Args:
        objects: The osu! objects.

    Returns:
        The mean nested score used by the classic miss estimator.
    """
    inner = _InnerNestedScorePerObject()

    for h in objects[: max(passed_objects, 0)]:
        inner.process_next(h)

    return inner.calculate()
