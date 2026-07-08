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
from typing import Any, TYPE_CHECKING

from ...data.attributes import AdjustedBeatmapAttributes, as_override
from ...data.mode import GameMode
from ...data.mods import PerformanceMods
from ...utils import lerp, reverse_lerp

from parsecore.Beatmap.utils import f32

from .convert import convert_objects, prepare_beatmap
from .legacy_score import OsuLegacyScoreSimulator, calculate_nested_score_per_object
from .hit_objects import (
    OsuDifficultyObject,
    OsuDifficultyObjects,
    OsuObject,
    PREEMPT_MIN,
    ScalingFactor,
)
from .skills import (
    Aim,
    Flashlight,
    Reading,
    Speed,
    count_top_weighted_sliders,
    difficulty_to_performance,
)
from ...utils import norm

if TYPE_CHECKING:
    from ...data.beatmap import PerformanceBeatmap

_STAR_RATING_MULTIPLIER: float = 0.0265
_HD_FADE_IN_DURATION_MULTIPLIER: float = 0.4
_DIFFICULTY_MULTIPLIER: float = 0.0675
_PERFORMANCE_BASE_MULTIPLIER: float = 1.14

@dataclass(slots=True)
class OsuDifficultyAttributes:
    aim: float = 0.0
    aim_difficult_slider_count: float = 0.0
    speed: float = 0.0
    flashlight: float = 0.0
    reading: float = 0.0
    slider_factor: float = 1.0
    aim_top_weighted_slider_factor: float = 0.0
    speed_top_weighted_slider_factor: float = 0.0
    speed_note_count: float = 0.0
    aim_difficult_strain_count: float = 0.0
    speed_difficult_strain_count: float = 0.0
    reading_difficult_note_count: float = 0.0

    nested_score_per_object: float = 0.0
    legacy_score_base_multiplier: float = 1.0
    maximum_legacy_combo_score: float = 0.0

    ar: float = 0.0
    hp: float = 0.0
    great_hit_window: float = 0.0
    ok_hit_window: float = 0.0
    meh_hit_window: float = 0.0

    n_circles: int = 0
    n_sliders: int = 0
    n_large_ticks: int = 0
    n_spinners: int = 0

    stars: float = 0.0
    max_combo: int = 0

    od: float = 0.0

    def n_objects(self) -> int:
        return self.n_circles + self.n_sliders + self.n_spinners

class OsuRatingCalculator:
    DIFFICULTY_MULTIPLIER: float = _DIFFICULTY_MULTIPLIER

    def __init__(
            self,
            mods: PerformanceMods,
            total_hits: int,
            approach_rate: float,
            overall_difficulty: float,
            mechanical_difficulty_rating: float,
            slider_factor: float,
    ) -> None:
        self.mods = mods
        self.total_hits = total_hits
        self.approach_rate = approach_rate
        self.overall_difficulty = overall_difficulty
        self.mechanical_difficulty_rating = mechanical_difficulty_rating
        self.slider_factor = slider_factor

    @staticmethod
    def calculate_difficulty_rating(difficulty_value: float) -> float:
        return math.sqrt(max(difficulty_value, 0.0)) * _DIFFICULTY_MULTIPLIER

    def compute_aim_rating(self, aim_difficulty_value: float) -> float:
        if getattr(self.mods, "ap", False):
            return 0.0

        aim_rating = self.calculate_difficulty_rating(aim_difficulty_value)

        if getattr(self.mods, "td", False):
            aim_rating = math.pow(aim_rating, 0.8)

        if getattr(self.mods, "rx", False):
            aim_rating *= 0.9

        rating_multiplier = 1.0

        log_term = (
            math.log10(self.total_hits / 2000.0)
            if self.total_hits > 0
            else -math.inf
        )
        ar_length_bonus = (
                0.95
                + 0.4 * min(self.total_hits / 2000.0, 1.0)
                + float(self.total_hits > 2000) * log_term * 0.5
        )

        if getattr(self.mods, "rx", False):
            ar_factor = 0.0
        elif self.approach_rate > 10.33:
            ar_factor = 0.3 * (self.approach_rate - 10.33)
        elif self.approach_rate < 8.0:
            ar_factor = 0.05 * (8.0 - self.approach_rate)
        else:
            ar_factor = 0.0

        rating_multiplier += ar_factor * ar_length_bonus

        if getattr(self.mods, "hd", False):
            visibility_factor = self._calculate_aim_visibility_factor(
                self.mechanical_difficulty_rating, self.approach_rate
            )
            rating_multiplier += self._calculate_visibility_bonus(
                self.approach_rate, visibility_factor, self.slider_factor
            )

        rating_multiplier *= 0.98 + max(self.overall_difficulty, 0.0) ** 2.0 / 2500.0

        return aim_rating * math.pow(rating_multiplier, 1.0 / 3.0)

    def compute_speed_rating(self, speed_difficulty_value: float) -> float:
        if getattr(self.mods, "rx", False):
            return 0.0

        speed_rating = self.calculate_difficulty_rating(speed_difficulty_value)

        if getattr(self.mods, "ap", False):
            speed_rating *= 0.5

        rating_multiplier = 1.0

        log_term = (
            math.log10(self.total_hits / 2000.0)
            if self.total_hits > 0
            else -math.inf
        )
        ar_length_bonus = (
                0.95
                + 0.4 * min(self.total_hits / 2000.0, 1.0)
                + float(self.total_hits > 2000) * log_term * 0.5
        )

        if getattr(self.mods, "ap", False):
            ar_factor = 0.0
        elif self.approach_rate > 10.33:
            ar_factor = 0.3 * (self.approach_rate - 10.33)
        else:
            ar_factor = 0.0

        rating_multiplier += ar_factor * ar_length_bonus

        if getattr(self.mods, "hd", False):
            visibility_factor = self._calculate_speed_visibility_factor(
                self.mechanical_difficulty_rating, self.approach_rate
            )
            rating_multiplier += self._calculate_visibility_bonus(
                self.approach_rate, visibility_factor, None
            )

        rating_multiplier *= 0.95 + max(self.overall_difficulty, 0.0) ** 2.0 / 750.0

        return speed_rating * math.pow(rating_multiplier, 1.0 / 3.0)

    def compute_flashlight_rating(self, flashlight_difficulty_value: float) -> float:
        if not getattr(self.mods, "fl", False):
            return 0.0

        flashlight_rating = self.calculate_difficulty_rating(flashlight_difficulty_value)

        if getattr(self.mods, "td", False):
            flashlight_rating = math.pow(flashlight_rating, 0.8)

        if getattr(self.mods, "rx", False):
            flashlight_rating *= 0.7
        elif getattr(self.mods, "ap", False):
            flashlight_rating *= 0.4

        rating_multiplier = 1.0

        rating_multiplier *= (
                0.7
                + 0.1 * min(self.total_hits / 200.0, 1.0)
                + (0.2 * min(max(self.total_hits - 200, 0) / 200.0, 1.0) if self.total_hits > 200 else 0.0)
        )

        rating_multiplier *= 0.98 + max(self.overall_difficulty, 0.0) ** 2.0 / 2500.0

        return flashlight_rating * math.sqrt(rating_multiplier)

    @staticmethod
    def _calculate_visibility_bonus(
            approach_rate: float,
            visibility_factor: float | None,
            slider_factor: float | None,
    ) -> float:
        reading_bonus = 0.04 * (12.0 - max(approach_rate, 7.0))
        reading_bonus *= visibility_factor if visibility_factor is not None else 1.0
        slider_visibility_factor = (slider_factor if slider_factor is not None else 1.0) ** 3.0

        if approach_rate < 7.0:
            reading_bonus += 0.045 * (7.0 - max(approach_rate, 0.0)) * slider_visibility_factor
        if approach_rate < 0.0:
            reading_bonus += 0.1 * (1.0 - math.pow(1.5, approach_rate)) * slider_visibility_factor

        return reading_bonus

    @staticmethod
    def _calculate_aim_visibility_factor(
            mechanical_difficulty_rating: float, approach_rate: float
    ) -> float:
        AR_FACTOR_END_POINT = 11.5
        mechanical_difficulty_factor = reverse_lerp(mechanical_difficulty_rating, 5.0, 10.0)
        ar_factor_starting_point = lerp(9.0, 10.33, mechanical_difficulty_factor)
        return reverse_lerp(approach_rate, AR_FACTOR_END_POINT, ar_factor_starting_point)

    @staticmethod
    def _calculate_speed_visibility_factor(
            mechanical_difficulty_rating: float, approach_rate: float
    ) -> float:
        AR_FACTOR_END_POINT = 11.5
        mechanical_difficulty_factor = reverse_lerp(mechanical_difficulty_rating, 5.0, 10.0)
        ar_factor_starting_point = lerp(10.0, 10.33, mechanical_difficulty_factor)
        return reverse_lerp(approach_rate, AR_FACTOR_END_POINT, ar_factor_starting_point)

def _calculate_mechanical_difficulty_rating(
        aim_difficulty_value: float, speed_difficulty_value: float
) -> float:
    aim = difficulty_to_performance(
        OsuRatingCalculator.calculate_difficulty_rating(aim_difficulty_value)
    )
    speed = difficulty_to_performance(
        OsuRatingCalculator.calculate_difficulty_rating(speed_difficulty_value)
    )
    total = math.pow(math.pow(aim, 1.1) + math.pow(speed, 1.1), 1.0 / 1.1)
    return _calculate_star_rating(total)

def _calculate_star_rating(base_performance: float) -> float:
    if base_performance <= 1e-5:
        return 0.0
    return (
            math.pow(_PERFORMANCE_BASE_MULTIPLIER, 1.0 / 3.0)
            * _STAR_RATING_MULTIPLIER
            * (
                    math.pow(
                        100_000.0 / math.pow(2.0, 1.0 / 1.1) * base_performance,
                        1.0 / 3.0,
                        )
                    + 4.0
            )
    )

_PERF_NORM_EXPONENT: float = 1.1
_PERF_BASE_MULTIPLIER: float = 1.12


def _sum_cognition_difficulty(reading: float, flashlight: float) -> float:
    if reading <= 0.0:
        return flashlight
    if flashlight <= 0.0:
        return reading
    return norm(
        _PERF_NORM_EXPONENT,
        [reading, flashlight * max(0.25, min(1.0, flashlight / reading))],
    )


def calculate_difficulty(
        pm: "PerformanceBeatmap",
        mods: PerformanceMods,
        *,
        lazer: bool = True,
        ar_override: float | None = None,
        cs_override: float | None = None,
        hp_override: float | None = None,
        od_override: float | None = None,
        passed_objects: int | None = None,
        **_: Any,
) -> OsuDifficultyAttributes:
    adjusted = AdjustedBeatmapAttributes.create(
        base_cs=pm.base_cs, base_ar=pm.base_ar,
        base_od=pm.base_od, base_hp=pm.base_hp,
        mode=GameMode.OSU, mods=mods,
        ar_override=as_override(ar_override),
        cs_override=as_override(cs_override),
        hp_override=as_override(hp_override),
        od_override=as_override(od_override),
    )

    clock_rate = adjusted.clock_rate
    scaling_factor = ScalingFactor.new(adjusted.cs)

    great_hit_window = adjusted.hit_windows.od_great or 0.0
    ok_hit_window = adjusted.hit_windows.od_ok or 0.0
    meh_hit_window = adjusted.hit_windows.od_meh or 0.0
    ar_window = adjusted.hit_windows.ar or 0.0

    time_preempt = float(int(ar_window * clock_rate))

    attrs = OsuDifficultyAttributes(
        ar=adjusted.ar,
        hp=float(adjusted.hp),
        great_hit_window=great_hit_window,
        ok_hit_window=ok_hit_window,
        meh_hit_window=meh_hit_window,
        od=float(adjusted.od),
    )

    take = passed_objects if passed_objects is not None else len(pm.hit_objects)
    reflection = getattr(mods, "reflection", None)
    if reflection is None:
        from ...data.mods import Reflection
        reflection = Reflection.NONE

    osu_objects = convert_objects(
        beatmap=pm,
        scaling_factor=scaling_factor,
        reflection=reflection,
        time_preempt=time_preempt,
        take=take,
        attrs=attrs,
    )

    diff_objects_list: list[OsuDifficultyObject] = []
    for i in range(1, len(osu_objects)):
        last = osu_objects[i - 1]
        curr = osu_objects[i]
        last_diff = diff_objects_list[-1] if diff_objects_list else None
        last_last_diff = diff_objects_list[-2] if len(diff_objects_list) >= 2 else None
        d = OsuDifficultyObject.new(
            curr, last, last_diff, last_last_diff, clock_rate, i - 1, scaling_factor
        )
        diff_objects_list.append(d)

    diff_objects = OsuDifficultyObjects(diff_objects_list)

    time_fade_in = (
        time_preempt * _HD_FADE_IN_DURATION_MULTIPLIER
        if getattr(mods, "hd", False) else 400.0
    )

    hit_window_great = 2.0 * great_hit_window
    overall_difficulty = (79.5 - hit_window_great / 2.0) / 6.0
    raw_preempt = time_preempt
    preempt_clock_rated = raw_preempt / clock_rate
    take_objects = min(len(pm.hit_objects), take)

    has_autopilot = getattr(mods, "ap", False)
    has_touch_device = getattr(mods, "td", False)
    has_relax = getattr(mods, "rx", False)
    has_hidden = getattr(mods, "hd", False)
    has_fl = getattr(mods, "fl", False)

    aim = Aim(
        include_sliders=True, overall_difficulty=overall_difficulty,
        object_radius=scaling_factor.radius, has_autopilot=has_autopilot,
        has_touch_device=has_touch_device, has_relax=has_relax,
    )
    aim_no_sliders = Aim(
        include_sliders=False, overall_difficulty=overall_difficulty,
        object_radius=scaling_factor.radius, has_autopilot=has_autopilot,
        has_touch_device=has_touch_device, has_relax=has_relax,
    )
    speed = Speed(
        hit_window_great=hit_window_great, has_relax=has_relax,
        has_autopilot=has_autopilot,
    )
    reading = Reading(
        has_hidden, preempt_clock_rated, raw_preempt, time_fade_in,
        overall_difficulty, mods,
    )
    flashlight = Flashlight(
        has_hidden, has_hidden, scaling_factor.radius, raw_preempt, time_fade_in,
        overall_difficulty, take_objects, has_touch_device=has_touch_device,
        has_relax=has_relax, has_autopilot=has_autopilot,
    )

    take_diff_objects = max(take_objects - 1, 0)
    for d in diff_objects.objects[:take_diff_objects]:
        aim.process(d, diff_objects)
        aim_no_sliders.process(d, diff_objects)
        speed.process(d, diff_objects)
        reading.process(d, diff_objects)
        if has_fl:
            flashlight.process(d, diff_objects)

    aim_difficulty_value = aim.difficulty_value()
    aim_no_sliders_difficulty_value = aim_no_sliders.difficulty_value()
    speed_difficulty_value = speed.difficulty_value()
    reading_difficulty_value = reading.difficulty_value()

    aim_difficult_strain_count = aim.count_top_weighted_strains(aim_difficulty_value)
    speed_difficult_strain_count = speed.count_top_weighted_object_difficulties(
        speed_difficulty_value
    )
    reading_difficult_note_count = reading.count_top_weighted_object_difficulties(
        reading_difficulty_value
    )

    speed_notes = speed.relevant_object_count()

    aim_no_sliders_top_weighted_slider_count = aim_no_sliders.count_top_weighted_sliders(
        aim_no_sliders_difficulty_value
    )
    aim_no_sliders_difficult_strain_count = aim_no_sliders.count_top_weighted_strains(
        aim_no_sliders_difficulty_value
    )
    aim_top_weighted_slider_factor = aim_no_sliders_top_weighted_slider_count / max(
        1.0,
        aim_no_sliders_difficult_strain_count - aim_no_sliders_top_weighted_slider_count,
    )

    speed_top_weighted_slider_count = speed.count_top_weighted_sliders(
        speed_difficulty_value
    )
    speed_top_weighted_slider_factor = speed_top_weighted_slider_count / max(
        1.0, speed_difficult_strain_count - speed_top_weighted_slider_count
    )

    difficult_sliders = aim.get_difficult_sliders()

    def _aim_rating(dv: float) -> float:
        return math.pow(dv, 0.63) * 0.02275

    def _diff_rating(dv: float) -> float:
        return math.sqrt(dv) * 0.0675

    slider_factor = (
        _aim_rating(aim_no_sliders_difficulty_value) / _aim_rating(aim_difficulty_value)
        if aim_difficulty_value > 0.0 else 1.0
    )

    aim_rating = _aim_rating(aim_difficulty_value)
    speed_rating = _diff_rating(speed_difficulty_value)
    reading_rating = _diff_rating(reading_difficulty_value)
    flashlight_rating = _diff_rating(flashlight.difficulty_value()) if has_fl else 0.0

    base_aim_performance = 4.0 * (aim_rating * aim_rating * aim_rating)
    base_speed_performance = 4.0 * (speed_rating * speed_rating * speed_rating)
    base_reading_performance = 4.0 * (reading_rating * reading_rating * reading_rating)
    base_flashlight_performance = Flashlight.difficulty_to_performance(flashlight_rating)
    base_cognition_performance = _sum_cognition_difficulty(
        base_reading_performance, base_flashlight_performance
    )

    base_performance = norm(
        _PERF_NORM_EXPONENT,
        [base_aim_performance, base_speed_performance, base_cognition_performance],
    )
    star_rating = math.cbrt(base_performance * _PERF_BASE_MULTIPLIER)

    attrs.aim = aim_rating
    attrs.aim_difficult_slider_count = difficult_sliders
    attrs.speed = speed_rating
    attrs.reading = reading_rating
    attrs.flashlight = flashlight_rating
    attrs.slider_factor = slider_factor
    attrs.aim_top_weighted_slider_factor = aim_top_weighted_slider_factor
    attrs.speed_top_weighted_slider_factor = speed_top_weighted_slider_factor
    attrs.aim_difficult_strain_count = aim_difficult_strain_count
    attrs.speed_difficult_strain_count = speed_difficult_strain_count
    attrs.reading_difficult_note_count = reading_difficult_note_count
    attrs.speed_note_count = speed_notes
    attrs.stars = star_rating

    simulator = OsuLegacyScoreSimulator(osu_objects, pm, take)
    score_attrs = simulator.simulate()
    attrs.maximum_legacy_combo_score = float(score_attrs.combo_score)

    attrs.legacy_score_base_multiplier = float(OsuLegacyScoreSimulator.score_multiplier(
        pm, take, hp=adjusted.raw_hp, od=adjusted.raw_od, cs=adjusted.raw_cs,
    ))

    attrs.nested_score_per_object = calculate_nested_score_per_object(osu_objects, take)

    return attrs

def difficulty(
        pm: "PerformanceBeatmap", mods: PerformanceMods, **kwargs: Any
) -> OsuDifficultyAttributes:
    return calculate_difficulty(pm, mods, **kwargs)