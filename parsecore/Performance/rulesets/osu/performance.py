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
from typing import Any, Optional, TYPE_CHECKING

from ...data.mods import PerformanceMods
from ...data.score_state import HitResultPriority, ScoreState
from ...utils import (
    erf, erf_inv, ieee_div, ieee_ln, ieee_pow, lerp, logistic,
    reverse_lerp, rust_max, rust_min, smoothstep,
)

from .difficulty import OsuDifficultyAttributes, OsuRatingCalculator
from .hitresult_generator import (
    OsuHitResults,
    OsuScoreOrigin,
    OsuScoreState,
    generate_hitresults,
)
from .skills import Aim, Flashlight, Speed, difficulty_to_performance
from ...utils import norm as _norm

if TYPE_CHECKING:
    from ...data.beatmap import PerformanceBeatmap

PERFORMANCE_BASE_MULTIPLIER: float = 1.12
PERFORMANCE_NORM_EXPONENT: float = 1.1


_SQRT2: float = 1.4142135623730950


def _dtp(difficulty: float) -> float:
    return 4.0 * (difficulty * difficulty * difficulty)


def _sum_cognition_difficulty(reading: float, flashlight: float) -> float:
    if reading <= 0.0:
        return flashlight
    if flashlight <= 0.0:
        return reading
    return _norm(
        PERFORMANCE_NORM_EXPONENT,
        [reading, flashlight * max(0.25, min(1.0, flashlight / reading))],
    )

class OsuLegacyScoreMissCalculator:

    def __init__(
            self,
            state: OsuScoreState,
            acc: float,
            mods: PerformanceMods,
            attrs: OsuDifficultyAttributes,
    ) -> None:
        self.state = state
        self.acc = acc
        self.mods = mods
        self.attrs = attrs

    def calculate(self) -> float:
        state = self.state
        attrs = self.attrs

        if attrs.max_combo == 0:
            return 0.0

        if state.legacy_total_score is None:
            return 0.0

        score_v1_multiplier = (
                attrs.legacy_score_base_multiplier * self._legacy_score_multiplier()
        )
        relevant_combo_per_object = self._relevant_score_combo_per_object()

        maximum_miss_count = self._maximum_combo_based_miss_count()

        score_obtained_during_max_combo = self._score_at_combo(
            state.max_combo, relevant_combo_per_object, score_v1_multiplier,
        )
        remaining_score = float(state.legacy_total_score) - score_obtained_during_max_combo

        if remaining_score <= 0.0:
            return maximum_miss_count

        remaining_combo = (attrs.max_combo - state.max_combo) & 0xFFFFFFFF
        expected_remaining_score = self._score_at_combo(
            remaining_combo, relevant_combo_per_object, score_v1_multiplier,
        )

        score_based_miss_count = ieee_div(expected_remaining_score, remaining_score)

        score_based_miss_count = rust_max(score_based_miss_count, 1.0)

        return rust_min(score_based_miss_count, maximum_miss_count)

    def _score_at_combo(
            self,
            combo: int,
            relevant_combo_per_object: float,
            score_v1_multiplier: float,
    ) -> float:
        state = self.state
        attrs = self.attrs
        total_hits = state.hit_results.total_hits()

        estimated_objects = ieee_div(float(combo), relevant_combo_per_object) - 1.0

        if relevant_combo_per_object > 0.0:
            combo_score = (
                    (2.0 * (relevant_combo_per_object - 1.0)
                     + (estimated_objects - 1.0) * relevant_combo_per_object)
                    * estimated_objects
                    / 2.0
            )
        else:
            combo_score = 0.0

        combo_score *= self.acc * 300.0 / 25.0 * score_v1_multiplier

        objects_hit = ieee_div(
            float(total_hits - state.hit_results.misses) * float(combo),
            float(attrs.max_combo),
        )

        non_combo_score = (300.0 + attrs.nested_score_per_object) * self.acc * objects_hit

        return combo_score + non_combo_score

    def _relevant_score_combo_per_object(self) -> float:
        attrs = self.attrs
        combo_score = attrs.maximum_legacy_combo_score

        combo_score = ieee_div(
            combo_score, 300.0 / 25.0 * attrs.legacy_score_base_multiplier,
        )

        result = float((attrs.max_combo - 2) * attrs.max_combo)
        result = ieee_div(
            result, rust_max(float(attrs.max_combo) + 2.0 * (combo_score - 1.0), 1.0),
        )

        return result

    def _maximum_combo_based_miss_count(self) -> float:
        state = self.state
        attrs = self.attrs

        if attrs.n_sliders == 0:
            return float(state.hit_results.misses)

        total_imperfect_hits = (
                state.hit_results.n100 + state.hit_results.n50 + state.hit_results.misses
        )

        miss_count = 0.0

        factor = min(attrs.aim_top_weighted_slider_factor, 1.0)
        likely_missed_sliderend_portion = 0.04 + 0.06 * (factor * factor)

        full_combo_threshold = float(attrs.max_combo) - min(
            4.0 + likely_missed_sliderend_portion * float(attrs.n_sliders),
            float(attrs.n_sliders),
        )

        if float(state.max_combo) < full_combo_threshold:
            miss_count = math.pow(
                full_combo_threshold / max(1.0, float(state.max_combo)), 2.5,
            )

        miss_count = min(miss_count, float(total_imperfect_hits))

        max_possible_slider_breaks = min(
            attrs.n_sliders,
            int((attrs.max_combo - state.max_combo) / 2),
        )

        slider_breaks = miss_count - float(state.hit_results.misses)

        if slider_breaks > float(max_possible_slider_breaks):
            miss_count = float(state.hit_results.misses + max_possible_slider_breaks)

        return miss_count

    def _legacy_score_multiplier(self) -> float:
        mods = self.mods
        score_v2 = getattr(mods, "sv2", False)
        multiplier = 1.0

        if getattr(mods, "nf", False):
            multiplier *= 1.0 if score_v2 else 0.5

        if getattr(mods, "ez", False):
            multiplier *= 0.5

        if mods.clock_rate < 1.0:
            multiplier *= 0.3

        if getattr(mods, "hd", False):
            multiplier *= 1.06

        if getattr(mods, "hr", False):
            multiplier *= 1.10 if score_v2 else 1.06

        if mods.clock_rate > 1.0:
            multiplier *= 1.20 if score_v2 else 1.12

        if getattr(mods, "fl", False):
            multiplier *= 1.12

        if getattr(mods, "so", False):
            multiplier *= 0.9

        if getattr(mods, "rx", False) or getattr(mods, "ap", False):
            multiplier *= 0.0

        return multiplier

@dataclass(slots=True)
class OsuPerformanceAttributes:
    pp: float = 0.0
    pp_aim: float = 0.0
    pp_speed: float = 0.0
    pp_acc: float = 0.0
    pp_reading: float = 0.0
    pp_flashlight: float = 0.0
    effective_miss_count: float = 0.0
    speed_deviation: Optional[float] = None
    combo_based_estimated_miss_count: float = 0.0
    score_based_estimated_miss_count: Optional[float] = None
    aim_estimated_slider_breaks: float = 0.0
    speed_estimated_slider_breaks: float = 0.0
    stars: float = 0.0
    max_combo: int = 0
    difficulty: OsuDifficultyAttributes = field(default_factory=OsuDifficultyAttributes)

    def n_objects(self) -> int:
        return self.difficulty.n_objects()

class OsuPerformanceCalculator:
    def __init__(
            self,
            attrs: OsuDifficultyAttributes,
            mods: PerformanceMods,
            acc: float,
            state: OsuScoreState,
            using_classic_slider_acc: bool,
    ) -> None:
        self.attrs = attrs
        self.mods = mods
        self.acc = acc
        self.state = state
        self.using_classic_slider_acc = using_classic_slider_acc

    def calculate(self) -> OsuPerformanceAttributes:
        total_hits = self.state.hit_results.total_hits()

        if total_hits == 0:
            return OsuPerformanceAttributes(
                difficulty=self.attrs,
                stars=self.attrs.stars,
                max_combo=self.attrs.max_combo,
            )

        combo_based_estimated_miss_count = self._calculate_combo_based_estimated_miss_count()

        score_based_estimated_miss_count: Optional[float] = None
        if (
                self.using_classic_slider_acc
                and self.state.legacy_total_score is not None
        ):
            score_based_estimated_miss_count = OsuLegacyScoreMissCalculator(
                self.state, self.acc, self.mods, self.attrs,
            ).calculate()
            effective_miss_count = score_based_estimated_miss_count
        else:
            effective_miss_count = combo_based_estimated_miss_count

        effective_miss_count = max(
            effective_miss_count, float(self.state.hit_results.misses)
        )
        effective_miss_count = min(
            effective_miss_count, float(self.state.hit_results.total_hits())
        )

        total_hits_f = float(total_hits)

        multiplier = PERFORMANCE_BASE_MULTIPLIER

        if getattr(self.mods, "nf", False):
            multiplier *= max(1.0 - 0.02 * effective_miss_count, 0.9)

        if getattr(self.mods, "so", False) and total_hits_f > 0.0:
            multiplier *= 1.0 - math.pow(self.attrs.n_spinners / total_hits_f, 0.85)

        if getattr(self.mods, "rx", False):
            od = self.attrs.od
            if od > 0.0:
                n100_mult = 0.75 * max(1.0 - od / 13.33, 0.0)
                _r = od / 13.33
                n50_mult = max(1.0 - (_r * _r * _r * _r * _r), 0.0)
            else:
                n100_mult = 0.75
                n50_mult = 1.0
            effective_miss_count = min(
                effective_miss_count
                + float(self.state.hit_results.n100) * n100_mult
                + float(self.state.hit_results.n50) * n50_mult,
                total_hits_f,
                )

        speed_deviation = self._calculate_speed_deviation()

        aim_est_breaks_ref = [0.0]
        speed_est_breaks_ref = [0.0]

        aim_value = self._compute_aim_value(effective_miss_count, aim_est_breaks_ref)
        speed_value = self._compute_speed_value(
            speed_deviation, effective_miss_count, speed_est_breaks_ref
        )
        acc_value = self._compute_accuracy_value()
        reading_value = self._compute_reading_value(
            effective_miss_count, aim_est_breaks_ref
        )
        flashlight_value = self._compute_flashlight_value(effective_miss_count)
        cognition_value = _sum_cognition_difficulty(reading_value, flashlight_value)

        pp = _norm(
            PERFORMANCE_NORM_EXPONENT,
            [aim_value, speed_value, acc_value, cognition_value],
        ) * multiplier

        return OsuPerformanceAttributes(
            difficulty=self.attrs,
            pp=pp,
            pp_aim=aim_value,
            pp_speed=speed_value,
            pp_acc=acc_value,
            pp_reading=reading_value,
            pp_flashlight=flashlight_value,
            effective_miss_count=effective_miss_count,
            speed_deviation=speed_deviation,
            combo_based_estimated_miss_count=combo_based_estimated_miss_count,
            score_based_estimated_miss_count=score_based_estimated_miss_count,
            aim_estimated_slider_breaks=aim_est_breaks_ref[0],
            speed_estimated_slider_breaks=speed_est_breaks_ref[0],
            stars=self.attrs.stars,
            max_combo=self.attrs.max_combo,
        )

    def _compute_aim_value(
            self, effective_miss_count: float, aim_est_breaks: list[float]
    ) -> float:
        if getattr(self.mods, "ap", False):
            return 0.0

        aim_difficulty = self.attrs.aim

        if (
                self.attrs.n_sliders > 0
                and self.attrs.aim_difficult_slider_count > 0.0
        ):
            if self.using_classic_slider_acc:
                maximum_possible_dropped_sliders = self._total_imperfect_hits()
                estimate_improperly_followed = max(
                    0.0,
                    min(
                        min(
                            maximum_possible_dropped_sliders,
                            float(self.attrs.max_combo - self.state.max_combo),
                        ),
                        self.attrs.aim_difficult_slider_count,
                    ),
                )
            else:
                estimate_improperly_followed = max(
                    0.0,
                    min(
                        float(
                            self._n_slider_ends_dropped() + self._n_large_tick_miss()
                        ),
                        self.attrs.aim_difficult_slider_count,
                    ),
                )

            _nerf_base = (
                1.0
                - estimate_improperly_followed
                / self.attrs.aim_difficult_slider_count
            )
            slider_nerf_factor = (
                    (1.0 - self.attrs.slider_factor)
                    * (_nerf_base * _nerf_base * _nerf_base)
                    + self.attrs.slider_factor
            )
            aim_difficulty *= slider_nerf_factor

        aim_value = _dtp(aim_difficulty)

        total_hits = self._total_hits()
        len_bonus = (
                0.95
                + 0.35 * min(total_hits / 2000.0, 1.0)
                + (math.log10(total_hits / 2000.0) * 0.5 if total_hits > 2000.0 else 0.0)
        )
        aim_value *= len_bonus

        if effective_miss_count > 0.0:
            aim_est_breaks[0] = self._calculate_estimated_slider_breaks(
                self.attrs.aim_top_weighted_slider_factor, effective_miss_count
            )
            relevant_miss_count = min(
                effective_miss_count + aim_est_breaks[0],
                self._total_imperfect_hits() + float(self._n_large_tick_miss()),
                )
            aim_value *= self._calculate_miss_penalty(
                relevant_miss_count, self.attrs.aim_difficult_strain_count
            )

        aim_value *= self.acc
        return aim_value

    def _compute_speed_value(
            self,
            speed_deviation: Optional[float],
            effective_miss_count: float,
            speed_est_breaks: list[float],
    ) -> float:
        if speed_deviation is None or getattr(self.mods, "rx", False):
            return 0.0

        speed_value = _dtp(self.attrs.speed)

        if effective_miss_count > 0.0:
            speed_est_breaks[0] = self._calculate_estimated_slider_breaks(
                self.attrs.speed_top_weighted_slider_factor, effective_miss_count
            )
            relevant_miss_count = min(
                effective_miss_count + speed_est_breaks[0],
                self._total_imperfect_hits() + float(self._n_large_tick_miss()),
                )
            speed_value *= self._calculate_miss_penalty(
                relevant_miss_count, self.attrs.speed_difficult_strain_count
            )


        speed_value *= self._calculate_speed_high_deviation_nerf(speed_deviation)

        effective_hit_window = 20.0 * ieee_pow(ieee_div(4.0, self.attrs.speed), 0.35)
        effective_accuracy = erf(ieee_div(effective_hit_window, speed_deviation))
        speed_value *= effective_accuracy * effective_accuracy

        return speed_value

    def _compute_accuracy_value(self) -> float:
        if getattr(self.mods, "rx", False):
            return 0.0

        amount_hit_objects_with_acc = self.attrs.n_circles
        if not self.using_classic_slider_acc:
            amount_hit_objects_with_acc += self.attrs.n_sliders

        hr = self.state.hit_results

        if amount_hit_objects_with_acc > 0:
            n300 = int(hr.n300)
            total_hits = int(hr.total_hits())
            offset = max(total_hits - amount_hit_objects_with_acc, 0)
            better_acc_percentage = (
                                            (n300 - offset) * 6 + hr.n100 * 2 + hr.n50
                                    ) / (amount_hit_objects_with_acc * 6)
        else:
            better_acc_percentage = 0.0

        if better_acc_percentage < 0.0:
            better_acc_percentage = 0.0

        acc_value = (
                math.pow(1.52163, self.attrs.od)
                * math.pow(better_acc_percentage, 24.0)
                * 2.83
        )

        if amount_hit_objects_with_acc < 1000:
            acc_value *= math.pow(amount_hit_objects_with_acc / 1000.0, 0.3)
        else:
            acc_value *= math.pow(amount_hit_objects_with_acc / 1000.0, 0.1)


        return acc_value

    def _compute_flashlight_value(self, effective_miss_count: float) -> float:
        if not getattr(self.mods, "fl", False):
            return 0.0

        flashlight_value = Flashlight.difficulty_to_performance(self.attrs.flashlight)
        total_hits = self._total_hits()

        if effective_miss_count > 0.0 and total_hits > 0:
            flashlight_value *= 0.97 * math.pow(
                1.0 - math.pow(effective_miss_count / total_hits, 0.775),
                math.pow(effective_miss_count, 0.875),
                )

        flashlight_value *= self._get_combo_scaling_factor()
        flashlight_value *= 0.5 + self.acc / 2.0

        return flashlight_value

    def _compute_reading_value(
            self, effective_miss_count: float, aim_est_breaks: list[float]
    ) -> float:
        reading_value = _dtp(self.attrs.reading)

        if effective_miss_count > 0.0:
            reading_value *= self._calculate_miss_penalty(
                effective_miss_count + aim_est_breaks[0],
                self.attrs.reading_difficult_note_count,
            )

        reading_value *= self.acc * self.acc * self.acc

        return reading_value

    def _calculate_combo_based_estimated_miss_count(self) -> float:
        if self.attrs.n_sliders == 0:
            return float(self.state.hit_results.misses)

        miss_count = float(self.state.hit_results.misses)

        if self.using_classic_slider_acc:
            factor = min(self.attrs.aim_top_weighted_slider_factor, 1.0)
            likely_missed_sliderend_portion = 0.04 + 0.06 * (factor * factor)

            full_combo_threshold = float(self.attrs.max_combo) - min(
                4.0 + likely_missed_sliderend_portion * float(self.attrs.n_sliders),
                float(self.attrs.n_sliders),
            )

            if float(self.state.max_combo) < full_combo_threshold:
                miss_count = full_combo_threshold / max(1.0, float(self.state.max_combo))

            miss_count = min(miss_count, self._total_imperfect_hits())

            max_possible_slider_breaks = min(
                self.attrs.n_sliders,
                int((self.attrs.max_combo - self.state.max_combo) / 2),
            )
            slider_breaks = miss_count - float(self.state.hit_results.misses)
            if slider_breaks > float(max_possible_slider_breaks):
                miss_count = float(
                    self.state.hit_results.misses + max_possible_slider_breaks
                )
        else:
            full_combo_threshold = float(
                self.attrs.max_combo - self._n_slider_ends_dropped()
            )
            if float(self.state.max_combo) < full_combo_threshold:
                miss_count = full_combo_threshold / max(float(self.state.max_combo), 1.0)
            miss_count = min(
                miss_count,
                float(self._n_large_tick_miss() + self.state.hit_results.misses),
            )

        return miss_count

    def _calculate_estimated_slider_breaks(
            self, top_weighted_slider_factor: float, effective_miss_count: float
    ) -> float:
        non_miss_mistakes = self.state.hit_results.n100 + self.state.hit_results.n50

        if not self.using_classic_slider_acc or non_miss_mistakes == 0:
            return 0.0

        missed_combo_percent = 1.0 - ieee_div(
            float(self.state.max_combo), float(self.attrs.max_combo)
        )
        estimated_slider_breaks = min(
            float(non_miss_mistakes),
            effective_miss_count * top_weighted_slider_factor,
        )

        non_miss_mistake_adjustment = (
            float(non_miss_mistakes) - estimated_slider_breaks + 4.5
        ) / (float(non_miss_mistakes) + 4.0)

        estimated_slider_breaks *= smoothstep(effective_miss_count, 1.0, 2.0)

        return (
                estimated_slider_breaks
                * non_miss_mistake_adjustment
                * logistic(missed_combo_percent, 0.33, 15.0, None)
        )

    def _calculate_speed_deviation(self) -> Optional[float]:
        if self._total_successful_hits() == 0:
            return None

        hr = self.state.hit_results
        speed_note_count = self.attrs.speed_note_count
        speed_note_count += (float(hr.total_hits()) - self.attrs.speed_note_count) * 0.1

        relevant_count_miss = min(float(hr.misses), speed_note_count)
        relevant_count_meh = min(
            float(hr.n50), speed_note_count - relevant_count_miss
        )
        relevant_count_ok = min(
            float(hr.n100),
            speed_note_count - relevant_count_miss - relevant_count_meh,
            )
        relevant_count_great = max(
            0.0,
            speed_note_count
            - relevant_count_miss
            - relevant_count_meh
            - relevant_count_ok,
            )

        return self._calculate_deviation(
            relevant_count_great, relevant_count_ok, relevant_count_meh
        )

    def _calculate_deviation(
            self,
            relevant_count_great: float,
            relevant_count_ok: float,
            relevant_count_meh: float,
    ) -> Optional[float]:
        if (
                relevant_count_great + relevant_count_ok + relevant_count_meh
                <= 0.0
        ):
            return None

        n = max(1.0, relevant_count_great + relevant_count_ok)
        p = relevant_count_great / n
        Z = 2.32634787404

        p_lower_bound = min(
            (n * p + Z * Z / 2.0) / (n + Z * Z)
            - Z / (n + Z * Z) * math.sqrt(n * p * (1.0 - p) + Z * Z / 4.0),
            p,
            )

        great_hw = self.attrs.great_hit_window
        ok_hw = self.attrs.ok_hit_window
        meh_hw = self.attrs.meh_hit_window

        if p_lower_bound > 0.01 and great_hw > 0:
            inv = erf_inv(p_lower_bound)
            if inv == 0.0:
                deviation = ok_hw / math.sqrt(3.0)
            else:
                deviation = great_hw / (_SQRT2 * inv)
                if ok_hw > 0 and deviation > 0:
                    erf_arg = ok_hw / (_SQRT2 * deviation)
                    erf_val = erf(erf_arg) if erf_arg != 0 else 1.0
                    if erf_val > 0:
                        _q = ok_hw / deviation
                        ok_tail = (
                                math.sqrt(2.0 / math.pi)
                                * ok_hw
                                * math.exp(-0.5 * (_q * _q))
                                / (deviation * erf_val)
                        )
                        if 1.0 - ok_tail > 0:
                            deviation *= math.sqrt(1.0 - ok_tail)
        else:
            deviation = ok_hw / math.sqrt(3.0) if ok_hw > 0 else 0.0

        meh_variance = (
                               meh_hw * meh_hw + ok_hw * meh_hw + ok_hw * ok_hw
                       ) / 3.0

        denom = relevant_count_great + relevant_count_ok + relevant_count_meh
        if denom <= 0:
            return None

        final = math.sqrt(
            (
                    (relevant_count_great + relevant_count_ok) * (deviation * deviation)
                    + relevant_count_meh * meh_variance
            )
            / denom
        )
        return final

    def _calculate_speed_high_deviation_nerf(self, speed_deviation: float) -> float:
        speed_value = _dtp(self.attrs.speed)
        if speed_deviation <= 0:
            return 1.0

        excess_cutoff = 100.0 + 220.0 * math.pow(22.0 / speed_deviation, 6.5)
        if speed_value <= excess_cutoff:
            return 1.0

        SCALE = 50.0
        adjusted = SCALE * (
                math.log((speed_value - excess_cutoff) / SCALE + 1.0)
                + excess_cutoff / SCALE
        )
        t = 1.0 - reverse_lerp(speed_deviation, 22.0, 27.0)
        adjusted = lerp(adjusted, speed_value, t)
        return adjusted / speed_value if speed_value > 0 else 1.0

    @staticmethod
    def _calculate_miss_penalty(miss_count: float, diff_strain_count: float) -> float:
        denom = 4.0 * ieee_ln(diff_strain_count)
        return 0.93 / (ieee_div(miss_count, denom) + 1.0)

    def _get_combo_scaling_factor(self) -> float:
        if self.attrs.max_combo == 0:
            return 1.0
        return min(
            math.pow(float(self.state.max_combo), 0.8)
            / math.pow(float(self.attrs.max_combo), 0.8),
            1.0,
            )

    def _total_hits(self) -> float:
        return float(self.state.hit_results.total_hits())

    def _total_successful_hits(self) -> int:
        hr = self.state.hit_results
        return hr.n300 + hr.n100 + hr.n50

    def _total_imperfect_hits(self) -> float:
        hr = self.state.hit_results
        return float(hr.n100 + hr.n50 + hr.misses)

    def _n_slider_ends_dropped(self) -> int:
        return self.attrs.n_sliders - self.state.hit_results.slider_end_hits

    def _n_large_tick_miss(self) -> int:
        if self.using_classic_slider_acc:
            return 0
        return self.attrs.n_large_ticks - self.state.hit_results.large_tick_hits

def calculate_performance(
        pm: "PerformanceBeatmap",
        attrs: OsuDifficultyAttributes,
        mods: PerformanceMods,
        state: "ScoreState",
        *,
        lazer: bool = True,
        target_accuracy: float | None = None,
        target_misses: int | None = None,
        target_combo: int | None = None,
        explicit_n300: int | None = None,
        explicit_n100: int | None = None,
        explicit_n50: int | None = None,
        explicit_large_tick_hits: int | None = None,
        explicit_small_tick_hits: int | None = None,
        explicit_slider_end_hits: int | None = None,
        priority: HitResultPriority = HitResultPriority.BEST_CASE,
        **_: Any,
) -> OsuPerformanceAttributes:
    using_classic_slider_acc = mods.no_slider_head_acc(lazer)
    if not lazer:
        origin = OsuScoreOrigin.STABLE
    elif using_classic_slider_acc:
        origin = OsuScoreOrigin.WITHOUT_SLIDER_ACC
    else:
        origin = OsuScoreOrigin.WITH_SLIDER_ACC

    osu_state = OsuScoreState(
        max_combo=state.max_combo,
        hit_results=OsuHitResults(
            n300=state.n300,
            n100=state.n100,
            n50=state.n50,
            misses=state.misses,
            large_tick_hits=getattr(state, "osu_large_tick_hits", 0),
            small_tick_hits=getattr(state, "osu_small_tick_hits", 0),
            slider_end_hits=getattr(state, "slider_end_hits", 0),
        ),
        legacy_total_score=getattr(state, "legacy_total_score", None),
    )

    hits_unset = (state.n300 == 0 and state.n100 == 0 and state.n50 == 0)
    no_explicit_hits = (
            explicit_n300 is None and explicit_n100 is None and explicit_n50 is None
    )
    has_target_accuracy = target_accuracy is not None
    need_generation = hits_unset and no_explicit_hits and has_target_accuracy

    if need_generation:
        n_objects = attrs.n_objects()
        target_acc = target_accuracy if target_accuracy is not None else 1.0
        if target_acc > 1.0:
            target_acc = target_acc / 100.0
        misses = target_misses if target_misses is not None else 0

        hit_results = generate_hitresults(
            n_objects=n_objects,
            n_circles=attrs.n_circles,
            n_sliders=attrs.n_sliders,
            n_spinners=attrs.n_spinners,
            n_large_ticks=attrs.n_large_ticks,
            target_acc=target_acc,
            misses=misses,
            n300=explicit_n300,
            n100=explicit_n100,
            n50=explicit_n50,
            combo=target_combo,
            max_combo=attrs.max_combo,
            priority=priority,
            origin=origin,
        )
        osu_state.hit_results = hit_results

    if not need_generation:
        hr = osu_state.hit_results
        remain = attrs.n_objects() - (hr.n300 + hr.n100 + hr.n50 + hr.misses)
        if remain > 0:
            provided_300 = explicit_n300 is not None or not hits_unset
            provided_100 = explicit_n100 is not None or not hits_unset
            provided_50 = explicit_n50 is not None or not hits_unset
            if priority == HitResultPriority.BEST_CASE:
                if not provided_300:
                    hr.n300 += remain
                elif not provided_100:
                    hr.n100 += remain
                elif not provided_50:
                    hr.n50 += remain
                else:
                    hr.n300 += remain
            else:
                if not provided_50:
                    hr.n50 += remain
                elif not provided_100:
                    hr.n100 += remain
                elif not provided_300:
                    hr.n300 += remain
                else:
                    hr.n50 += remain

    actual_misses = osu_state.hit_results.misses
    max_possible_combo = max(0, attrs.max_combo - actual_misses)
    if target_combo is not None:
        osu_state.max_combo = min(target_combo, max_possible_combo)
    elif osu_state.max_combo == 0:
        osu_state.max_combo = max_possible_combo
    else:
        osu_state.max_combo = min(osu_state.max_combo, max_possible_combo)

    if explicit_large_tick_hits is not None:
        osu_state.hit_results.large_tick_hits = explicit_large_tick_hits
    if explicit_small_tick_hits is not None:
        osu_state.hit_results.small_tick_hits = explicit_small_tick_hits
    if explicit_slider_end_hits is not None:
        osu_state.hit_results.slider_end_hits = explicit_slider_end_hits

    if not need_generation:
        if origin == OsuScoreOrigin.WITH_SLIDER_ACC:
            if explicit_large_tick_hits is None:
                osu_state.hit_results.large_tick_hits = attrs.n_large_ticks
            if explicit_slider_end_hits is None:
                osu_state.hit_results.slider_end_hits = attrs.n_sliders
        elif origin == OsuScoreOrigin.WITHOUT_SLIDER_ACC:
            if explicit_large_tick_hits is None:
                osu_state.hit_results.large_tick_hits = (
                    attrs.n_sliders + attrs.n_large_ticks
                )
            if explicit_small_tick_hits is None:
                osu_state.hit_results.small_tick_hits = attrs.n_sliders

    if origin == OsuScoreOrigin.WITHOUT_SLIDER_ACC:
        acc = osu_state.hit_results.accuracy(
            origin,
            max_large_ticks=attrs.n_sliders + attrs.n_large_ticks,
            max_small_ticks=attrs.n_sliders,
        )
    else:
        acc = osu_state.hit_results.accuracy(
            origin,
            max_large_ticks=attrs.n_large_ticks,
            max_small_ticks=0,
            max_slider_ends=attrs.n_sliders,
        )

    calc = OsuPerformanceCalculator(
        attrs=attrs,
        mods=mods,
        acc=acc,
        state=osu_state,
        using_classic_slider_acc=using_classic_slider_acc,
    )
    return calc.calculate()

def performance(
        pm: "PerformanceBeatmap",
        attrs: OsuDifficultyAttributes,
        mods: PerformanceMods,
        **kwargs: Any,
) -> OsuPerformanceAttributes:
    from ...data.score_state import ScoreState
    state = kwargs.pop("state", None) or ScoreState()
    return calculate_performance(pm, attrs, mods, state, **kwargs)