"""osu!catch object model: fruits, droplets, juice streams and difficulty objects.

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

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from parsecore.Beatmap.section.enums import GameMode as BeatmapGameMode
from parsecore.Beatmap.section.hit_objects import (
    Curve,
    SliderEventType,
    generate_slider_events,
)
from parsecore.Beatmap.utils import f32

from ...data.beatmap import (
    PerformanceBeatmap,
    difficulty_point_at,
    timing_point_at,
)
from ...data.hit_objects import Slider
from ...utils import (
    _interpolate_curve_position,
    clamp,
    get_precision_adjusted_beat_length,
)

PLAYFIELD_WIDTH = 512.0

_BASE_SCORING_DIST = 100.0
_DEFAULT_BEAT_LEN = 60_000.0 / 60.0
_DEFAULT_SLIDER_VELOCITY = 1.0

class ObjectCountBuilder:

    """Tallies fruits, droplets and tiny droplets while converting a map."""
    __slots__ = ("fruits", "droplets", "tiny_droplets", "take")

    def __init__(self, take: int) -> None:
        """Initialise the counter.

        Args:
            take: The number of objects to count (for partial maps).
        """
        self.fruits = 0
        self.droplets = 0
        self.tiny_droplets = 0
        self.take = take

    def record_fruit(self) -> None:
        """Count one caught fruit."""
        if self.take > 0:
            self.take -= 1
            self.fruits += 1

    def record_droplet(self) -> None:
        """Count one droplet."""
        if self.take > 0:
            self.take -= 1
            self.droplets += 1

    def record_tiny_droplets(self, n: int) -> None:
        """Count a number of tiny droplets."""
        if self.take > 0:
            self.tiny_droplets += n

@dataclass(slots=True)
class GradualObjectCount:
    """A running snapshot of object counts for gradual calculation."""
    fruit: bool = False
    tiny_droplets: int = 0

class GradualObjectCountBuilder:

    """Like :class:`ObjectCountBuilder` but keeps per-object snapshots."""
    __slots__ = ("_current", "all")

    def __init__(self) -> None:
        """Initialise with empty counts."""
        self._current = GradualObjectCount()
        self.all: list[GradualObjectCount] = []

    def record_fruit(self) -> None:
        """Count one fruit and snapshot the running totals."""
        self._current.fruit = True
        self.all.append(self._current)
        self._current = GradualObjectCount()

    def record_droplet(self) -> None:
        """Count one droplet and snapshot the running totals."""
        self.all.append(self._current)
        self._current = GradualObjectCount()

    def record_tiny_droplets(self, n: int) -> None:
        """Count tiny droplets and snapshot the running totals."""
        self._current.tiny_droplets += n

@dataclass(slots=True)
class PalpableObject:
    """A catchable object (fruit or droplet) at a position and time."""
    x: float
    x_offset: float
    start_time: float
    dist_to_hyper_dash: float = 0.0
    hyper_dash: bool = False

    def effective_x(self) -> float:
        """Return the horizontal position used for movement, accounting for hyperdash."""
        return clamp(f32(self.x + self.x_offset), 0.0, PLAYFIELD_WIDTH)

class NestedKind(Enum):
    """The kind of a nested juice-stream object (droplet, tiny droplet or fruit)."""
    FRUIT = 0
    DROPLET = 1
    TINY_DROPLET = 2

@dataclass(slots=True)
class NestedJuiceStreamObject:
    """A single nested object generated along a juice stream."""
    pos: float
    start_time: float
    kind: NestedKind

@dataclass(slots=True)
class JuiceStream:
    """A slider converted to a stream of fruits and droplets."""
    control_points: list[Any]
    nested_objects: list[NestedJuiceStreamObject] = field(default_factory=list)

def build_juice_stream(
        effective_x: float,
        start_time: float,
        slider: Slider,
        beatmap: PerformanceBeatmap,
        count: ObjectCountBuilder,
) -> JuiceStream:
    """Generate the nested fruits/droplets of a slider (juice stream).

    Args:
        effective_x: The stream's start x position.
        start_time: The slider start time.
        slider: The source slider.
        beatmap: The performance beatmap (for timing and tick rate).
        count: The object-count builder to record into.

    Returns:
        The generated juice stream.
    """
    slider_multiplier = beatmap.slider_multiplier
    slider_tick_rate = beatmap.slider_tick_rate

    tp = timing_point_at(beatmap.timing_points, start_time)
    beat_len = tp.beat_len if tp is not None else _DEFAULT_BEAT_LEN

    dp = difficulty_point_at(beatmap.difficulty_points, start_time)
    slider_velocity = dp.slider_velocity if dp is not None else _DEFAULT_SLIDER_VELOCITY

    try:
        path = Curve(BeatmapGameMode.Catch, slider.control_points, slider.expected_dist)
    except Exception:
        path = None
    path_dist = path.dist() if path is not None else 0.0

    velocity = (
            _BASE_SCORING_DIST * slider_multiplier
            / get_precision_adjusted_beat_length(slider_velocity, beat_len)
    )
    scoring_dist = velocity * beat_len

    if beatmap.version < 8:
        tick_dist_multiplier = (
            1.0 / slider_velocity if slider_velocity != 0.0 else math.inf
        )
    else:
        tick_dist_multiplier = 1.0

    tick_dist = scoring_dist / slider_tick_rate * tick_dist_multiplier

    span_count = float(slider.span_count)
    duration = span_count * path_dist / velocity
    span_duration = duration / span_count

    def _position_x(progress: float) -> float:
        """Return the stream x position at a given path progress."""
        if path is None:
            return 0.0
        pos = _interpolate_curve_position(path, progress)
        return pos.x if pos is not None else 0.0

    nested: list[NestedJuiceStreamObject] = []
    last_event_time: float | None = None

    for e in generate_slider_events(
            start_time=start_time,
            span_duration=span_duration,
            velocity=velocity,
            tick_dist=tick_dist,
            total_dist=path_dist,
            span_count=int(slider.span_count),
    ):
        if last_event_time is not None:
            tiny_droplets = 0
            since_last_tick = float(int(e.time) - int(last_event_time))

            if since_last_tick > 80.0:
                time_between_tiny = since_last_tick

                while time_between_tiny > 100.0:
                    time_between_tiny /= 2.0

                t = time_between_tiny

                while t < since_last_tick:
                    tiny_droplets += 1
                    nested.append(NestedJuiceStreamObject(
                        pos=0.0,
                        start_time=0.0,
                        kind=NestedKind.TINY_DROPLET,
                    ))
                    t += time_between_tiny

            count.record_tiny_droplets(tiny_droplets)

        last_event_time = e.time

        if e.kind == SliderEventType.Tick:
            count.record_droplet()
            kind = NestedKind.DROPLET
        elif e.kind in (
                SliderEventType.Head, SliderEventType.Repeat, SliderEventType.Tail,
        ):
            count.record_fruit()
            kind = NestedKind.FRUIT
        else:
            continue

        nested.append(NestedJuiceStreamObject(
            pos=f32(effective_x + _position_x(e.path_progress)),
            start_time=e.time,
            kind=kind,
        ))

    return JuiceStream(
        control_points=list(slider.control_points),
        nested_objects=nested,
    )

def banana_count(start_time: float, end_time: float) -> int:
    """Return the number of bananas in a banana shower.

    Args:
        start_time: The shower start time.
        end_time: The shower end time.

    Returns:
        The banana count (osu!-stable integer stepping).
    """
    start_i = int(start_time)
    end_i = int(end_time)
    spacing = f32(end_i - start_i)

    while spacing > 100.0:
        spacing = f32(spacing / 2.0)

    if spacing <= 0.0:
        return 0

    end_f = f32(end_i)
    time = f32(start_i)
    count = 0

    while time <= end_f:
        time = f32(time + spacing)
        count += 1

    return count

@dataclass(slots=True)
class LastObject:
    """The trailing catch object plus the cursor position after it."""
    hyper_dash: bool
    dist_to_hyper_dash: float
    player_pos: float | None

@dataclass(slots=True)
class CatchDifficultyObject:
    """One object's movement context (distance, time) for the movement skill."""
    idx: int
    start_time: float
    delta_time: float
    normalized_pos: float
    last_normalized_pos: float
    player_pos: float
    last_player_pos: float
    dist_moved: float
    exact_dist_moved: float
    strain_time: float
    last_object: LastObject

    NORMALIZED_HALF_CATCHER_WIDTH = 41.0
    ABSOLUTE_PLAYER_POSITIONING_ERROR = 16.0

    def previous(
            self, backwards_idx: int, diff_objects: list["CatchDifficultyObject"],
    ) -> "CatchDifficultyObject | None":
        """Return the difficulty object ``backwards_idx`` steps before this one.

        Args:
            backwards_idx: How far back to look (0 = the immediately previous object).
            diff_objects: The full list of difficulty objects.

        Returns:
            The earlier difficulty object, or ``None`` if out of range.
        """
        target = self.idx - (backwards_idx + 1)
        if 0 <= target < len(diff_objects):
            return diff_objects[target]
        return None

    @classmethod
    def new(
            cls,
            hit_object: PalpableObject,
            last_object: PalpableObject,
            clock_rate: float,
            scaling_factor: float,
            last_player_pos: float | None,
            idx: int,
    ) -> "CatchDifficultyObject":
        """Build a difficulty object from a catch object and its predecessor.

        Args:
            hit_object: The current palpable object.
            last_object: The previous object and cursor position.
            clock_rate: The active clock rate.
            scaling_factor: The catcher-size scaling factor.
            last_player_pos: The assumed cursor position after the last object.
            idx: The object's index.

        Returns:
            The constructed difficulty object.
        """
        normalized_pos = f32(hit_object.effective_x() * scaling_factor)
        last_normalized_pos = f32(last_object.effective_x() * scaling_factor)

        start_time = hit_object.start_time / clock_rate
        delta_time = (hit_object.start_time - last_object.start_time) / clock_rate
        strain_time = max(delta_time, 40.0)

        last = LastObject(
            hyper_dash=last_object.hyper_dash,
            dist_to_hyper_dash=last_object.dist_to_hyper_dash,
            player_pos=last_player_pos,
        )

        this = cls(
            idx=idx,
            start_time=start_time,
            delta_time=delta_time,
            normalized_pos=normalized_pos,
            last_normalized_pos=last_normalized_pos,
            player_pos=0.0,
            last_player_pos=0.0,
            dist_moved=0.0,
            exact_dist_moved=0.0,
            strain_time=strain_time,
            last_object=last,
        )
        this._set_movement_state()
        return this

    def _set_movement_state(self) -> None:
        """Compute and store this object's movement distance and timing."""
        self.last_player_pos = (
            self.last_object.player_pos
            if self.last_object.player_pos is not None
            else self.last_normalized_pos
        )

        term = self.NORMALIZED_HALF_CATCHER_WIDTH - self.ABSOLUTE_PLAYER_POSITIONING_ERROR

        self.player_pos = clamp(
            self.last_player_pos,
            f32(self.normalized_pos - term),
            f32(self.normalized_pos + term),
        )

        self.dist_moved = f32(self.player_pos - self.last_player_pos)

        self.exact_dist_moved = f32(self.normalized_pos - self.last_player_pos)

        if self.last_object.hyper_dash:
            self.player_pos = self.normalized_pos
