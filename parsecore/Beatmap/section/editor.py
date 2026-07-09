"""Parser and data model for the ``[Editor]`` section of a ``.osu`` file.

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

from ..utils import KeyValue, ParseNumberError, parse_float, parse_int, trim_comment


class ParseEditorError(Exception):
    """Raised when a line in the ``[Editor]`` section cannot be parsed."""
    def __init__(self, message: str):
        """Initialise the error with a message.

        Args:
            message: Human-readable description of the parse failure.
        """
        super().__init__(message)


class EditorKey(Enum):
    """Recognised keys of the ``[Editor]`` section."""
    Bookmarks = "Bookmarks"
    DistanceSpacing = "DistanceSpacing"
    BeatDivisor = "BeatDivisor"
    GridSize = "GridSize"
    TimelineZoom = "TimelineZoom"

    @classmethod
    def from_str(cls, s: str) -> EditorKey:
        """Return the ``EditorKey`` matching a raw key string.

        Args:
            s: The key text as it appears in the file.

        Returns:
            The matching enum member.

        Raises:
            ValueError: If the key is not a recognised editor key.
        """
        try:
            return cls(s)
        except ValueError:
            raise ValueError("invalid editor key")


@dataclass(slots=True, eq=True)
class Editor:
    """Parsed contents of the ``[Editor]`` section (bookmarks, grid, timeline, ...)."""
    bookmarks: list[int]
    distance_spacing: float
    beat_divisor: int
    grid_size: int
    timeline_zoom: float

    def __init__(self):
        """Initialise every editor field to its osu!-stable default."""
        self.bookmarks = []
        self.distance_spacing = 1.0
        self.beat_divisor = 4
        self.grid_size = 0
        self.timeline_zoom = 1.0

    def parse_editor(self, line: str) -> None:
        """Parse a single ``[Editor]`` line into this instance.

        Unknown keys are ignored; recognised keys update the matching field in place.

        Args:
            line: One raw ``key: value`` line from the section.

        Raises:
            ParseEditorError: If a value fails to parse as its expected type.
        """
        clean_line = trim_comment(line)

        kv = KeyValue.parse(clean_line, EditorKey.from_str)
        if kv is None:
            return

        try:
            match kv.key:
                case EditorKey.Bookmarks:
                    self.bookmarks = []
                    if kv.value:
                        for part in kv.value.split(","):
                            part = part.strip()
                            if part:
                                try:
                                    self.bookmarks.append(int(part))
                                except ValueError:
                                    pass
                case EditorKey.DistanceSpacing:
                    self.distance_spacing = parse_float(kv.value)
                case EditorKey.BeatDivisor:
                    self.beat_divisor = parse_int(kv.value)
                case EditorKey.GridSize:
                    self.grid_size = parse_int(kv.value)
                case EditorKey.TimelineZoom:
                    self.timeline_zoom = parse_float(kv.value)

        except ParseNumberError as e:
            raise ParseEditorError(f"failed to parse number: {e}")


EditorState = Editor
