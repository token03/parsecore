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
from typing import Optional

from parsecore.Beatmap.utils import f32

from ...utils import (
    bpm_to_milliseconds,
    clamp,
    lerp,
    logistic,
    logistic_exp,
    millisecods_to_bpm,
    norm,
    reverse_lerp,
    smootherstep,
    smoothstep,
    smoothstep_bell_curve,
)
from .hit_objects import (
    OsuDifficultyObject,
    OsuDifficultyObjects,
    OsuSlider,
)

SECTION_LENGTH_MS: float = 400.0
DECAY_WEIGHT: float = 0.9
REDUCED_SECTION_COUNT: int = 10
REDUCED_STRAIN_BASELINE: float = 0.75

def strain_decay(ms: float, decay_base: float) -> float:
    return math.pow(decay_base, ms / 1000.0)

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def osu_difficulty_value(
        current_strain_peaks: list[float],
        reduced_section_count: int = REDUCED_SECTION_COUNT,
        reduced_strain_baseline: float = REDUCED_STRAIN_BASELINE,
        decay_weight: float = DECAY_WEIGHT,
) -> float:
    peaks = [p for p in current_strain_peaks if p > 0.0]
    strains = sorted(peaks, reverse=True)

    n_reduce = min(reduced_section_count, len(strains))
    for i in range(n_reduce):
        clamped = max(0.0, min(1.0, float(f32(i / reduced_section_count))))
        scale = math.log10(_lerp(1.0, 10.0, clamped))
        strains[i] *= _lerp(reduced_strain_baseline, 1.0, scale)

    strains.sort(reverse=True)

    difficulty = 0.0
    weight = 1.0
    for s in strains:
        difficulty += s * weight
        weight *= decay_weight

    return difficulty

def difficulty_to_performance(difficulty: float) -> float:
    return math.pow(5.0 * max(1.0, difficulty / 0.0675) - 4.0, 3.0) / 100_000.0

def count_top_weighted_strains(strains: list[float], difficulty_value: float) -> float:
    if not strains:
        return 0.0
    consistent_top_strain = difficulty_value / 10.0
    if abs(consistent_top_strain) < 1e-15:
        return float(len(strains))
    total = 0.0
    for s in strains:
        total += 1.1 / (1.0 + math.exp(-10.0 * (s / consistent_top_strain - 0.88)))
    return total

def count_top_weighted_sliders(slider_strains: list[float], difficulty_value: float) -> float:
    if not slider_strains or difficulty_value <= 0.0:
        return 0.0
    consistent_top_strain = difficulty_value / 10.0
    if abs(consistent_top_strain) < 1e-15:
        return 0.0
    total = 0.0
    for s in slider_strains:
        x = s / consistent_top_strain
        total += 1.1 / (1.0 + math.exp(10.0 * (0.88 - x)))
    return total


class _OsuStrainSkill:
    SKILL_MULTIPLIER: float = 1.0
    STRAIN_DECAY_BASE: float = 0.15

    def __init__(self) -> None:
        self._current_section_peak: float = 0.0
        self._current_section_end: float = 0.0
        self._strain_peaks: list[float] = []
        self._object_strains: list[float] = []
        self._current_strain: float = 0.0

    def _strain_value_at(
            self, curr: OsuDifficultyObject, objects: OsuDifficultyObjects
    ) -> float:
        raise NotImplementedError

    def _calculate_initial_strain(
            self,
            time: float,
            curr: OsuDifficultyObject,
            objects: OsuDifficultyObjects,
    ) -> float:
        prev = objects.previous(curr, 0)
        prev_start_time = prev.start_time if prev is not None else 0.0
        return self._current_strain * strain_decay(
            time - prev_start_time, self.STRAIN_DECAY_BASE
        )

    def process(
            self, curr: OsuDifficultyObject, objects: OsuDifficultyObjects
    ) -> None:
        section = SECTION_LENGTH_MS

        if curr.idx == 0:
            self._current_section_end = math.ceil(curr.start_time / section) * section

        while curr.start_time > self._current_section_end:
            self._strain_peaks.append(self._current_section_peak)
            self._current_section_peak = self._calculate_initial_strain(
                self._current_section_end, curr, objects
            )
            self._current_section_end += section

        strain = self._strain_value_at(curr, objects)
        self._current_section_peak = max(strain, self._current_section_peak)
        self._object_strains.append(strain)

    def difficulty_value(self) -> float:
        peaks = list(self._strain_peaks) + [self._current_section_peak]
        return osu_difficulty_value(peaks)

    def count_top_weighted_strains_for(self, diff_value: float) -> float:
        return count_top_weighted_strains(self._object_strains, diff_value)

_AIM_WIDE_ANGLE_MULTIPLIER = 1.5
_AIM_ACUTE_ANGLE_MULTIPLIER = 2.55
_AIM_SLIDER_MULTIPLIER = 1.35
_AIM_VELOCITY_CHANGE_MULTIPLIER = 0.75
_AIM_WIGGLE_MULTIPLIER = 1.02

def _aim_calc_wide_angle_bonus(angle: float) -> float:
    return smoothstep(angle, math.radians(40.0), math.radians(140.0))

def _aim_calc_acute_angle_bonus(angle: float) -> float:
    return smoothstep(angle, math.radians(140.0), math.radians(40.0))

def aim_evaluate_diff_of(
        curr: OsuDifficultyObject,
        objects: OsuDifficultyObjects,
        with_slider_travel_dist: bool,
) -> float:
    last_obj = objects.previous(curr, 0)
    last_last_obj = objects.previous(curr, 1)
    if (
            last_obj is None
            or last_last_obj is None
            or curr.base.is_spinner()
            or last_obj.base.is_spinner()
    ):
        return 0.0

    RADIUS = 50.0
    DIAMETER = 100.0

    curr_vel = curr.lazy_jump_dist / curr.adjusted_delta_time

    if last_obj.base.is_slider() and with_slider_travel_dist:
        travel_vel = last_obj.travel_dist / last_obj.travel_time if last_obj.travel_time > 0 else 0.0
        movement_vel = curr.min_jump_dist / curr.min_jump_time if curr.min_jump_time > 0 else 0.0
        curr_vel = max(curr_vel, movement_vel + travel_vel)

    prev_vel = last_obj.lazy_jump_dist / last_obj.adjusted_delta_time

    if last_last_obj.base.is_slider() and with_slider_travel_dist:
        travel_vel = last_last_obj.travel_dist / last_last_obj.travel_time if last_last_obj.travel_time > 0 else 0.0
        movement_vel = last_obj.min_jump_dist / last_obj.min_jump_time if last_obj.min_jump_time > 0 else 0.0
        prev_vel = max(prev_vel, movement_vel + travel_vel)

    wide_angle_bonus = 0.0
    acute_angle_bonus = 0.0
    slider_bonus = 0.0
    vel_change_bonus = 0.0
    wiggle_bonus = 0.0

    aim_strain = curr_vel

    if curr.angle is not None and last_obj.angle is not None:
        curr_angle = curr.angle
        last_angle = last_obj.angle
        angle_bonus = min(curr_vel, prev_vel)

        if max(curr.adjusted_delta_time, last_obj.adjusted_delta_time) < 1.25 * min(
                curr.adjusted_delta_time, last_obj.adjusted_delta_time
        ):
            acute_angle_bonus = _aim_calc_acute_angle_bonus(curr_angle)
            acute_angle_bonus *= 0.08 + 0.92 * (
                    1.0
                    - min(
                acute_angle_bonus,
                math.pow(_aim_calc_acute_angle_bonus(last_angle), 3.0),
            )
            )
            acute_angle_bonus *= (
                    angle_bonus
                    * smootherstep(
                millisecods_to_bpm(curr.adjusted_delta_time, 2),
                300.0,
                400.0,
            )
                    * smootherstep(curr.lazy_jump_dist, DIAMETER, DIAMETER * 2)
            )

        wide_angle_bonus = _aim_calc_wide_angle_bonus(curr_angle)
        wide_angle_bonus *= 1.0 - min(
            wide_angle_bonus,
            math.pow(_aim_calc_wide_angle_bonus(last_angle), 3.0),
        )
        wide_angle_bonus *= angle_bonus * smootherstep(
            curr.lazy_jump_dist, 0.0, DIAMETER
        )

        wiggle_bonus = (
                angle_bonus
                * smootherstep(curr.lazy_jump_dist, RADIUS, DIAMETER)
                * math.pow(
            reverse_lerp(curr.lazy_jump_dist, DIAMETER * 3, DIAMETER), 1.8
        )
                * smootherstep(curr_angle, math.radians(110.0), math.radians(60.0))
                * smootherstep(last_obj.lazy_jump_dist, RADIUS, DIAMETER)
                * math.pow(
            reverse_lerp(last_obj.lazy_jump_dist, DIAMETER * 3, DIAMETER), 1.8
        )
                * smootherstep(last_angle, math.radians(110.0), math.radians(60.0))
        )

        last_2_obj = objects.previous(curr, 2)
        if last_2_obj is not None:
            sp_a = last_2_obj.base.stacked_pos()
            sp_b = last_obj.base.stacked_pos()
            dx = sp_a.x - sp_b.x
            dy = sp_a.y - sp_b.y
            distance = math.sqrt(dx * dx + dy * dy)
            if distance < 1.0:
                wide_angle_bonus *= 1.0 - 0.35 * (1.0 - distance)

    if max(prev_vel, curr_vel) > 1e-15:
        prev_vel = (
                (last_obj.lazy_jump_dist + last_last_obj.travel_dist)
                / last_obj.adjusted_delta_time
        )
        curr_vel = (
                (curr.lazy_jump_dist + last_obj.travel_dist)
                / curr.adjusted_delta_time
        )
        denom = max(prev_vel, curr_vel)
        dist_ratio = smoothstep(abs(prev_vel - curr_vel) / denom, 0.0, 1.0) if denom > 0 else 0.0
        min_dt = min(curr.adjusted_delta_time, last_obj.adjusted_delta_time)
        overlap_vel_buff = min(
            DIAMETER * 1.25 / min_dt if min_dt > 0 else 0.0,
            abs(prev_vel - curr_vel),
        )
        vel_change_bonus = overlap_vel_buff * dist_ratio
        max_dt = max(curr.adjusted_delta_time, last_obj.adjusted_delta_time)
        bonus_base = (
            min(curr.adjusted_delta_time, last_obj.adjusted_delta_time) / max_dt
            if max_dt > 0 else 0.0
        )
        vel_change_bonus *= math.pow(bonus_base, 2.0)

    if last_obj.base.is_slider() and last_obj.travel_time > 0:
        slider_bonus = last_obj.travel_dist / last_obj.travel_time

    aim_strain += wiggle_bonus * _AIM_WIGGLE_MULTIPLIER
    aim_strain += vel_change_bonus * _AIM_VELOCITY_CHANGE_MULTIPLIER
    aim_strain += max(
        acute_angle_bonus * _AIM_ACUTE_ANGLE_MULTIPLIER,
        wide_angle_bonus * _AIM_WIDE_ANGLE_MULTIPLIER,
        )
    aim_strain *= curr.small_circle_bonus
    if with_slider_travel_dist:
        aim_strain += slider_bonus * _AIM_SLIDER_MULTIPLIER

    return aim_strain

class Aim(_OsuStrainSkill):
    SKILL_MULTIPLIER = 26.0
    STRAIN_DECAY_BASE = 0.15

    def __init__(self, include_sliders: bool = True) -> None:
        super().__init__()
        self.include_sliders = include_sliders
        self._slider_strains: list[float] = []

    def _strain_value_at(
            self, curr: OsuDifficultyObject, objects: OsuDifficultyObjects
    ) -> float:
        self._current_strain *= strain_decay(curr.delta_time, self.STRAIN_DECAY_BASE)
        self._current_strain += (
                aim_evaluate_diff_of(curr, objects, self.include_sliders)
                * self.SKILL_MULTIPLIER
        )
        if curr.base.is_slider():
            self._slider_strains.append(self._current_strain)
        return self._current_strain

    def get_difficult_sliders(self) -> float:
        if not self._slider_strains:
            return 0.0
        max_strain = max(self._slider_strains)
        if max_strain <= 0:
            return 0.0
        return sum(
            1.0 / (1.0 + math.exp(-(s / max_strain * 12.0 - 6.0)))
            for s in self._slider_strains
        )

    @property
    def slider_strains(self) -> list[float]:
        return self._slider_strains

_SPEED_SINGLE_SPACING_THRESHOLD = 100.0 * 1.25
_SPEED_MIN_SPEED_BONUS = 200.0
_SPEED_BALANCING_FACTOR = 40.0
_SPEED_DIST_MULTIPLIER = 0.8

def _speed_high_bpm_bonus(ms: float) -> float:
    return 1.0 / (1.0 - math.pow(0.3, ms / 1000.0))


def speed_evaluate_diff_of(
        curr: OsuDifficultyObject,
        objects: OsuDifficultyObjects,
        hit_window_great: float,
) -> float:
    if curr.base.is_spinner():
        return 0.0

    min_speed_bonus = 200.0
    speed_balancing_factor = 40.0

    strain_time = curr.adjusted_delta_time
    next_obj = objects.next(curr, 0)
    double_tap_feasibility = 1.0 - curr.calculate_double_tap_feasibility(
        next_obj, hit_window_great
    )

    strain_time /= clamp((strain_time / hit_window_great) / 0.93, 0.92, 1.0)

    speed_bonus = 0.0
    if millisecods_to_bpm(strain_time, None) > min_speed_bonus:
        base = (
            bpm_to_milliseconds(min_speed_bonus, None) - strain_time
        ) / speed_balancing_factor
        speed_bonus = 0.75 * (base * base)

    speed_difficulty = (1.0 + speed_bonus) * 1000.0 / strain_time
    speed_difficulty *= _speed_high_bpm_bonus(curr.adjusted_delta_time)

    return speed_difficulty * double_tap_feasibility

_RHYTHM_HISTORY_TIME_MAX = 5 * 1000
_RHYTHM_HISTORY_OBJECTS_MAX = 32
_RHYTHM_OVERALL_MULTIPLIER = 0.95
_RHYTHM_MIN_DELTA_TIME = 25
_I32_MAX = 2147483647


class _Island:
    __slots__ = ("delta", "delta_count", "occurrences")

    def __init__(self, delta: int) -> None:
        self.delta = max(delta, _RHYTHM_MIN_DELTA_TIME)
        self.delta_count = 1
        self.occurrences = 1

    def add_delta(self, delta: int) -> None:
        if self.delta == _I32_MAX:
            self.delta = max(delta, _RHYTHM_MIN_DELTA_TIME)
        self.delta_count += 1

    def is_similar_polarity(self, other: "_Island", epsilon: float) -> bool:
        if self.delta_count <= 1 or other.delta_count <= 1:
            return False
        return (
            abs(self.delta - other.delta) < epsilon
            and self.delta_count % 2 == other.delta_count % 2
        )

    def almost_equals(self, other: "_Island", epsilon: float) -> bool:
        return (
            abs(self.delta - other.delta) < epsilon
            and self.delta_count == other.delta_count
        )


def _rhythm_get_effective_difficulty(delta_difference_ratio: float) -> float:
    rhythm_ratio_difficulty_multiplier = 26.0
    delta_difference_fraction = delta_difference_ratio - math.trunc(delta_difference_ratio)
    return 1.0 + rhythm_ratio_difficulty_multiplier * min(
        0.5, smoothstep_bell_curve(delta_difference_fraction)
    )


def rhythm_evaluate_diff_of(
        curr: OsuDifficultyObject,
        objects: OsuDifficultyObjects,
        hit_window_great: float,
) -> float:
    if curr.base.is_spinner():
        return 0.0

    history_time_max = 5 * 1000
    history_objects_max = 32
    rhythm_overall_multiplier = _RHYTHM_OVERALL_MULTIPLIER

    rhythm_complexity_sum = 0.0
    delta_difference_epsilon = hit_window_great * 0.3

    island = _Island(_I32_MAX)
    previous_island = _Island(_I32_MAX)
    islands: list[_Island] = []

    start_difficulty = 0.0
    first_delta_switch = False

    historical_note_count = min(curr.idx, history_objects_max)

    rhythm_start = 0
    while (
        rhythm_start < historical_note_count - 2
        and curr.start_time - objects.previous(curr, rhythm_start).start_time
        < history_time_max
    ):
        rhythm_start += 1

    prev_obj = objects.previous(curr, rhythm_start)
    prev_prev_obj = objects.previous(curr, rhythm_start + 1)

    for i in range(rhythm_start, 0, -1):
        curr_obj = objects.previous(curr, i - 1)

        if curr_obj.base.is_spinner():
            continue

        time_decay = (
            history_time_max - (curr.start_time - curr_obj.start_time)
        ) / history_time_max
        note_decay = (historical_note_count - i) / historical_note_count
        curr_historical_decay = min(note_decay, time_decay)

        delta_min_value = 1e-7
        curr_delta = max(curr_obj.delta_time, delta_min_value)
        prev_delta = max(prev_obj.delta_time, delta_min_value)

        delta_difference = abs(prev_delta - curr_delta)

        if island.delta == _I32_MAX:
            island = _Island(int(curr_delta))

        delta_difference_ratio = max(prev_delta, curr_delta) / min(prev_delta, curr_delta)
        difference_multiplier = clamp(2.0 - delta_difference_ratio / 8.0, 0.0, 1.0)
        window_penalty = clamp(
            (delta_difference - delta_difference_epsilon) / delta_difference_epsilon,
            0.0,
            1.0,
        )

        effective_difficulty = (
            _rhythm_get_effective_difficulty(delta_difference_ratio)
            * window_penalty
            * difference_multiplier
        )

        if prev_obj.base.is_slider():
            slider_lazy_end_delta = curr_obj.min_jump_time
            slider_lazy_ratio = max(slider_lazy_end_delta, curr_delta) / min(
                slider_lazy_end_delta, curr_delta
            )
            slider_real_end_delta = curr_obj.last_object_end_delta_time
            slider_real_ratio = max(slider_real_end_delta, curr_delta) / min(
                slider_real_end_delta, curr_delta
            )
            slider_effective_difficulty = min(
                _rhythm_get_effective_difficulty(slider_lazy_ratio),
                _rhythm_get_effective_difficulty(slider_real_ratio),
            )
            effective_difficulty = min(slider_effective_difficulty, effective_difficulty)

        if delta_difference < delta_difference_epsilon:
            island.add_delta(int(curr_delta))

        if first_delta_switch:
            if delta_difference > delta_difference_epsilon:
                if curr_obj.base.is_slider():
                    effective_difficulty *= 0.5
                if island.is_similar_polarity(previous_island, delta_difference_epsilon):
                    effective_difficulty *= 0.5
                if (
                    max(prev_prev_obj.delta_time, delta_min_value)
                    > prev_delta + delta_difference_epsilon
                    and prev_delta > curr_delta + delta_difference_epsilon
                ):
                    effective_difficulty *= 0.125
                if previous_island.delta_count == island.delta_count:
                    effective_difficulty *= 0.5

                is_speeding_up = prev_delta > curr_delta + delta_difference_epsilon
                if is_speeding_up:
                    effective_difficulty *= 0.65

                found = False
                for existing_island in islands:
                    if existing_island.almost_equals(island, delta_difference_epsilon):
                        if previous_island.almost_equals(island, delta_difference_epsilon):
                            existing_island.occurrences += 1
                        power = logistic(island.delta, 58.33, 0.24, 2.75)
                        effective_difficulty *= min(
                            3.0 / existing_island.occurrences,
                            math.pow(1.0 / existing_island.occurrences, power),
                        )
                        found = True
                        break

                if not found and island.delta_count > 0:
                    islands.append(island)

                effective_difficulty *= (
                    1.0
                    - prev_obj.calculate_double_tap_feasibility(curr_obj, hit_window_great)
                    * 0.75
                )

                if island.delta_count > 1:
                    rhythm_complexity_sum += (
                        math.sqrt(effective_difficulty * start_difficulty)
                        * curr_historical_decay
                    )
                else:
                    rhythm_complexity_sum += 0.7 * curr_historical_decay

                start_difficulty = effective_difficulty

                if prev_delta + delta_difference_epsilon < curr_delta:
                    first_delta_switch = False

                previous_island = island
                island = _Island(int(curr_delta))
        elif prev_delta > curr_delta + delta_difference_epsilon:
            first_delta_switch = True

            if curr_obj.base.is_slider():
                effective_difficulty *= 0.6
            if prev_obj.base.is_slider():
                effective_difficulty *= 0.6

            start_difficulty = effective_difficulty
            island = _Island(int(curr_delta))

        prev_prev_obj = prev_obj
        prev_obj = curr_obj

    rhythm_complexity_sum *= reverse_lerp(island.delta_count, 22, 3)

    return math.sqrt(4.0 + rhythm_complexity_sum * rhythm_overall_multiplier) / 2.0


_FL_MAX_OPACITY_BONUS = 0.4
_FL_HIDDEN_BONUS = 0.2
_FL_MIN_VELOCITY = 0.5
_FL_SLIDER_MULTIPLIER = 1.3
_FL_MIN_ANGLE_MULTIPLIER = 0.2

def flashlight_evaluate_diff_of(
        curr: OsuDifficultyObject,
        objects: OsuDifficultyObjects,
        hidden_for_opacity: bool,
        has_any_hidden: bool,
        scaling_factor: float,
        raw_preempt: float,
        fade_in: float,
) -> float:
    if curr.base.is_spinner():
        return 0.0

    small_dist_nerf = 1.0
    cumulative_strain_time = 0.0
    result = 0.0
    last_obj = curr
    angle_repeat_count = 0.0

    for i in range(min(curr.idx, 10)):
        curr_obj = objects.previous(curr, i)

        cumulative_strain_time += last_obj.adjusted_delta_time
        curr_hit_obj = curr_obj.base

        if not curr_obj.base.is_spinner():
            jump_dist = (
                curr.base.stacked_pos() - curr_hit_obj.stacked_end_pos()
            ).length()

            if i == 0:
                small_dist_nerf = min(jump_dist / 75.0, 1.0)

            stack_nerf = min((curr_obj.lazy_jump_dist / scaling_factor) / 25.0, 1.0)

            opacity_bonus = 1.0 + _FL_MAX_OPACITY_BONUS * (
                1.0
                - curr.opacity_at(
                    curr_hit_obj.start_time, hidden_for_opacity, raw_preempt, fade_in
                )
            )

            result += (
                stack_nerf * opacity_bonus * scaling_factor * jump_dist
                / cumulative_strain_time
            )

            if curr_obj.angle is not None and curr.angle is not None:
                if abs(curr_obj.angle - curr.angle) < 0.02:
                    angle_repeat_count += max(1.0 - 0.1 * i, 0.0)

        last_obj = curr_obj

    _v = small_dist_nerf * result
    result = _v * _v
    if has_any_hidden:
        result *= 1.0 + _FL_HIDDEN_BONUS
    result *= (
        _FL_MIN_ANGLE_MULTIPLIER
        + (1.0 - _FL_MIN_ANGLE_MULTIPLIER) / (angle_repeat_count + 1.0)
    )

    slider_bonus = 0.0
    if isinstance(curr.base.kind, OsuSlider):
        slider = curr.base.kind
        pixel_travel_dist = curr.lazy_travel_dist / scaling_factor
        slider_bonus = math.pow(
            max(pixel_travel_dist / curr.travel_time - _FL_MIN_VELOCITY, 0.0), 0.5
        )
        slider_bonus *= pixel_travel_dist
        repeat_count = slider.repeat_count()
        if repeat_count > 0:
            slider_bonus /= repeat_count + 1

    result += slider_bonus * _FL_SLIDER_MULTIPLIER
    return result


class Flashlight(_OsuStrainSkill):
    SKILL_MULTIPLIER = 0.058
    STRAIN_DECAY_BASE = 0.15

    def __init__(
            self,
            hidden_for_opacity: bool,
            has_any_hidden: bool,
            radius: float,
            raw_preempt: float,
            fade_in: float,
            overall_difficulty: float,
            total_objects: int,
            has_touch_device: bool = False,
            has_relax: bool = False,
            has_autopilot: bool = False,
    ) -> None:
        super().__init__()
        self._hidden_for_opacity = hidden_for_opacity
        self._has_any_hidden = has_any_hidden
        self.scaling_factor = 52.0 / radius
        self._raw_preempt = raw_preempt
        self._fade_in = fade_in
        self._overall_difficulty = overall_difficulty
        self._total_objects = total_objects
        self._has_touch_device = has_touch_device
        self._has_relax = has_relax
        self._has_autopilot = has_autopilot

    def _strain_value_at(
            self, curr: OsuDifficultyObject, objects: OsuDifficultyObjects
    ) -> float:
        self._current_strain *= strain_decay(curr.delta_time, self.STRAIN_DECAY_BASE)
        self._current_strain += (
            self._calculate_adjusted_difficulty(curr, objects) * self.SKILL_MULTIPLIER
        )
        return self._current_strain

    def _calculate_adjusted_difficulty(
            self, curr: OsuDifficultyObject, objects: OsuDifficultyObjects
    ) -> float:
        difficulty = flashlight_evaluate_diff_of(
            curr, objects, self._hidden_for_opacity, self._has_any_hidden,
            self.scaling_factor, self._raw_preempt, self._fade_in,
        )
        if self._has_touch_device:
            difficulty = math.pow(difficulty, 0.9)
        if self._has_relax:
            difficulty *= 0.7
        if self._has_autopilot:
            difficulty *= 0.4
        difficulty *= 0.985 + math.pow(max(0.0, self._overall_difficulty), 2) / 4000.0
        return difficulty

    def difficulty_value(self) -> float:
        peaks = list(self._strain_peaks) + [self._current_section_peak]
        s = sum(peaks)
        total = self._total_objects
        s *= (
            0.7
            + 0.1 * min(1.0, total / 200.0)
            + (0.2 * min(1.0, (total - 200) / 200.0) if total > 200 else 0.0)
        )
        return s

    @staticmethod
    def difficulty_to_performance(difficulty: float) -> float:
        return 25.0 * (difficulty * difficulty)


_READING_WINDOW_SIZE: float = 3000.0
_READING_DISTANCE_INFLUENCE_THRESHOLD: float = 100.0 * 1.5
_READING_NORMALISED_RADIUS: float = 50.0


def _reading_time_nerf_factor(delta_time: float) -> float:
    return clamp(2.0 - delta_time / (_READING_WINDOW_SIZE / 2.0), 0.0, 1.0)


def _reading_high_bpm_bonus(ms: float) -> float:
    return 1.0 / (1.0 - math.pow(0.8, ms / 1000.0))


def _reading_past_visible_objects(
        curr: OsuDifficultyObject, objects: OsuDifficultyObjects, preempt: float
) -> list[OsuDifficultyObject]:
    result: list[OsuDifficultyObject] = []
    for i in range(curr.idx):
        obj = objects.previous(curr, i)
        if (
            obj is None
            or curr.start_time - obj.start_time > _READING_WINDOW_SIZE
            or obj.start_time < curr.start_time - preempt
        ):
            break
        result.append(obj)
    return result


def _reading_past_influence(
        curr: OsuDifficultyObject,
        objects: OsuDifficultyObjects,
        preempt: float,
        raw_preempt: float,
        fade_in: float,
) -> float:
    influence = 0.0
    for loop in _reading_past_visible_objects(curr, objects, preempt):
        d = curr.opacity_at(loop.base.start_time, False, raw_preempt, fade_in)
        d *= smootherstep(
            loop.lazy_jump_dist, 15.0, _READING_DISTANCE_INFLUENCE_THRESHOLD
        )
        d *= _reading_time_nerf_factor(curr.start_time - loop.start_time)
        influence += d
    return influence


def _reading_current_visible_density(
        curr: OsuDifficultyObject,
        objects: OsuDifficultyObjects,
        preempt: float,
        raw_preempt: float,
        fade_in: float,
) -> float:
    count = 0.0
    obj = objects.next(curr, 0)
    while obj is not None:
        if (
            obj.start_time - curr.start_time > _READING_WINDOW_SIZE
            or curr.start_time < obj.start_time - preempt
        ):
            break
        time_between = obj.start_time - curr.start_time
        count += (
            obj.opacity_at(curr.base.start_time, False, raw_preempt, fade_in)
            * _reading_time_nerf_factor(time_between)
        )
        obj = objects.next(obj, 0)
    return count


def _reading_constant_angle_nerf_factor(
        curr: OsuDifficultyObject, objects: OsuDifficultyObjects
) -> float:
    minimum_angle_relevancy_time = 2000.0
    maximum_angle_relevancy_time = 200.0

    constant_angle_count = 0.0
    index = 0
    current_time_gap = 0.0

    loop_prev0: OsuDifficultyObject = curr
    loop_prev1: Optional[OsuDifficultyObject] = None
    loop_prev2: Optional[OsuDifficultyObject] = None

    while current_time_gap < minimum_angle_relevancy_time:
        loop = objects.previous(curr, index)
        if loop is None:
            break

        long_interval_factor = 1.0 - reverse_lerp(
            loop.adjusted_delta_time,
            maximum_angle_relevancy_time,
            minimum_angle_relevancy_time,
        )

        if loop.angle is not None and curr.angle is not None:
            angle_difference = abs(curr.angle - loop.angle)
            angle_difference_alternating = math.pi

            if (
                loop_prev0.angle is not None
                and loop_prev1 is not None
                and loop_prev1.angle is not None
                and loop_prev2 is not None
                and loop_prev2.angle is not None
            ):
                angle_difference_alternating = abs(loop_prev1.angle - loop.angle)
                angle_difference_alternating += abs(
                    loop_prev2.angle - loop_prev0.angle
                )

                weight = 1.0
                weight *= reverse_lerp(
                    min(loop.angle, loop_prev0.angle) * 180.0 / math.pi, 20.0, 5.0
                )
                weight *= reverse_lerp(
                    max(loop.angle, loop_prev0.angle) * 180.0 / math.pi, 60.0, 120.0
                )
                angle_difference_alternating = lerp(
                    math.pi, 0.1 * angle_difference_alternating, weight
                )

            stack_factor = smootherstep(
                loop.lazy_jump_dist, 0.0, _READING_NORMALISED_RADIUS
            )
            constant_angle_count += (
                math.cos(
                    3.0
                    * min(
                        math.radians(30.0),
                        min(angle_difference, angle_difference_alternating)
                        * stack_factor,
                    )
                )
                * long_interval_factor
            )

        current_time_gap = curr.start_time - loop.start_time
        index += 1
        loop_prev2 = loop_prev1
        loop_prev1 = loop_prev0
        loop_prev0 = loop

    if constant_angle_count == 0.0:
        return 1.0
    return clamp(2.0 / constant_angle_count, 0.2, 1.0)


def _reading_density_difficulty(
        next_obj: Optional[OsuDifficultyObject],
        velocity: float,
        constant_angle_nerf: float,
        past_influence: float,
        current_visible_density: float,
) -> float:
    density_multiplier = 2.4
    density_difficulty_base = 2.5

    future = math.sqrt(current_visible_density)
    if next_obj is not None:
        future *= smootherstep(
            next_obj.lazy_jump_dist, 15.0, _READING_DISTANCE_INFLUENCE_THRESHOLD
        )

    value = (
        math.pow(past_influence + future, 1.7)
        * 0.4
        * constant_angle_nerf
        * velocity
    )
    value = max(0.0, value - density_difficulty_base)
    value = math.pow(value, 0.45) * density_multiplier
    return value


def _reading_preempt_difficulty(
        velocity: float, constant_angle_nerf: float, preempt: float
) -> float:
    preempt_balancing_factor = 140000.0
    preempt_starting_point = 500.0
    value = (
        math.pow(
            (preempt_starting_point - preempt + abs(preempt - preempt_starting_point))
            / 2.0,
            2.5,
        )
        / preempt_balancing_factor
    )
    value *= constant_angle_nerf * velocity
    return value


def _reading_hidden_difficulty(
        curr: OsuDifficultyObject,
        objects: OsuDifficultyObjects,
        past_influence: float,
        current_visible_density: float,
        velocity: float,
        constant_angle_nerf: float,
        preempt: float,
        raw_preempt: float,
        fade_in: float,
) -> float:
    hidden_multiplier = 0.28

    preempt_factor = math.pow(preempt, 2.2) * 0.01
    density_factor = math.pow(current_visible_density + past_influence, 3.3) * 3.0

    value = (preempt_factor + density_factor) * constant_angle_nerf * velocity * 0.01
    value = math.pow(value, 0.4) * hidden_multiplier

    prev = objects.previous(curr, 0)
    if (
        prev is not None
        and curr.lazy_jump_dist == 0
        and curr.opacity_at(prev.base.start_time, True, raw_preempt, fade_in) == 0
        and prev.start_time > curr.start_time - preempt
    ):
        value += hidden_multiplier * 2500.0 / math.pow(curr.adjusted_delta_time, 1.5)

    return value


def reading_evaluate_diff_of(
        curr: OsuDifficultyObject,
        objects: OsuDifficultyObjects,
        hidden: bool,
        preempt: float,
        raw_preempt: float,
        fade_in: float,
) -> float:
    if curr.base.is_spinner() or curr.idx == 0:
        return 0.0

    next_obj = objects.next(curr, 0)

    velocity = max(1.0, curr.lazy_jump_dist / curr.adjusted_delta_time)

    current_visible_density = _reading_current_visible_density(
        curr, objects, preempt, raw_preempt, fade_in
    )
    past_influence = _reading_past_influence(
        curr, objects, preempt, raw_preempt, fade_in
    )
    constant_angle_nerf = _reading_constant_angle_nerf_factor(curr, objects)

    note_density_difficulty = _reading_density_difficulty(
        next_obj, velocity, constant_angle_nerf, past_influence, current_visible_density
    )

    hidden_difficulty = (
        _reading_hidden_difficulty(
            curr, objects, past_influence, current_visible_density,
            velocity, constant_angle_nerf, preempt, raw_preempt, fade_in,
        )
        if hidden
        else 0.0
    )

    preempt_difficulty = _reading_preempt_difficulty(
        velocity, constant_angle_nerf, preempt
    )

    reading_difficulty = norm(
        1.5, [preempt_difficulty, hidden_difficulty, note_density_difficulty]
    )

    reading_difficulty *= _reading_high_bpm_bonus(curr.adjusted_delta_time)

    return reading_difficulty


class _HarmonicSkill:
    HARMONIC_SCALE: float = 1.0
    DECAY_EXPONENT: float = 0.9

    def __init__(self) -> None:
        self._object_difficulties: list[float] = []
        self._object_weight_sum: float = 0.0

    def _object_difficulty_of(
            self, curr: OsuDifficultyObject, objects: OsuDifficultyObjects
    ) -> float:
        raise NotImplementedError

    def process(
            self, curr: OsuDifficultyObject, objects: OsuDifficultyObjects
    ) -> None:
        self._object_difficulties.append(self._object_difficulty_of(curr, objects))

    def _get_transformed_difficulties(self, difficulties: list[float]) -> list[float]:
        return difficulties

    def difficulty_value(self) -> float:
        if not self._object_difficulties:
            return 0.0

        difficulties = self._get_transformed_difficulties(
            list(self._object_difficulties)
        )
        ordered = sorted((v for v in difficulties if v > 0.0), reverse=True)

        difficulty = 0.0
        index = 0
        for obj in ordered:
            weight = (1.0 + (self.HARMONIC_SCALE / (1.0 + index))) / (
                math.pow(index, self.DECAY_EXPONENT)
                + 1.0
                + (self.HARMONIC_SCALE / (1.0 + index))
            )
            self._object_weight_sum += weight
            difficulty += obj * weight
            index += 1

        return difficulty

    def count_top_weighted_object_difficulties(self, difficulty_value: float) -> float:
        if not self._object_difficulties or self._object_weight_sum == 0.0:
            return 0.0
        consistent_top = difficulty_value / self._object_weight_sum
        if consistent_top == 0.0:
            return 0.0
        return sum(
            logistic(d / consistent_top, 0.88, 10.0, 1.1)
            for d in self._object_difficulties
        )

    @staticmethod
    def difficulty_to_performance(difficulty: float) -> float:
        return 4.0 * (difficulty * difficulty * difficulty)


class Reading(_HarmonicSkill):
    SKILL_MULTIPLIER: float = 2.5

    def __init__(
            self,
            has_hidden: bool,
            preempt: float,
            raw_preempt: float,
            fade_in: float,
            overall_difficulty: float,
            mods,
    ) -> None:
        super().__init__()
        self._has_hidden = has_hidden
        self._preempt = preempt
        self._raw_preempt = raw_preempt
        self._fade_in = fade_in
        self._overall_difficulty = overall_difficulty
        self._mods = mods
        self._object_list: list[OsuDifficultyObject] = []
        self._current_strain: float = 0.0

    @staticmethod
    def _strain_decay(ms: float) -> float:
        return math.pow(0.8, ms / 1000.0)

    def _object_difficulty_of(
            self, curr: OsuDifficultyObject, objects: OsuDifficultyObjects
    ) -> float:
        self._object_list.append(curr)
        decay = self._strain_decay(curr.delta_time)
        self._current_strain *= decay
        self._current_strain += (
            self._calculate_adjusted_difficulty(curr, objects)
            * (1.0 - decay)
            * self.SKILL_MULTIPLIER
        )
        return self._current_strain

    def _calculate_adjusted_difficulty(
            self, curr: OsuDifficultyObject, objects: OsuDifficultyObjects
    ) -> float:
        difficulty = reading_evaluate_diff_of(
            curr, objects, self._has_hidden,
            self._preempt, self._raw_preempt, self._fade_in,
        )

        if getattr(self._mods, "td", False):
            difficulty = math.pow(difficulty, 0.89)
        if getattr(self._mods, "rx", False):
            difficulty *= 0.4
        if getattr(self._mods, "ap", False):
            difficulty *= 0.1

        difficulty *= (
            0.825 + math.pow(max(0.0, self._overall_difficulty), 2.2) / 1125.0
        )

        return difficulty

    def _calculate_reduced_note_count(self) -> int:
        reduced_difficulty_duration = 60 * 1000
        if not self._object_list:
            return 0
        reduced_duration = self._object_list[0].start_time + reduced_difficulty_duration
        count = 0
        for obj in self._object_list:
            if obj.start_time > reduced_duration:
                break
            count += 1
        return count

    def _get_transformed_difficulties(self, difficulties: list[float]) -> list[float]:
        difficulties = [v for v in difficulties if v > 0.0]
        reduced_difficulty_base_line = 0.0
        reduced_note_count = self._calculate_reduced_note_count()
        for i in range(min(len(difficulties), reduced_note_count)):
            scale = math.log10(
                _lerp(1.0, 10.0, clamp(i / reduced_note_count, 0.0, 1.0))
            )
            difficulties[i] *= _lerp(reduced_difficulty_base_line, 1.0, scale)
        return difficulties

    def count_top_weighted_object_difficulties(self, difficulty_value: float) -> float:
        if not self._object_difficulties or self._object_weight_sum == 0.0:
            return 0.0
        consistent_top = difficulty_value / self._object_weight_sum
        if consistent_top == 0.0:
            return 0.0
        return sum(
            logistic(d / consistent_top, 1.15, 5.0, 1.1)
            for d in self._object_difficulties
        )


class Speed(_HarmonicSkill):
    HARMONIC_SCALE: float = 20.0
    DECAY_EXPONENT: float = 0.9
    SKILL_MULTIPLIER: float = 1.16

    def __init__(
            self,
            hit_window_great: float,
            has_relax: bool = False,
            has_autopilot: bool = False,
    ) -> None:
        super().__init__()
        self._hit_window_great = hit_window_great
        self._has_relax = has_relax
        self._has_autopilot = has_autopilot
        self._current_strain: float = 0.0
        self._slider_strains: list[float] = []

    @staticmethod
    def _strain_decay(ms: float) -> float:
        return math.pow(0.3, ms / 1000.0)

    def _object_difficulty_of(
            self, curr: OsuDifficultyObject, objects: OsuDifficultyObjects
    ) -> float:
        if self._has_relax:
            return 0.0

        decay = self._strain_decay(curr.adjusted_delta_time)
        self._current_strain *= decay
        self._current_strain += (
            self._calculate_adjusted_difficulty(curr, objects)
            * (1.0 - decay)
            * self.SKILL_MULTIPLIER
        )

        current_rhythm = rhythm_evaluate_diff_of(curr, objects, self._hit_window_great)
        total_strain = self._current_strain * current_rhythm

        if curr.base.is_slider():
            self._slider_strains.append(total_strain)

        return total_strain

    def _calculate_adjusted_difficulty(
            self, curr: OsuDifficultyObject, objects: OsuDifficultyObjects
    ) -> float:
        difficulty = speed_evaluate_diff_of(curr, objects, self._hit_window_great)
        if self._has_autopilot:
            difficulty *= 0.5
        return difficulty

    def relevant_object_count(self) -> float:
        if not self._object_difficulties:
            return 0.0
        max_strain = max(self._object_difficulties)
        if max_strain == 0.0:
            return 0.0
        return sum(
            1.0 / (1.0 + math.exp(-(s / max_strain * 12.0 - 6.0)))
            for s in self._object_difficulties
        )

    def count_top_weighted_sliders(self, difficulty_value: float) -> float:
        if not self._slider_strains or self._object_weight_sum == 0.0:
            return 0.0
        consistent_top = difficulty_value / self._object_weight_sum
        if consistent_top == 0.0:
            return 0.0
        return sum(
            logistic(s / consistent_top, 0.88, 10.0, 1.1)
            for s in self._slider_strains
        )


_AIM_NORMALISED_RADIUS = 50.0
_AIM_NORMALISED_DIAMETER = 100.0


def _calc_angle_wideness(angle: float) -> float:
    return smoothstep(angle, math.radians(40.0), math.radians(140.0))


def _calc_angle_acuteness(angle: float) -> float:
    return smoothstep(angle, math.radians(140.0), math.radians(40.0))


class _StrainPeak:
    __slots__ = ("value", "section_length")

    def __init__(self, value: float, section_length: float) -> None:
        self.value = value
        self.section_length = round(section_length)


class _VariableLengthStrainSkill:
    def __init__(self, decay_weight: float = 0.9, max_section_length: int = 400) -> None:
        self.DECAY_WEIGHT = decay_weight
        self.MAX_SECTION_LENGTH = max_section_length
        self._max_stored_length = 11.0 / (1.0 - decay_weight)
        self._current_section_peak = 0.0
        self._current_section_begin = 0.0
        self._current_section_end = 0.0
        self._strain_peaks: list[_StrainPeak] = []
        self._total_length = 0.0
        self._queued_strains: list[tuple[float, float]] = []
        self._object_difficulties: list[float] = []
        self._peaks_finalised = False

    def _strain_value_at(self, curr, objects) -> float:
        raise NotImplementedError

    def _calculate_initial_strain(self, time, curr, objects) -> float:
        raise NotImplementedError

    def process(self, curr, objects) -> None:
        self._object_difficulties.append(self._process_internal(curr, objects))

    def _process_internal(self, curr, objects) -> float:
        if curr.idx == 0:
            self._current_section_begin = curr.start_time
            self._current_section_end = self._current_section_begin + self.MAX_SECTION_LENGTH
            self._current_section_peak = self._strain_value_at(curr, objects)
            return self._current_section_peak

        self._backfill_peaks(curr, objects)

        current_strain = self._strain_value_at(curr, objects)

        if current_strain > self._current_section_peak:
            self._queued_strains.clear()
            self._save_current_peak(curr.start_time - self._current_section_begin)
            self._current_section_begin = curr.start_time
            self._current_section_end = self._current_section_begin + self.MAX_SECTION_LENGTH
            self._current_section_peak = current_strain
        else:
            while self._queued_strains and self._queued_strains[-1][0] < current_strain:
                self._queued_strains.pop()
            self._queued_strains.append((current_strain, curr.start_time))

        return current_strain

    def _backfill_peaks(self, curr, objects) -> None:
        while curr.start_time > self._current_section_end:
            self._save_current_peak(self._current_section_end - self._current_section_begin)
            self._current_section_begin = self._current_section_end

            if self._queued_strains:
                strain, start_time = self._queued_strains.pop(0)
                self._current_section_end = start_time + self.MAX_SECTION_LENGTH
                self._start_new_section_from(self._current_section_begin, curr, objects)
                self._current_section_peak = max(self._current_section_peak, strain)
            else:
                self._current_section_end = self._current_section_begin + self.MAX_SECTION_LENGTH
                self._start_new_section_from(self._current_section_begin, curr, objects)

    def _save_current_peak(self, section_length: float) -> None:
        _insert_strain_peak_sorted(
            self._strain_peaks, _StrainPeak(self._current_section_peak, section_length)
        )
        self._total_length += section_length
        while self._total_length > self._max_stored_length * self.MAX_SECTION_LENGTH:
            self._total_length -= self._strain_peaks[-1].section_length
            self._strain_peaks.pop()

    def _start_new_section_from(self, time, curr, objects) -> None:
        self._current_section_peak = self._calculate_initial_strain(time, curr, objects)

    def get_current_strain_peaks(self) -> list[_StrainPeak]:
        if not self._peaks_finalised:
            self._save_current_peak(self._current_section_end - self._current_section_begin)
            self._peaks_finalised = True
        return self._strain_peaks

    def count_top_weighted_strains(self, difficulty_value: float) -> float:
        if not self._object_difficulties:
            return 0.0
        consistent_top_strain = difficulty_value * (1.0 - self.DECAY_WEIGHT)
        if consistent_top_strain == 0.0:
            return float(len(self._object_difficulties))
        return sum(
            1.1 / (1.0 + math.exp(-10.0 * (s / consistent_top_strain - 0.88)))
            for s in self._object_difficulties
        )


def _insert_strain_peak_sorted(peaks: list[_StrainPeak], item: _StrainPeak) -> None:
    lo, hi = 0, len(peaks) - 1
    idx = None
    while lo <= hi:
        i = lo + ((hi - lo) >> 1)
        if peaks[i].value > item.value:
            order = -1
        elif peaks[i].value < item.value:
            order = 1
        else:
            order = 0
        if order == 0:
            idx = i
            break
        if order < 0:
            lo = i + 1
        else:
            hi = i - 1
    if idx is None:
        idx = lo
    peaks.insert(idx, item)


def _snap_high_bpm_bonus(ms: float) -> float:
    return 1.0 / (1.0 - math.pow(0.03, math.pow(ms / 1000.0, 0.65)))


def _vector_angle_repetition(curr, previous, objects) -> float:
    if curr.angle is None or previous.angle is None:
        return 1.0

    note_limit = 6
    maximum_repetition_nerf = 0.15
    maximum_vector_influence = 0.5

    constant_angle_count = 0.0
    for index in range(note_limit):
        prev_obj = objects.previous(curr, index)
        if prev_obj is None:
            break
        if max(curr.adjusted_delta_time, prev_obj.adjusted_delta_time) > 1.1 * min(
            curr.adjusted_delta_time, prev_obj.adjusted_delta_time
        ):
            break
        if (
            prev_obj.normalised_vector_angle is not None
            and curr.normalised_vector_angle is not None
        ):
            angle_difference = abs(
                curr.normalised_vector_angle - prev_obj.normalised_vector_angle
            )
            constant_angle_count += math.cos(
                8.0 * min(math.radians(11.25), angle_difference)
            )

    if constant_angle_count == 0.0:
        ratio = 1.0
    else:
        ratio = min(0.5 / constant_angle_count, 1.0)
    vector_repetition = ratio * ratio

    stack_factor = smootherstep(curr.lazy_jump_dist, 0.0, _AIM_NORMALISED_DIAMETER)

    angle_difference_adjusted = math.cos(
        2.0 * min(math.radians(45.0), abs(curr.angle - previous.angle) * stack_factor)
    )

    base_nerf = 1.0 - maximum_repetition_nerf * _calc_angle_acuteness(
        previous.angle
    ) * angle_difference_adjusted

    v = base_nerf + (1.0 - base_nerf) * vector_repetition * maximum_vector_influence * stack_factor
    return v * v


def snap_aim_evaluate_diff_of(curr, objects, with_slider_travel_distance) -> float:
    last_obj = objects.previous(curr, 0)
    if curr.base.is_spinner() or curr.idx <= 1 or (last_obj is not None and last_obj.base.is_spinner()):
        return 0.0

    last2_obj = objects.previous(curr, 2)

    wide_angle_multiplier = 9.67
    acute_angle_multiplier = 2.41
    slider_multiplier = 1.5
    velocity_change_multiplier = 0.9
    wiggle_multiplier = 1.02

    radius = _AIM_NORMALISED_RADIUS
    diameter = _AIM_NORMALISED_DIAMETER

    curr_distance = curr.lazy_jump_dist if with_slider_travel_distance else curr.jump_dist
    curr_velocity = curr_distance / curr.adjusted_delta_time

    if last_obj.base.is_slider() and with_slider_travel_distance:
        slider_distance = last_obj.lazy_travel_dist + curr.lazy_jump_dist
        curr_velocity = max(curr_velocity, slider_distance / curr.adjusted_delta_time)

    prev_distance = last_obj.lazy_jump_dist if with_slider_travel_distance else last_obj.jump_dist
    prev_velocity = prev_distance / last_obj.adjusted_delta_time

    snap_difficulty = curr_velocity
    snap_difficulty *= _vector_angle_repetition(curr, last_obj, objects)

    if curr.angle is not None and last_obj.angle is not None:
        curr_angle = curr.angle
        last_angle = last_obj.angle
        velocity_influence = min(curr_velocity, prev_velocity)

        acute_angle_bonus = 0.0
        if max(curr.adjusted_delta_time, last_obj.adjusted_delta_time) < 1.25 * min(
            curr.adjusted_delta_time, last_obj.adjusted_delta_time
        ):
            acute_angle_bonus = _calc_angle_acuteness(curr_angle)
            _la = _calc_angle_acuteness(last_angle)
            acute_angle_bonus *= 0.08 + 0.92 * (
                1.0 - min(acute_angle_bonus, _la * _la * _la)
            )
            acute_angle_bonus *= (
                velocity_influence
                * smootherstep(millisecods_to_bpm(curr.adjusted_delta_time, 2), 300.0, 400.0)
                * smootherstep(curr_distance, 0.0, diameter * 2.0)
            )

        wide_angle_bonus = _calc_angle_wideness(curr_angle)
        _lw = _calc_angle_wideness(last_angle)
        wide_angle_bonus *= 0.25 + 0.75 * (1.0 - min(wide_angle_bonus, _lw * _lw * _lw))

        wide_angle_time_scale = 1.45
        wide_angle_curr_velocity = curr_distance / math.pow(
            curr.adjusted_delta_time, wide_angle_time_scale
        )
        wide_angle_prev_velocity = prev_distance / math.pow(
            last_obj.adjusted_delta_time, wide_angle_time_scale
        )
        if last_obj.base.is_slider() and with_slider_travel_distance:
            slider_distance = last_obj.lazy_travel_dist + curr.lazy_jump_dist
            wide_angle_curr_velocity = max(
                wide_angle_curr_velocity,
                slider_distance / math.pow(curr.adjusted_delta_time, wide_angle_time_scale),
            )
        wide_angle_bonus *= min(wide_angle_curr_velocity, wide_angle_prev_velocity)

        if last2_obj is not None:
            sp_a = last2_obj.base.stacked_pos()
            sp_b = last_obj.base.stacked_pos()
            distance = (sp_a - sp_b).length()
            if distance < 1.0:
                wide_angle_bonus *= 1.0 - 0.55 * (1.0 - distance)

        snap_difficulty += max(
            acute_angle_bonus * acute_angle_multiplier,
            wide_angle_bonus * wide_angle_multiplier,
        )

        wiggle_bonus = (
            velocity_influence
            * smootherstep(curr_distance, radius, diameter)
            * math.pow(reverse_lerp(curr_distance, diameter * 3.0, diameter), 1.8)
            * smootherstep(curr_angle, math.radians(110.0), math.radians(60.0))
            * smootherstep(prev_distance, radius, diameter)
            * math.pow(reverse_lerp(prev_distance, diameter * 3.0, diameter), 1.8)
            * smootherstep(last_angle, math.radians(110.0), math.radians(60.0))
        )
        snap_difficulty += wiggle_bonus * wiggle_multiplier

    if max(prev_velocity, curr_velocity) != 0.0:
        if with_slider_travel_distance:
            curr_velocity = curr_distance / curr.adjusted_delta_time
        dist_ratio = smoothstep(
            abs(prev_velocity - curr_velocity) / max(prev_velocity, curr_velocity), 0.0, 1.0
        )
        overlap_velocity_buff = min(
            diameter * 1.25 / min(curr.adjusted_delta_time, last_obj.adjusted_delta_time),
            abs(prev_velocity - curr_velocity),
        )
        velocity_change_bonus = overlap_velocity_buff * dist_ratio
        _r = min(curr.adjusted_delta_time, last_obj.adjusted_delta_time) / max(
            curr.adjusted_delta_time, last_obj.adjusted_delta_time
        )
        velocity_change_bonus *= _r * _r
        snap_difficulty += velocity_change_bonus * velocity_change_multiplier

    if curr.base.is_slider() and with_slider_travel_distance:
        slider_bonus = curr.travel_dist / curr.travel_time
        snap_difficulty += (
            slider_bonus if slider_bonus < 1.0 else math.pow(slider_bonus, 0.75)
        ) * slider_multiplier

    snap_difficulty *= curr.small_circle_bonus
    snap_difficulty *= _snap_high_bpm_bonus(curr.adjusted_delta_time)

    return snap_difficulty


def _agility_high_bpm_bonus(ms: float) -> float:
    return 1.0 / (1.0 - math.pow(0.2, ms / 1000.0))


def agility_evaluate_diff_of(curr, objects) -> float:
    if curr.base.is_spinner():
        return 0.0

    distance_cap = _AIM_NORMALISED_DIAMETER * 1.2

    prev_obj = objects.previous(curr, 0) if curr.idx > 0 else None
    travel_distance = prev_obj.lazy_travel_dist if prev_obj is not None else 0.0
    distance = travel_distance + curr.lazy_jump_dist

    distance_scaled = min(distance, distance_cap) / distance_cap
    agility_difficulty = distance_scaled * 1000.0 / curr.adjusted_delta_time
    agility_difficulty *= math.pow(curr.small_circle_bonus, 1.5)
    agility_difficulty *= _agility_high_bpm_bonus(curr.adjusted_delta_time)

    return agility_difficulty


def _flow_overlap_factor(first, second, object_radius) -> float:
    distance = (first.base.stacked_pos() - second.base.stacked_pos()).length()
    _b = max(distance - object_radius, 0.0) / object_radius
    return clamp(1.0 - _b * _b, 0.0, 1.0)


def flow_aim_evaluate_diff_of(curr, objects, with_slider_travel_distance, object_radius) -> float:
    last_obj = objects.previous(curr, 0)
    if curr.base.is_spinner() or curr.idx <= 1 or (last_obj is not None and last_obj.base.is_spinner()):
        return 0.0

    last_last_obj = objects.previous(curr, 1)
    velocity_change_multiplier = 0.52

    curr_distance = curr.lazy_jump_dist if with_slider_travel_distance else curr.jump_dist
    prev_distance = last_obj.lazy_jump_dist if with_slider_travel_distance else last_obj.jump_dist

    curr_velocity = curr_distance / curr.adjusted_delta_time
    if last_obj.base.is_slider() and with_slider_travel_distance:
        slider_distance = last_obj.lazy_travel_dist + curr.lazy_jump_dist
        curr_velocity = max(curr_velocity, slider_distance / curr.adjusted_delta_time)

    prev_velocity = prev_distance / last_obj.adjusted_delta_time

    flow_difficulty = curr_velocity
    flow_difficulty *= math.sqrt(curr.small_circle_bonus)

    _d = (
        max(curr.adjusted_delta_time, last_obj.adjusted_delta_time)
        - min(curr.adjusted_delta_time, last_obj.adjusted_delta_time)
    ) / 50.0
    flow_difficulty *= 1.0 + min(0.25, _d * _d * _d * _d)

    if curr.angle is not None and last_obj.angle is not None:
        angle_difference = abs(curr.angle - last_obj.angle)
        angle_difference_adjusted = math.sin(angle_difference / 2.0) * 180.0
        angular_velocity = angle_difference_adjusted / (curr.adjusted_delta_time * 0.1)
        flow_difficulty *= 0.8 + math.sqrt(angular_velocity / 270.0)

    overlapped_notes_weight = 1.0
    if curr.idx > 2:
        o1 = _flow_overlap_factor(curr, last_obj, object_radius)
        o2 = _flow_overlap_factor(curr, last_last_obj, object_radius)
        o3 = _flow_overlap_factor(last_obj, last_last_obj, object_radius)
        overlapped_notes_weight = 1.0 - o1 * o2 * o3

    if curr.angle is not None:
        flow_difficulty += (
            curr_velocity * _calc_angle_acuteness(curr.angle) * overlapped_notes_weight
        )

    if max(prev_velocity, curr_velocity) != 0.0:
        if with_slider_travel_distance:
            curr_velocity = curr_distance / curr.adjusted_delta_time
        dist_ratio = smoothstep(
            abs(prev_velocity - curr_velocity) / max(prev_velocity, curr_velocity), 0.0, 1.0
        )
        overlap_velocity_buff = min(
            _AIM_NORMALISED_DIAMETER * 1.25
            / min(curr.adjusted_delta_time, last_obj.adjusted_delta_time),
            abs(prev_velocity - curr_velocity),
        )
        flow_difficulty += (
            overlap_velocity_buff * dist_ratio * overlapped_notes_weight * velocity_change_multiplier
        )

    if curr.base.is_slider() and with_slider_travel_distance:
        flow_difficulty += curr.travel_dist / curr.travel_time

    flow_difficulty = math.pow(flow_difficulty, 1.45)
    return flow_difficulty * smootherstep(curr_distance, 0.0, _AIM_NORMALISED_RADIUS)


class Aim(_VariableLengthStrainSkill):
    def __init__(
            self,
            include_sliders: bool = True,
            overall_difficulty: float = 0.0,
            object_radius: float = 0.0,
            has_autopilot: bool = False,
            has_touch_device: bool = False,
            has_relax: bool = False,
    ) -> None:
        super().__init__(decay_weight=0.9, max_section_length=400)
        self.include_sliders = include_sliders
        self._overall_difficulty = overall_difficulty
        self._object_radius = object_radius
        self._has_autopilot = has_autopilot
        self._has_touch_device = has_touch_device
        self._has_relax = has_relax
        self._current_strain = 0.0
        self._slider_strains: list[float] = []
        self._reduced_section_time = 4000
        self._reduced_strain_baseline = 0.727

    @staticmethod
    def _strain_decay(ms: float) -> float:
        return math.pow(0.2, ms / 1000.0)

    def _calculate_initial_strain(self, time, curr, objects) -> float:
        prev = objects.previous(curr, 0)
        prev_start_time = prev.start_time if prev is not None else 0.0
        return self._current_strain * self._strain_decay(time - prev_start_time)

    def _strain_value_at(self, curr, objects) -> float:
        if self._has_autopilot:
            return 0.0
        decay = self._strain_decay(curr.adjusted_delta_time)
        self._current_strain *= decay
        self._current_strain += self._calculate_adjusted_difficulty(curr, objects) * (1.0 - decay)
        if curr.base.is_slider():
            self._slider_strains.append(self._current_strain)
        return self._current_strain

    def _calculate_adjusted_difficulty(self, curr, objects) -> float:
        skill_multiplier_snap = 70.9
        skill_multiplier_agility = 2.35
        skill_multiplier_flow = 242.0

        snap = snap_aim_evaluate_diff_of(curr, objects, self.include_sliders) * skill_multiplier_snap
        agility = agility_evaluate_diff_of(curr, objects) * skill_multiplier_agility
        flow = flow_aim_evaluate_diff_of(
            curr, objects, self.include_sliders, self._object_radius
        ) * skill_multiplier_flow

        total_difficulty = self._calculate_total_value(snap, agility, flow)

        total_difficulty *= (
            0.985 + math.pow(max(0.0, self._overall_difficulty), 2) / 4000.0
        )
        return total_difficulty

    def _calculate_total_value(self, snap, agility, flow) -> float:
        skill_multiplier_total = 1.12
        combined_snap_norm_exponent = 1.2

        combined_snap = norm(combined_snap_norm_exponent, [snap, agility])
        p_snap = self._snap_flow_probability(
            flow / combined_snap if combined_snap != 0 else float("nan")
        )
        p_flow = 1.0 - p_snap

        if self._has_touch_device:
            snap = math.pow(snap, 0.89)
            combined_snap = norm(combined_snap_norm_exponent, [snap, agility])

        if self._has_relax:
            combined_snap *= 0.75
            flow *= 0.6

        total_difficulty = combined_snap * p_snap + flow * p_flow
        return total_difficulty * skill_multiplier_total

    @staticmethod
    def _snap_flow_probability(ratio: float) -> float:
        k = 7.27
        if ratio == 0:
            return 0.0
        if math.isnan(ratio):
            return 1.0
        return logistic_exp(-k * math.log(ratio))

    def get_difficult_sliders(self) -> float:
        if not self._slider_strains:
            return 0.0
        max_slider_strain = max(self._slider_strains)
        if max_slider_strain == 0.0:
            return 0.0
        return sum(
            1.0 / (1.0 + math.exp(-(strain / max_slider_strain * 12.0 - 6.0)))
            for strain in self._slider_strains
        )

    def count_top_weighted_sliders(self, difficulty_value: float) -> float:
        if not self._slider_strains:
            return 0.0
        consistent_top_strain = difficulty_value * (1.0 - self.DECAY_WEIGHT)
        if consistent_top_strain == 0.0:
            return 0.0
        return sum(
            logistic(s / consistent_top_strain, 0.88, 10.0, 1.1)
            for s in self._slider_strains
        )

    def _get_reduced_strain_peaks(self) -> list[_StrainPeak]:
        strains = [p for p in self.get_current_strain_peaks() if p.value > 0.0]
        chunk_size = 20
        time = 0.0
        skip_count = 0

        while len(strains) > skip_count and time < self._reduced_section_time:
            strain = strains[skip_count]
            added_time = 0.0
            while added_time < strain.section_length:
                scale = math.log10(
                    _lerp(
                        1.0,
                        10.0,
                        clamp(
                            (time + added_time) / self._reduced_section_time, 0.0, 1.0
                        ),
                    )
                )
                strains.append(
                    _StrainPeak(
                        strain.value * _lerp(self._reduced_strain_baseline, 1.0, scale),
                        min(chunk_size, strain.section_length - added_time),
                    )
                )
                added_time += chunk_size
            time += strain.section_length
            skip_count += 1

        rest = strains[skip_count:]
        rest.sort(key=lambda p: p.value, reverse=True)
        return rest

    def difficulty_value(self) -> float:
        difficulty = 0.0
        time = 0.0
        for strain in self._get_reduced_strain_peaks():
            start_time = time
            end_time = time + strain.section_length / self.MAX_SECTION_LENGTH
            weight = math.pow(self.DECAY_WEIGHT, start_time) - math.pow(
                self.DECAY_WEIGHT, end_time
            )
            difficulty += strain.value * weight
            time = end_time
        return difficulty / (1.0 - self.DECAY_WEIGHT)