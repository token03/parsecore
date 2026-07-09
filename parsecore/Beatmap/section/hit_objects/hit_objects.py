"""Parser and data model for the ``[HitObjects]`` section (circles, sliders, ...).

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
from enum import Enum

from ..enums import GameMode, HitSoundType, SampleBank, SplineType
from .slider import PathControlPoint, PathType, SliderPath
from ...utils import ParseNumberError, Pos, parse_float, parse_int, trim_comment


class ParseHitObjectsError(Exception):
    """Raised when a line in the ``[HitObjects]`` section cannot be parsed."""
    def __init__(self, message: str) -> None:
        """Initialise the error with a message.

        Args:
            message: Human-readable description of the parse failure.
        """
        super().__init__(message)


MAX_COORDINATE_VALUE = 131072


class HitObjectType:
    """Bit flags of a hit object's type column (circle, slider, spinner, hold, new combo)."""
    CIRCLE = 1 << 0
    SLIDER = 1 << 1
    NEW_COMBO = 1 << 2
    SPINNER = 1 << 3
    COMBO_OFFSET = (1 << 4) | (1 << 5) | (1 << 6)
    HOLD = 1 << 7

    @staticmethod
    def has_flag(value: int, flag: int) -> bool:
        """Return whether a type flag is set.

        Args:
            value: The raw type bitfield.
            flag: The single flag to test for.

        Returns:
            ``True`` if the flag bit is present.
        """
        return (value & flag) != 0


class HitSampleDefaultName(Enum):
    """Default hit-sound sample names (normal, whistle, finish, clap)."""
    Normal = "hitnormal"
    Whistle = "hitwhistle"
    Finish = "hitfinish"
    Clap = "hitclap"


@dataclass(slots=True, eq=True)
class HitSampleInfo:
    """A resolved hit sample: bank, name/file, volume and layering."""
    name_default: HitSampleDefaultName | None
    name_file: str | None
    bank: SampleBank
    suffix: int | None
    volume: int
    custom_sample_bank: int
    bank_specified: bool
    is_layered: bool


@dataclass(slots=True, eq=True)
class SampleBankInfo:
    """Working sample-bank state while parsing one hit object's hit sounds."""
    filename: str | None = None
    bank_for_normal: SampleBank | None = None
    bank_for_addition: SampleBank | None = None
    volume: int = 0
    custom_sample_bank: int = 0

    def read_custom_sample_bank(self, parts: list[str], banks_only: bool) -> None:
        """Parse the trailing ``sampleSet:...`` fields of a hit object.

        Args:
            parts: The colon-split extras (bank, addition bank, index, volume, file).
            banks_only: If ``True``, only read the two bank fields.
        """
        if not parts or not parts[0]:
            return

        try:
            bank_val = parse_int(parts[0])
        except ParseNumberError:
            bank_val = 0
        bank = SampleBank(bank_val) if bank_val in (1, 2, 3) else SampleBank.Normal

        try:
            add_bank_val = parse_int(parts[1]) if len(parts) > 1 else 0
        except ParseNumberError:
            add_bank_val = 0
        add_bank = (
            SampleBank(add_bank_val) if add_bank_val in (1, 2, 3) else SampleBank.Normal
        )

        self.bank_for_normal = bank if bank != SampleBank.None_ else None
        self.bank_for_addition = (
            add_bank if add_bank != SampleBank.None_ else self.bank_for_normal
        )

        if banks_only:
            return

        if len(parts) > 2 and parts[2]:
            self.custom_sample_bank = parse_int(parts[2])
        if len(parts) > 3 and parts[3]:
            self.volume = max(0, parse_int(parts[3]))
        if len(parts) > 4 and parts[4]:
            self.filename = parts[4]

    def convert_sound_type(self, sound_type: HitSoundType) -> list[HitSampleInfo]:
        """Expand a hit-sound bitfield into concrete sample infos.

        Args:
            sound_type: The hit-sound flags for the object.

        Returns:
            One :class:`HitSampleInfo` per active sound (normal plus any additions).
        """
        samples = []
        if self.filename:
            samples.append(
                HitSampleInfo(
                    None,
                    self.filename,
                    SampleBank.Normal,
                    1,
                    self.volume,
                    self.custom_sample_bank,
                    False,
                    False,
                )
            )
        else:
            is_layered = (
                sound_type != HitSoundType.NONE
            ) and not HitSoundType.has_flag(sound_type, HitSoundType.NORMAL)
            samples.append(
                HitSampleInfo(
                    HitSampleDefaultName.Normal,
                    None,
                    self.bank_for_normal or SampleBank.Normal,
                    self.custom_sample_bank if self.custom_sample_bank >= 2 else None,
                    self.volume,
                    self.custom_sample_bank,
                    self.bank_for_normal is not None,
                    is_layered,
                )
            )

        if HitSoundType.has_flag(sound_type, HitSoundType.FINISH):
            samples.append(
                HitSampleInfo(
                    HitSampleDefaultName.Finish,
                    None,
                    self.bank_for_addition or SampleBank.Normal,
                    self.custom_sample_bank if self.custom_sample_bank >= 2 else None,
                    self.volume,
                    self.custom_sample_bank,
                    self.bank_for_addition is not None,
                    False,
                )
            )
        if HitSoundType.has_flag(sound_type, HitSoundType.WHISTLE):
            samples.append(
                HitSampleInfo(
                    HitSampleDefaultName.Whistle,
                    None,
                    self.bank_for_addition or SampleBank.Normal,
                    self.custom_sample_bank if self.custom_sample_bank >= 2 else None,
                    self.volume,
                    self.custom_sample_bank,
                    self.bank_for_addition is not None,
                    False,
                )
            )
        if HitSoundType.has_flag(sound_type, HitSoundType.CLAP):
            samples.append(
                HitSampleInfo(
                    HitSampleDefaultName.Clap,
                    None,
                    self.bank_for_addition or SampleBank.Normal,
                    self.custom_sample_bank if self.custom_sample_bank >= 2 else None,
                    self.volume,
                    self.custom_sample_bank,
                    self.bank_for_addition is not None,
                    False,
                )
            )

        return samples


@dataclass(slots=True, eq=True)
class HitObjectCircle:
    """A hit circle at a position."""
    pos: Pos
    new_combo: bool
    combo_offset: int


@dataclass(slots=True, eq=True)
class HitObjectSpinner:
    """A spinner with a start and end time."""
    pos: Pos
    duration: float
    new_combo: bool


@dataclass(slots=True, eq=True)
class HitObjectHold:
    """An osu!mania hold note (column plus duration)."""
    pos_x: float
    duration: float


@dataclass(slots=True, eq=True)
class HitObjectSlider:
    """A slider: path, repeats, per-node samples and edge sounds."""
    pos: Pos
    new_combo: bool
    combo_offset: int
    path: SliderPath
    node_samples: list[list[HitSampleInfo]]
    repeat_count: int
    velocity: float
    edge_sounds: list[int] = field(default_factory=list)


@dataclass(slots=True, eq=True)
class HitObject:
    """A single parsed hit object (its kind plus shared start time and samples)."""
    start_time: float
    kind: HitObjectCircle | HitObjectSpinner | HitObjectHold | HitObjectSlider
    samples: list[HitSampleInfo]


def is_linear(p0: Pos, p1: Pos, p2: Pos) -> bool:
    """Return whether three points are collinear.

    Args:
        p0: First point.
        p1: Second point.
        p2: Third point.

    Returns:
        ``True`` if the points lie on a straight line (within tolerance).
    """
    return abs((p1.y - p0.y) * (p2.x - p0.x) - (p1.x - p0.x) * (p2.y - p0.y)) < 1e-7


def convert_points(
    curve_points: list[PathControlPoint],
    points: list[str],
    end_points: str | None,
    first: bool,
    offset: Pos,
) -> None:
    """Parse one segment of a slider path string into control points.

    Args:
        curve_points: The output list to append to.
        points: The pipe-split anchor tokens for this segment.
        end_points: An optional extra endpoint token.
        first: Whether this is the first segment of the path.
        offset: The slider's start position (anchors are stored relative to it).
    """
    path_type = PathType.new_from_str(points[0])

    def read_point(val: str) -> Pos:
        """Parse a single ``x:y`` anchor token into a position.

        Args:
            val: The ``x:y`` token.

        Returns:
            The anchor position relative to the slider start.
        """
        v = val.split(":")
        if len(v) < 2:
            raise ParseHitObjectsError("invalid point format")
        x = float(parse_int(v[0]))
        y = float(parse_int(v[1]))
        return Pos(x, y) - offset

    vertices: list[PathControlPoint] = []
    if first:
        vertices.append(PathControlPoint(Pos(0.0, 0.0), None))

    for point in points[1:]:
        vertices.append(PathControlPoint(read_point(point), None))

    if end_points:
        vertices.append(PathControlPoint(read_point(end_points), None))

    end_point_len = 1 if end_points else 0

    if path_type.kind == SplineType.PerfectCurve:
        if len(vertices) == 3:
            if is_linear(vertices[0].pos, vertices[1].pos, vertices[2].pos):
                path_type = PathType(SplineType.Linear)
        else:
            path_type = PathType(SplineType.BSpline)

    vertices[0].path_type = path_type

    start_idx = 0
    end_idx = 0

    while True:
        end_idx += 1
        if end_idx >= len(vertices) - end_point_len:
            break

        if vertices[end_idx].pos != vertices[end_idx - 1].pos:
            continue

        if path_type.kind == SplineType.Catmull and end_idx > 1:
            continue

        if end_idx == len(vertices) - end_point_len - 1:
            continue

        vertices[end_idx - 1].path_type = path_type
        curve_points.extend(vertices[start_idx:end_idx])
        start_idx = end_idx + 1

    if end_idx > start_idx:
        curve_points.extend(vertices[start_idx:end_idx])


def convert_path_str(point_str: str, offset: Pos) -> list[PathControlPoint]:
    """Parse a full slider path string into control points.

    Args:
        point_str: The raw path string (e.g. ``B|320:96|...``).
        offset: The slider's start position.

    Returns:
        The parsed control points.
    """
    point_split = point_str.split("|")
    curve_points: list[PathControlPoint] = []

    start_idx = 0
    end_idx = 0
    first = True

    while end_idx < len(point_split):
        end_idx += 1
        if end_idx < len(point_split):
            if point_split[end_idx] and point_split[end_idx][0].isalpha():
                end_points = (
                    point_split[end_idx + 1] if end_idx + 1 < len(point_split) else None
                )
                convert_points(
                    curve_points,
                    point_split[start_idx:end_idx],
                    end_points,
                    first,
                    offset,
                )
                start_idx = end_idx
                first = False

    if end_idx > start_idx:
        convert_points(
            curve_points, point_split[start_idx:end_idx], None, first, offset
        )

    return curve_points


class HitObjectsState:
    """Accumulates hit objects while decoding the ``[HitObjects]`` section."""
    def __init__(self) -> None:
        """Initialise with an empty object list and no previous object."""
        self.last_object_type: int | None = None
        self.hit_objects: list[HitObject] = []

    def last_object_was_spinner(self) -> bool:
        """Return whether the previously parsed object was a spinner.

        Returns:
            ``True`` if the last object was a spinner (affects new-combo handling).
        """
        return self.last_object_type is not None and HitObjectType.has_flag(
            self.last_object_type, HitObjectType.SPINNER
        )

    def parse_hit_object(self, line: str) -> None:
        """Parse a single ``[HitObjects]`` line and append the object.

        Args:
            line: One raw comma-separated hit-object line.

        Raises:
            ParseHitObjectsError: If the line is too short or malformed.
        """
        clean_line = trim_comment(line)
        split = clean_line.split(",")
        if len(split) < 5:
            raise ParseHitObjectsError("invalid line")

        try:
            x = float(parse_int(split[0]))
            y = float(parse_int(split[1]))
            pos = Pos(x, y)
            start_time = parse_float(split[2])

            type_flag = parse_int(split[3])
            combo_offset = (type_flag & HitObjectType.COMBO_OFFSET) >> 4
            new_combo = HitObjectType.has_flag(type_flag, HitObjectType.NEW_COMBO)

            sound_type = HitSoundType(parse_int(split[4]))
            bank_info = SampleBankInfo()

            is_first_obj = self.last_object_type is None
            force_new_combo = (
                is_first_obj or self.last_object_was_spinner() or new_combo
            )

            kind: HitObjectCircle | HitObjectSpinner | HitObjectHold | HitObjectSlider

            if HitObjectType.has_flag(type_flag, HitObjectType.CIRCLE):
                if len(split) > 5:
                    bank_info.read_custom_sample_bank(split[5].split(":"), False)

                circle = HitObjectCircle(
                    pos, force_new_combo, combo_offset if new_combo else 0
                )
                kind = circle

            elif HitObjectType.has_flag(type_flag, HitObjectType.SPINNER):
                end_time = parse_float(split[5]) if len(split) > 5 else start_time
                duration = max(0.0, end_time - start_time)

                if len(split) > 6:
                    bank_info.read_custom_sample_bank(split[6].split(":"), False)

                spinner = HitObjectSpinner(Pos(256.0, 192.0), duration, new_combo)
                kind = spinner

            elif HitObjectType.has_flag(type_flag, HitObjectType.HOLD):
                end_time_raw = start_time
                if len(split) > 5 and split[5]:
                    ss = split[5].split(":")
                    end_time_raw = parse_float(ss[0])
                    bank_info.read_custom_sample_bank(ss[1:], False)

                hold = HitObjectHold(pos.x, max(start_time, end_time_raw) - start_time)
                kind = hold

            elif HitObjectType.has_flag(type_flag, HitObjectType.SLIDER):
                if len(split) < 7:
                    raise ParseHitObjectsError("Invalid Line for Slider")

                point_str = split[5]
                repeat_count = max(0, parse_int(split[6]) - 1)
                expected_dist = parse_float(split[7]) if len(split) > 7 else None

                edge_sounds: list[int] = []
                if len(split) > 8 and split[8]:
                    for tok in split[8].split("|"):
                        try:
                            v = int(tok)
                        except ValueError:
                            v = 0
                        edge_sounds.append(v if 0 <= v <= 255 else 0)

                control_points = convert_path_str(point_str, pos)

                slider = HitObjectSlider(
                    pos,
                    force_new_combo,
                    combo_offset if new_combo else 0,
                    SliderPath(GameMode.Osu, control_points, expected_dist),
                    [],
                    repeat_count,
                    1.0,
                    edge_sounds,
                )
                kind = slider

            else:
                raise ParseHitObjectsError(f"Unknown Hit Object Type: {type_flag}")

            obj = HitObject(start_time, kind, bank_info.convert_sound_type(sound_type))
            self.hit_objects.append(obj)
            self.last_object_type = type_flag

        except Exception as e:
            raise ParseHitObjectsError(f"Failed to parse HitObject: {e}")
