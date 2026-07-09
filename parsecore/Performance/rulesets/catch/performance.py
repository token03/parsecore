"""osu!catch performance (pp) calculation.

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
from dataclasses import dataclass
from typing import Any

from ...data.beatmap import PerformanceBeatmap
from ...data.mods import PerformanceMods
from ...data.score_state import ScoreState
from .difficulty import CatchDifficultyAttributes
from .hitresult_generator import CatchHitResults, generate_hitresults

@dataclass(slots=True)
class CatchPerformanceAttributes:
    """Catch performance result (pp plus the difficulty attributes used)."""
    pp: float = 0.0
    stars: float = 0.0
    max_combo: int = 0
    state_n300: int = 0
    state_n100: int = 0
    state_n50: int = 0
    state_n_katu: int = 0
    state_misses: int = 0
    state_max_combo: int = 0

def calculate_performance(
        pm: PerformanceBeatmap,
        attrs: CatchDifficultyAttributes,
        mods: PerformanceMods,
        state: ScoreState,
        *,
        lazer: bool = True,
        target_accuracy: float | None = None,
        target_misses: int | None = None,
        target_combo: int | None = None,
        explicit_n300: int | None = None,
        explicit_n100: int | None = None,
        explicit_n50: int | None = None,
        explicit_n_geki: int | None = None,
        explicit_n_katu: int | None = None,
        **_: Any,
) -> CatchPerformanceAttributes:
    """Compute the catch pp for a beatmap, mods and score state.

    Args:
        pm: The performance beatmap.
        attrs: Pre-computed difficulty attributes, or ``None`` to compute them.
        mods: The mods and clock rate.
        state: The score state (or partial input to generate one from).

    Returns:
        The catch performance attributes.
    """
    misses = (
        min(target_misses, attrs.n_fruits + attrs.n_droplets)
        if target_misses is not None
        else 0
    )
    max_combo = (
        target_combo if target_combo is not None else attrs.max_combo - misses
    )

    hitresults = generate_hitresults(
        n_fruits=attrs.n_fruits,
        n_droplets=attrs.n_droplets,
        n_tiny_droplets=attrs.n_tiny_droplets,
        acc=target_accuracy,
        fruits=explicit_n300,
        droplets=explicit_n100,
        tiny_droplets=explicit_n50,
        tiny_droplet_misses=explicit_n_katu,
        misses=target_misses,
    )

    final_results = generate_hitresults(
        n_fruits=attrs.n_fruits,
        n_droplets=attrs.n_droplets,
        n_tiny_droplets=attrs.n_tiny_droplets,
        acc=target_accuracy,
        fruits=hitresults.fruits,
        droplets=hitresults.droplets,
        tiny_droplets=hitresults.tiny_droplets,
        tiny_droplet_misses=hitresults.tiny_droplet_misses,
        misses=hitresults.misses,
    )

    pp = _calculate_pp(attrs, mods, final_results, max_combo)

    return CatchPerformanceAttributes(
        pp=pp,
        stars=attrs.stars,
        max_combo=attrs.max_combo,
        state_n300=hitresults.fruits,
        state_n100=hitresults.droplets,
        state_n50=hitresults.tiny_droplets,
        state_n_katu=hitresults.tiny_droplet_misses,
        state_misses=hitresults.misses,
        state_max_combo=max_combo,
    )

def _calculate_pp(
        attrs: CatchDifficultyAttributes,
        mods: PerformanceMods,
        hitresults: CatchHitResults,
        score_max_combo: int,
) -> float:
    """Combine the star rating, combo and accuracy into the final catch pp."""
    stars = attrs.stars
    max_combo = attrs.max_combo

    pp = math.pow(5.0 * max(stars / 0.0049, 1.0) - 4.0, 2.0) / 100_000.0

    combo_hits = hitresults.fruits + hitresults.droplets + hitresults.misses
    if combo_hits == 0:
        combo_hits = max_combo

    len_bonus = 0.95 + 0.3 * min(float(combo_hits) / 2500.0, 1.0)
    if combo_hits > 2500:
        len_bonus += math.log10(float(combo_hits) / 2500.0) * 0.475

    pp *= len_bonus

    pp *= math.pow(0.97, float(hitresults.misses))

    if score_max_combo > 0:
        denominator = math.pow(float(max_combo), 0.35)
        if denominator == 0.0:
            ratio = math.inf
        else:
            ratio = math.pow(float(score_max_combo), 0.35) / denominator
        pp *= min(ratio, 1.0)

    if attrs.preempt > 1200.0:
        ar = -(attrs.preempt - 1800.0) / 120.0
    else:
        ar = -(attrs.preempt - 1200.0) / 150.0 + 5.0

    ar_factor = 1.0
    if ar > 9.0:
        ar_factor += 0.1 * (ar - 9.0) + float(ar > 10.0) * 0.1 * (ar - 10.0)
    elif ar < 8.0:
        ar_factor += 0.025 * (8.0 - ar)
    pp *= ar_factor

    if mods.hd:
        if ar <= 10.0:
            pp *= 1.05 + 0.075 * (10.0 - ar)
        elif ar > 10.0:
            pp *= 1.01 + 0.04 * (11.0 - min(ar, 11.0))

    if mods.fl:
        pp *= 1.35 * len_bonus

    pp *= math.pow(hitresults.accuracy(), 5.5)

    if mods.nf:
        pp *= max(1.0 - 0.02 * float(hitresults.misses), 0.9)

    return pp
