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
    try:
        return _F32_UNPACK(_F32_PACK(value))[0]
    except OverflowError:
        return math.inf if value > 0 else -math.inf


class KeyValue(Generic[K]):
    __slots__ = ("key", "value")

    def __init__(self, key: K, value: str) -> None:
        self.key: K = key
        self.value: str = value

    @classmethod
    def parse(cls, s: str, key_type: Callable[[str], K]) -> "KeyValue[K] | None":
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
    InvalidFloat = "invalid float"
    InvalidInteger = "invalid integer"
    NaN = "not a number"
    Overflow = "value is too high"
    Underflow = "value is too low"

    def __init__(self, message: str):
        super().__init__(message)


def parse_with_limits(s: str, limit: int | float, target_type: type[T_Num]) -> T_Num:
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
    return parse_with_limits(s, int(MAX_PARSE_VALUE), int)


def parse_float(s: str) -> float:
    return parse_with_limits(s, float(MAX_PARSE_VALUE), float)


@dataclass(slots=True, eq=True)
class Pos:
    x: float = 0.0
    y: float = 0.0

    def __post_init__(self) -> None:
        self.x = f32(self.x)
        self.y = f32(self.y)

    def length_squared(self) -> float:
        return self.dot(self)

    def length(self) -> float:
        return f32(math.sqrt(f32(f32(self.x * self.x) + f32(self.y * self.y))))

    def dot(self, other: "Pos") -> float:
        return f32(f32(self.x * other.x) + f32(self.y * other.y))

    def distance(self, other: "Pos") -> float:
        return (self - other).length()

    def normalize(self) -> "Pos":
        length = self.length()
        scale = f32(1.0 / length) if length != 0.0 else math.inf
        return Pos(self.x * scale, self.y * scale)

    def __add__(self, other: "Pos") -> "Pos":
        return Pos(self.x + other.x, self.y + other.y)

    def __iadd__(self, other: "Pos") -> "Pos":
        self.x = f32(self.x + other.x)
        self.y = f32(self.y + other.y)
        return self

    def __sub__(self, other: "Pos") -> "Pos":
        return Pos(self.x - other.x, self.y - other.y)

    def __isub__(self, other: "Pos") -> "Pos":
        self.x = f32(self.x - other.x)
        self.y = f32(self.y - other.y)
        return self

    def __mul__(self, other: float) -> "Pos":
        other = f32(other)
        return Pos(self.x * other, self.y * other)

    def __imul__(self, other: float) -> "Pos":
        other = f32(other)
        self.x = f32(self.x * other)
        self.y = f32(self.y * other)
        return self

    def __truediv__(self, other: float) -> "Pos":
        other = f32(other)
        return Pos(self.x / other, self.y / other)

    def __itruediv__(self, other: float) -> "Pos":
        other = f32(other)
        self.x = f32(self.x / other)
        self.y = f32(self.y / other)
        return self

    def __str__(self) -> str:
        return f"({self.x}, {self.y})"

    def __repr__(self) -> str:
        return f"Pos(x={self.x}, y={self.y})"


def trim_comment(s: str) -> str:
    index = s.find("//")
    if index == -1:
        return s.strip()
    return s[:index].rstrip()


def to_standardized_path(s: str) -> str:
    return s.replace("\\", "/")


def clean_filename(s: str) -> str:
    cleaned = s.strip('"')
    cleaned = cleaned.replace("\\\\", "\\")
    return to_standardized_path(cleaned)
