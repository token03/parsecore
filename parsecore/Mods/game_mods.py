"""The :class:`GameMods` collection: an ordered, ruleset-bound set of mods.

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

from collections.abc import Iterable, Iterator

from .acronym import Acronym
from .game_mod import GameMod
from .game_mod_intermode import GameModIntermode
from .game_mode import GameMode


class GameMods:
    """An ordered, de-duplicated collection of mods for a single ruleset."""
    def __init__(self, mods: Iterable[GameMod] = ()) -> None:
        """Create a mod collection from an iterable of mods.

        Args:
            mods: The initial mods; duplicates by acronym are ignored.
        """
        self._inner: dict[tuple, GameMod] = {}
        for m in mods:
            self.insert(m)

    def _key(self, m: GameMod) -> tuple:
        """Return the sort key (mode, kind rank, acronym) for a mod."""
        mode = m.mode()
        mode_val = mode.value if mode is not None else -1
        kind_val = m.kind().rank() if m.kind() is not None else 999
        return (mode_val, kind_val, str(m.acronym()))

    def _sorted(self) -> list[GameMod]:
        """Return the contained mods in stable display order."""
        return sorted(self._inner.values(), key=self._key)

    def insert(self, gamemod: GameMod) -> None:
        """Add a mod, ignoring it if its acronym is already present.

        Args:
            gamemod: The mod to add.
        """
        key = self._key(gamemod)
        self._inner[key] = gamemod

    def remove(self, gamemod: GameMod) -> bool:
        """Remove a specific mod.

        Args:
            gamemod: The mod to remove.

        Returns:
            ``True`` if it was present and removed.
        """
        key = self._key(gamemod)
        if key in self._inner:
            del self._inner[key]
            return True
        return False

    def remove_acronym(self, acronym: str | Acronym) -> bool:
        """Remove the mod with the given acronym.

        Args:
            acronym: The acronym to remove.

        Returns:
            ``True`` if a mod was removed.
        """
        s = str(acronym).upper()
        keys = [k for k in self._inner if k[2] == s]
        for k in keys:
            del self._inner[k]
        return bool(keys)

    def extend(self, mods: Iterable[GameMod]) -> None:
        """Add every mod from an iterable.

        Args:
            mods: The mods to add.
        """
        for m in mods:
            self.insert(m)

    def clear(self) -> None:
        """Remove all mods."""
        self._inner.clear()

    def is_empty(self) -> bool:
        """Return whether no mods are present."""
        return len(self._inner) == 0

    def len(self) -> int:
        """Return the number of mods."""
        return len(self._inner)

    def __len__(self) -> int:
        """Return the number of mods."""
        return len(self._inner)

    def contains(self, gamemod: GameMod) -> bool:
        """Return whether a specific mod is present.

        Args:
            gamemod: The mod to look for.
        """
        return self._key(gamemod) in self._inner

    def contains_acronym(self, acronym: str | Acronym) -> bool:
        """Return whether a mod with the given acronym is present.

        Args:
            acronym: The acronym to look for.
        """
        s = str(acronym).upper()
        return any(k[2] == s for k in self._inner)

    def get(
        self, acronym: str | Acronym, mode: GameMode | None = None
    ) -> GameMod | None:
        """Return the contained mod with the given acronym, or ``None``.

        Args:
            acronym: The acronym to look up.
            mode: The ruleset (unused for lookup; kept for API symmetry).

        Returns:
            The matching mod, or ``None``.
        """
        s = str(acronym).upper()
        for k, m in self._inner.items():
            if k[2] == s:
                if mode is None or m.mode() == mode:
                    return m
        return None

    def bits(self) -> int:
        """Return the combined legacy bitfield of all contained mods."""
        result = 0
        for m in self._inner.values():
            b = m.bits()
            if b is not None:
                result |= b
        return result

    def checked_bits(self) -> int | None:
        """Return the legacy bitfield, or ``None`` if any mod has no legacy bit."""
        result = 0
        for m in self._inner.values():
            b = m.bits()
            if b is None:
                return None
            result |= b
        return result

    def to_intermode(self):
        """Return the ruleset-agnostic (intermode) form of this collection."""
        from .game_mods_intermode import GameModsIntermode

        result = GameModsIntermode()
        for m in self._inner.values():
            intermode = GameModIntermode.from_acronym(str(m.acronym()))
            result.insert(intermode)
        return result

    def __iter__(self) -> Iterator[GameMod]:
        """Iterate the mods in display order."""
        return iter(self._sorted())

    def __contains__(self, item: object) -> bool:
        """Return whether a mod or acronym is present."""
        if isinstance(item, GameMod):
            return self.contains(item)
        return False

    def __ior__(self, other: GameMods) -> GameMods:
        """In-place union with another collection; returns ``self``."""
        self.extend(other)
        return self

    def __or__(self, other: GameMods) -> GameMods:
        """Return the union with another collection."""
        result = GameMods(self._sorted())
        result.extend(other)
        return result

    def __str__(self) -> str:
        """Return the concatenated acronyms (e.g. ``HDDT``)."""
        if not self._inner:
            return "NM"
        return "".join(str(m.acronym()) for m in self._sorted())

    def __repr__(self) -> str:
        """Return an unambiguous representation."""
        return f"GameMods([{', '.join(repr(m) for m in self._sorted())}])"

    def __eq__(self, other: object) -> bool:
        """Return whether two collections hold the same mods."""
        if isinstance(other, GameMods):
            return self._inner == other._inner
        return NotImplemented

    def __hash__(self) -> int:
        """Return a hash consistent with equality."""
        return hash(tuple(self._key(m) for m in self._sorted()))

    @classmethod
    def from_iter(cls, mods: Iterable[GameMod]) -> GameMods:
        """Create a collection from an iterable of mods.

        Args:
            mods: The mods to include.

        Returns:
            The new collection.
        """
        return cls(mods)


def _gamemods_clock_rate(self) -> float | None:
    """Return the effective clock rate of the mods, or ``None`` if indeterminate."""
    result = 1.0
    for gm in self:
        cr = gm.clock_rate()
        if cr is None:
            return None
        if cr != 1.0:
            result = cr
    return result


def _gamemod_clock_rate(self) -> float | None:
    """Return a single mod's clock-rate multiplier, or ``None``."""
    from .generated_mods import (
        AdaptiveSpeedMania,
        AdaptiveSpeedOsu,
        AdaptiveSpeedTaiko,
        DaycoreCatch,
        DaycoreMania,
        DaycoreOsu,
        DaycoreTaiko,
        DoubleTimeCatch,
        DoubleTimeMania,
        DoubleTimeOsu,
        DoubleTimeTaiko,
        HalfTimeCatch,
        HalfTimeMania,
        HalfTimeOsu,
        HalfTimeTaiko,
        NightcoreCatch,
        NightcoreMania,
        NightcoreOsu,
        NightcoreTaiko,
        WindDownCatch,
        WindDownMania,
        WindDownOsu,
        WindDownTaiko,
        WindUpCatch,
        WindUpMania,
        WindUpOsu,
        WindUpTaiko,
    )

    _DT = (DoubleTimeOsu, DoubleTimeTaiko, DoubleTimeCatch, DoubleTimeMania)
    _NC = (NightcoreOsu, NightcoreTaiko, NightcoreCatch, NightcoreMania)
    _HT = (HalfTimeOsu, HalfTimeTaiko, HalfTimeCatch, HalfTimeMania)
    _DC = (DaycoreOsu, DaycoreTaiko, DaycoreCatch, DaycoreMania)
    _NONE = (
        WindUpOsu,
        WindUpTaiko,
        WindUpCatch,
        WindUpMania,
        WindDownOsu,
        WindDownTaiko,
        WindDownCatch,
        WindDownMania,
        AdaptiveSpeedOsu,
        AdaptiveSpeedTaiko,
        AdaptiveSpeedMania,
    )

    inner = self._inner
    if isinstance(inner, _NONE):
        return None
    if isinstance(inner, _DT + _NC):
        return inner.speed_change if inner.speed_change is not None else 1.5
    if isinstance(inner, _HT + _DC):
        return inner.speed_change if inner.speed_change is not None else 0.75
    return 1.0


def _gamemods_is_valid(self) -> bool:
    """Return whether the mod combination is internally consistent."""
    for gm in self:
        own = str(gm.acronym())
        for incompat in gm.incompatible_mods():
            s = str(incompat)
            if s == own:
                continue
            if self.contains_acronym(s):
                return False
    return True


def _gamemods_sanitize(self) -> None:
    """Remove mutually incompatible mods in place."""
    changed = True
    while changed:
        changed = False
        for gm in list(self):
            own = str(gm.acronym())
            for incompat in gm.incompatible_mods():
                s = str(incompat)
                if s == own:
                    continue
                keys_to_remove = [k for k in self._inner if k[2] == s]
                if keys_to_remove:
                    for k in keys_to_remove:
                        del self._inner[k]
                    changed = True
                    break
            if changed:
                break


def _gamemods_as_legacy(self):
    """Return the mods as a :class:`GameModsLegacy` bitfield."""
    from .game_mods_legacy import GameModsLegacy

    return GameModsLegacy.from_bits(self.bits())


def _gamemods_try_as_legacy(self):
    """Return the legacy bitfield form, or ``None`` if not representable."""
    from .game_mods_legacy import GameModsLegacy

    b = self.checked_bits()
    return GameModsLegacy.from_bits(b) if b is not None else None


def _gamemods_contains_intermode(self, gamemod) -> bool:
    """Return whether an intermode mod is present."""
    s = str(gamemod) if not isinstance(gamemod, str) else gamemod
    return any(k[2] == s.upper() for k in self._inner)


def _gamemods_contains_any(self, mods) -> bool:
    """Return whether any of the given mods is present."""
    return any(self._gamemods_contains_intermode(self, m) for m in mods)


def _gamemods_remove_intermode(self, gamemod) -> bool:
    """Remove a mod given in intermode form; return whether it was present."""
    s = str(gamemod).upper()
    keys = [k for k in self._inner if k[2] == s]
    for k in keys:
        del self._inner[k]
    return bool(keys)


def _gamemods_remove_all(self, mods) -> None:
    """Remove every given mod."""
    for m in mods:
        self.remove(m)


def _gamemods_remove_all_intermode(self, mods) -> None:
    """Remove every given intermode mod."""
    for m in mods:
        self._gamemods_remove_intermode(self, m)


def _gamemods_intersects(self, other: GameMods) -> bool:
    """Return whether the two collections share any mod."""
    self_acrs = {k[2] for k in self._inner}
    other_acrs = {k[2] for k in other._inner}
    return bool(self_acrs & other_acrs)


def _gamemods_intersection(self, other: GameMods) -> GameMods:
    """Return the mods present in both collections."""
    from .game_mods import GameMods

    result = GameMods()
    for k, m in self._inner.items():
        if k in other._inner:
            result.insert(m)
    return result


def _gamemods_try_from_intermode(intermode, mode) -> GameMods | None:
    """Resolve intermode mods to a ruleset, or ``None`` on failure."""
    return intermode.try_with_mode(mode)


def _gamemods_from_intermode(intermode, mode) -> GameMods:
    """Resolve intermode mods to a ruleset-bound collection."""
    return intermode.with_mode(mode)


from .game_mods import GameMods

GameMods.clock_rate = _gamemods_clock_rate
GameMods.is_valid = _gamemods_is_valid
GameMods.sanitize = _gamemods_sanitize
GameMods.as_legacy = _gamemods_as_legacy
GameMods.try_as_legacy = _gamemods_try_as_legacy
GameMods.contains_intermode = lambda self, m: _gamemods_contains_intermode(self, m)
GameMods.contains_any = lambda self, mods: _gamemods_contains_any(self, mods)
GameMods.remove_intermode = lambda self, m: _gamemods_remove_intermode(self, m)
GameMods.remove_all = lambda self, mods: _gamemods_remove_all(self, mods)
GameMods.remove_all_intermode = lambda self, mods: _gamemods_remove_all_intermode(
    self, mods
)
GameMods.intersects = _gamemods_intersects
GameMods.intersection = _gamemods_intersection
GameMods.try_from_intermode = staticmethod(_gamemods_try_from_intermode)
GameMods.from_intermode = staticmethod(_gamemods_from_intermode)
GameMod.clock_rate = _gamemod_clock_rate


def _gamemods_from_acronyms(s: str, mode=None) -> GameMods:
    """Parse a ruleset-bound collection from an acronym string.

    Args:
        s: The acronyms (e.g. ``HDDT``).
        mode: The ruleset to resolve them in.

    Returns:
        The parsed collection.
    """
    from .game_mode import GameMode
    from .game_mods_intermode import GameModsIntermode

    intermode = GameModsIntermode.parse(s)
    return intermode.with_mode(mode if mode is not None else GameMode.Osu)


from .game_mods import GameMods

GameMods.from_acronyms = staticmethod(_gamemods_from_acronyms)
