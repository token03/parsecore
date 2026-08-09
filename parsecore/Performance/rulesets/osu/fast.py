"""Packed and compiled osu!standard structural difficulty calculation."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from parsecore.Beatmap.section.enums import GameMode as BeatmapGameMode
from parsecore.Beatmap.section.hit_objects.hit_objects import convert_path_str
from parsecore.Beatmap.section.hit_objects.slider import (
    Curve,
    SliderEventType,
    generate_slider_events,
)
from parsecore.Beatmap.utils import Pos

from ...data.attributes import AdjustedBeatmapAttributes, as_override
from ...data.hit_objects import HoldNote, Slider, Spinner
from ...data.mode import GameMode
from ...data.mods import PerformanceMods, Reflection
from ...utils import _interpolate_curve_position, get_precision_adjusted_beat_length
from .difficulty import OsuDifficultyAttributes

np: Any = None
njit: Any = None
try:
    import numpy as _numpy
    from numba import njit as _njit

    np = _numpy
    njit = _njit
except ImportError:
    pass

_Function = TypeVar("_Function", bound=Callable[..., Any])

if TYPE_CHECKING:
    def _compile(*args: Any, **kwargs: Any) -> Callable[[_Function], _Function]:
        ...
else:
    _compile = njit

if TYPE_CHECKING:
    from ...data.beatmap import PerformanceBeatmap

MAX_OBJECTS = 4096
_MIN_DELTA = 25.0
_NORMALISED_RADIUS = 50.0
_NORMALISED_DIAMETER = 100.0
_STACK_DISTANCE = 3.0


@dataclass(slots=True)
class PackedOsuMap:
    """Dense numeric representation of the prefix used by the fast calculator."""

    time: Any
    end_time: Any
    x: Any
    y: Any
    end_x: Any
    end_y: Any
    lazy_end_x: Any
    lazy_end_y: Any
    last_nested_x: Any
    last_nested_y: Any
    kind: Any
    repeats: Any
    slider_dist: Any
    slider_duration: Any
    stack_height: Any
    n_circles: int
    n_sliders: int
    n_spinners: int
    max_combo: int
    n_large_ticks: int
    truncated: bool


@dataclass(slots=True)
class FastBeatmap:
    """Minimal map metadata and packed objects produced by the direct parser."""

    packed: PackedOsuMap
    mode: int
    base_ar: float
    base_cs: float
    base_hp: float
    base_od: float
    slider_multiplier: float
    slider_tick_rate: float


def _slider_summary(
        curve: Curve,
        *,
        start_time: float,
        repeat_count: int,
        velocity: float,
        tick_distance: float,
        radius: float,
) -> tuple[float, float, float, float, float, float, float, float, float, int]:
    distance = curve.dist()
    span_count = repeat_count + 1
    if distance <= 0.0 or velocity <= 0.0:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)

    span_duration = distance / velocity
    duration = span_count * span_duration
    events = list(generate_slider_events(
        start_time=start_time,
        span_duration=span_duration,
        velocity=velocity,
        tick_dist=tick_distance,
        total_dist=distance,
        span_count=span_count,
    ))
    nested = [
        (event, _interpolate_curve_position(curve, event.path_progress))
        for event in events
        if event.kind in {
            SliderEventType.Tick,
            SliderEventType.Repeat,
            SliderEventType.Tail,
        }
    ]
    tail = nested[-1][1] if nested else Pos(0.0, 0.0)
    penultimate = nested[-2][1] if len(nested) >= 2 else Pos(0.0, 0.0)

    tracking_end_time = max(
        start_time + duration - 36.0,
        start_time + duration / 2.0,
    )
    last_tick_index = -1
    for index, (event, _) in enumerate(nested):
        if event.kind == SliderEventType.Tick:
            last_tick_index = index
    lazy_nested = nested
    if last_tick_index >= 0 and nested[last_tick_index][0].time > tracking_end_time:
        tracking_end_time = nested[last_tick_index][0].time
        lazy_nested = (
            nested[:last_tick_index]
            + nested[last_tick_index + 1:]
            + [nested[last_tick_index]]
        )

    lazy_travel_time = tracking_end_time - start_time
    progress = lazy_travel_time / span_duration if span_duration > 0.0 else 0.0
    progress = 1.0 - progress % 1.0 if progress % 2.0 >= 1.0 else progress % 1.0
    lazy_target = _interpolate_curve_position(curve, progress)
    cursor = Pos(0.0, 0.0)
    factor = 50.0 / radius if radius > 0.0 else 0.0
    lazy_travel_distance = 0.0
    for index, (event, position) in enumerate(lazy_nested):
        movement = position - cursor
        movement_length = factor * movement.length()
        required_movement = (
            50.0 if event.kind == SliderEventType.Repeat else 90.0
        )
        if index == len(lazy_nested) - 1:
            lazy_movement = lazy_target - cursor
            if lazy_movement.length() < movement.length():
                movement = lazy_movement
                movement_length = factor * movement.length()
        if movement_length > required_movement:
            fraction = (movement_length - required_movement) / movement_length
            cursor += movement * fraction
            lazy_travel_distance += movement_length * fraction

    nested_count = sum(
        event.kind in {SliderEventType.Tick, SliderEventType.Repeat}
        for event, _ in nested
    )
    return (
        tail.x,
        tail.y,
        cursor.x,
        cursor.y,
        penultimate.x,
        penultimate.y,
        lazy_travel_distance,
        lazy_travel_time,
        duration,
        nested_count,
    )


def _approximate_slider_summary(
        *,
        endpoint_x: float,
        endpoint_y: float,
        distance: float,
        repeat_count: int,
        velocity: float,
        tick_distance: float,
        radius: float,
) -> tuple[float, float, float, float, float, float, float, float, float, int]:
    span_count = repeat_count + 1
    if distance <= 0.0 or velocity <= 0.0:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)

    span_duration = distance / velocity
    duration = span_count * span_duration
    lazy_travel_time = max(duration - 36.0, duration / 2.0)
    factor = 50.0 / radius if radius > 0.0 else 0.0
    cursor_x = 0.0
    cursor_y = 0.0
    lazy_travel_distance = 0.0
    for span in range(span_count):
        is_last = span == span_count - 1
        if is_last:
            progress = lazy_travel_time / span_duration
            progress = (
                1.0 - progress % 1.0
                if progress % 2.0 >= 1.0
                else progress % 1.0
            )
            target_x = endpoint_x * progress
            target_y = endpoint_y * progress
            required = 90.0
        elif span % 2 == 0:
            target_x = endpoint_x
            target_y = endpoint_y
            required = 50.0
        else:
            target_x = 0.0
            target_y = 0.0
            required = 50.0
        movement_x = target_x - cursor_x
        movement_y = target_y - cursor_y
        movement_length = factor * math.sqrt(
            movement_x * movement_x + movement_y * movement_y
        )
        if movement_length > required:
            fraction = (movement_length - required) / movement_length
            cursor_x += movement_x * fraction
            cursor_y += movement_y * fraction
            lazy_travel_distance += movement_length * fraction

    tail_x = endpoint_x if span_count % 2 == 1 else 0.0
    tail_y = endpoint_y if span_count % 2 == 1 else 0.0
    if span_count % 2 == 1:
        penultimate_x = 0.0
        penultimate_y = 0.0
    else:
        penultimate_x = endpoint_x
        penultimate_y = endpoint_y
    min_distance_from_end = velocity * 10.0
    ticks = 0
    if tick_distance > 0.0:
        tick = tick_distance
        while tick < distance - min_distance_from_end:
            ticks += 1
            tick += tick_distance
    nested_count = ticks * span_count + repeat_count
    return (
        tail_x,
        tail_y,
        cursor_x,
        cursor_y,
        penultimate_x,
        penultimate_y,
        lazy_travel_distance,
        lazy_travel_time,
        duration,
        nested_count,
    )


@dataclass(frozen=True, slots=True)
class StructuralFactors:
    """The five independent structural difficulty factors for one map."""

    stars: float
    aim: float
    speed: float
    slider: float
    snap: float
    agility: float
    flow: float
    tap: float
    rhythm: float
    object_count: int
    objects_pruned: bool


def _parse_fast_bytes(
        data: bytes,
        max_objects: int,
        cs_override: float | tuple[float, bool] | None = None,
) -> FastBeatmap:
    array = _require_numpy()
    if max_objects < 1:
        raise ValueError("max_objects must be positive")

    mode = 0
    base_ar = 5.0
    base_cs = 5.0
    base_hp = 5.0
    base_od = 5.0
    slider_multiplier = 1.4
    slider_tick_rate = 1.0
    stack_leniency = 0.7
    version = 14.0
    truncated = False

    timing_times: list[float] = []
    timing_beats: list[float] = []
    difficulty_times: list[float] = []
    difficulty_velocity: list[float] = []

    times: list[float] = []
    x_values: list[float] = []
    y_values: list[float] = []
    end_x_values: list[float] = []
    end_y_values: list[float] = []
    kinds: list[int] = []
    repeat_values: list[int] = []
    distances: list[float] = []
    slider_paths: list[bytes | None] = []

    section = b""
    for raw_line in data.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(b"//"):
            continue
        if line.startswith(b"osu file format v"):
            try:
                version = float(line.rsplit(b"v", 1)[1])
            except ValueError:
                pass
            continue
        if line.startswith(b"[") and line.endswith(b"]"):
            section = line
            continue

        if section == b"[General]":
            key, separator, raw_value = line.partition(b":")
            if not separator:
                continue
            value = raw_value.strip()
            if key == b"Mode":
                mode = int(value)
            elif key == b"StackLeniency":
                stack_leniency = float(value)
        elif section == b"[Difficulty]":
            key, separator, raw_value = line.partition(b":")
            if not separator:
                continue
            numeric_value = float(raw_value)
            if key == b"ApproachRate":
                base_ar = numeric_value
            elif key == b"CircleSize":
                base_cs = numeric_value
            elif key == b"HPDrainRate":
                base_hp = numeric_value
            elif key == b"OverallDifficulty":
                base_od = numeric_value
            elif key == b"SliderMultiplier":
                slider_multiplier = numeric_value
            elif key == b"SliderTickRate":
                slider_tick_rate = numeric_value
        elif section == b"[TimingPoints]":
            parts = line.split(b",")
            if len(parts) < 2:
                continue
            point_time = float(parts[0])
            beat_length = float(parts[1])
            if math.isnan(beat_length):
                continue
            timing_change = len(parts) <= 6 or parts[6].strip().startswith(b"1")
            if beat_length > 0.0 and timing_change:
                timing_times.append(point_time)
                timing_beats.append(max(6.0, min(60000.0, beat_length)))
            if beat_length < 0.0:
                slider_velocity = max(0.1, min(10.0, 100.0 / -beat_length))
            else:
                slider_velocity = 1.0
            difficulty_times.append(point_time)
            difficulty_velocity.append(slider_velocity)
        elif section == b"[HitObjects]":
            if len(times) >= max_objects:
                truncated = True
                continue
            parts = line.split(b",")
            if len(parts) < 5:
                continue
            start = float(parts[2])
            type_flags = int(parts[3])
            start_x = float(parts[0])
            start_y = float(parts[1])
            times.append(start)
            x_values.append(start_x)
            y_values.append(start_y)
            end_x_values.append(start_x)
            end_y_values.append(start_y)
            repeat = 0
            distance = 0.0
            if type_flags & 2 and len(parts) >= 7:
                kinds.append(1)
                slider_paths.append(parts[5])
                repeat = max(0, int(parts[6]) - 1)
                repeat_values.append(repeat)
                if len(parts) > 7:
                    try:
                        distance = max(0.0, float(parts[7]))
                    except ValueError:
                        distance = 0.0

            elif type_flags & 8 and len(parts) >= 6:
                kinds.append(2)
                slider_paths.append(None)
                repeat_values.append(0)
                end_time = float(parts[5])
                distance = max(0.0, end_time - start)
            else:
                kinds.append(0)
                slider_paths.append(None)
                repeat_values.append(0)
            distances.append(distance)

    count = len(times)
    time_array = array.asarray(times, dtype=array.float32)
    end_time_array = time_array.copy()
    x_array = array.asarray(x_values, dtype=array.float32)
    y_array = array.asarray(y_values, dtype=array.float32)
    end_x_array = array.asarray(end_x_values, dtype=array.float32)
    end_y_array = array.asarray(end_y_values, dtype=array.float32)
    lazy_end_x_array = x_array.copy()
    lazy_end_y_array = y_array.copy()
    last_nested_x_array = x_array.copy()
    last_nested_y_array = y_array.copy()
    kind_array = array.asarray(kinds, dtype=array.uint8)
    repeat_array = array.asarray(repeat_values, dtype=array.int16)
    distance_array = array.asarray(distances, dtype=array.float32)
    duration_array = array.zeros(count, dtype=array.float32)

    effective_cs = (
        float(cs_override[0])
        if isinstance(cs_override, tuple) and cs_override[1]
        else base_cs
    )
    scale = (1.0 - 0.7 * (effective_cs - 5.0) / 5.0) / 2.0 * 1.00041
    radius = 64.0 * scale

    timing_index = 0
    difficulty_index = 0
    n_circles = 0
    n_sliders = 0
    n_spinners = 0
    max_combo = 0
    n_large_ticks = 0
    for index in range(count):
        max_combo += 1
        if kind_array[index] == 1:
            n_sliders += 1
            while (
                    timing_index + 1 < len(timing_times)
                    and timing_times[timing_index + 1] <= time_array[index]
            ):
                timing_index += 1
            while (
                    difficulty_index + 1 < len(difficulty_times)
                    and difficulty_times[difficulty_index + 1] <= time_array[index]
            ):
                difficulty_index += 1
            beat_length = (
                timing_beats[timing_index]
                if timing_times and timing_times[timing_index] <= time_array[index]
                else 1000.0
            )
            slider_velocity = (
                difficulty_velocity[difficulty_index]
                if difficulty_times
                and difficulty_times[difficulty_index] <= time_array[index]
                else 1.0
            )
            adjusted_beat_length = get_precision_adjusted_beat_length(
                slider_velocity, beat_length
            )
            velocity = (
                100.0 * slider_multiplier / adjusted_beat_length
                if adjusted_beat_length > 0.0
                else 0.0
            )
            tick_distance = (
                velocity * beat_length / slider_tick_rate
                * (1.0 / slider_velocity if version < 8.0 else 1.0)
                if slider_velocity > 0.0 and slider_tick_rate > 0.0
                else 0.0
            )
            endpoint_x = 0.0
            endpoint_y = 0.0
            previous_x = 0.0
            previous_y = 0.0
            polyline_length = 0.0
            for token in (slider_paths[index] or b"").split(b"|")[1:]:
                if token[:1].isalpha():
                    continue
                point = token.split(b":", 1)
                if len(point) != 2:
                    continue
                endpoint_x = float(point[0]) - float(x_array[index])
                endpoint_y = float(point[1]) - float(y_array[index])
                dx = endpoint_x - previous_x
                dy = endpoint_y - previous_y
                polyline_length += math.sqrt(dx * dx + dy * dy)
                previous_x = endpoint_x
                previous_y = endpoint_y
            distance = float(distance_array[index])
            if distance <= 0.0:
                distance = polyline_length
            chord_length = math.sqrt(
                endpoint_x * endpoint_x + endpoint_y * endpoint_y
            )
            needs_curve = (
                distance < chord_length * 0.5
                or distance > polyline_length * 1.3
            )
            try:
                if needs_curve:
                    points = convert_path_str(
                        (slider_paths[index] or b"").decode("ascii"),
                        Pos(float(x_array[index]), float(y_array[index])),
                    )
                    curve = Curve(
                        BeatmapGameMode.Osu,
                        points,
                        distance,
                    )
                    summary = _slider_summary(
                        curve,
                        start_time=float(time_array[index]),
                        repeat_count=int(repeat_array[index]),
                        velocity=velocity,
                        tick_distance=tick_distance,
                        radius=radius,
                    )
                else:
                    summary = _approximate_slider_summary(
                        endpoint_x=endpoint_x,
                        endpoint_y=endpoint_y,
                        distance=distance,
                        repeat_count=int(repeat_array[index]),
                        velocity=velocity,
                        tick_distance=tick_distance,
                        radius=radius,
                    )
            except Exception:
                summary = (0.0,) * 9 + (0,)
            end_x_array[index] += summary[0]
            end_y_array[index] += summary[1]
            lazy_end_x_array[index] += summary[2]
            lazy_end_y_array[index] += summary[3]
            last_nested_x_array[index] += summary[4]
            last_nested_y_array[index] += summary[5]
            distance_array[index] = summary[6]
            duration_array[index] = summary[7]
            duration = summary[8]
            end_time_array[index] = time_array[index] + duration
            max_combo += summary[9]
            n_large_ticks += summary[9]
        elif kind_array[index] == 2:
            n_spinners += 1
        else:
            n_circles += 1

    stack_height = _stack_heights(
        time_array,
        end_time_array,
        x_array,
        y_array,
        end_x_array,
        end_y_array,
        kind_array,
        stack_leniency,
        version,
    )
    packed = PackedOsuMap(
        time=time_array,
        end_time=end_time_array,
        x=x_array,
        y=y_array,
        end_x=end_x_array,
        end_y=end_y_array,
        lazy_end_x=lazy_end_x_array,
        lazy_end_y=lazy_end_y_array,
        last_nested_x=last_nested_x_array,
        last_nested_y=last_nested_y_array,
        kind=kind_array,
        repeats=repeat_array,
        slider_dist=distance_array,
        slider_duration=duration_array,
        stack_height=stack_height,
        n_circles=n_circles,
        n_sliders=n_sliders,
        n_spinners=n_spinners,
        max_combo=max_combo,
        n_large_ticks=n_large_ticks,
        truncated=truncated,
    )
    return FastBeatmap(
        packed=packed,
        mode=mode,
        base_ar=base_ar,
        base_cs=base_cs,
        base_hp=base_hp,
        base_od=base_od,
        slider_multiplier=slider_multiplier,
        slider_tick_rate=slider_tick_rate,
    )


def _require_numpy() -> Any:
    if np is None or njit is None:
        raise ImportError(
            "the fast osu calculator requires numpy and numba; "
            "install parsecore[fast]"
        )
    return np


def _pack_map(
        beatmap: PerformanceBeatmap,
        *,
        max_objects: int,
        radius: float,
) -> PackedOsuMap:
    array = _require_numpy()
    if max_objects < 1:
        raise ValueError("max_objects must be positive")

    source = beatmap.hit_objects
    count = min(len(source), max_objects)
    time = array.empty(count, dtype=array.float32)
    end_time = array.empty(count, dtype=array.float32)
    x = array.empty(count, dtype=array.float32)
    y = array.empty(count, dtype=array.float32)
    end_x = array.empty(count, dtype=array.float32)
    end_y = array.empty(count, dtype=array.float32)
    lazy_end_x = array.empty(count, dtype=array.float32)
    lazy_end_y = array.empty(count, dtype=array.float32)
    last_nested_x = array.empty(count, dtype=array.float32)
    last_nested_y = array.empty(count, dtype=array.float32)
    kind = array.zeros(count, dtype=array.uint8)
    repeats = array.zeros(count, dtype=array.int16)
    slider_dist = array.zeros(count, dtype=array.float32)
    slider_duration = array.zeros(count, dtype=array.float32)

    timing_points = beatmap.timing_points
    difficulty_points = beatmap.difficulty_points
    timing_index = 0
    difficulty_index = 0
    n_circles = 0
    n_sliders = 0
    n_spinners = 0
    max_combo = 0
    n_large_ticks = 0

    for index, hit_object in enumerate(source[:count]):
        start = float(hit_object.start_time)
        time[index] = start
        end_time[index] = float(hit_object.end_time)
        x[index] = float(hit_object.pos.x)
        y[index] = float(hit_object.pos.y)
        end_x[index] = x[index]
        end_y[index] = y[index]
        lazy_end_x[index] = x[index]
        lazy_end_y[index] = y[index]
        last_nested_x[index] = x[index]
        last_nested_y[index] = y[index]
        max_combo += 1

        inner = hit_object.kind
        if isinstance(inner, Slider):
            kind[index] = 1
            n_sliders += 1
            repeats[index] = inner.repeats

            while (
                    timing_index + 1 < len(timing_points)
                    and timing_points[timing_index + 1].time <= start
            ):
                timing_index += 1
            while (
                    difficulty_index + 1 < len(difficulty_points)
                    and difficulty_points[difficulty_index + 1].time <= start
            ):
                difficulty_index += 1

            beat_length = (
                timing_points[timing_index].beat_len
                if timing_points and timing_points[timing_index].time <= start
                else 1000.0
            )
            slider_velocity = (
                difficulty_points[difficulty_index].slider_velocity
                if difficulty_points
                and difficulty_points[difficulty_index].time <= start
                else 1.0
            )
            adjusted_beat_length = get_precision_adjusted_beat_length(
                slider_velocity, beat_length
            )
            velocity = (
                100.0 * beatmap.slider_multiplier / adjusted_beat_length
                if adjusted_beat_length > 0.0
                else 0.0
            )
            tick_distance = (
                velocity * beat_length / beatmap.slider_tick_rate
                if slider_velocity > 0.0
                and beat_length > 0.0
                and beatmap.slider_tick_rate > 0.0
                else 0.0
            )
            endpoint_x = 0.0
            endpoint_y = 0.0
            previous_x = 0.0
            previous_y = 0.0
            polyline_length = 0.0
            for point in inner.control_points:
                endpoint_x = float(point.pos.x)
                endpoint_y = float(point.pos.y)
                dx = endpoint_x - previous_x
                dy = endpoint_y - previous_y
                polyline_length += math.sqrt(dx * dx + dy * dy)
                previous_x = endpoint_x
                previous_y = endpoint_y
            distance = (
                float(inner.expected_dist)
                if inner.expected_dist is not None and inner.expected_dist > 0.0
                else polyline_length
            )
            chord_length = math.sqrt(
                endpoint_x * endpoint_x + endpoint_y * endpoint_y
            )
            needs_curve = (
                distance < chord_length * 0.5
                or distance > polyline_length * 1.3
            )
            try:
                if needs_curve:
                    curve = Curve(
                        BeatmapGameMode.Osu,
                        inner.control_points,
                        inner.expected_dist,
                    )
                    summary = _slider_summary(
                        curve,
                        start_time=start,
                        repeat_count=inner.repeats,
                        velocity=velocity,
                        tick_distance=tick_distance,
                        radius=radius,
                    )
                else:
                    summary = _approximate_slider_summary(
                        endpoint_x=endpoint_x,
                        endpoint_y=endpoint_y,
                        distance=distance,
                        repeat_count=inner.repeats,
                        velocity=velocity,
                        tick_distance=tick_distance,
                        radius=radius,
                    )
            except Exception:
                summary = (0.0,) * 9 + (0,)
            end_x[index] += summary[0]
            end_y[index] += summary[1]
            lazy_end_x[index] += summary[2]
            lazy_end_y[index] += summary[3]
            last_nested_x[index] += summary[4]
            last_nested_y[index] += summary[5]
            slider_dist[index] = summary[6]
            slider_duration[index] = summary[7]
            duration = summary[8]
            end_time[index] = start + duration
            max_combo += summary[9]
            n_large_ticks += summary[9]
        elif isinstance(inner, (Spinner, HoldNote)):
            kind[index] = 2
            n_spinners += 1
        else:
            n_circles += 1

    stack_height = _stack_heights(
        time,
        end_time,
        x,
        y,
        end_x,
        end_y,
        kind,
        float(getattr(beatmap, "stack_leniency", 0.7)),
        float(getattr(beatmap, "version", 14)),
    )

    return PackedOsuMap(
        time=time,
        end_time=end_time,
        x=x,
        y=y,
        end_x=end_x,
        end_y=end_y,
        lazy_end_x=lazy_end_x,
        lazy_end_y=lazy_end_y,
        last_nested_x=last_nested_x,
        last_nested_y=last_nested_y,
        kind=kind,
        repeats=repeats,
        slider_dist=slider_dist,
        slider_duration=slider_duration,
        stack_height=stack_height,
        n_circles=n_circles,
        n_sliders=n_sliders,
        n_spinners=n_spinners,
        max_combo=max_combo,
        n_large_ticks=n_large_ticks,
        truncated=len(source) > count,
    )


_stack_heights: Any = None
_preprocess: Any = None
_calculate_kernel: Any = None

if njit is not None:

    @_compile(cache=True, fastmath=True)
    def _stack_heights(
            time: Any,
            end_time: Any,
            x: Any,
            y: Any,
            end_x: Any,
            end_y: Any,
            kind: Any,
            stack_leniency: float,
            version: float,
    ) -> Any:
        count = time.shape[0]
        result = np.zeros(count, dtype=np.int16)
        if count == 0:
            return result

        threshold = max(0.0, time[0] * 0.0 + 450.0 * stack_leniency)
        for i in range(count - 1, 0, -1):
            if kind[i] == 2:
                continue
            j = i - 1
            while j >= 0:
                if version >= 6.0:
                    if time[i] - end_time[j] > threshold:
                        break
                elif time[i] - time[j] > threshold:
                    break

                if kind[j] != 2:
                    dx = x[j] - x[i]
                    dy = y[j] - y[i]
                    if dx * dx + dy * dy < _STACK_DISTANCE * _STACK_DISTANCE:
                        result[j] = result[i] + 1
                        break

                    dx = end_x[j] - x[i]
                    dy = end_y[j] - y[i]
                    if kind[j] == 1 and dx * dx + dy * dy < _STACK_DISTANCE * _STACK_DISTANCE:
                        result[j] = result[i] + 1
                        break
                j -= 1
        return result


    @_compile(cache=True, inline="always", fastmath=True)
    def _clamp(value: float, lower: float, upper: float) -> float:
        return min(max(value, lower), upper)


    @_compile(cache=True, inline="always", fastmath=True)
    def _smoothstep(value: float, start: float, end: float) -> float:
        value = _clamp((value - start) / (end - start), 0.0, 1.0)
        return value * value * (3.0 - 2.0 * value)


    @_compile(cache=True, inline="always", fastmath=True)
    def _smootherstep(value: float, start: float, end: float) -> float:
        value = _clamp((value - start) / (end - start), 0.0, 1.0)
        return value * value * value * (value * (6.0 * value - 15.0) + 10.0)


    @_compile(cache=True, inline="always", fastmath=True)
    def _norm2(a: float, b: float) -> float:
        return math.sqrt(a * a + b * b)


    @_compile(cache=True, inline="always", fastmath=True)
    def _decay(base: float, milliseconds: float) -> float:
        return float(base ** (milliseconds / 1000.0))


    @_compile(cache=True, inline="always", fastmath=True)
    def _high_bpm_bonus(milliseconds: float, base: float) -> float:
        return float(1.0 / (1.0 - base ** (milliseconds / 1000.0)))


    @_compile(cache=True, inline="always", fastmath=True)
    def _weighted_count(values: Any, max_value: float) -> float:
        if max_value <= 0.0:
            return 0.0
        total = 0.0
        for value in values:
            total += 1.0 / (1.0 + math.exp(-(value / max_value * 12.0 - 6.0)))
        return total


    @_compile(cache=True, fastmath=True)
    def _harmonic(values: Any, scale: float) -> float:
        ordered = np.sort(values)[::-1]
        result = 0.0
        for index in range(ordered.shape[0]):
            value = ordered[index]
            if value <= 0.0:
                break
            index_float = float(index)
            weight = (1.0 + scale / (1.0 + index_float)) / (
                index_float ** 0.9 + 1.0 + scale / (1.0 + index_float)
            )
            result += value * weight
        return result


    @_compile(cache=True, fastmath=True)
    def _peak_value(values: Any, time: Any) -> float:
        count = values.shape[0]
        peaks = np.zeros(count, dtype=np.float64)
        peak_count = 0
        current_peak = 0.0
        current_end = math.ceil(time[0] / 400.0) * 400.0 if count else 0.0

        for index in range(count):
            while time[index] > current_end:
                if peak_count < count:
                    peaks[peak_count] = current_peak
                    peak_count += 1
                current_peak = 0.0
                skipped = int((time[index] - current_end) / 400.0) + 1
                current_end += skipped * 400.0
            current = values[index]
            if current > current_peak:
                current_peak = current

        if count:
            peaks[peak_count] = current_peak
            peak_count += 1

        ordered = np.sort(peaks[:peak_count])[::-1]
        result = 0.0
        weight = 1.0
        for index in range(ordered.shape[0]):
            value = ordered[index]
            if value <= 0.0:
                break
            if index < 10:
                scale = math.log10(1.0 + 9.0 * min(index / 10.0, 1.0))
                value *= 0.727 + (1.0 - 0.727) * scale
            result += value * weight
            weight *= 0.9
        return result


    @_compile(cache=True, fastmath=True)
    def _variable_peak_value(values: Any, time: Any, clock_rate: float) -> float:
        count = values.shape[0]
        if count == 0:
            return 0.0

        capacity = count + 512
        peak_values = np.zeros(capacity, dtype=np.float64)
        peak_lengths = np.zeros(capacity, dtype=np.float64)
        peak_count = 0
        total_length = 0.0
        queued_values = np.zeros(count, dtype=np.float64)
        queued_times = np.zeros(count, dtype=np.float64)
        queue_start = 0
        queue_end = 0

        section_begin = time[0] / clock_rate
        section_end = section_begin + 400.0
        current_peak = values[0]

        for index in range(1, count):
            current_time = time[index] / clock_rate
            previous_time = time[index - 1] / clock_rate
            while current_time > section_end:
                section_length = round(section_end - section_begin)
                insert = peak_count
                while insert > 0 and peak_values[insert - 1] < current_peak:
                    peak_values[insert] = peak_values[insert - 1]
                    peak_lengths[insert] = peak_lengths[insert - 1]
                    insert -= 1
                peak_values[insert] = current_peak
                peak_lengths[insert] = section_length
                peak_count += 1
                total_length += section_length
                while total_length > 44_000.0 and peak_count > 0:
                    peak_count -= 1
                    total_length -= peak_lengths[peak_count]

                section_begin = section_end
                current_peak = values[index - 1] * _decay(
                    0.2, section_begin - previous_time
                )
                if queue_start < queue_end:
                    queued_strain = queued_values[queue_start]
                    section_end = queued_times[queue_start] + 400.0
                    queue_start += 1
                    current_peak = max(current_peak, queued_strain)
                else:
                    section_end = section_begin + 400.0

            current_strain = values[index]
            if current_strain > current_peak:
                queue_start = 0
                queue_end = 0
                section_length = round(current_time - section_begin)
                insert = peak_count
                while insert > 0 and peak_values[insert - 1] < current_peak:
                    peak_values[insert] = peak_values[insert - 1]
                    peak_lengths[insert] = peak_lengths[insert - 1]
                    insert -= 1
                peak_values[insert] = current_peak
                peak_lengths[insert] = section_length
                peak_count += 1
                total_length += section_length
                while total_length > 44_000.0 and peak_count > 0:
                    peak_count -= 1
                    total_length -= peak_lengths[peak_count]
                section_begin = current_time
                section_end = section_begin + 400.0
                current_peak = current_strain
            else:
                while (
                        queue_end > queue_start
                        and queued_values[queue_end - 1] < current_strain
                ):
                    queue_end -= 1
                queued_values[queue_end] = current_strain
                queued_times[queue_end] = current_time
                queue_end += 1

        section_length = round(section_end - section_begin)
        insert = peak_count
        while insert > 0 and peak_values[insert - 1] < current_peak:
            peak_values[insert] = peak_values[insert - 1]
            peak_lengths[insert] = peak_lengths[insert - 1]
            insert -= 1
        peak_values[insert] = current_peak
        peak_lengths[insert] = section_length
        peak_count += 1
        total_length += section_length
        while total_length > 44_000.0 and peak_count > 0:
            peak_count -= 1
            total_length -= peak_lengths[peak_count]

        reduced_values = np.zeros(capacity, dtype=np.float64)
        reduced_lengths = np.zeros(capacity, dtype=np.float64)
        reduced_count = 0
        reduced_time = 0.0
        skipped = 0
        while skipped < peak_count and reduced_time < 4000.0:
            value = peak_values[skipped]
            length = peak_lengths[skipped]
            added = 0.0
            chunks = math.ceil(length / 20.0)
            if reduced_count + chunks > capacity:
                raise ValueError("reduced strain capacity exceeded")
            while added < length:
                scale = math.log10(
                    1.0
                    + 9.0
                    * _clamp((reduced_time + added) / 4000.0, 0.0, 1.0)
                )
                chunk = min(20.0, length - added)
                reduced_values[reduced_count] = value * (
                    0.727 + (1.0 - 0.727) * scale
                )
                reduced_lengths[reduced_count] = round(chunk)
                reduced_count += 1
                added += 20.0
            reduced_time += length
            skipped += 1

        if reduced_count + peak_count - skipped > capacity:
            raise ValueError("reduced strain capacity exceeded")
        for index in range(skipped, peak_count):
            reduced_values[reduced_count] = peak_values[index]
            reduced_lengths[reduced_count] = peak_lengths[index]
            reduced_count += 1

        for index in range(1, reduced_count):
            value = reduced_values[index]
            length = reduced_lengths[index]
            insert = index
            while insert > 0 and reduced_values[insert - 1] < value:
                reduced_values[insert] = reduced_values[insert - 1]
                reduced_lengths[insert] = reduced_lengths[insert - 1]
                insert -= 1
            reduced_values[insert] = value
            reduced_lengths[insert] = length

        difficulty = 0.0
        weighted_time = 0.0
        for index in range(reduced_count):
            end = weighted_time + reduced_lengths[index] / 400.0
            weight = 0.9 ** weighted_time - 0.9 ** end
            difficulty += reduced_values[index] * weight
            weighted_time = end
        return difficulty / 0.1


    @_compile(cache=True, fastmath=True)
    def _preprocess(
            time: Any,
            end_time: Any,
            x: Any,
            y: Any,
            end_x: Any,
            end_y: Any,
            lazy_end_x: Any,
            lazy_end_y: Any,
            last_nested_x: Any,
            last_nested_y: Any,
            kind: Any,
            repeats: Any,
            slider_dist: Any,
            slider_duration: Any,
            stack_height: Any,
            clock_rate: float,
            radius: float,
            scale: float,
    ) -> Any:
        count = time.shape[0]
        delta = np.zeros(count, dtype=np.float64)
        adjusted_delta = np.zeros(count, dtype=np.float64)
        jump = np.zeros(count, dtype=np.float64)
        lazy_jump = np.zeros(count, dtype=np.float64)
        min_jump = np.zeros(count, dtype=np.float64)
        min_jump_time = np.zeros(count, dtype=np.float64)
        travel_dist = np.zeros(count, dtype=np.float64)
        travel_time = np.zeros(count, dtype=np.float64)
        lazy_travel_dist = np.zeros(count, dtype=np.float64)
        last_object_end_delta_time = np.zeros(count, dtype=np.float64)
        angle = np.zeros(count, dtype=np.float64)
        has_angle = np.zeros(count, dtype=np.uint8)
        normalised_vector_angle = np.zeros(count, dtype=np.float64)
        small_bonus = max(1.0, 1.0 + (30.0 - radius) / 70.0)

        offset_scale = scale * -6.4
        sx = x + stack_height * offset_scale
        sy = y + stack_height * offset_scale
        ex = end_x + stack_height * offset_scale
        ey = end_y + stack_height * offset_scale
        lex = lazy_end_x + stack_height * offset_scale
        ley = lazy_end_y + stack_height * offset_scale
        lnx = last_nested_x + stack_height * offset_scale
        lny = last_nested_y + stack_height * offset_scale

        for index in range(count):
            if kind[index] == 1:
                lazy = slider_dist[index]
                lazy_travel_dist[index] = lazy
                travel_dist[index] = lazy * max(1.0, float(repeats[index]) ** 0.3)
                travel_time[index] = max(
                    slider_duration[index] / clock_rate,
                    _MIN_DELTA,
                )

            if index == 0:
                delta[index] = 0.0
                adjusted_delta[index] = _MIN_DELTA
                min_jump_time[index] = _MIN_DELTA
                last_object_end_delta_time[index] = _MIN_DELTA
                continue

            delta[index] = (time[index] - time[index - 1]) / clock_rate
            adjusted_delta[index] = max(delta[index], _MIN_DELTA)
            last_x = lex[index - 1] if kind[index - 1] == 1 else sx[index - 1]
            last_y = ley[index - 1] if kind[index - 1] == 1 else sy[index - 1]
            dx = sx[index] - sx[index - 1]
            dy = sy[index] - sy[index - 1]
            jump[index] = _norm2(dx, dy) * 50.0 / radius
            dx = sx[index] - last_x
            dy = sy[index] - last_y
            lazy_jump[index] = _norm2(dx, dy) * 50.0 / radius
            min_jump[index] = lazy_jump[index]
            min_jump_time[index] = adjusted_delta[index]
            last_object_end_delta_time[index] = max(
                (time[index] - end_time[index - 1]) / clock_rate,
                _MIN_DELTA,
            )

            if kind[index - 1] == 1:
                previous_travel_time = max(travel_time[index - 1], _MIN_DELTA)
                min_jump_time[index] = max(
                    adjusted_delta[index] - previous_travel_time, _MIN_DELTA
                )

                tail_jump = _norm2(
                    ex[index - 1] - sx[index],
                    ey[index - 1] - sy[index],
                ) * 50.0 / radius
                min_jump[index] = max(
                    min(lazy_jump[index] - 30.0, tail_jump - 120.0),
                    0.0,
                )

            if index >= 2 and kind[index] != 2 and kind[index - 1] != 2:
                last_cursor_x = sx[index - 1] if kind[index - 1] == 1 else last_x
                last_cursor_y = sy[index - 1] if kind[index - 1] == 1 else last_y
                previous_x = lex[index - 2] if kind[index - 2] == 1 else sx[index - 2]
                previous_y = ley[index - 2] if kind[index - 2] == 1 else sy[index - 2]
                first_x = previous_x - last_cursor_x
                first_y = previous_y - last_cursor_y
                second_x = sx[index] - last_cursor_x
                second_y = sy[index] - last_cursor_y
                dot = first_x * second_x + first_y * second_y
                cross = abs(first_x * second_y - first_y * second_x)
                normalised_vector_angle[index] = math.atan2(
                    abs(second_y), abs(second_x)
                )
                direct_angle = math.atan2(cross, dot)
                slider_angle = direct_angle
                if kind[index - 1] == 1:
                    slider_first_x = lnx[index - 1] - lex[index - 1]
                    slider_first_y = lny[index - 1] - ley[index - 1]
                    slider_second_x = sx[index] - lex[index - 1]
                    slider_second_y = sy[index] - ley[index - 1]
                    slider_angle = math.atan2(
                        abs(
                            slider_first_x * slider_second_y
                            - slider_first_y * slider_second_x
                        ),
                        slider_first_x * slider_second_x
                        + slider_first_y * slider_second_y,
                    )
                angle[index] = min(direct_angle, slider_angle)
                has_angle[index] = 1

        return (
            delta,
            adjusted_delta,
            jump,
            lazy_jump,
            min_jump,
            min_jump_time,
            travel_dist,
            travel_time,
            lazy_travel_dist,
            last_object_end_delta_time,
            angle,
            has_angle,
            normalised_vector_angle,
            sx,
            sy,
            small_bonus,
        )


    @_compile(cache=True, inline="always", fastmath=True)
    def _flow_overlap(
            first_x: float,
            first_y: float,
            second_x: float,
            second_y: float,
            radius: float,
    ) -> float:
        distance = _norm2(first_x - second_x, first_y - second_y)
        base = max(distance - radius, 0.0) / radius
        return float(_clamp(1.0 - base * base, 0.0, 1.0))


    @_compile(cache=True, inline="always", fastmath=True)
    def _double_tap_feasibility(
            index: int,
            next_index: int,
            delta: Any,
            lazy_jump: Any,
            hit_window_great: float,
    ) -> float:
        if next_index < 0:
            return 0.0
        current_delta = max(delta[index], 1.0)
        next_delta = max(delta[next_index], 1.0)
        delta_difference = abs(next_delta - current_delta)
        speed_ratio = current_delta / max(current_delta, delta_difference)
        window_ratio = min(current_delta / hit_window_great, 1.0)
        window_ratio = window_ratio ** 5
        distance_ratio = _clamp((100.0 - lazy_jump[index]) / 50.0, 0.0, 1.0)
        distance_factor = distance_ratio * distance_ratio
        return float(1.0 - speed_ratio ** (distance_factor * (1.0 - window_ratio)))


    @_compile(cache=True, inline="always", fastmath=True)
    def _speed_value(
            index: int,
            kind: Any,
            delta: Any,
            adjusted_delta: Any,
            lazy_jump: Any,
            hit_window_great: float,
    ) -> float:
        if index == 0 or kind[index] == 2:
            return 0.0
        strain_time = adjusted_delta[index]
        next_index = index + 1
        double_tap = 1.0 - _double_tap_feasibility(
            index,
            next_index,
            delta,
            lazy_jump,
            hit_window_great,
        ) if next_index < adjusted_delta.shape[0] else 1.0
        strain_time /= _clamp(
            (strain_time / hit_window_great) / 0.93,
            0.92,
            1.0,
        )
        speed_bonus = 0.0
        if 60000.0 / (strain_time * 4.0) > 200.0:
            base = (75.0 - strain_time) / 40.0
            speed_bonus = 0.75 * base * base
        speed = (1.0 + speed_bonus) * 1000.0 / strain_time
        speed *= 1.0 / (1.0 - 0.3 ** (adjusted_delta[index] / 1000.0))
        return float(speed * double_tap)


    @_compile(cache=True, inline="always", fastmath=True)
    def _rhythm_effective(ratio: float) -> float:
        fraction = ratio - math.trunc(ratio)
        x = _clamp((fraction - 0.5) / 0.5, -1.0, 1.0)
        distance = 0.5 - abs(x) * 0.5
        smooth = distance * distance * (3.0 - 2.0 * distance)
        return 1.0 + 26.0 * min(0.5, smooth)


    @_compile(cache=True, fastmath=True)
    def _rhythm_value(
            index: int,
            time: Any,
            delta: Any,
            kind: Any,
            min_jump_time: Any,
            last_object_end_delta_time: Any,
            lazy_jump: Any,
            hit_window_great: float,
    ) -> float:
        if index <= 0 or kind[index] == 2:
            return 0.0

        history_time_max = 5000.0
        history_objects_max = 32
        epsilon = hit_window_great * 0.3
        historical_note_count = min(index, history_objects_max)
        rhythm_start = 0
        while (
                rhythm_start < historical_note_count - 2
                and time[index] - time[index - rhythm_start - 1] < history_time_max
        ):
            rhythm_start += 1

        prev_index = index - rhythm_start - 1
        prev_prev_index = prev_index - 1
        if prev_index < 0:
            return 0.0

        max_int = 2147483647
        island_delta = max_int
        island_count = 1
        previous_island_delta = max_int
        previous_island_count = 1
        island_deltas = np.empty(history_objects_max, dtype=np.int64)
        island_counts = np.empty(history_objects_max, dtype=np.int64)
        island_occurrences = np.ones(history_objects_max, dtype=np.int64)
        island_total = 0
        start_difficulty = 0.0
        first_delta_switch = False
        complexity = 0.0

        for history_index in range(rhythm_start, 0, -1):
            current_index = index - history_index
            if kind[current_index] == 2:
                continue

            time_decay = (
                history_time_max - (time[index] - time[current_index])
            ) / history_time_max
            note_decay = (historical_note_count - history_index) / historical_note_count
            historical_decay = min(note_decay, time_decay)
            current_delta = max(delta[current_index], 1e-7)
            previous_delta = max(delta[prev_index], 1e-7)
            difference = abs(previous_delta - current_delta)

            if island_delta == max_int:
                island_delta = int(current_delta)
            ratio = max(previous_delta, current_delta) / min(
                previous_delta, current_delta
            )
            difference_multiplier = _clamp(2.0 - ratio / 8.0, 0.0, 1.0)
            window_penalty = _clamp(
                (difference - epsilon) / epsilon,
                0.0,
                1.0,
            )
            effective = _rhythm_effective(ratio) * window_penalty * difference_multiplier

            if kind[prev_index] == 1:
                lazy_ratio = max(min_jump_time[current_index], current_delta) / min(
                    min_jump_time[current_index], current_delta
                )
                real_ratio = max(last_object_end_delta_time[current_index], current_delta) / min(
                    last_object_end_delta_time[current_index], current_delta
                )
                effective = min(
                    effective,
                    _rhythm_effective(lazy_ratio),
                    _rhythm_effective(real_ratio),
                )

            if difference < epsilon:
                island_count += 1

            if first_delta_switch:
                if difference > epsilon:
                    if kind[current_index] == 1:
                        effective *= 0.5
                    if (
                            island_count > 1
                            and previous_island_count > 1
                            and abs(island_delta - previous_island_delta) < epsilon
                            and island_count % 2 == previous_island_count % 2
                    ):
                        effective *= 0.5
                    if (
                            prev_prev_index >= 0
                            and max(delta[prev_prev_index], 1e-7)
                            > previous_delta + epsilon
                            and previous_delta > current_delta + epsilon
                    ):
                        effective *= 0.125
                    if previous_island_count == island_count:
                        effective *= 0.5
                    if previous_delta > current_delta + epsilon:
                        effective *= 0.65

                    found = False
                    for island_index in range(island_total):
                        if (
                                abs(island_deltas[island_index] - island_delta) < epsilon
                                and island_counts[island_index] == island_count
                        ):
                            if (
                                    abs(previous_island_delta - island_delta) < epsilon
                                    and previous_island_count == island_count
                            ):
                                island_occurrences[island_index] += 1
                            occurrence = island_occurrences[island_index]
                            power = 2.75 / (
                                1.0 + math.exp(0.24 * (58.33 - island_delta))
                            )
                            effective *= min(
                                3.0 / occurrence,
                                (1.0 / occurrence) ** power,
                            )
                            found = True
                            break
                    if not found and island_total < history_objects_max:
                        island_deltas[island_total] = island_delta
                        island_counts[island_total] = island_count
                        island_total += 1

                    previous_feasibility = _double_tap_feasibility(
                        prev_index,
                        current_index,
                        delta,
                        lazy_jump,
                        hit_window_great,
                    )
                    effective *= 1.0 - previous_feasibility * 0.75
                    if island_count > 1:
                        complexity += math.sqrt(max(effective * start_difficulty, 0.0)) * historical_decay
                    else:
                        complexity += 0.7 * historical_decay
                    start_difficulty = effective
                    if previous_delta + epsilon < current_delta:
                        first_delta_switch = False
                    previous_island_delta = island_delta
                    previous_island_count = island_count
                    island_delta = int(current_delta)
                    island_count = 1
            elif previous_delta > current_delta + epsilon:
                first_delta_switch = True
                if kind[current_index] == 1:
                    effective *= 0.6
                if kind[prev_index] == 1:
                    effective *= 0.6
                start_difficulty = effective
                island_delta = int(current_delta)
                island_count = 1

            prev_prev_index = prev_index
            prev_index = current_index

        section_factor = _clamp((island_count - 22.0) / (3.0 - 22.0), 0.0, 1.0)
        return math.sqrt(4.0 + complexity * 0.95 * section_factor) / 2.0


    @_compile(cache=True, inline="always", fastmath=True)
    def _aim_value(
            index: int,
            kind: Any,
            repeats: Any,
            adjusted_delta: Any,
            jump: Any,
            lazy_jump: Any,
            min_jump: Any,
            min_jump_time: Any,
            travel_dist: Any,
            travel_time: Any,
            lazy_travel_dist: Any,
            angle: Any,
            has_angle: Any,
            normalised_vector_angle: Any,
            stacked_x: Any,
            stacked_y: Any,
            object_radius: float,
            small_bonus: float,
            with_slider: bool,
    ) -> Any:
        if index == 0 or kind[index] == 2:
            return 0.0, 0.0, 0.0, 0.0

        travel_distance = lazy_travel_dist[index - 1]
        agility = min(travel_distance + lazy_jump[index], 120.0) / 120.0
        agility *= 1000.0 / adjusted_delta[index]
        agility *= small_bonus ** 1.5
        agility *= 1.0 / (1.0 - 0.2 ** (adjusted_delta[index] / 1000.0))
        if index <= 2 or kind[index - 1] == 2:
            return 0.0, agility, 0.0, 0.0

        current_distance = lazy_jump[index] if with_slider else jump[index]
        current_velocity = current_distance / adjusted_delta[index]
        previous_distance = lazy_jump[index - 1] if with_slider else jump[index - 1]
        previous_velocity = previous_distance / adjusted_delta[index - 1]

        if with_slider and kind[index - 1] == 1:
            current_velocity = max(
                current_velocity,
                (lazy_travel_dist[index - 1] + lazy_jump[index])
                / adjusted_delta[index],
            )

        snap = current_velocity

        if has_angle[index] and has_angle[index - 1]:
            constant_angle_count = 0.0
            lower = max(0, index - 6)
            for previous in range(index - 1, lower - 1, -1):
                if max(adjusted_delta[index], adjusted_delta[previous]) > 1.1 * min(
                    adjusted_delta[index], adjusted_delta[previous]
                ):
                    break
                angle_difference = abs(
                    normalised_vector_angle[index]
                    - normalised_vector_angle[previous]
                )
                constant_angle_count += math.cos(
                    8.0 * min(math.radians(11.25), angle_difference)
                )
            ratio = (
                1.0
                if constant_angle_count == 0.0
                else min(0.5 / constant_angle_count, 1.0)
            )
            vector_repetition = ratio * ratio
            stack_factor = _smootherstep(lazy_jump[index], 0.0, 100.0)
            angle_difference_adjusted = math.cos(
                2.0
                * min(
                    math.radians(45.0),
                    abs(angle[index] - angle[index - 1]) * stack_factor,
                )
            )
            base_nerf = 1.0 - 0.15 * _smoothstep(
                angle[index - 1], math.radians(140.0), math.radians(40.0)
            ) * angle_difference_adjusted
            snap *= (
                base_nerf
                + (1.0 - base_nerf) * vector_repetition * 0.5 * stack_factor
            ) ** 2

            current_angle = angle[index]
            previous_angle = angle[index - 1]
            velocity_influence = min(current_velocity, previous_velocity)
            current_angle = angle[index]
            acute = 0.0
            if max(adjusted_delta[index], adjusted_delta[index - 1]) < 1.25 * min(
                    adjusted_delta[index], adjusted_delta[index - 1]
            ):
                acute = _smoothstep(
                    current_angle, math.radians(140.0), math.radians(40.0)
                )
                previous_acute = _smoothstep(
                    previous_angle, math.radians(140.0), math.radians(40.0)
                )
                acute *= 0.08 + 0.92 * (1.0 - min(acute, previous_acute ** 3))
                acute *= velocity_influence * _smootherstep(
                    60000.0 / (adjusted_delta[index] * 2.0), 300.0, 400.0
                ) * _smootherstep(current_distance, 0.0, 200.0)
            wide = _smoothstep(
                current_angle, math.radians(40.0), math.radians(140.0)
            )
            previous_wide = _smoothstep(
                previous_angle, math.radians(40.0), math.radians(140.0)
            )
            wide *= 0.25 + 0.75 * (1.0 - min(wide, previous_wide ** 3))
            wide *= min(
                max(
                    current_distance,
                    lazy_travel_dist[index - 1] + lazy_jump[index]
                    if with_slider and kind[index - 1] == 1
                    else current_distance,
                ) / adjusted_delta[index] ** 1.45,
                previous_distance / adjusted_delta[index - 1] ** 1.45,
            )
            if index >= 3:
                distance = _norm2(
                    stacked_x[index - 3] - stacked_x[index - 1],
                    stacked_y[index - 3] - stacked_y[index - 1],
                )
                if distance < 1.0:
                    wide *= 1.0 - 0.55 * (1.0 - distance)
            snap += max(acute * 2.41, wide * 9.67)

            wiggle = (
                velocity_influence
                * _smootherstep(current_distance, 50.0, 100.0)
                * _clamp((current_distance - 300.0) / (100.0 - 300.0), 0.0, 1.0) ** 1.8
                * _smootherstep(current_angle, math.radians(110.0), math.radians(60.0))
                * _smootherstep(previous_distance, 50.0, 100.0)
                * _clamp((previous_distance - 300.0) / (100.0 - 300.0), 0.0, 1.0) ** 1.8
                * _smootherstep(previous_angle, math.radians(110.0), math.radians(60.0))
            )
            snap += wiggle * 1.02

        if max(previous_velocity, current_velocity) > 0.0:
            if with_slider:
                current_velocity = current_distance / adjusted_delta[index]
            velocity_max = max(previous_velocity, current_velocity)
            ratio = (
                abs(previous_velocity - current_velocity) / velocity_max
                if velocity_max > 0.0
                else 0.0
            )
            overlap = min(
                125.0 / min(adjusted_delta[index], adjusted_delta[index - 1]),
                abs(previous_velocity - current_velocity),
            )
            base = min(adjusted_delta[index], adjusted_delta[index - 1]) / max(
                adjusted_delta[index], adjusted_delta[index - 1]
            )
            snap += overlap * _smoothstep(ratio, 0.0, 1.0) * base * base * 0.9

        if with_slider and kind[index] == 1:
            slider_bonus = travel_dist[index] / max(travel_time[index], _MIN_DELTA)
            snap += (
                slider_bonus if slider_bonus < 1.0 else slider_bonus ** 0.75
            ) * 1.5

        snap *= small_bonus
        snap *= 1.0 / (
            1.0 - 0.03 ** (adjusted_delta[index] / 1000.0) ** 0.65
        )

        flow = current_velocity * math.sqrt(small_bonus)
        delta_difference = (
            max(adjusted_delta[index], adjusted_delta[index - 1])
            - min(adjusted_delta[index], adjusted_delta[index - 1])
        ) / 50.0
        flow *= 1.0 + min(0.25, delta_difference ** 4)
        if has_angle[index] and has_angle[index - 1]:
            angular_velocity = (
                math.sin(abs(angle[index] - angle[index - 1]) / 2.0) * 180.0
                / (adjusted_delta[index] * 0.1)
            )
            flow *= 0.8 + math.sqrt(max(angular_velocity / 270.0, 0.0))
        overlap_weight = 1.0
        if index > 2:
            o1 = _flow_overlap(
                stacked_x[index],
                stacked_y[index],
                stacked_x[index - 1],
                stacked_y[index - 1],
                object_radius,
            )
            o2 = _flow_overlap(
                stacked_x[index],
                stacked_y[index],
                stacked_x[index - 2],
                stacked_y[index - 2],
                object_radius,
            )
            o3 = _flow_overlap(
                stacked_x[index - 1],
                stacked_y[index - 1],
                stacked_x[index - 2],
                stacked_y[index - 2],
                object_radius,
            )
            overlap_weight = 1.0 - o1 * o2 * o3
        if has_angle[index]:
            flow += current_velocity * _smoothstep(
                angle[index], math.radians(140.0), math.radians(40.0)
            ) * overlap_weight
        if max(previous_velocity, current_velocity) != 0.0:
            if with_slider:
                current_velocity = current_distance / adjusted_delta[index]
            velocity_max = max(previous_velocity, current_velocity)
            ratio = (
                abs(previous_velocity - current_velocity) / velocity_max
                if velocity_max > 0.0
                else 0.0
            )
            overlap = min(
                125.0 / min(adjusted_delta[index], adjusted_delta[index - 1]),
                abs(previous_velocity - current_velocity),
            )
            flow += overlap * _smoothstep(ratio, 0.0, 1.0) * overlap_weight * 0.52
        if with_slider and kind[index] == 1:
            flow += travel_dist[index] / max(travel_time[index], _MIN_DELTA)
        flow = flow ** 1.45 * _smootherstep(current_distance, 0.0, 50.0)

        scaled_snap = snap * 70.9
        scaled_agility = agility * 2.35
        scaled_flow = flow * 242.0
        combined = (scaled_snap ** 1.2 + scaled_agility ** 1.2) ** (1.0 / 1.2)
        ratio = scaled_flow / combined if combined > 0.0 else 0.0
        if ratio <= 0.0:
            snap_probability = 0.0
        else:
            snap_probability = ratio ** 7.27 / (1.0 + ratio ** 7.27)
        combined = (
            combined * snap_probability
            + scaled_flow * (1.0 - snap_probability)
        ) * 1.12
        return snap, agility, flow, combined


    @_compile(cache=True, fastmath=True)
    def _calculate_kernel(
            time: Any,
            kind: Any,
            repeats: Any,
            delta: Any,
            adjusted_delta: Any,
            jump: Any,
            lazy_jump: Any,
            min_jump: Any,
            min_jump_time: Any,
            travel_dist: Any,
            travel_time: Any,
            lazy_travel_dist: Any,
            last_object_end_delta_time: Any,
            angle: Any,
            has_angle: Any,
            normalised_vector_angle: Any,
            stacked_x: Any,
            stacked_y: Any,
            object_radius: float,
            clock_rate: float,
            small_bonus: float,
            overall_difficulty: float,
            hit_window_great: float,
    ) -> Any:
        count = time.shape[0]
        aim_values = np.zeros(count, dtype=np.float64)
        aim_no_slider_values = np.zeros(count, dtype=np.float64)
        snap_values = np.zeros(count, dtype=np.float64)
        agility_values = np.zeros(count, dtype=np.float64)
        flow_values = np.zeros(count, dtype=np.float64)
        speed_values = np.zeros(count, dtype=np.float64)
        rhythm_values = np.zeros(count, dtype=np.float64)

        aim_current = 0.0
        aim_no_slider_current = 0.0
        snap_current = 0.0
        agility_current = 0.0
        flow_current = 0.0

        speed_current = 0.0

        for index in range(count):
            snap_raw, agility_raw, flow_raw, aim_raw = _aim_value(
                index,
                kind,
                repeats,
                adjusted_delta,
                jump,
                lazy_jump,
                min_jump,
                min_jump_time,
                travel_dist,
                travel_time,
                lazy_travel_dist,
                angle,
                has_angle,
                normalised_vector_angle,
                stacked_x,
                stacked_y,
                object_radius,
                small_bonus,
                True,
            )
            _, _, _, aim_no_slider_raw = _aim_value(
                index,
                kind,
                repeats,
                adjusted_delta,
                jump,
                lazy_jump,
                min_jump,
                min_jump_time,
                travel_dist,
                travel_time,
                lazy_travel_dist,
                angle,
                has_angle,
                normalised_vector_angle,
                stacked_x,
                stacked_y,
                object_radius,
                small_bonus,
                False,
            )
            aim_raw *= 0.985 + max(overall_difficulty, 0.0) ** 2 / 4000.0
            aim_no_slider_raw *= 0.985 + max(overall_difficulty, 0.0) ** 2 / 4000.0
            aim_current *= _decay(0.2, adjusted_delta[index])
            aim_no_slider_current *= _decay(0.2, adjusted_delta[index])
            aim_current += aim_raw * (1.0 - _decay(0.2, adjusted_delta[index]))
            aim_no_slider_current += aim_no_slider_raw * (
                1.0 - _decay(0.2, adjusted_delta[index])
            )
            snap_current *= _decay(0.2, adjusted_delta[index])
            agility_current *= _decay(0.2, adjusted_delta[index])
            flow_current *= _decay(0.2, adjusted_delta[index])
            snap_current += snap_raw * (1.0 - _decay(0.2, adjusted_delta[index]))
            agility_current += agility_raw * (1.0 - _decay(0.2, adjusted_delta[index]))
            flow_current += flow_raw * (1.0 - _decay(0.2, adjusted_delta[index]))
            aim_values[index] = aim_current
            aim_no_slider_values[index] = aim_no_slider_current
            snap_values[index] = snap_current
            agility_values[index] = agility_current
            flow_values[index] = flow_current

            speed_raw = _speed_value(
                index,
                kind,
                delta,
                adjusted_delta,
                lazy_jump,
                hit_window_great,
            )
            speed_current *= _decay(0.3, adjusted_delta[index])
            speed_current += speed_raw * (1.0 - _decay(0.3, adjusted_delta[index])) * 1.16
            rhythm = _rhythm_value(
                index,
                time,
                delta,
                kind,
                min_jump_time,
                last_object_end_delta_time,
                lazy_jump,
                hit_window_great,
            )
            rhythm_values[index] = rhythm
            speed_values[index] = speed_current * rhythm

        aim_difficulty = _variable_peak_value(
            aim_values[1:], time[1:], clock_rate
        )
        aim_no_slider_difficulty = _variable_peak_value(
            aim_no_slider_values[1:], time[1:], clock_rate
        )
        snap_difficulty = _peak_value(snap_values, time)
        agility_difficulty = _peak_value(agility_values, time)
        flow_difficulty = _peak_value(flow_values, time)
        speed_difficulty = _harmonic(speed_values, 20.0)
        rhythm_difficulty = _harmonic(rhythm_values, 20.0)
        return (
            aim_difficulty,
            aim_no_slider_difficulty,
            speed_difficulty,
            snap_difficulty,
            agility_difficulty,
            flow_difficulty,
            rhythm_difficulty,
        )

def _calculate_from_packed(
        packed: PackedOsuMap,
        *,
        adjusted: AdjustedBeatmapAttributes,
        stack_leniency: float,
        cs: float,
) -> tuple[float, float, float, float, float, float, float]:
    _require_numpy()
    scale = (1.0 - 0.7 * (cs - 5.0) / 5.0) / 2.0 * 1.00041
    radius = 64.0 * scale
    great = float(adjusted.hit_windows.od_great or 20.0)
    preprocessed = _preprocess(
        packed.time,
        packed.end_time,
        packed.x,
        packed.y,
        packed.end_x,
        packed.end_y,
        packed.lazy_end_x,
        packed.lazy_end_y,
        packed.last_nested_x,
        packed.last_nested_y,
        packed.kind,
        packed.repeats,
        packed.slider_dist,
        packed.slider_duration,
        packed.stack_height,
        adjusted.clock_rate,
        radius,
        scale,
    )
    result = _calculate_kernel(
        packed.time,
        packed.kind,
        packed.repeats,
        preprocessed[0],
        preprocessed[1],
        preprocessed[2],
        preprocessed[3],
        preprocessed[4],
        preprocessed[5],
        preprocessed[6],
        preprocessed[7],
        preprocessed[8],
        preprocessed[9],
        preprocessed[10],
        preprocessed[11],
        preprocessed[12],
        preprocessed[13],
        preprocessed[14],
        radius,
        adjusted.clock_rate,
        preprocessed[15],
        (79.5 - 2.0 * great / 2.0) / 6.0,
        great,
    )
    return (
        float(result[0]),
        float(result[1]),
        float(result[2]),
        float(result[3]),
        float(result[4]),
        float(result[5]),
        float(result[6]),
    )


def _factors_from_packed(packed: PackedOsuMap, adjusted: AdjustedBeatmapAttributes) -> StructuralFactors:
    result = _calculate_from_packed(
        packed,
        adjusted=adjusted,
        stack_leniency=0.7,
        cs=adjusted.cs,
    )
    aim_rating = 0.02275 * max(result[0], 0.0) ** 0.63
    speed_rating = math.sqrt(max(result[2], 0.0)) * 0.0675
    performance = (
        (4.0 * aim_rating ** 3) ** 1.1
        + (4.0 * speed_rating ** 3) ** 1.1
    ) ** (1.0 / 1.1)
    return StructuralFactors(
        stars=(performance * 1.12) ** (1.0 / 3.0),
        aim=aim_rating,
        speed=speed_rating,
        slider=(max(result[1], 0.0) / max(result[0], 1e-12)) ** 0.63
        if result[0] > 0.0
        else 1.0,
        snap=result[3],
        agility=result[4],
        flow=result[5],
        tap=result[2],
        rhythm=result[6],
        object_count=int(packed.time.shape[0]),
        objects_pruned=packed.truncated,
    )


def _attributes_from_packed(
        packed: PackedOsuMap,
        *,
        adjusted: AdjustedBeatmapAttributes,
        stack_leniency: float,
) -> OsuDifficultyAttributes:
    aim_difficulty, aim_no_slider, speed_difficulty, *_ = (
        _calculate_from_packed(
            packed,
            adjusted=adjusted,
            stack_leniency=stack_leniency,
            cs=adjusted.cs,
        )
    )

    aim_rating = 0.02275 * max(aim_difficulty, 0.0) ** 0.63
    speed_rating = math.sqrt(max(speed_difficulty, 0.0)) * 0.0675
    reading_rating = 0.0
    slider_factor = (
        max(aim_no_slider, 0.0) ** 0.63 / max(aim_difficulty, 1e-12) ** 0.63
        if aim_difficulty > 0.0
        else 1.0
    )
    base_aim = 4.0 * aim_rating ** 3
    base_speed = 4.0 * speed_rating ** 3
    base_reading = 4.0 * reading_rating ** 3
    performance = (
        base_aim ** 1.1 + base_speed ** 1.1 + base_reading ** 1.1
    ) ** (1.0 / 1.1)
    stars = (performance * 1.12) ** (1.0 / 3.0)

    attrs = OsuDifficultyAttributes(
        aim=aim_rating,
        speed=speed_rating,
        reading=reading_rating,
        slider_factor=slider_factor,
        ar=adjusted.ar,
        hp=float(adjusted.hp),
        great_hit_window=float(adjusted.hit_windows.od_great or 0.0),
        ok_hit_window=float(adjusted.hit_windows.od_ok or 0.0),
        meh_hit_window=float(adjusted.hit_windows.od_meh or 0.0),
        n_circles=packed.n_circles,
        n_sliders=packed.n_sliders,
        n_spinners=packed.n_spinners,
        n_large_ticks=packed.n_large_ticks,
        stars=stars,
        max_combo=packed.max_combo,
        objects_pruned=packed.truncated,
        od=adjusted.od,
        aim_difficult_slider_count=0.0,
        speed_note_count=0.0,
        aim_difficult_strain_count=0.0,
        speed_difficult_strain_count=0.0,
        reading_difficult_note_count=0.0,
    )
    attrs.aim_top_weighted_slider_factor = slider_factor
    attrs.speed_top_weighted_slider_factor = 0.0
    return attrs


def calculate_fast(
        pm: PerformanceBeatmap,
        mods: PerformanceMods,
        *,
        lazer: bool = True,
        ar_override: float | tuple[float, bool] | None = None,
        cs_override: float | tuple[float, bool] | None = None,
        hp_override: float | tuple[float, bool] | None = None,
        od_override: float | tuple[float, bool] | None = None,
        max_objects: int = MAX_OBJECTS,
        **_: Any,
) -> OsuDifficultyAttributes:
    """Calculate approximate osu! difficulty with packed arrays and Numba."""
    if pm.mode != GameMode.OSU:
        raise NotImplementedError("the fast calculator only supports osu!standard")
    if getattr(mods, "reflection", Reflection.NONE) != Reflection.NONE:
        raise NotImplementedError("the fast calculator does not support reflection")

    adjusted = AdjustedBeatmapAttributes.create(
        base_cs=pm.base_cs,
        base_ar=pm.base_ar,
        base_od=pm.base_od,
        base_hp=pm.base_hp,
        mode=GameMode.OSU,
        mods=mods,
        ar_override=as_override(ar_override),
        cs_override=as_override(cs_override),
        hp_override=as_override(hp_override),
        od_override=as_override(od_override),
    )
    packed = _pack_map(
        pm,
        max_objects=max_objects,
        radius=64.0 * (1.0 - 0.7 * (adjusted.cs - 5.0) / 5.0) / 2.0 * 1.00041,
    )
    return _attributes_from_packed(
        packed,
        adjusted=adjusted,
        stack_leniency=float(getattr(pm, "stack_leniency", 0.7)),
    )


def calculate_fast_factors(
        pm: PerformanceBeatmap,
        mods: PerformanceMods,
        *,
        ar_override: float | tuple[float, bool] | None = None,
        cs_override: float | tuple[float, bool] | None = None,
        hp_override: float | tuple[float, bool] | None = None,
        od_override: float | tuple[float, bool] | None = None,
        max_objects: int = MAX_OBJECTS,
        **_: Any,
) -> StructuralFactors:
    """Calculate the five independent structural factors for one prepared map."""
    if pm.mode != GameMode.OSU:
        raise NotImplementedError("the fast calculator only supports osu!standard")
    if getattr(mods, "reflection", Reflection.NONE) != Reflection.NONE:
        raise NotImplementedError("the fast calculator does not support reflection")

    adjusted = AdjustedBeatmapAttributes.create(
        base_cs=pm.base_cs,
        base_ar=pm.base_ar,
        base_od=pm.base_od,
        base_hp=pm.base_hp,
        mode=GameMode.OSU,
        mods=mods,
        ar_override=as_override(ar_override),
        cs_override=as_override(cs_override),
        hp_override=as_override(hp_override),
        od_override=as_override(od_override),
    )
    packed = _pack_map(
        pm,
        max_objects=max_objects,
        radius=64.0 * (1.0 - 0.7 * (adjusted.cs - 5.0) / 5.0) / 2.0 * 1.00041,
    )
    return _factors_from_packed(packed, adjusted)


def calculate_fast_bytes(
        data: bytes,
        mods: PerformanceMods,
        *,
        ar_override: float | tuple[float, bool] | None = None,
        cs_override: float | tuple[float, bool] | None = None,
        hp_override: float | tuple[float, bool] | None = None,
        od_override: float | tuple[float, bool] | None = None,
        max_objects: int = MAX_OBJECTS,
        **_: Any,
) -> OsuDifficultyAttributes:
    """Parse only calculation-relevant sections and calculate packed difficulty."""
    beatmap = _parse_fast_bytes(data, max_objects, cs_override)
    if beatmap.mode != int(GameMode.OSU):
        raise NotImplementedError("the fast calculator only supports osu!standard")
    if getattr(mods, "reflection", Reflection.NONE) != Reflection.NONE:
        raise NotImplementedError("the fast calculator does not support reflection")

    adjusted = AdjustedBeatmapAttributes.create(
        base_cs=beatmap.base_cs,
        base_ar=beatmap.base_ar,
        base_od=beatmap.base_od,
        base_hp=beatmap.base_hp,
        mode=GameMode.OSU,
        mods=mods,
        ar_override=as_override(ar_override),
        cs_override=as_override(cs_override),
        hp_override=as_override(hp_override),
        od_override=as_override(od_override),
    )
    return _attributes_from_packed(
        beatmap.packed,
        adjusted=adjusted,
        stack_leniency=0.7,
    )


def calculate_fast_factors_bytes(
        data: bytes,
        mods: PerformanceMods,
        *,
        ar_override: float | tuple[float, bool] | None = None,
        cs_override: float | tuple[float, bool] | None = None,
        hp_override: float | tuple[float, bool] | None = None,
        od_override: float | tuple[float, bool] | None = None,
        max_objects: int = MAX_OBJECTS,
        **_: Any,
) -> StructuralFactors:
    """Parse and calculate the five independent structural factors for one map."""
    beatmap = _parse_fast_bytes(data, max_objects, cs_override)
    if beatmap.mode != int(GameMode.OSU):
        raise NotImplementedError("the fast calculator only supports osu!standard")
    if getattr(mods, "reflection", Reflection.NONE) != Reflection.NONE:
        raise NotImplementedError("the fast calculator does not support reflection")

    adjusted = AdjustedBeatmapAttributes.create(
        base_cs=beatmap.base_cs,
        base_ar=beatmap.base_ar,
        base_od=beatmap.base_od,
        base_hp=beatmap.base_hp,
        mode=GameMode.OSU,
        mods=mods,
        ar_override=as_override(ar_override),
        cs_override=as_override(cs_override),
        hp_override=as_override(hp_override),
        od_override=as_override(od_override),
    )
    return _factors_from_packed(beatmap.packed, adjusted)


class FastDifficulty:
    """Small fixed-settings builder for the packed calculator."""

    __slots__ = ("_mods", "_ar", "_cs", "_hp", "_od", "_max_objects")

    def __init__(self, max_objects: int = MAX_OBJECTS) -> None:
        self._mods: PerformanceMods | None = None
        self._ar: tuple[float, bool] | None = None
        self._cs: tuple[float, bool] | None = None
        self._hp: tuple[float, bool] | None = None
        self._od: tuple[float, bool] | None = None
        self._max_objects = max_objects

    def mods(self, mods: Any) -> FastDifficulty:
        self._mods = (
            mods if isinstance(mods, PerformanceMods) else PerformanceMods.from_mods(mods)
        )
        return self

    def ar(self, value: float, fixed: bool = False) -> FastDifficulty:
        self._ar = (float(value), bool(fixed))
        return self

    def cs(self, value: float, fixed: bool = False) -> FastDifficulty:
        self._cs = (float(value), bool(fixed))
        return self

    def hp(self, value: float, fixed: bool = False) -> FastDifficulty:
        self._hp = (float(value), bool(fixed))
        return self

    def od(self, value: float, fixed: bool = False) -> FastDifficulty:
        self._od = (float(value), bool(fixed))
        return self

    def calculate(self, beatmap: PerformanceBeatmap) -> OsuDifficultyAttributes:
        mods = self._mods or PerformanceMods.from_mods(0)
        pm = getattr(beatmap, "inner", beatmap)
        return calculate_fast(
            pm,
            mods,
            ar_override=self._ar,
            cs_override=self._cs,
            hp_override=self._hp,
            od_override=self._od,
            max_objects=self._max_objects,
        )

    def calculate_bytes(self, data: bytes) -> OsuDifficultyAttributes:
        mods = self._mods or PerformanceMods.from_mods(0)
        return calculate_fast_bytes(
            data,
            mods,
            ar_override=self._ar,
            cs_override=self._cs,
            hp_override=self._hp,
            od_override=self._od,
            max_objects=self._max_objects,
        )

    def calculate_factors(self, beatmap: PerformanceBeatmap) -> StructuralFactors:
        mods = self._mods or PerformanceMods.from_mods(0)
        pm = getattr(beatmap, "inner", beatmap)
        return calculate_fast_factors(
            pm,
            mods,
            ar_override=self._ar,
            cs_override=self._cs,
            hp_override=self._hp,
            od_override=self._od,
            max_objects=self._max_objects,
        )

    def calculate_factors_bytes(self, data: bytes) -> StructuralFactors:
        mods = self._mods or PerformanceMods.from_mods(0)
        return calculate_fast_factors_bytes(
            data,
            mods,
            ar_override=self._ar,
            cs_override=self._cs,
            hp_override=self._hp,
            od_override=self._od,
            max_objects=self._max_objects,
        )


StructuralCalculator = FastDifficulty
