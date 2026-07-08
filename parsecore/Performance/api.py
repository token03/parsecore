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

from typing import Any

from .data.beatmap import PerformanceBeatmap
from .data.mode import GameMode
from .data.mods import PerformanceMods
from .data.score_state import ScoreState

class RulesetNotImplementedError(NotImplementedError):
    def __init__(self, mode: GameMode, stage: str) -> None:
        self.mode = mode
        self.stage = stage
        super().__init__(
            f"ruleset {mode.name.lower()!r} {stage} is not implemented yet"
        )

class Beatmap:
    __slots__ = ("_pm",)

    def __init__(self, pm: PerformanceBeatmap) -> None:
        self._pm = pm

    @classmethod
    def from_path(cls, path: str) -> "Beatmap":
        from parsecore.Beatmap.beatmap import Beatmap as UserBeatmap
        return cls.from_user_beatmap(UserBeatmap.from_path(path))

    @classmethod
    def from_user_beatmap(
            cls,
            user_beatmap: Any,
            override_mode: GameMode | None = None,
    ) -> "Beatmap":
        return cls(PerformanceBeatmap(user_beatmap, override_mode=override_mode))

    @property
    def mode(self) -> GameMode:
        return self._pm.mode

    @property
    def inner(self) -> PerformanceBeatmap:
        return self._pm

def _import_difficulty(mode: GameMode):
    try:
        if mode == GameMode.OSU:
            from .rulesets.osu.difficulty import calculate_difficulty
        elif mode == GameMode.TAIKO:
            from .rulesets.taiko.difficulty import calculate_difficulty
        elif mode == GameMode.CATCH:
            from .rulesets.catch.difficulty import calculate_difficulty
        elif mode == GameMode.MANIA:
            from .rulesets.mania.difficulty import calculate_difficulty
        else:
            raise ValueError(f"unknown mode: {mode}")
        return calculate_difficulty
    except ImportError as e:
        raise RulesetNotImplementedError(mode, "difficulty") from e

def _call_difficulty(mode: GameMode, *args: Any, **kwargs: Any) -> Any:
    calc = _import_difficulty(mode)
    try:
        return calc(*args, **kwargs)
    except NotImplementedError as e:
        if isinstance(e, RulesetNotImplementedError):
            raise
        raise RulesetNotImplementedError(mode, "difficulty") from e

def _import_performance(mode: GameMode):
    try:
        if mode == GameMode.OSU:
            from .rulesets.osu.performance import calculate_performance
        elif mode == GameMode.TAIKO:
            from .rulesets.taiko.performance import calculate_performance
        elif mode == GameMode.CATCH:
            from .rulesets.catch.performance import calculate_performance
        elif mode == GameMode.MANIA:
            from .rulesets.mania.performance import calculate_performance
        else:
            raise ValueError(f"unknown mode: {mode}")
        return calculate_performance
    except ImportError as e:
        raise RulesetNotImplementedError(mode, "performance") from e

def _call_performance(mode: GameMode, *args: Any, **kwargs: Any) -> Any:
    calc = _import_performance(mode)
    try:
        return calc(*args, **kwargs)
    except NotImplementedError as e:
        if isinstance(e, RulesetNotImplementedError):
            raise
        raise RulesetNotImplementedError(mode, "performance") from e

class Difficulty:
    __slots__ = (
        "_mods", "_clock_rate", "_lazer",
        "_ar", "_cs", "_hp", "_od", "_passed_objects",
    )

    def __init__(self) -> None:
        self._mods: PerformanceMods | None = None
        self._clock_rate: float | None = None
        self._lazer: bool = True
        self._ar: tuple[float, bool] | None = None
        self._cs: tuple[float, bool] | None = None
        self._hp: tuple[float, bool] | None = None
        self._od: tuple[float, bool] | None = None
        self._passed_objects: int | None = None

    def mods(self, mods: Any) -> "Difficulty":
        self._mods = (
            mods if isinstance(mods, PerformanceMods) else PerformanceMods.from_mods(mods)
        )
        return self

    def clock_rate(self, cr: float) -> "Difficulty":
        self._clock_rate = float(cr)
        return self

    def lazer(self, lazer: bool) -> "Difficulty":
        self._lazer = bool(lazer)
        return self

    def ar(self, ar: float, fixed: bool = False) -> "Difficulty":
        self._ar = (float(ar), bool(fixed))
        return self

    def cs(self, cs: float, fixed: bool = False) -> "Difficulty":
        self._cs = (float(cs), bool(fixed))
        return self

    def hp(self, hp: float, fixed: bool = False) -> "Difficulty":
        self._hp = (float(hp), bool(fixed))
        return self

    def od(self, od: float, fixed: bool = False) -> "Difficulty":
        self._od = (float(od), bool(fixed))
        return self

    def passed_objects(self, n: int) -> "Difficulty":
        self._passed_objects = int(n)
        return self

    def calculate(self, beatmap: "Beatmap | PerformanceBeatmap | Any") -> Any:
        pm = _coerce_to_performance_beatmap(beatmap)
        mods = self._mods or PerformanceMods.from_mods(0)
        if self._clock_rate is not None:
            mods.clock_rate = self._clock_rate
        return _call_difficulty(
            pm.mode,
            pm, mods,
            lazer=self._lazer,
            ar_override=self._ar, cs_override=self._cs,
            hp_override=self._hp, od_override=self._od,
            passed_objects=self._passed_objects,
        )

class Performance:
    __slots__ = (
        "_beatmap", "_mods", "_clock_rate", "_lazer",
        "_accuracy", "_combo", "_misses",
        "_n300", "_n100", "_n50", "_n_geki", "_n_katu",
        "_large_tick_hits", "_small_tick_hits", "_slider_end_hits",
        "_passed_objects", "_legacy_total_score",
        "_ar", "_cs", "_hp", "_od",
    )

    def __init__(self, beatmap: "Beatmap | PerformanceBeatmap | Any") -> None:
        self._beatmap = _coerce_to_performance_beatmap(beatmap)
        self._mods: PerformanceMods | None = None
        self._clock_rate: float | None = None
        self._lazer: bool = True
        self._accuracy: float | None = None
        self._combo: int | None = None
        self._misses: int | None = None
        self._n300: int | None = None
        self._n100: int | None = None
        self._n50: int | None = None
        self._n_geki: int | None = None
        self._n_katu: int | None = None
        self._large_tick_hits: int | None = None
        self._small_tick_hits: int | None = None
        self._slider_end_hits: int | None = None
        self._passed_objects: int | None = None
        self._legacy_total_score: int | None = None
        self._ar: tuple[float, bool] | None = None
        self._cs: tuple[float, bool] | None = None
        self._hp: tuple[float, bool] | None = None
        self._od: tuple[float, bool] | None = None

    def mods(self, mods: Any) -> "Performance":
        self._mods = (
            mods if isinstance(mods, PerformanceMods) else PerformanceMods.from_mods(mods)
        )
        return self

    def clock_rate(self, cr: float) -> "Performance":
        self._clock_rate = float(cr)
        return self

    def lazer(self, lazer: bool) -> "Performance":
        self._lazer = bool(lazer)
        return self

    def accuracy(self, acc: float) -> "Performance":
        self._accuracy = float(acc) / 100.0 if acc > 1.0 else float(acc)
        return self

    def combo(self, c: int) -> "Performance":
        self._combo = int(c)
        return self

    def misses(self, m: int) -> "Performance":
        self._misses = int(m)
        return self

    def n300(self, n: int) -> "Performance":
        self._n300 = int(n)
        return self

    def n100(self, n: int) -> "Performance":
        self._n100 = int(n)
        return self

    def n50(self, n: int) -> "Performance":
        self._n50 = int(n)
        return self

    def n_geki(self, n: int) -> "Performance":
        self._n_geki = int(n)
        return self

    def n_katu(self, n: int) -> "Performance":
        self._n_katu = int(n)
        return self

    def large_tick_hits(self, n: int) -> "Performance":
        self._large_tick_hits = int(n)
        return self

    def small_tick_hits(self, n: int) -> "Performance":
        self._small_tick_hits = int(n)
        return self

    def slider_end_hits(self, n: int) -> "Performance":
        self._slider_end_hits = int(n)
        return self

    def passed_objects(self, n: int) -> "Performance":
        self._passed_objects = int(n)
        return self

    def legacy_total_score(self, score: int) -> "Performance":
        self._legacy_total_score = int(score)
        return self

    def ar(self, ar: float, fixed: bool = False) -> "Performance":
        self._ar = (float(ar), bool(fixed))
        return self

    def cs(self, cs: float, fixed: bool = False) -> "Performance":
        self._cs = (float(cs), bool(fixed))
        return self

    def hp(self, hp: float, fixed: bool = False) -> "Performance":
        self._hp = (float(hp), bool(fixed))
        return self

    def od(self, od: float, fixed: bool = False) -> "Performance":
        self._od = (float(od), bool(fixed))
        return self

    def calculate(self, attrs: Any | None = None) -> Any:
        pm = self._beatmap
        mods = self._mods or PerformanceMods.from_mods(0)
        if self._clock_rate is not None:
            mods.clock_rate = self._clock_rate

        if attrs is None:
            d = Difficulty()
            d._mods = mods
            d._lazer = self._lazer
            d._passed_objects = self._passed_objects
            d._ar = self._ar
            d._cs = self._cs
            d._hp = self._hp
            d._od = self._od
            attrs = d.calculate(pm)

        state = ScoreState(
            n300=self._n300 or 0,
            n100=self._n100 or 0,
            n50=self._n50 or 0,
            misses=self._misses or 0,
            max_combo=self._combo or 0,
            n_geki=self._n_geki or 0,
            n_katu=self._n_katu or 0,
            osu_large_tick_hits=self._large_tick_hits or 0,
            osu_small_tick_hits=self._small_tick_hits or 0,
            slider_end_hits=self._slider_end_hits or 0,
            legacy_total_score=self._legacy_total_score,
        )

        calc_res = _call_performance(
            pm.mode,
            pm, attrs, mods, state,
            lazer=self._lazer,
            target_accuracy=self._accuracy,
            target_misses=self._misses,
            target_combo=self._combo,
            explicit_n300=self._n300,
            explicit_n100=self._n100,
            explicit_n50=self._n50,
            explicit_n_geki=self._n_geki,
            explicit_n_katu=self._n_katu,
            explicit_large_tick_hits=self._large_tick_hits,
            explicit_small_tick_hits=self._small_tick_hits,
            explicit_slider_end_hits=self._slider_end_hits,
        )
        return calc_res

def _coerce_to_performance_beatmap(beatmap: Any) -> PerformanceBeatmap:
    if isinstance(beatmap, Beatmap):
        return beatmap.inner
    if isinstance(beatmap, PerformanceBeatmap):
        return beatmap
    return PerformanceBeatmap(beatmap)
