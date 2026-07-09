"""osu!taiko performance (pp) calculation.

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
from ...utils import erf, erf_inv
from .difficulty import TaikoDifficultyAttributes
from .hitresult_generator import generate_hitresults


@dataclass(slots=True)
class TaikoPerformanceAttributes:
    """Taiko performance result (pp plus the difficulty attributes used)."""
    pp: float = 0.0
    pp_acc: float = 0.0
    pp_difficulty: float = 0.0
    estimated_unstable_rate: float | None = None
    stars: float = 0.0
    max_combo: int = 0

Z_CONST = 2.32634787404
_SQRT2 = 1.4142135623730950

def _pow_int(x: float, n: int) -> float:
    """Return ``x`` to an integer power via explicit multiplication (C# ``DiffUtils.Pow``)."""
    if n == 0:
        return 1.0
    if n == 1:
        return x
    if n == 2:
        return x * x
    if n == 3:
        return x * x * x
    if n == 4:
        return x * x * x * x
    if n == 5:
        return x * x * x * x * x
    return math.pow(x, float(n))


def _logistic(x: float, midpoint: float, multiplier: float, max_value: float = 1.0) -> float:
    """Return the value of a logistic (sigmoid) curve."""
    return max_value / (1.0 + math.exp(multiplier * (midpoint - x)))

def _reverse_lerp(value: float, start: float, end: float) -> float:
    """Return the ``0``-``1`` position of a value between two bounds (clamped)."""
    if end == start:
        return 0.0
    return max(0.0, min(1.0, (value - start) / (end - start)))

def calculate_performance(
        pm: PerformanceBeatmap,
        attrs: TaikoDifficultyAttributes,
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
        explicit_large_tick_hits: int | None = None,
        explicit_small_tick_hits: int | None = None,
        explicit_slider_end_hits: int | None = None,
        **_: Any,
) -> TaikoPerformanceAttributes:
    """Compute the taiko pp for a beatmap, mods and score state.

    Args:
        pm: The performance beatmap.
        attrs: Pre-computed difficulty attributes, or ``None`` to compute them.
        mods: The mods and clock rate.
        state: The score state (or partial input to generate one from).

    Returns:
        The taiko performance attributes.
    """
    is_classic = mods.no_slider_head_acc(True)

    hitresults = generate_hitresults(
        max_combo=attrs.max_combo,
        target_accuracy=target_accuracy,
        target_misses=target_misses,
        explicit_n300=explicit_n300,
        explicit_n100=explicit_n100,
    )

    total_hits = hitresults.total_hits()

    if hitresults.n300 == 0 or attrs.great_hit_window <= 0.0 or total_hits == 0:
        eur: float | None = None
    else:
        eur = _compute_deviation_upper_bound(
            attrs=attrs,
            accuracy=hitresults.n300 / total_hits,
            n_total=total_hits,
        ) * 10.0

    total_difficult_hits = total_hits * attrs.consistency_factor

    difficulty_value = _compute_difficulty_value(
        attrs=attrs, mods=mods, is_classic=is_classic,
        total_difficult_hits=total_difficult_hits,
        estimated_unstable_rate=eur, n_total=total_hits,
        n_misses=hitresults.misses,
    ) * 1.08

    accuracy_value = _compute_accuracy_value(
        attrs=attrs, mods=mods,
        total_difficult_hits=total_difficult_hits,
        estimated_unstable_rate=eur, n_total=total_hits,
    ) * 1.1

    pp = difficulty_value + accuracy_value

    return TaikoPerformanceAttributes(
        pp=pp,
        pp_acc=accuracy_value,
        pp_difficulty=difficulty_value,
        estimated_unstable_rate=eur,
        stars=attrs.stars,
        max_combo=attrs.max_combo,
    )

def _compute_deviation_upper_bound(
        *, attrs: TaikoDifficultyAttributes, accuracy: float, n_total: int,
) -> float:
    """Estimate the player's hit deviation from the accuracy (worst-case bound)."""
    n = float(n_total)
    p = accuracy

    z_sq = Z_CONST * Z_CONST
    p_lower = (n * p + z_sq / 2.0) / (n + z_sq) \
              - Z_CONST / (n + z_sq) * math.sqrt(n * p * (1.0 - p) + z_sq / 4.0)

    if p_lower <= 0.0 or p_lower >= 1.0:
        return 0.0 if p_lower >= 1.0 else math.inf

    return attrs.great_hit_window / (_SQRT2 * erf_inv(p_lower))

def _compute_difficulty_value(
        *, attrs: TaikoDifficultyAttributes, mods: PerformanceMods,
        is_classic: bool, total_difficult_hits: float,
        estimated_unstable_rate: float | None, n_total: int, n_misses: int,
) -> float:
    """Combine the star rating and mods into the difficulty pp component."""
    if estimated_unstable_rate is None:
        return 0.0
    if math.isclose(total_difficult_hits, 0.0, abs_tol=1e-12):
        return 0.0

    eur = estimated_unstable_rate

    rhythm_expected_eur = _compute_deviation_upper_bound(
        attrs=attrs, accuracy=1.0, n_total=n_total,
    ) * 10.0
    rhythm_maximum_eur = _compute_deviation_upper_bound(
        attrs=attrs, accuracy=0.8, n_total=n_total,
    ) * 10.0

    rhythm_factor = _reverse_lerp(
        attrs.rhythm / attrs.stars if attrs.stars > 0 else 0.0,
        0.15, 0.4,
    )

    denom = rhythm_maximum_eur - rhythm_expected_eur
    if denom == 0.0:
        rhythm_penalty = 1.0
    else:
        rhythm_penalty = 1.0 - _logistic(
            eur,
            (rhythm_expected_eur + rhythm_maximum_eur) / 2.0,
            10.0 / denom,
            0.25 * (rhythm_factor * rhythm_factor * rhythm_factor),
            )

    base_difficulty = 5.0 * max(1.0, attrs.stars * rhythm_penalty / 0.11) - 4.0

    difficulty_value = min(
        (base_difficulty * base_difficulty * base_difficulty) / 69052.51,
        base_difficulty ** 2.25 / 1250.0,
        )

    difficulty_value *= 1.0 + 0.10 * max(0.0, attrs.stars - 10.0)

    length_bonus = 1.0 + 0.25 * total_difficult_hits / (total_difficult_hits + 4000.0)
    difficulty_value *= length_bonus

    miss_penalty = 0.97 + 0.03 * total_difficult_hits / (total_difficult_hits + 1500.0)
    difficulty_value *= _pow_int(miss_penalty, n_misses)

    if mods.hd:
        hidden_bonus = 0.025 if attrs.is_convert else 0.1
        if not mods.fl:
            if not is_classic:
                hidden_bonus *= 0.2
            if mods.ez and is_classic:
                hidden_bonus *= 0.5
        difficulty_value *= 1.0 + hidden_bonus

    if mods.fl:
        difficulty_value *= max(
            1.0,
            1.05 - min(attrs.mono_stamina_factor / 50.0, 1.0) * length_bonus,
            )

    mono_acc_scaling_exponent = 2.0 + attrs.mono_stamina_factor
    mono_acc_scaling_shift = 500.0 - 100.0 * (attrs.mono_stamina_factor * 3.0)

    return difficulty_value * (
        erf(mono_acc_scaling_shift / (_SQRT2 * eur))
    ) ** mono_acc_scaling_exponent

def _compute_accuracy_value(
        *, attrs: TaikoDifficultyAttributes, mods: PerformanceMods,
        total_difficult_hits: float, estimated_unstable_rate: float | None,
        n_total: int,
) -> float:
    """Compute the accuracy pp component from the deviation and object count."""
    if estimated_unstable_rate is None:
        return 0.0
    if attrs.great_hit_window <= 0.0:
        return 0.0

    eur = estimated_unstable_rate

    accuracy_value = 470.0 * (0.9885 ** eur)
    accuracy_value *= 1.0 + ((50.0 / eur) * (50.0 / eur)) * (attrs.stars ** 2.8) / 600.0

    if mods.hd and not attrs.is_convert:
        accuracy_value *= 1.075

    accuracy_value *= 1.0 + 0.3 * total_difficult_hits / (total_difficult_hits + 4000.0)

    if mods.fl and mods.hd and not attrs.is_convert:
        memory_length_bonus = min(1.15, (n_total / 1500.0) ** 0.3)
        accuracy_value *= max(1.0, 1.05 * memory_length_bonus)

    return accuracy_value