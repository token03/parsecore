"""Parser and data model for the ``[Difficulty]`` section of a ``.osu`` file.

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
from enum import Enum

from ..utils import KeyValue, ParseNumberError, parse_float, trim_comment


class ParseDifficultyError(Exception):
    """Raised when a line in the ``[Difficulty]`` section cannot be parsed."""
    def __init__(self, message: str):
        """Initialise the error with a message.

        Args:
            message: Human-readable description of the parse failure.
        """
        super().__init__(message)


class DifficultyKey(Enum):
    """Recognised keys of the ``[Difficulty]`` section."""
    HPDrainRate = "HPDrainRate"
    CircleSize = "CircleSize"
    OverallDifficulty = "OverallDifficulty"
    ApproachRate = "ApproachRate"
    SliderMultiplier = "SliderMultiplier"
    SliderTickRate = "SliderTickRate"

    @classmethod
    def from_str(cls, s: str) -> DifficultyKey:
        """Return the ``DifficultyKey`` matching a raw key string.

        Args:
            s: The key text as it appears in the file.

        Returns:
            The matching enum member.

        Raises:
            ValueError: If the key is not a recognised difficulty key.
        """
        try:
            return cls(s)
        except ValueError:
            raise ValueError("invalid difficulty key")


@dataclass(slots=True, eq=True)
class Difficulty:
    """Difficulty settings of a beatmap (HP, CS, OD, AR, slider multiplier/tick rate)."""
    hp_drain_rate: float
    circle_size: float
    overall_difficulty: float
    approach_rate: float
    slider_multiplier: float
    slider_tick_rate: float

    def __init__(self):
        """Initialise every difficulty setting to its osu!-stable default."""
        self.hp_drain_rate = 5.0
        self.circle_size = 5.0
        self.overall_difficulty = 5.0
        self.approach_rate = 5.0
        self.slider_multiplier = 1.4
        self.slider_tick_rate = 1.0


class DifficultyState:
    """Accumulates ``[Difficulty]`` values while decoding.

    The beatmap format version is tracked because older versions default the
    approach rate to the overall difficulty when ``ApproachRate`` is absent.
    """
    __slots__ = ("has_approach_rate", "difficulty")

    def __init__(self, format_version: int = 14):
        """Initialise with defaults for the given format version.

        Args:
            format_version: The ``osu file format v<N>`` version of the map.
        """
        self.has_approach_rate: bool = False
        self.difficulty: Difficulty = Difficulty()

    def parse_difficulty(self, line: str) -> None:
        """Parse a single ``[Difficulty]`` line into this instance.

        Args:
            line: One raw ``key:value`` line from the section.

        Raises:
            ParseDifficultyError: If a value fails to parse as a number.
        """
        clean_line = trim_comment(line)

        kv = KeyValue.parse(clean_line, DifficultyKey.from_str)
        if kv is None:
            return

        try:
            match kv.key:
                case DifficultyKey.HPDrainRate:
                    self.difficulty.hp_drain_rate = parse_float(kv.value)
                case DifficultyKey.CircleSize:
                    self.difficulty.circle_size = parse_float(kv.value)
                case DifficultyKey.OverallDifficulty:
                    self.difficulty.overall_difficulty = parse_float(kv.value)

                    if not self.has_approach_rate:
                        self.difficulty.approach_rate = (
                            self.difficulty.overall_difficulty
                        )

                case DifficultyKey.ApproachRate:
                    self.difficulty.approach_rate = parse_float(kv.value)
                    self.has_approach_rate = True
                case DifficultyKey.SliderMultiplier:
                    val = parse_float(kv.value)
                    self.difficulty.slider_multiplier = max(0.4, min(3.6, val))
                case DifficultyKey.SliderTickRate:
                    val = parse_float(kv.value)
                    self.difficulty.slider_tick_rate = max(0.5, min(8.0, val))

        except ParseNumberError as e:
            raise ParseDifficultyError(f"failed to parse number: {e}")
