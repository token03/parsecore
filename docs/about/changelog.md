# Changelog

All notable changes to parsecore are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/).

## 1.0.1

### Fixed

- Repaired the `parsecore.Mods` package import (`game_mod_intermode` had shipped a
  duplicate module, which raised `ImportError`).

### Documentation

- Added Google-style docstrings across the entire package (100% coverage).
- Added this Sphinx documentation site.

## 1.0.0

Initial public release.

- `.osu` beatmap parsing (all sections) and re-encoding.
- Complete mod system for all four rulesets, with legacy and intermode representations.
- Star rating and pp for osu!, osu!taiko, osu!catch and osu!mania, implementing the
  **2026 Q2** rework and verified bit-exact against the official implementation.
- Faithful osu! → taiko / catch / mania converts.
- Lazer and stable scoring support.
