# How the pp calculation works

`parsecore.Performance` is a pure-Python port of the **official osu! difficulty and
performance algorithms** (ppy/osu, deploy `2026.702.1`) not of a third-party
reimplementation.

## The pipeline

```{eval-rst}
1. **Parse** the ``.osu`` file is decoded into hit objects and timing/difficulty/effect
   points with osu!-faithful float semantics (positions and curve math run in 32-bit
   floats, exactly like the game client).
2. **Convert** if the target ruleset differs from the map's native mode, the map is
   converted first (taiko drum-roll splitting with scroll-speed effect points, catch
   mode flag, mania legacy pattern generator with osu!stable RNG).
3. **Preprocess** per-ruleset difficulty objects are built (distances, angles, rhythm
   groupings, effective BPM, ...).
4. **Skills** each ruleset evaluates its skills and aggregates them into the star
   rating:

   - osu!: Aim (snap/flow), Speed, Reading, Flashlight
   - taiko: Rhythm, Reading, Colour, Stamina
   - catch: Movement
   - mania: Strain (individual + overall)

5. **Performance** the score state (given explicitly or generated from accuracy and
   miss count) is combined with the difficulty attributes into pp, including miss
   penalties, slider-break estimation, and the classic/lazer scoring differences.
```

## What's new in the 2026 Q2 rework

parsecore implements the July 2026 rework: the AR/HD bonuses were replaced by a dedicated
**Reading** skill, aim was split into **Snap** and **Flow** components, speed pp became
**deviation-based**, taiko rhythm gained a long-gap penalty, and catch received a
linear-spacing nerf.

Every step reproduces the C# reference **including its floating-point quirks**, which is
what makes the results {doc}`bit-exact <bit-exactness>` rather than merely close.
