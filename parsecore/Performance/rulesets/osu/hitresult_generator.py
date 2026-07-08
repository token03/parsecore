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
from typing import Optional

from ...data.score_state import HitResultPriority

class OsuScoreOrigin(Enum):
    STABLE = "stable"
    WITH_SLIDER_ACC = "with_slider_acc"
    WITHOUT_SLIDER_ACC = "without_slider_acc"

@dataclass(slots=True)
class OsuHitResults:
    n300: int = 0
    n100: int = 0
    n50: int = 0
    misses: int = 0
    large_tick_hits: int = 0
    small_tick_hits: int = 0
    slider_end_hits: int = 0

    def total_hits(self) -> int:
        return self.n300 + self.n100 + self.n50 + self.misses

    def accuracy(
            self,
            origin: OsuScoreOrigin,
            max_large_ticks: int = 0,
            max_small_ticks: int = 0,
            max_slider_ends: int = 0,
    ) -> float:
        numerator = float(6 * self.n300 + 2 * self.n100 + self.n50)
        denominator = float(6 * (self.n300 + self.n100 + self.n50 + self.misses))

        if origin == OsuScoreOrigin.WITH_SLIDER_ACC:
            slider_end_hits = min(self.slider_end_hits, max_slider_ends)
            large_tick_hits = min(self.large_tick_hits, max_large_ticks)
            numerator += 3.0 * slider_end_hits + 0.6 * large_tick_hits
            denominator += 3.0 * max_slider_ends + 0.6 * max_large_ticks
        elif origin == OsuScoreOrigin.WITHOUT_SLIDER_ACC:
            large_tick_hits = min(self.large_tick_hits, max_large_ticks)
            small_tick_hits = min(self.small_tick_hits, max_small_ticks)
            numerator += 0.6 * large_tick_hits + 0.2 * small_tick_hits
            denominator += 0.6 * max_large_ticks + 0.2 * max_small_ticks

        if denominator <= 0.0:
            return 0.0
        return numerator / denominator

@dataclass(slots=True)
class OsuScoreState:
    max_combo: int = 0
    hit_results: OsuHitResults = field(default_factory=OsuHitResults)
    legacy_total_score: Optional[int] = None

def _tick_scores(
        origin: OsuScoreOrigin,
        large_tick_hits: int,
        small_tick_hits: int,
        slider_end_hits: int,
        max_large_ticks: int,
        max_small_ticks: int,
        max_slider_ends: int,
) -> tuple[int, int]:
    if origin == OsuScoreOrigin.WITH_SLIDER_ACC:
        return (
            150 * slider_end_hits + 30 * large_tick_hits,
            150 * max_slider_ends + 30 * max_large_ticks,
        )
    if origin == OsuScoreOrigin.WITHOUT_SLIDER_ACC:
        return (
            30 * large_tick_hits + 10 * small_tick_hits,
            30 * max_large_ticks + 10 * max_small_ticks,
        )
    return (0, 0)


def generate_hitresults(
        *,
        n_objects: int,
        n_circles: int = 0,
        n_sliders: int = 0,
        n_spinners: int = 0,
        n_large_ticks: int = 0,
        target_acc: float = 1.0,
        misses: int = 0,
        n300: Optional[int] = None,
        n100: Optional[int] = None,
        n50: Optional[int] = None,
        combo: Optional[int] = None,
        max_combo: Optional[int] = None,
        priority: HitResultPriority = HitResultPriority.BEST_CASE,
        origin: OsuScoreOrigin = OsuScoreOrigin.WITH_SLIDER_ACC,
) -> OsuHitResults:
    total_hits = n_objects
    misses = max(0, min(misses, total_hits))
    remain = total_hits - misses

    if priority == HitResultPriority.BEST_CASE:
        large_tick_hits = n_large_ticks
        small_tick_hits = 0
        slider_end_hits = n_sliders
    else:
        large_tick_hits = 0
        small_tick_hits = 0
        slider_end_hits = 0

    if remain == 0:
        return OsuHitResults(
            n300=0, n100=0, n50=0, misses=misses,
            large_tick_hits=large_tick_hits,
            small_tick_hits=small_tick_hits,
            slider_end_hits=slider_end_hits,
        )

    tick_score, tick_max = _tick_scores(
        origin, large_tick_hits, small_tick_hits, slider_end_hits,
        n_large_ticks, 0, n_sliders,
    )

    has300 = n300 is not None
    has100 = n100 is not None
    has50 = n50 is not None

    prelim_300 = min(int(n300), remain) if has300 else 0
    prelim_100 = min(int(n100), remain - prelim_300) if has100 else 0
    prelim_50 = min(int(n50), remain - prelim_300 - prelim_100) if has50 else 0

    if has300 and has100 and has50:
        r300, r100, r50 = prelim_300, prelim_100, prelim_50
    elif has300 and has100 and not has50:
        r300, r100, r50 = prelim_300, prelim_100, remain - prelim_300 - prelim_100
    elif has300 and not has100 and has50:
        r300, r100, r50 = prelim_300, remain - prelim_300 - prelim_50, prelim_50
    elif not has300 and has100 and has50:
        r300, r100, r50 = remain - prelim_100 - prelim_50, prelim_100, prelim_50
    else:
        numerator = float(6 * prelim_300 + 2 * prelim_100 + prelim_50) + tick_score / 50.0
        denominator = float(6 * total_hits) + tick_max / 50.0

        raw = max(0.0, target_acc * denominator - numerator)
        target_total = int(round(raw))

        baseline = remain - prelim_300 - prelim_100 - prelim_50
        delta = max(0, target_total - baseline)

        if has300:
            r300 = min(remain - prelim_100 - prelim_50, int(n300))
        else:
            r300 = min(remain - prelim_100 - prelim_50, delta // 5)
            delta = max(0, delta - 5 * r300)

        if has100:
            r100 = min(remain - r300 - prelim_50, int(n100))
        else:
            r100 = min(remain - r300 - prelim_50, delta)

        if has50:
            r50 = min(remain - r300 - r100, int(n50))
        else:
            r50 = min(remain - r300 - r100, remain)

    res = OsuHitResults(
        n300=r300, n100=r100, n50=r50, misses=misses,
        large_tick_hits=large_tick_hits,
        small_tick_hits=small_tick_hits,
        slider_end_hits=slider_end_hits,
    )

    if res.total_hits() < total_hits:
        left = total_hits - res.total_hits()
        if priority == HitResultPriority.BEST_CASE:
            if not has300:
                res.n300 += left
            elif not has100:
                res.n100 += left
            elif not has50:
                res.n50 += left
            else:
                res.n300 += left
        else:
            if not has50:
                res.n50 += left
            elif not has100:
                res.n100 += left
            elif not has300:
                res.n300 += left
            else:
                res.n50 += left

    return res