"""osu!mania performance (pp) calculation.

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

from dataclasses import dataclass
from typing import Any

from ...data.beatmap import PerformanceBeatmap
from ...data.mods import PerformanceMods
from ...data.score_state import ScoreState
from .difficulty import ManiaDifficultyAttributes
from .hitresult_generator import ManiaHitResults, generate_hitresults

@dataclass(slots=True)
class ManiaPerformanceAttributes:
    """Mania performance result (pp plus the difficulty attributes used)."""
    pp: float = 0.0
    pp_difficulty: float = 0.0
    stars: float = 0.0
    max_combo: int = 0

def _custom_accuracy(hitresults: ManiaHitResults) -> float:
    """Return mania's weighted custom accuracy used by the pp formula."""
    total_hits = hitresults.total_hits()
    if total_hits == 0:
        return 0.0
    numerator = (
            hitresults.n320 * 32
            + hitresults.n300 * 30
            + hitresults.n200 * 20
            + hitresults.n100 * 10
            + hitresults.n50 * 5
    )
    denominator = total_hits * 32
    return numerator / denominator

def calculate_performance(
        pm: PerformanceBeatmap,
        attrs: ManiaDifficultyAttributes,
        mods: PerformanceMods,
        state: ScoreState,
        *,
        lazer: bool = True,
        target_accuracy: float | None = None,
        target_misses: int | None = None,
        target_combo: int | None = None,
        explicit_n300: int | None = None,
        explicit_n100: int | None = None,
        explicit_n_geki: int | None = None,
        explicit_n_katu: int | None = None,
        explicit_n50: int | None = None,
        **_: Any,
) -> ManiaPerformanceAttributes:
    """Compute the mania pp for a beatmap, mods and score state.

    Args:
        pm: The performance beatmap.
        attrs: Pre-computed difficulty attributes, or ``None`` to compute them.
        mods: The mods and clock rate.
        state: The score state (or partial input to generate one from).

    Returns:
        The mania performance attributes.
    """
    is_classic = mods.no_slider_head_acc(lazer)

    if is_classic:
        n_objects_for_hits = attrs.n_objects
    else:
        n_objects_for_hits = attrs.n_objects + attrs.n_hold_notes

    hitresults = generate_hitresults(
        n_objects=n_objects_for_hits,
        target_accuracy=target_accuracy,
        target_misses=target_misses,
        is_classic=is_classic,
        explicit_n320=explicit_n_geki,
        explicit_n300=explicit_n300,
        explicit_n200=explicit_n_katu,
        explicit_n100=explicit_n100,
        explicit_n50=explicit_n50,
    )

    total_hits = float(hitresults.total_hits())
    score_accuracy = _custom_accuracy(hitresults)

    stars = attrs.stars
    base = max(stars - 0.15, 0.05)
    difficulty_value = (
            8.0 * (base ** 2.2)
            * max(0.0, 5.0 * score_accuracy - 4.0)
            * (1.0 + 0.1 * min(1.0, total_hits / 1500.0))
    )

    multiplier = 1.0
    if mods.nf:
        multiplier *= 0.75
    if mods.ez:
        multiplier *= 0.5

    pp = difficulty_value * multiplier

    return ManiaPerformanceAttributes(
        pp=pp,
        pp_difficulty=difficulty_value,
        stars=stars,
        max_combo=attrs.max_combo,
    )