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
from dataclasses import dataclass

@dataclass(slots=True)
class TaikoHitResults:
    n300: int = 0
    n100: int = 0
    misses: int = 0

    def total_hits(self) -> int:
        return self.n300 + self.n100 + self.misses

    def accuracy(self) -> float:
        total = self.total_hits()
        if total == 0:
            return 0.0
        numerator = 2 * self.n300 + self.n100
        denominator = 2 * total
        return numerator / denominator

def generate_hitresults(
        max_combo: int,
        target_accuracy: float | None,
        target_misses: int | None,
        explicit_n300: int | None,
        explicit_n100: int | None,
) -> TaikoHitResults:
    total_hits = max_combo
    misses = target_misses if target_misses is not None else 0
    misses = min(misses, total_hits)
    remain = total_hits - misses

    if target_accuracy is None:
        n300 = explicit_n300 if explicit_n300 is not None else remain
        n300 = min(n300, remain)
        n100 = explicit_n100 if explicit_n100 is not None else (remain - n300)
        n100 = min(n100, remain - n300)
        return TaikoHitResults(n300=n300, n100=n100, misses=misses)

    acc = target_accuracy

    if explicit_n300 is not None and explicit_n100 is not None:
        n300 = min(explicit_n300, remain)
        n100 = min(explicit_n100, remain - n300)
        return TaikoHitResults(n300=n300, n100=n100, misses=misses)

    if explicit_n300 is not None:
        n300 = min(explicit_n300, remain)
        n100 = remain - n300
        return TaikoHitResults(n300=n300, n100=n100, misses=misses)

    if explicit_n100 is not None:
        n100 = min(explicit_n100, remain)
        n300 = remain - n100
        return TaikoHitResults(n300=n300, n100=n100, misses=misses)

    if remain == 0:
        return TaikoHitResults(n300=0, n100=0, misses=misses)

    target_total = acc * (2 * total_hits)
    raw300 = target_total - remain

    min300 = min(remain, max(0, math.floor(raw300)))
    max300 = min(remain, max(0, math.ceil(raw300)))

    best_dist = math.inf
    best_n300 = 0
    best_n100 = remain

    for new300 in range(min300, max300 + 1):
        new100 = remain - new300
        candidate = TaikoHitResults(n300=new300, n100=new100, misses=misses)
        dist = abs(acc - candidate.accuracy())
        if dist < best_dist:
            best_dist = dist
            best_n300 = new300
            best_n100 = new100

    return TaikoHitResults(n300=best_n300, n100=best_n100, misses=misses)