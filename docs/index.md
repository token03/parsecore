---
sd_hide_title: true
---

```{raw} html
<div class="pc-hero">
  <h1>parsecore</h1>
  <p>The all-in-one Python library for osu! beatmap parsing, mod handling, and
  performance-point calculation — bit-exact with the official osu! algorithm.</p>
</div>
```

**parsecore** parses `.osu` files, models every osu! mod, and computes star ratings
and performance points for **all four rulesets** (osu!, osu!taiko, osu!catch,
osu!mania). Its results are verified **bit-for-bit identical** to the official osu!
implementation — currently the **2026 Q2 pp/star-rating rework** (`2026.702.1`).

::::{grid} 1 2 2 2
:gutter: 3
:class-container: sd-mb-4

:::{grid-item-card} 🚀 Installation
:link: installation
:link-type: doc

Get parsecore from PyPI and be ready in seconds.
:::

:::{grid-item-card} 🎯 Quickstart
:link: quickstart/pp
:link-type: doc

Compute pp and star ratings in just a few lines.
:::

:::{grid-item-card} 🧠 How pp works
:link: guide/how-pp-works
:link-type: doc

The parse → convert → skills → performance pipeline.
:::

:::{grid-item-card} 📖 API Reference
:link: api/performance
:link-type: doc

Every class and function, generated from the source.
:::

::::

## Why parsecore?

```{eval-rst}
- **Bit-exact** verified identical to the official osu! C# implementation across a
  4,400+ case test matrix (all rulesets, mods, converts, lazer & stable scores).
- **Up to date** implements the 2026 Q2 rework: the new Reading skill, Snap/Flow aim,
  deviation-based speed pp, reworked taiko rhythm, catch linear-spacing nerf.
- **Complete** parsing, mods, star rating and pp for osu!, taiko, catch and mania,
  including faithful osu! → other-mode converts.
- **Type-safe & dependency-light** fully typed, mypy-checked, pure-Python core.
```

```{toctree}
:hidden:
:caption: Getting Started

installation
quickstart/parsing
quickstart/star-rating
quickstart/pp
quickstart/converts
quickstart/mods
```

```{toctree}
:hidden:
:caption: Guide

guide/how-pp-works
guide/bit-exactness
guide/lazer-vs-stable
guide/converts
```

```{toctree}
:hidden:
:caption: API Reference

api/beatmap
api/mods
api/performance
```

```{toctree}
:hidden:
:caption: About

about/versioning
about/changelog
```
