"""Lightweight hit-object types used by the performance calculators.

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

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Pos:
    """A 2D position used by the calculators."""
    x: float
    y: float

@dataclass(slots=True)
class Slider:
    """A slider: expected distance, repeats, control points and per-node sounds."""
    expected_dist: float | None
    repeats: int
    control_points: list[Any] = field(default_factory=list)
    node_sounds: list[Any] = field(default_factory=list)

    @property
    def span_count(self) -> int:
        """Return the number of spans (traversals).

        Returns:
            ``repeats + 1``.
        """
        return self.repeats + 1

@dataclass(slots=True)
class Spinner:
    """A spinner given by its duration."""
    duration: float

@dataclass(slots=True)
class HoldNote:
    """An osu!mania hold note given by its duration."""
    duration: float

@dataclass(slots=True)
class HitObject:
    """A calculation hit object: a start time plus its kind (circle/slider/spinner/hold)."""
    pos: Pos
    start_time: float
    kind: Slider | Spinner | HoldNote | None = None
    hit_sound: int = 0

    def is_circle(self) -> bool:
        """Return whether this object is a hit circle."""
        return self.kind is None

    def is_slider(self) -> bool:
        """Return whether this object is a slider."""
        return isinstance(self.kind, Slider)

    def is_spinner(self) -> bool:
        """Return whether this object is a spinner."""
        return isinstance(self.kind, Spinner)

    def is_hold_note(self) -> bool:
        """Return whether this object is a mania hold note."""
        return isinstance(self.kind, HoldNote)

    @property
    def end_time(self) -> float:
        """Return the object's end time.

        Returns:
            The end time for sliders/spinners/holds, or the start time for circles.
        """
        if isinstance(self.kind, (Spinner, HoldNote)):
            return self.start_time + self.kind.duration
        return self.start_time