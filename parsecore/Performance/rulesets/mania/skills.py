"""osu!mania strain skill (individual and overall column strain).

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

from .hit_objects import ManiaObject

INDIVIDUAL_DECAY_BASE = 0.125
OVERALL_DECAY_BASE = 0.30
RELEASE_THRESHOLD = 30.0

STRAIN_DECAY_BASE = 1.0
SKILL_MULTIPLIER = 1.0

SECTION_LENGTH_MS = 400.0
DECAY_WEIGHT = 0.9

def _apply_decay(value: float, delta_time: float, decay_base: float) -> float:
    """Return a strain value decayed over a time span."""
    return value * (decay_base ** (delta_time / 1000.0))

def _logistic(x: float, multiplier: float, midpoint_offset: float, max_value: float = 1.0) -> float:
    """Return the value of a logistic (sigmoid) curve."""
    return max_value / (1.0 + math.exp(-multiplier * (x - midpoint_offset)))

def _definitely_bigger(a: float, b: float, tol: float = 1.0) -> bool:
    """Return whether one value exceeds another beyond a small epsilon."""
    return (a - b) > tol

@dataclass(slots=True)
class ManiaDifficultyHitObject:
    """One mania object enriched with per-column and cross-column timing state."""
    idx: int
    start_time: float
    end_time: float
    delta_time: float
    column: int
    column_strain_time: float
    previous_hit_objects: list[Optional["ManiaDifficultyHitObject"]] = field(default_factory=list)

def _osu_legacy_sort_in_place(keys: list, comparer) -> None:
    """Sort objects in place using osu!'s legacy (unstable) sort algorithm."""
    if len(keys) < 2:
        return
    _legacy_quicksort(keys, 0, len(keys) - 1, comparer, 32)

def _legacy_quicksort(keys: list, left: int, right: int, comparer, depth_limit: int) -> None:
    """The recursive quicksort half of osu!'s legacy introsort."""
    while True:
        if depth_limit == 0:
            _legacy_heap_sort(keys, left, right, comparer)
            return

        i = left
        j = right
        middle = i + ((j - i) >> 1)

        if i != middle and comparer(keys[i], keys[middle]) > 0:
            keys[i], keys[middle] = keys[middle], keys[i]
        if i != j and comparer(keys[i], keys[j]) > 0:
            keys[i], keys[j] = keys[j], keys[i]
        if middle != j and comparer(keys[middle], keys[j]) > 0:
            keys[middle], keys[j] = keys[j], keys[middle]

        while True:
            while comparer(keys[i], keys[middle]) < 0:
                i += 1
            while comparer(keys[middle], keys[j]) < 0:
                j -= 1

            if i < j:
                keys[i], keys[j] = keys[j], keys[i]
                if middle == i:
                    middle = j
                elif middle == j:
                    middle = i
            elif i == j:
                pass
            else:
                break

            i += 1
            j = max(0, j - 1)

            if i > j:
                break

        depth_limit -= 1

        if (j - left if j >= left else 0) <= (right - i):
            if left < j:
                _legacy_quicksort(keys, left, j, comparer, depth_limit)
            left = i
        else:
            if i < right:
                _legacy_quicksort(keys, i, right, comparer, depth_limit)
            right = j

        if left >= right:
            break

def _legacy_heap_sort(keys: list, lo: int, hi: int, comparer) -> None:
    """The heap-sort fallback of osu!'s legacy introsort."""
    n = hi - lo + 1

    for i in range(n // 2, 0, -1):
        _legacy_down_heap(keys, i, n, lo, comparer)

    for i in range(n, 1, -1):
        if lo != lo + i - 1:
            keys[lo], keys[lo + i - 1] = keys[lo + i - 1], keys[lo]
        _legacy_down_heap(keys, 1, i - 1, lo, comparer)

def _legacy_down_heap(keys: list, i: int, n: int, lo: int, comparer) -> None:
    """Sift an element down the heap (legacy heap sort helper)."""
    while i <= n // 2:
        child = 2 * i
        if child < n and comparer(keys[lo + child - 1], keys[lo + child]) < 0:
            child += 1
        if comparer(keys[lo + i - 1], keys[lo + child - 1]) >= 0:
            break
        keys[lo + i - 1], keys[lo + child - 1] = keys[lo + child - 1], keys[lo + i - 1]
        i = child

def create_mania_difficulty_objects(
        mania_objects: list[ManiaObject],
        clock_rate: float,
        total_columns: int,
) -> list[ManiaDifficultyHitObject]:
    """Build the difficulty objects for the mania strain skill.

    Args:
        objects: The mania objects.
        clock_rate: The active clock rate.
        total_columns: The stage's column count.

    Returns:
        The preprocessed difficulty objects.
    """
    if len(mania_objects) < 2:
        return []

    sorted_objects = mania_objects

    out: list[ManiaDifficultyHitObject] = []
    per_column: list[list[ManiaDifficultyHitObject]] = [
        [] for _ in range(total_columns)
    ]

    for i in range(1, len(sorted_objects)):
        curr = sorted_objects[i]
        prev = sorted_objects[i - 1]
        curr_start_time = curr.start_time / clock_rate
        curr_end_time = curr.end_time / clock_rate
        delta_time = (curr.start_time - prev.start_time) / clock_rate

        col = curr.column
        if 0 <= col < total_columns and per_column[col]:
            prev_in_column = per_column[col][-1]
            column_strain_time = curr_start_time - prev_in_column.start_time
        else:
            column_strain_time = 0.0

        prev_arr: list[Optional[ManiaDifficultyHitObject]]
        if out:
            prev_note = out[-1]
            prev_arr = list(prev_note.previous_hit_objects)
            if 0 <= prev_note.column < total_columns:
                prev_arr[prev_note.column] = prev_note
        else:
            prev_arr = [None] * total_columns

        diff_obj = ManiaDifficultyHitObject(
            idx=i - 1,
            start_time=curr_start_time,
            end_time=curr_end_time,
            delta_time=delta_time,
            column=col,
            column_strain_time=column_strain_time,
            previous_hit_objects=prev_arr,
        )

        out.append(diff_obj)
        if 0 <= col < total_columns:
            per_column[col].append(diff_obj)

    return out

class IndividualStrainEvaluator:
    """Evaluates per-column strain (repeated notes in the same column)."""
    @staticmethod
    def evaluate_difficulty_of(curr: ManiaDifficultyHitObject) -> float:
        """Return the individual (per-column) strain of one object."""
        start_time = curr.start_time
        end_time = curr.end_time
        hold_factor = 1.0

        for prev in curr.previous_hit_objects:
            if prev is None:
                continue
            if _definitely_bigger(prev.end_time, end_time, 1.0) and \
                    _definitely_bigger(start_time, prev.start_time, 1.0):
                hold_factor = 1.25
                break

        return 2.0 * hold_factor

class OverallStrainEvaluator:
    """Evaluates overall strain (notes across all columns)."""
    @staticmethod
    def evaluate_difficulty_of(curr: ManiaDifficultyHitObject) -> float:
        """Return the overall (cross-column) strain of one object."""
        start_time = curr.start_time
        end_time = curr.end_time
        is_overlapping = False

        closest_end_time = abs(end_time - start_time)
        hold_factor = 1.0
        hold_addition = 0.0

        for prev in curr.previous_hit_objects:
            if prev is None:
                continue

            if (_definitely_bigger(prev.end_time, start_time, 1.0) and
                    _definitely_bigger(end_time, prev.end_time, 1.0) and
                    _definitely_bigger(start_time, prev.start_time, 1.0)):
                is_overlapping = True

            if (_definitely_bigger(prev.end_time, end_time, 1.0) and
                    _definitely_bigger(start_time, prev.start_time, 1.0)):
                hold_factor = 1.25

            d = abs(end_time - prev.end_time)
            if d < closest_end_time:
                closest_end_time = d

        if is_overlapping:
            hold_addition = _logistic(
                closest_end_time, multiplier=0.27, midpoint_offset=RELEASE_THRESHOLD, max_value=1.0,
            )

        return (1.0 + hold_addition) * hold_factor

class Strain:
    """The mania strain skill combining individual and overall strain."""
    DECAY_WEIGHT = DECAY_WEIGHT
    SECTION_LENGTH = SECTION_LENGTH_MS
    STRAIN_DECAY_BASE = STRAIN_DECAY_BASE
    SKILL_MULTIPLIER = SKILL_MULTIPLIER

    def __init__(self, total_columns: int) -> None:
        """Initialise the skill's strain and peak state."""
        self.total_columns = total_columns
        self.individual_strains: list[float] = [0.0] * total_columns
        self.highest_individual_strain: float = 0.0
        self.overall_strain: float = 1.0
        self._current_section_peak: float = 0.0
        self._current_section_end: float = 0.0
        self._strain_peaks: list[float] = []
        self._object_strains: list[float] = []
        self._macro_strain: float = 0.0

    def process(self, curr: ManiaDifficultyHitObject) -> None:
        """Process one object, updating the running strain and section peaks."""
        section = self.SECTION_LENGTH
        if curr.idx == 0:
            self._current_section_end = math.ceil(curr.start_time / section) * section

        while curr.start_time > self._current_section_end:
            self._save_current_peak()
            self._start_new_section_from(self._current_section_end, curr)
            self._current_section_end += section

        strain = self._strain_value_at(curr)
        self._current_section_peak = max(strain, self._current_section_peak)
        self._object_strains.append(strain)

    def _save_current_peak(self) -> None:
        """Record the current strain as a section peak."""
        self._strain_peaks.append(self._current_section_peak)

    def _start_new_section_from(self, time: float, curr: ManiaDifficultyHitObject) -> None:
        """Begin a new strain section from a decayed baseline."""
        self._current_section_peak = self._calculate_initial_strain(time, curr)

    def _strain_value_at(self, curr: ManiaDifficultyHitObject) -> float:
        """Advance and return the strain at the current object."""
        self._macro_strain *= self.STRAIN_DECAY_BASE
        val = self._strain_value_of(curr)
        self._macro_strain += val * self.SKILL_MULTIPLIER
        return self._macro_strain

    def _calculate_initial_strain(self, time: float, curr: ManiaDifficultyHitObject) -> float:
        """Return the decayed strain carried into a new section."""
        prev_start = self._prev_processed_start_time
        offset = time - prev_start
        return (
                _apply_decay(self.highest_individual_strain, offset, INDIVIDUAL_DECAY_BASE)
                + _apply_decay(self.overall_strain, offset, OVERALL_DECAY_BASE)
        )

    _prev_processed_start_time: float = 0.0

    def _strain_value_of(self, curr: ManiaDifficultyHitObject) -> float:
        """Return the strain contribution of the current object."""
        col = curr.column

        if 0 <= col < len(self.individual_strains):
            self.individual_strains[col] = _apply_decay(
                self.individual_strains[col], curr.column_strain_time, INDIVIDUAL_DECAY_BASE,
            )
            self.individual_strains[col] += IndividualStrainEvaluator.evaluate_difficulty_of(curr)
            this_col_strain = self.individual_strains[col]
        else:
            this_col_strain = IndividualStrainEvaluator.evaluate_difficulty_of(curr)

        if curr.delta_time <= 1.0:
            self.highest_individual_strain = max(self.highest_individual_strain, this_col_strain)
        else:
            self.highest_individual_strain = this_col_strain

        self.overall_strain = _apply_decay(
            self.overall_strain, curr.delta_time, OVERALL_DECAY_BASE,
        )
        self.overall_strain += OverallStrainEvaluator.evaluate_difficulty_of(curr)
        self._prev_processed_start_time = curr.start_time

        return self.highest_individual_strain + self.overall_strain - self._macro_strain

    def get_current_strain_peaks(self) -> list[float]:
        """Return the recorded strain peaks."""
        return [*self._strain_peaks, self._current_section_peak]

    def difficulty_value(self) -> float:
        """Aggregate the strain peaks into the mania difficulty value."""
        peaks = [p for p in self.get_current_strain_peaks() if p > 0.0]
        peaks.sort(reverse=True)
        difficulty = 0.0
        weight = 1.0
        for strain in peaks:
            difficulty += strain * weight
            weight *= self.DECAY_WEIGHT
        return difficulty

def run_strain(
        diff_objects: list[ManiaDifficultyHitObject],
        total_columns: int,
) -> Strain:
    """Run the mania strain skill over the difficulty objects.

    Args:
        diff_objects: The preprocessed mania difficulty objects.
        total_columns: The stage's column count.

    Returns:
        The processed strain skill.
    """
    skill = Strain(total_columns)
    for obj in diff_objects:
        skill.process(obj)
    return skill