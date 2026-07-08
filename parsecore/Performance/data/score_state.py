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

from dataclasses import dataclass
from enum import Enum, auto

from .mode import GameMode


@dataclass(slots=True)
class ScoreState:
    max_combo: int = 0
    osu_large_tick_hits: int = 0
    osu_small_tick_hits: int = 0
    slider_end_hits: int = 0
    n_geki: int = 0
    n_katu: int = 0
    n300: int = 0
    n100: int = 0
    n50: int = 0
    misses: int = 0
    legacy_total_score: int | None = None

    def total_hits(self, mode: GameMode) -> int:
        amount = self.n300 + self.n100 + self.misses

        if mode != GameMode.TAIKO:
            amount += self.n50

            if mode != GameMode.OSU:
                amount += self.n_katu
                amount += (1 if mode != GameMode.CATCH else 0) * self.n_geki

        return amount

class HitResult(Enum):
    NONE = auto()
    MISS = auto()
    MEH = auto()
    OK = auto()
    GOOD = auto()
    GREAT = auto()
    PERFECT = auto()
    SMALL_TICK_MISS = auto()
    SMALL_TICK_HIT = auto()
    LARGE_TICK_MISS = auto()
    LARGE_TICK_HIT = auto()
    SMALL_BONUS = auto()
    LARGE_BONUS = auto()
    IGNORE_MISS = auto()
    IGNORE_HIT = auto()
    COMBO_BREAK = auto()
    SLIDER_TAIL_HIT = auto()
    LEGACY_COMBO_INCREASE = auto()

    def base_score(self, mode: GameMode) -> int:
        if mode == GameMode.OSU:
            return _OSU_BASE_SCORES.get(self, 0)
        raise NotImplementedError(
            f"HitResult.base_score not implemented for mode {mode.name}"
        )

_OSU_BASE_SCORES: dict["HitResult", int] = {
    HitResult.SMALL_TICK_HIT: 10,
    HitResult.LARGE_TICK_HIT: 30,
    HitResult.SLIDER_TAIL_HIT: 150,
    HitResult.MEH: 50,
    HitResult.OK: 100,
    HitResult.GOOD: 200,
    HitResult.GREAT: 300,
    HitResult.PERFECT: 300,
    HitResult.SMALL_BONUS: 10,
    HitResult.LARGE_BONUS: 50,
}

class HitResultPriority(Enum):
    BEST_CASE = auto()
    WORST_CASE = auto()

    @classmethod
    def default(cls) -> "HitResultPriority":
        return cls.BEST_CASE