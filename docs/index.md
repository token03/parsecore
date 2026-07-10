# Welcome to parsecore

parsecore is a modern, easy to use, feature-rich Python library for osu! beatmap
parsing, mod handling, and performance-point calculation.

**Features:**

- Bit-exact with the official osu! implementation — currently the
  **2026 Q2 pp/star-rating rework** (`2026.702.1`)
- Star rating and performance points for **all four rulesets**
  (osu!, osu!taiko, osu!catch, osu!mania)
- Faithful osu! → taiko / catch / mania converts
- Complete mod model — lazer and legacy mods, acronyms, settings
- Fully typed, mypy-checked, dependency-light pure-Python core

## Getting started

Is this your first time using the library? This is the place to get started!

- **First steps:** [Installation](installation) | [Quickstart](quickstart/pp)
- **Working with beatmaps:** [Parsing](quickstart/parsing) |
  [Star rating](quickstart/star-rating) | [Performance points](quickstart/pp)
- **Going further:** [Converts](quickstart/converts) | [Mods](quickstart/mods)

## Getting help

If you're having trouble with something, these resources might help.

- Read the [guide to how pp calculation works](guide/how-pp-works).
- Wondering why results differ from other tools? See
  [Bit-exactness & parity](guide/bit-exactness) and
  [Lazer vs stable scoring](guide/lazer-vs-stable).
- Try the search, or browse the API reference below.
- Report bugs in the [issue tracker](https://github.com/O-Lib/parsecore/issues).

## Manuals

These pages go into great detail about everything the library can do.

- [Beatmap API](api/beatmap) — parsing, sections, hit objects, encoding
- [Mods API](api/mods) — mods, acronyms, game modes
- [Performance API](api/performance) — difficulty and performance calculation

## Meta

If you're looking for something related to the project itself, it's here.

- [Versioning & algorithm tracking](about/versioning) — how parsecore follows osu! updates
- [Changelog](about/changelog) — the changelog for the library

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
