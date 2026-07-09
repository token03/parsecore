"""Low-level parsing helpers and the f32-faithful 2D ``Pos`` vector.

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
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

K = TypeVar("K")

_F32_STRUCT = struct.Struct("<f")
_F32_PACK = _F32_STRUCT.pack
_F32_UNPACK = _F32_STRUCT.unpack

F32_EPSILON = 1.1920928955078125e-07


def f32(value: float) -> float:
    """Round a double to IEEE-754 single precision (32-bit float).

    osu! and osu!lazer perform position and several timing calculations in 32-bit
    floats. Mirroring that here is what keeps parsecore bit-exact with the game, so
    this helper is applied wherever the reference uses ``float`` (Rust ``f32``).

    Args:
        value: The double-precision value.

    Returns:
        ``value`` rounded to the nearest 32-bit float, as a Python ``float``.
    """
    try:
        return _F32_UNPACK(_F32_PACK(value))[0]
    except OverflowError:
        return math.inf if value > 0 else -math.inf


class KeyValue(Generic[K]):
    """A parsed ``key: value`` pair with the key mapped to an enum."""
    __slots__ = ("key", "value")

    def __init__(self, key: K, value: str) -> None:
        """Store the parsed key and its raw value.

        Args:
            key: The key already converted to its enum type.
            value: The raw value text (trimmed).
        """
        self.key: K = key
        self.value: str = value

    @classmethod
    def parse(cls, s: str, key_type: Callable[[str], K]) -> "KeyValue[K] | None":
        """Split a ``key<sep>value`` line and map the key via ``key_type``.

        Args:
            s: The raw line.
            key_type: A callable turning the key text into an enum member; it may
                raise to signal an unknown key.

        Returns:
            The parsed :class:`KeyValue`, or ``None`` if the line has no separator or
            the key is not recognised.
        """
        parts = [part.strip() for part in s.split(":", 1)]

        raw_key = parts[0] if parts else s.strip()
        raw_value = parts[1] if len(parts) > 1 else ""

        try:
            parsed_key = key_type(raw_key)
            return cls(key=parsed_key, value=raw_value)
        except (ValueError, TypeError, KeyError):
            return None


MAX_PARSE_VALUE = 2147483647

T_Num = TypeVar("T_Num", int, float)


class ParseNumberError(Exception):
    """Raised when a numeric field cannot be parsed."""
    InvalidFloat = "invalid float"
    InvalidInteger = "invalid integer"
    NaN = "not a number"
    Overflow = "value is too high"
    Underflow = "value is too low"

    def __init__(self, message: str):
        """Initialise the error with a message.

        Args:
            message: Human-readable description of the parse failure.
        """
        super().__init__(message)


def parse_with_limits(s: str, limit: float, target_type: type[T_Num]) -> T_Num:
    """Parse a number and clamp it to osu!'s allowed coordinate range.

    Args:
        s: The numeric text.
        limit: The absolute bound; values outside ``[-limit, limit]`` are rejected.
        target_type: ``int`` or ``float``.

    Returns:
        The parsed, range-checked number.

    Raises:
        ParseNumberError: If the text is not a number or exceeds the limit.
    """
    try:
        n = target_type(s.strip())
    except ValueError:
        if target_type is int:
            raise ParseNumberError(ParseNumberError.InvalidInteger)
        raise ParseNumberError(ParseNumberError.InvalidFloat)

    if n < -limit:
        raise ParseNumberError(ParseNumberError.Underflow)

    if n > limit:
        raise ParseNumberError(ParseNumberError.Overflow)

    if isinstance(n, float) and math.isnan(n):
        raise ParseNumberError(ParseNumberError.NaN)

    return n


def parse_int(s: str) -> int:
    """Parse an integer the way osu!-stable does (truncating trailing junk).

    Args:
        s: The integer text.

    Returns:
        The parsed integer.

    Raises:
        ParseNumberError: If no integer can be read.
    """
    return parse_with_limits(s, int(MAX_PARSE_VALUE), int)


def parse_float(s: str) -> float:
    """Parse a float using osu!-stable's lenient rules.

    Args:
        s: The float text.

    Returns:
        The parsed value.

    Raises:
        ParseNumberError: If no float can be read.
    """
    return parse_with_limits(s, float(MAX_PARSE_VALUE), float)


@dataclass(slots=True, eq=True)
class Pos:
    """A 2D position/vector whose arithmetic is computed in 32-bit floats.

    Every operation routes through :func:`f32` so that distances, dot products and
    curve math reproduce osu!'s float behaviour exactly.
    """
    x: float = 0.0
    y: float = 0.0

    def __post_init__(self) -> None:
        """Coerce the stored coordinates to 32-bit floats."""
        self.x = f32(self.x)
        self.y = f32(self.y)

    def length_squared(self) -> float:
        """Return the squared length (``x*x + y*y``) in f32.

        Returns:
            The squared magnitude of the vector.
        """
        return self.dot(self)

    def length(self) -> float:
        """Return the vector length in f32.

        Returns:
            The Euclidean magnitude, computed as osu! does.
        """
        return f32(math.sqrt(f32(f32(self.x * self.x) + f32(self.y * self.y))))

    def dot(self, other: "Pos") -> float:
        """Return the f32 dot product with another vector.

        Args:
            other: The other vector.

        Returns:
            ``self.x*other.x + self.y*other.y`` in f32.
        """
        return f32(f32(self.x * other.x) + f32(self.y * other.y))

    def distance(self, other: "Pos") -> float:
        """Return the f32 distance to another position.

        Args:
            other: The other position.

        Returns:
            The length of ``self - other``.
        """
        return (self - other).length()

    def normalize(self) -> "Pos":
        """Return a unit vector in the same direction.

        Returns:
            ``self`` divided by its length (in f32).
        """
        length = self.length()
        scale = f32(1.0 / length) if length != 0.0 else math.inf
        return Pos(self.x * scale, self.y * scale)

    def __add__(self, other: "Pos") -> "Pos":
        """Return the f32 component-wise sum ``self + other``."""
        return Pos(self.x + other.x, self.y + other.y)

    def __iadd__(self, other: "Pos") -> "Pos":
        """In-place f32 addition; returns ``self``."""
        self.x = f32(self.x + other.x)
        self.y = f32(self.y + other.y)
        return self

    def __sub__(self, other: "Pos") -> "Pos":
        """Return the f32 component-wise difference ``self - other``."""
        return Pos(self.x - other.x, self.y - other.y)

    def __isub__(self, other: "Pos") -> "Pos":
        """In-place f32 subtraction; returns ``self``."""
        self.x = f32(self.x - other.x)
        self.y = f32(self.y - other.y)
        return self

    def __mul__(self, other: float) -> "Pos":
        """Return ``self`` scaled by a scalar (f32)."""
        other = f32(other)
        return Pos(self.x * other, self.y * other)

    def __imul__(self, other: float) -> "Pos":
        """In-place f32 scalar multiplication; returns ``self``."""
        other = f32(other)
        self.x = f32(self.x * other)
        self.y = f32(self.y * other)
        return self

    def __truediv__(self, other: float) -> "Pos":
        """Return ``self`` divided by a scalar (f32)."""
        other = f32(other)
        return Pos(self.x / other, self.y / other)

    def __itruediv__(self, other: float) -> "Pos":
        """In-place f32 scalar division; returns ``self``."""
        other = f32(other)
        self.x = f32(self.x / other)
        self.y = f32(self.y / other)
        return self

    def __str__(self) -> str:
        """Return a readable ``(x, y)`` string."""
        return f"({self.x}, {self.y})"

    def __repr__(self) -> str:
        """Return an unambiguous representation of the position."""
        return f"Pos(x={self.x}, y={self.y})"


def trim_comment(s: str) -> str:
    """Strip a trailing ``//`` comment from a line.

    Args:
        s: The raw line.

    Returns:
        The line with any ``//`` comment and surrounding whitespace removed.
    """
    index = s.find("//")
    if index == -1:
        return s.strip()
    return s[:index].rstrip()


def to_standardized_path(s: str) -> str:
    """Normalise a file path to use forward slashes.

    Args:
        s: The raw path from the file.

    Returns:
        The path with backslashes converted to ``/``.
    """
    return s.replace("\\", "/")


def clean_filename(s: str) -> str:
    """Trim and standardise a filename field.

    Args:
        s: The raw filename value.

    Returns:
        The cleaned filename.
    """
    cleaned = s.strip('"')
    cleaned = cleaned.replace("\\\\", "\\")
    return to_standardized_path(cleaned)
