"""The :class:`GameModsIntermode` collection: mods not bound to any ruleset.

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
from .game_mod_intermode import GameModIntermode, UnknownGameMod


class GameModsIntermode:
    """An ordered set of ruleset-agnostic mods (identified by acronym only)."""
    def __init__(self, mods: Iterable[GameModIntermode] = ()) -> None:
        """Create the collection from an iterable of intermode mods.

        Args:
            mods: The initial mods; duplicates are ignored.
        """
        self._inner: list[GameModIntermode] = []
        for m in mods:
            self.insert(m)

    def insert(self, gamemod: GameModIntermode) -> None:
        """Add a mod, ignoring duplicates by acronym."""
        if gamemod not in self._inner:
            self._inner.append(gamemod)
            self._inner.sort()

    def remove(self, gamemod: GameModIntermode) -> bool:
        """Remove a mod; return whether it was present."""
        if gamemod in self._inner:
            self._inner.remove(gamemod)
            return True
        return False

    def remove_all(self, mods: Iterable[GameModIntermode]) -> None:
        """Remove every given mod."""
        for m in mods:
            self.remove(m)

    def extend(self, mods: Iterable[GameModIntermode]) -> None:
        """Add every mod from an iterable."""
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

    def contains(self, gamemod: GameModIntermode | str) -> bool:
        """Return whether a specific mod is present."""
        if isinstance(gamemod, str):
            gamemod = GameModIntermode.from_acronym(gamemod)
        return gamemod in self._inner

    def contains_acronym(self, acronym: Acronym | str) -> bool:
        """Return whether a mod with the given acronym is present."""
        s = str(acronym).upper()
        return any(str(m) == s for m in self._inner)

    def bits(self) -> int:
        """Return the combined legacy bitfield of all mods."""
        result = 0
        for m in self._inner:
            b = m.bits()
            if b is not None:
                result |= b
        return result

    def checked_bits(self) -> int | None:
        """Return the legacy bitfield, or ``None`` if any mod lacks one."""
        result = 0
        for m in self._inner:
            b = m.bits()
            if b is None:
                return None
            result |= b
        return result

    def intersection(self, other: GameModsIntermode) -> GameModsIntermode:
        """Return the mods present in both collections."""
        return GameModsIntermode(m for m in self._inner if m in other._inner)

    def union(self, other: GameModsIntermode) -> GameModsIntermode:
        """Return the union with another collection."""
        result = GameModsIntermode(self._inner)
        result.extend(other._inner)
        return result

    def difference(self, other: GameModsIntermode) -> GameModsIntermode:
        """Return the mods in this collection but not the other."""
        return GameModsIntermode(m for m in self._inner if m not in other._inner)

    @classmethod
    def from_bits(cls, bits: int) -> GameModsIntermode:
        """Create the collection from a legacy bitfield.

        Args:
            bits: The legacy mod bitfield.

        Returns:
            The parsed collection (NC implies DT, PF implies SD, etc.).
        """
        NC_BITS = 576
        DT_BITS = 64
        PF_BITS = 16416
        SD_BITS = 32

        if (bits & NC_BITS) == NC_BITS:
            bits &= ~DT_BITS
        else:
            bits &= ~(1 << 9)

        if (bits & PF_BITS) == PF_BITS:
            bits &= ~SD_BITS
        else:
            bits &= ~(1 << 14)

        BITFLAG_MODS = [
            GameModIntermode.NoFail,
            GameModIntermode.Easy,
            GameModIntermode.TouchDevice,
            GameModIntermode.Hidden,
            GameModIntermode.HardRock,
            GameModIntermode.SuddenDeath,
            GameModIntermode.DoubleTime,
            GameModIntermode.Relax,
            GameModIntermode.HalfTime,
            GameModIntermode.Nightcore,
            GameModIntermode.Flashlight,
            GameModIntermode.Autoplay,
            GameModIntermode.SpunOut,
            GameModIntermode.Autopilot,
            GameModIntermode.Perfect,
            GameModIntermode.FourKeys,
            GameModIntermode.FiveKeys,
            GameModIntermode.SixKeys,
            GameModIntermode.SevenKeys,
            GameModIntermode.EightKeys,
            GameModIntermode.FadeIn,
            GameModIntermode.Random,
            GameModIntermode.Cinema,
            GameModIntermode.TargetPractice,
            GameModIntermode.NineKeys,
            GameModIntermode.DualStages,
            GameModIntermode.OneKey,
            GameModIntermode.ThreeKeys,
            GameModIntermode.TwoKeys,
            GameModIntermode.ScoreV2,
            GameModIntermode.Mirror,
        ]

        result = cls()
        for bit_pos, gamemod in enumerate(BITFLAG_MODS):
            if bits & (1 << bit_pos):
                result.insert(gamemod)
        return result

    @classmethod
    def from_acronyms(cls, acronyms: Iterable[str | Acronym]) -> GameModsIntermode:
        """Create the collection from an iterable of acronyms.

        Args:
            acronyms: The acronyms or acronym objects.

        Returns:
            The parsed collection.
        """
        result = cls()
        for a in acronyms:
            result.insert(GameModIntermode.from_acronym(str(a)))
        return result

    @classmethod
    def parse(cls, s: str) -> GameModsIntermode:
        """Parse the collection from a concatenated acronym string.

        Args:
            s: The acronyms (e.g. ``HDNC``).

        Returns:
            The parsed collection.
        """
        from .game_mod_intermode import _FROM_ACRONYM

        result = cls()
        s = s.upper()

        if not s or s == "NM":
            return result

        tokens: list[str] = []
        i = 0
        while i < len(s):
            remaining = len(s) - i

            if remaining == 1:
                if tokens:
                    tokens[-1] = tokens[-1] + s[i]
                i += 1

            elif s[i : i + 3] in _FROM_ACRONYM:
                tokens.append(s[i : i + 3])
                i += 3

            else:
                tokens.append(s[i : i + 2])
                i += 2

        for token in tokens:
            if token in _FROM_ACRONYM:
                result.insert(_FROM_ACRONYM[token])
            else:
                result.insert(UnknownGameMod(token))

        return result

    def __iter__(self) -> Iterator[GameModIntermode]:
        """Iterate the mods in order."""
        return iter(self._inner)

    def __contains__(self, item: object) -> bool:
        """Return whether a mod or acronym is present."""
        return item in self._inner

    def __ior__(self, other: GameModsIntermode) -> GameModsIntermode:
        """In-place union; returns ``self``."""
        self.extend(other)
        return self

    def __or__(self, other: GameModsIntermode) -> GameModsIntermode:
        """Return the union with another collection."""
        return self.union(other)

    def __sub__(self, other: GameModsIntermode) -> GameModsIntermode:
        """Return the difference with another collection."""
        return self.difference(other)

    def __isub__(self, other: GameModsIntermode) -> GameModsIntermode:
        """In-place difference; returns ``self``."""
        self.remove_all(other)
        return self

    def __str__(self) -> str:
        """Return the concatenated acronyms."""
        if not self._inner:
            return "NM"
        return "".join(str(m) for m in self._inner)

    def __repr__(self) -> str:
        """Return an unambiguous representation."""
        return f"GameModsIntermode([{', '.join(repr(m) for m in self._inner)}])"

    def __eq__(self, other: object) -> bool:
        """Return whether two collections hold the same mods."""
        if isinstance(other, GameModsIntermode):
            return self._inner == other._inner
        return NotImplemented

    def __hash__(self) -> int:
        """Return a hash consistent with equality."""
        return hash(tuple(self._inner))
