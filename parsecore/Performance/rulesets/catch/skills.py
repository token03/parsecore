"""The osu!catch Movement skill and its strain aggregation.

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

from parsecore.Beatmap.utils import F32_EPSILON, f32

from ...utils import eq, signum
from .hit_objects import CatchDifficultyObject

def _eq_f32(a: float, b: float) -> bool:
    """Return whether two values are equal when compared as 32-bit floats."""
    return abs(f32(a - b)) <= F32_EPSILON

def _difficulty_value(current_strain_peaks: list[float], decay_weight: float) -> float:
    """Aggregate strain peaks into a difficulty value (weighted decaying sum)."""
    difficulty = 0.0
    weight = 1.0

    peaks = [p for p in current_strain_peaks if p > 0.0]
    peaks.sort(reverse=True)

    for strain in peaks:
        difficulty += strain * weight
        weight *= decay_weight

    return difficulty

class MovementEvaluator:
    """Evaluates the movement difficulty of a single catch object."""
    NORMALIZED_HITOBJECT_RADIUS = 41.0
    DIRECTION_CHANGE_BONUS = 21.0

    @classmethod
    def evaluate_diff_of(
            cls,
            curr: CatchDifficultyObject,
            diff_objects: list[CatchDifficultyObject],
            clock_rate: float,
    ) -> float:
        """Return the raw movement difficulty of one object.

        Args:
            curr: The current difficulty object.
            diff_objects: All difficulty objects (for look-back).
            clock_rate: The active clock rate.

        Returns:
            The object's movement difficulty contribution.
        """
        catch_last_obj = curr.previous(0, diff_objects)
        catch_last_last_obj = curr.previous(1, diff_objects)

        weighted_strain_time = curr.strain_time + 13.0 + (3.0 / clock_rate)
        _wst_k = weighted_strain_time / 1000.0
        _wst_cube = _wst_k * _wst_k * _wst_k

        dist_addition = math.pow(abs(curr.dist_moved), 1.3) / 510.0
        sqrt_strain = math.sqrt(weighted_strain_time)

        edge_dash_bonus = 0.0

        last_strain_time = (
            catch_last_obj.strain_time if catch_last_obj is not None else 0.0
        )

        if abs(curr.dist_moved) > 0.1:
            last_dist_moved = (
                catch_last_obj.dist_moved if catch_last_obj is not None else 0.0
            )

            if (
                    curr.idx >= 1
                    and abs(last_dist_moved) > 0.1
                    and signum(curr.dist_moved) != signum(last_dist_moved)
            ):
                bonus_factor = float(f32(min(abs(curr.dist_moved), 50.0) / 50.0))
                anti_flow_factor = max(
                    float(f32(min(abs(last_dist_moved), 70.0) / 70.0)), 0.38,
                )

                dist_addition += (
                        cls.DIRECTION_CHANGE_BONUS
                        / math.sqrt(last_strain_time + 16.0)
                        * bonus_factor
                        * anti_flow_factor
                        * max(1.0 - _wst_cube, 0.0)
                )

            dist_addition += (
                    12.5
                    * float(f32(min(abs(curr.dist_moved),
                                    f32(cls.NORMALIZED_HITOBJECT_RADIUS * 2.0))))
                    / float(f32(cls.NORMALIZED_HITOBJECT_RADIUS * 6.0))
                    / sqrt_strain
            )

        linear_spacing_count = 0
        for i in range(min(curr.idx, 10)):
            prev_obj = curr.previous(i, diff_objects)
            if prev_obj is None:
                break
            if (
                    signum(curr.dist_moved) != signum(prev_obj.dist_moved)
                    or curr.dist_moved == 0.0
                    or prev_obj.dist_moved == 0.0
            ):
                break
            current_spacing = abs(curr.dist_moved / curr.strain_time)
            prev_spacing = abs(prev_obj.dist_moved / prev_obj.strain_time)
            relative_difference = abs(current_spacing / prev_spacing - 1.0)
            if relative_difference > 0.05:
                break
            linear_spacing_count += 1

        dist_addition *= math.pow(0.7, float(linear_spacing_count))

        if curr.last_object.dist_to_hyper_dash <= 20.0:
            if not curr.last_object.hyper_dash:
                edge_dash_bonus += 5.7

            dist_addition *= (
                    1.0
                    + edge_dash_bonus
                    * float(f32(f32(20.0 - curr.last_object.dist_to_hyper_dash) / 20.0))
                    * math.pow(min(curr.strain_time * clock_rate, 265.0) / 265.0, 1.5)
            )

        last_exact_dist_moved = (
            catch_last_obj.exact_dist_moved if catch_last_obj is not None else 0.0
        )
        last_last_exact_dist_moved = (
            catch_last_last_obj.exact_dist_moved
            if catch_last_last_obj is not None else 0.0
        )
        last_last_strain_time = (
            catch_last_last_obj.strain_time
            if catch_last_last_obj is not None else 0.0
        )

        if (
                curr.idx >= 2
                and abs(curr.exact_dist_moved)
                <= CatchDifficultyObject.NORMALIZED_HALF_CATCHER_WIDTH * 2.0
                and _eq_f32(curr.exact_dist_moved, -last_exact_dist_moved)
                and _eq_f32(last_exact_dist_moved, -last_last_exact_dist_moved)
                and eq(curr.strain_time, last_strain_time)
                and eq(last_strain_time, last_last_strain_time)
        ):
            dist_addition = 0.0

        return dist_addition / weighted_strain_time

class Movement:

    """The catch movement strain skill, accumulating per-object strain peaks."""
    SKILL_MULTIPLIER = 1.0
    STRAIN_DECAY_BASE = 0.2
    DECAY_WEIGHT = 0.94
    SECTION_LENGTH = 750.0

    __slots__ = (
        "clock_rate",
        "_current_strain",
        "_current_section_peak",
        "_current_section_end",
        "_strain_peaks",
        "_object_strains",
    )

    def __init__(self, clock_rate: float) -> None:
        """Initialise the skill.

        Args:
            clock_rate: The active clock rate.
        """
        self.clock_rate = clock_rate
        self._current_strain = 0.0
        self._current_section_peak = 0.0
        self._current_section_end = 0.0
        self._strain_peaks: list[float] = []
        self._object_strains: list[float] = []

    @staticmethod
    def _strain_decay(ms: float) -> float:
        """Return the strain decay multiplier over a time span in milliseconds."""
        return math.pow(Movement.STRAIN_DECAY_BASE, ms / 1000.0)

    def _strain_value_of(
            self,
            curr: CatchDifficultyObject,
            diff_objects: list[CatchDifficultyObject],
    ) -> float:
        """Return the strain contribution of the current object."""
        return MovementEvaluator.evaluate_diff_of(curr, diff_objects, self.clock_rate)

    def _strain_value_at(
            self,
            curr: CatchDifficultyObject,
            diff_objects: list[CatchDifficultyObject],
    ) -> float:
        """Advance and return the strain at the current object."""
        self._current_strain *= self._strain_decay(curr.delta_time)
        self._current_strain += (
                self._strain_value_of(curr, diff_objects) * self.SKILL_MULTIPLIER
        )
        return self._current_strain

    def _calculate_initial_strain(
            self,
            time: float,
            curr: CatchDifficultyObject,
            diff_objects: list[CatchDifficultyObject],
    ) -> float:
        """Return the decayed strain carried into a new section."""
        prev = curr.previous(0, diff_objects)
        prev_start_time = prev.start_time if prev is not None else 0.0
        return self._current_strain * self._strain_decay(time - prev_start_time)

    def process(
            self,
            curr: CatchDifficultyObject,
            diff_objects: list[CatchDifficultyObject],
    ) -> None:
        """Process one object, updating the running strain and peaks."""
        section_length = float(self.SECTION_LENGTH)

        if curr.idx == 0:
            self._current_section_end = (
                    math.ceil(curr.start_time / section_length) * section_length
            )

        while curr.start_time > self._current_section_end:
            self._strain_peaks.append(self._current_section_peak)
            self._current_section_peak = self._calculate_initial_strain(
                self._current_section_end, curr, diff_objects,
            )
            self._current_section_end += section_length

        strain = self._strain_value_at(curr, diff_objects)
        self._current_section_peak = max(strain, self._current_section_peak)
        self._object_strains.append(strain)

    def into_current_strain_peaks(self) -> list[float]:
        """Return the recorded strain peaks."""
        peaks = list(self._strain_peaks)
        peaks.append(self._current_section_peak)
        return peaks

    def into_difficulty_value(self) -> float:
        """Return the aggregated movement difficulty value."""
        return _difficulty_value(self.into_current_strain_peaks(), self.DECAY_WEIGHT)
