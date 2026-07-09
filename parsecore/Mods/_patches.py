"""Runtime patches wiring cross-type mod helpers onto the mod classes.

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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .game_mode import GameMode
    from .game_mods import GameMods
    from .game_mods_intermode import GameModsIntermode


def _with_mode_impl(intermode: GameModsIntermode, mode: GameMode) -> GameMods:
    """Resolve intermode mods to a ruleset-bound :class:`GameMods`.

    Args:
        intermode: The ruleset-agnostic mods.
        mode: The target ruleset.

    Returns:
        The resolved collection.
    """
    from .game_mod import GameMod
    from .game_mods import GameMods

    result = GameMods()
    for m in intermode:
        result.insert(GameMod.new(str(m), mode))
    return result


def _try_with_mode_impl(
    intermode: GameModsIntermode, mode: GameMode
) -> GameMods | None:
    """Like :func:`_with_mode_impl` but return ``None`` instead of raising."""
    from .game_mod import GameMod
    from .game_mods import GameMods

    result = GameMods()
    for m in intermode:
        gm = GameMod.new(str(m), mode)
        if gm.is_unknown():
            return None
        result.insert(gm)
    return result


def _patch_gamemods_intermode():
    """Attach ``with_mode``/``to_json`` helpers onto ``GameModsIntermode``."""
    from .game_mods_intermode import GameModsIntermode

    def with_mode(self, mode):
        """Resolve these intermode mods to the given ruleset."""
        return _with_mode_impl(self, mode)

    def try_with_mode(self, mode):
        """Resolve to a ruleset, or ``None`` on failure."""
        return _try_with_mode_impl(self, mode)

    def to_json(self) -> str:
        """Return the intermode mods as a JSON string."""
        import json

        return json.dumps(str(self))

    @classmethod
    def from_json(cls, s: str) -> GameModsIntermode:
        """Parse intermode mods from a JSON string."""
        import json

        raw = json.loads(s)
        if isinstance(raw, str):
            return cls.parse(raw)
        if isinstance(raw, int):
            return cls.from_bits(raw)
        if isinstance(raw, list):
            result = cls()
            for item in raw:
                if isinstance(item, str):
                    result.extend(cls.parse(item))
                elif isinstance(item, int):
                    result |= cls.from_bits(item)
            return result
        raise ValueError(f"Cannot parse GameModsIntermode from {raw!r}")

    GameModsIntermode.with_mode = with_mode
    GameModsIntermode.try_with_mode = try_with_mode
    GameModsIntermode.to_json = to_json
    GameModsIntermode.from_json = from_json


def _patch_gamemods():
    """Attach ``to_json``/``from_json`` helpers onto ``GameMods``."""
    from .game_mod import GameMod
    from .game_mods import GameMods

    def to_json(self) -> str:
        """Return the mods as a JSON string."""
        import json

        return json.dumps([m.to_dict() for m in self])

    @classmethod
    def from_json(
        cls, s: str, mode=None, deny_unknown_fields: bool = False
    ) -> GameMods:
        """Parse ruleset-bound mods from a JSON string."""
        import json

        raw = json.loads(s)
        result = cls()
        if isinstance(raw, str):
            from .game_mods_intermode import GameModsIntermode

            intermode = GameModsIntermode.parse(raw)
            if mode is not None:
                return intermode.with_mode(mode)
            for _m_try in (None,):
                for item in intermode:
                    result.insert(
                        GameMod.new(str(item), mode)
                        if mode
                        else _guess_mode_for_acronym(str(item))
                    )
            return result
        if isinstance(raw, int):
            from .game_mods_intermode import GameModsIntermode

            intermode = GameModsIntermode.from_bits(raw)
            if mode is not None:
                return intermode.with_mode(mode)
            return _allow_multiple_modes(intermode)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, int):
                    from .game_mod_intermode import GameModIntermode

                    m = GameModIntermode.try_from_bits(item)
                    if m is None:
                        continue
                    acronym = str(m)
                    gm = (
                        GameMod.new(acronym, mode)
                        if mode
                        else _guess_mode_for_acronym(acronym)
                    )
                    result.insert(gm)
                elif isinstance(item, str):
                    gm = (
                        GameMod.new(item, mode)
                        if mode
                        else _guess_mode_for_acronym(item)
                    )
                    result.insert(gm)
                elif isinstance(item, dict):
                    gm = GameMod.from_dict(
                        item, mode=mode, deny_unknown_fields=deny_unknown_fields
                    )
                    result.insert(gm)
            return result
        if isinstance(raw, dict):
            result.insert(
                GameMod.from_dict(
                    raw, mode=mode, deny_unknown_fields=deny_unknown_fields
                )
            )
            return result
        raise ValueError(f"Cannot parse GameMods from {raw!r}")

    GameMods.to_json = to_json
    GameMods.from_json = from_json


def _guess_mode_for_acronym(acronym: str):
    """Return a plausible ruleset for an acronym, or ``None`` if ambiguous."""
    from .game_mod import GameMod
    from .game_mode import GameMode

    for mode in (GameMode.Osu, GameMode.Taiko, GameMode.Catch, GameMode.Mania):
        candidate = GameMod.new(acronym, mode)
        if not candidate.is_unknown():
            return candidate
    return GameMod.new(acronym, GameMode.Osu)


def _allow_multiple_modes(intermode):
    """Return whether the acronyms may legitimately span several rulesets."""
    from .game_mods import GameMods

    result = GameMods()
    for m in intermode:
        result.insert(_guess_mode_for_acronym(str(m)))
    return result


_patch_gamemods_intermode()
_patch_gamemods()


def _patch_gamemods_intermode_extra():
    """Attach the remaining set-algebra helpers onto ``GameModsIntermode``."""
    from .game_mod_intermode import GameModIntermode
    from .game_mods_intermode import GameModsIntermode
    from .game_mods_legacy import GameModsLegacy

    def intersects(self, other) -> bool:
        """Return whether the two collections share any mod."""
        return bool(set(self._inner) & set(other._inner))

    def legacy_clock_rate(self) -> float:
        """Return the clock rate from the legacy bit representation."""
        for m in self._inner:
            if m in (GameModIntermode.DoubleTime, GameModIntermode.Nightcore):
                return 1.5
            if m in (GameModIntermode.HalfTime, GameModIntermode.Daycore):
                return 0.75
        return 1.0

    def as_legacy(self) -> GameModsLegacy:
        """Return the mods as a legacy bitfield."""
        return GameModsLegacy.from_bits(self.bits())

    def try_as_legacy(self):
        """Return the legacy bitfield, or ``None`` if not representable."""
        b = self.checked_bits()
        return GameModsLegacy.from_bits(b) if b is not None else None

    def remove_all(self, mods) -> None:
        """Remove every given mod."""
        for m in mods:
            self.remove(m)

    def contains_any(self, mods) -> bool:
        """Return whether any of the given mods is present."""
        return any(m in self._inner for m in mods)

    GameModsIntermode.intersects = intersects
    GameModsIntermode.legacy_clock_rate = legacy_clock_rate
    GameModsIntermode.as_legacy = as_legacy
    GameModsIntermode.try_as_legacy = try_as_legacy
    GameModsIntermode.remove_all = remove_all
    GameModsIntermode.contains_any = contains_any


def _patch_legacy_extra():
    """Attach set-algebra and conversion helpers onto ``GameModsLegacy``."""
    from .game_mods_legacy import GameModsLegacy

    def to_intermode(self):
        """Return the intermode form of the legacy bitfield."""
        from .game_mods_intermode import GameModsIntermode

        return GameModsIntermode.from_bits(self._bits)

    def remove(self, other: GameModsLegacy) -> None:
        """Clear the given bits in place."""
        self._bits &= ~other._bits

    def intersection(self, other: GameModsLegacy) -> GameModsLegacy:
        """Return the bitwise intersection."""
        return GameModsLegacy(self._bits & other._bits)

    def union(self, other: GameModsLegacy) -> GameModsLegacy:
        """Return the bitwise union."""
        return GameModsLegacy(self._bits | other._bits)

    def difference(self, other: GameModsLegacy) -> GameModsLegacy:
        """Return this bitfield with the other's bits cleared."""
        return GameModsLegacy(self._bits & ~other._bits)

    def symmetric_difference(self, other: GameModsLegacy) -> GameModsLegacy:
        """Return the bitwise symmetric difference."""
        return GameModsLegacy(self._bits ^ other._bits)

    def try_from_bits_strict(bits: int):
        """Parse bits, returning ``None`` if any bit is unknown."""
        known = 0x7FFFFFFF
        if bits & ~known:
            return None
        return GameModsLegacy(bits)

    GameModsLegacy.to_intermode = to_intermode
    GameModsLegacy.remove = remove
    GameModsLegacy.intersection = intersection
    GameModsLegacy.union = union
    GameModsLegacy.difference = difference
    GameModsLegacy.symmetric_difference = symmetric_difference
    GameModsLegacy.try_from_bits_strict = staticmethod(try_from_bits_strict)


_patch_gamemods_intermode_extra()
_patch_legacy_extra()


def _patch_intermode_acronym_methods():
    """Attach the acronym constructors onto ``GameModsIntermode``."""
    from .game_mod_intermode import GameModIntermode
    from .game_mods_intermode import GameModsIntermode

    @classmethod
    def from_acronyms_str(cls, s: str) -> GameModsIntermode:
        """Parse intermode mods from a concatenated acronym string."""
        return cls.parse(s)

    @classmethod
    def from_acronyms_iter(cls, acronyms) -> GameModsIntermode:
        """Parse intermode mods from an iterable of acronyms."""
        result = cls()
        for a in acronyms:
            result.insert(GameModIntermode.from_acronym(str(a)))
        return result

    @classmethod
    def try_from_acronyms(cls, s: str):
        """Parse acronyms leniently, returning ``None`` on failure."""
        result = cls()
        s = s.upper()
        i = 0
        from .game_mod_intermode import _FROM_ACRONYM

        while i < len(s):
            matched = False
            for length in (3, 2):
                token = s[i : i + length]
                if token in _FROM_ACRONYM:
                    result.insert(_FROM_ACRONYM[token])
                    i += length
                    matched = True
                    break
            if not matched:
                return None
        return result

    GameModsIntermode.from_acronyms_str = from_acronyms_str
    GameModsIntermode.from_acronyms_iter = from_acronyms_iter
    GameModsIntermode.try_from_acronyms = try_from_acronyms


_patch_intermode_acronym_methods()
