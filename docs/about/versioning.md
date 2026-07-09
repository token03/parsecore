# Versioning & algorithm tracking

parsecore follows [Semantic Versioning](https://semver.org/).

## Algorithm updates

parsecore tracks the **official osu! difficulty and performance algorithm**. When ppy
deploys a pp/star-rating rework, parsecore is updated to match the new deploy and the
parity suite is re-run to confirm bit-exactness.

The current target is the **2026 Q2 rework**, osu! deploy **`2026.702.1`**.

:::{note}
Because parsecore follows the official algorithm directly, its values can differ from
third-party calculators or the osu! website in the days after a rework those are often
still recalculating or running an older algorithm. Values for newly set in-game scores
are the source of truth.
:::

## Python support

parsecore supports **Python 3.10, 3.11, 3.12 and 3.13**.
