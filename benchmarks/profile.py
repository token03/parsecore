"""cProfile entry point for the baseline osu!standard pipeline."""

from __future__ import annotations

import argparse
import cProfile
import pstats
from collections.abc import Sequence
from pathlib import Path

from .structural import (
    DEFAULT_CORPUS,
    WORKLOADS,
    execute_workload,
    load_cases,
    make_difficulty,
    make_fast_difficulty,
    parse_cases,
    prepare_cases,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--map-id", type=int, action="append", dest="map_ids")
    parser.add_argument("--workload", choices=WORKLOADS, default="full")
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("profile.prof"))
    parser.add_argument("--sort", default="cumulative")
    parser.add_argument("--lines", type=int, default=40)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Profile one baseline workload and write pstats output."""
    args = _build_parser().parse_args(argv)
    cases = load_cases(args.corpus, limit=args.limit, map_ids=args.map_ids)
    calculator = (
        make_fast_difficulty()
        if args.workload in {"fast", "fast_full"}
        else make_difficulty()
    )
    parsed = parse_cases(cases) if args.workload in {"prepare", "difficulty", "fast"} else None
    prepared = (
        prepare_cases(parsed, cases)
        if args.workload in {"difficulty", "fast"} and parsed is not None
        else None
    )

    for _ in range(args.warmup):
        execute_workload(
            cases,
            args.workload,
            calculator=calculator,
            parsed=parsed,
            prepared=prepared,
        )

    profiler = cProfile.Profile()
    profiler.enable()
    execute_workload(
        cases,
        args.workload,
        calculator=calculator,
        parsed=parsed,
        prepared=prepared,
    )
    profiler.disable()
    profiler.dump_stats(args.output)

    stats = pstats.Stats(profiler).strip_dirs().sort_stats(args.sort)
    stats.print_stats(args.lines)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
