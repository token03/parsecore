from __future__ import annotations

from pathlib import Path

import pytest

from parsecore.Beatmap.beatmap import Beatmap
from parsecore.Performance.api import Beatmap as PreparedBeatmap
from parsecore.Performance.api import Difficulty
from parsecore.Performance.rulesets.osu.fast import FastDifficulty, _parse_fast_bytes


def _calculator() -> FastDifficulty:
    pytest.importorskip("numpy")
    pytest.importorskip("numba")
    return (
        FastDifficulty()
        .mods(0)
        .ar(10.0, fixed=True)
        .cs(4.0, fixed=True)
        .hp(10.0, fixed=True)
        .od(10.0, fixed=True)
    )


def test_fast_calculator_is_close_to_reference() -> None:
    path = Path(__file__).parent / "data" / "162.osu"
    data = path.read_bytes()
    reference_map = PreparedBeatmap.from_user_beatmap(Beatmap.from_bytes(data))
    reference = (
        Difficulty()
        .mods(0)
        .ar(10.0, fixed=True)
        .cs(4.0, fixed=True)
        .hp(10.0, fixed=True)
        .od(10.0, fixed=True)
        .calculate(reference_map)
    )
    actual = _calculator().calculate_bytes(data)

    assert actual.stars == pytest.approx(reference.stars, rel=0.3)
    assert actual.aim == pytest.approx(reference.aim, rel=0.3)


def test_fast_calculator_handles_length_adjusted_sliders() -> None:
    path = Path(__file__).parent / "data" / "4645077.osu"
    data = path.read_bytes()
    reference_map = PreparedBeatmap.from_user_beatmap(Beatmap.from_bytes(data))
    reference = (
        Difficulty()
        .mods(0)
        .ar(10.0, fixed=True)
        .cs(4.0, fixed=True)
        .hp(10.0, fixed=True)
        .od(10.0, fixed=True)
        .calculate(reference_map)
    )
    actual = _calculator().calculate_factors_bytes(data)

    assert actual.stars == pytest.approx(reference.stars, rel=0.02)
    assert actual.aim == pytest.approx(reference.aim, rel=0.02)
    assert actual.speed == pytest.approx(reference.speed, rel=0.02)
    assert actual.slider == pytest.approx(reference.slider_factor, abs=0.01)


def test_fast_calculator_returns_five_independent_factors() -> None:
    path = Path(__file__).parent / "data" / "162.osu"
    data = path.read_bytes()
    actual = _calculator().calculate_factors_bytes(data)

    assert actual.object_count > 0
    assert actual.stars > 0.0
    assert actual.aim > 0.0
    assert actual.speed > 0.0
    assert actual.snap > 0.0
    assert actual.agility > 0.0
    assert actual.flow > 0.0
    assert actual.tap > 0.0
    assert actual.rhythm > 0.0


def test_fast_parser_prunes_after_4096_objects() -> None:
    calculator = _calculator()
    lines = [
        b"osu file format v14",
        b"[General]",
        b"Mode:0",
        b"[Difficulty]",
        b"HPDrainRate:10",
        b"CircleSize:4",
        b"OverallDifficulty:10",
        b"ApproachRate:10",
        b"SliderMultiplier:1.4",
        b"SliderTickRate:1",
        b"[TimingPoints]",
        b"0,500,4,1,0,100,1,0",
        b"[HitObjects]",
    ]
    lines.extend(
        f"256,192,{index * 100},1,0".encode("ascii")
        for index in range(4097)
    )
    data = b"\n".join(lines)

    parsed = _parse_fast_bytes(data, 4096)
    attrs = calculator.calculate_bytes(data)

    assert parsed.packed.truncated
    assert parsed.packed.time.shape == (4096,)
    assert attrs.n_objects() == 4096
    assert attrs.objects_pruned
    assert sum(
        array.nbytes
        for array in (
            parsed.packed.time,
            parsed.packed.end_time,
            parsed.packed.x,
            parsed.packed.y,
            parsed.packed.end_x,
            parsed.packed.end_y,
            parsed.packed.lazy_end_x,
            parsed.packed.lazy_end_y,
            parsed.packed.last_nested_x,
            parsed.packed.last_nested_y,
            parsed.packed.kind,
            parsed.packed.repeats,
            parsed.packed.slider_dist,
            parsed.packed.slider_duration,
            parsed.packed.stack_height,
        )
    ) < 300_000


def test_fast_parser_rejects_oversized_slider_distance() -> None:
    data = b"\n".join([
        b"osu file format v14",
        b"[General]",
        b"Mode:0",
        b"[Difficulty]",
        b"SliderMultiplier:1.4",
        b"[TimingPoints]",
        b"0,500,4,1,0,100,1,0",
        b"[HitObjects]",
        b"256,192,0,2,0,L|300:192,1,1e400",
    ])

    with pytest.raises(ValueError, match="slider distance"):
        _calculator().calculate_factors_bytes(data)
