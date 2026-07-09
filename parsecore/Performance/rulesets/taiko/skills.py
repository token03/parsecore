"""osu!taiko difficulty skills: stamina, rhythm, colour and reading.

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
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from ...data.beatmap import (
    PerformanceBeatmap,
    effect_point_at,
    timing_point_at,
)
from ...utils import ieee_pow
from .hit_objects import TaikoHitType, TaikoObject


DIFFICULTY_MULTIPLIER = 0.084375
RHYTHM_SKILL_MULTIPLIER = 0.770 * DIFFICULTY_MULTIPLIER
READING_SKILL_MULTIPLIER = 0.100 * DIFFICULTY_MULTIPLIER
COLOR_SKILL_MULTIPLIER = 0.375 * DIFFICULTY_MULTIPLIER
STAMINA_SKILL_MULTIPLIER = 0.445 * DIFFICULTY_MULTIPLIER

STAMINA_SUBSKILL_MULTIPLIER = 1.1
COLOR_SUBSKILL_MULTIPLIER = 0.12
RHYTHM_STRAIN_DECAY_BASE = 0.4
STAMINA_STRAIN_DECAY_BASE = 0.4
COLOR_STRAIN_DECAY_BASE = 0.8

SECTION_LENGTH_MS = 400.0
DECAY_WEIGHT = 0.9

INTERVAL_MARGIN_OF_ERROR = 5.0
MAX_REPETITION_INTERVAL = 16

COMMON_RATIOS = [
    1.0 / 1.0, 2.0 / 1.0, 1.0 / 2.0, 3.0 / 1.0, 1.0 / 3.0,
    3.0 / 2.0, 2.0 / 3.0, 5.0 / 4.0, 4.0 / 5.0,
    ]


def _strain_decay(ms: float, base: float) -> float:
    """Return the strain decay multiplier over a time span in milliseconds."""
    return base ** (ms / 1000.0)

def _logistic(x: float, midpoint_offset: float, multiplier: float, max_value: float = 1.0) -> float:
    """Return the value of a logistic (sigmoid) curve."""
    return max_value / (1.0 + math.exp(multiplier * (midpoint_offset - x)))

_logistic_via_rust = _logistic

def _logistic_exp(neg_x: float, multiplier: Optional[float] = None) -> float:
    """Return a logistic curve evaluated on an exponent argument."""
    m = multiplier if multiplier is not None else 1.0
    return m / (1.0 + math.exp(neg_x))

def _reverse_lerp(value: float, start: float, end: float) -> float:
    """Return the clamped ``0``-``1`` position of a value between two bounds."""
    if end == start:
        return 0.0
    return max(0.0, min(1.0, (value - start) / (end - start)))

def _smootherstep(x: float, start: float, end: float) -> float:
    """Return the smootherstep interpolation of a value between two edges."""
    t = _reverse_lerp(x, start, end)
    return t * t * t * (t * (6.0 * t - 15.0) + 10.0)

def _bell_curve(x: float, mean: float, width: float, multiplier: Optional[float] = None) -> float:
    """Return a bell-curve weight peaking at a given centre."""
    m = multiplier if multiplier is not None else 1.0
    return m * math.exp(math.e * -(((x - mean) * (x - mean)) / (width * width)))

def _norm(p: float, values: list[float]) -> float:
    """Return the p-norm of several values (with Rust ``powf`` NaN semantics)."""
    s = 0.0
    for v in values:
        s += ieee_pow(v, p)
    return ieee_pow(s, 1.0 / p)

def _almost_eq(a: float, b: float, margin: float) -> bool:
    """Return whether two values are equal within a small margin."""
    return abs(a - b) <= margin

@dataclass(slots=True)
class MonoIndex:
    """Indices locating an object within the mono-streak colour hierarchy."""
    kind: int
    idx: int

@dataclass
class MonoStreak:
    """A run of consecutive same-colour (all don or all kat) hits."""
    hit_objects: list["TaikoDifficultyObject"] = field(default_factory=list)
    parent: Optional["AlternatingMonoPattern"] = None
    idx: int = 0

    def run_len(self) -> int:
        """Return the number of hits in the streak."""
        return len(self.hit_objects)

    def hit_type(self) -> Optional[TaikoHitType]:
        """Return the streak's shared hit type (don or kat)."""
        if not self.hit_objects:
            return None
        return self.hit_objects[0].base_hit_type

    def first_hit_object(self) -> Optional["TaikoDifficultyObject"]:
        """Return the streak's first difficulty object."""
        return self.hit_objects[0] if self.hit_objects else None

    def last_hit_object(self) -> Optional["TaikoDifficultyObject"]:
        """Return the streak's last difficulty object."""
        return self.hit_objects[-1] if self.hit_objects else None

@dataclass
class AlternatingMonoPattern:
    """A pattern of alternating mono streaks (e.g. ddkk ddkk)."""
    mono_streaks: list[MonoStreak] = field(default_factory=list)
    parent: Optional["RepeatingHitPatterns"] = None
    idx: int = 0

    def first_hit_object(self) -> Optional["TaikoDifficultyObject"]:
        """Return the pattern's first difficulty object."""
        if not self.mono_streaks:
            return None
        return self.mono_streaks[0].first_hit_object()

    def has_identical_mono_len(self, other: "AlternatingMonoPattern") -> bool:
        """Return whether all its mono streaks share the same length."""
        return self.mono_streaks[0].run_len() == other.mono_streaks[0].run_len()

    def is_repetition_of(self, other: "AlternatingMonoPattern") -> bool:
        """Return whether this pattern repeats another."""
        if not (self.has_identical_mono_len(other)
                and len(self.mono_streaks) == len(other.mono_streaks)):
            return False
        return self.mono_streaks[0].hit_type() == other.mono_streaks[0].hit_type()

@dataclass
class RepeatingHitPatterns:
    """A sequence of alternating patterns that repeats, used for colour repetition."""
    alternating_mono_patterns: list[AlternatingMonoPattern] = field(default_factory=list)
    prev: Optional["RepeatingHitPatterns"] = None
    repetition_interval: int = 0

    def first_hit_object(self) -> Optional["TaikoDifficultyObject"]:
        """Return the sequence's first difficulty object."""
        if not self.alternating_mono_patterns:
            return None
        return self.alternating_mono_patterns[0].first_hit_object()

    def is_repetition_of(self, other: "RepeatingHitPatterns") -> bool:
        """Return whether this sequence repeats another."""
        if len(self.alternating_mono_patterns) != len(other.alternating_mono_patterns):
            return False
        for a, b in zip(self.alternating_mono_patterns[:2], other.alternating_mono_patterns[:2]):
            if not a.has_identical_mono_len(b):
                return False
        return True

    def find_repetition_interval(self) -> None:
        """Find how many patterns back this sequence repeats, if any."""
        if self.prev is None:
            self.repetition_interval = MAX_REPETITION_INTERVAL + 1
            return
        other = self.prev
        interval = 1
        while interval < MAX_REPETITION_INTERVAL:
            if self.is_repetition_of(other):
                self.repetition_interval = min(interval, MAX_REPETITION_INTERVAL)
                return
            if other.prev is None:
                break
            other = other.prev
            interval += 1
        self.repetition_interval = MAX_REPETITION_INTERVAL + 1

@dataclass
class SameRhythmHitObjectGrouping:
    """A group of consecutive objects sharing the same time interval."""
    hit_objects: list["TaikoDifficultyObject"] = field(default_factory=list)
    previous: Optional["SameRhythmHitObjectGrouping"] = None
    hit_object_interval: Optional[float] = None
    hit_object_interval_ratio: float = 1.0
    interval: float = math.inf

    def first_hit_object(self) -> Optional["TaikoDifficultyObject"]:
        """Return the group's first object."""
        return self.hit_objects[0] if self.hit_objects else None

    def start_time(self) -> Optional[float]:
        """Return the group's start time."""
        return self.hit_objects[0].start_time if self.hit_objects else None

    def duration(self) -> Optional[float]:
        """Return the group's total duration."""
        if not self.hit_objects:
            return None
        return self.hit_objects[-1].start_time - self.hit_objects[0].start_time

@dataclass
class SamePatternsGroupedHitObjects:
    """A group of same-rhythm groupings sharing a repeating interval pattern."""
    groups: list[SameRhythmHitObjectGrouping] = field(default_factory=list)
    previous: Optional["SamePatternsGroupedHitObjects"] = None

    def first_hit_object(self) -> Optional["TaikoDifficultyObject"]:
        """Return the group's first object."""
        if not self.groups:
            return None
        return self.groups[0].first_hit_object()

    def group_interval(self) -> Optional[float]:
        """Return the interval between the grouped rhythms."""
        if not self.groups:
            return None
        g = self.groups[1] if len(self.groups) > 1 else self.groups[0]
        return g.interval

    def interval_ratio(self) -> float:
        """Return the ratio of this group's interval to the previous one."""
        curr = self.group_interval()
        prev = self.previous.group_interval() if self.previous is not None else None
        if curr is None or prev is None or prev == 0.0:
            return 1.0
        return curr / prev

@dataclass(slots=True)
class ColorData:
    """Per-object colour-skill state (its place in the mono/pattern hierarchy)."""
    mono_streak: Optional[MonoStreak] = None
    alternating_mono_pattern: Optional[AlternatingMonoPattern] = None
    repeating_hit_patterns: Optional[RepeatingHitPatterns] = None

@dataclass(slots=True)
class RhythmData:
    """Per-object rhythm-skill state (interval, ratio and grouping links)."""
    same_rhythm_grouped_hit_objects: Optional[SameRhythmHitObjectGrouping] = None
    same_patterns_grouped_hit_objects: Optional[SamePatternsGroupedHitObjects] = None
    ratio: float = 1.0

    @classmethod
    def create(cls, delta_time: float, prev_delta_time: Optional[float]) -> "RhythmData":
        """Build the rhythm data for one object from its neighbours.

        Returns:
            The rhythm data (delta time, ratio to the previous interval, ...).
        """
        if prev_delta_time is None:
            return cls(ratio=1.0)
        actual_ratio = delta_time / prev_delta_time if prev_delta_time != 0.0 else 1.0
        closest = min(COMMON_RATIOS, key=lambda r: abs(r - actual_ratio))
        return cls(ratio=closest)

@dataclass(slots=True)
class TaikoDifficultyObject:
    """One taiko object enriched with rhythm and colour preprocessing state."""
    idx: int
    delta_time: float
    start_time: float
    base_hit_type: TaikoHitType
    mono_idx: MonoIndex
    note_idx: int
    rhythm_data: RhythmData
    color_data: ColorData
    effective_bpm: float

class TaikoDifficultyObjects:
    """The ordered collection of taiko difficulty objects with navigation helpers."""
    __slots__ = ("objects", "center_hit_objects", "rim_hit_objects", "note_objects")

    def __init__(self) -> None:
        """Initialise an empty collection."""
        self.objects: list[TaikoDifficultyObject] = []
        self.center_hit_objects: list[TaikoDifficultyObject] = []
        self.rim_hit_objects: list[TaikoDifficultyObject] = []
        self.note_objects: list[TaikoDifficultyObject] = []

    def push(self, obj: TaikoDifficultyObject) -> None:
        """Append a difficulty object."""
        self.objects.append(obj)

    def previous(self, curr: TaikoDifficultyObject, backwards_idx: int) -> Optional[TaikoDifficultyObject]:
        """Return the object ``n`` steps before the given index, or ``None``."""
        target = curr.idx - backwards_idx - 1
        if 0 <= target < len(self.objects):
            return self.objects[target]
        return None

    def previous_mono(self, curr: TaikoDifficultyObject, backwards_idx: int) -> Optional[TaikoDifficultyObject]:
        """Return the previous object of the same colour, or ``None``."""
        backwards_idx += 1
        if curr.mono_idx.kind == 0:
            target = curr.mono_idx.idx - backwards_idx
            if 0 <= target < len(self.center_hit_objects):
                return self.center_hit_objects[target]
        elif curr.mono_idx.kind == 1:
            target = curr.mono_idx.idx - backwards_idx
            if 0 <= target < len(self.rim_hit_objects):
                return self.rim_hit_objects[target]
        return None

    def previous_note(self, curr: TaikoDifficultyObject, backwards_idx: int) -> Optional[TaikoDifficultyObject]:
        """Return the previous hit note, skipping non-hits, or ``None``."""
        target = curr.note_idx - backwards_idx - 1
        if 0 <= target < len(self.note_objects):
            return self.note_objects[target]
        return None

    def next_note(self, curr: TaikoDifficultyObject, forwards_idx: int) -> Optional[TaikoDifficultyObject]:
        """Return the next hit note, skipping non-hits, or ``None``."""
        target = curr.note_idx + forwards_idx + 1
        if 0 <= target < len(self.note_objects):
            return self.note_objects[target]
        return None

def create_taiko_difficulty_objects(
        pm: PerformanceBeatmap,
        taiko_objects: list[TaikoObject],
        clock_rate: float,
        global_slider_velocity: float,
) -> TaikoDifficultyObjects:
    """Build the difficulty objects for a list of taiko objects.

    Args:
        objects: The taiko objects.
        clock_rate: The active clock rate.

    Returns:
        The preprocessed difficulty-object collection.
    """
    out = TaikoDifficultyObjects()
    if len(taiko_objects) < 3:
        return out

    last = taiko_objects[1]
    prev_delta_time: Optional[float] = None
    for i, curr in enumerate(taiko_objects[2:]):
        delta_time = (curr.start_time - last.start_time) / clock_rate

        if curr.hit_type is TaikoHitType.CENTER:
            note_idx = len(out.note_objects)
            mono_idx = MonoIndex(kind=0, idx=len(out.center_hit_objects))
        elif curr.hit_type is TaikoHitType.RIM:
            note_idx = len(out.note_objects)
            mono_idx = MonoIndex(kind=1, idx=len(out.rim_hit_objects))
        else:
            note_idx = 0
            mono_idx = MonoIndex(kind=2, idx=0)

        start_time = curr.start_time / clock_rate
        normalized_start_time = start_time * clock_rate

        tp = timing_point_at(pm.timing_points, normalized_start_time)
        curr_bpm = tp.bpm() if tp is not None else 60.0

        ep = effect_point_at(pm.effect_points, normalized_start_time)
        scroll_speed = (
            ep.scroll_speed if (ep is not None and hasattr(ep, "scroll_speed"))
            else 1.0
        )
        curr_slider_velocity = global_slider_velocity * scroll_speed * clock_rate
        effective_bpm = curr_bpm * curr_slider_velocity

        diff_obj = TaikoDifficultyObject(
            idx=i,
            delta_time=delta_time,
            start_time=start_time,
            base_hit_type=curr.hit_type,
            mono_idx=mono_idx,
            note_idx=note_idx,
            rhythm_data=RhythmData.create(delta_time, prev_delta_time),
            color_data=ColorData(),
            effective_bpm=effective_bpm,
        )

        out.push(diff_obj)
        if curr.hit_type is TaikoHitType.CENTER:
            out.note_objects.append(diff_obj)
            out.center_hit_objects.append(diff_obj)
        elif curr.hit_type is TaikoHitType.RIM:
            out.note_objects.append(diff_obj)
            out.rim_hit_objects.append(diff_obj)

        last = curr
        prev_delta_time = delta_time

    return out

class ColorDifficultyPreprocessor:
    """Builds the mono-streak/alternating/repeating colour hierarchy."""
    @staticmethod
    def process_and_assign(diff_objects: TaikoDifficultyObjects) -> None:
        """Encode the colour hierarchy and assign it back onto each object."""
        hit_patterns = ColorDifficultyPreprocessor._encode(diff_objects)
        for repeating in hit_patterns:
            for i, mono_pattern in enumerate(repeating.alternating_mono_patterns):
                mono_pattern.parent = repeating
                mono_pattern.idx = i
                for j, mono_streak in enumerate(mono_pattern.mono_streaks):
                    mono_streak.parent = mono_pattern
                    mono_streak.idx = j
                    for h in mono_streak.hit_objects:
                        h.color_data.repeating_hit_patterns = repeating
                        h.color_data.alternating_mono_pattern = mono_pattern
                        h.color_data.mono_streak = mono_streak

    @staticmethod
    def _encode(diff_objects: TaikoDifficultyObjects) -> list[RepeatingHitPatterns]:
        """Encode the full colour hierarchy from the objects."""
        mono_streaks = ColorDifficultyPreprocessor._encode_mono_streaks(diff_objects)
        mono_patterns = ColorDifficultyPreprocessor._encode_alternating_mono_pattern(mono_streaks)
        return ColorDifficultyPreprocessor._encode_repeating_hit_patterns(mono_patterns)

    @staticmethod
    def _encode_mono_streaks(diff_objects: TaikoDifficultyObjects) -> list[MonoStreak]:
        """Group consecutive same-colour hits into mono streaks."""
        if not diff_objects.objects:
            return []

        mono_streaks: list[MonoStreak] = [MonoStreak()]
        curr = mono_streaks[-1]
        curr.hit_objects.append(diff_objects.objects[0])

        for taiko_object in diff_objects.objects[1:]:
            prev = diff_objects.previous_note(taiko_object, 0)
            same_type = prev is not None and prev.base_hit_type == taiko_object.base_hit_type
            if not same_type:
                mono_streaks.append(MonoStreak())
                curr = mono_streaks[-1]
            curr.hit_objects.append(taiko_object)

        return mono_streaks

    @staticmethod
    def _encode_alternating_mono_pattern(mono_streaks: list[MonoStreak]) -> list[AlternatingMonoPattern]:
        """Group mono streaks into alternating patterns."""
        if not mono_streaks:
            return []

        patterns: list[AlternatingMonoPattern] = [AlternatingMonoPattern()]
        curr = patterns[-1]
        first = mono_streaks[0]
        prev_run_len = first.run_len()
        curr.mono_streaks.append(first)

        for mono in mono_streaks[1:]:
            run_len = mono.run_len()
            if run_len != prev_run_len:
                patterns.append(AlternatingMonoPattern())
                curr = patterns[-1]
            prev_run_len = run_len
            curr.mono_streaks.append(mono)

        return patterns

    @staticmethod
    def _encode_repeating_hit_patterns(patterns: list[AlternatingMonoPattern]) -> list[RepeatingHitPatterns]:
        """Group alternating patterns into repeating sequences."""
        hit_patterns: list[RepeatingHitPatterns] = []
        data: list[AlternatingMonoPattern] = list(patterns)
        curr_hit_pattern: Optional[RepeatingHitPatterns] = None
        prev_for_link: Optional[RepeatingHitPatterns] = None

        while data:
            curr_hit_pattern = RepeatingHitPatterns(prev=prev_for_link)

            def is_coupled() -> bool:
                """Return whether two patterns are coupled (repeat within the interval)."""
                return len(data) > 2 and data[0].is_repetition_of(data[2])

            if is_coupled():
                while is_coupled():
                    curr_hit_pattern.alternating_mono_patterns.append(data.pop(0))
                for _ in range(min(2, len(data))):
                    curr_hit_pattern.alternating_mono_patterns.append(data.pop(0))
            else:
                curr_hit_pattern.alternating_mono_patterns.append(data.pop(0))

            hit_patterns.append(curr_hit_pattern)
            prev_for_link = curr_hit_pattern

        for pattern in hit_patterns:
            pattern.find_repetition_interval()

        return hit_patterns

def _interval_of(item: object) -> float:
    """Return the time interval between two objects."""
    if isinstance(item, TaikoDifficultyObject):
        return item.delta_time
    if isinstance(item, SameRhythmHitObjectGrouping):
        return item.interval
    raise TypeError(f"no interval for {type(item)}")

def _group_by_interval(items: list) -> list[list]:
    """Group objects that share (nearly) the same interval."""
    out: list[list] = []
    i = 0
    n = len(items)
    while i < n:
        grouped = [items[i]]
        i += 1
        while i < n - 1:
            if not _almost_eq(_interval_of(items[i]), _interval_of(items[i + 1]), INTERVAL_MARGIN_OF_ERROR):
                if _interval_of(items[i + 1]) > _interval_of(items[i]) + INTERVAL_MARGIN_OF_ERROR:
                    grouped.append(items[i])
                    i += 1
                out.append(grouped)
                break
            grouped.append(items[i])
            i += 1
        else:
            if n > 2 and i < n and _almost_eq(_interval_of(items[n - 1]), _interval_of(items[n - 2]), INTERVAL_MARGIN_OF_ERROR):
                grouped.append(items[i])
                i += 1
            out.append(grouped)
    return out

def _normalize_delta_times(
        hit_objects: list[TaikoDifficultyObject],
        margin_of_error: float,
) -> dict[int, float]:
    """Snap near-equal delta times together to stabilise grouping."""
    distinct: list[float] = []
    for h in hit_objects:
        d = h.delta_time
        idx = 0
        found = False
        for j, existing in enumerate(distinct):
            if existing == d:
                found = True
                break
            if existing > d:
                idx = j
                break
            idx = j + 1
        if not found:
            distinct.insert(idx, d)

    sets: list[list[float]] = []
    if distinct:
        curr = [distinct[0]]
        for v in distinct[1:]:
            if abs(v - curr[0]) <= margin_of_error:
                curr.append(v)
            else:
                sets.append(curr)
                curr = [v]
        sets.append(curr)

    median_lookup: dict[float, float] = {}
    for s in sets:
        s.sort()
        mid = len(s) // 2
        median = s[mid] if len(s) % 2 == 1 else (s[mid - 1] + s[mid]) / 2.0
        for v in s:
            median_lookup[v] = median

    out: dict[int, float] = {}
    for h in hit_objects:
        out[id(h)] = median_lookup.get(h.delta_time, h.delta_time)
    return out

def _round_ties_even(x: float) -> float:
    """Round half-to-even (banker's rounding), matching osu!/C#."""
    return float(round(x))

class RhythmDifficultyPreprocessor:
    """Builds the same-rhythm and same-pattern groupings for the rhythm skill."""
    SNAP_TOLERANCE = INTERVAL_MARGIN_OF_ERROR

    @staticmethod
    def process_and_assign(diff_objects: TaikoDifficultyObjects) -> None:
        """Build the rhythm groupings and assign them back onto each object."""
        rhythm_groups = RhythmDifficultyPreprocessor._create_same_rhythm_groups(
            diff_objects.note_objects
        )
        for rhythm_group in rhythm_groups:
            for h in rhythm_group.hit_objects:
                h.rhythm_data.same_rhythm_grouped_hit_objects = rhythm_group

        pattern_groups = RhythmDifficultyPreprocessor._create_same_pattern_groups(rhythm_groups)
        for pattern_group in pattern_groups:
            for group in pattern_group.groups:
                for h in group.hit_objects:
                    h.rhythm_data.same_patterns_grouped_hit_objects = pattern_group

    @staticmethod
    def _create_same_rhythm_groups(
            notes: list[TaikoDifficultyObject],
    ) -> list[SameRhythmHitObjectGrouping]:
        """Group consecutive objects that share a time interval."""
        groups: list[SameRhythmHitObjectGrouping] = []
        prev: Optional[SameRhythmHitObjectGrouping] = None
        for grouped in _group_by_interval(notes):
            g = RhythmDifficultyPreprocessor._make_rhythm_grouping(prev, grouped)
            groups.append(g)
            prev = g
        return groups

    @staticmethod
    def _make_rhythm_grouping(
            previous: Optional[SameRhythmHitObjectGrouping],
            hit_objects: list[TaikoDifficultyObject],
    ) -> SameRhythmHitObjectGrouping:
        """Build one same-rhythm grouping from a run of objects."""
        normalized = _normalize_delta_times(
            hit_objects, RhythmDifficultyPreprocessor.SNAP_TOLERANCE,
        )
        modal_delta = 0.0
        if len(hit_objects) > 1:
            modal_delta = _round_ties_even(normalized.get(id(hit_objects[1]), 0.0))

        normalized_count = max(0, len(hit_objects) - 1)

        if normalized_count > 0:
            prev_delta = previous.hit_object_interval if previous is not None else None
            if (prev_delta is not None and
                    abs(modal_delta - prev_delta) <= RhythmDifficultyPreprocessor.SNAP_TOLERANCE):
                hit_object_interval = prev_delta
            else:
                hit_object_interval = modal_delta
        else:
            hit_object_interval = None

        prev_interval = previous.hit_object_interval if previous is not None else None
        if prev_interval is not None and hit_object_interval is not None:
            if prev_interval == 0.0:
                hit_object_interval_ratio = math.inf
            else:
                hit_object_interval_ratio = hit_object_interval / prev_interval
        else:
            hit_object_interval_ratio = 1.0

        prev_start = previous.start_time() if previous is not None else None
        curr_start = hit_objects[0].start_time if hit_objects else None
        if prev_start is not None and curr_start is not None:
            if abs(curr_start - prev_start) <= RhythmDifficultyPreprocessor.SNAP_TOLERANCE:
                interval = 0.0
            else:
                interval = curr_start - prev_start
        else:
            interval = math.inf

        return SameRhythmHitObjectGrouping(
            hit_objects=hit_objects,
            previous=previous,
            hit_object_interval=hit_object_interval,
            hit_object_interval_ratio=hit_object_interval_ratio,
            interval=interval,
        )

    @staticmethod
    def _create_same_pattern_groups(
            rhythm_groups: list[SameRhythmHitObjectGrouping],
    ) -> list[SamePatternsGroupedHitObjects]:
        """Group same-rhythm groupings that share a repeating interval pattern."""
        out: list[SamePatternsGroupedHitObjects] = []
        prev: Optional[SamePatternsGroupedHitObjects] = None
        for grouped in _group_by_interval(rhythm_groups):
            curr = SamePatternsGroupedHitObjects(groups=grouped, previous=prev)
            out.append(curr)
            prev = curr
        return out

class StaminaEvaluator:
    """Evaluates the stamina (finger-speed) difficulty of a hit."""
    @staticmethod
    def evaluate_diff_of(curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> float:
        """Return the stamina difficulty of one object."""
        if not curr.base_hit_type.is_hit():
            return 0.0

        prev = objects.previous(curr, 1)
        fingers = StaminaEvaluator._available_fingers_for(curr, objects)
        prev_mono = objects.previous_mono(curr, fingers - 1)

        object_strain = 0.5
        if prev is None:
            return object_strain

        if prev_mono is not None:
            object_strain += (
                    StaminaEvaluator._speed_bonus(curr.start_time - prev_mono.start_time)
                    + 0.5 * StaminaEvaluator._speed_bonus(curr.start_time - prev.start_time)
            )

        return object_strain

    @staticmethod
    def _available_fingers_for(curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> int:
        """Return how many fingers are assumed available for a hit."""
        ms = curr.color_data.mono_streak
        if ms is not None:
            first = ms.first_hit_object()
            if first is not None:
                prev_color_change = objects.previous_note(first, 0)
                if prev_color_change is not None and (curr.start_time - prev_color_change.start_time) < 300.0:
                    return 2

            last = ms.last_hit_object()
            if last is not None:
                next_color_change = objects.next_note(last, 0)
                if next_color_change is not None and (next_color_change.start_time - curr.start_time) < 300.0:
                    return 2

        return 8

    @staticmethod
    def _speed_bonus(interval: float) -> float:
        """Return the stamina bonus for very fast intervals."""
        interval = max(interval, 1.0)
        return 20.0 / interval

class ColorEvaluator:
    """Evaluates the colour (don/kat variation) difficulty of a hit."""
    @staticmethod
    def evaluate_difficulty_of(curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> float:
        """Return the colour difficulty of one object."""
        difficulty = 0.0
        cd = curr.color_data

        if cd.mono_streak is not None:
            first = cd.mono_streak.first_hit_object()
            if first is curr:
                difficulty += ColorEvaluator._eval_mono_streak_diff(cd.mono_streak)

        if cd.alternating_mono_pattern is not None:
            first = cd.alternating_mono_pattern.first_hit_object()
            if first is curr:
                difficulty += ColorEvaluator._eval_alternating_mono_pattern_diff(cd.alternating_mono_pattern)

        if cd.repeating_hit_patterns is not None:
            first = cd.repeating_hit_patterns.first_hit_object()
            if first is curr:
                difficulty += ColorEvaluator._eval_repeating_hit_patterns_diff(cd.repeating_hit_patterns)

        consistency_penalty = ColorEvaluator._consistent_ratio_penalty(curr, objects)
        difficulty *= consistency_penalty

        return difficulty

    @staticmethod
    def _eval_mono_streak_diff(mono_streak: MonoStreak) -> float:
        """Return the difficulty contribution of a mono streak."""
        parent_eval = (
            ColorEvaluator._eval_alternating_mono_pattern_diff(mono_streak.parent)
            if mono_streak.parent is not None else 1.0
        )
        return _logistic_exp(math.e * mono_streak.idx - 2.0 * math.e) * parent_eval * 0.5

    @staticmethod
    def _eval_alternating_mono_pattern_diff(pattern: AlternatingMonoPattern) -> float:
        """Return the difficulty contribution of an alternating pattern."""
        parent_eval = (
            ColorEvaluator._eval_repeating_hit_patterns_diff(pattern.parent)
            if pattern.parent is not None else 1.0
        )
        return _logistic_exp(math.e * pattern.idx - 2.0 * math.e) * parent_eval

    @staticmethod
    def _eval_repeating_hit_patterns_diff(repeating: RepeatingHitPatterns) -> float:
        """Return the difficulty contribution of a repeating sequence."""
        interval = float(repeating.repetition_interval)
        return 2.0 * (1.0 - _logistic_exp(math.e * interval - 2.0 * math.e))

    @staticmethod
    def _consistent_ratio_penalty(
            hit_object: TaikoDifficultyObject,
            objects: TaikoDifficultyObjects,
            threshold: float = 0.01,
            max_objects_to_check: int = 64,
    ) -> float:
        """Penalise long stretches of a consistent interval ratio."""
        consistent_ratio_count = 0
        total_ratio_count = 0.0
        recent_ratios: list[float] = []

        def iteration(current: TaikoDifficultyObject, previous_hit_object: TaikoDifficultyObject) -> bool:
            """Accumulate the penalty over one look-back step."""
            nonlocal consistent_ratio_count, total_ratio_count
            if current.idx <= 1:
                return True
            current_ratio = current.rhythm_data.ratio
            previous_ratio = previous_hit_object.rhythm_data.ratio
            recent_ratios.append(current_ratio)
            if previous_ratio == 0.0:
                return False
            if abs(1.0 - current_ratio / previous_ratio) <= threshold:
                consistent_ratio_count += 1
                total_ratio_count += current_ratio
                return True
            return False

        if max_objects_to_check > 0:
            prev = objects.previous(hit_object, 1)
            if prev is not None:
                broke = iteration(hit_object, prev)
                if not broke and max_objects_to_check > 1:
                    iteration(prev, prev)

        if consistent_ratio_count > 0:
            return 1.0 - total_ratio_count / float(consistent_ratio_count + 1) * 0.8

        if len(recent_ratios) <= 1:
            return 1.0

        avg = sum(recent_ratios) / len(recent_ratios)
        max_dev = max(abs(r - avg) for r in recent_ratios)
        return 0.7 + 0.3 * _smootherstep(max_dev, 0.0, 1.0)

class RhythmEvaluator:
    """Evaluates the rhythm-complexity difficulty of a hit."""
    @staticmethod
    def evaluate_diff_of(hit_object: TaikoDifficultyObject, hit_window: float) -> float:
        """Return the rhythm difficulty of one object."""
        rd = hit_object.rhythm_data
        difficulty = 0.0
        same_rhythm = 0.0
        same_pattern = 0.0
        interval_penalty = 0.0
        gap_penalty = 0.0

        srg = rd.same_rhythm_grouped_hit_objects
        if srg is not None and srg.first_hit_object() is hit_object:
            same_rhythm += 10.0 * RhythmEvaluator._evaluate_diff_of_inner(srg, hit_window)
            interval_penalty = RhythmEvaluator._repeated_interval_penalty(srg, hit_window)
            gap_penalty = RhythmEvaluator._long_gap_penalty(srg.previous)

        spg = rd.same_patterns_grouped_hit_objects
        if spg is not None and spg.first_hit_object() is hit_object:
            same_pattern += 1.15 * RhythmEvaluator._ratio_difficulty(spg.interval_ratio())

        difficulty += max(same_rhythm, same_pattern) * interval_penalty * gap_penalty
        return difficulty

    @staticmethod
    def _long_gap_penalty(previous: Optional["SameRhythmHitObjectGrouping"]) -> float:
        """Penalise groupings preceded by a long gap."""
        if previous is None:
            return 1.0
        gap_interval = previous.first_hit_object().delta_time
        rhythm_interval = (
            previous.hit_object_interval
            if previous.hit_object_interval is not None
            else gap_interval
        )
        rhythm_length = float(len(previous.hit_objects))
        gap_ratio = gap_interval / max(rhythm_interval, 1.0)
        gap_factor = _logistic(gap_ratio, 1.75, 20.0, 1.0)
        length_factor = _reverse_lerp(rhythm_length, 8.0, 2.0)
        return 1.0 - 0.75 * gap_factor * length_factor

    @staticmethod
    def _evaluate_diff_of_inner(
            srg: SameRhythmHitObjectGrouping,
            hit_window: float,
    ) -> float:
        """Compute the core rhythm difficulty before the gap penalty."""
        interval_diff = RhythmEvaluator._ratio_difficulty(srg.hit_object_interval_ratio)
        prev_interval = srg.previous.hit_object_interval if srg.previous is not None else None

        interval_diff *= RhythmEvaluator._repeated_interval_penalty(srg, hit_window)
        duration = srg.duration()

        if prev_interval is not None and len(srg.hit_objects) > 1 and duration is not None:
            expected_duration_from_prev = prev_interval * len(srg.hit_objects)
            duration_diff = duration - expected_duration_from_prev
            if duration_diff > 0.0:
                interval_diff *= _logistic(duration_diff / hit_window, 0.7, 1.0, 1.0)

        if duration is not None:
            interval_diff *= _logistic(duration / hit_window, 0.6, 1.0, 1.0)

        return interval_diff ** 0.75

    @staticmethod
    def _repeated_interval_penalty(
            srg: SameRhythmHitObjectGrouping,
            hit_window: float,
            threshold: float = 0.1,
    ) -> float:
        """Penalise repeated identical rhythm intervals."""
        def same_interval(start: SameRhythmHitObjectGrouping, interval_count: int) -> float:
            """Return whether two groupings share an interval."""
            intervals: list[float] = []
            curr: Optional[SameRhythmHitObjectGrouping] = start
            for _ in range(interval_count):
                if curr is None:
                    break
                if curr.hit_object_interval is not None:
                    intervals.append(curr.hit_object_interval)
                curr = curr.previous
            if len(intervals) < interval_count:
                return 1.0
            for i in range(len(intervals)):
                for j in range(i + 1, len(intervals)):
                    if intervals[j] == 0.0:
                        continue
                    ratio = intervals[i] / intervals[j]
                    if abs(1.0 - ratio) <= threshold:
                        return 0.8
            return 1.0

        long_penalty = same_interval(srg, 3)
        short_penalty = same_interval(srg, 4) if len(srg.hit_objects) < 6 else 1.0

        duration = srg.duration()
        if duration is None:
            duration_penalty = 0.5
        elif hit_window > 0:
            duration_penalty = max(1.0 - duration * 2.0 / hit_window, 0.5)
        else:
            duration_penalty = 0.5

        return min(long_penalty, short_penalty) * duration_penalty

    @staticmethod
    def _ratio_difficulty(ratio: float, terms: int = 8) -> float:
        """Return the difficulty of a given interval ratio."""
        if math.isnan(ratio) or math.isinf(ratio) or ratio == 0.0 or abs(ratio) < 1e-300:
            ratio = 0.0

        difficulty = 0.0
        for i in range(1, terms + 1):
            difficulty += -1.0 * (math.cos(float(i) * math.pi * ratio) ** 4.0)

        difficulty += float(terms) / (1.0 + ratio)
        difficulty += _bell_curve(ratio, 1.0, 0.5)
        difficulty -= _bell_curve(ratio, 1.0, 0.3)
        difficulty = max(difficulty, 0.0)
        difficulty /= math.sqrt(8.0)
        return difficulty

class ReadingEvaluator:
    """Evaluates the reading (variable scroll-speed) difficulty of a hit."""
    @staticmethod
    def evaluate_diff_of(curr: TaikoDifficultyObject) -> float:
        """Return the reading difficulty of one object from its effective BPM."""
        mid_center = (360.0 + 480.0) / 2.0
        mid_range = 480.0 - 360.0
        high_center = (480.0 + 640.0) / 2.0
        high_range = 640.0 - 480.0

        effective_bpm = max(1.0, curr.effective_bpm)

        mid_velocity_diff = 0.5 * _logistic(
            effective_bpm, mid_center, 1.0 / (mid_range / 10.0), 1.0,
                                       )
        expected_delta_time = 21_000.0 / effective_bpm
        object_density = expected_delta_time / max(1.0, curr.delta_time)

        density_penalty = _logistic(object_density, 0.925, 15.0, 1.0)

        high_velocity_diff = (1.0 - 0.33 * density_penalty) * _logistic(
            effective_bpm,
            high_center + 8.0 * density_penalty,
            (1.0 + 0.5 * density_penalty) / (high_range / 10.0),
            1.0,
            )

        return mid_velocity_diff + high_velocity_diff

class _StrainSkillBase:
    """Base class for the taiko strain skills (peak tracking and aggregation)."""
    DECAY_WEIGHT: float = DECAY_WEIGHT
    SECTION_LENGTH: float = SECTION_LENGTH_MS

    def __init__(self) -> None:
        """Initialise the skill's strain and peak state."""
        self._current_section_peak: float = 0.0
        self._current_section_end: float = 0.0
        self._strain_peaks: list[float] = []
        self._object_strains: list[float] = []

    def _strain_value_at(self, curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> float:
        """Advance and return the strain at the current object."""
        raise NotImplementedError

    def _calculate_initial_strain(self, time: float, curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> float:
        """Return the decayed strain carried into a new section."""
        raise NotImplementedError

    def process(self, curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> None:
        """Process one object, updating the running strain and section peaks."""
        section = self.SECTION_LENGTH

        if curr.idx == 0:
            self._current_section_end = math.ceil(curr.start_time / section) * section

        while curr.start_time > self._current_section_end:
            self._save_current_peak()
            self._start_new_section_from(self._current_section_end, curr, objects)
            self._current_section_end += section

        strain = self._strain_value_at(curr, objects)
        self._current_section_peak = max(strain, self._current_section_peak)
        self._object_strains.append(strain)

    def _save_current_peak(self) -> None:
        """Record the current strain as a section peak."""
        self._strain_peaks.append(self._current_section_peak)

    def _start_new_section_from(self, time: float, curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> None:
        """Begin a new strain section from a decayed baseline."""
        self._current_section_peak = self._calculate_initial_strain(time, curr, objects)

    def get_current_strain_peaks(self) -> list[float]:
        """Return the recorded strain peaks."""
        return [*self._strain_peaks, self._current_section_peak]

    def object_strains(self) -> list[float]:
        """Return the per-object strain values."""
        return self._object_strains

    @staticmethod
    def _difficulty_value(peaks: list[float], decay_weight: float) -> float:
        """Aggregate strain peaks into a difficulty value."""
        filtered = [p for p in peaks if p > 0.0]
        filtered.sort(reverse=True)
        difficulty = 0.0
        weight = 1.0
        for strain in filtered:
            difficulty += strain * weight
            weight *= decay_weight
        return difficulty

    def cloned_difficulty_value(self) -> float:
        """Return the difficulty value without consuming the peaks."""
        return self._difficulty_value(self.get_current_strain_peaks(), self.DECAY_WEIGHT)

    def into_difficulty_value(self) -> float:
        """Consume the peaks and return the difficulty value."""
        return self.cloned_difficulty_value()

    def count_top_weighted_strains(self, difficulty_value: float) -> float:
        """Return the effective count of high strains (difficulty consistency)."""
        strains = self._object_strains
        if not strains:
            return 0.0
        consistent_top_strain = difficulty_value / 10.0
        if math.isclose(consistent_top_strain, 0.0, abs_tol=1e-12):
            return float(len(strains))
        total = 0.0
        for s in strains:
            total += 1.1 / (1.0 + math.exp(-10.0 * (s / consistent_top_strain - 0.88)))
        return total

class Stamina(_StrainSkillBase):
    """The taiko stamina strain skill."""
    def __init__(self, single_color: bool, is_convert: bool) -> None:
        """Initialise the stamina skill."""
        super().__init__()
        self.single_color = single_color
        self.is_convert = is_convert
        self._current_strain = 0.0

    def _calculate_initial_strain(self, time: float, curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> float:
        """Return the decayed stamina strain into a new section."""
        if self.single_color:
            return 0.0
        prev = objects.previous(curr, 0)
        prev_start_time = prev.start_time if prev is not None else 0.0
        return self._current_strain * _strain_decay(time - prev_start_time, STAMINA_STRAIN_DECAY_BASE)

    def _strain_value_at(self, curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> float:
        """Advance and return the stamina strain at the current object."""
        self._current_strain *= _strain_decay(curr.delta_time, STAMINA_STRAIN_DECAY_BASE)
        stamina_difficulty = StaminaEvaluator.evaluate_diff_of(curr, objects) * STAMINA_SUBSKILL_MULTIPLIER

        index = 0
        ms = curr.color_data.mono_streak
        if ms is not None:
            for i, h in enumerate(ms.hit_objects):
                if h.idx == curr.idx:
                    index = i
                    break

        mono_length_bonus = (
            1.0 if self.is_convert
            else 1.0 + 0.5 * _reverse_lerp(float(index), 5.0, 20.0)
        )
        if not self.single_color:
            stamina_difficulty *= mono_length_bonus

        self._current_strain += stamina_difficulty

        if self.single_color:
            return _logistic_exp(-(float(index) - 10.0) / 2.0, self._current_strain)
        return self._current_strain

class Rhythm(_StrainSkillBase):
    """The taiko rhythm strain skill."""
    SKILL_MULTIPLIER = 1.0

    def __init__(self, great_hit_window: float) -> None:
        """Initialise the rhythm skill."""
        super().__init__()
        self.great_hit_window = great_hit_window
        self._current_strain = 0.0

    def _calculate_initial_strain(self, time: float, curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> float:
        """Return the decayed rhythm strain into a new section."""
        prev = objects.previous(curr, 0)
        prev_start_time = prev.start_time if prev is not None else 0.0
        return self._current_strain * _strain_decay(time - prev_start_time, RHYTHM_STRAIN_DECAY_BASE)

    def _strain_value_at(self, curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> float:
        """Advance and return the rhythm strain at the current object."""
        self._current_strain *= _strain_decay(curr.delta_time, RHYTHM_STRAIN_DECAY_BASE)

        difficulty = RhythmEvaluator.evaluate_diff_of(curr, self.great_hit_window)
        stamina_diff = StaminaEvaluator.evaluate_diff_of(curr, objects) - 0.5
        difficulty *= _logistic(stamina_diff, 1.0 / 15.0, 50.0)

        difficulty *= self.SKILL_MULTIPLIER
        self._current_strain += difficulty
        return self._current_strain

class Color(_StrainSkillBase):
    """The taiko colour strain skill."""
    SKILL_MULTIPLIER = COLOR_SUBSKILL_MULTIPLIER

    def __init__(self) -> None:
        """Initialise the colour skill."""
        super().__init__()
        self._current_strain = 0.0

    def _calculate_initial_strain(self, time: float, curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> float:
        """Return the decayed colour strain into a new section."""
        prev = objects.previous(curr, 0)
        prev_start_time = prev.start_time if prev is not None else 0.0
        return self._current_strain * _strain_decay(time - prev_start_time, COLOR_STRAIN_DECAY_BASE)

    def _strain_value_at(self, curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> float:
        """Advance and return the colour strain at the current object."""
        self._current_strain *= _strain_decay(curr.delta_time, COLOR_STRAIN_DECAY_BASE)
        difficulty = ColorEvaluator.evaluate_difficulty_of(curr, objects) * self.SKILL_MULTIPLIER
        self._current_strain += difficulty
        return self._current_strain

class Reading(_StrainSkillBase):
    """The taiko reading strain skill."""
    SKILL_MULTIPLIER = 1.0
    STRAIN_DECAY_BASE = 0.4

    def __init__(self) -> None:
        """Initialise the reading skill."""
        super().__init__()
        self._current_strain = 0.0
        self._reading_strain = 0.0

    def _calculate_initial_strain(self, time: float, curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> float:
        """Return the decayed reading strain into a new section."""
        prev = objects.previous(curr, 0)
        prev_start_time = prev.start_time if prev is not None else 0.0
        return self._current_strain * _strain_decay(time - prev_start_time, self.STRAIN_DECAY_BASE)

    def _strain_value_at(self, curr: TaikoDifficultyObject, objects: TaikoDifficultyObjects) -> float:
        """Advance and return the reading strain at the current object."""
        self._current_strain *= _strain_decay(curr.delta_time, self.STRAIN_DECAY_BASE)

        if curr.base_hit_type.is_hit():
            index = 0
            ms = curr.color_data.mono_streak
            if ms is not None:
                for i, h in enumerate(ms.hit_objects):
                    if h.idx == curr.idx:
                        index = i
                        break

            damp = _logistic(float(index), 4.0, -1.0 / 25.0, 0.5) + 0.5
            self._reading_strain *= damp
            self._reading_strain *= self.STRAIN_DECAY_BASE
            self._reading_strain += ReadingEvaluator.evaluate_diff_of(curr) * self.SKILL_MULTIPLIER
            val = self._reading_strain
        else:
            val = 0.0

        self._current_strain += val * self.SKILL_MULTIPLIER
        return self._current_strain

@dataclass(slots=True)
class TaikoSkills:
    """Bundle of the processed taiko skills for one beatmap."""
    rhythm: Rhythm
    reading: Reading
    color: Color
    stamina: Stamina
    single_color_stamina: Stamina

def run_skills(
        diff_objects: TaikoDifficultyObjects,
        great_hit_window: float,
        is_convert: bool,
        skill_limit: Optional[int] = None,
) -> TaikoSkills:
    """Run every taiko skill over the difficulty objects.

    Args:
        diff_objects: The preprocessed taiko difficulty objects.

    Returns:
        The processed skills.
    """
    ColorDifficultyPreprocessor.process_and_assign(diff_objects)
    RhythmDifficultyPreprocessor.process_and_assign(diff_objects)

    skills = TaikoSkills(
        rhythm=Rhythm(great_hit_window),
        reading=Reading(),
        color=Color(),
        stamina=Stamina(single_color=False, is_convert=is_convert),
        single_color_stamina=Stamina(single_color=True, is_convert=is_convert),
    )

    objs = diff_objects.objects
    if skill_limit is not None:
        objs = objs[:skill_limit]

    for obj in objs:
        skills.rhythm.process(obj, diff_objects)
        skills.reading.process(obj, diff_objects)
        skills.color.process(obj, diff_objects)
        skills.stamina.process(obj, diff_objects)
        skills.single_color_stamina.process(obj, diff_objects)

    return skills

def _rescale(stars: float) -> float:
    """Rescale a raw star value onto the final taiko star-rating curve."""
    if stars < 0.0:
        return stars
    return 10.43 * math.log(stars / 8.0 + 1.0)

def _combine_peaks(
        rhythm_peaks: list[float],
        reading_peaks: list[float],
        color_peaks: list[float],
        stamina_peaks: list[float],
        is_relax: bool,
        is_convert: bool,
        pattern_multiplier: float,
        strain_length_bonus: float,
) -> list[float]:
    """Combine the per-skill strain peaks into unified peaks."""
    out: list[float] = []
    n = min(len(rhythm_peaks), len(reading_peaks), len(color_peaks), len(stamina_peaks))
    for i in range(n):
        r = rhythm_peaks[i] * RHYTHM_SKILL_MULTIPLIER * pattern_multiplier
        c = color_peaks[i] * (0.0 if is_relax else COLOR_SKILL_MULTIPLIER)
        rd = reading_peaks[i] * READING_SKILL_MULTIPLIER
        s = stamina_peaks[i] * STAMINA_SKILL_MULTIPLIER * strain_length_bonus
        s /= 1.5 if (is_convert or is_relax) else 1.0
        peak = _norm(2.0, [_norm(1.5, [c, s]), r, rd])
        if peak > 0.0:
            out.append(peak)
    return out

def _combined_difficulty_value(
        skills: TaikoSkills,
        is_relax: bool,
        is_convert: bool,
        pattern_multiplier: float,
        strain_length_bonus: float,
) -> tuple[float, float]:
    """Aggregate the combined peaks into the mechanical difficulty and consistency."""
    hit_object_strain_peaks = _combine_peaks(
        skills.rhythm.object_strains(),
        skills.reading.object_strains(),
        skills.color.object_strains(),
        skills.stamina.object_strains(),
        is_relax, is_convert, pattern_multiplier, strain_length_bonus,
    )
    peaks = _combine_peaks(
        skills.rhythm.get_current_strain_peaks(),
        skills.reading.get_current_strain_peaks(),
        skills.color.get_current_strain_peaks(),
        skills.stamina.get_current_strain_peaks(),
        is_relax, is_convert, pattern_multiplier, strain_length_bonus,
    )

    if not peaks:
        return (0.0, 0.0)

    peaks_sorted = sorted(peaks, reverse=True)
    difficulty = 0.0
    weight = 1.0
    for strain in peaks_sorted:
        difficulty += strain * weight
        weight *= DECAY_WEIGHT

    if not hit_object_strain_peaks:
        return (0.0, 0.0)

    total_sum = sum(hit_object_strain_peaks)
    take = min(1 + len(hit_object_strain_peaks) // 20, len(hit_object_strain_peaks))
    sorted_peaks = sorted(hit_object_strain_peaks, reverse=True)
    top_avg = sum(sorted_peaks[:take]) / take if take > 0 else 0.0

    if top_avg == 0.0 or len(hit_object_strain_peaks) == 0:
        return (difficulty, 0.0)

    consistency_factor = total_sum / (top_avg * len(hit_object_strain_peaks))
    return (difficulty, consistency_factor)

@dataclass(slots=True)
class TaikoEvalResult:
    """The combined taiko skill outputs (rhythm, colour, stamina, reading, consistency)."""
    rhythm: float
    reading: float
    color: float
    stamina: float
    mono_stamina_factor: float
    mechanical_difficulty: float
    consistency_factor: float
    stars: float

def eval_skills(
        skills: TaikoSkills,
        is_convert: bool,
        is_relax: bool = False,
) -> TaikoEvalResult:
    """Evaluate all taiko skills into combined difficulty values.

    Args:
        skills: The processed taiko skills.

    Returns:
        The combined evaluation result.
    """
    rhythm_difficulty_value = skills.rhythm.cloned_difficulty_value()
    reading_difficulty_value = skills.reading.cloned_difficulty_value()
    color_difficulty_value = skills.color.cloned_difficulty_value()
    stamina_difficulty_value = skills.stamina.cloned_difficulty_value()

    rhythm_skill = rhythm_difficulty_value * RHYTHM_SKILL_MULTIPLIER
    reading_skill = reading_difficulty_value * READING_SKILL_MULTIPLIER
    color_skill = color_difficulty_value * COLOR_SKILL_MULTIPLIER
    stamina_skill = stamina_difficulty_value * STAMINA_SKILL_MULTIPLIER

    mono_stamina_rating = skills.single_color_stamina.into_difficulty_value() * STAMINA_SKILL_MULTIPLIER
    if abs(stamina_skill) >= 1e-12:
        _msr = mono_stamina_rating / stamina_skill
        mono_stamina_factor = _msr * _msr * _msr * _msr * _msr
    else:
        mono_stamina_factor = 1.0

    stamina_difficult_strains = skills.stamina.count_top_weighted_strains(stamina_difficulty_value)

    product = stamina_skill * color_skill
    pattern_multiplier = product ** 0.10 if product > 0 else 0.0
    strain_length_bonus = 1.0 + 0.15 * _reverse_lerp(stamina_difficult_strains, 1000.0, 1555.0)

    combined_rating, consistency_factor = _combined_difficulty_value(
        skills, is_relax, is_convert, pattern_multiplier, strain_length_bonus,
    )
    star_rating = _rescale(combined_rating * 1.4)

    total_skill = rhythm_skill + reading_skill + color_skill + stamina_skill
    skill_rating = star_rating / total_skill if total_skill > 0 else 0.0

    rhythm_difficulty = rhythm_skill * skill_rating
    reading_difficulty = reading_skill * skill_rating
    color_difficulty = color_skill * skill_rating
    stamina_difficulty = stamina_skill * skill_rating
    mechanical_difficulty = color_difficulty + stamina_difficulty

    return TaikoEvalResult(
        rhythm=rhythm_difficulty,
        reading=reading_difficulty,
        color=color_difficulty,
        stamina=stamina_difficulty,
        mono_stamina_factor=mono_stamina_factor,
        mechanical_difficulty=mechanical_difficulty,
        consistency_factor=consistency_factor,
        stars=star_rating,
    )