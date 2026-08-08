from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.structural import discover_paths, load_cases, run_benchmark


def test_discover_paths_sorts_numeric_stems(tmp_path: Path) -> None:
    (tmp_path / "10.osu").write_bytes(b"10")
    (tmp_path / "2.osu").write_bytes(b"2")
    (tmp_path / "metadata.osu").write_bytes(b"metadata")
    (tmp_path / "ignored.txt").write_bytes(b"ignored")

    assert [path.name for path in discover_paths(tmp_path)] == [
        "2.osu",
        "10.osu",
        "metadata.osu",
    ]


def test_load_cases_supports_id_selection() -> None:
    corpus = Path(__file__).parent / "data"
    if not corpus.is_dir():
        pytest.skip("the local beatmap corpus is not available")

    cases = load_cases(corpus, map_ids=[162])

    assert len(cases) == 1
    assert cases[0].map_id == 162
    assert cases[0].data


def test_parse_benchmark_report_has_stage_statistics() -> None:
    corpus = Path(__file__).parent / "data"
    if not corpus.is_dir():
        pytest.skip("the local beatmap corpus is not available")

    cases = load_cases(corpus, limit=1)
    report = run_benchmark(cases, workload="parse", repeat=1, warmup=0)
    workload = report["workloads"]["parse"]

    assert report["settings"] == {"ar": 10.0, "cs": 4.0, "od": 10.0, "hp": 10.0, "mods": "NM"}
    assert workload["map_count"] == 1
    assert workload["stages"]["parse"]["median_seconds"] >= 0.0
    assert len(workload["digest"]) == 1
