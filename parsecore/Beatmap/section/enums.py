"""Shared enums for ``.osu`` sections: game mode, sample banks, hit sounds, ...

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

from enum import Enum, IntEnum, IntFlag


class ParseGameModeError(Exception):
    """Raised when a game-mode value cannot be parsed."""
    def __init__(self, message: str = "invalid game mode"):
        """Initialise the error with a message.

        Args:
            message: Human-readable description of the parse failure.
        """
        super().__init__(message)


class GameMode(IntEnum):
    """The four osu! rulesets (osu!, taiko, catch, mania)."""
    Osu = 0
    Taiko = 1
    Catch = 2
    Mania = 3

    @classmethod
    def from_str(cls, mode: str) -> "GameMode":
        """Return the ``GameMode`` for a raw mode value.

        Args:
            mode: The mode as written in the file (usually ``0``-``3``).

        Returns:
            The matching ruleset.

        Raises:
            ParseGameModeError: If the value is not a valid mode.
        """
        match mode:
            case "0":
                return cls.Osu
            case "1":
                return cls.Taiko
            case "2":
                return cls.Catch
            case "3":
                return cls.Mania
            case _:
                raise ParseGameModeError()

    @classmethod
    def from_int(cls, mode: int) -> "GameMode":
        """Return the ``GameMode`` for an integer id.

        Args:
            mode: The ruleset id, ``0`` (osu!) to ``3`` (mania).

        Returns:
            The matching ruleset.

        Raises:
            ParseGameModeError: If the id is out of range.
        """
        match mode:
            case 0:
                return cls.Osu
            case 1:
                return cls.Taiko
            case 2:
                return cls.Catch
            case 3:
                return cls.Mania
            case _:
                return cls.Osu


class ParseCountdownTypeError(Exception):
    """Raised when a countdown value cannot be parsed."""
    def __init__(self, message: str = "invalid countdown type"):
        """Initialise the error with a message.

        Args:
            message: Human-readable description of the parse failure.
        """
        super().__init__(message)


class CountdownType(IntEnum):
    """The countdown speed shown before the first object (none, normal, half, double)."""
    NONE = 0
    NORMAL = 1
    HALFSPEED = 2
    DOUBLESPEED = 3

    @classmethod
    def from_str(cls, s: str) -> "CountdownType":
        """Return the ``CountdownType`` for a raw value.

        Args:
            s: The countdown value as written in the file.

        Returns:
            The matching enum member.

        Raises:
            ParseCountdownTypeError: If the value is not valid.
        """
        match s:
            case "0" | "None":
                return cls.NONE
            case "1" | "Normal":
                return cls.NORMAL
            case "2" | "Half speed":
                return cls.HALFSPEED
            case "3" | "Double speed":
                return cls.DOUBLESPEED
            case _:
                raise ParseCountdownTypeError()


class SampleBank(IntEnum):
    """A hit-sound sample bank (none, normal, soft, drum)."""
    None_ = 0
    Normal = 1
    Soft = 2
    Drum = 3

    def to_lowercase_str(self) -> str:
        """Return the bank's lowercase name as used in ``.osu`` files.

        Returns:
            ``"normal"``, ``"soft"`` or ``"drum"`` (``"none"`` for the unset bank).
        """
        return self.name.lower().replace("none_", "none")

    def __str__(self) -> str:
        """Return the bank's lowercase file-format name.

        Returns:
            The same value as :meth:`to_lowercase_str`.
        """
        return self.to_lowercase_str()


class HitSoundType(IntFlag):
    """Bit flags for a hit sound (normal, whistle, finish, clap)."""
    NONE = 0
    NORMAL = 1
    WHISTLE = 2
    FINISH = 4
    CLAP = 8

    def has_flag(self, flag: "HitSoundType") -> bool:
        """Return whether a given hit-sound flag is set.

        Args:
            flag: The single flag to test for.

        Returns:
            ``True`` if the flag bit is present.
        """
        return (self.value & flag.value) != 0


class SplineType(Enum):
    """The interpolation type of a slider path segment (linear, bezier, catmull, circle)."""
    Catmull = 0
    BSpline = 1
    Linear = 2
    PerfectCurve = 3


class Section(Enum):
    """A top-level ``.osu`` file section header (``[General]``, ``[HitObjects]``, ...)."""
    General = "General"
    Editor = "Editor"
    Metadata = "Metadata"
    Difficulty = "Difficulty"
    Events = "Events"
    TimingPoints = "TimingPoints"
    Colors = "Colours"
    HitObjects = "HitObjects"
    Variables = "Variables"
    CatchTheBeat = "CatchTheBeat"
    Mania = "Mania"

    @classmethod
    def try_from_line(cls, line: str) -> "Section | None":
        """Return the ``Section`` for a header line, or ``None``.

        Args:
            line: A raw line that may be a ``[Section]`` header.

        Returns:
            The matching section, or ``None`` if the line is not a known header.
        """
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1]
            try:
                return cls(name)
            except ValueError:
                return None
        return None
