# Performance API

The public calculation API build a {class}`Beatmap`, then compute difficulty or
performance.

## Builders

```{eval-rst}
.. automodule:: parsecore.Performance.api
   :members:
   :member-order: bysource
```

## Score state

```{eval-rst}
.. automodule:: parsecore.Performance.data.score_state
   :members:
```

## Difficulty attributes

```{eval-rst}
.. autoclass:: parsecore.Performance.rulesets.osu.difficulty.OsuDifficultyAttributes
   :members:

.. autoclass:: parsecore.Performance.rulesets.taiko.difficulty.TaikoDifficultyAttributes
   :members:

.. autoclass:: parsecore.Performance.rulesets.catch.difficulty.CatchDifficultyAttributes
   :members:

.. autoclass:: parsecore.Performance.rulesets.mania.difficulty.ManiaDifficultyAttributes
   :members:
```

## Performance attributes

```{eval-rst}
.. autoclass:: parsecore.Performance.rulesets.osu.performance.OsuPerformanceAttributes
   :members:

.. autoclass:: parsecore.Performance.rulesets.taiko.performance.TaikoPerformanceAttributes
   :members:

.. autoclass:: parsecore.Performance.rulesets.catch.performance.CatchPerformanceAttributes
   :members:

.. autoclass:: parsecore.Performance.rulesets.mania.performance.ManiaPerformanceAttributes
   :members:
```

## Gradual calculation (catch)

```{eval-rst}
.. autoclass:: parsecore.Performance.rulesets.catch.gradual.CatchGradualDifficulty
   :members:

.. autoclass:: parsecore.Performance.rulesets.catch.gradual.CatchGradualPerformance
   :members:
```
