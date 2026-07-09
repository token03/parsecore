"""osu!taiko object model (don/kat hits and drum rolls).

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


class TaikoHitType(Enum):
    """The type of a taiko object (don/centre, kat/rim, or non-hit)."""
    CENTER = 0
    RIM = 1
    NON_HIT = 2

    def is_hit(self) -> bool:
        """Return whether this type is an actual hit (don or kat)."""
        return self is not TaikoHitType.NON_HIT

HIT_SOUND_NORMAL = 1
HIT_SOUND_WHISTLE = 1 << 1
HIT_SOUND_FINISH = 1 << 2
HIT_SOUND_CLAP = 1 << 3

RIM_SOUND_MASK = HIT_SOUND_CLAP | HIT_SOUND_WHISTLE

@dataclass(slots=True)
class TaikoObject:
    """A taiko object at a time, with its hit type."""
    start_time: float
    hit_type: TaikoHitType

    @classmethod
    def from_hit(cls, start_time: float, is_circle: bool, hit_sound: int) -> TaikoObject:
        """Build a taiko object from a converted hit.

        Args:
            start_time: The object's time.
            is_circle: Whether it is a hittable circle (vs a drum roll/swell).
            hit_sound: The hit-sound flags deciding don vs kat.

        Returns:
            The taiko object.
        """
        if not is_circle:
            hit_type = TaikoHitType.NON_HIT
        elif hit_sound & RIM_SOUND_MASK:
            hit_type = TaikoHitType.RIM
        else:
            hit_type = TaikoHitType.CENTER

        return cls(start_time=float(start_time), hit_type=hit_type)

    def is_hit(self) -> bool:
        """Return whether this object is an actual hit (don or kat)."""
        return self.hit_type.is_hit()
