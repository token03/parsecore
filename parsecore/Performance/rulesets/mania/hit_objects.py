"""osu!mania object model (notes and hold notes in columns).

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

@dataclass(slots=True)
class ManiaObject:
    """A mania note or hold note in a column, with start and end times."""
    start_time: float
    end_time: float
    column: int

    def is_long_note(self) -> bool:
        """Return whether this is a hold note (has a positive duration)."""
        return self.end_time > self.start_time

def column_for_x(x: float, total_columns: int) -> int:
    """Return the column index for an x position.

    Args:
        x: The object's x coordinate.
        total_columns: The stage's column count.

    Returns:
        The zero-based column index.
    """
    if total_columns <= 0:
        return 0
    x_divisor = 512.0 / total_columns
    raw = int(x // x_divisor)
    if raw < 0:
        return 0
    if raw >= total_columns:
        return total_columns - 1
    return raw