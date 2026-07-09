"""Gradual (object-by-object) catch difficulty and performance calculation.

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
from dataclasses import dataclass, field, replace
from typing import Any

from parsecore.Beatmap.utils import f32

from ...data.attributes import AdjustedBeatmapAttributes, as_override
from ...data.mode import GameMode
from ...data.mods import PerformanceMods
from .convert import calculate_catch_width, convert_objects
from .difficulty import (
    DIFFICULTY_MULTIPLIER,
    CatchDifficultyAttributes,
    _create_difficulty_objects,
)
from .hit_objects import GradualObjectCountBuilder
from .hitresult_generator import CatchHitResults
from .performance import CatchPerformanceAttributes, calculate_performance
from .skills import Movement


@dataclass(slots=True)
class CatchScoreState:
    """A catch score state (fruits, droplets, tiny droplets and their misses)."""
    max_combo: int = 0
    hitresults: CatchHitResults = field(default_factory=CatchHitResults)

class CatchGradualDifficulty:

    """Iterates catch difficulty attributes, revealing one more object each step."""
    def __init__(self, difficulty: Any, beatmap: Any) -> None:
        """Prepare the gradual calculation.

        Args:
            difficulty: A configured :class:`~parsecore.Performance.api.Difficulty`.
            beatmap: The beatmap to evaluate.
        """
        from ...api import Difficulty, _coerce_to_performance_beatmap

        if not isinstance(difficulty, Difficulty):
            raise TypeError("expected a parsecore Difficulty instance")

        pm = _coerce_to_performance_beatmap(beatmap)
        if pm.mode != GameMode.CATCH:
            raise ValueError(
                f"cannot calculate catch difficulty for {pm.mode.name} map"
            )

        mods = difficulty._mods or PerformanceMods.from_mods(0)
        if difficulty._clock_rate is not None:
            mods.clock_rate = difficulty._clock_rate

        adjusted = AdjustedBeatmapAttributes.create(
            base_cs=pm.base_cs, base_ar=pm.base_ar,
            base_od=pm.base_od, base_hp=pm.base_hp,
            mode=GameMode.CATCH, mods=mods,
            ar_override=as_override(difficulty._ar),
            cs_override=as_override(difficulty._cs),
            hp_override=as_override(difficulty._hp),
            od_override=as_override(difficulty._od),
        )

        cs = adjusted.cs
        clock_rate = adjusted.clock_rate

        count = GradualObjectCountBuilder()
        palpable_objects = convert_objects(
            pm, count, mods.reflection, mods.hardrock_offsets, cs,
        )

        half_catcher_width = f32(calculate_catch_width(cs) * 0.5)
        half_catcher_width = f32(
            half_catcher_width
            * f32(1.0 - f32(max(f32(cs - 5.5), 0.0) * 0.0625))
        )

        self._mods = mods
        self._lazer = difficulty._lazer
        self._pm = pm
        self.idx = 0
        self._count = count.all
        self._diff_objects = _create_difficulty_objects(
            clock_rate, half_catcher_width, palpable_objects,
        )
        self._movement = Movement(clock_rate)
        self._attrs = CatchDifficultyAttributes(
            preempt=adjusted.hit_windows.ar or 0.0,
            is_convert=pm.is_convert,
            ar=adjusted.ar,
            cs=adjusted.cs,
            hp=adjusted.hp,
            od=adjusted.od,
            clock_rate=clock_rate,
        )

    def __iter__(self) -> CatchGradualDifficulty:
        """Return the iterator (``self``)."""
        return self

    def __len__(self) -> int:
        """Return the number of remaining steps."""
        return len(self._diff_objects) + 1 - self.idx

    def _add_object_count(self) -> None:
        """Advance the internal object counts by the next object."""
        count = self._count[self.idx]
        if count.fruit:
            self._attrs.n_fruits += 1
        else:
            self._attrs.n_droplets += 1
        self._attrs.n_tiny_droplets += count.tiny_droplets

    def _current_attrs(self) -> CatchDifficultyAttributes:
        """Compute the attributes for the objects revealed so far."""
        attrs = replace(self._attrs)
        movement = self._movement.into_difficulty_value()
        attrs.stars = math.sqrt(movement) * DIFFICULTY_MULTIPLIER
        return attrs

    def __next__(self) -> CatchDifficultyAttributes:
        """Reveal the next object and return the attributes, or stop."""
        if self.idx > 0:
            if self.idx - 1 >= len(self._diff_objects):
                raise StopIteration
            curr = self._diff_objects[self.idx - 1]
            self._movement.process(curr, self._diff_objects)
        elif not self._count:
            raise StopIteration

        self._add_object_count()
        self.idx += 1

        return self._current_attrs()

    def next(self) -> CatchDifficultyAttributes | None:
        """Reveal the next object and return its attributes, or ``None``."""
        try:
            return self.__next__()
        except StopIteration:
            return None

    def nth(self, n: int) -> CatchDifficultyAttributes | None:
        """Skip ahead and return the attributes after the ``n``-th next object.

        Args:
            n: How many objects to advance (0 = the next object).

        Returns:
            The attributes at that point, or ``None`` if exhausted.
        """
        skip_from = max(self.idx - 1, 0)
        take = min(n, max(len(self) - 1, 0))

        if self.idx == 0 and take > 0:
            take -= 1
            self._add_object_count()
            self.idx += 1

        for curr in self._diff_objects[skip_from:skip_from + take]:
            self._movement.process(curr, self._diff_objects)
            self._add_object_count()
            self.idx += 1

        return self.next()

class CatchGradualPerformance:

    """Feeds gradual difficulty into pp for object-by-object performance."""
    def __init__(self, difficulty: Any, beatmap: Any) -> None:
        """Prepare the gradual performance calculation.

        Args:
            difficulty: A configured difficulty builder.
            beatmap: The beatmap to evaluate.
        """
        self._difficulty = CatchGradualDifficulty(difficulty, beatmap)

    def __len__(self) -> int:
        """Return the number of remaining steps."""
        return len(self._difficulty)

    def next(self, state: CatchScoreState) -> CatchPerformanceAttributes | None:
        """Advance one object and return the pp for the given state.

        Args:
            state: The score state so far.

        Returns:
            The performance attributes, or ``None`` if exhausted.
        """
        return self.nth(state, 0)

    def last(self, state: CatchScoreState) -> CatchPerformanceAttributes | None:
        """Advance to the final object and return the pp for the state."""
        return self.nth(state, (1 << 62))

    def nth(self, state: CatchScoreState, n: int) -> CatchPerformanceAttributes | None:
        """Advance ``n`` objects and return the pp for the state."""
        attrs = self._difficulty.nth(n)
        if attrs is None:
            return None

        hr = state.hitresults
        return calculate_performance(
            self._difficulty._pm, attrs, self._difficulty._mods, None,
            lazer=self._difficulty._lazer,
            target_accuracy=None,
            target_misses=hr.misses,
            target_combo=state.max_combo,
            explicit_n300=hr.fruits,
            explicit_n100=hr.droplets,
            explicit_n50=hr.tiny_droplets,
            explicit_n_katu=hr.tiny_droplet_misses,
        )
