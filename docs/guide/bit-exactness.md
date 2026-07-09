# Bit-exactness & parity

parsecore's star ratings and pp values are **bit-for-bit identical** to the official osu!
implementation. This is the project's core promise.

## How it's achieved

Reproducing the reference *closely* is not enough parsecore reproduces it *exactly*,
including the floating-point behaviour of the original:

```{eval-rst}
- **f32 intermediates** positions, curve math and several constants are computed in
  32-bit floats, matching the game client (and rosu-pp's Rust ``f32``).
- **Explicit integer powers** ``x * x * x`` where the reference uses ``DiffUtils.Pow(x, 3)``,
  not ``math.pow`` (they can differ in the last bit).
- **IEEE semantics** division by zero, NaN handling and negative-base powers follow
  Rust/C# rules via dedicated helpers (``ieee_div``, ``rust_min``, ...), never Python's
  exceptions.
- **Exact RNG and sorting** the legacy converters use osu!stable's RNG in the exact call
  order, and the C# unstable sort is reproduced for nested slider objects.
```

## How it's verified

Correctness is enforced by a parity test suite that compares parsecore against an oracle
built from the official `ppy.osu.Game` packages (with rosu-pp as a secondary cross-check):

```{eval-rst}
- 4,400+ cases: star ratings and pp across all four rulesets
- extended mod matrix (EZ/HR/DT/NC/HT/HD/FL/TD/RX/AP/SO, key mods 1K-9K, combinations)
- all convert directions, native maps, edge-case and pathological maps
- randomized full score states, partial states, fails, lazer & stable scores
- **result: 0 differences every value bit-identical to the official implementation**
```

:::{important}
After a pp rework deploys, public calculators and bots that rely on outdated libraries
can disagree with parsecore. When in doubt: new scores set in-game receive exactly the
values parsecore computes.
:::
