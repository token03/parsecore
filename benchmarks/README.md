# Baseline Benchmarks

The baseline measures the existing ParseCore osu!standard pipeline at fixed
AR10, CS4, OD10, HP10, NoMod settings. The default workload parses preloaded
bytes, prepares the public performance model, and calculates difficulty.

Run a small smoke benchmark:

```bash
uv run python -m benchmarks.structural --limit 3 --repeat 1 --warmup 0
```

Run the complete preloaded benchmark and save JSON metadata:

```bash
uv run python -m benchmarks.structural \
  --workload full \
  --output benchmarks/baseline.json
```

The harness preflights the corpus and reports maps rejected by the existing
calculator, allowing the remaining maps to be measured. Use `--strict` to
fail on the first rejected map.

Available workloads are:

- `io`: filesystem reads only
- `parse`: parse preloaded bytes
- `prepare`: prepare already parsed maps
- `difficulty`: calculate already prepared maps
- `fast`: calculate packed maps with the Numba structural backend
- `full`: parse, prepare, and calculate from preloaded bytes
- `fast_full`: parse and return five Numba structural factors
- `path`: read, parse, prepare, and calculate
- `all`: run every workload above

Profile a warmed calculation pass over ten maps:

```bash
uv run python -m benchmarks.profile \
  --workload full \
  --limit 10 \
  --output profile.prof
```

Numba compilation is not part of this baseline. Future accelerated reports
should keep cold compilation, warm single-map latency, and warm corpus
throughput as separate measurements.
