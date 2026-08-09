from __future__ import annotations

from pathlib import Path

import pytest

from parsecore.Beatmap.beatmap import Beatmap
from parsecore.Beatmap.section.enums import GameMode
from parsecore.Beatmap.section.hit_objects.hit_objects import convert_path_str
from parsecore.Beatmap.section.hit_objects.slider import Curve
from parsecore.Beatmap.utils import Pos
from parsecore.Performance.api import Beatmap as PreparedBeatmap
from parsecore.Performance.api import Difficulty
from parsecore.Performance.rulesets.osu import fast
from parsecore.Performance.rulesets.osu.fast import (
    FastDifficulty,
    _append_raw_slider_path,
    _compiled_slider_summaries,
    _parse_fast_bytes,
    _slider_summary,
)


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


@pytest.mark.parametrize(
    ("path", "distance", "repeats", "velocity", "tick_distance"),
    [
        ("L|356:192|356:292", 250.0, 2, 0.28, 28.0),
        ("P|306:142|356:192", 157.0, 0, 0.28, 28.0),
        ("B|306:92|406:292|456:192", 260.0, 1, 0.28, 28.0),
        ("L|356:192", 100.0, 0, 0.28, 90.0),
    ],
)
def test_compiled_slider_summary_matches_reference(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    distance: float,
    repeats: int,
    velocity: float,
    tick_distance: float,
) -> None:
    np = pytest.importorskip("numpy")
    pytest.importorskip("numba")
    points = convert_path_str(path, Pos(256.0, 192.0))
    reference = _slider_summary(
        Curve(GameMode.Osu, points, distance),
        start_time=1000.0,
        repeat_count=repeats,
        velocity=velocity,
        tick_distance=tick_distance,
        radius=36.48,
    )

    def fail_fallback(*args: object, **kwargs: object) -> None:
        raise AssertionError("unexpected Python slider fallback")

    monkeypatch.setattr(fast, "_slider_summary", fail_fallback)
    actual = _compiled_slider_summaries(
        [points],
        np.asarray([1000.0]),
        np.asarray([1], dtype=np.uint8),
        np.asarray([repeats], dtype=np.int16),
        np.asarray([distance]),
        np.asarray([velocity]),
        np.asarray([tick_distance]),
        36.48,
    )[0]

    assert actual == pytest.approx(reference, abs=1e-4)


@pytest.mark.parametrize("version", [5.0, 6.0])
def test_stack_heights_positive_circle_chain(version: float) -> None:
    np = pytest.importorskip("numpy")
    pytest.importorskip("numba")

    actual = fast._stack_heights(
        np.asarray([0.0, 100.0, 200.0]),
        np.asarray([0.0, 100.0, 200.0]),
        np.asarray([64.0, 64.0, 64.0]),
        np.asarray([64.0, 64.0, 64.0]),
        np.asarray([64.0, 64.0, 64.0]),
        np.asarray([64.0, 64.0, 64.0]),
        np.asarray([0, 0, 0], dtype=np.uint8),
        315.0,
        version,
    )

    assert actual.tolist() == [2, 1, 0]


@pytest.mark.parametrize("version", [5.0, 6.0])
def test_stack_heights_slider_tail_negative_correction(version: float) -> None:
    np = pytest.importorskip("numpy")
    pytest.importorskip("numba")

    actual = fast._stack_heights(
        np.asarray([0.0, 100.0, 200.0]),
        np.asarray([300.0, 100.0, 200.0]),
        np.asarray([0.0, 100.0, 100.0]),
        np.asarray([0.0, 0.0, 0.0]),
        np.asarray([100.0, 100.0, 100.0]),
        np.asarray([0.0, 0.0, 0.0]),
        np.asarray([1, 0, 0], dtype=np.uint8),
        315.0,
        version,
    )

    assert actual.tolist() == [0, -1, -2]


def test_modern_stack_heights_slider_start_chain_and_spinner() -> None:
    np = pytest.importorskip("numpy")
    pytest.importorskip("numba")

    slider_chain = fast._stack_heights(
        np.asarray([0.0, 100.0, 200.0]),
        np.asarray([50.0, 150.0, 250.0]),
        np.asarray([32.0, 32.0, 32.0]),
        np.asarray([32.0, 32.0, 32.0]),
        np.asarray([32.0, 32.0, 32.0]),
        np.asarray([32.0, 32.0, 32.0]),
        np.asarray([1, 1, 1], dtype=np.uint8),
        315.0,
        6.0,
    )
    with_spinner = fast._stack_heights(
        np.asarray([0.0, 100.0, 200.0]),
        np.asarray([0.0, 150.0, 200.0]),
        np.asarray([32.0, 32.0, 32.0]),
        np.asarray([32.0, 32.0, 32.0]),
        np.asarray([32.0, 32.0, 32.0]),
        np.asarray([32.0, 32.0, 32.0]),
        np.asarray([0, 2, 0], dtype=np.uint8),
        315.0,
        6.0,
    )

    assert slider_chain.tolist() == [2, 1, 0]
    assert with_spinner.tolist() == [1, 0, 0]


def test_modern_circle_stacking_preserves_fractional_times() -> None:
    np = pytest.importorskip("numpy")
    pytest.importorskip("numba")

    actual = fast._stack_heights(
        np.asarray([685.1, 1000.9]),
        np.asarray([685.1, 1000.9]),
        np.asarray([32.0, 32.0]),
        np.asarray([32.0, 32.0]),
        np.asarray([32.0, 32.0]),
        np.asarray([32.0, 32.0]),
        np.asarray([0, 0], dtype=np.uint8),
        315.0,
        6.0,
    )

    assert actual.tolist() == [0, 0]


def test_modern_odd_repeat_stacking_uses_generated_tail() -> None:
    data = b"\n".join([
        b"osu file format v14",
        b"[General]",
        b"Mode:0",
        b"StackLeniency:0.7",
        b"[Difficulty]",
        b"ApproachRate:10",
        b"CircleSize:4",
        b"SliderMultiplier:1.4",
        b"SliderTickRate:1",
        b"[TimingPoints]",
        b"0,500,4,1,0,100,1,0",
        b"[HitObjects]",
        b"256,192,0,2,0,L|356:192,2,100",
        b"356,192,800,1,0",
    ])

    direct = _parse_fast_bytes(data, 32).packed
    prepared = PreparedBeatmap.from_user_beatmap(Beatmap.from_bytes(data))
    prepared_inner = getattr(prepared, "inner", prepared)
    packed = fast._pack_map(
        prepared_inner,
        max_objects=32,
        radius=36.48,
        stack_threshold=315.0,
    )

    assert direct.end_x.tolist() == pytest.approx([256.0, 356.0])
    assert direct.stack_height.tolist() == [0, 0]
    assert packed.end_x.tolist() == pytest.approx([256.0, 356.0])
    assert packed.stack_height.tolist() == [0, 0]


def test_fast_parser_batches_common_sliders(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("numpy")
    pytest.importorskip("numba")
    calls = 0
    kernel = fast._slider_summary_kernel

    def counted_kernel(*args: object) -> object:
        nonlocal calls
        calls += 1
        return kernel(*args)

    def fail_fallback(*args: object, **kwargs: object) -> None:
        raise AssertionError("unexpected Python slider fallback")

    monkeypatch.setattr(fast, "_slider_summary_kernel", counted_kernel)
    monkeypatch.setattr(fast, "_slider_summary", fail_fallback)
    monkeypatch.setattr(fast, "convert_path_str", fail_fallback)
    data = b"\n".join([
        b"osu file format v14",
        b"[General]",
        b"Mode:0",
        b"[Difficulty]",
        b"CircleSize:4",
        b"SliderMultiplier:1.4",
        b"SliderTickRate:5",
        b"[TimingPoints]",
        b"0,500,4,1,0,100,1,0",
        b"[HitObjects]",
        b"256,192,0,2,0,L|356:192|356:292,3,250",
        b"256,192,3000,2,0,P|306:142|356:192,1,157",
        b"256,192,4000,2,0,B|306:92|406:292|456:192,2,260",
        b"256,192,5000,2,0,B|306:92|356:192|L|406:192|406:292,1,260",
        b"256,192,6000,2,0,B|306:92|356:192|356:192|406:292,1,220",
    ])

    packed = _parse_fast_bytes(data, 32).packed

    assert calls == 1
    assert packed.n_sliders == 5
    assert packed.max_combo > 5


@pytest.mark.parametrize(
    "path",
    [
        "B|306:92|356:192|L|406:192|406:292",
        "B|306:92|356:192|356:192|406:292",
        "L|306:192|306:192|406:292",
        "P|306:192|356:192",
        "P|306:92|356:192|406:292",
    ],
)
def test_raw_slider_path_matches_object_parser(path: str) -> None:
    expected = convert_path_str(path, Pos(256.0, 192.0))
    control_x: list[float] = []
    control_y: list[float] = []
    control_type: list[int] = []

    _append_raw_slider_path(
        path.encode("ascii"),
        256.0,
        192.0,
        control_x,
        control_y,
        control_type,
    )

    assert list(zip(control_x, control_y, control_type, strict=True)) == [
        (
            point.pos.x,
            point.pos.y,
            -1 if point.path_type is None else point.path_type.kind.value,
        )
        for point in expected
    ]
