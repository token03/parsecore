"""Baseline osu!standard parsing and difficulty benchmarks."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import platform
import statistics
import struct
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from parsecore.Beatmap.beatmap import Beatmap as UserBeatmap
from parsecore.Performance.api import Beatmap as PreparedBeatmap
from parsecore.Performance.api import Difficulty
from parsecore.Performance.data.mode import GameMode
from parsecore.Performance.rulesets.osu.fast import FastDifficulty, StructuralFactors

DEFAULT_CORPUS = Path(__file__).resolve().parents[1] / "tests" / "data"
WORKLOADS = (
    "io",
    "parse",
    "prepare",
    "difficulty",
    "fast",
    "full",
    "fast_full",
    "path",
)
ALL_WORKLOADS = WORKLOADS

AR = 10.0
CS = 4.0
OD = 10.0
HP = 10.0


@dataclass(frozen=True, slots=True)
class CorpusCase:
    """One preloaded beatmap used by a benchmark workload."""

    path: Path
    data: bytes

    @property
    def map_id(self) -> int | None:
        """Return the numeric map ID encoded in the filename, if present."""
        try:
            return int(self.path.stem)
        except ValueError:
            return None


@dataclass(slots=True)
class Execution:
    """The timed stages and outputs produced by one workload pass."""

    stages: dict[str, float]
    payloads: list[bytes] | None = None
    parsed: list[Any] | None = None
    prepared: list[PreparedBeatmap] | None = None
    attributes: list[Any] | None = None


def _path_sort_key(path: Path) -> tuple[int, int, str]:
    try:
        return (0, int(path.stem), path.name)
    except ValueError:
        return (1, 0, path.name)


def discover_paths(corpus: str | Path = DEFAULT_CORPUS) -> list[Path]:
    """Return `.osu` files in deterministic filename order."""
    root = Path(corpus)
    if not root.is_dir():
        raise FileNotFoundError(f"beatmap corpus does not exist: {root}")

    paths = [path.resolve() for path in root.iterdir() if path.is_file() and path.suffix.lower() == ".osu"]
    paths.sort(key=_path_sort_key)
    if not paths:
        raise ValueError(f"beatmap corpus contains no .osu files: {root}")
    return paths


def load_cases(
        corpus: str | Path = DEFAULT_CORPUS,
        *,
        limit: int | None = None,
        map_ids: Sequence[int] | None = None,
) -> list[CorpusCase]:
    """Load and preload a deterministic subset of the beatmap corpus."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")

    paths = discover_paths(corpus)
    if map_ids is not None:
        wanted = set(map_ids)
        paths = [path for path in paths if _numeric_stem(path) in wanted]
        found = {_numeric_stem(path) for path in paths}
        missing = sorted(wanted - found)
        if missing:
            raise ValueError(f"beatmap IDs were not found: {', '.join(map(str, missing))}")

    if limit is not None:
        paths = paths[:limit]

    return [CorpusCase(path, path.read_bytes()) for path in paths]


def _numeric_stem(path: Path) -> int:
    try:
        return int(path.stem)
    except ValueError:
        return -1


def make_difficulty() -> Difficulty:
    """Return the fixed NM AR10/CS4/OD10/HP10 difficulty builder."""
    return (
        Difficulty()
        .mods(0)
        .ar(AR, fixed=True)
        .cs(CS, fixed=True)
        .hp(HP, fixed=True)
        .od(OD, fixed=True)
    )


def make_fast_difficulty() -> FastDifficulty:
    """Return the packed Numba calculator with the fixed benchmark settings."""
    return (
        FastDifficulty(max_objects=4096)
        .mods(0)
        .ar(AR, fixed=True)
        .cs(CS, fixed=True)
        .hp(HP, fixed=True)
        .od(OD, fixed=True)
    )


def _parse_case(case: CorpusCase) -> UserBeatmap:
    beatmap = UserBeatmap.from_bytes(case.data)
    if int(beatmap.mode) != int(GameMode.OSU):
        raise ValueError(f"unsupported native mode: {beatmap.mode.name.lower()}")
    return beatmap


def parse_cases(cases: Sequence[CorpusCase]) -> list[UserBeatmap]:
    """Parse preloaded beatmap bytes and require native osu!standard mode."""
    parsed: list[UserBeatmap] = []
    for case in cases:
        try:
            parsed.append(_parse_case(case))
        except Exception as exc:
            raise RuntimeError(f"parse failed for {case.path}") from exc
    return parsed


def _prepare_case(beatmap: UserBeatmap) -> PreparedBeatmap:
    return PreparedBeatmap.from_user_beatmap(beatmap)


def prepare_cases(parsed: Sequence[UserBeatmap], cases: Sequence[CorpusCase]) -> list[PreparedBeatmap]:
    """Prepare parsed maps for the existing performance calculator."""
    prepared: list[PreparedBeatmap] = []
    for beatmap, case in zip(parsed, cases, strict=True):
        try:
            prepared.append(_prepare_case(beatmap))
        except Exception as exc:
            raise RuntimeError(f"preparation failed for {case.path}") from exc
    return prepared


def calculate_cases(
        prepared: Sequence[PreparedBeatmap],
        cases: Sequence[CorpusCase],
        calculator: Any,
) -> list[Any]:
    """Calculate fixed-settings osu! difficulty attributes."""
    attributes: list[Any] = []
    for beatmap, case in zip(prepared, cases, strict=True):
        try:
            attributes.append(calculator.calculate(beatmap))
        except Exception as exc:
            raise RuntimeError(f"difficulty calculation failed for {case.path}") from exc
    return attributes


def execute_workload(
        cases: Sequence[CorpusCase],
        workload: str,
        *,
        calculator: Any | None = None,
        parsed: Sequence[UserBeatmap] | None = None,
        prepared: Sequence[PreparedBeatmap] | None = None,
) -> Execution:
    """Execute one timed workload pass."""
    if workload not in WORKLOADS:
        raise ValueError(f"unknown workload: {workload}")

    stages: dict[str, float] = {}
    payloads: list[bytes] | None = None
    parsed_result: list[UserBeatmap] | None = None
    prepared_result: list[PreparedBeatmap] | None = None
    attributes: list[Any] | None = None

    if workload == "fast_full":
        fast_calculator = calculator or make_fast_difficulty()
        started = time.perf_counter()
        attributes = [
            fast_calculator.calculate_factors_bytes(case.data)
            for case in cases
        ]
        stages["fast"] = time.perf_counter() - started
        return Execution(stages, attributes=attributes)

    if workload == "io":
        started = time.perf_counter()
        payloads = [case.path.read_bytes() for case in cases]
        stages["read"] = time.perf_counter() - started
        return Execution(stages, payloads=payloads)

    if workload in {"parse", "full", "fast_full", "path"}:
        if workload == "path":
            started = time.perf_counter()
            payloads = [case.path.read_bytes() for case in cases]
            stages["read"] = time.perf_counter() - started
        else:
            payloads = [case.data for case in cases]

        started = time.perf_counter()
        parsed_result = parse_cases(
            [CorpusCase(case.path, data) for case, data in zip(cases, payloads, strict=True)]
        )
        stages["parse"] = time.perf_counter() - started
    elif workload in {"prepare", "difficulty", "fast"}:
        if parsed is None:
            raise ValueError(f"{workload} workload requires parsed maps")
        parsed_result = list(parsed)

    if workload in {"prepare", "full", "fast_full", "path"}:
        if parsed_result is None:
            raise ValueError(f"{workload} workload did not produce parsed maps")
        started = time.perf_counter()
        prepared_result = prepare_cases(parsed_result, cases)
        stages["prepare"] = time.perf_counter() - started
    elif workload in {"difficulty", "fast"}:
        if prepared is None:
            raise ValueError("difficulty workload requires prepared maps")
        prepared_result = list(prepared)

    if workload in {"difficulty", "fast", "full", "fast_full", "path"}:
        if prepared_result is None:
            raise ValueError(f"{workload} workload did not produce prepared maps")
        started = time.perf_counter()
        attributes = calculate_cases(
            prepared_result,
            cases,
            calculator or (
                make_fast_difficulty()
                if workload in {"fast", "fast_full"}
                else make_difficulty()
            ),
        )
        stages["difficulty"] = time.perf_counter() - started

    return Execution(
        stages,
        payloads=payloads,
        parsed=parsed_result,
        prepared=prepared_result,
        attributes=attributes,
    )


def _execution_digest(execution: Execution) -> str:
    digest = hashlib.blake2b(digest_size=16)

    if execution.attributes is not None:
        for attrs in execution.attributes:
            names = (
                (
                    "stars", "aim", "speed", "slider", "snap", "agility",
                    "flow", "tap", "rhythm", "object_count",
                )
                if isinstance(attrs, StructuralFactors)
                else ("stars", "aim", "speed", "reading", "flashlight", "max_combo")
            )
            for name in names:
                digest.update(name.encode("ascii"))
                digest.update(struct.pack("<d", float(getattr(attrs, name))))
    elif execution.parsed is not None:
        for beatmap in execution.parsed:
            digest.update(struct.pack("<q", int(beatmap.format_version)))
            objects = beatmap.hit_objects.hit_objects
            digest.update(struct.pack("<q", len(objects)))
            for obj in objects:
                digest.update(struct.pack("<d", float(obj.start_time)))
                digest.update(type(obj.kind).__name__.encode("ascii"))
    elif execution.prepared is not None:
        for beatmap in execution.prepared:
            objects = beatmap.inner.hit_objects
            digest.update(struct.pack("<q", len(objects)))
            for obj in objects:
                digest.update(struct.pack("<d", float(obj.start_time)))
    elif execution.payloads is not None:
        for payload in execution.payloads:
            digest.update(struct.pack("<q", len(payload)))
            digest.update(payload[:16])
            digest.update(payload[-16:])

    return digest.hexdigest()


def _corpus_info(cases: Sequence[CorpusCase]) -> dict[str, Any]:
    ids = [case.map_id for case in cases if case.map_id is not None]
    sizes = [len(case.data) for case in cases]
    return {
        "maps": len(cases),
        "bytes": sum(sizes),
        "min_bytes": min(sizes),
        "max_bytes": max(sizes),
        "min_map_id": min(ids) if ids else None,
        "max_map_id": max(ids) if ids else None,
    }


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _git_head(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _environment(root: Path) -> dict[str, Any]:
    return {
        "python": sys.version,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "parsecore_version": _package_version("parsecore"),
        "numpy_version": _package_version("numpy"),
        "numba_version": _package_version("numba"),
        "git_head": _git_head(root),
    }


def _stats(samples: Sequence[float], map_count: int) -> dict[str, float]:
    median = statistics.median(samples)
    return {
        "min_seconds": min(samples),
        "max_seconds": max(samples),
        "mean_seconds": statistics.fmean(samples),
        "median_seconds": median,
        "maps_per_second": map_count / median if median > 0.0 else float("inf"),
        "milliseconds_per_map": median * 1000.0 / map_count,
    }


def _workload_report(
        cases: Sequence[CorpusCase],
        workload: str,
        *,
        repeat: int,
        warmup: int,
) -> dict[str, Any]:
    calculator = (
        make_fast_difficulty()
        if workload in {"fast", "fast_full"}
        else make_difficulty()
    )
    parsed: list[UserBeatmap] | None = None
    prepared: list[PreparedBeatmap] | None = None

    if workload == "prepare":
        parsed = parse_cases(cases)
    elif workload in {"difficulty", "fast"}:
        parsed = parse_cases(cases)
        prepared = prepare_cases(parsed, cases)

    for _ in range(warmup):
        execute_workload(
            cases,
            workload,
            calculator=calculator,
            parsed=parsed,
            prepared=prepared,
        )

    samples: list[dict[str, Any]] = []
    digests: set[str] = set()
    for _ in range(repeat):
        execution = execute_workload(
            cases,
            workload,
            calculator=calculator,
            parsed=parsed,
            prepared=prepared,
        )
        digest = _execution_digest(execution)
        digests.add(digest)
        total = sum(execution.stages.values())
        samples.append({"stages": execution.stages, "total_seconds": total})

    stage_names = sorted({name for sample in samples for name in sample["stages"]})
    total_samples = [sample["total_seconds"] for sample in samples]
    return {
        "repeat": repeat,
        "warmup": warmup,
        "map_count": len(cases),
        "digest": sorted(digests),
        "samples": samples,
        "total": _stats(total_samples, len(cases)),
        "stages": {
            name: _stats([sample["stages"][name] for sample in samples], len(cases))
            for name in stage_names
        },
    }


def _preflight_cases(
        cases: Sequence[CorpusCase],
        *,
        needs_preparation: bool,
) -> tuple[list[CorpusCase], list[CorpusCase], list[dict[str, str]]]:
    parseable: list[CorpusCase] = []
    preparable: list[CorpusCase] = []
    failures: list[dict[str, str]] = []
    for case in cases:
        try:
            parsed = _parse_case(case)
        except Exception as exc:
            failures.append({
                "map": case.path.name,
                "stage": "parse",
                "error": type(exc).__name__,
                "message": str(exc),
            })
            continue

        parseable.append(case)
        if not needs_preparation:
            continue

        try:
            _prepare_case(parsed)
        except Exception as exc:
            failures.append({
                "map": case.path.name,
                "stage": "prepare",
                "error": type(exc).__name__,
                "message": str(exc),
            })
            continue
        preparable.append(case)

    return parseable, preparable, failures


def run_benchmark(
        cases: Sequence[CorpusCase],
        *,
        workload: str = "full",
        repeat: int = 3,
        warmup: int = 1,
        continue_on_error: bool = True,
) -> dict[str, Any]:
    """Run baseline workloads and return a JSON-serializable report."""
    if not cases:
        raise ValueError("at least one beatmap is required")
    if repeat < 1:
        raise ValueError("repeat must be positive")
    if warmup < 0:
        raise ValueError("warmup cannot be negative")
    if workload == "all":
        selected: Sequence[str] = ALL_WORKLOADS
    elif workload in WORKLOADS:
        selected = (workload,)
    else:
        raise ValueError(f"unknown workload: {workload}")

    case_sets = {name: list(cases) for name in selected}
    failures: list[dict[str, str]] = []
    preflight_selected = [
        name for name in selected if name not in {"io", "fast_full"}
    ]
    if continue_on_error and preflight_selected:
        parseable, preparable, failures = _preflight_cases(
            cases,
            needs_preparation=any(
                name in {
                    "prepare", "difficulty", "fast", "full", "fast_full", "path"
                }
                for name in preflight_selected
            ),
        )
        for name in preflight_selected:
            case_sets[name] = (
                preparable
                if name in {"prepare", "difficulty", "fast", "full", "path"}
                else parseable
            )

    root = cases[0].path.parents[1]
    workloads: dict[str, Any] = {}
    for name in selected:
        selected_cases = case_sets[name]
        if not selected_cases:
            workloads[name] = {
                "map_count": 0,
                "skipped": "no maps passed preflight",
            }
            continue
        workloads[name] = _workload_report(
            selected_cases,
            name,
            repeat=repeat,
            warmup=warmup,
        )

    return {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "settings": {"ar": AR, "cs": CS, "od": OD, "hp": HP, "mods": "NM"},
        "corpus": _corpus_info(cases),
        "environment": _environment(root),
        "failures": failures,
        "workloads": workloads,
    }


def _print_report(report: dict[str, Any]) -> None:
    corpus = report["corpus"]
    print(f"Corpus: {corpus['maps']} maps, {corpus['bytes']} bytes")
    if report["failures"]:
        print(f"Preflight failures: {len(report['failures'])}")
        for failure in report["failures"]:
            print(
                f"  {failure['map']} ({failure['stage']}): "
                f"{failure['error']}: {failure['message']}"
            )
    for name, workload in report["workloads"].items():
        if "skipped" in workload:
            print(f"{name}: skipped ({workload['skipped']})")
            continue
        total = workload["total"]
        print(
            f"{name}: {total['median_seconds']:.6f}s median, "
            f"{total['maps_per_second']:.2f} maps/s, "
            f"digest={','.join(workload['digest'])}"
        )
        for stage, stats in workload["stages"].items():
            print(
                f"  {stage}: {stats['median_seconds']:.6f}s median, "
                f"{stats['maps_per_second']:.2f} maps/s"
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--map-id", type=int, action="append", dest="map_ids")
    parser.add_argument(
        "--workload",
        choices=("all", *WORKLOADS),
        default="full",
    )
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail instead of excluding maps rejected during preflight",
    )
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line benchmark."""
    args = _build_parser().parse_args(argv)
    cases = load_cases(args.corpus, limit=args.limit, map_ids=args.map_ids)
    report = run_benchmark(
        cases,
        workload=args.workload,
        repeat=args.repeat,
        warmup=args.warmup,
        continue_on_error=not args.strict,
    )
    _print_report(report)
    if args.output is not None:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
