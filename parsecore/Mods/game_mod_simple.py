"""Ruleset-agnostic mod representations: a single setting and a simple mod.

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

from dataclasses import dataclass, field

from .acronym import Acronym


class SettingSimple:
    """A single mod setting value that may be a bool, float or string."""
    __slots__ = ("_value",)

    def __init__(self, value: bool | float | str) -> None:
        """Store a raw setting value.

        Args:
            value: The bool, float or string value of the setting.
        """
        self._value = value

    @property
    def value(self) -> bool | float | str:
        """Return the raw underlying value."""
        return self._value

    def is_bool(self) -> bool:
        """Return whether the value is a boolean."""
        return isinstance(self._value, bool)

    def is_float(self) -> bool:
        """Return whether the value is a float."""
        return isinstance(self._value, float) and not isinstance(self._value, bool)

    def is_str(self) -> bool:
        """Return whether the value is a string."""
        return isinstance(self._value, str)

    def as_bool(self) -> bool:
        """Return the value as a bool.

        Raises:
            TypeError: If the value is not a boolean.
        """
        if isinstance(self._value, bool):
            return self._value
        raise TypeError(f"Setting is not a bool: {self._value!r}")

    def as_float(self) -> float:
        """Return the value as a float.

        Raises:
            TypeError: If the value is not a float.
        """
        if isinstance(self._value, (int, float)) and not isinstance(self._value, bool):
            return float(self._value)
        raise TypeError(f"Setting is not a float: {self._value!r}")

    def as_str(self) -> str:
        """Return the value as a string.

        Raises:
            TypeError: If the value is not a string.
        """
        if isinstance(self._value, str):
            return self._value
        raise TypeError(f"Setting is not a str: {self._value!r}")

    def __eq__(self, other: object) -> bool:
        """Return whether two settings hold equal values."""
        if isinstance(other, SettingSimple):
            return self._value == other._value
        return self._value == other

    def __float__(self) -> float:
        """Return the value coerced to ``float``."""
        return self.as_float()

    def __repr__(self) -> str:
        """Return an unambiguous representation."""
        return f"SettingSimple({self._value!r})"

    def __str__(self) -> str:
        """Return the value as text."""
        return str(self._value)


@dataclass
class GameModSimple:
    """A mod identified only by acronym and free-form settings, without a ruleset."""
    acronym: Acronym
    settings: dict[str, SettingSimple] = field(default_factory=dict)

    def __repr__(self) -> str:
        """Return an unambiguous representation including settings."""
        return f"GameModSimple(acronym={self.acronym!r}, settings={self.settings!r})"

    def __str__(self) -> str:
        """Return the mod's acronym."""
        return str(self.acronym)
