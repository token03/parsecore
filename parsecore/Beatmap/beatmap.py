"""The public :class:`Beatmap` type: decode, inspect and re-encode ``.osu`` files.

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

import io
from dataclasses import dataclass

from .encode import encode_beatmap
from .reader import Decoder
from .section import (
    Colors,
    ControlPoints,
    Difficulty,
    DifficultyState,
    Editor,
    Events,
    GameMode,
    General,
    Metadata,
    Section,
    TimingPointsState,
)
from .section.hit_objects import HitObjectsState

LATEST_FORMAT_VERSION = 14


class ParseBeatmapError(Exception):
    """Raised when a ``.osu`` file cannot be decoded."""
    pass


class UnknownFileFormatError(ParseBeatmapError):
    """Raised when the ``osu file format v<N>`` header is missing or invalid."""
    pass


def try_version_from_line(line: str) -> int | None:
    """Return the format version from a header line, if present.

    Args:
        line: A line that may be the ``osu file format v<N>`` header.

    Returns:
        The version number, or ``None`` if the line is not a version header.
    """
    if not line.startswith("osu file format v"):
        if not line:
            return None
        raise UnknownFileFormatError("unknown file format")

    parts = line.split("v", 1)
    if len(parts) > 1:
        try:
            return int(parts[-1])
        except ValueError:
            raise ParseBeatmapError("failed to parse number in format version")

    return LATEST_FORMAT_VERSION


@dataclass(slots=True, eq=True)
class Beatmap:
    """A fully parsed ``.osu`` beatmap.

    Bundles every section (general, metadata, difficulty, events, timing points,
    hit objects, colours, editor) and exposes convenient accessors plus decoding
    and encoding entry points.
    """
    format_version: int
    general: General
    editor: Editor
    metadata: Metadata
    difficulty: Difficulty
    events: Events
    timing_points: TimingPointsState
    colors: Colors
    hit_objects: HitObjectsState

    @property
    def control_points(self) -> ControlPoints:
        """Return the beatmap's timing/difficulty/sample/effect control points."""
        return self.timing_points.control_points

    @property
    def mode(self) -> GameMode:
        """Return the beatmap's game mode."""
        return self.general.mode

    @property
    def audio_filename(self) -> str:
        """Return the audio file name from ``[General]``."""
        return self.general.audio_filename

    @property
    def audio_lead_in(self) -> int:
        """Return the audio lead-in in milliseconds."""
        return self.general.audio_lead_in

    @property
    def preview_time(self) -> int:
        """Return the audio preview time in milliseconds."""
        return self.general.preview_time

    @property
    def stack_leniency(self) -> float:
        """Return the stack leniency."""
        return self.general.stack_leniency

    @property
    def letterbox_in_breaks(self) -> bool:
        """Return whether letterboxing is shown during breaks."""
        return self.general.letterbox_in_breaks

    @property
    def widescreen_storyboard(self) -> bool:
        """Return whether the storyboard is widescreen."""
        return self.general.widescreen_storyboard

    @property
    def epilepsy_warning(self) -> bool:
        """Return whether an epilepsy warning is shown."""
        return self.general.epilepsy_warning

    @property
    def special_style(self) -> bool:
        """Return whether osu!mania special (N+1) style is enabled."""
        return self.general.special_style

    @property
    def samples_match_playback_rate(self) -> bool:
        """Return whether samples follow the playback rate."""
        return self.general.samples_match_playback_rate

    @property
    def title(self) -> str:
        """Return the romanised song title."""
        return self.metadata.title

    @property
    def title_unicode(self) -> str:
        """Return the song title in its original script."""
        return self.metadata.title_unicode

    @property
    def artist(self) -> str:
        """Return the romanised artist name."""
        return self.metadata.artist

    @property
    def artist_unicode(self) -> str:
        """Return the artist name in its original script."""
        return self.metadata.artist_unicode

    @property
    def creator(self) -> str:
        """Return the mapper's username."""
        return self.metadata.creator

    @property
    def version(self) -> str:
        """Return the difficulty name."""
        return self.metadata.version

    @property
    def source(self) -> str:
        """Return the song source."""
        return self.metadata.source

    @property
    def tags(self) -> str:
        """Return the search tags."""
        return self.metadata.tags

    @property
    def beatmap_id(self) -> int:
        """Return the beatmap (difficulty) id."""
        return self.metadata.beatmap_id

    @property
    def beatmap_set_id(self) -> int:
        """Return the beatmap set id."""
        return self.metadata.beatmap_set_id

    @property
    def hp_drain_rate(self) -> float:
        """Return the HP drain rate (HP)."""
        return self.difficulty.hp_drain_rate

    @property
    def circle_size(self) -> float:
        """Return the circle size (CS)."""
        return self.difficulty.circle_size

    @property
    def overall_difficulty(self) -> float:
        """Return the overall difficulty (OD)."""
        return self.difficulty.overall_difficulty

    @property
    def approach_rate(self) -> float:
        """Return the approach rate (AR)."""
        return self.difficulty.approach_rate

    @property
    def slider_multiplier(self) -> float:
        """Return the base slider velocity multiplier."""
        return self.difficulty.slider_multiplier

    @property
    def slider_tick_rate(self) -> float:
        """Return the slider tick rate."""
        return self.difficulty.slider_tick_rate

    @classmethod
    def from_path(cls, path: str) -> Beatmap:
        """Decode a beatmap from a ``.osu`` file on disk.

        Args:
            path: Path to the ``.osu`` file.

        Returns:
            The parsed beatmap.

        Raises:
            ParseBeatmapError: If the file cannot be decoded.
            UnknownFileFormatError: If the format header is missing.
        """
        with open(path, "rb") as f:
            decoder = Decoder(f)
            return cls._decode(decoder)

    @classmethod
    def from_bytes(cls, data: bytes) -> Beatmap:
        """Decode a beatmap from in-memory ``.osu`` file bytes.

        Args:
            data: The raw file contents.

        Returns:
            The parsed beatmap.

        Raises:
            ParseBeatmapError: If the data cannot be decoded.
            UnknownFileFormatError: If the format header is missing.
        """
        reader = io.BytesIO(data)
        decoder = Decoder(reader)
        return cls._decode(decoder)

    @classmethod
    def _decode(cls, decoder: Decoder) -> Beatmap:
        """Decode a beatmap from an open, BOM-resolved decoder.

        Args:
            decoder: A :class:`~parsecore.Beatmap.reader.Decoder` over the file.

        Returns:
            The parsed beatmap.
        """
        format_version = LATEST_FORMAT_VERSION
        use_current_line = False
        current_line_content = ""

        while True:
            line = decoder.read_line()
            if line is None:
                break
            try:
                version = try_version_from_line(line)
                if version is not None:
                    format_version = int(version)
                    break
            except Exception:
                use_current_line = True
                current_line_content = line
                break

        general = General()
        editor = Editor()
        metadata = Metadata()
        difficulty = DifficultyState()
        events = Events()
        colors = Colors()
        hit_objects = HitObjectsState()
        timing_points = TimingPointsState(
            general.mode, general.sample_bank, 100
        )

        current_section: Section | None = None

        if use_current_line:
            sec = Section.try_from_line(current_line_content)
            if sec is not None:
                current_section = sec

        if current_section is None:
            while True:
                line = decoder.read_line()
                if line is None:
                    break
                sec = Section.try_from_line(line)
                if sec is not None:
                    current_section = sec
                    break

        while True:
            line = decoder.read_line()
            if line is None:
                break

            if not line or line.lstrip().startswith("//"):
                continue

            next_section = Section.try_from_line(line)
            if next_section is not None:
                current_section = next_section
                continue

            if current_section is None:
                continue

            try:
                if current_section == Section.General:
                    general.parse_general(line)
                    timing_points.general_mode = general.mode
                    timing_points.general_default_sample_bank = general.sample_bank
                elif current_section == Section.Editor:
                    editor.parse_editor(line)
                elif current_section == Section.Metadata:
                    metadata.parse_metadata(line)
                elif current_section == Section.Difficulty:
                    difficulty.parse_difficulty(line)
                elif current_section == Section.Events:
                    events.parse_events(line)
                elif current_section == Section.TimingPoints:
                    timing_points.parse_timing_points(line)
                elif current_section == Section.Colors:
                    colors.parse_colors(line)
                elif current_section == Section.HitObjects:
                    hit_objects.parse_hit_object(line)
            except Exception:
                pass

        timing_points.flush_pending()

        for break_period in events.breaks:
            if not break_period.has_effect():
                continue

            for obj in hit_objects.hit_objects:
                if obj.start_time > break_period.end_time and hasattr(obj.kind, "new_combo"):
                    obj.kind.new_combo = True
                    break

        return cls(
            format_version=format_version,
            general=general,
            editor=editor,
            metadata=metadata,
            difficulty=difficulty.difficulty,
            events=events,
            timing_points=timing_points,
            colors=colors,
            hit_objects=hit_objects,
        )

    def to_bytes(self, *, lazer_compatible: bool = False) -> bytes:
        """Encode the beatmap to ``.osu`` file bytes.

        Returns:
            The UTF-8 encoded ``.osu`` file contents.
        """
        return self.encode_to_string(lazer_compatible=lazer_compatible).encode("utf-8")

    def encode_to_path(self, path: str, *, lazer_compatible: bool = False) -> None:
        """Encode the beatmap and write it to a file.

        Args:
            path: Destination path for the ``.osu`` file.
        """
        with open(path, "w", encoding="utf-8") as f:
            encode_beatmap(self, f, lazer_compatible=lazer_compatible)

    def encode_to_string(self, *, lazer_compatible: bool = False) -> str:
        """Encode the beatmap to a ``.osu`` file string.

        Returns:
            The encoded ``.osu`` text.
        """
        writer = io.StringIO()
        encode_beatmap(self, writer, lazer_compatible=lazer_compatible)
        return writer.getvalue()
