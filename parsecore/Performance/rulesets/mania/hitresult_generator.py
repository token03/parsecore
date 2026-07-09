"""Generation of mania hit-result counts from partial score information.

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


@dataclass(slots=True)
class ManiaHitResults:
    """A complete set of mania hit-result counts (geki/300/katu/100/50/miss)."""
    n320: int = 0
    n300: int = 0
    n200: int = 0
    n100: int = 0
    n50: int = 0
    misses: int = 0

    def total_hits(self) -> int:
        """Return the total number of judged objects."""
        return self.n320 + self.n300 + self.n200 + self.n100 + self.n50 + self.misses

    def accuracy(self, classic: bool) -> float:
        """Return the accuracy in the ``0``-``1`` range."""
        total_hits = self.total_hits()
        if total_hits == 0:
            return 0.0
        perfect_weight = 60 if classic else 61
        numerator = (
                perfect_weight * self.n320
                + 60 * self.n300
                + 40 * self.n200
                + 20 * self.n100
                + 10 * self.n50
        )
        denominator = perfect_weight * total_hits
        return numerator / denominator

def _round_ties_even(x: float) -> int:
    """Round half-to-even (banker's rounding), matching osu!/C#."""
    return int(round(x))

def generate_hitresults(
        n_objects: int,
        target_accuracy: float | None,
        target_misses: int | None,
        is_classic: bool,
        explicit_n320: int | None,
        explicit_n300: int | None,
        explicit_n200: int | None,
        explicit_n100: int | None,
        explicit_n50: int | None,
) -> ManiaHitResults:
    """Generate a complete mania hit-result state from the requested inputs."""
    total_hits = n_objects
    misses = target_misses if target_misses is not None else 0
    misses = min(misses, total_hits)
    remain = total_hits - misses

    if target_accuracy is None:
        n320 = explicit_n320 if explicit_n320 is not None else remain
        n320 = min(n320, remain)
        n300 = explicit_n300 if explicit_n300 is not None else 0
        n300 = min(n300, remain - n320)
        n200 = explicit_n200 if explicit_n200 is not None else 0
        n200 = min(n200, remain - n320 - n300)
        n100 = explicit_n100 if explicit_n100 is not None else 0
        n100 = min(n100, remain - n320 - n300 - n200)
        n50 = explicit_n50 if explicit_n50 is not None else 0
        n50 = min(n50, remain - n320 - n300 - n200 - n100)
        return ManiaHitResults(
            n320=n320, n300=n300, n200=n200, n100=n100, n50=n50, misses=misses,
        )

    if remain == 0:
        return ManiaHitResults(
            n320=0, n300=0, n200=0, n100=0, n50=0, misses=misses,
        )

    prelim_320 = 0 if explicit_n320 is None else min(explicit_n320, remain)
    prelim_300 = 0 if explicit_n300 is None else min(explicit_n300, remain - prelim_320)
    prelim_200 = 0 if explicit_n200 is None else min(explicit_n200, remain - prelim_320 - prelim_300)
    prelim_100 = 0 if explicit_n100 is None else min(
        explicit_n100, remain - prelim_320 - prelim_300 - prelim_200,
                       )
    prelim_50 = 0 if explicit_n50 is None else min(
        explicit_n50, remain - prelim_320 - prelim_300 - prelim_200 - prelim_100,
                      )

    provided = [explicit_n320, explicit_n300, explicit_n200, explicit_n100, explicit_n50]
    num_provided = sum(1 for v in provided if v is not None)

    if num_provided == 5:
        used = prelim_320 + prelim_300 + prelim_200 + prelim_100 + prelim_50
        left = max(remain - used, 0)
        return ManiaHitResults(
            n320=prelim_320, n300=prelim_300, n200=prelim_200,
            n100=prelim_100, n50=prelim_50 + left, misses=misses,
        )

    if num_provided == 4:
        used = prelim_320 + prelim_300 + prelim_200 + prelim_100 + prelim_50
        left = remain - used
        n320 = left if explicit_n320 is None else prelim_320
        n300 = left if explicit_n300 is None else prelim_300
        n200 = left if explicit_n200 is None else prelim_200
        n100 = left if explicit_n100 is None else prelim_100
        n50 = left if explicit_n50 is None else prelim_50
        return ManiaHitResults(
            n320=n320, n300=n300, n200=n200, n100=n100, n50=n50, misses=misses,
        )

    perfect_weight = 60 if is_classic else 61

    numerator = (
            perfect_weight * prelim_320
            + 60 * prelim_300
            + 40 * prelim_200
            + 20 * prelim_100
            + 10 * prelim_50
    )
    denominator = perfect_weight * total_hits

    target_total = _round_ties_even(max(0.0, target_accuracy * denominator - numerator))

    baseline = 10 * (remain - prelim_320 - prelim_300 - prelim_200 - prelim_100 - prelim_50)
    delta = max(0, target_total - baseline)

    n320_increase = perfect_weight - 10
    if explicit_n320 is not None:
        n320 = min(remain - prelim_300 - prelim_200 - prelim_100 - prelim_50, prelim_320)
    else:
        n320 = min(remain - prelim_300 - prelim_200 - prelim_100 - prelim_50, delta // n320_increase)
        delta = max(0, delta - n320_increase * n320)

    if explicit_n300 is not None:
        n300 = min(remain - n320 - prelim_200 - prelim_100 - prelim_50, prelim_300)
    else:
        n300 = min(remain - n320 - prelim_200 - prelim_100 - prelim_50, delta // 50)
        delta = max(0, delta - 50 * n300)

    if explicit_n200 is not None:
        n200 = min(remain - n320 - n300 - prelim_100 - prelim_50, prelim_200)
    else:
        n200 = min(remain - n320 - n300 - prelim_100 - prelim_50, delta // 30)
        delta = max(0, delta - 30 * n200)

    if explicit_n100 is not None:
        n100 = min(remain - n320 - n300 - n200 - prelim_50, prelim_100)
    else:
        n100 = min(remain - n320 - n300 - n200 - prelim_50, delta // 10)

    if explicit_n50 is not None:
        n50 = min(remain - n320 - n300 - n200 - n100, prelim_50)
    else:
        n50 = min(remain - n320 - n300 - n200 - n100, remain)

    hitresults = ManiaHitResults(
        n320=n320, n300=n300, n200=n200, n100=n100, n50=n50, misses=misses,
    )

    actual_total = hitresults.total_hits()
    if actual_total < total_hits:
        left = total_hits - actual_total
        if explicit_n320 is None:
            hitresults.n320 += left
        elif explicit_n300 is None:
            hitresults.n300 += left
        elif explicit_n200 is None:
            hitresults.n200 += left
        elif explicit_n100 is None:
            hitresults.n100 += left
        else:
            hitresults.n50 += left

    return hitresults