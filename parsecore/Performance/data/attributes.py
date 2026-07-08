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

import math
from dataclasses import dataclass

from parsecore.Beatmap.utils import f32

from .mode import GameMode
from .mods import PerformanceMods

_F32_1_4 = f32(1.4)
_F32_1_3 = f32(1.3)

_VALUE = "value"
_GIVEN = "given"
_FIXED = "fixed"

def _difficulty_range(difficulty: float, min_val: float, mid_val: float, max_val: float) -> float:
    if difficulty > 5.0:
        return mid_val + (max_val - mid_val) * (difficulty - 5.0) / 5.0
    if difficulty < 5.0:
        return mid_val - (mid_val - min_val) * (5.0 - difficulty) / 5.0
    return mid_val

def _inverse_difficulty_range(time: float, min_val: float, mid_val: float, max_val: float) -> float:
    if time > mid_val:
        return 5.0 - (time - mid_val) * 5.0 / (min_val - mid_val)
    if time < mid_val:
        return 5.0 + (mid_val - time) * 5.0 / (mid_val - max_val)
    return 5.0

@dataclass(slots=True)
class GameModeHitWindows:
    min: float
    mid: float
    max: float

    def difficulty_range(self, difficulty: float) -> float:
        return _difficulty_range(difficulty, self.min, self.mid, self.max)

    def inverse_difficulty_range(self, time: float) -> float:
        return _inverse_difficulty_range(time, self.min, self.mid, self.max)

AR_WINDOWS = GameModeHitWindows(min=1800.0, mid=1200.0, max=450.0)

OSU_GREAT = GameModeHitWindows(min=80.0, mid=50.0, max=20.0)
OSU_OK = GameModeHitWindows(min=140.0, mid=100.0, max=60.0)
OSU_MEH = GameModeHitWindows(min=200.0, mid=150.0, max=100.0)

TAIKO_GREAT = GameModeHitWindows(min=50.0, mid=35.0, max=20.0)
TAIKO_OK = GameModeHitWindows(min=120.0, mid=80.0, max=50.0)

MANIA_PERFECT = GameModeHitWindows(min=22.4, mid=19.4, max=13.9)
MANIA_GREAT = GameModeHitWindows(min=64.0, mid=49.0, max=34.0)
MANIA_GOOD = GameModeHitWindows(min=97.0, mid=82.0, max=67.0)
MANIA_OK = GameModeHitWindows(min=127.0, mid=112.0, max=97.0)
MANIA_MEH = GameModeHitWindows(min=151.0, mid=136.0, max=121.0)

@dataclass(slots=True)
class HitWindows:
    ar: float | None = None
    od_perfect: float | None = None
    od_great: float | None = None
    od_good: float | None = None
    od_ok: float | None = None
    od_meh: float | None = None

@dataclass(slots=True)
class AdjustedBeatmapAttributes:
    cs: float
    ar: float
    od: float
    hp: float
    clock_rate: float
    hit_windows: HitWindows
    raw_cs: float = 5.0
    raw_od: float = 5.0
    raw_hp: float = 5.0

    @classmethod
    def create(
            cls,
            base_cs: float,
            base_ar: float,
            base_od: float,
            base_hp: float,
            mode: GameMode,
            mods: PerformanceMods,
            *,
            is_convert: bool = False,
            classic_and_not_v2: bool = False,
            ar_override: "tuple[float, bool] | None" = None,
            od_override: "tuple[float, bool] | None" = None,
            cs_override: "tuple[float, bool] | None" = None,
            hp_override: "tuple[float, bool] | None" = None,
    ) -> "AdjustedBeatmapAttributes":
        def _state(base: float, clamp01: bool, override: "tuple[float, bool] | None"):
            if override is not None:
                value, fixed = override
                return [f32(max(-20.0, min(20.0, value))), _FIXED if fixed else _GIVEN]
            if clamp01:
                base = max(0.0, min(10.0, base))
            return [f32(base), _VALUE]

        ar_s = _state(base_ar, True, ar_override)
        od_s = _state(base_od, True, od_override)
        cs_s = _state(base_cs, False, cs_override)
        hp_s = _state(base_hp, False, hp_override)

        def _try_mutate(state, fn) -> None:
            if state[1] != _FIXED:
                state[0] = fn(state[0])

        if mods.ez:
            _try_mutate(ar_s, lambda v: f32(v * 0.5))
            _try_mutate(cs_s, lambda v: f32(v * 0.5))
            _try_mutate(hp_s, lambda v: f32(v * 0.5))
            if mode != GameMode.MANIA:
                _try_mutate(od_s, lambda v: f32(v * 0.5))
        elif mods.hr:
            _try_mutate(hp_s, lambda v: min(f32(v * _F32_1_4), 10.0))
            if mode != GameMode.MANIA:
                _try_mutate(od_s, lambda v: min(f32(v * _F32_1_4), 10.0))
            if mode == GameMode.OSU or mode == GameMode.CATCH:
                _try_mutate(cs_s, lambda v: min(f32(v * _F32_1_3), 10.0))
                _try_mutate(ar_s, lambda v: min(f32(v * _F32_1_4), 10.0))

        clock_rate = mods.clock_rate

        hw = _compute_hit_windows(
            ar_state=ar_s, od_state=od_s, mode=mode, clock_rate=clock_rate,
            is_convert=is_convert, classic_and_not_v2=classic_and_not_v2,
        )

        ar_val, ar_kind = ar_s
        od_val, od_kind = od_s

        final_ar = float(ar_val)
        final_od = float(od_val)
        if mode in (GameMode.OSU, GameMode.CATCH) and ar_kind != _FIXED:
            final_ar = AR_WINDOWS.inverse_difficulty_range(
                AR_WINDOWS.difficulty_range(float(ar_val)) / clock_rate
            )
        if mode == GameMode.OSU and hw.od_great is not None:
            final_od = (79.5 - hw.od_great) / 6.0

        raw_od = float(od_val)
        if od_kind == _FIXED and mode in (GameMode.OSU, GameMode.TAIKO):
            windows = OSU_GREAT if mode == GameMode.OSU else TAIKO_GREAT
            raw_od = f32(windows.inverse_difficulty_range(
                windows.difficulty_range(float(od_val)) * clock_rate
            ))

        return cls(
            cs=float(cs_s[0]),
            ar=final_ar,
            od=final_od,
            hp=float(hp_s[0]),
            clock_rate=clock_rate,
            hit_windows=hw,
            raw_cs=float(cs_s[0]),
            raw_od=raw_od,
            raw_hp=float(hp_s[0]),
        )

def as_override(value) -> "tuple[float, bool] | None":
    if value is None:
        return None
    if isinstance(value, tuple):
        return (float(value[0]), bool(value[1]))
    return (float(value), False)


def _compute_hit_windows(
        *,
        ar_state: list,
        od_state: list,
        mode: GameMode,
        clock_rate: float,
        is_convert: bool,
        classic_and_not_v2: bool,
) -> HitWindows:
    ar, ar_kind = ar_state
    od, od_kind = od_state

    hw = HitWindows()

    if mode in (GameMode.OSU, GameMode.CATCH):
        if ar_kind == _FIXED:
            hw.ar = AR_WINDOWS.difficulty_range(float(ar))
        else:
            hw.ar = AR_WINDOWS.difficulty_range(float(ar)) / clock_rate

    def osu_taiko_set_difficulty(windows: GameModeHitWindows) -> float:
        if od_kind == _FIXED:
            f_value = windows.difficulty_range(float(od)) * clock_rate
            return (math.floor(f_value) - 0.5) / clock_rate
        return (math.floor(windows.difficulty_range(float(od))) - 0.5) / clock_rate

    if mode == GameMode.OSU:
        hw.od_great = osu_taiko_set_difficulty(OSU_GREAT)
        hw.od_ok = osu_taiko_set_difficulty(OSU_OK)
        hw.od_meh = osu_taiko_set_difficulty(OSU_MEH)
    elif mode == GameMode.TAIKO:
        hw.od_great = osu_taiko_set_difficulty(TAIKO_GREAT)
        hw.od_ok = osu_taiko_set_difficulty(TAIKO_OK)
    elif mode == GameMode.MANIA:
        hw = _compute_mania_hit_windows(
            ar_hw=hw, od=float(od), is_convert=is_convert,
            classic_and_not_v2=classic_and_not_v2,
        )

    return hw

def _compute_mania_hit_windows(
        *,
        ar_hw: HitWindows,
        od: float,
        is_convert: bool,
        classic_and_not_v2: bool,
) -> HitWindows:
    speed_multiplier = 1.0
    difficulty_multiplier = 1.0
    total_multiplier = speed_multiplier / difficulty_multiplier

    if classic_and_not_v2:
        if is_convert:
            od_rounded = _round_ties_even(od)
            great_base = 34.0 if od_rounded > 4.0 else 47.0
            good_base = 67.0 if od_rounded > 4.0 else 77.0
            perfect = math.floor(16.0 * total_multiplier) + 0.5
            great = math.floor(great_base * total_multiplier) + 0.5
            good = math.floor(good_base * total_multiplier) + 0.5
            ok = math.floor(97.0 * total_multiplier) + 0.5
            meh = math.floor(121.0 * total_multiplier) + 0.5
        else:
            inverted_od = max(0.0, min(10.0, 10.0 - od))

            def hw_value(add: float) -> float:
                return math.floor((add + 3.0 * inverted_od) * total_multiplier) + 0.5

            perfect = math.floor(16.0 * total_multiplier) + 0.5
            great = hw_value(34.0)
            good = hw_value(67.0)
            ok = hw_value(97.0)
            meh = hw_value(121.0)
    else:
        def hw_from_range(windows: GameModeHitWindows) -> float:
            return math.floor(windows.difficulty_range(od) * total_multiplier) + 0.5

        perfect = hw_from_range(MANIA_PERFECT)
        great = hw_from_range(MANIA_GREAT)
        good = hw_from_range(MANIA_GOOD)
        ok = hw_from_range(MANIA_OK)
        meh = hw_from_range(MANIA_MEH)

    return HitWindows(
        ar=ar_hw.ar,
        od_perfect=perfect,
        od_great=great,
        od_good=good,
        od_ok=ok,
        od_meh=meh,
    )

def _round_ties_even(x: float) -> float:
    return float(round(x))