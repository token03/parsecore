"""Parser and data model for the ``[Colours]`` section of a ``.osu`` file.

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

from ..utils import KeyValue, ParseNumberError, parse_int, trim_comment


class ParseColorsError(Exception):
    """Raised when a line in the ``[Colours]`` section cannot be parsed."""
    def __init__(self, message: str):
        """Initialise the error with a message.

        Args:
            message: Human-readable description of the parse failure.
        """
        super().__init__(message)


def parse_u8(s: str) -> int:
    """Parse a colour channel value and clamp it to the ``0``-``255`` range.

    Args:
        s: The channel text (a decimal integer).

    Returns:
        The parsed value clamped to a valid unsigned byte.

    Raises:
        ParseColorsError: If the text is not an integer.
    """
    try:
        val = parse_int(s)
        if not (0 <= val <= 255):
            raise ValueError("color value out of bounds (mustbe 0-255)")
        return val
    except ParseNumberError as e:
        raise ValueError(str(e))


@dataclass(slots=True, eq=True)
class Color:
    """An RGB combo/border colour with channels in the ``0``-``255`` range."""
    red: int
    green: int
    blue: int
    alpha: int = 255

    @classmethod
    def from_str(cls, s: str) -> Color:
        """Parse an ``R,G,B`` triplet into a ``Color``.

        Args:
            s: The comma-separated channel string.

        Returns:
            The parsed colour.

        Raises:
            ParseColorsError: If the triplet is malformed.
        """
        parts = [part.strip() for part in s.split(",")]

        if len(parts) == 3:
            r, g, b = parts
            a = "255"
        elif len(parts) == 4:
            r, g, b, a = parts
        else:
            raise ParseColorsError(
                "color specified incorrect format (should be R,G,B or R,G,B,A"
            )

        try:
            return cls(parse_u8(r), parse_u8(g), parse_u8(b), parse_u8(a))
        except ValueError as e:
            raise ParseColorsError(f"invalid color number: {e}")


@dataclass(slots=True, eq=True)
class CustomColor:
    """A named custom colour entry (key plus its RGB value)."""
    name: str
    color: Color


@dataclass(slots=True, eq=True)
class Colors:
    """Parsed contents of the ``[Colours]`` section (combo and custom colours)."""
    custom_combo_colors: list[Color]
    custom_colors: list[CustomColor]

    def __init__(self):
        """Initialise with empty combo- and custom-colour collections."""
        self.custom_combo_colors = []
        self.custom_colors = []

    def parse_colors(self, line: str):
        """Parse a single ``[Colours]`` line into this instance.

        Combo colours are appended in order; other keys are stored as custom colours.

        Args:
            line: One raw ``key : R,G,B`` line from the section.

        Raises:
            ParseColorsError: If the colour value is malformed.
        """
        clean_line = trim_comment(line)

        kv = KeyValue.parse(clean_line, str)
        if kv is None:
            return

        color = Color.from_str(kv.value)

        if kv.key.startswith("Combo"):
            self.custom_combo_colors.append(color)
        else:
            for cc in self.custom_colors:
                if cc.name == kv.key:
                    cc.color = color
                    break
            else:
                self.custom_colors.append(CustomColor(name=kv.key, color=color))


ColorsState = Colors
