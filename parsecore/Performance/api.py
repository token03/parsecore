"""Public calculation API: the Beatmap, Difficulty and Performance builders.

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
    """Raised when a ruleset does not implement the requested calculation stage."""
    def __init__(self, mode: GameMode, stage: str) -> None:
        """Initialise with the offending mode and stage.

        Args:
            mode: The game mode that lacks an implementation.
            stage: The calculation stage (``difficulty`` or ``performance``).
        """
        self.mode = mode
        self.stage = stage
        super().__init__(
            f"ruleset {mode.name.lower()!r} {stage} is not implemented yet"
        )

class Beatmap:
    """A beatmap prepared for calculation, wrapping a parsed map.

    Create one with :meth:`from_path` or :meth:`from_user_beatmap`, then pass it to
    :class:`Difficulty` or :class:`Performance`.
    """
    __slots__ = ("_pm",)

    def __init__(self, pm: PerformanceBeatmap) -> None:
        """Wrap an already-prepared performance beatmap.

        Args:
            pm: The internal performance beatmap.
        """
        self._pm = pm

    @classmethod
    def from_path(cls, path: str) -> "Beatmap":
        """Load and prepare a beatmap from a ``.osu`` file.

        Args:
            path: Path to the ``.osu`` file.

        Returns:
            The prepared beatmap in its native mode.
        """
        from parsecore.Beatmap.beatmap import Beatmap as UserBeatmap
        return cls.from_user_beatmap(UserBeatmap.from_path(path))

    @classmethod
    def from_user_beatmap(
            cls,
            user_beatmap: Any,
            override_mode: GameMode | None = None,
    ) -> "Beatmap":
        """Prepare a beatmap from an already-parsed map, optionally converting it.

        Args:
            user_beatmap: A parsed :class:`parsecore.Beatmap.beatmap.Beatmap`.
            override_mode: The target ruleset to convert to, or ``None`` to keep the
                map's native mode.

        Returns:
            The prepared beatmap.
        """
        return cls(PerformanceBeatmap(user_beatmap, override_mode=override_mode))

    @property
    def mode(self) -> GameMode:
        """Return the (possibly converted) game mode of this beatmap."""
        return self._pm.mode

    @property
    def inner(self) -> PerformanceBeatmap:
        """Return the underlying performance beatmap."""
        return self._pm

def _import_difficulty(mode: GameMode):
    """Import the difficulty calculator module for a ruleset."""
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
    """Dispatch a difficulty calculation to the ruleset's implementation."""
    calc = _import_difficulty(mode)
    try:
        return calc(*args, **kwargs)
    except NotImplementedError as e:
        if isinstance(e, RulesetNotImplementedError):
            raise
        raise RulesetNotImplementedError(mode, "difficulty") from e

def _import_performance(mode: GameMode):
    """Import the performance calculator module for a ruleset."""
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
    """Dispatch a performance calculation to the ruleset's implementation."""
    calc = _import_performance(mode)
    try:
        return calc(*args, **kwargs)
    except NotImplementedError as e:
        if isinstance(e, RulesetNotImplementedError):
            raise
        raise RulesetNotImplementedError(mode, "performance") from e

class Difficulty:
    """Builder for a star-rating (difficulty) calculation.

    Configure mods, clock rate and difficulty overrides with the chaining methods,
    then call :meth:`calculate`.
    """
    __slots__ = (
        "_mods", "_clock_rate", "_lazer",
        "_ar", "_cs", "_hp", "_od", "_passed_objects",
    )

    def __init__(self) -> None:
        """Create a difficulty builder with default (NoMod, lazer) settings."""
        self._mods: PerformanceMods | None = None
        self._clock_rate: float | None = None
        self._lazer: bool = True
        self._ar: tuple[float, bool] | None = None
        self._cs: tuple[float, bool] | None = None
        self._hp: tuple[float, bool] | None = None
        self._od: tuple[float, bool] | None = None
        self._passed_objects: int | None = None

    def mods(self, mods: Any) -> "Difficulty":
        """Set the mods.

        Args:
            mods: Legacy bitflags, an acronym string, or a mods object.

        Returns:
            ``self`` for chaining.
        """
        self._mods = (
            mods if isinstance(mods, PerformanceMods) else PerformanceMods.from_mods(mods)
        )
        return self

    def clock_rate(self, cr: float) -> "Difficulty":
        """Override the clock rate directly.

        Args:
            cr: The clock-rate multiplier (e.g. ``1.5`` for DT).

        Returns:
            ``self`` for chaining.
        """
        self._clock_rate = float(cr)
        return self

    def lazer(self, lazer: bool) -> "Difficulty":
        """Choose lazer or stable scoring semantics.

        Args:
            lazer: ``True`` for osu!lazer, ``False`` for osu!(stable).

        Returns:
            ``self`` for chaining.
        """
        self._lazer = bool(lazer)
        return self

    def ar(self, ar: float, fixed: bool = False) -> "Difficulty":
        """Override the approach rate.

        Args:
            ar: The AR value.
            fixed: If ``True`` use as-is; if ``False`` mods and clock rate still adjust it.

        Returns:
            ``self`` for chaining.
        """
        self._ar = (float(ar), bool(fixed))
        return self

    def cs(self, cs: float, fixed: bool = False) -> "Difficulty":
        """Override the circle size (see :meth:`ar` for ``fixed``).

        Args:
            cs: The CS value.
            fixed: Whether to use the value as-is.

        Returns:
            ``self`` for chaining.
        """
        self._cs = (float(cs), bool(fixed))
        return self

    def hp(self, hp: float, fixed: bool = False) -> "Difficulty":
        """Override the HP drain rate (see :meth:`ar` for ``fixed``).

        Args:
            hp: The HP value.
            fixed: Whether to use the value as-is.

        Returns:
            ``self`` for chaining.
        """
        self._hp = (float(hp), bool(fixed))
        return self

    def od(self, od: float, fixed: bool = False) -> "Difficulty":
        """Override the overall difficulty (see :meth:`ar` for ``fixed``).

        Args:
            od: The OD value.
            fixed: Whether to use the value as-is.

        Returns:
            ``self`` for chaining.
        """
        self._od = (float(od), bool(fixed))
        return self

    def passed_objects(self, n: int) -> "Difficulty":
        """Only consider the first ``n`` hit objects (partial map).

        Args:
            n: The number of objects to include.

        Returns:
            ``self`` for chaining.
        """
        self._passed_objects = int(n)
        return self

    def calculate(self, beatmap: "Beatmap | PerformanceBeatmap | Any") -> Any:
        """Run the difficulty calculation.

        Args:
            beatmap: The beatmap to evaluate (a :class:`Beatmap` or compatible object).

        Returns:
            The ruleset's difficulty attributes (including ``stars`` and ``max_combo``).
        """
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
    """Builder for a performance (pp) calculation.

    Configure mods and the score state with the chaining methods, then call
    :meth:`calculate`. Unset counts are generated from the accuracy/miss count.
    """
    __slots__ = (
        "_beatmap", "_mods", "_clock_rate", "_lazer",
        "_accuracy", "_combo", "_misses",
        "_n300", "_n100", "_n50", "_n_geki", "_n_katu",
        "_large_tick_hits", "_small_tick_hits", "_slider_end_hits",
        "_passed_objects", "_legacy_total_score",
        "_ar", "_cs", "_hp", "_od",
    )

    def __init__(self, beatmap: "Beatmap | PerformanceBeatmap | Any") -> None:
        """Create a performance builder for a beatmap.

        Args:
            beatmap: The beatmap to evaluate.
        """
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
        """Set the mods from a bitflag, acronym string or mods object; returns ``self``."""
        self._mods = (
            mods if isinstance(mods, PerformanceMods) else PerformanceMods.from_mods(mods)
        )
        return self

    def clock_rate(self, cr: float) -> "Performance":
        """Override the clock-rate multiplier; returns ``self``."""
        self._clock_rate = float(cr)
        return self

    def lazer(self, lazer: bool) -> "Performance":
        """Select lazer or stable scoring semantics; returns ``self``."""
        self._lazer = bool(lazer)
        return self

    def accuracy(self, acc: float) -> "Performance":
        """Set the target accuracy in percent (generates a matching state); returns ``self``."""
        self._accuracy = float(acc) / 100.0 if acc > 1.0 else float(acc)
        return self

    def combo(self, c: int) -> "Performance":
        """Set the achieved max combo; returns ``self``."""
        self._combo = int(c)
        return self

    def misses(self, m: int) -> "Performance":
        """Set the miss count; returns ``self``."""
        self._misses = int(m)
        return self

    def n300(self, n: int) -> "Performance":
        """Set the number of 300s (great hits); returns ``self``."""
        self._n300 = int(n)
        return self

    def n100(self, n: int) -> "Performance":
        """Set the number of 100s (ok hits); returns ``self``."""
        self._n100 = int(n)
        return self

    def n50(self, n: int) -> "Performance":
        """Set the number of 50s (meh hits); returns ``self``."""
        self._n50 = int(n)
        return self

    def n_geki(self, n: int) -> "Performance":
        """Set the number of gekis (mania perfects / max hits); returns ``self``."""
        self._n_geki = int(n)
        return self

    def n_katu(self, n: int) -> "Performance":
        """Set the number of katus (mania good / catch tiny-droplet misses); returns ``self``."""
        self._n_katu = int(n)
        return self

    def large_tick_hits(self, n: int) -> "Performance":
        """Set the number of large tick hits (lazer sliders); returns ``self``."""
        self._large_tick_hits = int(n)
        return self

    def small_tick_hits(self, n: int) -> "Performance":
        """Set the number of small tick hits (lazer); returns ``self``."""
        self._small_tick_hits = int(n)
        return self

    def slider_end_hits(self, n: int) -> "Performance":
        """Set the number of slider ends hit (lazer sliders); returns ``self``."""
        self._slider_end_hits = int(n)
        return self

    def passed_objects(self, n: int) -> "Performance":
        """Only consider the first ``n`` objects (fails/partial plays); returns ``self``."""
        self._passed_objects = int(n)
        return self

    def legacy_total_score(self, score: int) -> "Performance":
        """Set the stable total score for score-based miss estimation; returns ``self``."""
        self._legacy_total_score = int(score)
        return self

    def ar(self, ar: float, fixed: bool = False) -> "Performance":
        """Override AR (see :meth:`Difficulty.ar` for ``fixed``); returns ``self``."""
        self._ar = (float(ar), bool(fixed))
        return self

    def cs(self, cs: float, fixed: bool = False) -> "Performance":
        """Override CS (see :meth:`Difficulty.ar` for ``fixed``); returns ``self``."""
        self._cs = (float(cs), bool(fixed))
        return self

    def hp(self, hp: float, fixed: bool = False) -> "Performance":
        """Override HP (see :meth:`Difficulty.ar` for ``fixed``); returns ``self``."""
        self._hp = (float(hp), bool(fixed))
        return self

    def od(self, od: float, fixed: bool = False) -> "Performance":
        """Override OD (see :meth:`Difficulty.ar` for ``fixed``); returns ``self``."""
        self._od = (float(od), bool(fixed))
        return self

    def calculate(self, attrs: Any | None = None) -> Any:
        """Run the performance calculation.

        Args:
            attrs: Pre-computed difficulty attributes to reuse, or ``None`` to compute
                them from the configured settings.

        Returns:
            The ruleset's performance attributes (including ``pp``).
        """
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
    """Return the internal performance beatmap for a Beatmap-like argument."""
    if isinstance(beatmap, Beatmap):
        return beatmap.inner
    if isinstance(beatmap, PerformanceBeatmap):
        return beatmap
    return PerformanceBeatmap(beatmap)
